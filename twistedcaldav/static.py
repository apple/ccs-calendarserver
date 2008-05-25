##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
CalDAV-aware static resources.
"""

__all__ = [
    "CalDAVFile",
    "AutoProvisioningFileMixIn",
    "CalendarHomeProvisioningFile",
    "CalendarHomeUIDProvisioningFile",
    "CalendarHomeFile",
    "ScheduleFile",
    "ScheduleInboxFile",
    "ScheduleOutboxFile",
    "DropBoxHomeFile",
    "DropBoxCollectionFile",
    "DropBoxChildFile",
    "TimezoneServiceFile",
]

import datetime
import os
import errno
from urlparse import urlsplit

from twisted.internet.defer import fail, succeed, inlineCallbacks, returnValue
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.http import HTTPError, StatusResponse
from twisted.web2.dav import davxml
from twisted.web2.dav.fileop import mkcollection, rmdir
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.idav import IDAVResource
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.dav.resource import davPrivilegeSet
from twisted.web2.dav.util import parentForURL, bindMethods

from twistedcaldav import caldavxml
from twistedcaldav import customxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.extensions import DAVFile
from twistedcaldav.extensions import CachingXattrPropertyStore
from twistedcaldav.ical import Component as iComponent
from twistedcaldav.ical import Property as iProperty
from twistedcaldav.index import Index, IndexSchedule
from twistedcaldav.resource import CalDAVResource, isCalendarCollectionResource, isPseudoCalendarCollectionResource
from twistedcaldav.schedule import ScheduleInboxResource, ScheduleOutboxResource
from twistedcaldav.dropbox import DropBoxHomeResource, DropBoxCollectionResource
from twistedcaldav.directory.calendar import uidsResourceName
from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeTypeProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeUIDProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeResource
from twistedcaldav.directory.resource import AutoProvisioningResourceMixIn
from twistedcaldav.log import Logger
from twistedcaldav.timezoneservice import TimezoneServiceResource

from twistedcaldav.cache import XattrCacheChangeNotifier, PropfindCacheMixin

log = Logger()

class CalDAVFile (CalDAVResource, DAVFile):
    """
    CalDAV-accessible L{DAVFile} resource.
    """
    def __repr__(self):
        if self.isCalendarCollection():
            return "<%s (calendar collection): %s>" % (self.__class__.__name__, self.fp.path)
        else:
            return super(CalDAVFile, self).__repr__()

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = CachingXattrPropertyStore(self)

        return self._dead_properties

    ##
    # CalDAV
    ##

    def resourceType(self):
        if self.isCalendarCollection():
            return davxml.ResourceType.calendar
        else:
            return super(CalDAVFile, self).resourceType()

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

        parent = self._checkParents(request, isPseudoCalendarCollectionResource)
        parent.addCallback(_defer)
        return parent

    def createCalendarCollection(self):
        #
        # Create the collection once we know it is safe to do so
        #
        def onCalendarCollection(status):
            if status != responsecode.CREATED:
                raise HTTPError(status)

            # Initialize CTag on the calendar collection
            d1 = self.updateCTag()

            # Create the index so its ready when the first PUTs come in
            d1.addCallback(lambda _: self.index().create())
            d1.addCallback(lambda _: status)
            return d1

        d = self.createSpecialCollection(davxml.ResourceType.calendar)
        d.addCallback(onCalendarCollection)
        return d

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

    @inlineCallbacks
    def iCalendarRolledup(self, request):
        if self.isPseudoCalendarCollection():
            # Generate a monolithic calendar
            calendar = iComponent("VCALENDAR")
            calendar.addProperty(iProperty("VERSION", "2.0"))

            # Do some optimisation of access control calculation by determining any inherited ACLs outside of
            # the child resource loop and supply those to the checkPrivileges on each child.
            filteredaces = yield self.inheritedACEsforChildren(request)

            # Must verify ACLs which means we need a request object at this point
            for name, uid, type in self.index().search(None): #@UnusedVariable
                try:
                    child = yield request.locateChildResource(self, name)
                    child = IDAVResource(child)
                except TypeError:
                    child = None

                if child is not None:
                    # Check privileges of child - skip if access denied
                    try:
                        yield child.checkPrivileges(request, (davxml.Read(),), inherited_aces=filteredaces)
                    except AccessDeniedError:
                        continue
                    subcalendar = self.iCalendar(name)
                    assert subcalendar.name() == "VCALENDAR"

                    for component in subcalendar.subcomponents():
                        calendar.addComponent(component)

            returnValue(calendar)

        raise HTTPError((ErrorResponse(responsecode.BAD_REQUEST)))

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
            def gotParent(parent):
                if parent and isCalendarCollectionResource(parent):
                    return succeed(calendarPrivilegeSet)
                else:
                    return super(CalDAVFile, self).supportedPrivileges(request)

            d = self.locateParent(request, request.urlForResource(self))
            d.addCallback(gotParent)
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
            if not child.startswith(".")
        ]

    def updateCTag(self):
        assert self.isCollection()
        try:
            self.writeDeadProperty(customxml.GETCTag(
                    str(datetime.datetime.now())))
        except:
            return fail(Failure())

        if hasattr(self, 'cacheNotifier'):
            return self.cacheNotifier.changed()

        return succeed(True)

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
            @inlineCallbacks
            def walktree(top):
                """
                Recursively descend the directory tree rooted at top,
                calling the callback function for each regular file

                @param top: L{FilePath} for the directory to walk.
                """

                total = 0
                for f in top.listdir():

                    # Ignore the database
                    if f.startswith("."):
                        continue

                    child = top.child(f)
                    if child.isdir():
                        # It's a directory, recurse into it
                        total += yield walktree(child)
                    elif child.isfile():
                        # It's a file, call the callback function
                        total += child.getsize()
                    else:
                        # Unknown file type, print a message
                        pass

                returnValue(total)

            return walktree(self.fp)
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

    @inlineCallbacks
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

            parent = yield request.locateResource(parent_uri)

            if test(parent):
                returnValue(parent)

class AutoProvisioningFileMixIn (AutoProvisioningResourceMixIn):
    def provision(self):
        self.provisionFile()
        return super(AutoProvisioningFileMixIn, self).provision()


    def provisionFile(self):
        if hasattr(self, "_provisioned_file"):
            return False
        else:
            self._provisioned_file = True

        fp = self.fp

        fp.restat(False)
        if fp.exists():
            return False

        log.msg("Provisioning file: %s" % (self,))

        if hasattr(self, "parent"):
            parent = self.parent
            if not parent.exists() and isinstance(parent, AutoProvisioningFileMixIn):
                parent.provision()

            assert parent.exists(), "Parent %s of %s does not exist" % (parent, self)
            assert parent.isCollection(), "Parent %s of %s is not a collection" % (parent, self)

        if self.isCollection():
            try:
                fp.makedirs()
            except OSError:
                # It's possible someone else created the directory in the meantime...
                # Check our status again, and re-raise if we're not a collection.
                if not self.isCollection():
                    raise
            fp.restat(False)
        else:
            fp.open("w").close()
            fp.restat(False)

        return True

class CalendarHomeProvisioningFile (AutoProvisioningFileMixIn, DirectoryCalendarHomeProvisioningResource, DAVFile):
    """
    Resource which provisions calendar home collections as needed.
    """
    def __init__(self, path, directory, url):
        """
        @param path: the path to the file which will back the resource.
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param url: the canonical URL for the resource.
        """
        DAVFile.__init__(self, path)
        DirectoryCalendarHomeProvisioningResource.__init__(self, directory, url)

    def provisionChild(self, name):
        if name == uidsResourceName:
            return CalendarHomeUIDProvisioningFile(self.fp.child(name).path, self)

        return CalendarHomeTypeProvisioningFile(self.fp.child(name).path, self, name)

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

class CalendarHomeTypeProvisioningFile (AutoProvisioningFileMixIn, DirectoryCalendarHomeTypeProvisioningResource, DAVFile):
    def __init__(self, path, parent, recordType):
        """
        @param path: the path to the file which will back the resource.
        @param parent: the parent of this resource
        @param recordType: the directory record type to provision.
        """
        DAVFile.__init__(self, path)
        DirectoryCalendarHomeTypeProvisioningResource.__init__(self, parent, recordType)

class CalendarHomeUIDProvisioningFile (AutoProvisioningFileMixIn, DirectoryCalendarHomeUIDProvisioningResource, DAVFile):
    def __init__(self, path, parent, homeResourceClass=None):
        """
        @param path: the path to the file which will back the resource.
        """
        DAVFile.__init__(self, path)
        DirectoryCalendarHomeUIDProvisioningResource.__init__(self, parent)
        if homeResourceClass is None:
            self.homeResourceClass = CalendarHomeFile
        else:
            self.homeResourceClass = homeResourceClass

    def provisionChild(self, name):
        record = self.directory.recordWithGUID(name)

        if record is None:
            log.msg("No directory record with GUID %r" % (name,))
            return None

        if not record.enabledForCalendaring:
            log.msg("Directory record %r is not enabled for calendaring" % (record,))
            return None

        assert len(name) > 4
        
        childPath = self.fp.child(name[0:2]).child(name[2:4]).child(name)
        child = self.homeResourceClass(childPath.path, self, record)

        if not child.exists():
            self.provision()

            if not childPath.parent().isdir():
                childPath.parent().makedirs()

            for oldPath in (
                # Pre 2.0: All in one directory
                self.fp.child(name),
                # Pre 1.2: In types hierarchy instead of the GUID hierarchy
                self.parent.getChild(record.recordType).fp.child(record.shortName),
            ):
                if oldPath.exists():
                    # The child exists at an old location.  Move to new location.
                    log.msg("Moving calendar home from old location %r to new location %r." % (oldPath, childPath))
                    try:
                        oldPath.moveTo(childPath)
                    except (OSError, IOError), e:
                        log.err("Error moving calendar home %r: %s" % (oldPath, e))
                        raise HTTPError(StatusResponse(
                            responsecode.INTERNAL_SERVER_ERROR,
                            "Unable to move calendar home."
                        ))
                    child.fp.restat(False)
                    break
            else:
                #
                # NOTE: provisionDefaultCalendars() returns a deferred, which we are ignoring.
                # The result being that the default calendars will be present at some point
                # in the future, not necessarily right now, and we don't have a way to wait
                # on that to finish.
                #
                child.provisionDefaultCalendars()

                #
                # Try to work around the above a little by telling the client that something
                # when wrong temporarily if the child isn't provisioned right away.
                #
                if not child.exists():
                    raise HTTPError(StatusResponse(
                        responsecode.SERVICE_UNAVAILABLE,
                        "Provisioning calendar home."
                    ))

            assert child.exists()

        return child

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

class CalendarHomeFile (PropfindCacheMixin, AutoProvisioningFileMixIn, DirectoryCalendarHomeResource, CalDAVFile):
    """
    Calendar home collection resource.
    """
    cacheNotifierFactory = XattrCacheChangeNotifier

    def __init__(self, path, parent, record):
        """
        @param path: the path to the file which will back the resource.
        """
        CalDAVFile.__init__(self, path)
        DirectoryCalendarHomeResource.__init__(self, parent, record)
        self.cacheNotifier = self.cacheNotifierFactory(self.deadProperties())

    def provisionChild(self, name):
        if config.EnableDropBox:
            DropBoxHomeFileClass = DropBoxHomeFile
        else:
            DropBoxHomeFileClass = None

        cls = {
            "inbox"        : ScheduleInboxFile,
            "outbox"       : ScheduleOutboxFile,
            "dropbox"      : DropBoxHomeFileClass,
        }.get(name, None)

        if cls is not None:
            return cls(self.fp.child(name).path, self)

        return self.createSimilarFile(self.fp.child(name).path)

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            similar = CalDAVFile(path, principalCollections=self.principalCollections())
            similar.cacheNotifier = self.cacheNotifier
            return similar

    def getChild(self, name):
        # This avoids finding case variants of put children on case-insensitive filesystems.
        if name not in self.putChildren and name.lower() in (x.lower() for x in self.putChildren):
            return None

        return super(CalendarHomeFile, self).getChild(name)


class ScheduleFile (AutoProvisioningFileMixIn, CalDAVFile):
    def __init__(self, path, parent):
        super(ScheduleFile, self).__init__(path, principalCollections=parent.principalCollections())

    def isCollection(self):
        return True

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

    def http_MKCALENDAR(self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (caldav_namespace, "calendar-collection-location-ok")
        )


    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(schedulePrivilegeSet)

class ScheduleInboxFile (ScheduleInboxResource, ScheduleFile):
    """
    Calendar scheduling inbox collection resource.
    """
    def __init__(self, path, parent):
        ScheduleFile.__init__(self, path, parent)
        ScheduleInboxResource.__init__(self, parent)

    def provision(self):
        if self.provisionFile():

            # Initialize CTag on the calendar collection
            self.updateCTag()

        return super(ScheduleInboxFile, self).provision()

    def __repr__(self):
        return "<%s (calendar inbox collection): %s>" % (self.__class__.__name__, self.fp.path)

class ScheduleOutboxFile (ScheduleOutboxResource, ScheduleFile):
    """
    Calendar scheduling outbox collection resource.
    """
    def __init__(self, path, parent):
        ScheduleFile.__init__(self, path, parent)
        ScheduleOutboxResource.__init__(self, parent)

    def provision(self):
        if self.provisionFile():
            # Initialize CTag on the calendar collection
            self.updateCTag()

        return super(ScheduleOutboxFile, self).provision()

    def __repr__(self):
        return "<%s (calendar outbox collection): %s>" % (self.__class__.__name__, self.fp.path)

class DropBoxHomeFile (AutoProvisioningFileMixIn, DropBoxHomeResource, CalDAVFile):
    def __init__(self, path, parent):
        DropBoxHomeResource.__init__(self)
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())
        self.parent = parent

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            return DropBoxCollectionFile(path, self)

    def __repr__(self):
        return "<%s (dropbox home collection): %s>" % (self.__class__.__name__, self.fp.path)

class DropBoxCollectionFile (DropBoxCollectionResource, CalDAVFile):
    def __init__(self, path, parent):
        DropBoxCollectionResource.__init__(self)
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            return DropBoxChildFile(path, self)

    def __repr__(self):
        return "<%s (dropbox collection): %s>" % (self.__class__.__name__, self.fp.path)

class DropBoxChildFile (CalDAVFile):
    def __init__(self, path, parent):
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())

        assert self.fp.isfile() or not self.fp.exists()

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            return responsecode.NOT_FOUND

class TimezoneServiceFile (TimezoneServiceResource, CalDAVFile):
    def __init__(self, path, parent):
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())
        TimezoneServiceResource.__init__(self, parent)

        assert self.fp.isfile() or not self.fp.exists()

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            return responsecode.NOT_FOUND

    def http_PUT        (self, request): return responsecode.FORBIDDEN
    def http_COPY       (self, request): return responsecode.FORBIDDEN
    def http_MOVE       (self, request): return responsecode.FORBIDDEN
    def http_DELETE     (self, request): return responsecode.FORBIDDEN
    def http_MKCOL      (self, request): return responsecode.FORBIDDEN

    def http_MKCALENDAR(self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (caldav_namespace, "calendar-collection-location-ok")
        )

##
# Utilities
##

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

# Some resources do not support some methods
setattr(DropBoxCollectionFile, "http_MKCALENDAR", None)
setattr(DropBoxChildFile, "http_MKCOL", None)
setattr(DropBoxChildFile, "http_MKCALENDAR", None)

# FIXME: Little bit of a circular dependency here...
twistedcaldav.method.copymove.CalDAVFile = CalDAVFile
twistedcaldav.method.delete.CalDAVFile   = CalDAVFile
twistedcaldav.method.get.CalDAVFile      = CalDAVFile
twistedcaldav.method.mkcol.CalDAVFile    = CalDAVFile
twistedcaldav.method.propfind.CalDAVFile = CalDAVFile
twistedcaldav.method.put.CalDAVFile      = CalDAVFile
