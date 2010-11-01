# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
SQL backend for CalDAV storage.
"""

__all__ = [
    "CalendarHome",
    "Calendar",
    "CalendarObject",
]

from twext.python.vcomponent import VComponent
from twext.web2.dav.element.rfc2518 import ResourceType
from twext.web2.http_headers import MimeType, generateContentType

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.error import ConnectionLost
from twisted.internet.interfaces import ITransport
from twisted.python import hashlib
from twisted.python.failure import Failure

from twistedcaldav import caldavxml, customxml
from twistedcaldav.caldavxml import ScheduleCalendarTransp, Opaque
from twistedcaldav.dateops import normalizeForIndex, datetimeMktime
from txdav.common.icommondatastore import IndexedSearchException
from twistedcaldav.instance import InvalidOverriddenInstanceError

from txdav.caldav.datastore.util import validateCalendarComponent,\
    dropboxIDFromCalendarObject
from txdav.caldav.icalendarstore import ICalendarHome, ICalendar, ICalendarObject,\
    IAttachment

from txdav.common.datastore.sql import CommonHome, CommonHomeChild,\
    CommonObjectResource
from txdav.common.datastore.sql_legacy import \
    PostgresLegacyIndexEmulator, SQLLegacyCalendarInvites,\
    SQLLegacyCalendarShares, PostgresLegacyInboxIndexEmulator
from txdav.common.datastore.sql_tables import CALENDAR_TABLE,\
    CALENDAR_BIND_TABLE, CALENDAR_OBJECT_REVISIONS_TABLE, CALENDAR_OBJECT_TABLE,\
    _ATTACHMENTS_MODE_WRITE, CALENDAR_HOME_TABLE
from txdav.base.propertystore.base import PropertyName

from vobject.icalendar import utc

import datetime

from zope.interface.declarations import implements

class CalendarHome(CommonHome):

    implements(ICalendarHome)

    def __init__(self, transaction, ownerUID, notifier):

        self._homeTable = CALENDAR_HOME_TABLE
        self._childClass = Calendar
        self._childTable = CALENDAR_TABLE
        self._bindTable = CALENDAR_BIND_TABLE
        self._revisionsTable = CALENDAR_OBJECT_REVISIONS_TABLE

        super(CalendarHome, self).__init__(transaction, ownerUID, notifier)
        self._shares = SQLLegacyCalendarShares(self)

    createCalendarWithName = CommonHome.createChildWithName
    removeCalendarWithName = CommonHome.removeChildWithName
    calendarWithName = CommonHome.childWithName
    calendars = CommonHome.children
    listCalendars = CommonHome.listChildren


    @inlineCallbacks
    def calendarObjectWithDropboxID(self, dropboxID):
        """
        Implement lookup with brute-force scanning.
        """
        for calendar in (yield self.calendars()):
            for calendarObject in (yield calendar.calendarObjects()):
                dbid = yield calendarObject.dropboxID()
                if dropboxID == dbid:
                    returnValue(calendarObject)


    @inlineCallbacks
    def createdHome(self):
        yield self.createCalendarWithName("calendar")
        defaultCal = yield self.calendarWithName("calendar")
        props = defaultCal.properties()
        props[PropertyName(*ScheduleCalendarTransp.qname())] = ScheduleCalendarTransp(
            Opaque())
        yield self.createCalendarWithName("inbox")



class Calendar(CommonHomeChild):
    """
    File-based implementation of L{ICalendar}.
    """
    implements(ICalendar)

    def __init__(self, home, name, resourceID, notifier):
        """
        Initialize a calendar pointing at a record in a database.

        @param name: the name of the calendar resource.
        @type name: C{str}

        @param home: the home containing this calendar.
        @type home: L{CalendarHome}
        """
        super(Calendar, self).__init__(home, name, resourceID, notifier)

        if name == 'inbox':
            self._index = PostgresLegacyInboxIndexEmulator(self)
        else:
            self._index = PostgresLegacyIndexEmulator(self)
        self._invites = SQLLegacyCalendarInvites(self)
        self._objectResourceClass = CalendarObject
        self._bindTable = CALENDAR_BIND_TABLE
        self._homeChildTable = CALENDAR_TABLE
        self._revisionsTable = CALENDAR_OBJECT_REVISIONS_TABLE
        self._objectTable = CALENDAR_OBJECT_TABLE


    @property
    def _calendarHome(self):
        return self._home


    def resourceType(self):
        return ResourceType.calendar #@UndefinedVariable


    ownerCalendarHome = CommonHomeChild.ownerHome
    calendarObjects = CommonHomeChild.objectResources
    listCalendarObjects = CommonHomeChild.listObjectResources
    calendarObjectWithName = CommonHomeChild.objectResourceWithName
    calendarObjectWithUID = CommonHomeChild.objectResourceWithUID
    createCalendarObjectWithName = CommonHomeChild.createObjectResourceWithName
    removeCalendarObjectWithName = CommonHomeChild.removeObjectResourceWithName
    removeCalendarObjectWithUID = CommonHomeChild.removeObjectResourceWithUID
    calendarObjectsSinceToken = CommonHomeChild.objectResourcesSinceToken


    def calendarObjectsInTimeRange(self, start, end, timeZone):
        raise NotImplementedError()


    def initPropertyStore(self, props):
        # Setup peruser special properties
        props.setSpecialProperties(
            (
                PropertyName.fromElement(caldavxml.CalendarDescription),
                PropertyName.fromElement(caldavxml.CalendarTimeZone),
            ),
            (
                PropertyName.fromElement(customxml.GETCTag),
                PropertyName.fromElement(caldavxml.SupportedCalendarComponentSet),
            ),
        )

    def contentType(self):
        """
        The content type of Calendar objects is text/calendar.
        """
        return MimeType.fromString("text/calendar; charset=utf-8")

#
# Duration into the future through which recurrences are expanded in the index
# by default.  This is a caching parameter which affects the size of the index;
# it does not affect search results beyond this period, but it may affect
# performance of such a search.
#
default_future_expansion_duration = datetime.timedelta(days=365 * 1)

#
# Maximum duration into the future through which recurrences are expanded in the
# index.  This is a caching parameter which affects the size of the index; it
# does not affect search results beyond this period, but it may affect
# performance of such a search.
#
# When a search is performed on a time span that goes beyond that which is
# expanded in the index, we have to open each resource which may have data in
# that time period.  In order to avoid doing that multiple times, we want to
# cache those results.  However, we don't necessarily want to cache all
# occurrences into some obscenely far-in-the-future date, so we cap the caching
# period.  Searches beyond this period will always be relatively expensive for
# resources with occurrences beyond this period.
#
maximum_future_expansion_duration = datetime.timedelta(days=365 * 5)

icalfbtype_to_indexfbtype = {
    "UNKNOWN"         : 0,
    "FREE"            : 1,
    "BUSY"            : 2,
    "BUSY-UNAVAILABLE": 3,
    "BUSY-TENTATIVE"  : 4,
}

indexfbtype_to_icalfbtype = {
    0: '?',
    1: 'F',
    2: 'B',
    3: 'U',
    4: 'T',
}

def _pathToName(path):
    return path.rsplit(".", 1)[0]



class CalendarObject(CommonObjectResource):
    implements(ICalendarObject)

    def __init__(self, calendar, name, uid):

        super(CalendarObject, self).__init__(calendar, name, uid)
        self._objectTable = CALENDAR_OBJECT_TABLE


    @property
    def _calendar(self):
        return self._parentCollection


    def calendar(self):
        return self._calendar


    @inlineCallbacks
    def setComponent(self, component, inserting=False):

        old_size = 0 if inserting else self.size()

        validateCalendarComponent(self, self._calendar, component, inserting)

        yield self.updateDatabase(component, inserting=inserting)
        if inserting:
            yield self._calendar._insertRevision(self._name)
        else:
            yield self._calendar._updateRevision(self._name)

        # Adjust quota
        yield self._calendar._home.adjustQuotaUsedBytes(self.size() - old_size)

        self._calendar.notifyChanged()


    @inlineCallbacks
    def updateDatabase(self, component, expand_until=None, reCreate=False, inserting=False):
        """
        Update the database tables for the new data being written.

        @param component: calendar data to store
        @type component: L{Component}
        """

        # Decide how far to expand based on the component
        master = component.masterComponent()
        if master is None or not component.isRecurring() and not component.isRecurringUnbounded():
            # When there is no master we have a set of overridden components - index them all.
            # When there is one instance - index it.
            # When bounded - index all.
            expand = datetime.datetime(2100, 1, 1, 0, 0, 0, tzinfo=utc)
        else:
            if expand_until:
                expand = expand_until
            else:
                expand = datetime.date.today() + default_future_expansion_duration

            if expand > (datetime.date.today() + maximum_future_expansion_duration):
                raise IndexedSearchException

        try:
            instances = component.expandTimeRanges(expand, ignoreInvalidInstances=reCreate)
        except InvalidOverriddenInstanceError, e:
            self.log_error("Invalid instance %s when indexing %s in %s" % (e.rid, self._name, self._calendar,))
            
            if self._txn._migrating:
                # TODO: fix the data here by re-writing component then re-index
                instances = component.expandTimeRanges(expand, ignoreInvalidInstances=True)
            else:
                raise

        componentText = str(component)
        self._objectText = componentText
        organizer = component.getOrganizer()
        if not organizer:
            organizer = ""

        # CALENDAR_OBJECT table update
        self._md5 = hashlib.md5(componentText).hexdigest()
        self._size = len(componentText)
        if inserting:
            self._resourceID, self._created, self._modified  = (
                yield self._txn.execSQL(
                """
                insert into CALENDAR_OBJECT
                (CALENDAR_RESOURCE_ID, RESOURCE_NAME, ICALENDAR_TEXT, ICALENDAR_UID, ICALENDAR_TYPE, ATTACHMENTS_MODE, ORGANIZER, RECURRANCE_MAX, MD5)
                 values
                (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning
                 RESOURCE_ID,
                 CREATED,
                 MODIFIED
                """,
                # FIXME: correct ATTACHMENTS_MODE based on X-APPLE-
                # DROPBOX
                [
                    self._calendar._resourceID,
                    self._name,
                    componentText,
                    component.resourceUID(),
                    component.resourceType(),
                    _ATTACHMENTS_MODE_WRITE,
                    organizer,
                    normalizeForIndex(instances.limit) if instances.limit else None,
                    self._md5,
                ]
            ))[0]
        else:
            yield self._txn.execSQL(
                """
                update CALENDAR_OBJECT set
                (ICALENDAR_TEXT, ICALENDAR_UID, ICALENDAR_TYPE, ATTACHMENTS_MODE, ORGANIZER, RECURRANCE_MAX, MD5, MODIFIED)
                 =
                (%s, %s, %s, %s, %s, %s, %s, timezone('UTC', CURRENT_TIMESTAMP))
                where RESOURCE_ID = %s
                returning MODIFIED
                """,
                # should really be filling out more fields: ORGANIZER,
                # ORGANIZER_OBJECT, a correct ATTACHMENTS_MODE based on X-APPLE-
                # DROPBOX
                [
                    componentText,
                    component.resourceUID(),
                    component.resourceType(),
                    _ATTACHMENTS_MODE_WRITE,
                    organizer,
                    normalizeForIndex(instances.limit) if instances.limit else None,
                    self._md5,
                    self._resourceID,
                ]
            )

            # Need to wipe the existing time-range for this and rebuild
            yield self._txn.execSQL(
                """
                delete from TIME_RANGE where CALENDAR_OBJECT_RESOURCE_ID = %s
                """,
                [
                    self._resourceID,
                ],
            )
        self._uid = component.resourceUID()


        # CALENDAR_OBJECT table update
        for key in instances:
            instance = instances[key]
            start = instance.start.replace(tzinfo=utc)
            end = instance.end.replace(tzinfo=utc)
            float = instance.start.tzinfo is None
            transp = instance.component.propertyValue("TRANSP") == "TRANSPARENT"
            instanceid = (yield self._txn.execSQL(
                """
                insert into TIME_RANGE
                (CALENDAR_RESOURCE_ID, CALENDAR_OBJECT_RESOURCE_ID, FLOATING, START_DATE, END_DATE, FBTYPE, TRANSPARENT)
                 values
                (%s, %s, %s, %s, %s, %s, %s)
                 returning
                INSTANCE_ID
                """,
                [
                    self._calendar._resourceID,
                    self._resourceID,
                    float,
                    start,
                    end,
                    icalfbtype_to_indexfbtype.get(instance.component.getFBType(), icalfbtype_to_indexfbtype["FREE"]),
                    transp,
                ],
            ))[0][0]
            peruserdata = component.perUserTransparency(instance.rid)
            for useruid, transp in peruserdata:
                yield self._txn.execSQL(
                    """
                    insert into TRANSPARENCY
                    (TIME_RANGE_INSTANCE_ID, USER_ID, TRANSPARENT)
                     values
                    (%s, %s, %s)
                    """,
                    [
                        instanceid,
                        useruid,
                        transp,
                    ],
                )

        # Special - for unbounded recurrence we insert a value for "infinity"
        # that will allow an open-ended time-range to always match it.
        if component.isRecurringUnbounded():
            start = datetime.datetime(2100, 1, 1, 0, 0, 0, tzinfo=utc)
            end = datetime.datetime(2100, 1, 1, 1, 0, 0, tzinfo=utc)
            float = False
            instanceid = (yield self._txn.execSQL(
                """
                insert into TIME_RANGE
                (CALENDAR_RESOURCE_ID, CALENDAR_OBJECT_RESOURCE_ID, FLOATING, START_DATE, END_DATE, FBTYPE, TRANSPARENT)
                 values
                (%s, %s, %s, %s, %s, %s, %s)
                 returning
                INSTANCE_ID
                """,
                [
                    self._calendar._resourceID,
                    self._resourceID,
                    float,
                    start,
                    end,
                    icalfbtype_to_indexfbtype["UNKNOWN"],
                    True,
                ],
            ))[0][0]
            peruserdata = component.perUserTransparency(None)
            for useruid, transp in peruserdata:
                yield self._txn.execSQL(
                    """
                    insert into TRANSPARENCY
                    (TIME_RANGE_INSTANCE_ID, USER_ID, TRANSPARENT)
                     values
                    (%s, %s, %s)
                    """,
                    [
                        instanceid,
                        useruid,
                        transp,
                    ],
                )


    @inlineCallbacks
    def component(self):
        returnValue(VComponent.fromString((yield self.iCalendarText())))


    iCalendarText = CommonObjectResource.text


    @inlineCallbacks
    def organizer(self):
        returnValue((yield self.component()).getOrganizer())


    @inlineCallbacks
    def createAttachmentWithName(self, name, contentType):

        try:
            self._attachmentPathRoot().makedirs()
        except:
            pass

        attachment = Attachment(self, name)
        yield self._txn.execSQL(
            """
            insert into ATTACHMENT (CALENDAR_OBJECT_RESOURCE_ID, CONTENT_TYPE,
            SIZE, MD5, PATH) values (%s, %s, %s, %s, %s)
            """,
            [
                self._resourceID, generateContentType(contentType), 0, "",
                name,
            ]
        )
        returnValue(attachment.store(contentType))


    @inlineCallbacks
    def removeAttachmentWithName(self, name):
        attachment = (yield self.attachmentWithName(name))
        old_size = attachment.size()
        self._txn.postCommit(attachment._path.remove)
        yield self._txn.execSQL(
            """
            delete from ATTACHMENT where CALENDAR_OBJECT_RESOURCE_ID = %s AND
            PATH = %s
            """, [self._resourceID, name]
        )

        # Adjust quota
        yield self._calendar._home.adjustQuotaUsedBytes(-old_size)


    @inlineCallbacks
    def attachmentWithName(self, name):
        attachment = Attachment(self, name)
        attachment = (yield attachment.initFromStore())
        returnValue(attachment)

    @inlineCallbacks
    def attendeesCanManageAttachments(self):
        returnValue((yield self.component()).hasPropertyInAnyComponent(
            "X-APPLE-DROPBOX"
        ))


    dropboxID = dropboxIDFromCalendarObject


    def _attachmentPathRoot(self):
        attachmentRoot = self._txn._store.attachmentsPath
        
        # Use directory hashing scheme based on owner user id
        homeName = self._calendar.ownerHome().name()
        return attachmentRoot.child(homeName[0:2]).child(homeName[2:4]).child(homeName).child(self.uid())


    @inlineCallbacks
    def attachments(self):
        rows = yield self._txn.execSQL(
            """
            select PATH from ATTACHMENT where CALENDAR_OBJECT_RESOURCE_ID = %s
            """, [self._resourceID])
        result = []
        for row in rows:
            result.append((yield self.attachmentWithName(row[0])))
        returnValue(result)


    def initPropertyStore(self, props):
        # Setup peruser special properties
        props.setSpecialProperties(
            (
            ),
            (
                PropertyName.fromElement(customxml.TwistedCalendarAccessProperty),
                PropertyName.fromElement(customxml.TwistedSchedulingObjectResource),
                PropertyName.fromElement(caldavxml.ScheduleTag),
                PropertyName.fromElement(customxml.TwistedScheduleMatchETags),
                PropertyName.fromElement(customxml.TwistedCalendarHasPrivateCommentsProperty),
                PropertyName.fromElement(caldavxml.Originator),
                PropertyName.fromElement(caldavxml.Recipient),
                PropertyName.fromElement(customxml.ScheduleChanges),
            ),
        )

    # IDataStoreResource
    def contentType(self):
        """
        The content type of Calendar objects is text/calendar.
        """
        return MimeType.fromString("text/calendar; charset=utf-8")

class AttachmentStorageTransport(object):

    implements(ITransport)

    def __init__(self, attachment, contentType):
        self.attachment = attachment
        self.contentType = contentType
        self.buf = ''
        self.hash = hashlib.md5()


    @property
    def _txn(self):
        return self.attachment._txn


    def write(self, data):
        self.buf += data
        self.hash.update(data)


    @inlineCallbacks
    def loseConnection(self):

        old_size = self.attachment.size()

        self.attachment._path.setContent(self.buf)
        self.attachment._contentType = self.contentType
        self.attachment._md5 = self.hash.hexdigest()
        self.attachment._size = len(self.buf)
        self.attachment._created, self.attachment._modified = map(
            sqltime,
            (yield self._txn.execSQL(
                """
                update ATTACHMENT set CONTENT_TYPE = %s, SIZE = %s, MD5 = %s,
                 MODIFIED = timezone('UTC', CURRENT_TIMESTAMP)
                where PATH = %s
                returning CREATED, MODIFIED
                """,
                [
                    generateContentType(self.contentType),
                    self.attachment._size,
                    self.attachment._md5,
                    self.attachment.name()
                ]
            ))[0]
        )

        # Adjust quota
        yield self.attachment._calendarObject._calendar._home.adjustQuotaUsedBytes(self.attachment.size() - old_size)


def sqltime(value):
    return datetimeMktime(datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f"))

class Attachment(object):

    implements(IAttachment)

    def __init__(self, calendarObject, name):
        self._calendarObject = calendarObject
        self._name = name
        self._size = 0


    @property
    def _txn(self):
        return self._calendarObject._txn


    @inlineCallbacks
    def initFromStore(self):
        """
        Execute necessary SQL queries to retrieve attributes.

        @return: C{True} if this attachment exists, C{False} otherwise.
        """
        rows = yield self._txn.execSQL(
            """
            select CONTENT_TYPE, SIZE, MD5, CREATED, MODIFIED from ATTACHMENT where PATH = %s
            """,
            [self._name]
        )
        if not rows:
            returnValue(None)
        self._contentType = MimeType.fromString(rows[0][0])
        self._size = rows[0][1]
        self._md5 = rows[0][2]
        self._created = sqltime(rows[0][3])
        self._modified = sqltime(rows[0][4])
        returnValue(self)


    def name(self):
        return self._name

    @property
    def _path(self):
        attachmentPath = self._calendarObject._attachmentPathRoot()
        return attachmentPath.child(self.name())

    def properties(self):
        pass # stub


    def store(self, contentType):
        return AttachmentStorageTransport(self, contentType)


    def retrieve(self, protocol):
        protocol.dataReceived(self._path.getContent())
        protocol.connectionLost(Failure(ConnectionLost()))


    # IDataStoreResource
    def contentType(self):
        return self._contentType


    def md5(self):
        return self._md5


    def size(self):
        return self._size


    def created(self):
        return self._created

    def modified(self):
        return self._modified


