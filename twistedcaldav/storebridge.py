# -*- test-case-name: twistedcaldav.test.test_wrapping -*-
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
Wrappers to translate between the APIs in L{txcaldav.icalendarstore} and
L{txcarddav.iaddressbookstore} and those in L{twistedcaldav}.
"""

import hashlib

from urlparse import urlsplit

from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twisted.internet.protocol import Protocol
from twisted.python.util import FancyEqMixin

from twext.python import vcomponent
from twext.python.filepath import CachingFilePath as FilePath
from twext.python.log import Logger

from twext.web2.http_headers import ETag, MimeType
from twext.web2.dav.http import ErrorResponse, ResponseQueue
from twext.web2.dav.element.base import dav_namespace
from twext.web2.responsecode import (
    FORBIDDEN, NO_CONTENT, NOT_FOUND, CREATED, CONFLICT, PRECONDITION_FAILED,
    BAD_REQUEST, OK, NOT_IMPLEMENTED, NOT_ALLOWED)
from twext.web2.dav import davxml
from twext.web2.dav.resource import TwistedGETContentMD5, TwistedACLInheritable
from twext.web2.dav.util import parentForURL, allDataFromStream, joinURL, \
    davXMLFromStream
from twext.web2.http import HTTPError, StatusResponse, Response
from twext.web2.stream import ProducerStream, readStream

from twistedcaldav.static import CalDAVFile, ScheduleInboxFile, \
    NotificationCollectionFile, NotificationFile, GlobalAddressBookFile
from twistedcaldav.vcard import Component as VCard
from twistedcaldav.resource import CalDAVResource

from txdav.common.icommondatastore import NoSuchObjectResourceError, \
    InternalDataStoreError
from txdav.propertystore.base import PropertyName

from twistedcaldav.caldavxml import ScheduleTag, caldav_namespace
from twistedcaldav.scheduling.implicit import ImplicitScheduler
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError

from twisted.python.log import err as logDefaultException
from twistedcaldav.method.propfind import http_PROPFIND

log = Logger()


class _NewStorePropertiesWrapper(object):
    """
    Wrap a new-style property store (a L{txdav.idav.IPropertyStore}) in the old-
    style interface for compatibility with existing code.
    """

    # FIXME: UID arguments on everything need to be tested against something.
    def __init__(self, newPropertyStore):
        """
        Initialize an old-style property store from a new one.

        @param newPropertyStore: the new-style property store.
        @type newPropertyStore: L{txdav.idav.IPropertyStore}
        """
        self._newPropertyStore = newPropertyStore

    @classmethod
    def _convertKey(cls, qname):
        namespace, name = qname
        return PropertyName(namespace, name)


    # FIXME 'uid' here should be verifying something.
    def get(self, qname, uid=None):
        """
        
        """
        try:
            return self._newPropertyStore[self._convertKey(qname)]
        except KeyError:
            raise HTTPError(StatusResponse(
                    NOT_FOUND,
                    "No such property: {%s}%s" % qname))


    def set(self, property, uid=None):
        """
        
        """
        self._newPropertyStore[self._convertKey(property.qname())] = property


    def delete(self, qname, uid=None):
        """
        
        """
        del self._newPropertyStore[self._convertKey(qname)]


    def contains(self, qname, uid=None, cache=True):
        """
        
        """
        return (self._convertKey(qname) in self._newPropertyStore)


    def list(self, uid=None, filterByUID=True, cache=True):
        """
        
        """
        return [(pname.namespace, pname.name) for pname in
                self._newPropertyStore.keys()]



def requiresPermissions(*permissions, **kw):
    """
    A decorator to wrap http_ methods in, to indicate that they should not be
    run until the current user principal has been authorized for the given
    permission set.
    """
    fromParent = kw.get('fromParent')
    # FIXME: direct unit tests
    def wrap(thunk):
        def authAndContinue(self, request):
            if permissions:
                d = self.authorize(request, permissions)
            else:
                d = succeed(None)
            if fromParent:
                d.addCallback(
                    lambda whatever:
                        request.locateResource(parentForURL(request.uri))
                ).addCallback(
                    lambda parent:
                        parent.authorize(request, fromParent)
                )
            d.addCallback(lambda whatever: thunk(self, request))
            return d
        return authAndContinue
    return wrap



class _CalendarChildHelper(object):
    """
    Methods for things which are like calendars.
    """

    def _initializeWithCalendar(self, calendar, home):
        """
        Initialize with a calendar.

        @param calendar: the wrapped calendar.
        @type calendar: L{txcaldav.icalendarstore.ICalendar}

        @param home: the home through which the given calendar was accessed.
        @type home: L{txcaldav.icalendarstore.ICalendarHome}
        """
        self._newStoreCalendar = calendar
        self._newStoreParentHome = home
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreCalendar.properties()
        )


    def index(self):
        """
        Retrieve the new-style index wrapper.
        """
        return self._newStoreCalendar.retrieveOldIndex()


    def invitesDB(self):
        """
        Retrieve the new-style invites DB wrapper.
        """
        if not hasattr(self, "_invitesDB"):
            self._invitesDB = self._newStoreCalendar.retrieveOldInvites()
        return self._invitesDB

    def exists(self):
        # FIXME: tests
        return True


    @classmethod
    def transform(cls, self, calendar, home):
        """
        Transform C{self} into a L{CalendarCollectionFile}.
        """
        self.__class__ = cls
        self._initializeWithCalendar(calendar, home)


    def createSimilarFile(self, path):
        """
        Create a L{CalendarObjectFile} or L{ProtoCalendarObjectFile} based on a
        path object.
        """
        if not isinstance(path, FilePath):
            path = FilePath(path)

        newStoreObject = self._newStoreCalendar.calendarObjectWithName(
            path.basename()
        )

        if newStoreObject is not None:
            similar = CalendarObjectFile(newStoreObject, path,
                principalCollections=self._principalCollections)
        else:
            # FIXME: creation in http_PUT should talk to a specific resource
            # type; this is the domain of StoreCalendarObjectResource.
            # similar = ProtoCalendarObjectFile(self._newStoreCalendar, path)
            similar = ProtoCalendarObjectFile(self._newStoreCalendar, path,
                principalCollections=self._principalCollections)

        # FIXME: tests should be failing without this line.
        # Specifically, http_PUT won't be committing its transaction properly.
        self.propagateTransaction(similar)
        return similar


    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)



class StoreScheduleInboxFile(_CalendarChildHelper, ScheduleInboxFile):

    def __init__(self, *a, **kw):
        super(StoreScheduleInboxFile, self).__init__(*a, **kw)
        self.parent.propagateTransaction(self)
        home = self.parent._newStoreCalendarHome
        storage = home.calendarWithName("inbox")
        if storage is None:
            # raise RuntimeError("backend should be handling this for us")
            # FIXME: spurious error, sanity check, should not be needed;
            # unfortunately, user09's calendar home does not have an inbox, so
            # this is a temporary workaround.
            home.createCalendarWithName("inbox")
            storage = home.calendarWithName("inbox")
        self._initializeWithCalendar(
            storage,
            self.parent._newStoreCalendarHome
        )


    def isCollection(self):
        return True


    def provisionFile(self):
        pass


    def provision(self):
        pass



class _GetChildHelper(CalDAVResource):

    def locateChild(self, request, segments):
        if segments[0] == '':
            return self, segments[1:]
        return self.getChild(segments[0]), segments[1:]


    def getChild(self, name):
        return None


    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == (dav_namespace, "resourcetype"):
            return self.resourceType(request)
        return super(_GetChildHelper, self).readProperty(property, request)


    def davComplianceClasses(self):
        return ("1", "access-control")


    @requiresPermissions(davxml.Read())
    def http_GET(self, request):
        return super(_GetChildHelper, self).http_GET(request)


    http_PROPFIND = http_PROPFIND



class DropboxCollection(_GetChildHelper):
    """
    A collection of all dropboxes (containers for attachments), presented as a
    resource under the user's calendar home, where a dropbox is a
    L{CalendarObjectDropbox}.
    """
    # FIXME: no direct tests for this class at all.

    def __init__(self, path, parent, *a, **kw):
        # FIXME: constructor signature takes a 'path' because CalendarHomeFile
        # requires it, but we don't need it (and shouldn't have it) eventually.
        kw.update(principalCollections=parent.principalCollections())
        super(DropboxCollection, self).__init__(*a, **kw)
        self._newStoreCalendarHome = parent._newStoreCalendarHome
        parent.propagateTransaction(self)


    def isCollection(self):
        """
        It is a collection.
        """
        return True


    def getChild(self, name):
        calendarObject = self._newStoreCalendarHome.calendarObjectWithDropboxID(name)
        if calendarObject is None:
            return NoDropboxHere()
        objectDropbox = CalendarObjectDropbox(
            calendarObject, principalCollections=self.principalCollections()
        )
        self.propagateTransaction(objectDropbox)
        return objectDropbox


    def resourceType(self, request):
        return succeed(davxml.ResourceType.dropboxhome)


    def listChildren(self):
        l = []
        for everyCalendar in self._newStoreCalendarHome.calendars():
            for everyObject in everyCalendar.calendarObjects():
                l.append(everyObject.dropboxID())
        return l



class NoDropboxHere(_GetChildHelper):

    def isCollection(self):
        return False


    def http_GET(self, request):
        return NOT_FOUND


    def http_MKCALENDAR(self, request):
        return NOT_ALLOWED


    def http_MKCOL(self, request):
        return NOT_IMPLEMENTED



class CalendarObjectDropbox(_GetChildHelper):
    """
    A wrapper around a calendar object which serves that calendar object's
    attachments as a DAV collection.
    """

    def __init__(self, calendarObject, *a, **kw):
        super(CalendarObjectDropbox, self).__init__(*a, **kw)
        self._newStoreCalendarObject = calendarObject


    def isCollection(self):
        return True


    def resourceType(self, request):
        return succeed(davxml.ResourceType.dropbox)


    def getChild(self, name):
        attachment = self._newStoreCalendarObject.attachmentWithName(name)
        if attachment is None:
            result = ProtoCalendarAttachment(
                self._newStoreCalendarObject,
                name,
                principalCollections=self.principalCollections())
        else:
            result = CalendarAttachment(
                self._newStoreCalendarObject,
                attachment, principalCollections=self.principalCollections())
        self.propagateTransaction(result)
        return result


    @inlineCallbacks
    def http_ACL(self, request):
        """
        Don't ever actually make changes, but attempt to deny any ACL requests
        that refer to permissions not referenced by attendees in the iCalendar
        data.
        """
        attendees = self._newStoreCalendarObject.component().getAttendees()
        attendees = [attendee.split("urn:uuid:")[-1] for attendee in attendees]
        document = yield davXMLFromStream(request.stream)
        for ace in document.root_element.children:
            for element in ace.children:
                if isinstance(element, davxml.Principal):
                    for href in element.children:
                        principalURI = href.children[0].data
                        uidsPrefix = '/principals/__uids__/'
                        if not principalURI.startswith(uidsPrefix):
                            # Unknown principal.
                            returnValue(FORBIDDEN)
                        principalElements = principalURI[
                            len(uidsPrefix):].split("/")
                        if principalElements[-1] == '':
                            principalElements.pop()
                        if principalElements[-1] in ('calendar-proxy-read',
                                                     'calendar-proxy-write'):
                            principalElements.pop()
                        if len(principalElements) != 1:
                            returnValue(FORBIDDEN)
                        principalUID = principalElements[0]
                        if principalUID not in attendees:
                            returnValue(FORBIDDEN)
        returnValue(OK)


    def http_MKCOL(self, request):
        return CREATED


    def http_DELETE(self, request):
        return NO_CONTENT


    def listChildren(self):
        l = []
        for attachment in self._newStoreCalendarObject.attachments():
            l.append(attachment.name())
        return l


    def accessControlList(self, *a, **kw):
        """
        All principals identified as ATTENDEEs on the event for this dropbox
        may read all its children.
        """
        d = super(CalendarObjectDropbox, self).accessControlList(*a, **kw)
        def moreACLs(originalACL):
            othersCanWrite = (
                self._newStoreCalendarObject.attendeesCanManageAttachments()
            )
            originalACEs = list(originalACL.children)
            cuas = self._newStoreCalendarObject.component().getAttendees()
            newACEs = []
            for calendarUserAddress in cuas:
                principal = self.principalForCalendarUserAddress(
                    calendarUserAddress
                )
                principalURL = principal.principalURL()
                if othersCanWrite:
                    privileges = [davxml.Privilege(davxml.All())]
                else:
                    privileges = [
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet())
                    ]
                newACEs.append(davxml.ACE(
                    davxml.Principal(davxml.HRef(principalURL)),
                    davxml.Grant(*privileges),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ))
            return davxml.ACL(*tuple(newACEs + originalACEs))
        d.addCallback(moreACLs)
        return d



class ProtoCalendarAttachment(_GetChildHelper):

    def __init__(self, calendarObject, attachmentName, **kw):
        super(ProtoCalendarAttachment, self).__init__(**kw)
        self.calendarObject = calendarObject
        self.attachmentName = attachmentName


    def isCollection(self):
        return False


    def http_DELETE(self, request):
        return NO_CONTENT


    # FIXME: Permissions should dictate a different response, sometimes.
    def http_GET(self, request):
        return NOT_FOUND


    @requiresPermissions(fromParent=[davxml.Bind()])
    def http_PUT(self, request):
        # FIXME: direct test
        # FIXME: transformation?

        content_type = request.headers.getHeader("content-type")
        if content_type is None:
            content_type = MimeType("application", "octet-stream")

        t = self.calendarObject.createAttachmentWithName(
            self.attachmentName,
            content_type,
        )
        def done(ignored):
            t.loseConnection()
            return CREATED
        return readStream(request.stream, t.write).addCallback(done)



class CalendarAttachment(_GetChildHelper):

    def __init__(self, calendarObject, attachment, **kw):
        super(CalendarAttachment, self).__init__(**kw)
        self._newStoreCalendarObject = calendarObject
        self._newStoreAttachment = attachment


    def etag(self):
        # FIXME: test
        md5 = self._newStoreAttachment.md5()
        return ETag(md5)


    def contentType(self):
        # FIXME: test
        return self._newStoreAttachment.contentType()


    def getChild(self, name):
        return None


    @requiresPermissions(davxml.WriteContent())
    def http_PUT(self, request):
        # FIXME: direct test
        # FIXME: refactor with ProtoCalendarAttachment.http_PUT
        # FIXME: CDT test to make sure that permissions are enforced.

        content_type = request.headers.getHeader("content-type")
        if content_type is None:
            content_type = MimeType("application", "octet-stream")

        t = self._newStoreAttachment.store(content_type)
        def done(ignored):
            t.loseConnection()
            return NO_CONTENT
        return readStream(request.stream, t.write).addCallback(done)


    @requiresPermissions(davxml.Read())
    def http_GET(self, request):
        stream = ProducerStream()
        class StreamProtocol(Protocol):
            def dataReceived(self, data):
                stream.write(data)
            def connectionLost(self, reason):
                stream.finish()
        self._newStoreAttachment.retrieve(StreamProtocol())
        return Response(OK, {"content-type":self.contentType()}, stream)

    @requiresPermissions(fromParent=[davxml.Unbind()])
    def http_DELETE(self, request):
        self._newStoreCalendarObject.removeAttachmentWithName(
            self._newStoreAttachment.name()
        )
        del self._newStoreCalendarObject
        self.__class__ = ProtoCalendarAttachment
        return NO_CONTENT


    def isCollection(self):
        return False



class CalendarCollectionFile(_CalendarChildHelper, CalDAVFile):
    """
    Wrapper around a L{txcaldav.icalendar.ICalendar}.
    """

    def __init__(self, calendar, home, *args, **kw):
        """
        Create a CalendarCollectionFile from a L{txcaldav.icalendar.ICalendar}
        and the arguments required for L{CalDAVFile}.
        """
        super(CalendarCollectionFile, self).__init__(*args, **kw)
        self._initializeWithCalendar(calendar, home)


    def isCollection(self):
        return True


    def isCalendarCollection(self):
        """
        Yes, it is a calendar collection.
        """
        return True


    @requiresPermissions(fromParent=[davxml.Unbind()])
    @inlineCallbacks
    def http_DELETE(self, request):
        """
        Override http_DELETE to validate 'depth' header. 
        """

        depth = request.headers.getHeader("depth", "infinity")
        if depth != "infinity":
            msg = "illegal depth header for DELETE on collection: %s" % (
                depth,
            )
            log.err(msg)
            raise HTTPError(StatusResponse(BAD_REQUEST, msg))
        response = (yield self.storeRemove(request, True, request.uri))
        returnValue(response)


    @inlineCallbacks
    def storeRemove(self, request, implicitly, where):
        """
        Delete this calendar collection resource, first deleting each contained
        calendar resource.

        This has to emulate the behavior in fileop.delete in that any errors
        need to be reported back in a multistatus response.

        @param request: The request used to locate child resources.  Note that
            this is the request which I{triggered} the C{DELETE}, but which may
            not actually be a C{DELETE} request itself.

        @type request: L{twext.web2.iweb.IRequest}

        @param implicitly: Should implicit scheduling operations be triggered
            as a resut of this C{DELETE}?

        @type implicitly: C{bool}

        @param where: the URI at which the resource is being deleted.
        @type where: C{str}

        @return: an HTTP response suitable for sending to a client (or
            including in a multi-status).

         @rtype: something adaptable to L{twext.web2.iweb.IResponse}
        """

        # Not allowed to delete the default calendar
        default = (yield self.isDefaultCalendar(request))
        if default:
            log.err("Cannot DELETE default calendar: %s" % (self,))
            raise HTTPError(ErrorResponse(FORBIDDEN,
                            (caldav_namespace,
                             "default-calendar-delete-allowed",)))

        # Is this a sharee's view of a shared calendar?  If so, they can't do
        # scheduling onto it, so just delete it and move on.
        isVirtual = yield self.isVirtualShare(request)
        if isVirtual:
            log.debug("Removing shared calendar %s" % (self,))
            yield self.removeVirtualShare(request)
            returnValue(NO_CONTENT)

        log.debug("Deleting calendar %s" % (self,))

        # 'deluri' is this resource's URI; I should be able to synthesize it
        # from 'self'.

        errors = ResponseQueue(where, "DELETE", NO_CONTENT)

        for childname in self.listChildren():

            childurl = joinURL(where, childname)

            # FIXME: use a more specific API; we should know what this child
            # resource is, and not have to look it up.  (Sharing information
            # needs to move into the back-end first, though.)
            child = (yield request.locateChildResource(self, childname))

            try:
                yield child.storeRemove(request, implicitly, childurl)
            except:
                logDefaultException()
                errors.add(childurl, BAD_REQUEST)

        # Now do normal delete

        # Handle sharing
        wasShared = (yield self.isShared(request))
        if wasShared:
            yield self.downgradeFromShare(request)

        # Actually delete it.
        self._newStoreParentHome.removeCalendarWithName(
            self._newStoreCalendar.name()
        )
        self.__class__ = ProtoCalendarCollectionFile
        del self._newStoreCalendar

        # FIXME: handle exceptions, possibly like this:

        #        if isinstance(more_responses, MultiStatusResponse):
        #            # Merge errors
        #            errors.responses.update(more_responses.children)

        response = errors.response()

        if response == NO_CONTENT:
            # Do some clean up
            yield self.deletedCalendar(request)

        returnValue(response)


    def http_COPY(self, request):
        """
        Copying of calendar collections isn't allowed.
        """
        # FIXME: no direct tests
        return FORBIDDEN


    # FIXME: access control
    @inlineCallbacks
    def http_MOVE(self, request):
        """
        Moving a calendar collection is allowed for the purposes of changing
        that calendar's name.
        """
        defaultCalendar = (yield self.isDefaultCalendar(request))
        # FIXME: created to fix CDT test, no unit tests yet
        sourceURI = request.uri
        destinationURI = urlsplit(request.headers.getHeader("destination"))[2]
        if parentForURL(sourceURI) != parentForURL(destinationURI):
            returnValue(FORBIDDEN)
        destination = yield request.locateResource(destinationURI)
        # FIXME: should really use something other than 'fp' attribute.
        basename = destination.fp.basename()
        calendar = self._newStoreCalendar
        calendar.rename(basename)
        CalendarCollectionFile.transform(destination, calendar,
                                         self._newStoreParentHome)
        del self._newStoreCalendar
        self.__class__ = ProtoCalendarCollectionFile
        self.movedCalendar(request, defaultCalendar,
                           destination, destinationURI)
        returnValue(NO_CONTENT)



class NoParent(CalDAVFile):
    def http_MKCALENDAR(self, request):
        return CONFLICT


    def http_PUT(self, request):
        return CONFLICT



class ProtoCalendarCollectionFile(CalDAVFile):
    """
    A resource representing a calendar collection which hasn't yet been created.
    """

    def __init__(self, home, *args, **kw):
        """
        A placeholder resource for a calendar collection which does not yet
        exist, but will become a L{CalendarCollectionFile}.

        @param home: The calendar home which will be this resource's parent,
            when it exists.

        @type home: L{txcaldav.icalendarstore.ICalendarHome}
        """
        self._newStoreParentHome = home
        super(ProtoCalendarCollectionFile, self).__init__(*args, **kw)


    def isCollection(self):
        return True

    def createSimilarFile(self, path):
        # FIXME: this is necessary for 
        # twistedcaldav.test.test_mkcalendar.
        #     MKCALENDAR.test_make_calendar_no_parent - there should be a more
        # structured way to refuse creation with a non-existent parent.
        return NoParent(path)


    def provisionFile(self):
        """
        Create a calendar collection.
        """
        # FIXME: there should be no need for this.
        return self.createCalendarCollection()


    def createCalendarCollection(self):
        """
        Override C{createCalendarCollection} to actually do the work.
        """
        d = succeed(CREATED)

        calendarName = self.fp.basename()
        self._newStoreParentHome.createCalendarWithName(calendarName)
        newStoreCalendar = self._newStoreParentHome.calendarWithName(
            calendarName
        )
        CalendarCollectionFile.transform(
            self, newStoreCalendar, self._newStoreParentHome
        )
        return d


    def exists(self):
        # FIXME: tests
        return False


    def provision(self):
        """
        This resource should do nothing if it's provisioned.
        """
        # FIXME: should be deleted, or raise an exception


    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)



class CalendarObjectFile(CalDAVFile, FancyEqMixin):
    """
    A resource wrapping a calendar object.
    """

    compareAttributes = '_newStoreObject'.split()

    def __init__(self, calendarObject, *args, **kw):
        """
        Construct a L{CalendarObjectFile} from an L{ICalendarObject}.

        @param calendarObject: The storage for the calendar object.
        @type calendarObject: L{txcaldav.icalendarstore.ICalendarObject}
        """
        super(CalendarObjectFile, self).__init__(*args, **kw)
        self._initializeWithObject(calendarObject)


    def isCollection(self):
        return False


    def inNewTransaction(self, request):
        """
        Implicit auto-replies need to span multiple transactions.  Clean out
        the given request's resource-lookup mapping, transaction, and re-look-
        up my calendar object in a new transaction.

        Return the new transaction so it can be committed.
        """
        # FIXME: private names from 'file' implementation; maybe there should
        # be a public way to do this?  or maybe we should just have a real
        # queue.
        objectName = self._newStoreObject.name()
        calendarName = self._newStoreObject._calendar.name()
        homeUID = self._newStoreObject._calendar._calendarHome.uid()
        store = self._newStoreObject._transaction.store()
        txn = store.newTransaction("new transaction for " + self._newStoreObject.name())
        newObject = (txn.calendarHomeWithUID(homeUID)
                        .calendarWithName(calendarName)
                        .calendarObjectWithName(objectName))
        request._newStoreTransaction = txn
        request._resourcesByURL.clear()
        request._urlsByResource.clear()
        self._initializeWithObject(newObject)
        return txn


    def exists(self):
        # FIXME: Tests
        return True


    def name(self):
        return self._newStoreObject.name()


    def etag(self):
        # FIXME: far too slow to be used for real, but I needed something to
        # placate the etag computation in the case where the file doesn't exist
        # yet (an uncommited transaction creating this calendar file)

        # FIXME: direct tests
        try:
            if self.hasDeadProperty(TwistedGETContentMD5):
                return ETag(str(self.readDeadProperty(TwistedGETContentMD5)))
            else:
                return ETag(
                    hashlib.new("md5", self.iCalendarText()).hexdigest(),
                    weak=False
                )
        except (NoSuchObjectResourceError, InternalDataStoreError):
            # FIXME: a workaround for the fact that DELETE still rudely vanishes
            # the calendar object out from underneath the store, and doesn't
            # call storeRemove.
            return None


    def newStoreProperties(self):
        return self._newStoreObject.properties()


    def quotaSize(self, request):
        # FIXME: tests
        return succeed(len(self._newStoreObject.iCalendarText()))


    def iCalendarText(self, ignored=None):
        assert ignored is None, "This is a calendar object, not a calendar"
        return self._newStoreObject.iCalendarText()


    @requiresPermissions(fromParent=[davxml.Unbind()])
    def http_DELETE(self, request):
        """
        Override http_DELETE to validate 'depth' header. 
        """
        return self.storeRemove(request, True, request.uri)


    @inlineCallbacks
    def storeStream(self, stream):
        # FIXME: direct tests
        component = vcomponent.VComponent.fromString(
            (yield allDataFromStream(stream))
        )
        self._newStoreObject.setComponent(component)
        returnValue(NO_CONTENT)


    def validIfScheduleMatch(self, request):
        """
        Check to see if the given request's C{If-Schedule-Tag-Match} header
        matches this resource's schedule tag.

        @raise HTTPError: if the tag does not match.

        @return: None
        """
        # Note, internal requests shouldn't issue this.
        header = request.headers.getHeader("If-Schedule-Tag-Match")
        if header:
            # Do "precondition" test
            matched = False
            if self.hasDeadProperty(ScheduleTag):
                scheduletag = self.readDeadProperty(ScheduleTag)
                matched = (scheduletag == header)
            if not matched:
                log.debug(
                    "If-Schedule-Tag-Match: header value '%s' does not match resource value '%s'" %
                    (header, scheduletag,))
                raise HTTPError(PRECONDITION_FAILED)


    @inlineCallbacks
    def storeRemove(self, request, implicitly, where):
        """
        Delete this calendar object and do implicit scheduling actions if
        required.

        @param request: Unused by this implementation; present for signature
            compatibility with L{CalendarCollectionFile.storeRemove}.

        @type request: L{twext.web2.iweb.IRequest}

        @param implicitly: Should implicit scheduling operations be triggered
            as a resut of this C{DELETE}?

        @type implicitly: C{bool}

        @param where: the URI at which the resource is being deleted.
        @type where: C{str}

        @return: an HTTP response suitable for sending to a client (or
            including in a multi-status).

         @rtype: something adaptable to L{twext.web2.iweb.IResponse}
        """

        # TODO: need to use transaction based delete on live scheduling object
        # resources as the iTIP operation may fail and may need to prevent the
        # delete from happening.

        isinbox = self._newStoreObject._calendar.name() == "inbox"

        # Do If-Schedule-Tag-Match behavior first
        if not isinbox:
            self.validIfScheduleMatch(request)

        # Do quota checks before we start deleting things
        myquota = (yield self.quota(request))
        if myquota is not None:
            old_size = (yield self.quotaSize(request))
        else:
            old_size = 0

        scheduler = None
        lock = None
        if not isinbox and implicitly:
            # Get data we need for implicit scheduling
            calendar = (yield self.iCalendarForUser(request))
            scheduler = ImplicitScheduler()
            do_implicit_action, _ignore = (
                yield scheduler.testImplicitSchedulingDELETE(
                    request, self, calendar
                )
            )
            if do_implicit_action:
                lock = MemcacheLock(
                    "ImplicitUIDLock", calendar.resourceUID(), timeout=60.0
                )

        try:
            if lock:
                yield lock.acquire()

            storeCalendar = self._newStoreObject._calendar
            # Do delete

            # FIXME: public attribute please.  Should ICalendar maybe just have
            # a delete() method?
            storeCalendar.removeCalendarObjectWithName(
                self._newStoreObject.name()
            )

            # FIXME: clean this up with a 'transform' method
            self._newStoreParentCalendar = storeCalendar
            del self._newStoreObject
            self.__class__ = ProtoCalendarObjectFile

            # Adjust quota
            if myquota is not None:
                yield self.quotaSizeAdjust(request, -old_size)

            # Do scheduling
            if not isinbox and implicitly:
                yield scheduler.doImplicitScheduling()

        except MemcacheLockTimeoutError:
            raise HTTPError(StatusResponse(
                CONFLICT,
                "Resource: %s currently in use on the server." % (where,))
            )

        finally:
            if lock:
                yield lock.clean()

        returnValue(NO_CONTENT)


    def _initializeWithObject(self, calendarObject):
        self._newStoreObject = calendarObject
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreObject.properties()
        )


    @classmethod
    def transform(cls, self, calendarObject):
        self.__class__ = cls
        self._initializeWithObject(calendarObject)



class ProtoCalendarObjectFile(CalDAVFile, FancyEqMixin):

    compareAttributes = '_newStoreParentCalendar'.split()

    def __init__(self, parentCalendar, *a, **kw):
        super(ProtoCalendarObjectFile, self).__init__(*a, **kw)
        self._newStoreParentCalendar = parentCalendar


    @inlineCallbacks
    def storeStream(self, stream):
        # FIXME: direct tests 
        component = vcomponent.VComponent.fromString(
            (yield allDataFromStream(stream))
        )
        self._newStoreParentCalendar.createCalendarObjectWithName(
            self.fp.basename(), component
        )
        CalendarObjectFile.transform(self, self._newStoreParentCalendar.calendarObjectWithName(self.fp.basename()))
        returnValue(CREATED)


    def createSimilarFile(self, name):
        return None


    def isCollection(self):
        return False

    def exists(self):
        # FIXME: tests
        return False


    def name(self):
        return self.fp.basename()

    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)



class _AddressBookChildHelper(object):
    """
    Methods for things which are like addressbooks.
    """

    def _initializeWithAddressBook(self, addressbook, home):
        """
        Initialize with a addressbook.

        @param addressbook: the wrapped addressbook.
        @type addressbook: L{txcarddav.iaddressbookstore.IAddressBook}

        @param home: the home through which the given addressbook was accessed.
        @type home: L{txcarddav.iaddressbookstore.IAddressBookHome}
        """
        self._newStoreAddressBook = addressbook
        self._newStoreParentHome = home
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreAddressBook.properties()
        )


    def index(self):
        """
        Retrieve the new-style index wrapper.
        """
        return self._newStoreAddressBook.retrieveOldIndex()


    def invitesDB(self):
        """
        Retrieve the new-style invites DB wrapper.
        """
        if not hasattr(self, "_invitesDB"):
            self._invitesDB = self._newStoreAddressBook.retrieveOldInvites()
        return self._invitesDB

    def exists(self):
        # FIXME: tests
        return True


    @classmethod
    def transform(cls, self, addressbook, home):
        """
        Transform C{self} into a L{AddressBookCollectionFile}.
        """
        self.__class__ = cls
        self._initializeWithAddressBook(addressbook, home)


    def createSimilarFile(self, path):
        """
        Create a L{AddressBookObjectFile} or L{ProtoAddressBookObjectFile} based on a
        path object.
        """
        if not isinstance(path, FilePath):
            path = FilePath(path)

        newStoreObject = self._newStoreAddressBook.addressbookObjectWithName(
            path.basename()
        )

        if newStoreObject is not None:
            similar = AddressBookObjectFile(newStoreObject, path,
                principalCollections=self._principalCollections)
        else:
            # FIXME: creation in http_PUT should talk to a specific resource
            # type; this is the domain of StoreAddressBookObjectResource.
            # similar = ProtoAddressBookObjectFile(self._newStoreAddressBook, path)
            similar = ProtoAddressBookObjectFile(self._newStoreAddressBook, path,
                principalCollections=self._principalCollections)

        # FIXME: tests should be failing without this line.
        # Specifically, http_PUT won't be committing its transaction properly.
        self.propagateTransaction(similar)
        return similar


    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)



class AddressBookCollectionFile(_AddressBookChildHelper, CalDAVFile):
    """
    Wrapper around a L{txcarddav.iaddressbook.IAddressBook}.
    """

    def __init__(self, addressbook, home, *args, **kw):
        """
        Create a AddressBookCollectionFile from a L{txcarddav.iaddressbook.IAddressBook}
        and the arguments required for L{CalDAVFile}.
        """
        super(AddressBookCollectionFile, self).__init__(*args, **kw)
        self._initializeWithAddressBook(addressbook, home)


    def isCollection(self):
        return True


    def isAddressBookCollection(self):
        """
        Yes, it is a calendar collection.
        """
        return True


    @requiresPermissions(fromParent=[davxml.Unbind()])
    @inlineCallbacks
    def http_DELETE(self, request):
        """
        Override http_DELETE to validate 'depth' header. 
        """
        depth = request.headers.getHeader("depth", "infinity")
        if depth != "infinity":
            msg = "illegal depth header for DELETE on collection: %s" % (
                depth,
            )
            log.err(msg)
            raise HTTPError(StatusResponse(BAD_REQUEST, msg))
        response = (yield self.storeRemove(request, request.uri))
        returnValue(response)


    @inlineCallbacks
    def storeRemove(self, request, where):
        """
        Delete this addressbook collection resource, first deleting each contained
        addressbook resource.

        This has to emulate the behavior in fileop.delete in that any errors
        need to be reported back in a multistatus response.

        @param request: The request used to locate child resources.  Note that
            this is the request which I{triggered} the C{DELETE}, but which may
            not actually be a C{DELETE} request itself.

        @type request: L{twext.web2.iweb.IRequest}

        @param where: the URI at which the resource is being deleted.
        @type where: C{str}

        @return: an HTTP response suitable for sending to a client (or
            including in a multi-status).

         @rtype: something adaptable to L{twext.web2.iweb.IResponse}
        """

        # Check virtual share first
        isVirtual = yield self.isVirtualShare(request)
        if isVirtual:
            log.debug("Removing shared calendar %s" % (self,))
            yield self.removeVirtualShare(request)
            returnValue(NO_CONTENT)

        log.debug("Deleting addressbook %s" % (self,))

        # 'deluri' is this resource's URI; I should be able to synthesize it
        # from 'self'.

        errors = ResponseQueue(where, "DELETE", NO_CONTENT)

        for childname in self.listChildren():

            childurl = joinURL(where, childname)

            # FIXME: use a more specific API; we should know what this child
            # resource is, and not have to look it up.  (Sharing information
            # needs to move into the back-end first, though.)
            child = (yield request.locateChildResource(self, childname))

            try:
                yield child.storeRemove(request, childurl)
            except:
                logDefaultException()
                errors.add(childurl, BAD_REQUEST)

        # Now do normal delete

        # Handle sharing
        wasShared = (yield self.isShared(request))
        if wasShared:
            yield self.downgradeFromShare(request)

        # Actually delete it.
        self._newStoreParentHome.removeAddressBookWithName(
            self._newStoreAddressBook.name()
        )
        self.__class__ = ProtoAddressBookCollectionFile
        del self._newStoreAddressBook

        # FIXME: handle exceptions, possibly like this:

        #        if isinstance(more_responses, MultiStatusResponse):
        #            # Merge errors
        #            errors.responses.update(more_responses.children)

        response = errors.response()

        returnValue(response)


    def http_COPY(self, request):
        """
        Copying of addressbook collections isn't allowed.
        """
        # FIXME: no direct tests
        return FORBIDDEN


    # FIXME: access control
    @inlineCallbacks
    def http_MOVE(self, request):
        """
        Moving a addressbook collection is allowed for the purposes of changing
        that addressbook's name.
        """
        # FIXME: created to fix CDT test, no unit tests yet
        sourceURI = request.uri
        destinationURI = urlsplit(request.headers.getHeader("destination"))[2]
        if parentForURL(sourceURI) != parentForURL(destinationURI):
            returnValue(FORBIDDEN)
        destination = yield request.locateResource(destinationURI)
        # FIXME: should really use something other than 'fp' attribute.
        basename = destination.fp.basename()
        addressbook = self._newStoreAddressBook
        addressbook.rename(basename)
        AddressBookCollectionFile.transform(destination, addressbook,
                                         self._newStoreParentHome)
        del self._newStoreAddressBook
        self.__class__ = ProtoAddressBookCollectionFile
        returnValue(NO_CONTENT)



class ProtoAddressBookCollectionFile(CalDAVFile):
    """
    A resource representing an addressbook collection which hasn't yet been created.
    """

    def __init__(self, home, *args, **kw):
        """
        A placeholder resource for an addressbook collection which does not yet
        exist, but will become a L{AddressBookCollectionFile}.

        @param home: The addressbook home which will be this resource's parent,
            when it exists.

        @type home: L{txcarddav.iaddressbookstore.IAddressBookHome}
        """
        self._newStoreParentHome = home
        super(ProtoAddressBookCollectionFile, self).__init__(*args, **kw)


    def isCollection(self):
        return True


    def createSimilarFile(self, path):
        # FIXME: this is necessary for 
        # twistedcaldav.test.test_mkcol.
        #     MKCOL.test_make_addressbook_no_parent - there should be a more
        # structured way to refuse creation with a non-existent parent.
        return NoParent(path)


    def provisionFile(self):
        """
        Create an addressbook collection.
        """
        # FIXME: this should be done in the backend; provisionDefaultAddressBooks
        # should go away.
        return self.createAddressBookCollection()


    def createAddressBookCollection(self):
        """
        Override C{createAddressBookCollection} to actually do the work.
        """
        d = succeed(CREATED)

        Name = self.fp.basename()
        self._newStoreParentHome.createAddressBookWithName(Name)
        newStoreAddressBook = self._newStoreParentHome.addressbookWithName(
            Name
        )
        AddressBookCollectionFile.transform(
            self, newStoreAddressBook, self._newStoreParentHome
        )
        return d


    def exists(self):
        # FIXME: tests
        return False


    def provision(self):
        """
        This resource should do nothing if it's provisioned.
        """
        # FIXME: should be deleted, or raise an exception


    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)


class GlobalAddressBookCollectionFile(_AddressBookChildHelper, GlobalAddressBookFile):
    """
    Wrapper around a L{txcarddav.iaddressbook.IAddressBook}.
    """

    def __init__(self, addressbook, home, *args, **kw):
        """
        Create a GlobalAddressBookCollectionFile from a L{txcarddav.iaddressbook.IAddressBook}
        and the arguments required for L{CalDAVFile}.
        """
        super(GlobalAddressBookCollectionFile, self).__init__(*args, **kw)
        self._initializeWithAddressBook(addressbook, home)


    def isCollection(self):
        return True

    def isAddressBookCollection(self):
        """
        Yes, it is a calendar collection.
        """
        return True

class ProtoGlobalAddressBookCollectionFile(GlobalAddressBookFile):
    """
    A resource representing an addressbook collection which hasn't yet been created.
    """

    def __init__(self, home, *args, **kw):
        """
        A placeholder resource for an addressbook collection which does not yet
        exist, but will become a L{GlobalAddressBookCollectionFile}.

        @param home: The addressbook home which will be this resource's parent,
            when it exists.

        @type home: L{txcarddav.iaddressbookstore.IAddressBookHome}
        """
        self._newStoreParentHome = home
        super(ProtoGlobalAddressBookCollectionFile, self).__init__(*args, **kw)


    def isCollection(self):
        return True


    def createSimilarFile(self, path):
        # FIXME: this is necessary for 
        # twistedcaldav.test.test_mkcol.
        #     MKCOL.test_make_addressbook_no_parent - there should be a more
        # structured way to refuse creation with a non-existent parent.
        return NoParent(path)


    def provisionFile(self):
        """
        Create an addressbook collection.
        """
        # FIXME: this should be done in the backend; provisionDefaultAddressBooks
        # should go away.
        return self.createAddressBookCollection()


    def createAddressBookCollection(self):
        """
        Override C{createAddressBookCollection} to actually do the work.
        """
        d = succeed(CREATED)

        Name = self.fp.basename()
        self._newStoreParentHome.createAddressBookWithName(Name)
        newStoreAddressBook = self._newStoreParentHome.addressbookWithName(
            Name
        )
        GlobalAddressBookCollectionFile.transform(
            self, newStoreAddressBook, self._newStoreParentHome
        )
        return d


    def exists(self):
        # FIXME: tests
        return False


    def provision(self):
        """
        This resource should do nothing if it's provisioned.
        """
        # FIXME: should be deleted, or raise an exception


    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)



class AddressBookObjectFile(CalDAVFile, FancyEqMixin):
    """
    A resource wrapping a addressbook object.
    """

    compareAttributes = '_newStoreObject'.split()

    def __init__(self, Object, *args, **kw):
        """
        Construct a L{AddressBookObjectFile} from an L{IAddressBookObject}.

        @param Object: The storage for the addressbook object.
        @type Object: L{txcarddav.iaddressbookstore.IAddressBookObject}
        """
        super(AddressBookObjectFile, self).__init__(*args, **kw)
        self._initializeWithObject(Object)


    def inNewTransaction(self, request):
        """
        Implicit auto-replies need to span multiple transactions.  Clean out the
        given request's resource-lookup mapping, transaction, and re-look-up my
        addressbook object in a new transaction.

        Return the new transaction so it can be committed.
        """
        # FIXME: private names from 'file' implementation; maybe there should be
        # a public way to do this?  or maybe we should just have a real queue.
        objectName = self._newStoreObject.name()
        Name = self._newStoreObject._addressbook.name()
        homeUID = self._newStoreObject._addressbook._addressbookHome.uid()
        store = self._newStoreObject._transaction.store()
        txn = store.newTransaction("new AB transaction for " + self._newStoreObject.name())
        newObject = (txn.HomeWithUID(homeUID)
                        .addressbookWithName(Name)
                        .addressbookObjectWithName(objectName))
        request._newStoreTransaction = txn
        request._resourcesByURL.clear()
        request._urlsByResource.clear()
        self._initializeWithObject(newObject)
        return txn


    def isCollection(self):
        return False

    def exists(self):
        # FIXME: Tests
        return True


    def name(self):
        return self._newStoreObject.name()

    def etag(self):
        # FIXME: far too slow to be used for real, but I needed something to
        # placate the etag computation in the case where the file doesn't exist
        # yet (an uncommited transaction creating this addressbook file)

        # FIXME: direct tests
        try:
            if self.hasDeadProperty(TwistedGETContentMD5):
                return ETag(str(self.readDeadProperty(TwistedGETContentMD5)))
            else:
                return ETag(
                    hashlib.new("md5", self.vCardText()).hexdigest(),
                    weak=False
                )
        except (NoSuchObjectResourceError, InternalDataStoreError):
            # FIXME: a workaround for the fact that DELETE still rudely vanishes
            # the addressbook object out from underneath the store, and doesn't
            # call storeRemove.
            return None


    def newStoreProperties(self):
        return self._newStoreObject.properties()


    def quotaSize(self, request):
        # FIXME: tests
        return succeed(len(self._newStoreObject.vCardText()))


    def vCardText(self, ignored=None):
        assert ignored is None, "This is a addressbook object, not a addressbook"
        return self._newStoreObject.vCardText()


    @requiresPermissions(fromParent=[davxml.Unbind()])
    def http_DELETE(self, request):
        """
        Override http_DELETE to validate 'depth' header. 
        """
        return self.storeRemove(request, request.uri)


    @inlineCallbacks
    def storeStream(self, stream):
        # FIXME: direct tests
        component = VCard.fromString(
            (yield allDataFromStream(stream))
        )
        self._newStoreObject.setComponent(component)
        returnValue(NO_CONTENT)


    @inlineCallbacks
    def storeRemove(self, request, where):
        """
        Remove this addressbook object.
        """
        # Do quota checks before we start deleting things
        myquota = (yield self.quota(request))
        if myquota is not None:
            old_size = (yield self.quotaSize(request))
        else:
            old_size = 0

        try:

            storeAddressBook = self._newStoreObject._addressbook

            # Do delete

            # FIXME: public attribute please
            storeAddressBook.removeAddressBookObjectWithName(self._newStoreObject.name())

            # FIXME: clean this up with a 'transform' method
            self._newStoreParentAddressBook = storeAddressBook
            del self._newStoreObject
            self.__class__ = ProtoAddressBookObjectFile

            # Adjust quota
            if myquota is not None:
                yield self.quotaSizeAdjust(request, -old_size)

        except MemcacheLockTimeoutError:
            raise HTTPError(StatusResponse(CONFLICT, "Resource: %s currently in use on the server." % (where,)))

        returnValue(NO_CONTENT)


    def _initializeWithObject(self, Object):
        self._newStoreObject = Object
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreObject.properties()
        )


    @classmethod
    def transform(cls, self, Object):
        self.__class__ = cls
        self._initializeWithObject(Object)



class ProtoAddressBookObjectFile(CalDAVFile, FancyEqMixin):

    compareAttributes = '_newStoreParentAddressBook'.split()

    def __init__(self, parentAddressBook, *a, **kw):
        super(ProtoAddressBookObjectFile, self).__init__(*a, **kw)
        self._newStoreParentAddressBook = parentAddressBook


    @inlineCallbacks
    def storeStream(self, stream):
        # FIXME: direct tests 
        component = VCard.fromString(
            (yield allDataFromStream(stream))
        )
        self._newStoreParentAddressBook.createAddressBookObjectWithName(
            self.fp.basename(), component
        )
        AddressBookObjectFile.transform(self, self._newStoreParentAddressBook.addressbookObjectWithName(self.fp.basename()))
        returnValue(CREATED)


    def createSimilarFile(self, name):
        return None


    def isCollection(self):
        return False


    def exists(self):
        # FIXME: tests
        return False


    def name(self):
        return self.fp.basename()

    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)


class _NotificationChildHelper(object):
    """
    Methods for things which are like notification objects.
    """

    def _initializeWithNotifications(self, notifications, home):
        """
        Initialize with a notification collection.

        @param notifications: the wrapped notification collection backend
            object.
        @type notifications: L{txdav.common.inotification.INotificationCollection}

        @param home: the home through which the given notification collection
            was accessed.
        @type home: L{txdav.icommonstore.ICommonHome}
        """
        self._newStoreNotifications = notifications
        self._newStoreParentHome = home
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreNotifications.properties()
        )


    def notificationsDB(self):
        """
        Retrieve the new-style index wrapper.
        """
        return self._newStoreNotifications.retrieveOldIndex()


    def exists(self):
        # FIXME: tests
        return True


    @classmethod
    def transform(cls, self, notifications, home):
        """
        Transform C{self} into a L{NotificationCollectionFile}.
        """
        self.__class__ = cls
        self._initializeWithNotifications(notifications, home)


    def createSimilarFile(self, path):
        """
        Create a L{NotificationObjectFile} or L{ProtoNotificationObjectFile} based on a
        path object.
        """
        if not isinstance(path, FilePath):
            path = FilePath(path)

        newStoreObject = self._newStoreNotifications.notificationObjectWithName(
            path.basename()
        )

        if newStoreObject is not None:
            similar = StoreNotificationObjectFile(newStoreObject, path, self)
        else:
            # FIXME: creation in http_PUT should talk to a specific resource
            # type; this is the domain of StoreCalendarObjectResource.
            # similar = ProtoCalendarObjectFile(self._newStoreCalendar, path)
            similar = ProtoStoreNotificationObjectFile(self._newStoreNotifications, path, self)

        # FIXME: tests should be failing without this line.
        # Specifically, http_PUT won't be committing its transaction properly.
        self.propagateTransaction(similar)
        return similar


    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)



class StoreNotificationCollectionFile(_NotificationChildHelper,
                                      NotificationCollectionFile):
    """
    Wrapper around a L{txcaldav.icalendar.ICalendar}.
    """

    def __init__(self, notifications, home, *args, **kw):
        """
        Create a CalendarCollectionFile from a L{txcaldav.icalendar.ICalendar}
        and the arguments required for L{CalDAVFile}.
        """
        super(StoreNotificationCollectionFile, self).__init__(*args, **kw)
        self._initializeWithNotifications(notifications, home)


    def isCollection(self):
        return True


    @inlineCallbacks
    def http_DELETE(self, request):
        """
        Override http_DELETE to reject. 
        """
        raise HTTPError(StatusResponse(FORBIDDEN, "Cannot delete notification collections"))


    def http_COPY(self, request):
        """
        Copying of calendar collections isn't allowed.
        """
        raise HTTPError(StatusResponse(FORBIDDEN, "Cannot copy notification collections"))


    @inlineCallbacks
    def http_MOVE(self, request):
        """
        Moving a calendar collection is allowed for the purposes of changing
        that calendar's name.
        """
        raise HTTPError(StatusResponse(FORBIDDEN, "Cannot move notification collections"))



class StoreNotificationObjectFile(NotificationFile):
    """
    A resource wrapping a calendar object.
    """

    def __init__(self, notificationObject, *args, **kw):
        """
        Construct a L{CalendarObjectFile} from an L{ICalendarObject}.

        @param calendarObject: The storage for the calendar object.
        @type calendarObject: L{txcaldav.icalendarstore.ICalendarObject}
        """
        super(StoreNotificationObjectFile, self).__init__(*args, **kw)
        self._initializeWithObject(notificationObject)


    def isCollection(self):
        return False


    def exists(self):
        # FIXME: Tests
        return True


    def etag(self):
        # FIXME: far too slow to be used for real, but I needed something to
        # placate the etag computation in the case where the file doesn't exist
        # yet (an uncommited transaction creating this calendar file)

        # FIXME: direct tests
        try:
            if self.hasDeadProperty(TwistedGETContentMD5):
                return ETag(str(self.readDeadProperty(TwistedGETContentMD5)))
            else:
                return ETag(
                    hashlib.new("md5", self.text()).hexdigest(),
                    weak=False
                )
        except NoSuchObjectResourceError:
            # FIXME: a workaround for the fact that DELETE still rudely vanishes
            # the calendar object out from underneath the store, and doesn't
            # call storeRemove.
            return None


    def newStoreProperties(self):
        return self._newStoreObject.properties()


    def quotaSize(self, request):
        # FIXME: tests
        return succeed(len(self._newStoreObject.xmldata()))


    def text(self, ignored=None):
        assert ignored is None, "This is a notification object, not a notification"
        return self._newStoreObject.xmldata()


    @requiresPermissions(fromParent=[davxml.Unbind()])
    def http_DELETE(self, request):
        """
        Override http_DELETE to validate 'depth' header. 
        """
        return self.storeRemove(request, request.uri)


    @inlineCallbacks
    def storeRemove(self, request, where):
        """
        Remove this notification object.
        """
        # Do quota checks before we start deleting things
        myquota = (yield self.quota(request))
        if myquota is not None:
            old_size = (yield self.quotaSize(request))
        else:
            old_size = 0

        try:

            storeNotifications = self._newStoreObject._notificationCollection

            # Do delete

            # FIXME: public attribute please
            storeNotifications.removeNotificationObjectWithName(self._newStoreObject.name())

            # FIXME: clean this up with a 'transform' method
            self._newStoreParentNotifications = storeNotifications
            del self._newStoreObject
            self.__class__ = ProtoStoreNotificationObjectFile

            # Adjust quota
            if myquota is not None:
                yield self.quotaSizeAdjust(request, -old_size)

        except MemcacheLockTimeoutError:
            raise HTTPError(StatusResponse(CONFLICT, "Resource: %s currently in use on the server." % (where,)))

        returnValue(NO_CONTENT)


    def _initializeWithObject(self, notificationObject):
        self._newStoreObject = notificationObject
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreObject.properties()
        )


    @classmethod
    def transform(cls, self, notificationObject):
        self.__class__ = cls
        self._initializeWithObject(notificationObject)



class ProtoStoreNotificationObjectFile(NotificationFile):

    def __init__(self, parentNotifications, *a, **kw):
        super(ProtoStoreNotificationObjectFile, self).__init__(*a, **kw)
        self._newStoreParentNotifications = parentNotifications


    def isCollection(self):
        return False


    def exists(self):
        # FIXME: tests
        return False


    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)



