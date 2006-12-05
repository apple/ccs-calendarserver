##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
CalDAV-aware static resources.
"""

__all__ = [
    "CalDAVFile",
    "ScheduleInboxFile",
    "ScheduleOutboxFile",
    "CalendarHomeFile",
    "CalendarHomeProvisioningFile",
    "CalendarPrincipalCollectionFile",
]

import os
import errno
from urlparse import urlsplit

from twisted.internet.defer import deferredGenerator, fail, succeed, waitForDeferred
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.http import HTTPError, StatusResponse
from twisted.web2.dav import davxml
from twisted.web2.dav.fileop import mkcollection, rmdir
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.idav import IDAVResource
from twisted.web2.dav.resource import TwistedACLInheritable, TwistedQuotaRootProperty, davPrivilegeSet
from twisted.web2.dav.util import parentForURL, joinURL, bindMethods

from twistedcaldav import caldavxml
from twistedcaldav import customxml
from twistedcaldav.extensions import ReadOnlyResourceMixIn
from twistedcaldav.ical import Component as iComponent
from twistedcaldav.ical import Property as iProperty
from twistedcaldav.index import Index, IndexSchedule, db_basename
from twistedcaldav.resource import CalDAVResource, isNonCalendarCollectionParentResource
from twistedcaldav.resource import ScheduleInboxResource, ScheduleOutboxResource
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.extensions import DAVFile
from twistedcaldav.dropbox import DropBox
from twistedcaldav.directory.idirectory import IDirectoryService

class CalDAVFile (CalDAVResource, DAVFile):
    """
    CalDAV-accessible L{DAVFile} resource.
    """
    def __repr__(self):
        if self.isCalendarCollection():
            return "<%s (calendar collection): %s>" % (self.__class__.__name__, self.fp.path)
        else:
            return super(CalDAVFile, self).__repr__()

    ##
    # CalDAV
    ##

    def createCalendar(self, request):
        #
        # request object is required because we need to validate against parent
        # resources, and we need the request in order to locate the parents.
        #

        if self.fp.exists():
            log.err("Attempt to create collection where file exists: %s" % (self.fp.path,))
            raise HTTPError(StatusResponse(responsecode.NOT_ALLOWED, "File exists"))

        if not os.path.isdir(os.path.dirname(self.fp.path)):
            log.err("Attempt to create collection with no parent: %s" % (self.fp.path,))
            raise HTTPError(StatusResponse(responsecode.CONFLICT, "No parent collection"))

        #
        # Verify that no parent collection is a calendar also
        #
        log.msg("Creating calendar collection %s" % (self,))

        def _defer(parent):
            if parent is not None:
                log.err("Cannot create a calendar collection within a calendar collection %s" % (parent,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldavxml.caldav_namespace, "calendar-collection-location-ok")
                ))
    
            return self.createCalendarCollection()
            
        parent = self._checkParents(request, isNonCalendarCollectionParentResource)
        parent.addCallback(_defer)
        return parent

    def createCalendarCollection(self):
        #
        # Create the collection once we know it is safe to do so
        #
        return self.createSpecialCollection(davxml.ResourceType.calendar)
    
    def createSpecialCollection(self, resourceType=None):
        #
        # Create the collection once we know it is safe to do so
        #
        def onCollection(status):
            if status != responsecode.CREATED:
                raise HTTPError(status)
    
            self.writeDeadProperty(resourceType)
            return status
        
        def onError(f):
            try:
                rmdir(self.fp)
            except Exception, e:
                log.err("Unable to clean up after failed MKCOL (special resource type: %s): %s" % (e, resourceType,))
            return f

        d = mkcollection(self.fp)
        if resourceType is not None:
            d.addCallback(onCollection)
        d.addErrback(onError)
        return d
 
    def iCalendarRolledup(self, request):
        if self.isPseudoCalendarCollection():
            # Generate a monolithic calendar
            calendar = iComponent("VCALENDAR")
            calendar.addProperty(iProperty("VERSION", "2.0"))

            # Do some optimisation of access control calculation by determining any inherited ACLs outside of
            # the child resource loop and supply those to the checkPrivileges on each child.
            filteredaces = waitForDeferred(self.inheritedACEsforChildren(request))
            yield filteredaces
            filteredaces = filteredaces.getResult()

            # Must verify ACLs which means we need a request object at this point
            for name, uid, type in self.index().search(None): #@UnusedVariable
                try:
                    child = waitForDeferred(request.locateChildResource(self, name))
                    yield child
                    child = child.getResult()
                    child = IDAVResource(child)
                except TypeError:
                    child = None
    
                if child is not None:
                    # Check privileges of child - skip if access denied
                    try:
                        d = waitForDeferred(child.checkPrivileges(request, (davxml.Read(),), inherited_aces=filteredaces))
                        yield d
                        d.getResult()
                    except:
                        continue
                    subcalendar = self.iCalendar(name)
                    assert subcalendar.name() == "VCALENDAR"

                    for component in subcalendar.subcomponents():
                        calendar.addComponent(component)
                        
            yield calendar
            return

        yield fail(HTTPError((ErrorResponse(responsecode.BAD_REQUEST))))

    iCalendarRolledup = deferredGenerator(iCalendarRolledup)

    def iCalendarText(self, name=None):
        if self.isPseudoCalendarCollection():
            if name is None:
                return str(self.iCalendar())

            try:
                calendar_file = self.fp.child(name).open()
            except IOError, e:
                if e[0] == errno.ENOENT: return None
                raise

        elif self.isCollection():
            return None

        else:
            if name is not None:
                raise AssertionError("name must be None for non-collection calendar resource")

            calendar_file = self.fp.open()

        # FIXME: This is blocking I/O
        try:
            calendar_data = calendar_file.read()
        finally:
            calendar_file.close()

        return calendar_data

    def iCalendarXML(self, name=None):
        return caldavxml.CalendarData.fromCalendarData(self.iCalendarText(name))

    def supportedPrivileges(self, request):
        # read-free-busy support on calendar collection and calendar object resources
        if self.isCollection():
            return succeed(calendarPrivilegeSet)
        else:
            def _callback(parent):
                if parent and isCalendarCollectionResource(parent):
                    return succeed(calendarPrivilegeSet)
                else:
                    return super(CalDAVFile, self).supportedPrivileges(request)

            d = self.locateParent(request, request.urlForResource(self))
            d.addCallback(_callback)
            return d
        
        return super(CalDAVFile, self).supportedPrivileges(request)

    ##
    # Public additions
    ##

    def index(self):
        """
        Obtains the index for a calendar collection resource.
        @return: the index object for this resource.
        @raise AssertionError: if this resource is not a calendar collection
            resource.
        """
        return Index(self)

    ##
    # File
    ##

    def listChildren(self):
        return [
            child for child in super(CalDAVFile, self).listChildren()
            if child != db_basename
        ]

    ##
    # Quota
    ##

    def quotaSize(self, request):
        """
        Get the size of this resource.
        TODO: Take into account size of dead-properties. Does stat
            include xattrs size?

        @return: an L{Deferred} with a C{int} result containing the size of the resource.
        """
        if self.isCollection():
            def walktree(top, top_level = False):
                """
                Recursively descend the directory tree rooted at top,
                calling the callback function for each regular file
                
                @param top: L{FilePath} for the directory to walk.
                """
            
                total = 0
                for f in top.listdir():
    
                    # Ignore the database
                    if top_level and f == db_basename:
                        continue
    
                    child = top.child(f)
                    if child.isdir():
                        # It's a directory, recurse into it
                        result = waitForDeferred(walktree(child))
                        yield result
                        total += result.getResult()
                    elif child.isfile():
                        # It's a file, call the callback function
                        total += child.getsize()
                    else:
                        # Unknown file type, print a message
                        pass
            
                yield total
            
            walktree = deferredGenerator(walktree)
    
            return walktree(self.fp, True)
        else:
            return succeed(self.fp.getsize())

    ##
    # Utilities
    ##

    @staticmethod
    def _isChildURI(request, uri, immediateChild=True):
        """
        Verify that the supplied URI represents a resource that is a child
        of the request resource.
        @param request: the request currently in progress
        @param uri: the URI to test
        @return: True if the supplied URI is a child resource
                 False if not
        """
        if uri is None: return False

        #
        # Parse the URI
        #
    
        (scheme, host, path, query, fragment) = urlsplit(uri) #@UnusedVariable
    
        # Request hostname and child uri hostname have to be the same.
        if host and host != request.headers.getHeader("host"):
            return False
        
        # Child URI must start with request uri text.
        parent = request.uri
        if not parent.endswith("/"):
            parent += "/"
            
        return path.startswith(parent) and (len(path) > len(parent)) and (not immediateChild or (path.find("/", len(parent)) == -1))
    
    def _checkParents(self, request, test):
        """
        @param request: the request being processed.
        @param test: a callable
        @return: the closest parent for this resource using the request URI from
            the given request for which C{test(parent)} evaluates to a true
            value, or C{None} if no parent matches.
        """
        parent = self
        parent_uri = request.uri

        while True:
            parent_uri = parentForURL(parent_uri)
            if not parent_uri: break

            parent = waitForDeferred(request.locateResource(parent_uri))
            yield parent
            parent = parent.getResult()

            if test(parent):
                yield parent
                return

        yield None
    
    _checkParents = deferredGenerator(_checkParents)

class ScheduleFile (CalDAVFile):
    def __init__(self, path, parent):
        super(ScheduleFile, self).__init__(path, principalCollections=parent.principalCollections())
        self._parent = parent

    def provision(self):
        provisionFile(self, self._parent)

    def locateChild(self, path, segments):
        self.provision()
        return super(ScheduleFile, self).locateChild(path, segments)

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            return CalDAVFile(path, principalCollections=self.principalCollections())

    def index(self):
        """
        Obtains the index for an schedule collection resource.
        @return: the index object for this resource.
        @raise AssertionError: if this resource is not a calendar collection
            resource.
        """
        return IndexSchedule(self)

    def http_COPY       (self, request): return responsecode.FORBIDDEN
    def http_MOVE       (self, request): return responsecode.FORBIDDEN
    def http_DELETE     (self, request): return responsecode.FORBIDDEN
    def http_MKCOL      (self, request): return responsecode.FORBIDDEN
    def http_MKCALENDAR (self, request): return responsecode.FORBIDDEN

    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(schedulePrivilegeSet)

class ScheduleInboxFile (ScheduleInboxResource, ScheduleFile):
    """
    Calendar scheduling inbox collection resource.
    """
    def provision(self):
        if provisionFile(self, self._parent):
            # FIXME: This should probably be a directory record option that
            # maps to the property value directly without the need to store one.
            if self._parent.record.recordType == "resource":
                # Resources should have autorespond turned on by default,
                # since they typically don't have someone responding for them.
                self.writeDeadProperty(customxml.TwistedScheduleAutoRespond())

    def __repr__(self):
        return "<%s (calendar inbox collection): %s>" % (self.__class__.__name__, self.fp.path)

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        return davxml.ACL(
            # CalDAV:schedule for any authenticated user
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(
                    davxml.Privilege(caldavxml.Schedule()),
                ),
            ),
        )

class ScheduleOutboxFile (ScheduleOutboxResource, ScheduleFile):
    """
    Calendar scheduling outbox collection resource.
    """
    def __repr__(self):
        return "<%s (calendar outbox collection): %s>" % (self.__class__.__name__, self.fp.path)

class CalendarHomeProvisioningFile (ReadOnlyResourceMixIn, DAVFile):
    """
    Resource which provisions calendar home collections as needed.    
    """
    def __init__(self, path, directory, url):
        """
        @param path: the path to the file which will back the resource.
        @param directory: an L{IDirectoryService} to provision calendars from.
        """
        assert url.endswith("/"), "Collection URL must end in '/'"

        super(CalendarHomeProvisioningFile, self).__init__(path)

        self.directory = IDirectoryService(directory)
        self._url = url

        # FIXME: Smells like a hack
        directory.calendarHomesCollection = self

    def provision(self):
        provisionFile(self)

        if not self.putChildren:
            # Create children
            for recordType in self.directory.recordTypes():
                self.putChild(recordType, CalendarHomeTypeProvisioningFile(self.fp.child(recordType).path, self, recordType))

    def url(self):
        return self._url

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name):
        self.provision()

        children = self.putChildren
        if name not in children and name.lower() in (x.lower() for x in children):
            # This avoids finding case variants of put children on case-insensitive filesystems.
            return None
        else:
            return children.get(name, None)

    def listChildren(self):
        return self.directory.recordTypes()

    def principalCollections(self):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalCollections()

    def homeForDirectoryRecord(self, record):
        typeResource = self.getChild(record.recordType)
        if typeResource is None:
            return None
        else:
            return typeResource.getChild(record.shortName)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        return readOnlyACL

class CalendarHomeTypeProvisioningFile (ReadOnlyResourceMixIn, DAVFile):
    """
    Resource which provisions calendar home collections of a specific
    record type as needed.
    """
    def __init__(self, path, parent, recordType):
        """
        @param path: the path to the file which will back the resource.
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param recordType: the directory record type to provision.
        """
        super(CalendarHomeTypeProvisioningFile, self).__init__(path)

        self.directory = parent.directory
        self.recordType = recordType
        self._parent = parent

    def provision(self):
        provisionFile(self, self._parent)

    def url(self):
        return joinURL(self._parent.url(), self.recordType)

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name, record=None):
        self.provision()

        if name == "":
            return self

        if record is None:
            record = self.directory.recordWithShortName(self.recordType, name)
            if record is None:
                return None
        else:
            assert name is None
            name = record.shortName

        return CalendarHomeFile(self.fp.child(name).path, self, record)

    def listChildren(self):
        return (record.shortName for record in self.directory.listRecords(self.recordType))

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        return readOnlyACL

    def principalCollections(self):
        return self._parent.principalCollections()

class CalendarHomeFile (CalDAVFile):
    """
    Calendar home collection resource.
    """
    # A global quota limit for all calendar homes. Either a C{int} (size in bytes) to limit
    # quota to that size, or C{None} for no limit.
    quotaLimit = None

    def __init__(self, path, parent, record):
        """
        @param path: the path to the file which will back the resource.
        """
        super(CalendarHomeFile, self).__init__(path)

        self.record = record
        self._parent = parent

        # Cache children which must be of a specific type
        for name, cls in (
            ("inbox" , ScheduleInboxFile),
            ("outbox", ScheduleOutboxFile),
        ):
            self.putChild(name, cls(self.fp.child(name).path, self))

    def provision(self):
        if not provisionFile(self, self._parent):
            return succeed(None)

        # Create a calendar collection

        child_name = "calendar"
        childURL = joinURL(self.url(), child_name)
        child = CalDAVFile(os.path.join(self.fp.path, child_name))

        def setupChild(_):
            # Grant read-free-busy access to authenticated users
            child.setAccessControlList(
                davxml.ACL(
                    davxml.ACE(
                        davxml.Principal(davxml.Authenticated()),
                        davxml.Grant(davxml.Privilege(caldavxml.ReadFreeBusy())),
                        TwistedACLInheritable(),
                    ),
                )
            )

            # Set calendar-free-busy-set on inbox
            inbox = self.getChild("inbox")
            inbox.provision()
            inbox.writeDeadProperty(caldavxml.CalendarFreeBusySet(davxml.HRef(childURL)))

        d = child.createCalendarCollection()
        d.addCallback(setupChild)

        # FIXME: This should provision itself also
        # Provision a drop box
        if self.record.recordType == "user":
            DropBox.provision(self)

        return d

    def url(self):
        return joinURL(self._parent.url(), self.record.shortName)

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            return CalDAVFile(path, principalCollections=self.principalCollections())

    def getChild(self, name):
        # This avoids finding case variants of put children on case-insensitive filesystems.
        if name not in self.putChildren and name.lower() in (x.lower() for x in self.putChildren):
            return None

        return super(CalendarHomeFile, self).getChild(name)

    def locateChild(self, path, segments):
        d = self.provision()
        d.addCallback(lambda _: super(CalendarHomeFile, self).locateChild(path, segments))
        return d

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        myPrincipal = self._parent._parent.directory.principalCollection.principalForRecord(self.record)

        return davxml.ACL(
            # DAV:read access for authenticated users.
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(davxml.Privilege(davxml.Read())),
            ),
            # Inheritable DAV:all access for the resource's associated principal.
            davxml.ACE(
                davxml.Principal(davxml.HRef(myPrincipal.principalURL())),
                davxml.Grant(davxml.Privilege(davxml.All())),
                davxml.Protected(),
                TwistedACLInheritable(),
            ),
        )

    def principalCollections(self):
        return self._parent.principalCollections()

    ##
    # Quota
    ##

    def hasQuotaRoot(self, request):
        """
        @return: a C{True} if this resource has quota root, C{False} otherwise.
        """
        return self.hasDeadProperty(TwistedQuotaRootProperty) or CalendarHomeFile.quotaLimit is not None
    
    def quotaRoot(self, request):
        """
        @return: a C{int} containing the maximum allowed bytes if this collection
            is quota-controlled, or C{None} if not quota controlled.
        """
        if self.hasDeadProperty(TwistedQuotaRootProperty):
            return int(str(self.readDeadProperty(TwistedQuotaRootProperty)))
        else:
            return CalendarHomeFile.quotaLimit

##
# Utilities
##

def provisionFile(resource, parent=None, isFile=False):
    fp = resource.fp

    fp.restat(False)
    if fp.exists():
        return False

    if parent is not None:
        assert parent.exists()
        assert parent.isCollection()

    if isFile:
        fp.open("w").close()
        fp.restat(False)
    else:
        fp.makedirs()
        fp.restat(False)

    return True

def locateExistingChild(resource, request, segments):
    """
    This C{locateChild()} implementation fails to find children if C{getChild()}
    doesn't return one.
    """
    # If getChild() finds a child resource, return it
    child = resource.getChild(segments[0])
    if child is not None:
        return (child, segments[1:])

    # Otherwise, there is no child
    return (None, ())

# DAV:read access for authenticated users.
readOnlyACL = davxml.ACL(
    davxml.ACE(
        davxml.Principal(davxml.Authenticated()),
        davxml.Grant(davxml.Privilege(davxml.Read())),
        davxml.Protected(),
    ),
)

def _schedulePrivilegeSet():
    edited = False

    top_supported_privileges = []

    for supported_privilege in davPrivilegeSet.childrenOfType(davxml.SupportedPrivilege):
        all_privilege = supported_privilege.childOfType(davxml.Privilege)
        if isinstance(all_privilege.children[0], davxml.All):
            all_description = supported_privilege.childOfType(davxml.Description)
            all_supported_privileges = list(supported_privilege.childrenOfType(davxml.SupportedPrivilege))
            all_supported_privileges.append(
                davxml.SupportedPrivilege(
                    davxml.Privilege(caldavxml.Schedule()),
                    davxml.Description("schedule privileges for current principal", **{"xml:lang": "en"}),
                ),
            )
            top_supported_privileges.append(
                davxml.SupportedPrivilege(all_privilege, all_description, *all_supported_privileges)
            )
            edited = True
        else:
            top_supported_privileges.append(supported_privilege)

    assert edited, "Structure of davPrivilegeSet changed in a way that I don't know how to extend for schedulePrivilegeSet"

    return davxml.SupportedPrivilegeSet(*top_supported_privileges)

schedulePrivilegeSet = _schedulePrivilegeSet()

def _calendarPrivilegeSet ():
    edited = False

    top_supported_privileges = []

    for supported_privilege in davPrivilegeSet.childrenOfType(davxml.SupportedPrivilege):
        all_privilege = supported_privilege.childOfType(davxml.Privilege)
        if isinstance(all_privilege.children[0], davxml.All):
            all_description = supported_privilege.childOfType(davxml.Description)
            all_supported_privileges = []
            for all_supported_privilege in supported_privilege.childrenOfType(davxml.SupportedPrivilege):
                read_privilege = all_supported_privilege.childOfType(davxml.Privilege)
                if isinstance(read_privilege.children[0], davxml.Read):
                    read_description = all_supported_privilege.childOfType(davxml.Description)
                    read_supported_privileges = list(all_supported_privilege.childrenOfType(davxml.SupportedPrivilege))
                    read_supported_privileges.append(
                        davxml.SupportedPrivilege(
                            davxml.Privilege(caldavxml.ReadFreeBusy()),
                            davxml.Description("allow free busy report query", **{"xml:lang": "en"}),
                        ),
                    )
                    all_supported_privileges.append(
                        davxml.SupportedPrivilege(read_privilege, read_description, *read_supported_privileges)
                    )
                    edited = True
                else:
                    all_supported_privileges.append(all_supported_privilege)
            top_supported_privileges.append(
                davxml.SupportedPrivilege(all_privilege, all_description, *all_supported_privileges)
            )
        else:
            top_supported_privileges.append(supported_privilege)

    assert edited, "Structure of davPrivilegeSet changed in a way that I don't know how to extend for calendarPrivilegeSet"

    return davxml.SupportedPrivilegeSet(*top_supported_privileges)

calendarPrivilegeSet = _calendarPrivilegeSet()

##
# Attach methods
##

import twistedcaldav.method

bindMethods(twistedcaldav.method, CalDAVFile)

# FIXME: Little bit of a circular dependency here...
twistedcaldav.method.copymove.CalDAVFile = CalDAVFile
twistedcaldav.method.delete.CalDAVFile   = CalDAVFile
twistedcaldav.method.mkcol.CalDAVFile    = CalDAVFile
twistedcaldav.method.put.CalDAVFile      = CalDAVFile
