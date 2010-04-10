##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
##

"""
Implements a directory-backed addressbook hierarchy.
"""

__all__ = [
    "uidsResourceName",
   #"DirectoryAddressBookProvisioningResource",
    "DirectoryAddressBookHomeProvisioningResource",
    "DirectoryAddressBookHomeTypeProvisioningResource",
    "DirectoryAddressBookHomeUIDProvisioningResource",
    "DirectoryAddressBookHomeResource",
]

from twisted.internet.defer import succeed
from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.http import HTTPError
from twext.web2.dav.util import joinURL
from twext.web2.dav.resource import TwistedACLInheritable, TwistedQuotaRootProperty

from twistedcaldav.config import config
from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVResource
from twistedcaldav.resource import CalDAVResource, SearchAddressBookResource, SearchAllAddressBookResource, CalDAVComplianceMixIn
from twistedcaldav.directory.idirectory import IDirectoryService
from twistedcaldav.directory.resource import AutoProvisioningResourceMixIn

from twistedcaldav.directory.directory import DirectoryService

from twistedcaldav.report_addressbook_findshared import getReadWriteSharedAddressBookGroups, getReadOnlySharedAddressBookGroups, getWritersGroupForSharedAddressBookGroup

# Use __underbars__ convention to avoid conflicts with directory resource types.
uidsResourceName = "__uids__"


class DirectoryAddressBookProvisioningResource (
    AutoProvisioningResourceMixIn,
    ReadOnlyResourceMixIn,
    CalDAVComplianceMixIn,
    DAVResource,
):
    def defaultAccessControlList(self):
        return config.ProvisioningResourceACL

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inherritance rules, etc.
        return succeed(self.defaultAccessControlList())


class DirectoryAddressBookHomeProvisioningResource (DirectoryAddressBookProvisioningResource):
    """
    Resource which provisions address book home collections as needed.    
    """
    def __init__(self, directory, url):
        """
        @param directory: an L{IDirectoryService} to provision address books from.
        @param url: the canonical URL for the resource.
        """
        assert directory is not None
        assert url.endswith("/"), "Collection URL must end in '/'"

        DAVResource.__init__(self)

        self.directory = IDirectoryService(directory)
        self._url = url

        # FIXME: Smells like a hack
        directory.addressBookHomesCollection = self

        #
        # Create children
        #
        def provisionChild(name):
            self.putChild(name, self.provisionChild(name))

        for recordType in self.directory.recordTypes():
            provisionChild(recordType)

        provisionChild(uidsResourceName)

    def provisionChild(self, recordType):
        raise NotImplementedError("Subclass must implement provisionChild()")

    def url(self):
        return self._url

    def getChild(self, name):
        return self.putChildren.get(name, None)

    def listChildren(self):
        return self.directory.recordTypes()

    def principalCollections(self):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalCollections()

    def principalForRecord(self, record):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalForRecord(record)

    def homeForDirectoryRecord(self, record):
        uidResource = self.getChild(uidsResourceName)
        if uidResource is None:
            return None
        else:
            return uidResource.getChild(record.guid)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True


class DirectoryAddressBookHomeTypeProvisioningResource (DirectoryAddressBookProvisioningResource):
    """
    Resource which provisions address book home collections of a specific
    record type as needed.
    """
    def __init__(self, parent, recordType):
        """
        @param parent: the parent of this resource
        @param recordType: the directory record type to provision.
        """
        assert parent is not None
        assert recordType is not None

        DAVResource.__init__(self)

        self.directory = parent.directory
        self.recordType = recordType
        self._parent = parent

    def url(self):
        return joinURL(self._parent.url(), self.recordType)

    def getChild(self, name, record=None):
        self.provision()
        if name == "":
            return self

        if record is None:
            record = self.directory.recordWithShortName(self.recordType, name)
            if record is None:
                return None

        return self._parent.homeForDirectoryRecord(record)

    def listChildren(self):
        if config.EnablePrincipalListings:

            def _recordShortnameExpand():
                for record in self.directory.listRecords(self.recordType):
                    if record.enabledForAddressBooks:
                        for shortName in record.shortNames:
                            yield shortName

            return _recordShortnameExpand()
        else:
            # Not a listable collection
            raise HTTPError(responsecode.FORBIDDEN)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    def http_COPY(self, request):
        return responsecode.FORBIDDEN

    ##
    # ACL
    ##

    def principalCollections(self):
        return self._parent.principalCollections()

    def principalForRecord(self, record):
        return self._parent.principalForRecord(record)


class DirectoryAddressBookHomeUIDProvisioningResource (DirectoryAddressBookProvisioningResource):
    def __init__(self, parent):
        """
        @param parent: the parent of this resource
        """
        assert parent is not None

        DAVResource.__init__(self)

        self.directory = parent.directory
        self.parent = parent

    def url(self):
        return joinURL(self.parent.url(), uidsResourceName)

    def getChild(self, name, record=None):
        self.provision()
        if name == "":
            return self

        if record is None:
            record = self.directory.recordWithUID(name)
            if record is None:
                return None

        return self.provisionChild(name)

    def listChildren(self):
        # Not a listable collection
        raise HTTPError(responsecode.FORBIDDEN)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def principalCollections(self):
        return self.parent.principalCollections()

    def principalForRecord(self, record):
        return self.parent.principalForRecord(record)


class DirectoryAddressBookHomeResource (AutoProvisioningResourceMixIn, CalDAVResource):
    """
    Address book home collection resource.
    """
    def __init__(self, parent, record):
        """
        @param path: the path to the file which will back the resource.
        """
        assert parent is not None
        assert record is not None

        CalDAVResource.__init__(self)

        self.record = record
        self.parent = parent
        
        # Cache children which must be of a specific type
        childlist = ()
        if config.EnableSearchAddressBook and config.DirectoryAddressBook:
            childlist += (("search" , SearchAddressBookResource ), )
        if config.EnableSearchAllAddressBook:
            childlist += (("searchall" , SearchAllAddressBookResource ),)
        
        for name, cls in childlist:
            child = self.provisionChild(name)
            assert isinstance(child, cls), "Child %r not a %s: %r" % (name, cls.__name__, child)
            self.putChild(name, child)


    def provisionDefaultAddressBooks(self):
        self.provision()

        childName = "addressbook"
        child = self.provisionChild(childName)
        assert isinstance(child, CalDAVResource), "Child %r is not a %s: %r" % (childName, CalDAVResource.__name__, child) #@UndefinedVariable

        return child.createAddressBookCollection()

    def provisionChild(self, name):
        raise NotImplementedError("Subclass must implement provisionChild()")

    def url(self):
        return joinURL(self.parent.url(), self.record.guid)
        ##
        ## While the underlying primary location is GUID-based, we want
        ## the canonical user-facing location to be recordType &
        ## shortName-based, because that's friendlier.
        ##
        #return joinURL(self.parent.parent.getChild(self.record.recordType).url(), self.record.shortName)

    def canonicalURL(self, request):
        return succeed(self.url())
    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def owner(self, request):
        return succeed(davxml.HRef(self.principalForRecord().principalURL()))

    def _determineGroupAccessMode(self):
        """
        Determines whether this record (assumed to be a group) is provisioned in the list of read-write address books or read-only address books
        Returns:
            "ReadWrite", "ReadOnly" or None
        """
        
        members = getReadWriteSharedAddressBookGroups(self.record.service)      # list of members of the "ab_readwrite" group
        if self.record in members:                                              # membership must be explicit in the "ab_readwrite" group - no membership expansion is done
            return "ReadWrite"

        members = getReadOnlySharedAddressBookGroups(self.record.service)       # list of members of the "ab_readonly" group
        if self.record in members:                                              # membership must be explicit in the "ab_readonly" group - no membership expansion is done
            return "ReadOnly"
            
        return None
    
    def _getWritersURL(self):
        """
           Looks for a "-writers" group, and if found, extract the principal URL to it
        """

        writerRecord = getWritersGroupForSharedAddressBookGroup(self.record)
        if writerRecord == None:
            return None
        
        
        # TO-DO: Need better way to build the principal URL to the "-writers" group
        #principalURL = "/principals/__uids__/%s/" % writerRecord.guid
        
        principalURL = None
        for principalCollection in self.principalCollections():     # based on principalForCalendarUserAddress in resource.CalDAVResource
            groups = principalCollection.getChild(DirectoryService.recordType_groups)       # get only the "groups" collection within the parent collection
            if groups:
                p = groups.principalForRecord(writerRecord)
                if p is not None:
                    principalURL = p.principalURL()
                    break
        
        return principalURL
        
    def ownerPrincipal(self, request):
        return succeed(self.principalForRecord())

    def defaultAccessControlList(self):
        myPrincipal = self.principalForRecord()
        
        if self.record.recordType != DirectoryService.recordType_groups:
            # Original ACE logic
            aces = (
                # DAV:read access for authenticated users.
                davxml.ACE(
                    davxml.Principal(davxml.Authenticated()),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                    ),
                ),
                # Inheritable DAV:all access for the resource's associated principal.
                davxml.ACE(
                    davxml.Principal(davxml.HRef(myPrincipal.principalURL())),
                    davxml.Grant(davxml.Privilege(davxml.All())),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ),
            )
        else:
            # Determine access for this group (members are read-write or members are read-only)
            accMode = self._determineGroupAccessMode()
                        
            aces = ()
                 
            if accMode == "ReadWrite":
                aces += (davxml.ACE(
                    davxml.Principal(davxml.HRef(myPrincipal.principalURL())),
                    davxml.Grant(davxml.Privilege(davxml.All())),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ), )            
            elif accMode == "ReadOnly":
                aces += (davxml.ACE(
                    davxml.Principal(davxml.HRef(myPrincipal.principalURL())),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ), )          
                
                # Look for a "-writers" group and add those members with read-write access
                writerURL = self._getWritersURL()
                if writerURL:
                    aces += (davxml.ACE(
                        davxml.Principal(davxml.HRef(writerURL)),
                        davxml.Grant(davxml.Privilege(davxml.All())),
                        davxml.Protected(),
                        TwistedACLInheritable(),
                    ), )            
            else:
                pass

        # Give read access to config.ReadPrincipals
        aces += config.ReadACEs

        # Give all access to config.AdminPrincipals
        aces += config.AdminACEs
        
        return davxml.ACL(*aces)

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return succeed(self.defaultAccessControlList())

    def principalCollections(self):
        return self.parent.principalCollections()

    def principalForRecord(self):
        return self.parent.principalForRecord(self.record)

    ##
    # Quota
    ##

    def hasQuotaRoot(self, request):
        """
        @return: a C{True} if this resource has quota root, C{False} otherwise.
        """
        return self.hasDeadProperty(TwistedQuotaRootProperty) or config.UserQuota > 0
    
    def quotaRoot(self, request):
        """
        @return: a C{int} containing the maximum allowed bytes if this collection
            is quota-controlled, or C{None} if not quota controlled.
        """
        if self.hasDeadProperty(TwistedQuotaRootProperty):
            return int(str(self.readDeadProperty(TwistedQuotaRootProperty)))
        else:
            return config.UserQuota if config.UserQuota > 0 else None
