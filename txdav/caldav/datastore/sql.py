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
from twisted.python import hashlib
from twisted.python.failure import Failure

from twistedcaldav import caldavxml, customxml
from twistedcaldav.caldavxml import ScheduleCalendarTransp, Opaque
from twistedcaldav.config import config
from twistedcaldav.dateops import normalizeForIndex, datetimeMktime,\
    parseSQLTimestamp, pyCalendarTodatetime
from twistedcaldav.ical import Component
from twistedcaldav.instance import InvalidOverriddenInstanceError
from twistedcaldav.memcacher import Memcacher

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
from twext.enterprise.dal.syntax import Select
from twext.enterprise.dal.syntax import Insert
from twext.enterprise.dal.syntax import Update
from twext.enterprise.dal.syntax import Delete
from twext.enterprise.dal.syntax import Parameter
from twext.enterprise.dal.syntax import utcNowSQL
from twext.enterprise.dal.syntax import Len

from txdav.caldav.datastore.util import CalendarObjectBase
from txdav.caldav.icalendarstore import QuotaExceeded

from txdav.caldav.datastore.util import StorageTransportBase
from txdav.common.icommondatastore import IndexedSearchException

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.duration import PyCalendarDuration
from pycalendar.timezone import PyCalendarTimezone

from zope.interface.declarations import implements

class CalendarHome(CommonHome):

    implements(ICalendarHome)

    # structured tables.  (new, preferred)
    _homeSchema = schema.CALENDAR_HOME
    _bindSchema = schema.CALENDAR_BIND
    _homeMetaDataSchema = schema.CALENDAR_HOME_METADATA
    _revisionsSchema = schema.CALENDAR_OBJECT_REVISIONS
    _objectSchema = schema.CALENDAR_OBJECT

    # string mappings (old, removing)
    _homeTable = CALENDAR_HOME_TABLE
    _homeMetaDataTable = CALENDAR_HOME_METADATA_TABLE
    _childTable = CALENDAR_TABLE
    _bindTable = CALENDAR_BIND_TABLE
    _objectBindTable = CALENDAR_OBJECT_AND_BIND_TABLE
    _notifierPrefix = "CalDAV"
    _revisionsTable = CALENDAR_OBJECT_REVISIONS_TABLE

    _cacher = Memcacher("SQL.calhome", pickle=True, key_normalization=False)

    def __init__(self, transaction, ownerUID, notifiers):

        self._childClass = Calendar
        super(CalendarHome, self).__init__(transaction, ownerUID, notifiers)
        self._shares = SQLLegacyCalendarShares(self)


    def quotaAllowedBytes(self):
        return self._txn.store().quota


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
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        rows = (yield Select(
            [co.PARENT_RESOURCE_ID,
             co.RESOURCE_ID],
            From=co.join(cb, co.PARENT_RESOURCE_ID == cb.RESOURCE_ID,
                         'left outer'),
            Where=(co.DROPBOX_ID == dropboxID).And(
                cb.HOME_RESOURCE_ID == self._resourceID)
        ).on(self._txn))

        if rows:
            calendarID, objectID = rows[0]
            calendar = (yield self.childWithID(calendarID))
            if calendar:
                calendarObject = (yield calendar.objectResourceWithID(objectID))
                returnValue(calendarObject)
        returnValue(None)


    @inlineCallbacks
    def getAllDropboxIDs(self):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        rows = (yield Select(
            [co.DROPBOX_ID],
            From=co.join(cb, co.PARENT_RESOURCE_ID == cb.RESOURCE_ID),
            Where=(co.DROPBOX_ID != None).And(
                cb.HOME_RESOURCE_ID == self._resourceID),
            OrderBy=co.DROPBOX_ID
        ).on(self._txn))
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

    # structured tables.  (new, preferred)
    _bindSchema = schema.CALENDAR_BIND
    _homeChildSchema = schema.CALENDAR
    _revisionsSchema = schema.CALENDAR_OBJECT_REVISIONS
    _objectSchema = schema.CALENDAR_OBJECT

    # string mappings (old, removing)
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


    def objectResourcesHaveProperties(self):
        """
        inbox resources need to store Originator, Recipient etc properties.
        Other calendars do not have object resources with properties.
        """
        return self._name == "inbox"

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



class CalendarObject(CommonObjectResource, CalendarObjectBase):
    implements(ICalendarObject)

    _objectTable = CALENDAR_OBJECT_TABLE
    _objectSchema = schema.CALENDAR_OBJECT

    def __init__(self, calendar, name, uid, resourceID=None, metadata=None):

        super(CalendarObject, self).__init__(calendar, name, uid, resourceID)

        if metadata is None:
            metadata = {}
        self.accessMode = metadata.get("accessMode", "")
        self.isScheduleObject = metadata.get("isScheduleObject", False)
        self.scheduleTag = metadata.get("scheduleTag", "")
        self.scheduleEtags = metadata.get("scheduleEtags", "")
        self.hasPrivateComment = metadata.get("hasPrivateComment", False)


    _allColumns = [
        _objectSchema.RESOURCE_ID,
        _objectSchema.RESOURCE_NAME,
        _objectSchema.UID,
        _objectSchema.MD5,
        Len(_objectSchema.TEXT),
        _objectSchema.ATTACHMENTS_MODE,
        _objectSchema.DROPBOX_ID,
        _objectSchema.ACCESS,
        _objectSchema.SCHEDULE_OBJECT,
        _objectSchema.SCHEDULE_TAG,
        _objectSchema.SCHEDULE_ETAGS,
        _objectSchema.PRIVATE_COMMENTS,
        _objectSchema.CREATED,
        _objectSchema.MODIFIED
    ]


    def _initFromRow(self, row):
        """
        Given a select result using the columns from L{_allColumns}, initialize
        the calendar object resource state.
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
    def updateDatabase(self, component,
                       expand_until=None, reCreate=False, inserting=False):
        """
        Update the database tables for the new data being written.

        @param component: calendar data to store
        @type component: L{Component}
        """

        # Decide how far to expand based on the component
        doInstanceIndexing = False
        master = component.masterComponent()
        if ( master is None or not component.isRecurring() ):
            # When there is no master we have a set of overridden components -
            #   index them all.
            # When there is one instance - index it.
            expand = PyCalendarDateTime(2100, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
            doInstanceIndexing = True
        else:

            # If migrating or re-creating or config option for delayed indexing is off, always index
            if reCreate or self._txn._migrating or not config.FreeBusyIndexDelayedExpand:
                doInstanceIndexing = True

            # Duration into the future through which recurrences are expanded in the index
            # by default.  This is a caching parameter which affects the size of the index;
            # it does not affect search results beyond this period, but it may affect
            # performance of such a search.
            expand = (PyCalendarDateTime.getToday() +
                      PyCalendarDuration(days=config.FreeBusyIndexExpandAheadDays))

            if expand_until and expand_until > expand:
                expand = expand_until

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
            if expand > (PyCalendarDateTime.getToday() +
                         PyCalendarDuration(days=config.FreeBusyIndexExpandMaxDays)):
                raise IndexedSearchException

        # Always do recurrence expansion even if we do not intend to index - we need this to double-check the
        # validity of the iCalendar recurrence data.
        try:
            instances = component.expandTimeRanges(expand, ignoreInvalidInstances=reCreate)
            recurrenceLimit = instances.limit
        except InvalidOverriddenInstanceError, e:
            self.log_error("Invalid instance %s when indexing %s in %s" %
                           (e.rid, self._name, self._calendar,))

            if self._txn._migrating:
                # TODO: fix the data here by re-writing component then re-index
                instances = component.expandTimeRanges(expand, ignoreInvalidInstances=True)
                recurrenceLimit = instances.limit
            else:
                raise

        # Now coerce indexing to off if needed
        if not doInstanceIndexing:
            instances = None
            recurrenceLimit = PyCalendarDateTime(1900, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))

        co = schema.CALENDAR_OBJECT
        tr = schema.TIME_RANGE
        tpy = schema.TRANSPARENCY

        # Do not update if reCreate (re-indexing - we don't want to re-write data
        # or cause modified to change)
        if not reCreate:
            componentText = str(component)
            self._objectText = componentText
            organizer = component.getOrganizer()
            if not organizer:
                organizer = ""

            # CALENDAR_OBJECT table update
            self._uid = component.resourceUID()
            self._md5 = hashlib.md5(componentText).hexdigest()
            self._size = len(componentText)

            # Special - if migrating we need to preserve the original md5
            if self._txn._migrating and hasattr(component, "md5"):
                self._md5 = component.md5

            # Determine attachment mode (ignore inbox's) - NB we have to do this
            # after setting up other properties as UID at least is needed
            self._attachment = _ATTACHMENTS_MODE_NONE
            self._dropboxID = None
            if self._parentCollection.name() != "inbox":
                if component.hasPropertyInAnyComponent("X-APPLE-DROPBOX"):
                    self._attachment = _ATTACHMENTS_MODE_WRITE
                    self._dropboxID = (yield self.dropboxID())
                elif component.hasPropertyInAnyComponent("ATTACH"):
                    # FIXME: really we ought to check to see if the ATTACH
                    # properties have URI values and if those are pointing to our
                    # server dropbox collections and only then set the read mode
                    self._attachment = _ATTACHMENTS_MODE_READ
                    self._dropboxID = (yield self.dropboxID())

            values = {
                co.CALENDAR_RESOURCE_ID            : self._calendar._resourceID,
                co.RESOURCE_NAME                   : self._name,
                co.ICALENDAR_TEXT                  : componentText,
                co.ICALENDAR_UID                   : self._uid,
                co.ICALENDAR_TYPE                  : component.resourceType(),
                co.ATTACHMENTS_MODE                : self._attachment,
                co.DROPBOX_ID                      : self._dropboxID,
                co.ORGANIZER                       : organizer,
                co.RECURRANCE_MAX                  :
                    pyCalendarTodatetime(normalizeForIndex(recurrenceLimit)) if recurrenceLimit else None,
                co.ACCESS                          : self._access,
                co.SCHEDULE_OBJECT                 : self._schedule_object,
                co.SCHEDULE_TAG                    : self._schedule_tag,
                co.SCHEDULE_ETAGS                  : self._schedule_etags,
                co.PRIVATE_COMMENTS                : self._private_comments,
                co.MD5                             : self._md5
            }

            if inserting:
                self._resourceID, self._created, self._modified = (
                    yield Insert(
                        values,
                        Return=(co.RESOURCE_ID, co.CREATED, co.MODIFIED)
                    ).on(self._txn)
                )[0]
            else:
                values[co.MODIFIED] = utcNowSQL
                self._modified = (
                    yield Update(
                        values, Return=co.MODIFIED,
                        Where=co.RESOURCE_ID == self._resourceID
                    ).on(self._txn)
                )[0][0]
                # Need to wipe the existing time-range for this and rebuild
                yield Delete(
                    From=tr,
                    Where=tr.CALENDAR_OBJECT_RESOURCE_ID == self._resourceID
                ).on(self._txn)
        else:
            values = {
                co.RECURRANCE_MAX :
                    pyCalendarTodatetime(normalizeForIndex(recurrenceLimit)) if recurrenceLimit else None,
            }

            yield Update(
                values,
                Where=co.RESOURCE_ID == self._resourceID
            ).on(self._txn)

            # Need to wipe the existing time-range for this and rebuild
            yield Delete(
                From=tr,
                Where=tr.CALENDAR_OBJECT_RESOURCE_ID == self._resourceID
            ).on(self._txn)

        if doInstanceIndexing:
            # TIME_RANGE table update
            for key in instances:
                instance = instances[key]
                start = instance.start
                end = instance.end
                float = instance.start.floating()
                start.setTimezoneUTC(True)
                end.setTimezoneUTC(True)
                transp = instance.component.propertyValue("TRANSP") == "TRANSPARENT"
                instanceid = (yield Insert({
                    tr.CALENDAR_RESOURCE_ID        : self._calendar._resourceID,
                    tr.CALENDAR_OBJECT_RESOURCE_ID : self._resourceID,
                    tr.FLOATING                    : float,
                    tr.START_DATE                  : pyCalendarTodatetime(start),
                    tr.END_DATE                    : pyCalendarTodatetime(end),
                    tr.FBTYPE                      :
                        icalfbtype_to_indexfbtype.get(
                            instance.component.getFBType(),
                            icalfbtype_to_indexfbtype["FREE"]),
                    tr.TRANSPARENT                 : transp,
                }, Return=tr.INSTANCE_ID).on(self._txn))[0][0]
                peruserdata = component.perUserTransparency(instance.rid)
                for useruid, transp in peruserdata:
                    (yield Insert({
                        tpy.TIME_RANGE_INSTANCE_ID : instanceid,
                        tpy.USER_ID                : useruid,
                        tpy.TRANSPARENT            : transp,
                    }).on(self._txn))

            # Special - for unbounded recurrence we insert a value for "infinity"
            # that will allow an open-ended time-range to always match it.
            if component.isRecurringUnbounded():
                start = PyCalendarDateTime(2100, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
                end = PyCalendarDateTime(2100, 1, 1, 1, 0, 0, tzid=PyCalendarTimezone(utc=True))
                float = False
                transp = True
                instanceid = (yield Insert({
                    tr.CALENDAR_RESOURCE_ID        : self._calendar._resourceID,
                    tr.CALENDAR_OBJECT_RESOURCE_ID : self._resourceID,
                    tr.FLOATING                    : float,
                    tr.START_DATE                  : pyCalendarTodatetime(start),
                    tr.END_DATE                    : pyCalendarTodatetime(end),
                    tr.FBTYPE                      :
                        icalfbtype_to_indexfbtype["UNKNOWN"],
                    tr.TRANSPARENT                 : transp,
                }, Return=tr.INSTANCE_ID).on(self._txn))[0][0]
                peruserdata = component.perUserTransparency(None)
                for useruid, transp in peruserdata:
                    (yield Insert({
                        tpy.TIME_RANGE_INSTANCE_ID : instanceid,
                        tpy.USER_ID                : useruid,
                        tpy.TRANSPARENT            : transp,
                    }).on(self._txn))


    @inlineCallbacks
    def component(self):
        returnValue(VComponent.fromString((yield self.iCalendarText())))


    iCalendarText = CommonObjectResource.text


    @inlineCallbacks
    def organizer(self):
        returnValue((yield self.component()).getOrganizer())


    def getMetadata(self):
        metadata = {}
        metadata["accessMode"] = self.accessMode
        metadata["isScheduleObject"] = self.isScheduleObject
        metadata["scheduleTag"] = self.scheduleTag
        metadata["scheduleEtags"] = self.scheduleEtags
        metadata["hasPrivateComment"] = self.hasPrivateComment
        return metadata

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

    def attachmentWithName(self, name):
        return Attachment.loadWithName(self._txn, self._dropboxID, name)

    def attendeesCanManageAttachments(self):
        return self._attachment == _ATTACHMENTS_MODE_WRITE


    dropboxID = dropboxIDFromCalendarObject


    _attachmentsQuery = Select(
        [schema.ATTACHMENT.PATH],
        From=schema.ATTACHMENT,
        Where=schema.ATTACHMENT.DROPBOX_ID == Parameter('dropboxID')
    )


    @inlineCallbacks
    def attachments(self):
        if self._dropboxID:
            rows = yield self._attachmentsQuery.on(self._txn,
                                                   dropboxID=self._dropboxID)
            result = []
            for row in rows:
                result.append((yield self.attachmentWithName(row[0])))
            returnValue(result)
        else:
            returnValue(())


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

    # IDataStoreObject
    def contentType(self):
        """
        The content type of Calendar objects is text/calendar.
        """
        return MimeType.fromString("text/calendar; charset=utf-8")



class AttachmentStorageTransport(StorageTransportBase):

    def __init__(self, attachment, contentType, creating=False):
        super(AttachmentStorageTransport, self).__init__(
            attachment, contentType)
        self._buf = ''
        self._hash = hashlib.md5()
        self._creating = creating


    @property
    def _txn(self):
        return self._attachment._txn


    def write(self, data):
        if isinstance(data, buffer):
            data = str(data)
        self._buf += data
        self._hash.update(data)


    @inlineCallbacks
    def loseConnection(self):

        # FIXME: this should be synchronously accessible; IAttachment should
        # have a method for getting its parent just as CalendarObject/Calendar
        # do.

        # FIXME: If this method isn't called, the transaction should be
        # prevented from committing successfully.  It's not valid to have an
        # attachment that doesn't point to a real file.

        home = (yield self._txn.calendarHomeWithResourceID(
                    self._attachment._ownerHomeID))

        oldSize = self._attachment.size()

        if home.quotaAllowedBytes() < ((yield home.quotaUsedBytes())
                                       + (len(self._buf) - oldSize)):
            if self._creating:
                yield self._attachment._internalRemove()
            raise QuotaExceeded()

        self._attachment._path.setContent(self._buf)
        self._attachment._contentType = self._contentType
        self._attachment._md5 = self._hash.hexdigest()
        self._attachment._size = len(self._buf)
        att = schema.ATTACHMENT
        self._attachment._created, self._attachment._modified = map(
            sqltime,
            (yield Update(
                {
                    att.CONTENT_TYPE : generateContentType(self._contentType),
                    att.SIZE         : self._attachment._size,
                    att.MD5          : self._attachment._md5,
                    att.MODIFIED     : utcNowSQL
                },
                Where=att.PATH == self._attachment.name(),
                Return=(att.CREATED, att.MODIFIED)).on(self._txn))[0]
        )

        if home:
            # Adjust quota
            yield home.adjustQuotaUsedBytes(self._attachment.size() - oldSize)

            # Send change notification to home
            yield home.notifyChanged()



def sqltime(value):
    return datetimeMktime(parseSQLTimestamp(value))

class Attachment(object):

    implements(IAttachment)

    def __init__(self, txn, dropboxID, name, ownerHomeID=None, justCreated=False):
        self._txn = txn
        self._dropboxID = dropboxID
        self._name = name
        self._ownerHomeID = ownerHomeID
        self._size = 0
        self._justCreated = justCreated


    @classmethod
    def _attachmentPathRoot(cls, txn, dropboxID):
        attachmentRoot = txn._store.attachmentsPath

        # Use directory hashing scheme based on MD5 of dropboxID
        hasheduid = hashlib.md5(dropboxID).hexdigest()
        return attachmentRoot.child(hasheduid[0:2]).child(
            hasheduid[2:4]).child(hasheduid)


    @classmethod
    @inlineCallbacks
    def create(cls, txn, dropboxID, name, ownerHomeID):

        # File system paths need to exist
        try:
            cls._attachmentPathRoot(txn, dropboxID).makedirs()
        except:
            pass

        # Now create the DB entry
        attachment = cls(txn, dropboxID, name, ownerHomeID, True)
        att = schema.ATTACHMENT
        yield Insert({
            att.CALENDAR_HOME_RESOURCE_ID : ownerHomeID,
            att.DROPBOX_ID                : dropboxID,
            att.CONTENT_TYPE              : "",
            att.SIZE                      : 0,
            att.MD5                       : "",
            att.PATH                      : name
        }).on(txn)
        returnValue(attachment)


    @classmethod
    @inlineCallbacks
    def loadWithName(cls, txn, dropboxID, name):
        attachment = cls(txn, dropboxID, name)
        attachment = (yield attachment.initFromStore())
        returnValue(attachment)


    @inlineCallbacks
    def initFromStore(self):
        """
        Execute necessary SQL queries to retrieve attributes.

        @return: C{True} if this attachment exists, C{False} otherwise.
        """
        att = schema.ATTACHMENT
        rows = (yield Select([att.CALENDAR_HOME_RESOURCE_ID, att.CONTENT_TYPE,
                              att.SIZE, att.MD5, att.CREATED, att.MODIFIED],
                             From=att,
                             Where=(att.DROPBOX_ID == self._dropboxID).And(
                                 att.PATH == self._name)).on(self._txn))
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
        return attachmentRoot.child(hasheduid[0:2]).child(
            hasheduid[2:4]).child(hasheduid).child(self.name())


    def properties(self):
        pass # stub


    def store(self, contentType):
        return AttachmentStorageTransport(self, contentType, self._justCreated)


    def retrieve(self, protocol):
        protocol.dataReceived(self._path.getContent())
        protocol.connectionLost(Failure(ConnectionLost()))


    _removeStatement = Delete(
        From=schema.ATTACHMENT,
        Where=(schema.ATTACHMENT.DROPBOX_ID == Parameter("dropboxID")).And(
            schema.ATTACHMENT.PATH == Parameter("path")
        ))


    @inlineCallbacks
    def remove(self):
        oldSize = self._size
        self._txn.postCommit(self._path.remove)
        yield self._internalRemove()
        # Adjust quota
        home = (yield self._txn.calendarHomeWithResourceID(self._ownerHomeID))
        if home:
            yield home.adjustQuotaUsedBytes(-oldSize)

            # Send change notification to home
            yield home.notifyChanged()


    def _internalRemove(self):
        """
        Just delete the row; don't do any accounting / bookkeeping.  (This is
        for attachments that have failed to be created due to errors during
        storage.)
        """
        return self._removeStatement.on(self._txn, dropboxID=self._dropboxID,
                                        path=self._name)


    # IDataStoreObject
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


