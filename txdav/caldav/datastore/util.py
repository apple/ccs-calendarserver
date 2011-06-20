# -*- test-case-name: txdav.caldav.datastore.test.test_util -*-
##
# Copyright (c) 2010-2011 Apple Inc. All rights reserved.
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
Utility logic common to multiple backend implementations.
"""

from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
from twisted.internet.protocol import Protocol

from twext.python.vcomponent import InvalidICalendarDataError
from twext.python.vcomponent import VComponent

from txdav.common.icommondatastore import InvalidObjectResourceError, \
    NoSuchObjectResourceError, InternalDataStoreError

from twistedcaldav.datafilters.privateevents import PrivateEventFilter
from twistedcaldav.datafilters.peruserdata import PerUserDataFilter
from zope.interface.declarations import implements
from txdav.caldav.icalendarstore import IAttachmentStorageTransport
from twext.python.log import Logger
log = Logger()

def validateCalendarComponent(calendarObject, calendar, component, inserting):
    """
    Validate a calendar component for a particular calendar.

    @param calendarObject: The calendar object whose component will be
        replaced.
    @type calendarObject: L{ICalendarObject}

    @param calendar: The calendar which the L{ICalendarObject} is present in.
    @type calendar: L{ICalendar}

    @param component: The VComponent to be validated.
    @type component: L{VComponent}
    """

    if not isinstance(component, VComponent):
        raise TypeError(type(component))

    try:
        if not inserting and component.resourceUID() != calendarObject.uid():
            raise InvalidObjectResourceError(
                "UID may not change (%s != %s)" % (
                    component.resourceUID(), calendarObject.uid()
                 )
            )
    except NoSuchObjectResourceError:
        pass

    try:
        # FIXME: This is a bad way to do this test, there should be a
        # Calendar-level API for it.
        if calendar.name() == 'inbox':
            component.validateComponentsForCalDAV(True)
        else:
            component.validateForCalDAV()
    except InvalidICalendarDataError, e:
        raise InvalidObjectResourceError(e)


@inlineCallbacks
def dropboxIDFromCalendarObject(calendarObject):
    """
    Helper to implement L{ICalendarObject.dropboxID}.

    @param calendarObject: The calendar object to retrieve a dropbox ID for.
    @type calendarObject: L{ICalendarObject}
    """

    # Try "X-APPLE-DROPBOX" first
    dropboxProperty = (yield calendarObject.component(
        )).getFirstPropertyInAnyComponent("X-APPLE-DROPBOX")
    if dropboxProperty is not None:
        componentDropboxID = dropboxProperty.value().rstrip("/").split("/")[-1]
        returnValue(componentDropboxID)

    # Now look at each ATTACH property and see if it might be a dropbox item
    # and if so extract the id from that

    attachments = (yield calendarObject.component()).getAllPropertiesInAnyComponent(
        "ATTACH",
        depth=1,
    )
    for attachment in attachments:

        # Make sure the value type is URI and http(s) and it is in a dropbox
        valueType = attachment.parameterValue("VALUE", "URI")
        if valueType == "URI" and attachment.value().startswith("http"):
            segments = attachment.value().split("/")
            try:
                if segments[-3] == "dropbox":
                    returnValue(segments[-2])
            except IndexError:
                pass

    returnValue(calendarObject.uid() + ".dropbox")


@inlineCallbacks
def _migrateCalendar(inCalendar, outCalendar, getComponent):
    """
    Copy all calendar objects and properties in the given input calendar to the
    given output calendar.

    @param inCalendar: the L{ICalendar} to retrieve calendar objects from.
    @param outCalendar: the L{ICalendar} to store calendar objects to.
    @param getComponent: a 1-argument callable; see L{migrateHome}.

    @return: a L{Deferred} which fires when the calendar has migrated.
    """
    outCalendar.properties().update(inCalendar.properties())
    for calendarObject in (yield inCalendar.calendarObjects()):
        
        try:
            # Must account for metadata
            component = (yield calendarObject.component()) # XXX WRONG SHOULD CALL getComponent
            component.md5 = calendarObject.md5()
            yield outCalendar.createCalendarObjectWithName(
                calendarObject.name(),
                component,
                metadata=calendarObject.getMetadata(),
            )

            # Only the owner's properties are migrated, since previous releases of
            # calendar server didn't have per-user properties.
            outObject = yield outCalendar.calendarObjectWithName(
                calendarObject.name())
            if outCalendar.objectResourcesHaveProperties():
                outObject.properties().update(calendarObject.properties())
    
            if inCalendar.name() == "inbox":
                # Because of 9023803, skip attachment processing within inboxes
                continue

            # Migrate attachments.
            for attachment in (yield calendarObject.attachments()):
                name = attachment.name()
                ctype = attachment.contentType()
                newattachment = yield outObject.createAttachmentWithName(name)
                transport = newattachment.store(ctype)
                proto =_AttachmentMigrationProto(transport)
                attachment.retrieve(proto)
                yield proto.done

        except InternalDataStoreError:
            log.error("  Failed to migrate calendar object: %s/%s/%s" % (
                inCalendar.ownerHome().name(),
                inCalendar.name(),
                calendarObject.name(),
            ))



class _AttachmentMigrationProto(Protocol, object):
    def __init__(self, storeTransport):
        self.storeTransport = storeTransport
        self.done = Deferred()

    def dataReceived(self, data):
        self.storeTransport.write(data)

    def connectionLost(self, reason):
        try:
            self.storeTransport.loseConnection()
        except:
            self.done.errback()
        else:
            self.done.callback(None)



@inlineCallbacks
def migrateHome(inHome, outHome, getComponent=lambda x: x.component()):
    """
    Copy all calendars and properties in the given input calendar to the given
    output calendar.

    @param inHome: the L{ICalendarHome} to retrieve calendars and properties
        from.

    @param outHome: the L{ICalendarHome} to store calendars and properties
        into.

    @param getComponent: a 1-argument callable that takes an L{ICalendarObject}
        (from a calendar in C{inHome}) and returns a L{VComponent} (to store in
        a calendar in outHome).
    """
    yield outHome.removeCalendarWithName("calendar")
    yield outHome.removeCalendarWithName("inbox")
    outHome.properties().update(inHome.properties())
    inCalendars = yield inHome.calendars()
    for calendar in inCalendars:
        name = calendar.name()
        if name == "outbox":
            continue
        yield outHome.createCalendarWithName(name)
        outCalendar = yield outHome.calendarWithName(name)
        try:
            yield _migrateCalendar(calendar, outCalendar, getComponent)
        except InternalDataStoreError:
            log.error("  Failed to migrate calendar: %s/%s" % (inHome.name(), name,))

    # No migration for notifications, since they weren't present in earlier
    # released versions of CalendarServer.


class CalendarObjectBase(object):
    """
    Base logic shared between file- and sql-based L{ICalendarObject}
    implementations.
    """

    @inlineCallbacks
    def filteredComponent(self, accessUID, asAdmin=False):
        """
        Filter this calendar object's iCalendar component as it would be
        perceived by a particular user, accounting for per-user iCalendar data
        and private events, and return a L{Deferred} that fires with that
        object.

        Unlike the result of C{component()}, which contains storage-specific
        iCalendar properties, this is a valid iCalendar object which could be
        serialized and displayed to other iCalendar-processing software.

        @param accessUID: the UID of the principal who is accessing this
            component.
        @type accessUID: C{str} (UTF-8 encoded)

        @param asAdmin: should the given UID be treated as an administrator?  If
            this is C{True}, the resulting component will have an unobscured
            view of private events, even if the given UID is not actually the
            owner of said events.  (However, per-instance overridden values will
            still be seen as the given C{accessUID}.)

        @return: a L{Deferred} which fires with a
            L{twistedcaldav.ical.Component}.
        """
        component = yield self.component()
        calendar = self.calendar()
        isOwner = asAdmin or (calendar._owned and
                              calendar.ownerCalendarHome().uid() == accessUID)
        for filter in [PrivateEventFilter(self.accessMode, isOwner),
                       PerUserDataFilter(accessUID)]:
            component = filter.filter(component)
        returnValue(component)



class StorageTransportAddress(object):
    """
    Peer / host address for L{IAttachmentStorageTransport} implementations.

    @ivar attachment: the L{IAttachment} being stored.

    @type attachment: L{IAttachment} provider

    @ivar isHost: is this a host address or peer address?

    @type isHost: C{bool}
    """

    def __init__(self, attachment, isHost):
        """
        Initialize with the attachment being stored.
        """
        self.attachment = attachment
        self.isHost = isHost


    def __repr__(self):
        if self.isHost:
            host = " (host)"
        else:
            host = ""
        return '<Storing Attachment: %r%s>' % (self.attachment.name(), host)



class StorageTransportBase(object):
    """
    Base logic shared between file- and sql-based L{IAttachmentStorageTransport}
    implementations.
    """

    implements(IAttachmentStorageTransport)

    def __init__(self, attachment, contentType):
        """
        Create a storage transport with a reference to an L{IAttachment} and a
        L{twext.web2.http_headers.MimeType}.
        """
        self._attachment = attachment
        self._contentType = contentType


    def getPeer(self):
        return StorageTransportAddress(self._attachment, False)


    def getHost(self):
        return StorageTransportAddress(self._attachment, True)


    def writeSequence(self, seq):
        return self.write(''.join(seq))


