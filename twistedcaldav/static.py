# -*- test-case-name: twistedcaldav.test -*-
##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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
    "IScheduleInboxFile",
    "DropBoxHomeFile",
    "DropBoxCollectionFile",
    "DropBoxChildFile",
    "TimezoneServiceFile",
    "NotificationCollectionFile",
    "NotificationFile",
    "AddressBookHomeProvisioningFile",
    "AddressBookHomeUIDProvisioningFile",
    "AddressBookHomeFile",
    "DirectoryBackedAddressBookFile",
    "GlobalAddressBookFile",
]

import datetime
import os
import errno
from urlparse import urlsplit
from uuid import uuid4

from twext.python.log import Logger

from twisted.internet.defer import fail, succeed, inlineCallbacks, returnValue, maybeDeferred
from twisted.python.failure import Failure
from twext.python.filepath import CachingFilePath as FilePath
from twext.web2 import responsecode, http, http_headers
from twext.web2.http import HTTPError, StatusResponse
from twext.web2.dav import davxml
from twext.web2.dav.element.base import dav_namespace
from twext.web2.dav.fileop import mkcollection, rmdir
from twext.web2.dav.http import ErrorResponse, MultiStatusResponse
from twext.web2.dav.idav import IDAVResource
from twext.web2.dav.method import put_common, delete_common
from twext.web2.dav.noneprops import NonePropertyStore
from twext.web2.dav.resource import AccessDeniedError
from twext.web2.dav.resource import davPrivilegeSet
from twext.web2.dav.util import parentForURL, bindMethods, joinURL
from twext.web2.http_headers import generateContentType, MimeType
from txdav.idav import AlreadyFinishedError

from twistedcaldav import caldavxml
from twistedcaldav import carddavxml
from twistedcaldav import customxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.client.reverseproxy import ReverseProxyResource
from twistedcaldav.config import config
from twistedcaldav.customxml import TwistedCalendarAccessProperty, TwistedScheduleMatchETags
from twistedcaldav.datafilters.peruserdata import PerUserDataFilter
from twistedcaldav.directory.internal import InternalDirectoryRecord
from twistedcaldav.directory.util import NotFilePath
from twistedcaldav.extensions import DAVFile, CachingPropertyStore
from twistedcaldav.linkresource import LinkResource, LinkFollowerMixIn
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError

from twistedcaldav.freebusyurl import FreeBusyURLResource
from twistedcaldav.ical import Component as iComponent
from twistedcaldav.ical import Property as iProperty
from twistedcaldav.index import Index, IndexSchedule, SyncTokenValidException
from twistedcaldav.resource import CalDAVResource, isCalendarCollectionResource, isPseudoCalendarCollectionResource
from twistedcaldav.resource import isAddressBookCollectionResource
from twistedcaldav.schedule import ScheduleInboxResource, ScheduleOutboxResource, IScheduleInboxResource
from twistedcaldav.datafilters.privateevents import PrivateEventFilter
from twistedcaldav.dropbox import DropBoxHomeResource, DropBoxCollectionResource
from twistedcaldav.directorybackedaddressbook import DirectoryBackedAddressBookResource
from twistedcaldav.directory.addressbook import uidsResourceName as uidsResourceNameAddressBook,\
    GlobalAddressBookResource
from twistedcaldav.directory.addressbook import DirectoryAddressBookHomeProvisioningResource
from twistedcaldav.directory.addressbook import DirectoryAddressBookHomeTypeProvisioningResource
from twistedcaldav.directory.addressbook import DirectoryAddressBookHomeUIDProvisioningResource
from twistedcaldav.directory.addressbook import DirectoryAddressBookHomeResource
from twistedcaldav.directory.calendar import uidsResourceName
from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeTypeProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeUIDProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeResource
from twistedcaldav.directory.resource import AutoProvisioningResourceMixIn
from twistedcaldav.sharing import SharedHomeMixin
from twistedcaldav.timezoneservice import TimezoneServiceResource
from twistedcaldav.vcardindex import AddressBookIndex
from twistedcaldav.notify import getPubSubConfiguration, getPubSubXMPPURI
from twistedcaldav.notify import getPubSubHeartbeatURI, getPubSubPath
from twistedcaldav.notify import Notifier, getNodeCacher
from twistedcaldav.notifications import NotificationCollectionResource,\
    NotificationResource

log = Logger()

class ReadOnlyResourceMixIn(object):

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



class CalDAVFile (LinkFollowerMixIn, CalDAVResource, DAVFile):
    """
    CalDAV-accessible L{DAVFile} resource.
    """
#    def __repr__(self):
#        if self.isCalendarCollection():
#            return "<%s (calendar collection): %s>" % (self.__class__.__name__, self.fp.path)
#        else:
#            return super(CalDAVFile, self).__repr__()

    def __eq__(self, other):
        if not isinstance(other, CalDAVFile):
            return False
        return self.fp.path == other.fp.path

    def checkPreconditions(self, request):
        """
        We override the base class to handle the special implicit scheduling weak ETag behavior
        for compatibility with old clients using If-Match.
        """
        
        if config.Scheduling.CalDAV.ScheduleTagCompatibility:
            
            if self.exists() and self.hasDeadProperty(TwistedScheduleMatchETags):
                etags = self.readDeadProperty(TwistedScheduleMatchETags).children
                if len(etags) > 1:
                    # This is almost verbatim from twext.web2.static.checkPreconditions
                    if request.method not in ("GET", "HEAD"):
                        
                        # Loop over each tag and succeed if any one matches, else re-raise last exception
                        exists = self.exists()
                        last_modified = self.lastModified()
                        last_exception = None
                        for etag in etags:
                            try:
                                http.checkPreconditions(
                                    request,
                                    entityExists = exists,
                                    etag = http_headers.ETag(etag),
                                    lastModified = last_modified,
                                )
                            except HTTPError, e:
                                last_exception = e
                            else:
                                break
                        else:
                            if last_exception:
                                raise last_exception
            
                    # Check per-method preconditions
                    method = getattr(self, "preconditions_" + request.method, None)
                    if method:
                        response = maybeDeferred(method, request)
                        response.addCallback(lambda _: request)
                        return response
                    else:
                        return None

        return super(CalDAVFile, self).checkPreconditions(request)

    def deadProperties(self, caching=True):
        if not hasattr(self, "_dead_properties"):
            # FIXME: this code should actually be dead, as the property store
            # should be initialized as part of the traversal process.
 
            # Get the property store from super
            deadProperties = super(CalDAVFile, self).deadProperties()

            if caching:
                # Wrap the property store in a memory store
                deadProperties = CachingPropertyStore(deadProperties)

            self._dead_properties = deadProperties

        return self._dead_properties

    ##
    # CalDAV
    ##

    def createCalendar(self, request):
        """
        External API for creating a calendar.  Verify that the parent is a
        collection, exists, is I{not} a calendar collection; that this resource
        does not yet exist, then create it.

        @param request: the request used to look up parent resources to
            validate.

        @type request: L{twext.web2.iweb.IRequest}

        @return: a deferred that fires when a calendar collection has been
            created in this resource.
        """
        if self.fp.exists():
            log.err("Attempt to create collection where file exists: %s" % (self.fp.path,))
            raise HTTPError(StatusResponse(responsecode.NOT_ALLOWED, "File exists"))

        # newStore guarantees that we always have a parent calendar home
        #if not self.fp.parent().isdir():
        #    log.err("Attempt to create collection with no parent: %s" % (self.fp.path,))
        #    raise HTTPError(StatusResponse(responsecode.CONFLICT, "No parent collection"))

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
        """
        Internal API for creating a calendar collection.

        This will immediately create the collection without performing any
        verification.  For the normal API, see L{CalDAVFile.createCalendar}.

        The default behavior is to return a failing Deferred; for a working
        implementation, see L{twistedcaldav.legacy}.

        @return: a L{Deferred} which fires when the underlying collection has
            actually been created.
        """
        return fail(NotImplementedError())


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


# FIXME: move cache implementation!
            # Determine the cache key
#            isvirt = (yield self.isVirtualShare(request))
#            if isvirt:
#                principal = (yield self.resourceOwnerPrincipal(request))
#                if principal:
#                    cacheKey = principal.principalUID()
#                else:
#                    cacheKey = "unknown"
#            else:
#                isowner = (yield self.isOwner(request, adminprincipals=True, readprincipals=True))
#                cacheKey = "owner" if isowner else "notowner"
                
            # Now check for a cached .ics
#            rolled = self.fp.child(".subscriptions")
#            if not rolled.exists():
#                try:
#                    rolled.makedirs()
#                except IOError, e:
#                    log.err("Unable to create internet calendar subscription cache directory: %s because of: %s" % (rolled.path, e,))
#                    raise HTTPError(ErrorResponse(responsecode.INTERNAL_SERVER_ERROR))
#            cached = rolled.child(cacheKey)
#            if cached.exists():
#                try:
#                    cachedData = cached.open().read()
#                except IOError, e:
#                    log.err("Unable to open or read internet calendar subscription cache file: %s because of: %s" % (cached.path, e,))
#                else:
#                    # Check the cache token
#                    token, data = cachedData.split("\r\n", 1)
#                    if token == self.getSyncToken():
#                        returnValue(data)

            # Generate a monolithic calendar
            calendar = iComponent("VCALENDAR")
            calendar.addProperty(iProperty("VERSION", "2.0"))

            # Do some optimisation of access control calculation by determining any inherited ACLs outside of
            # the child resource loop and supply those to the checkPrivileges on each child.
            filteredaces = (yield self.inheritedACEsforChildren(request))

            tzids = set()
            isowner = (yield self.isOwner(request, adminprincipals=True, readprincipals=True))
            accessPrincipal = (yield self.resourceOwnerPrincipal(request))

            for name, uid, type in self.index().bruteForceSearch(): #@UnusedVariable
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

                    # Get the access filtered view of the data
                    caldata = child.iCalendarTextFiltered(isowner, accessPrincipal.principalUID() if accessPrincipal else "")
                    try:
                        subcalendar = iComponent.fromString(caldata)
                    except ValueError:
                        continue
                    assert subcalendar.name() == "VCALENDAR"

                    for component in subcalendar.subcomponents():
                        
                        # Only insert VTIMEZONEs once
                        if component.name() == "VTIMEZONE":
                            tzid = component.propertyValue("TZID")
                            if tzid in tzids:
                                continue
                            tzids.add(tzid)

                        calendar.addComponent(component)

            # Cache the data
            data = str(calendar)
            data = self.getSyncToken() + "\r\n" + data
#            try:
#                cached.open(mode='w').write(data)
#            except IOError, e:
#                log.err("Unable to open or write internet calendar subscription cache file: %s because of: %s" % (cached.path, e,))
                
            returnValue(calendar)

        raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST))

    def iCalendarTextFiltered(self, isowner, accessUID=None):
        try:
            access = self.readDeadProperty(TwistedCalendarAccessProperty)
        except HTTPError:
            access = None

        # Now "filter" the resource calendar data
        caldata = PrivateEventFilter(access, isowner).filter(self.iCalendarText())
        if accessUID:
            caldata = PerUserDataFilter(accessUID).filter(caldata)
        return str(caldata)

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

    def createAddressBook(self, request):
        """
        External API for creating an addressbook.  Verify that the parent is a
        collection, exists, is I{not} an addressbook collection; that this resource
        does not yet exist, then create it.

        @param request: the request used to look up parent resources to
            validate.

        @type request: L{twext.web2.iweb.IRequest}

        @return: a deferred that fires when an addressbook collection has been
            created in this resource.
        """
        #
        # request object is required because we need to validate against parent
        # resources, and we need the request in order to locate the parents.
        #

        if self.fp.exists():
            log.err("Attempt to create collection where file exists: %s" % (self.fp.path,))
            raise HTTPError(StatusResponse(responsecode.NOT_ALLOWED, "File exists"))

        # newStore guarantees that we always have a parent calendar home
        #if not os.path.isdir(os.path.dirname(self.fp.path)):
        #    log.err("Attempt to create collection with no parent: %s" % (self.fp.path,))
        #    raise HTTPError(StatusResponse(responsecode.CONFLICT, "No parent collection"))

        #
        # Verify that no parent collection is a calendar also
        #
        log.msg("Creating address book collection %s" % (self,))

        def _defer(parent):
            if parent is not None:
                log.err("Cannot create an address book collection within an address book collection %s" % (parent,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (carddavxml.carddav_namespace, "addressbook-collection-location-ok")
                ))

            return self.createAddressBookCollection()

        parent = self._checkParents(request, isAddressBookCollectionResource)
        parent.addCallback(_defer)
        return parent

    def createAddressBookCollection(self):
        """
        Internal API for creating an addressbook collection.

        This will immediately create the collection without performing any
        verification.  For the normal API, see L{CalDAVFile.createAddressBook}.

        The default behavior is to return a failing Deferred; for a working
        implementation, see L{twistedcaldav.legacy}.

        @return: a L{Deferred} which fires when the underlying collection has
            actually been created.
        """
        return fail(NotImplementedError())

    @inlineCallbacks
    def vCardRolledup(self, request):
        # TODO: just catenate all the vCards together 
        yield fail(HTTPError((ErrorResponse(responsecode.BAD_REQUEST))))

    def vCardText(self, name=None):
        if self.isAddressBookCollection():
            if name is None:
                return str(self.vCard())

            try:
                vcard_file = self.fp.child(name).open()
            except IOError, e:
                if e[0] == errno.ENOENT: return None
                raise

        elif self.isCollection():
            return None

        else:
            if name is not None:
                raise AssertionError("name must be None for non-collection vcard resource")

            vcard_file = self.fp.open()

        # FIXME: This is blocking I/O
        try:
            vcard_data = vcard_file.read()
        finally:
            vcard_file.close()

        return vcard_data

    def vCardXML(self, name=None):
        return carddavxml.AddressData.fromAddressData(self.vCardText(name))

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
        if self.isAddressBookCollection():
            return AddressBookIndex(self)
        else:
            return Index(self)

    def whatchanged(self, client_token):
        
        current_token = str(self.readDeadProperty(customxml.GETCTag))
        current_uuid, current_revision = current_token.split("#", 1)
        current_revision = int(current_revision)

        if client_token:
            try:
                caluuid, revision = client_token.split("#", 1)
                revision = int(revision)
                
                # Check client token validity
                if caluuid != current_uuid:
                    raise ValueError
                if revision > current_revision:
                    raise ValueError
            except ValueError:
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "valid-sync-token")))
        else:
            revision = 0

        try:
            changed, removed = self.index().whatchanged(revision)
        except SyncTokenValidException:
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "valid-sync-token")))

        return changed, removed, current_token

    @inlineCallbacks
    def bumpSyncToken(self):
        """
        Increment the sync-token which is also the ctag.
        
        return: a deferred that returns the new revision number
        """
        assert self.isCollection()
        
        # Need to lock
        lock = MemcacheLock("ResourceLock", self.fp.path, timeout=60.0)
        try:
            try:
                yield lock.acquire()
            except MemcacheLockTimeoutError:
                raise HTTPError(StatusResponse(responsecode.CONFLICT, "Resource: %s currently in use on the server." % (self.uri,)))

            try:
                token = str(self.readDeadProperty(customxml.GETCTag))
                caluuid, revision = token.split("#", 1)
                revision = int(revision) + 1
                token = "%s#%d" % (caluuid, revision,)
    
            except (HTTPError, ValueError):
                # Initialise it
                caluuid = uuid4()
                revision = 1
                token = "%s#%d" % (caluuid, revision,)
    
            yield self.updateCTag(token)
            returnValue(revision)
        finally:
            yield lock.clean()

    def initSyncToken(self):
        """
        Create a new sync-token which is also the ctag.
        """
        # FIXME: new implementation is in txcaldav.file, this should be
        # deleted.
        assert self.isCollection()
        # Initialise it
        caluuid = uuid4()
        revision = 1
        token = "%s#%d" % (caluuid, revision,)
        try:
            self.writeDeadProperty(customxml.GETCTag(token))
        except:
            return fail(Failure())

    def getSyncToken(self):
        """
        Return current sync-token value.
        """
        assert self.isCollection()
        
        return str(self.readDeadProperty(customxml.GETCTag))

    def updateCTag(self, token=None):
        assert self.isCollection()
        
        if not token:
            token = str(datetime.datetime.now())
        try:
            self.writeDeadProperty(customxml.GETCTag(token))
        except:
            return fail(Failure())

        if hasattr(self, 'clientNotifier'):
            self.clientNotifier.notify(op="update")

        return succeed(True)

    ##
    # File
    ##

    def listChildren(self):
        return [
            child for child in super(CalDAVFile, self).listChildren()
            if not child.startswith(".")
        ]

    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self

        similar = super(CalDAVFile, self).createSimilarFile(path)

        if isCalendarCollectionResource(self):
            raise RuntimeError("Calendar collection resources should really "
                               "be represented by a different class.")

        return similar

    ##
    # Quota
    ##

    def quotaSize(self, request):
        """
        Get the size of this resource.
        TODO: Take into account size of dead-properties. Does stat include xattrs size?

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

class AutoProvisioningFileMixIn (LinkFollowerMixIn, AutoProvisioningResourceMixIn):
    def provision(self):
        self.provisionFile()
        return super(AutoProvisioningFileMixIn, self).provision()


    def provisionFile(self):
        if hasattr(self, "_provisioned_file"):
            return False
        else:
            self._provisioned_file = True

        # If the file already exists we can just exit here - there is no need to go further
        if self.fp.exists():
            return False

        # At this point the original FilePath did not indicate an existing file, but we should
        # recheck it to see if some other request sneaked in and already created/provisioned it

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
            fp.changed()
        else:
            fp.open("w").close()
            fp.changed()

        return True

    def _initTypeAndEncoding(self):

        # Handle cases not covered by getTypeAndEncoding()
        if self.isCollection():
            self._type = "httpd/unix-directory"
        else:
            super(AutoProvisioningFileMixIn, self)._initTypeAndEncoding()


class CalendarHomeProvisioningFile(AutoProvisioningFileMixIn, 
                                   DirectoryCalendarHomeProvisioningResource,
                                   DAVFile):
    """
    Resource which provisions calendar home collections as needed.
    """

    def __init__(self, path, directory, url, store):
        """
        Initialize this L{CalendarHomeProvisioningFile}.

        @param path: the path to the filesystem directory which will back the
            resource.

        @type path: L{FilePath}

        @param directory: an L{IDirectoryService} to provision calendars from.

        @param url: the canonical URL for this L{CalendarHomeProvisioningFile} 
            resource.
        """
        DAVFile.__init__(self, path)
        DirectoryCalendarHomeProvisioningResource.__init__(self, directory, url)
        self._newStore = store


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



def _transactionFromRequest(request, newStore):
    """
    Return the associated transaction from the given HTTP request, creating a
    new one from the given data store if none has yet been associated.

    Also, if the request was not previously associated with a transaction, add
    a failsafe transaction-abort response filter to abort any transaction which
    has not been committed or aborted by the resource which responds to the
    request.

    @param request: The request to inspect.
    @type request: L{IRequest}

    @param newStore: The store to create a transaction from.
    @type newStore: L{IDataStore}

    @return: a transaction that should be used to read and write data
        associated with the request.
    @rtype: L{ITransaction} (and possibly L{ICalendarTransaction} and
        L{IAddressBookTransaction} as well.
    """
    TRANSACTION_KEY = '_newStoreTransaction'
    transaction = getattr(request, TRANSACTION_KEY, None)
    if transaction is None:
        transaction = newStore.newTransaction(repr(request))
        def abortIfUncommitted(request, response):
            try:
                transaction.abort()
            except AlreadyFinishedError:
                pass
            return response
        abortIfUncommitted.handleErrors = True
        request.addResponseFilter(abortIfUncommitted)
        setattr(request, TRANSACTION_KEY, transaction)
    return transaction



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


    def locateChild(self, request, segments):

        name = segments[0]
        if name == "":
            return (self, ())

        record = self.directory.recordWithUID(name)
        if record:
            return (self.homeResourceForRecord(record, request), segments[1:])
        else:
            return (None, ())

    def homeResourceForRecord(self, record, request):
        self.provision()
        transaction = _transactionFromRequest(request, self.parent._newStore)

        name = record.uid

        if record is None:
            log.msg("No directory record with GUID %r" % (name,))
            return None

        if not record.enabledForCalendaring:
            log.msg("Directory record %r is not enabled for calendaring" % (record,))
            return None

        assert len(name) > 4, "Directory record has an invalid GUID: %r" % (name,)
        
        if record.locallyHosted():
            childPath = self.fp.child(name[0:2]).child(name[2:4]).child(name)
            child = self.homeResourceClass(childPath.path, self, record, transaction)
    
            if not child.exists():
                self.provision()
    
                if not childPath.parent().isdir():
                    childPath.parent().makedirs()
    
                for oldPath in (
                    # Pre 2.0: All in one directory
                    self.fp.child(name),
                    # Pre 1.2: In types hierarchy instead of the GUID hierarchy
                    self.parent.getChild(record.recordType).fp.child(record.shortNames[0]),
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
                        child.fp.changed()
                        break

                assert child.exists()
        
        else:
            childPath = self.fp.child(name[0:2]).child(name[2:4]).child(name)
            child = CalendarHomeReverseProxyFile(childPath.path, self, record)

        return child

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

class CalendarHomeReverseProxyFile(ReverseProxyResource):
    
    def __init__(self, path, parent, record):
        self.path = path
        self.parent = parent
        self.record = record
        
        super(CalendarHomeReverseProxyFile, self).__init__(self.record.hostedAt)
    
    def url(self):
        return joinURL(self.parent.url(), self.record.uid)

class CalendarHomeFile(AutoProvisioningFileMixIn, SharedHomeMixin, 
                       DirectoryCalendarHomeResource, CalDAVFile):
    """
    Calendar home collection resource.
    """
    def liveProperties(self):
        
        return super(CalendarHomeFile, self).liveProperties() + (
            (customxml.calendarserver_namespace, "push-transports"),
            (customxml.calendarserver_namespace, "pushkey"),
            (customxml.calendarserver_namespace, "xmpp-uri"),
            (customxml.calendarserver_namespace, "xmpp-heartbeat-uri"),
            (customxml.calendarserver_namespace, "xmpp-server"),
        )

    def __init__(self, path, parent, record, transaction):
        """
        @param path: the path to the file which will back the resource.
        """

        self.associateWithTransaction(transaction)

        storeHome = transaction.calendarHomeWithUID(record.uid)
        if storeHome is not None:
            created = False
        else:
            storeHome = transaction.calendarHomeWithUID(
                record.uid, create=True
            )
            created = True
        self._newStoreCalendarHome = storeHome
        CalDAVFile.__init__(self, path)
        DirectoryCalendarHomeResource.__init__(self, parent, record)
        from twistedcaldav.storebridge import _NewStorePropertiesWrapper
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreCalendarHome.properties()
        )
        if created:
            # This is a bit of a hack.  Really we ought to be always generating
            # this URL live from a back-end method that tells us what the
            # default calendar is.
            inbox = self.getChild("inbox")
            childURL = joinURL(self.url(), "calendar")
            inbox.processFreeBusyCalendar(childURL, True)


    def sharesDB(self):
        """
        Retrieve the new-style shares DB wrapper.
        """
        if not hasattr(self, "_sharesDB"):
            self._sharesDB = self._newStoreCalendarHome.retrieveOldShares()
        return self._sharesDB


    def exists(self):
        # FIXME: tests
        return True
    
    
    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)


    def provision(self):
        if config.Sharing.Enabled and config.Sharing.Calendars.Enabled and self.fp.exists():
            self.provisionShares()
        return

    def provisionChild(self, name):
        from twistedcaldav.storebridge import StoreScheduleInboxFile
        from twistedcaldav.storebridge import DropboxCollection
        if config.EnableDropBox:
            DropBoxHomeFileClass = DropboxCollection
        else:
            DropBoxHomeFileClass = None

        if config.FreeBusyURL.Enabled:
            FreeBusyURLFileClass = FreeBusyURLFile
        else:
            FreeBusyURLFileClass = None
            
        if config.Sharing.Enabled and config.Sharing.Calendars.Enabled:
            NotificationCollectionFileClass = NotificationCollectionFile
        else:
            NotificationCollectionFileClass = None


        # For storebridge stuff we special case this
        if name == "notification":
            return self.createNotificationsFile(self.fp.child(name).path)

        cls = {
            "inbox"        : StoreScheduleInboxFile,
            "outbox"       : ScheduleOutboxFile,
            "dropbox"      : DropBoxHomeFileClass,
            "freebusy"     : FreeBusyURLFileClass,
            "notification" : NotificationCollectionFileClass,
        }.get(name, None)

        if cls is not None:
            child = cls(self.fp.child(name).path, self)
            return child
        return self.createSimilarFile(self.fp.child(name).path)

    def createNotificationsFile(self, path):
        
        txn = self._newStoreCalendarHome._transaction
        notifications = txn.notificationsWithUID(self._newStoreCalendarHome.uid())

        from twistedcaldav.storebridge import StoreNotificationCollectionFile
        similar = StoreNotificationCollectionFile(
            notifications, self._newStoreCalendarHome,
            path, self,
        )
        self.propagateTransaction(similar)
        return similar

    def createSimilarFile(self, path):

        if self.comparePath(path):
            return self
        else:
            if not isinstance(path, FilePath):
                path = FilePath(path)
            newCalendar = self._newStoreCalendarHome.calendarWithName(
                path.basename()
            )
            if newCalendar is None:
                # Local imports.due to circular dependency between modules.
                from twistedcaldav.storebridge import (
                     ProtoCalendarCollectionFile)
                similar = ProtoCalendarCollectionFile(
                    self._newStoreCalendarHome,
                    path, principalCollections=self.principalCollections()
                )
            else:
                from twistedcaldav.storebridge import CalendarCollectionFile
                similar = CalendarCollectionFile(
                    newCalendar, self._newStoreCalendarHome,
                    path, principalCollections=self.principalCollections()
                )
            self.propagateTransaction(similar)
            return similar

    def getChild(self, name):
        # This avoids finding case variants of put children on case-insensitive filesystems.
        if name not in self.putChildren and name.lower() in (x.lower() for x in self.putChildren):
            return None

        return super(CalendarHomeFile, self).getChild(name)


    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == (customxml.calendarserver_namespace, "push-transports"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if (pubSubConfiguration['enabled'] and
                getattr(self, "clientNotifier", None) is not None):
                    id = self.clientNotifier.getID()
                    nodeName = getPubSubPath(id, pubSubConfiguration)
                    children = []
                    if pubSubConfiguration['aps-bundle-id']:
                        children.append(
                            customxml.PubSubTransportProperty(
                                customxml.PubSubSubscriptionProperty(
                                    davxml.HRef(
                                        pubSubConfiguration['subscription-url']
                                    ),
                                ),
                                customxml.PubSubAPSBundleIDProperty(
                                    pubSubConfiguration['aps-bundle-id']
                                ),
                                type="APSD",
                            )
                        )
                    if pubSubConfiguration['xmpp-server']:
                        children.append(
                            customxml.PubSubTransportProperty(
                                customxml.PubSubXMPPServerProperty(
                                    pubSubConfiguration['xmpp-server']
                                ),
                                customxml.PubSubXMPPURIProperty(
                                    getPubSubXMPPURI(id, pubSubConfiguration)
                                ),
                                type="XMPP",
                            )
                        )

                    propVal = customxml.PubSubPushTransportsProperty(*children)
                    nodeCacher = getNodeCacher()
                    d = nodeCacher.createNode(self.clientNotifier, nodeName)
                    # In either case we're going to return the value
                    d.addBoth(lambda ignored: propVal)
                    return d


            else:
                return succeed(customxml.PubSubPushTransportsProperty())

        if qname == (customxml.calendarserver_namespace, "pushkey"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if pubSubConfiguration['enabled']:
                if getattr(self, "clientNotifier", None) is not None:
                    id = self.clientNotifier.getID()
                    nodeName = getPubSubPath(id, pubSubConfiguration)
                    propVal = customxml.PubSubXMPPPushKeyProperty(nodeName)
                    nodeCacher = getNodeCacher()
                    d = nodeCacher.createNode(self.clientNotifier, nodeName)
                    # In either case we're going to return the xmpp-uri value
                    d.addBoth(lambda ignored: propVal)
                    return d
            else:
                return succeed(customxml.PubSubXMPPPushKeyProperty())


        if qname == (customxml.calendarserver_namespace, "xmpp-uri"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if pubSubConfiguration['enabled']:
                if getattr(self, "clientNotifier", None) is not None:
                    id = self.clientNotifier.getID()
                    nodeName = getPubSubPath(id, pubSubConfiguration)
                    propVal = customxml.PubSubXMPPURIProperty(
                        getPubSubXMPPURI(id, pubSubConfiguration))
                    nodeCacher = getNodeCacher()
                    d = nodeCacher.createNode(self.clientNotifier, nodeName)
                    # In either case we're going to return the xmpp-uri value
                    d.addBoth(lambda ignored: propVal)
                    return d
            else:
                return succeed(customxml.PubSubXMPPURIProperty())

        elif qname == (customxml.calendarserver_namespace, "xmpp-heartbeat-uri"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if pubSubConfiguration['enabled']:
                return succeed(
                    customxml.PubSubHeartbeatProperty(
                        customxml.PubSubHeartbeatURIProperty(
                            getPubSubHeartbeatURI(pubSubConfiguration)
                        ),
                        customxml.PubSubHeartbeatMinutesProperty(
                            str(pubSubConfiguration['heartrate'])
                        )
                    )
                )
            else:
                return succeed(customxml.PubSubHeartbeatURIProperty())

        elif qname == (customxml.calendarserver_namespace, "xmpp-server"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if pubSubConfiguration['enabled']:
                return succeed(customxml.PubSubXMPPServerProperty(
                    pubSubConfiguration['xmpp-server']))
            else:
                return succeed(customxml.PubSubXMPPServerProperty())

        return super(CalendarHomeFile, self).readProperty(property, request)


class ScheduleFile (ReadOnlyResourceMixIn, AutoProvisioningFileMixIn, CalDAVFile):
    def __init__(self, path, parent):
        super(ScheduleFile, self).__init__(path, principalCollections=parent.principalCollections())

    def isCollection(self):
        return True

    def createSimilarFile(self, path):
        if self.comparePath(path):
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

class ScheduleInboxFile (ScheduleInboxResource, ScheduleFile):
    """
    Calendar scheduling inbox collection resource.
    """
    def __init__(self, path, parent):
        ScheduleFile.__init__(self, path, parent)
        ScheduleInboxResource.__init__(self, parent)

    def __repr__(self):
        return "<%s (calendar inbox collection): %s>" % (self.__class__.__name__, self.fp.path)


    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(deliverSchedulePrivilegeSet)

class ScheduleOutboxFile (ScheduleOutboxResource, ScheduleFile):
    """
    Calendar scheduling outbox collection resource.
    """
    def __init__(self, path, parent):
        ScheduleFile.__init__(self, NotFilePath(isdir=True), parent)
        ScheduleOutboxResource.__init__(self, parent)

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties

    def etag(self):
        return None

    def provision(self):
        """
        Schedule outboxes do not need to be provisioned; they shouldn't store
        anything.
        """

    def __repr__(self):
        return "<%s (calendar outbox collection): %s>" % (self.__class__.__name__, self.fp.path)


    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(sendSchedulePrivilegeSet)

    def report_urn_ietf_params_xml_ns_caldav_calendar_query(self, request, calendar_query):
        return succeed(MultiStatusResponse(()))
        
    def report_urn_ietf_params_xml_ns_caldav_calendar_multiget(self, request, multiget):
        responses = [davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)) for href in multiget.resources]
        return succeed(MultiStatusResponse((responses)))

class IScheduleInboxFile (ReadOnlyResourceMixIn, IScheduleInboxResource, CalDAVFile):
    """
    Server-to-server scheduling inbox resource.
    """
    def __init__(self, path, parent):
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())
        IScheduleInboxResource.__init__(self, parent)

    def __repr__(self):
        return "<%s (server-to-server inbox resource): %s>" % (self.__class__.__name__, self.fp.path)

    def isCollection(self):
        return False

    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self
        else:
            return responsecode.NOT_FOUND

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties

    def etag(self):
        return None

    def checkPreconditions(self, request):
        return None

    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(deliverSchedulePrivilegeSet)



class FreeBusyURLFile (ReadOnlyResourceMixIn, AutoProvisioningFileMixIn, FreeBusyURLResource, CalDAVFile):
    """
    Free-busy URL resource.
    """
    def __init__(self, path, parent):
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())
        FreeBusyURLResource.__init__(self, parent)

    def __repr__(self):
        return "<%s (free-busy URL resource): %s>" % (self.__class__.__name__, self.fp.path)

    def isCollection(self):
        return False

    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self
        else:
            return responsecode.NOT_FOUND

    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(deliverSchedulePrivilegeSet)

class DropBoxHomeFile (AutoProvisioningFileMixIn, DropBoxHomeResource, CalDAVFile):
    def __init__(self, path, parent):
        DropBoxHomeResource.__init__(self)
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())
        self.parent = parent

    def createSimilarFile(self, path):
        if self.comparePath(path):
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
        if self.comparePath(path):
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
        if self.comparePath(path):
            return self
        else:
            return responsecode.NOT_FOUND

class TimezoneServiceFile (ReadOnlyResourceMixIn, TimezoneServiceResource, CalDAVFile):
    def __init__(self, path, parent):
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())
        TimezoneServiceResource.__init__(self, parent)

        assert self.fp.isfile() or not self.fp.exists()

    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self
        else:
            return responsecode.NOT_FOUND

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties

    def etag(self):
        return None

    def checkPreconditions(self, request):
        return None

    def checkPrivileges(self, request, privileges, recurse=False, principal=None, inherited_aces=None):
        return succeed(None)

class NotificationCollectionFile(ReadOnlyResourceMixIn, NotificationCollectionResource, CalDAVFile):
    """
    Notification collection resource.
    """
    def __init__(self, path, parent):
        NotificationCollectionResource.__init__(self)
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())
        self.parent = parent

    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self
        else:
            return NotificationFile(path, self)

    def __repr__(self):
        return "<%s (notification collection): %s>" % (self.__class__.__name__, self.fp.path)

    def _writeNotification(self, request, uid, rname, xmltype, xmldata):
        
        # TODO: use the generic StoreObject api so that quota, sync-token etc all get changed properly
        child = self.createSimilarFile(self.fp.child(rname).path)
        def _defer(_):
            child.writeDeadProperty(davxml.GETContentType.fromString(generateContentType(MimeType("text", "xml", params={"charset":"utf-8"}))))
            child.writeDeadProperty(customxml.NotificationType(xmltype))
            return True

        url = request.urlForResource(self)
        url = joinURL(url, rname)
        request._rememberResource(child, url)
        d = put_common.storeResource(request, data=xmldata, destination=child, destination_uri=url)
        d.addCallback(_defer)
        return d


    def _deleteNotification(self, request, rname):
        child = self.createSimilarFile(self.fp.child(rname).path)
        url = request.urlForResource(self)
        url = joinURL(url, rname)
        request._rememberResource(child, url)
        return delete_common.deleteResource(request, child, url)

class NotificationFile(NotificationResource, CalDAVFile):

    def __init__(self, path, parent):
        NotificationResource.__init__(self, parent)
        CalDAVFile.__init__(self, path, principalCollections=parent.principalCollections())

        assert self.fp.isfile() or not self.fp.exists()

    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self
        else:
            return responsecode.NOT_FOUND

    def __repr__(self):
        return "<%s (notification file): %s>" % (self.__class__.__name__, self.fp.path)
        
    def resourceName(self):
        return self.fp.basename()

class AddressBookHomeProvisioningFile (AutoProvisioningFileMixIn, DirectoryAddressBookHomeProvisioningResource, DAVFile):
    """
    Resource which provisions address book home collections as needed.
    """
    def __init__(self, path, directory, url, store):
        """
        @param path: the path to the file which will back the resource.
        @param directory: an L{IDirectoryService} to provision address books from.
        @param url: the canonical URL for the resource.
        """
        DAVFile.__init__(self, path)
        DirectoryAddressBookHomeProvisioningResource.__init__(self, directory, url)
        self._newStore = store


    def provisionChild(self, name):
        if name == uidsResourceNameAddressBook:
            return AddressBookHomeUIDProvisioningFile(self.fp.child(name).path, self)

        return AddressBookHomeTypeProvisioningFile(self.fp.child(name).path, self, name)

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

class AddressBookHomeTypeProvisioningFile (AutoProvisioningFileMixIn, DirectoryAddressBookHomeTypeProvisioningResource, DAVFile):
    def __init__(self, path, parent, recordType):
        """
        @param path: the path to the file which will back the resource.
        @param parent: the parent of this resource
        @param recordType: the directory record type to provision.
        """
        DAVFile.__init__(self, path)
        DirectoryAddressBookHomeTypeProvisioningResource.__init__(self, parent, recordType)

class AddressBookHomeUIDProvisioningFile (AutoProvisioningFileMixIn, DirectoryAddressBookHomeUIDProvisioningResource, DAVFile):
    def __init__(self, path, parent, homeResourceClass=None):
        """
        @param path: the path to the file which will back the resource.
        """
        DAVFile.__init__(self, path)
        DirectoryAddressBookHomeUIDProvisioningResource.__init__(self, parent)
        if homeResourceClass is None:
            self.homeResourceClass = AddressBookHomeFile
        else:
            self.homeResourceClass = homeResourceClass

    def locateChild(self, request, segments):

        name = segments[0]
        if name == "":
            return (self, ())

        record = self.directory.recordWithUID(name)
        if record:
            return (self.homeResourceForRecord(record, request), segments[1:])
        else:
            return (None, ())

    def homeResourceForRecord(self, record, request):
        self.provision()
        transaction = _transactionFromRequest(request, self.parent._newStore)

        name = record.uid

        if record is None:
            log.msg("No directory record with GUID %r" % (name,))
            return None

        if not record.enabledForAddressBooks:
            log.msg("Directory record %r is not enabled for address books" % (record,))
            return None

        assert len(name) > 4
        
        childPath = self.fp.child(name[0:2]).child(name[2:4]).child(name)
        child = self.homeResourceClass(childPath.path, self, record, transaction)

        if not child.exists():
            self.provision()

            if not childPath.parent().isdir():
                childPath.parent().makedirs()

            for oldPath in (
                # Pre 2.0: All in one directory
                self.fp.child(name),
                # Pre 1.2: In types hierarchy instead of the GUID hierarchy
                self.parent.getChild(record.recordType).fp.child(record.shortNames[0]),
            ):
                if oldPath.exists():
                    # The child exists at an old location.  Move to new location.
                    log.msg("Moving address book home from old location %r to new location %r." % (oldPath, childPath))
                    try:
                        oldPath.moveTo(childPath)
                    except (OSError, IOError), e:
                        log.err("Error moving address book home %r: %s" % (oldPath, e))
                        raise HTTPError(StatusResponse(
                            responsecode.INTERNAL_SERVER_ERROR,
                            "Unable to move address book home."
                        ))
                    child.fp.restat(False)
                    break
            else:
                #
                # NOTE: provisionDefaultAddressBooks() returns a deferred, which we are ignoring.
                # The result being that the default calendars will be present at some point
                # in the future, not necessarily right now, and we don't have a way to wait
                # on that to finish.
                #
                child.provisionDefaultAddressBooks()

                #
                # Try to work around the above a little by telling the client that something
                # when wrong temporarily if the child isn't provisioned right away.
                #
                if not child.exists():
                    raise HTTPError(StatusResponse(
                        responsecode.SERVICE_UNAVAILABLE,
                        "Provisioning address book home."
                    ))

            assert child.exists()

        return child

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

class AddressBookHomeFile (AutoProvisioningFileMixIn, SharedHomeMixin, DirectoryAddressBookHomeResource, CalDAVFile):
    """
    Address book home collection resource.
    """
    
    def liveProperties(self):
        return super(AddressBookHomeFile, self).liveProperties() + (
            (customxml.calendarserver_namespace, "push-transports"),
            (customxml.calendarserver_namespace, "pushkey"),
            (customxml.calendarserver_namespace, "xmpp-uri"),
            (customxml.calendarserver_namespace, "xmpp-heartbeat-uri"),
            (customxml.calendarserver_namespace, "xmpp-server"),
        )

    def __init__(self, path, parent, record, transaction):
        """
        @param path: the path to the file which will back the resource.
        """

        self.associateWithTransaction(transaction)

        # TODO: when addressbook home gets a resourceID( ) method, remove
        # the "id=record.uid" keyword from this call:
        # self.clientNotifier = ClientNotifier(self, id=record.uid)
        self._newStoreAddressBookHome = (
            transaction.addressbookHomeWithUID(record.uid, create=True)
        )
        CalDAVFile.__init__(self, path)
        DirectoryAddressBookHomeResource.__init__(self, parent, record)

        from twistedcaldav.storebridge import _NewStorePropertiesWrapper
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreAddressBookHome.properties()
        )


    def sharesDB(self):
        """
        Retrieve the new-style shares DB wrapper.
        """
        if not hasattr(self, "_sharesDB"):
            self._sharesDB = self._newStoreAddressBookHome.retrieveOldShares()
        return self._sharesDB


    def exists(self):
        # FIXME: tests
        return True
    
    
    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)


    def provision(self):
        if config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled:
            self.provisionShares()
        self.provisionLinks()

    def provisionLinks(self):
        
        if not hasattr(self, "_provisionedLinks"):
            if config.GlobalAddressBook.Enabled:
                self.putChild(
                    config.GlobalAddressBook.Name,
                    LinkResource(self, "/addressbooks/public/global/addressbook/"),
                )
            self._provisionedLinks = True

    def provisionChild(self, name):
 
        if config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled and not config.Sharing.Calendars.Enabled:
            NotificationCollectionFileClass = NotificationCollectionFile
        else:
            NotificationCollectionFileClass = None

        cls = {
            "notification" : NotificationCollectionFileClass,
        }.get(name, None)

        if cls is not None:
            child = cls(self.fp.child(name).path, self)
            return child
        return self.createSimilarFile(self.fp.child(name).path)

    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self
        else:
            if not isinstance(path, FilePath):
                path = FilePath(path)

            # Check for public/global path
            from twistedcaldav.storebridge import (
                AddressBookCollectionFile,
                ProtoAddressBookCollectionFile,
                GlobalAddressBookCollectionFile,
                ProtoGlobalAddressBookCollectionFile,
            )
            mainCls = AddressBookCollectionFile
            protoCls = ProtoAddressBookCollectionFile
            if isinstance(self.record, InternalDirectoryRecord):
                if "global" in self.record.shortNames:
                    mainCls = GlobalAddressBookCollectionFile
                    protoCls = ProtoGlobalAddressBookCollectionFile

            newAddressBook = self._newStoreAddressBookHome.addressbookWithName(
                path.basename()
            )
            if newAddressBook is None:
                # Local imports.due to circular dependency between modules.
                similar = protoCls(
                    self._newStoreAddressBookHome,
                    path, principalCollections=self.principalCollections()
                )
            else:
                similar = mainCls(
                    newAddressBook, self._newStoreAddressBookHome,
                    path, principalCollections=self.principalCollections()
                )
            self.propagateTransaction(similar)
            return similar

    def getChild(self, name):
        # This avoids finding case variants of put children on case-insensitive filesystems.
        if name not in self.putChildren and name.lower() in (x.lower() for x in self.putChildren):
            return None

        return super(AddressBookHomeFile, self).getChild(name)


    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == (customxml.calendarserver_namespace, "push-transports"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if (pubSubConfiguration['enabled'] and
                getattr(self, "clientNotifier", None) is not None):
                    id = self.clientNotifier.getID()
                    nodeName = getPubSubPath(id, pubSubConfiguration)
                    children = []
                    if pubSubConfiguration['aps-bundle-id']:
                        children.append(
                            customxml.PubSubTransportProperty(
                                customxml.PubSubSubscriptionProperty(
                                    davxml.HRef(
                                        pubSubConfiguration['subscription-url']
                                    ),
                                ),
                                customxml.PubSubAPSBundleIDProperty(
                                    pubSubConfiguration['aps-bundle-id']
                                ),
                                type="APSD",
                            )
                        )
                    if pubSubConfiguration['xmpp-server']:
                        children.append(
                            customxml.PubSubTransportProperty(
                                customxml.PubSubXMPPServerProperty(
                                    pubSubConfiguration['xmpp-server']
                                ),
                                customxml.PubSubXMPPURIProperty(
                                    getPubSubXMPPURI(id, pubSubConfiguration)
                                ),
                                type="XMPP",
                            )
                        )

                    propVal = customxml.PubSubPushTransportsProperty(*children)
                    nodeCacher = getNodeCacher()
                    d = nodeCacher.createNode(self.clientNotifier, nodeName)
                    # In either case we're going to return the value
                    d.addBoth(lambda ignored: propVal)
                    return d


            else:
                return succeed(customxml.PubSubPushTransportsProperty())

        if qname == (customxml.calendarserver_namespace, "pushkey"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if pubSubConfiguration['enabled']:
                if getattr(self, "clientNotifier", None) is not None:
                    id = self.clientNotifier.getID()
                    nodeName = getPubSubPath(id, pubSubConfiguration)
                    propVal = customxml.PubSubXMPPPushKeyProperty(nodeName)
                    nodeCacher = getNodeCacher()
                    d = nodeCacher.createNode(self.clientNotifier, nodeName)
                    # In either case we're going to return the xmpp-uri value
                    d.addBoth(lambda ignored: propVal)
                    return d
            else:
                return succeed(customxml.PubSubXMPPPushKeyProperty())


        if qname == (customxml.calendarserver_namespace, "xmpp-uri"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if pubSubConfiguration['enabled']:
                if getattr(self, "clientNotifier", None) is not None:
                    id = self.clientNotifier.getID()
                    nodeName = getPubSubPath(id, pubSubConfiguration)
                    propVal = customxml.PubSubXMPPURIProperty(
                        getPubSubXMPPURI(id, pubSubConfiguration))
                    nodeCacher = getNodeCacher()
                    d = nodeCacher.createNode(self.clientNotifier, nodeName)
                    # In either case we're going to return the xmpp-uri value
                    d.addBoth(lambda ignored: propVal)
                    return d
            else:
                return succeed(customxml.PubSubXMPPURIProperty())

        elif qname == (customxml.calendarserver_namespace, "xmpp-heartbeat-uri"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if pubSubConfiguration['enabled']:
                return succeed(
                    customxml.PubSubHeartbeatProperty(
                        customxml.PubSubHeartbeatURIProperty(
                            getPubSubHeartbeatURI(pubSubConfiguration)
                        ),
                        customxml.PubSubHeartbeatMinutesProperty(
                            str(pubSubConfiguration['heartrate'])
                        )
                    )
                )
            else:
                return succeed(customxml.PubSubHeartbeatURIProperty())

        elif qname == (customxml.calendarserver_namespace, "xmpp-server"):
            pubSubConfiguration = getPubSubConfiguration(config)
            if pubSubConfiguration['enabled']:
                return succeed(customxml.PubSubXMPPServerProperty(
                    pubSubConfiguration['xmpp-server']))
            else:
                return succeed(customxml.PubSubXMPPServerProperty())

        return super(AddressBookHomeFile, self).readProperty(property, request)


class DirectoryBackedAddressBookFile (ReadOnlyResourceMixIn, DirectoryBackedAddressBookResource, CalDAVFile):
    """
    Directory-backed address book, supporting directory vcard search.
    """
    def __init__(self, path, principalCollections):
        CalDAVFile.__init__(self, path, principalCollections=principalCollections)
        DirectoryBackedAddressBookResource.__init__(self)

        # create with permissions, similar to CardDAVOptions in tap.py
        # FIXME:  /Directory does not need to be in file system unless debug-only caching options are used
        try:
            os.mkdir(path)
            os.chmod(path, 0750)
            if config.UserName and config.GroupName:
                import pwd
                import grp
                uid = pwd.getpwnam(config.UserName)[2]
                gid = grp.getgrnam(config.GroupName)[2]
                os.chown(path, uid, gid)
 
            log.msg("Created %s" % (path,))
            
        except (OSError,), e:
            # this is caused by multiprocessor race and is harmless
            if e.errno != errno.EEXIST:
                raise

    
    def getChild(self, name):
        
        if name is "":
            return self
        else:
            from twistedcaldav.simpleresource import SimpleCalDAVResource
            return SimpleCalDAVResource(principalCollections=self.principalCollections())
       
    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self
        else:
            from twistedcaldav.simpleresource import SimpleCalDAVResource
            return SimpleCalDAVResource(principalCollections=self.principalCollections())
 
class GlobalAddressBookFile (ReadOnlyResourceMixIn, GlobalAddressBookResource, CalDAVFile):
    """
    Directory-backed address book, supporting directory vcard search.
    """
    def __init__(self, path, principalCollections):
        CalDAVFile.__init__(self, path, principalCollections=principalCollections)
        # self.clientNotifier = ClientNotifier(self)

    def createSimilarFile(self, path):
        if self.comparePath(path):
            return self
        else:
            similar = CalDAVFile(path, principalCollections=self.principalCollections())
            return similar

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

def _schedulePrivilegeSet(deliver):
    edited = False

    top_supported_privileges = []

    for supported_privilege in davPrivilegeSet.childrenOfType(davxml.SupportedPrivilege):
        all_privilege = supported_privilege.childOfType(davxml.Privilege)
        if isinstance(all_privilege.children[0], davxml.All):
            all_description = supported_privilege.childOfType(davxml.Description)
            all_supported_privileges = list(supported_privilege.childrenOfType(davxml.SupportedPrivilege))
            all_supported_privileges.append(
                davxml.SupportedPrivilege(
                    davxml.Privilege(caldavxml.ScheduleDeliver() if deliver else caldavxml.ScheduleSend()),
                    davxml.Description("schedule privileges for current principal", **{"xml:lang": "en"}),
                ),
            )
            if config.Scheduling.CalDAV.OldDraftCompatibility:
                all_supported_privileges.append(
                    davxml.SupportedPrivilege(
                        davxml.Privilege(caldavxml.Schedule()),
                        davxml.Description("old-style schedule privileges for current principal", **{"xml:lang": "en"}),
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

deliverSchedulePrivilegeSet = _schedulePrivilegeSet(True)
sendSchedulePrivilegeSet = _schedulePrivilegeSet(False)

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
                        )
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
setattr(CalendarHomeFile, "http_ACL", None)
setattr(AddressBookHomeFile, "http_ACL", None)

setattr(DropBoxCollectionFile, "http_MKCALENDAR", None)
setattr(DropBoxChildFile, "http_MKCOL", None)
setattr(DropBoxChildFile, "http_MKCALENDAR", None)

# FIXME: Little bit of a circular dependency here...
twistedcaldav.method.acl.CalDAVFile      = CalDAVFile
twistedcaldav.method.copymove.CalDAVFile = CalDAVFile
twistedcaldav.method.delete.CalDAVFile   = CalDAVFile
twistedcaldav.method.get.CalDAVFile      = CalDAVFile
twistedcaldav.method.mkcol.CalDAVFile    = CalDAVFile
twistedcaldav.method.propfind.CalDAVFile = CalDAVFile
twistedcaldav.method.put.CalDAVFile      = CalDAVFile


