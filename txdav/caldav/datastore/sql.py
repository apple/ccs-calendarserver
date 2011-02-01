# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
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
from twistedcaldav.ical import Component
from twistedcaldav.instance import InvalidOverriddenInstanceError

from txdav.base.propertystore.base import PropertyName
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
    _ATTACHMENTS_MODE_NONE, _ATTACHMENTS_MODE_READ, _ATTACHMENTS_MODE_WRITE,\
    CALENDAR_HOME_TABLE, CALENDAR_HOME_METADATA_TABLE,\
    CALENDAR_AND_CALENDAR_BIND, CALENDAR_OBJECT_REVISIONS_AND_BIND_TABLE,\
    CALENDAR_OBJECT_AND_BIND_TABLE, schema
from txdav.common.icommondatastore import IndexedSearchException

from vobject.icalendar import utc

import datetime

from zope.interface.declarations import implements

class CalendarHome(CommonHome):

    implements(ICalendarHome)

    _homeTable = CALENDAR_HOME_TABLE
    _homeMetaDataTable = CALENDAR_HOME_METADATA_TABLE
    _childTable = CALENDAR_TABLE
    _bindTable = CALENDAR_BIND_TABLE
    _objectBindTable = CALENDAR_OBJECT_AND_BIND_TABLE
    _notifierPrefix = "CalDAV"
    _revisionsTable = CALENDAR_OBJECT_REVISIONS_TABLE

    def __init__(self, transaction, ownerUID, notifiers):

        self._childClass = Calendar
        super(CalendarHome, self).__init__(transaction, ownerUID, notifiers)
        self._shares = SQLLegacyCalendarShares(self)

    createCalendarWithName = CommonHome.createChildWithName
    removeCalendarWithName = CommonHome.removeChildWithName
    calendarWithName = CommonHome.childWithName
    calendars = CommonHome.children
    listCalendars = CommonHome.listChildren
    loadCalendars = CommonHome.loadChildren


    @inlineCallbacks
    def hasCalendarResourceUIDSomewhereElse(self, uid, ok_object, type):
        
        objectResources = (yield self.objectResourcesWithUID(uid, ("inbox",)))
        for objectResource in objectResources:
            if ok_object and objectResource._resourceID == ok_object._resourceID:
                continue
            matched_type = "schedule" if objectResource.isScheduleObject else "calendar"
            if type == "schedule" or matched_type == "schedule":
                returnValue(True)
            
        returnValue(False)

    @inlineCallbacks
    def getCalendarResourcesForUID(self, uid, allow_shared=False):
        
        results = []
        objectResources = (yield self.objectResourcesWithUID(uid, ("inbox",)))
        for objectResource in objectResources:
            if allow_shared or objectResource._parentCollection._owned:
                results.append(objectResource)
            
        returnValue(results)

    @inlineCallbacks
    def calendarObjectWithDropboxID(self, dropboxID):
        """
        Implement lookup via queries.
        """
        rows = (yield self._txn.execSQL("""
            select %(OBJECT:name)s.%(OBJECT:column_PARENT_RESOURCE_ID)s, %(OBJECT:column_RESOURCE_ID)s
            from %(OBJECT:name)s
            left outer join %(BIND:name)s on (
              %(OBJECT:name)s.%(OBJECT:column_PARENT_RESOURCE_ID)s = %(BIND:name)s.%(BIND:column_RESOURCE_ID)s
            )
            where
             %(OBJECT:column_DROPBOX_ID)s = %%s and
             %(BIND:name)s.%(BIND:column_HOME_RESOURCE_ID)s = %%s
            """ % CALENDAR_OBJECT_AND_BIND_TABLE,
            [dropboxID, self._resourceID,]
        ))

        if rows:
            calendarID, objectID = rows[0]
            calendar = (yield self.childWithID(calendarID))
            if calendar:
                calendarObject = (yield calendar.objectResourceWithID(objectID))
                returnValue(calendarObject)
        
        returnValue(None)

    @inlineCallbacks
    def getAllDropboxIDs(self):

        rows = (yield self._txn.execSQL("""
            select %(OBJECT:column_DROPBOX_ID)s
            from %(OBJECT:name)s
            left outer join %(BIND:name)s on (
              %(OBJECT:name)s.%(OBJECT:column_PARENT_RESOURCE_ID)s = %(BIND:name)s.%(BIND:column_RESOURCE_ID)s
            )
            where
             %(OBJECT:column_DROPBOX_ID)s is not null and
             %(BIND:name)s.%(BIND:column_HOME_RESOURCE_ID)s = %%s
            order by %(OBJECT:column_DROPBOX_ID)s
            """ % CALENDAR_OBJECT_AND_BIND_TABLE,
            [self._resourceID]
        ))
        
        returnValue([row[0] for row in rows])

    @inlineCallbacks
    def createdHome(self):
        defaultCal = yield self.createCalendarWithName("calendar")
        props = defaultCal.properties()
        props[PropertyName(*ScheduleCalendarTransp.qname())] = ScheduleCalendarTransp(
            Opaque())
        yield self.createCalendarWithName("inbox")

class Calendar(CommonHomeChild):
    """
    File-based implementation of L{ICalendar}.
    """
    implements(ICalendar)

    _bindSchema = schema.CALENDAR_BIND
    _bindTable = CALENDAR_BIND_TABLE
    _homeChildTable = CALENDAR_TABLE
    _homeChildBindTable = CALENDAR_AND_CALENDAR_BIND
    _revisionsTable = CALENDAR_OBJECT_REVISIONS_TABLE
    _revisionsBindTable = CALENDAR_OBJECT_REVISIONS_AND_BIND_TABLE
    _objectTable = CALENDAR_OBJECT_TABLE

    def __init__(self, home, name, resourceID, owned):
        """
        Initialize a calendar pointing at a record in a database.

        @param name: the name of the calendar resource.
        @type name: C{str}

        @param home: the home containing this calendar.
        @type home: L{CalendarHome}
        """
        super(Calendar, self).__init__(home, name, resourceID, owned)

        if name == 'inbox':
            self._index = PostgresLegacyInboxIndexEmulator(self)
        else:
            self._index = PostgresLegacyIndexEmulator(self)
        self._invites = SQLLegacyCalendarInvites(self)
        self._objectResourceClass = CalendarObject


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

accessMode_to_type = {
    ""                           : 0,
    Component.ACCESS_PUBLIC      : 1,
    Component.ACCESS_PRIVATE     : 2,
    Component.ACCESS_CONFIDENTIAL: 3,
    Component.ACCESS_RESTRICTED  : 4,
}
accesstype_to_accessMode = dict([(v, k) for k,v in accessMode_to_type.items()])

def _pathToName(path):
    return path.rsplit(".", 1)[0]



class CalendarObject(CommonObjectResource):
    implements(ICalendarObject)

    _objectTable = CALENDAR_OBJECT_TABLE

    def __init__(self, calendar, name, uid, resourceID=None, metadata=None):

        super(CalendarObject, self).__init__(calendar, name, uid, resourceID)
        
        if metadata is None:
            metadata = {}
        self.accessMode = metadata.get("accessMode", "")
        self.isScheduleObject = metadata.get("isScheduleObject", False)
        self.scheduleTag = metadata.get("scheduleTag", "")
        self.scheduleEtags = metadata.get("scheduleEtags", "")
        self.hasPrivateComment = metadata.get("hasPrivateComment", False)


    @classmethod
    def _selectAllColumns(cls):
        """
        Full set of columns in the object table that need to be loaded to
        initialize the object resource state.
        """
        return """
            select 
              %(column_RESOURCE_ID)s,
              %(column_RESOURCE_NAME)s,
              %(column_UID)s,
              %(column_MD5)s,
              character_length(%(column_TEXT)s),
              %(column_ATTACHMENTS_MODE)s,
              %(column_DROPBOX_ID)s,
              %(column_ACCESS)s,
              %(column_SCHEDULE_OBJECT)s,
              %(column_SCHEDULE_TAG)s,
              %(column_SCHEDULE_ETAGS)s,
              %(column_PRIVATE_COMMENTS)s,
              %(column_CREATED)s,
              %(column_MODIFIED)s
        """ % cls._objectTable

    def _initFromRow(self, row):
        """
        Given a select result using the columns from L{_selectAllColumns}, initialize
        the object resource state.
        """
        (self._resourceID,
         self._name,
         self._uid,
         self._md5,
         self._size,
         self._attachment,
         self._dropboxID,
         self._access,
         self._schedule_object,
         self._schedule_tag,
         self._schedule_etags,
         self._private_comments,
         self._created,
         self._modified,) = tuple(row)

    @property
    def _calendar(self):
        return self._parentCollection


    def calendar(self):
        return self._calendar


    @inlineCallbacks
    def setComponent(self, component, inserting=False):

        validateCalendarComponent(self, self._calendar, component, inserting)

        yield self.updateDatabase(component, inserting=inserting)
        if inserting:
            yield self._calendar._insertRevision(self._name)
        else:
            yield self._calendar._updateRevision(self._name)

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
        self._uid = component.resourceUID()
        self._md5 = hashlib.md5(componentText).hexdigest()
        self._size = len(componentText)

        # Determine attachment mode (ignore inbox's) - NB we have to do this
        # after setting up other properties as UID at least is needed
        self._attachment = _ATTACHMENTS_MODE_NONE
        self._dropboxID = None
        if self._parentCollection.name() != "inbox":
            if component.hasPropertyInAnyComponent("X-APPLE-DROPBOX"):
                self._attachment = _ATTACHMENTS_MODE_WRITE
                self._dropboxID = (yield self.dropboxID())
            elif component.hasPropertyInAnyComponent("ATTACH"):
                # FIXME: really we ought to check to see if the ATTACH properties have URI values
                # and if those are pointing to our server dropbox collections and only then set
                # the read mode
                self._attachment = _ATTACHMENTS_MODE_READ
                self._dropboxID = (yield self.dropboxID())

        if inserting:
            self._resourceID, self._created, self._modified  = (
                yield self._txn.execSQL(
                """
                insert into CALENDAR_OBJECT
                (CALENDAR_RESOURCE_ID, RESOURCE_NAME, ICALENDAR_TEXT, ICALENDAR_UID, ICALENDAR_TYPE,
                 ATTACHMENTS_MODE, DROPBOX_ID, ORGANIZER, RECURRANCE_MAX, ACCESS, SCHEDULE_OBJECT, SCHEDULE_TAG,
                 SCHEDULE_ETAGS, PRIVATE_COMMENTS, MD5)
                 values
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning
                 RESOURCE_ID,
                 CREATED,
                 MODIFIED
                """,
                [
                    self._calendar._resourceID,
                    self._name,
                    componentText,
                    self._uid,
                    component.resourceType(),
                    self._attachment,
                    self._dropboxID,
                    organizer,
                    normalizeForIndex(instances.limit) if instances.limit else None,
                    self._access,
                    self._schedule_object,
                    self._schedule_tag,
                    self._schedule_etags,
                    self._private_comments,
                    self._md5,
                ]
            ))[0]
        else:
            yield self._txn.execSQL(
                """
                update CALENDAR_OBJECT set
                (ICALENDAR_TEXT, ICALENDAR_UID, ICALENDAR_TYPE, ATTACHMENTS_MODE,
                 DROPBOX_ID, ORGANIZER, RECURRANCE_MAX, ACCESS, SCHEDULE_OBJECT, SCHEDULE_TAG,
                 SCHEDULE_ETAGS, PRIVATE_COMMENTS, MD5, MODIFIED)
                 =
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, timezone('UTC', CURRENT_TIMESTAMP))
                where RESOURCE_ID = %s
                returning MODIFIED
                """,
                [
                    componentText,
                    self._uid,
                    component.resourceType(),
                    self._attachment,
                    self._dropboxID,
                    organizer,
                    normalizeForIndex(instances.limit) if instances.limit else None,
                    self._access,
                    self._schedule_object,
                    self._schedule_tag,
                    self._schedule_etags,
                    self._private_comments,
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


    def _get_accessMode(self):
        return accesstype_to_accessMode[self._access]

    def _set_accessMode(self, value):
        self._access = accessMode_to_type[value]

    accessMode = property(_get_accessMode, _set_accessMode)

    def _get_isScheduleObject(self):
        return self._schedule_object

    def _set_isScheduleObject(self, value):
        self._schedule_object = value

    isScheduleObject = property(_get_isScheduleObject, _set_isScheduleObject)

    def _get_scheduleTag(self):
        return self._schedule_tag

    def _set_scheduleTag(self, value):
        self._schedule_tag = value

    scheduleTag = property(_get_scheduleTag, _set_scheduleTag)

    def _get_scheduleEtags(self):
        return tuple(self._schedule_etags.split(",")) if self._schedule_etags else ()

    def _set_scheduleEtags(self, value):
        self._schedule_etags = ",".join(value) if value else ""

    scheduleEtags = property(_get_scheduleEtags, _set_scheduleEtags)

    def _get_hasPrivateComment(self):
        return self._private_comments

    def _set_hasPrivateComment(self, value):
        self._private_comments = value

    hasPrivateComment = property(_get_hasPrivateComment, _set_hasPrivateComment)

    @inlineCallbacks
    def createAttachmentWithName(self, name):
        
        # We need to know the resource_ID of the home collection of the owner (not sharee)
        # of this event
        sharerHomeID = (yield self._parentCollection.sharerHomeID())
        returnValue((yield Attachment.create(self._txn, self._dropboxID, name, sharerHomeID)))

    @inlineCallbacks
    def removeAttachmentWithName(self, name):
        attachment = (yield self.attachmentWithName(name))
        yield attachment.remove()

    @inlineCallbacks
    def attachmentWithName(self, name):
        attachment = Attachment(self._txn, self._dropboxID, name)
        attachment = (yield attachment.initFromStore())
        returnValue(attachment)

    def attendeesCanManageAttachments(self):
        return self._attachment == _ATTACHMENTS_MODE_WRITE


    dropboxID = dropboxIDFromCalendarObject


    @inlineCallbacks
    def attachments(self):
        rows = yield self._txn.execSQL(
            """
            select PATH from ATTACHMENT where DROPBOX_ID = %s
            """, [self._dropboxID])
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

        home = (yield self._txn.calendarHomeWithResourceID(self.attachment._ownerHomeID))
        if home:
            # Adjust quota
            yield home.adjustQuotaUsedBytes(self.attachment.size() - old_size)
            
            # Send change notification to home
            yield home.notifyChanged()


def sqltime(value):
    return datetimeMktime(datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f"))

class Attachment(object):

    implements(IAttachment)

    def __init__(self, txn, dropboxID, name, ownerHomeID=None):
        self._txn = txn
        self._dropboxID = dropboxID
        self._name = name
        self._ownerHomeID = ownerHomeID
        self._size = 0


    @classmethod
    def _attachmentPathRoot(cls, txn, dropboxID):
        attachmentRoot = txn._store.attachmentsPath
        
        # Use directory hashing scheme based on MD5 of dropboxID
        hasheduid = hashlib.md5(dropboxID).hexdigest()
        return attachmentRoot.child(hasheduid[0:2]).child(hasheduid[2:4]).child(hasheduid)


    @classmethod
    @inlineCallbacks
    def create(cls, txn, dropboxID, name, ownerHomeID):

        # File system paths need to exist
        try:
            cls._attachmentPathRoot(txn, dropboxID).makedirs()
        except:
            pass

        # Now create the DB entry
        attachment = cls(txn, dropboxID, name, ownerHomeID)
        yield txn.execSQL(
            """
            insert into ATTACHMENT
              (CALENDAR_HOME_RESOURCE_ID, DROPBOX_ID, CONTENT_TYPE, SIZE, MD5, PATH)
             values
              (%s, %s, %s, %s, %s, %s)
            """,
            [
                ownerHomeID,
                dropboxID,
                "",
                0,
                "",
                name,
            ]
        )
        returnValue(attachment)

    @inlineCallbacks
    def initFromStore(self):
        """
        Execute necessary SQL queries to retrieve attributes.

        @return: C{True} if this attachment exists, C{False} otherwise.
        """
        rows = yield self._txn.execSQL(
            """
            select CALENDAR_HOME_RESOURCE_ID, CONTENT_TYPE, SIZE, MD5, CREATED, MODIFIED
             from ATTACHMENT
             where DROPBOX_ID = %s and PATH = %s
            """,
            [self._dropboxID, self._name]
        )
        if not rows:
            returnValue(None)
        self._ownerHomeID = rows[0][0]
        self._contentType = MimeType.fromString(rows[0][1])
        self._size = rows[0][2]
        self._md5 = rows[0][3]
        self._created = sqltime(rows[0][4])
        self._modified = sqltime(rows[0][5])
        returnValue(self)


    def name(self):
        return self._name

    @property
    def _path(self):
        attachmentRoot = self._txn._store.attachmentsPath
        
        # Use directory hashing scheme based on MD5 of dropboxID
        hasheduid = hashlib.md5(self._dropboxID).hexdigest()
        return attachmentRoot.child(hasheduid[0:2]).child(hasheduid[2:4]).child(hasheduid).child(self.name())

    def properties(self):
        pass # stub


    def store(self, contentType):
        return AttachmentStorageTransport(self, contentType)


    def retrieve(self, protocol):
        protocol.dataReceived(self._path.getContent())
        protocol.connectionLost(Failure(ConnectionLost()))


    @inlineCallbacks
    def remove(self):
        old_size = self._size
        self._txn.postCommit(self._path.remove)
        yield self._txn.execSQL(
            """
            delete from ATTACHMENT
             where DROPBOX_ID = %s and PATH = %s
            """,
            [self._dropboxID, self._name]
        )

        # Adjust quota
        home = (yield self._txn.calendarHomeWithResourceID(self._ownerHomeID))
        if home:
            yield home.adjustQuotaUsedBytes(-old_size)
            
            # Send change notification to home
            yield home.notifyChanged()

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


