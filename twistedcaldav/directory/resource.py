##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Implements a directory-backed principal hierarchy.
"""

__all__ = [
    "DirectoryPrincipalFile",
    "DirectoryUserPrincipalProvisioningResource",
    "DirectoryGroupPrincipalProvisioningResource",
    "DirectoryResourcePrincipalProvisioningResource",
    "DirectoryPrincipalProvisioningResource",
]

from twisted.python import log
from twisted.internet import reactor
from twisted.internet import task
from twisted.internet.defer import succeed
from twisted.cred import credentials
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.static import DAVFile
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError
from twisted.web2.http import StatusResponse

from twistedcaldav import caldavxml
from twistedcaldav import customxml
from twistedcaldav.principalindex import GroupIndex
from twistedcaldav.principalindex import ResourceIndex
from twistedcaldav.principalindex import UserIndex
from twistedcaldav.resource import CalendarPrincipalCollectionResource
from twistedcaldav.static import CalendarPrincipalFile

import dsattributes
import opendirectory
import os
import unicodedata

class DirectoryPrincipalFile (CalendarPrincipalFile):
    """
    Directory principal resource.
    """
    def __init__(self, parent, path, url):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  This is the url which
            will be returned by L{principalURL}.
        """
        super(DirectoryPrincipalFile, self).__init__(path, url)

        self._parent = parent

    def checkCredentials(self, creds):
        """
        Check whether the provided credentials can be used to authenticate this prinicpal.
        
        @param creds: the L{ICredentials} for testing.
        @return:      True if the credentials match, False otherwise
        """

        # If there is no calendar principal URI then the calendar user is disabled.
        if not self.hasDeadProperty(customxml.TwistedCalendarPrincipalURI):
            return False

        if isinstance(creds, credentials.UsernamePassword):
            return opendirectory.authenticateUser(self._parent.directory, self.fp.basename(), creds.password)
        else:
            return False

    def directory(self):
        """
        Get the directory object used for directory operations.
        
        @return:      C{object} for the directory instance
        """

        return self._parent.directory

    def groupMembers(self):
        """
        See L{IDAVPrincipalResource.groupMembers}.
        """
        
        # Check for the list of group member GUIDs
        if self.hasDeadProperty(customxml.TwistedGroupMemberGUIDs):
            # Get the list of GUIDs from the WebDAV private property
            memberguids = self.readDeadProperty(customxml.TwistedGroupMemberGUIDs())
            guids = [str(e) for e in memberguids.children]
            
            # Try to find each GUID in collections
            result = []
            for guid in guids:
                uri = DirectoryTypePrincipalProvisioningResource.findAnyGUID(guid)
                if uri is not None:
                    result.append(uri)
            
            return result            

        return ()

    def groupMemberships(self):
        """
        See L{IDAVPrincipalResource.groupMemberships}.
        """
        
        # Find any groups that match this user's GUID
        guid = self.getGUID()
        return DirectoryTypePrincipalProvisioningResource.findAnyGroupGUID(guid)

    def getPropertyValue(self, cls):
        """
        Get the requested proeprty value or return empty string.
        """
        
        if self.hasDeadProperty(cls()):
            prop = self.readDeadProperty(cls())
            return str(prop)
        else:
            return ""
    
    def setPropertyValue(self, str, cls):
        """
        Set the requested property value or remove it if the value is empty.
        """

        if str:
            self.writeDeadProperty(cls.fromString(str))
        else:
            self.removeDeadProperty(cls())

    def getGUID(self):
        return self.getPropertyValue(customxml.TwistedGUIDProperty)
    
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname

        if namespace == caldavxml.caldav_namespace:
            if name == "calendar-user-address-set":
                return succeed(caldavxml.CalendarUserAddressSet(
                    *[davxml.HRef().fromString(uri) for uri in self.calendarUserAddresses()]
                ))

        return super(DirectoryPrincipalFile, self).readProperty(qname, request)

    def writeProperty(self, property, request):
        # This resource is read-only.
        raise HTTPError(StatusResponse(
            responsecode.FORBIDDEN,
            "Protected property %s may not be set." % (property.sname(),)
        ))

    def calendarUserAddresses(self):
        # Must have a valid calendar principal uri
        if self.hasDeadProperty(customxml.TwistedCalendarPrincipalURI):
            return (self.getPropertyValue(customxml.TwistedCalendarPrincipalURI),)
        else:
            # If there is no calendar principal URI then the calendar user is disabled so do not provide
            # a valid calendar address.
            return ()

    def matchesCalendarUserAddress(self, request, address):
        # By default we will always allow either a relative or absolute URI to the principal to
        # be supplied as a valid calendar user address.

        # Try calendar principal URI
        return self.hasDeadProperty(customxml.TwistedCalendarPrincipalURI) and (self.getPropertyValue(customxml.TwistedCalendarPrincipalURI) == address)

    def enable(self, calhome, enable):
        """
        Enable or disable this principal and access to any calendars owned by it.
        
        @param calhome: L{DAVFile} for the container of the calendar home of this user.
        @param enable: C{True} to enable, C{False} to disable.
        """
        # Get home collection resource
        calrsrc = calhome.getChild(self.principalUID())

        # Handle access for the calendar home
        if enable:
            calrsrc.disable(False)
        else:
            calrsrc.disable(True)

    def remove(self, calhome):
        """
        Remove this principal by hiding (archiving) any calendars owned by it. This is done
        by turning on the disabling and renaming the calendar home to ensure a future user
        with the same id won't see the old calendars.
        
        @param calhome: L{DAVFile} for the container of the calendar home of this user.
        """
        
        # Get home collection resource
        calrsrc = calhome.getChild(self.principalUID())

        # Disable access for the calendar home
        calrsrc.disable(True)
        
        # Rename the calendar home to the original name with the GUID appended
        newname = self.principalUID() + "-" + self.getPropertyValue(customxml.TwistedGUIDProperty)
        
        try:
            # Make sure the new name is not already in use
            if os.path.exists(newname):
                count = 1
                tempname = newname + "-%d"
                while(os.path.exists(tempname % count)):
                    count += 1
                newname = tempname % count 
            os.rename(calrsrc.fp.path, calrsrc.fp.sibling(newname).path)
        except OSError:
            log.msg("Directory: Failed to rename %s to %s when deleting a principal" %
                    (calrsrc.fp.path, calrsrc.fp.sibling(newname).path))
            
            # Remove the disabled property to prevent lock out in the future
            calrsrc.disable(False)

class DirectoryTypePrincipalProvisioningResource (CalendarPrincipalCollectionResource, DAVFile):
    """
    L{DAVFile} resource which provisions user L{CalendarPrincipalFile} resources
    as needed.
    
    This includes a periodic task for refreshing the cached data.
    """
    periodicSyncIntervalSeconds = 60.0
    
    typeUnknown  = 0
    typeUser     = 1
    typeGroup    = 2
    typeResource = 3

    def __init__(self, path, url):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  Provisioned child
            resources will use a URL based on C{url} as their primary URLs.
        @param directory: the reference to the directory to use
        """
        CalendarPrincipalCollectionResource.__init__(self, url)
        DAVFile.__init__(self, path)
        self.directory = None
        self.calendarhomeroot = None
        self.index = None
        self.type = DirectoryTypePrincipalProvisioningResource.typeUnknown

    def setup(self, directory):
        self.directory = directory

    def initialize(self, homeuri, home):
        """
        May be called during repository account initialization.
         
        @param homeuri: C{str} uri of the calendar home root.
        @param home: L{DAVFile} of the calendar home root.
        """
        
        # Make sure index is valid and sync with directory
        self.index.check()
        self.calendarhomeroot = (homeuri, home)

        #
        # There is a problem with the interaction of Directory Services and the
        # fork/fork process the server goes through to daemonize itself. For some
        # resaon, if DS is used before the fork, then calls to it afterwards all
        # return eServerSendError (-14740) errors.
        # 
        # To get around this we must not use opendirectory module calls here, as this
        # method gets run before the fork/fork. So instead, we schedule a sync
        # operation to occur one second after the reactor starts up - which is after
        # the fork/fork. The problem with this is that the http server is already up
        # and running at that point BEFORE any initially provisioning is done.
        #

        # Create a periodic sync operation to keep the cached user list
        # in sync with the directory server.
        def periodicSync(self):
            self.syncNames()
        
        # Add initial sync operation
        reactor.callLater(1.0, periodicSync, self) #@UndefinedVariable

        # Add periodic sync operations
        runner = task.LoopingCall(periodicSync, self)
        runner.start(DirectoryTypePrincipalProvisioningResource.periodicSyncIntervalSeconds, now=False)
    
    def listNames(self):
        """
        List all the names currently in the directory.

        @return: C{list} containing C{str}'s for each name found, or C{None} if failed.
        """
        raise NotImplementedError

    def listIndexAttributes(self):
        """
        List all the names currently in the directory with specific attributes needed for indexing.

        @return: C{list} containing C{tuple}'s of C{str}'s for each entry found, or C{None} if failed.
            The C{tuple} elements are: uid, guid, last-modified.
        """
        raise NotImplementedError

    def listCommonAttributes(self, names):
        """
        List specified names currently in the directory returning useful attributes.

        @param names: C{list} of record entries to list attributes for.
        @return: C{dict} with keys for each entry found, and a C{dict} value containg the attributes,
            or C{None} on failure.
        """
        raise NotImplementedError

    def validName(self, name):
        """
        Verify that the supplied name exists as an entry in the directory and that the
        name corresponds to one that can use the calendar.

        @param name: C{str} of the name to check.
        @return: C{True} if the name exists, C{False} otherwise.
        """
        raise NotImplementedError

    def directoryAttributes(self, name):
        """
        Return the attributes relevant to the directory entry.
        
        @param name: C{str} containing the name for the directory entry.
        @return: C{dict} containing the attribute key/value map.
        """
        raise NotImplementedError

    def syncNames(self):
        """
        Synchronize the data in the directory with the local cache of resources in the file system.
        """
        #log.msg("Directory: Synchronizing cache for %s" % (self.getTitle(),))

        # Get index entries from directory and from cache
        remoteindex = self.listIndexAttributes()
        localindex = self.index.listIndex()

        # Create dicts indexed by GUID for each
        remotedict = {}
        for entry in remoteindex:
            remotedict[entry[dsattributes.indexGUID]] = entry
        localdict = {}
        for entry in localindex:
            localdict[entry[dsattributes.indexGUID]] = entry

        # Extract list of GUIDs in each
        remoteguids = [entry[dsattributes.indexGUID] for entry in remoteindex]
        localguids = [entry[dsattributes.indexGUID] for entry in localindex]

        remoteguidset = set(remoteguids)
        remoteguids = None
        localguidset = set(localguids)
        localguids = None
        
        new_remote = list(remoteguidset.difference(localguidset))
        removed_remote = list(localguidset.difference(remoteguidset))
        
        # Remove old principals
        old_names = [localdict[guid][dsattributes.indexUID] for guid in removed_remote]
        old_names.sort()
        for name in old_names:
            self.removePrincipal(name, True)

        # Get new ones (but only those with a CalendarPrincipalURI attribute)
        new_names = [remotedict[guid][dsattributes.indexUID] for guid in new_remote if remotedict[guid][dsattributes.indexCalendarPrincipalURI]]

        # Get all the directory entries for the new ones in one go for better performance
        if new_names:
            new_entries = self.listCommonAttributes(new_names)
            if new_entries is not None:
                new_names = [n for n in new_entries.iterkeys()]
                new_names.sort()
                for name in new_names:
                    self.addPrincipal(name, attrs=new_entries[name], fast=True)
            
        # Look for changes in entries
        common_entries = list(remoteguidset.intersection(localguidset))
        for guid in common_entries:
            old = localdict[guid]
            new = remotedict[guid]
            if old != new:
                # Special case issue with unicode normalization of names
                if ((old[dsattributes.indexUID] != new [dsattributes.indexUID]) and
                    (unicodedata.normalize("NFKC", old[dsattributes.indexUID].decode("UTF-8")) ==
                     unicodedata.normalize("NFKC", new[dsattributes.indexUID].decode("UTF-8"))) and
                    (old[1:] == new[1:])):
                    continue
                
                self.changedPrincipal(old, new)
        
        # Commit index after all changes are done
        self.index.commit()

    def addPrincipal(self, name, attrs=None, fast=False):
        """
        Add a new principal resource to the server.
        
        @param name: C{str} containing the name of the resource to add.
        @param attrs: C{dict} directory attributes for this name, or C{None} if attributes need to be read in.
        @param fast: if C{True} then final commit is not done, if C{False} commit is done.
        """
        # This will create it
        child_fp = self.fp.child(name)
        #assert not child_fp.exists()

        assert self.exists()
        assert self.isCollection()

        child_fp.open("w").close()
        
        # Now update the principal's cached data
        self.updatePrincipal(name, attrs=attrs, fast=fast, new=True, nolog=True)
        
        log.msg("Directory: Add %s to %s" % (name, self.getTitle()))
    
    def changedPrincipal(self, old, new, fast=False):
        """
        Change a new principal resource to sync with directory.
        
        @param old: C{str} containing the name of the original resource.
        @param new: C{str} containing the name of the new resource.
        @param fast: if C{True} then final commit is not done, if C{False} commit is done.
        """
        # Look for change to calendar enabled state
        
        # See if the name changed because that is a real pain!
        if ((old[dsattributes.indexUID] != new[dsattributes.indexUID]) and
            (unicodedata.normalize("NFKC", old[dsattributes.indexUID].decode("UTF-8")) ==
             unicodedata.normalize("NFKC", new[dsattributes.indexUID].decode("UTF-8")))):
            self.renamePrincipal(old[dsattributes.indexUID], new[dsattributes.indexUID])
        
        # See if change in enable state
        enable_state = old[dsattributes.indexCalendarPrincipalURI] != new[dsattributes.indexCalendarPrincipalURI]
        
        # Do update (no log message if enable state is being changed as that will generate a log message itself)
        self.updatePrincipal(new[dsattributes.indexUID], nolog=enable_state)

        # Look for change in calendar enable state
        if enable_state:
            self.enablePrincipal(new[dsattributes.indexUID], len(new[dsattributes.indexCalendarPrincipalURI]) != 0)

    def renamePrincipal(self, old, new):
        """
        Change a principal resource name to sync with directory.
        
        @param old: C{str} containing the name of the original resource.
        @param new: C{str} containing the name of the new resource.
        """
        log.msg("Directory: Renamed Principal %s to %s in %s" % (old, new, self.getTitle()))
        raise NotImplementedError
    
    def updatePrincipal(self, name, attrs = None, fast=False, new=False, nolog=False):
        """
        Update details about the named principal in the principal's own property store
        and the principal collection index.
        
        @param name: C{str} containing the principal name to update.
        @param attrs: C{dict} directory attributes for this name, or C{None} if attributes need to be read in.
        @param fast: if C{True} then final commit is not done, if C{False} commit is done.
        @param new: C{True} when this update is the result of adding a new principal,
            C{False} otherwise.
        """
        # Get attributes from directory
        if attrs is None:
            attrs = self.directoryAttributes(name)
        realname = attrs.get(dsattributes.attrRealName, None)
        guid = attrs.get(dsattributes.attrGUID, None)
        lastModified = attrs.get(dsattributes.attrLastModified, None)
        principalurl = attrs.get(dsattributes.attrCalendarPrincipalURI, None)

        # Do provisioning (if the principal is a resource we will turn on the auto-provisioning option)
        principal = self.getChild(name)
        if principal is None:
            log.msg("Directory: Failed to update missing principal: %s in %s" % (name, self.getTitle()))
            return

        if (new):
            principal.provisionCalendarAccount(name, None, True, None, self.calendarhomeroot,
                                               None, None, ["calendar"],
                                               self.type == DirectoryTypePrincipalProvisioningResource.typeResource, 
                                               self.type == DirectoryTypePrincipalProvisioningResource.typeUser)
        
        # Add directory specific attributes to principal
        principal.setPropertyValue(realname, davxml.DisplayName)
        principal.setPropertyValue(guid, customxml.TwistedGUIDProperty)
        principal.setPropertyValue(lastModified, customxml.TwistedLastModifiedProperty)
        principal.setPropertyValue(principalurl, customxml.TwistedCalendarPrincipalURI)
        
        # Special for group
        if self.type == DirectoryTypePrincipalProvisioningResource.typeGroup:
            # Get comma separated list of members and split into a list
            groupmembers = attrs.get(dsattributes.attrGroupMembers, None)
            if isinstance(groupmembers, list):
                members = groupmembers
            elif isinstance(groupmembers, str):
                members = [groupmembers]
            else:
                members = []
            
            # Create and write the group property
            children = [customxml.TwistedGUIDProperty.fromString(s) for s in members]
            principal.writeDeadProperty(customxml.TwistedGroupMemberGUIDs(*children))
        
        # Do index
        self.index.addPrincipal(name, principal, fast)

        if not nolog:
            log.msg("Directory: Updated %s in %s" % (name, self.getTitle()))
    
    def enablePrincipal(self, name, enable):
        """
        Enable or disable calendar access for this principal.
        
        @param enable: C{True} to enable, C{False} to disable
        """
        principal = self.getChild(name)
        if principal is None:
            log.msg("Directory: Failed to enable/disable missing principal: %s in %s" % (name, self.getTitle()))
            return

        if enable:
            principal.enable(self.calendarhomeroot[1], True)
            log.msg("Directory: Enabled %s in %s" % (name, self.getTitle()))
        else:
            principal.enable(self.calendarhomeroot[1], False)
            log.msg("Directory: Disabled %s in %s" % (name, self.getTitle()))

    def removePrincipal(self, name, fast=False):
        """
        Remove a principal from the cached resources.
        
        @param name: C{str} containing the name of the principal to remove.
        @param fast: if C{True} then final commit is not done, if C{False} commit is done.
        """
        
        # Get the principal to 'hide' its calendars
        principal = self.getChild(name)
        if principal is None:
            log.msg("Directory: Failed to remove missing principal: %s in %s" % (name, self.getTitle()))
        else:
            principal.remove(self.calendarhomeroot[1])

        # Now remove the principal resource itself
        child_fp = self.fp.child(name)
        if child_fp.exists():
            os.remove(child_fp.path)

        # Do index
        self.index.deleteName(name, fast)

        log.msg("Directory: Delete %s from %s" % (name, self.getTitle()))
    
    @staticmethod
    def findAnyGUID(guid):
        """
        Find the principal associated with the specified GUID.

        @param guid: the C{str} containing the GUID to match.
        @return: C{str} with matching principal URI, or C{None}
        """
        for url in CalendarPrincipalCollectionResource.principleCollectionSet.keys():
            try:
                pcollection = CalendarPrincipalCollectionResource.principleCollectionSet[url]
                if isinstance(pcollection, DirectoryTypePrincipalProvisioningResource):
                    principal = pcollection.findGUID(guid)
                    if principal is not None:
                        return principal
            except ReferenceError:
                pass

        return None

    def findGUID(self, guid):
        """
        See if a principal with the specified GUID exists and if so return its principal URI.
        
        @param guid: the C{str} containing the GUID to match.
        @return: C{str} with matching principal URI, or C{None}
        """
        name = self.index.nameFromGUID(guid)
        if name is not None:
            principal = self.getChild(name)
            return principal.principalURL()
        else:
            return None

    @staticmethod
    def findAnyGroupGUID(clazz, guid):
        """
        Find the principals containing the specified GUID as a group member.

        @param guid: the C{str} containing the GUID to match.
        @return: C{list} with matching principal URIs
        """
        
        result = []
        for url in CalendarPrincipalCollectionResource.principleCollectionSet.keys():
            try:
                pcollection = CalendarPrincipalCollectionResource.principleCollectionSet[url]
                if isinstance(pcollection, DirectoryTypePrincipalProvisioningResource):
                    result.extend(pcollection.findGroupGUID(guid))
            except ReferenceError:
                pass

        return result

    def findGroupGUID(self, guid):
        """
        Find principals with the specified GUID as a group member.
        
        @param guid: the C{str} containing the GUID to match.
        @return: C{list} with matching principal URIs
        """
        # Only both for group collections
        if self.type != DirectoryTypePrincipalProvisioningResource.typeGroup:
            return []
        
        result = []
        for name in self.listChildren():
            principal = self.getChild(name)
            if principal.hasDeadProperty(customxml.TwistedGroupMemberGUIDs):
                guids = principal.readDeadProperty(customxml.TwistedGroupMemberGUIDs)
                for g in guids.children:
                    if str(g) == guid:
                        result.append(principal.principalURL())
                        break

        return result

    def isCollection(self):
        """
        See L{IDAVResource.isCollection}.
        """
        return True

    def getChild(self, name):
        """
        Look up a child resource.
        @return: the child of this resource with the given name.
        """
        if name == "":
            return self

        child = self.putChildren.get(name, None)
        if child: return child

        child_fp = self.fp.child(name)
        if child_fp.exists():
            return DirectoryPrincipalFile(self, child_fp.path, joinURL(self._url, name))
        else:
            return None

    def principalSearchPropertySet(self):
        """
        See L{IDAVResource.principalSearchPropertySet}.        
        """
        return davxml.PrincipalSearchPropertySet(
            davxml.PrincipalSearchProperty(
                davxml.PropertyContainer(
                    davxml.DisplayName()
                ),
                davxml.Description(
                    davxml.PCDATAElement("Display Name"),
                    **{"xml:lang":"en"}
                ),
            ),
            davxml.PrincipalSearchProperty(
                davxml.PropertyContainer(
                    caldavxml.CalendarUserAddressSet()
                ),
                davxml.Description(
                    davxml.PCDATAElement("Calendar User Addresses"),
                    **{"xml:lang":"en"}
                ),
            ),
        )

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            # TODO: Fix this - not sure how to get URI for second argument of __init__
            return CalendarPrincipalFile(path, "")

    def http_PUT        (self, request): return responsecode.FORBIDDEN
    def http_MKCOL      (self, request): return responsecode.FORBIDDEN
    def http_MKCALENDAR (self, request): return responsecode.FORBIDDEN

class DirectoryUserPrincipalProvisioningResource (DirectoryTypePrincipalProvisioningResource):
    """
    L{DAVFile} resource which provisions user L{CalendarPrincipalFile} resources
    as needed.
    """
    def __init__(self, path, url):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  Provisioned child
            resources will use a URL based on C{url} as their primary URLs.
        @param directory: the reference to the directory to use
        """
        DirectoryTypePrincipalProvisioningResource.__init__(self, path, url)
        self.index = UserIndex(self)
        self.type = DirectoryTypePrincipalProvisioningResource.typeUser

    def listNames(self):
        """
        List all the names currently in the directory.

        @return: C{list} containg C{str}'s for each name found, or C{None} if failed.
        """

        # Lookup all users
        return [i[0] for i in opendirectory.listUsers(self.directory)]
 
    def listIndexAttributes(self):
        """
        List all the names currently in the directory with specific attributes needed for indexing.

        @return: C{list} containing C{tuple}'s of C{str}'s for each entry found, or C{None} if failed.
            The C{tuple} elements are: uid, guid, last-modified.
        """
        return opendirectory.listUsers(self.directory)

    def listCommonAttributes(self, names):
        """
        List specified names currently in the directory returning useful attributes.

        @param names: C{list} of record entries to list attributes for.
        @return: C{dict} with keys for each entry found, and a C{dict} value containg the attributes,
            or C{None} on failure.
        """
        return opendirectory.listUsersWithAttributes(self.directory, names)

    def validName(self, name):
        """
        Verify that the supplied name exists as an entry in the directory.

        @param name: C{str} of the namer to check.
        @return: C{True} if the name exists, C{False} otherwise.
        """
        return opendirectory.checkUser(self.directory, name)

    def directoryAttributes(self, name):
        """
        Return the attributes relevant to the directory entry.
        
        @param name: C{str} containing the name for the directory entry.
        @return: C{dict} containing the attribute key/value map.
        """
        result = opendirectory.listUsersWithAttributes(self.directory, [name])
        if result:
            return result[name]
        else:
            return None

    def getTitle(self):
        return "User Principals"

class DirectoryGroupPrincipalProvisioningResource (DirectoryTypePrincipalProvisioningResource):
    """
    L{DAVFile} resource which provisions user L{CalendarPrincipalFile} resources
    as needed.
    """
    def __init__(self, path, url):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  Provisioned child
            resources will use a URL based on C{url} as their primary URLs.
        @param directory: the reference to the directory to use
        """
        DirectoryTypePrincipalProvisioningResource.__init__(self, path, url)
        self.index = GroupIndex(self)
        self.type = DirectoryTypePrincipalProvisioningResource.typeGroup

    def listNames(self):
        """
        List all the names currently in the directory.

        @return: C{list} containg C{str}'s for each name found, or C{None} if failed.
        """

        # Lookup all users
        return [i[0] for i in opendirectory.listGroups(self.directory)]
 
    def listIndexAttributes(self):
        """
        List all the names currently in the directory with specific attributes needed for indexing.

        @return: C{list} containing C{tuple}'s of C{str}'s for each entry found, or C{None} if failed.
            The C{tuple} elements are: uid, guid, last-modified.
        """
        return opendirectory.listGroups(self.directory)

    def listCommonAttributes(self, names):
        """
        List specified names currently in the directory returning useful attributes.

        @param names: C{list} of record entries to list attributes for.
        @return: C{dict} with keys for each entry found, and a C{dict} value containg the attributes,
            or C{None} on failure.
        """
        return opendirectory.listGroupsWithAttributes(self.directory, names)

    def validName(self, name):
        """
        Verify that the supplied name exists as an entry in the directory.

        @param name: C{str} of the namer to check
        @return: C{True} if the name exists, C{False} otherwise
        """
        return opendirectory.checkGroup(self.directory, name)

    def directoryAttributes(self, name):
        """
        Return the attributes relevant to the directory entry.
        
        @param name: C{str} containing the name for the directory entry.
        @return: C{dict} containing the attribute key/value map.
        """
        result = opendirectory.listGroupsWithAttributes(self.directory, [name])
        if result:
            return result[name]
        else:
            return None

    def getTitle(self):
        return "Group Principals"

class DirectoryResourcePrincipalProvisioningResource (DirectoryTypePrincipalProvisioningResource):
    """
    L{DAVFile} resource which provisions user L{CalendarPrincipalFile} resources
    as needed.
    """
    def __init__(self, path, url):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  Provisioned child
            resources will use a URL based on C{url} as their primary URLs.
        @param directory: the reference to the directory to use
        """
        DirectoryTypePrincipalProvisioningResource.__init__(self, path, url)
        self.index = ResourceIndex(self)
        self.type = DirectoryTypePrincipalProvisioningResource.typeResource

    def listNames(self):
        """
        List all the names currently in the directory.

        @return: C{list} containg C{str}'s for each name found, or C{None} if failed.
        """

        # Lookup all users
        return [i[0] for i in opendirectory.listResources(self.directory)]
 
    def listIndexAttributes(self):
        """
        List all the names currently in the directory with specific attributes needed for indexing.

        @return: C{list} containing C{tuple}'s of C{str}'s for each entry found, or C{None} if failed.
            The C{tuple} elements are: uid, guid, last-modified.
        """
        return opendirectory.listResources(self.directory)

    def listCommonAttributes(self, names):
        """
        List specified names currently in the directory returning useful attributes.

        @param names: C{list} of record entries to list attributes for.
        @return: C{dict} with keys for each entry found, and a C{dict} value containg the attributes,
            or C{None} on failure.
        """
        return opendirectory.listResourcesWithAttributes(self.directory, names)

    def validName(self, name):
        """
        Verify that the supplied name exists as an entry in the directory.

        @param name: C{str} of the namer to check
        @return: C{True} if the name exists, C{False} otherwise
        """
        return opendirectory.checkResource(self.directory, name)

    def directoryAttributes(self, name):
        """
        Return the attributes relevant to the directory entry.
        
        @param name: C{str} containing the name for the directory entry.
        @return: C{dict} containing the attribute key/value map.
        """
        result = opendirectory.listResourcesWithAttributes(self.directory, [name])
        if result:
            return result[name]
        else:
            return None

    def getTitle(self):
        return "Resource Principals"

class DirectoryPrincipalProvisioningResource (DAVFile):
    """
    L{DAVFile} resource which provisions calendar principal resources as needed.
    """
    def __init__(self, path, url, params={}):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  Provisioned child
            resources will use a URL based on C{url} as their primary URLs.
        """
        super(DirectoryPrincipalProvisioningResource, self).__init__(path)

        assert self.exists(), "%s should exist" % (self,)
        assert self.isCollection(), "%s should be a collection" % (self,)

        # Extract parameters
        if (params.has_key("DirectoryNode")):
            self.directory = opendirectory.odInit(params["DirectoryNode"])
            if self.directory is None:
                raise ValueError("Failed to open Open Directory Node: %s" % (params["DirectoryNode"],))
        else:
            raise ValueError("DirectoryPrincipalProvisioningResource must be configured with an Open Directory Node")

        # Create children
        for name, clazz in (
            ("users" , DirectoryUserPrincipalProvisioningResource),
            ("groups" , DirectoryGroupPrincipalProvisioningResource),
            ("resources" , DirectoryResourcePrincipalProvisioningResource),
        ):
            child_fp = self.fp.child(name)
            if not child_fp.exists(): child_fp.makedirs()
            principalCollection = clazz(child_fp.path, joinURL(url, name) + "/")
            principalCollection.setup(self.directory)
            self.putChild(name, principalCollection)

    def isCollection(self):
        """
        See L{IDAVResource.isCollection}.
        """
        return True

    def initialize(self, homeuri, home):
        """
        May be called during repository account initialization.
        This implementation does nothing.
        
        @param homeuri: C{str} uri of the calendar home root.
        @param home: L{DAVFile} of the calendar home root.
        """
        for name in ("users", "groups", "resources",):
            self.getChild(name).initialize(joinURL(homeuri, name), home.getChild(name))
    
    def createSimilarFile(self, path):
        return DAVFile(path)

    def render(self, request):
        return StatusResponse(
            responsecode.OK,
            "This collection contains principal resources",
            title=self.displayName()
        )
