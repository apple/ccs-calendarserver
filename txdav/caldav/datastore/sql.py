# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Delete
from twext.enterprise.dal.syntax import Insert
from twext.enterprise.dal.syntax import Len
from twext.enterprise.dal.syntax import Parameter
from twext.enterprise.dal.syntax import Select, Count, ColumnSyntax
from twext.enterprise.dal.syntax import Update
from twext.enterprise.dal.syntax import utcNowSQL
from twext.python.clsprop import classproperty
from twext.python.filepath import CachingFilePath
from twext.python.vcomponent import VComponent
from twext.web2.http_headers import MimeType, generateContentType
from twext.web2.stream import readStream

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import hashlib

from twistedcaldav import caldavxml, customxml
from twistedcaldav.caldavxml import ScheduleCalendarTransp, Opaque
from twistedcaldav.config import config
from twistedcaldav.dateops import normalizeForIndex, datetimeMktime, \
    parseSQLTimestamp, pyCalendarTodatetime, parseSQLDateToPyCalendar
from twistedcaldav.ical import Component, InvalidICalendarDataError, Property
from twistedcaldav.instance import InvalidOverriddenInstanceError
from twistedcaldav.memcacher import Memcacher

from txdav.base.propertystore.base import PropertyName
from txdav.caldav.datastore.util import AttachmentRetrievalTransport
from txdav.caldav.datastore.util import CalendarObjectBase
from txdav.caldav.datastore.util import StorageTransportBase
from txdav.caldav.datastore.util import validateCalendarComponent, \
    dropboxIDFromCalendarObject
from txdav.caldav.icalendarstore import ICalendarHome, ICalendar, ICalendarObject, \
    IAttachment, AttachmentStoreFailed, AttachmentStoreValidManagedID
from txdav.caldav.icalendarstore import QuotaExceeded
from txdav.common.datastore.sql import CommonHome, CommonHomeChild, \
    CommonObjectResource, ECALENDARTYPE
from txdav.common.datastore.sql_legacy import PostgresLegacyIndexEmulator, \
    PostgresLegacyInboxIndexEmulator
from txdav.common.datastore.sql_tables import CALENDAR_TABLE, \
    CALENDAR_BIND_TABLE, CALENDAR_OBJECT_REVISIONS_TABLE, CALENDAR_OBJECT_TABLE, \
    _ATTACHMENTS_MODE_NONE, _ATTACHMENTS_MODE_READ, _ATTACHMENTS_MODE_WRITE, \
    CALENDAR_HOME_TABLE, CALENDAR_HOME_METADATA_TABLE, \
    CALENDAR_AND_CALENDAR_BIND, CALENDAR_OBJECT_REVISIONS_AND_BIND_TABLE, \
    CALENDAR_OBJECT_AND_BIND_TABLE, schema
from txdav.common.icommondatastore import IndexedSearchException, \
    InternalDataStoreError, HomeChildNameAlreadyExistsError, \
    HomeChildNameNotAllowedError
from txdav.xml.rfc2518 import ResourceType

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.duration import PyCalendarDuration
from pycalendar.timezone import PyCalendarTimezone
from pycalendar.value import PyCalendarValue

from zope.interface.declarations import implements

import collections
import os
import tempfile
import uuid

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

    _dataVersionKey = "CALENDAR-DATAVERSION"

    _cacher = Memcacher("SQL.calhome", pickle=True, key_normalization=False)

    def __init__(self, transaction, ownerUID, notifiers):

        self._childClass = Calendar
        super(CalendarHome, self).__init__(transaction, ownerUID, notifiers)

    createCalendarWithName = CommonHome.createChildWithName
    removeCalendarWithName = CommonHome.removeChildWithName
    calendarWithName = CommonHome.childWithName
    calendars = CommonHome.children
    listCalendars = CommonHome.listChildren
    loadCalendars = CommonHome.loadChildren

    @inlineCallbacks
    def remove(self):
        ch = schema.CALENDAR_HOME
        cb = schema.CALENDAR_BIND
        cor = schema.CALENDAR_OBJECT_REVISIONS
        rp = schema.RESOURCE_PROPERTY

        # delete attachments corresponding to this home, also removing from disk
        yield Attachment.removedHome(self._txn, self._resourceID)

        yield Delete(
            From=cb,
            Where=cb.CALENDAR_HOME_RESOURCE_ID == self._resourceID
        ).on(self._txn)

        yield Delete(
            From=cor,
            Where=cor.CALENDAR_HOME_RESOURCE_ID == self._resourceID
        ).on(self._txn)

        yield Delete(
            From=ch,
            Where=ch.RESOURCE_ID == self._resourceID
        ).on(self._txn)

        yield Delete(
            From=rp,
            Where=rp.RESOURCE_ID == self._resourceID
        ).on(self._txn)

        yield self._cacher.delete(str(self._ownerUID))


    @inlineCallbacks
    def hasCalendarResourceUIDSomewhereElse(self, uid, ok_object, mode):
        """
        Determine if this calendar home contains any calendar objects which
        would potentially conflict with the given UID for scheduling purposes.

        @param uid: The UID to search for.
        @type uid: C{str}

        @param ok_object: a calendar object with the given UID, that doesn't
            count as a potential conflict (since, for example, it is the one
            being updated).  May be C{None} if all objects potentially count.
        @type ok_object: L{CalendarObject} or C{NoneType}

        @param mode: a string, indicating the mode to check for conflicts.  If
            this is the string "schedule", then we are checking for potential
            conflicts with a new scheduled calendar object, which will conflict
            with any calendar object matching the given C{uid} in the home.
            Otherwise, (if this is the string "calendar") we are checking for
            conflicts with a new unscheduled calendar object, which will
            conflict only with other scheduled objects.
        @type type: C{str}

        @return: a L{Deferred} which fires with C{True} if there is a conflict
            and C{False} if not.
        """
        # FIXME: this should be documented on the interface; it should also
        # refer to calendar *object* UIDs, since calendar *resources* are an
        # HTTP protocol layer thing, not a data store thing.  (See also
        # objectResourcesWithUID.)
        objectResources = (
            yield self.objectResourcesWithUID(uid, ["inbox"], False)
        )
        for objectResource in objectResources:
            if ok_object and objectResource._resourceID == ok_object._resourceID:
                continue
            matched_mode = ("schedule" if objectResource.isScheduleObject
                            else "calendar")
            if mode == "schedule" or matched_mode == "schedule":
                returnValue(True)

        returnValue(False)


    @inlineCallbacks
    def getCalendarResourcesForUID(self, uid, allow_shared=False):

        results = []
        objectResources = (yield self.objectResourcesWithUID(uid, ["inbox"]))
        for objectResource in objectResources:
            if allow_shared or objectResource._parentCollection.owned():
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
    def getAllAttachmentNames(self):
        att = schema.ATTACHMENT
        rows = (yield Select(
            [att.DROPBOX_ID],
            From=att,
            Where=(att.CALENDAR_HOME_RESOURCE_ID == self._resourceID),
            OrderBy=att.DROPBOX_ID
        ).on(self._txn))
        returnValue([row[0] for row in rows])


    @inlineCallbacks
    def attachmentObjectWithID(self, managedID):
        attach = (yield ManagedAttachment.load(self._txn, managedID))
        returnValue(attach)


    @inlineCallbacks
    def createdHome(self):

        # Default calendar
        defaultCal = yield self.createCalendarWithName("calendar")
        props = defaultCal.properties()
        props[PropertyName(*ScheduleCalendarTransp.qname())] = ScheduleCalendarTransp(Opaque())

        # Check whether components type must be separate
        if config.RestrictCalendarsToOneComponentType:
            yield defaultCal.setSupportedComponents("VEVENT")

            # Default tasks
            defaultTasks = yield self.createCalendarWithName("tasks")
            yield defaultTasks.setSupportedComponents("VTODO")

        yield self.createCalendarWithName("inbox")


    @inlineCallbacks
    def splitCalendars(self):
        """
        Split all regular calendars by component type
        """

        # Make sure the loop does not operate on any new calendars created during the loop
        self.log_warn("Splitting calendars for user %s" % (self._ownerUID,))
        calendars = yield self.calendars()
        for calendar in calendars:

            # Ignore inbox - also shared calendars are not part of .calendars()
            if calendar.name() == "inbox":
                continue
            split_count = yield calendar.splitCollectionByComponentTypes()
            self.log_warn("  Calendar: '%s', split into %d" % (calendar.name(), split_count + 1,))

        yield self.ensureDefaultCalendarsExist()


    @inlineCallbacks
    def ensureDefaultCalendarsExist(self):
        """
        Double check that we have calendars supporting at least VEVENT and VTODO,
        and create if missing.
        """

        # Double check that we have calendars supporting at least VEVENT and VTODO
        if config.RestrictCalendarsToOneComponentType:
            supported_components = set()
            names = set()
            calendars = yield self.calendars()
            for calendar in calendars:
                if calendar.name() == "inbox":
                    continue
                names.add(calendar.name())
                result = yield calendar.getSupportedComponents()
                supported_components.update(result.split(","))

            @inlineCallbacks
            def _requireCalendarWithType(support_component, tryname):
                if support_component not in supported_components:
                    newname = tryname
                    if newname in names:
                        newname = str(uuid.uuid4())
                    newcal = yield self.createCalendarWithName(newname)
                    yield newcal.setSupportedComponents(support_component)

            yield _requireCalendarWithType("VEVENT", "calendar")
            yield _requireCalendarWithType("VTODO", "tasks")


CalendarHome._register(ECALENDARTYPE)



class Calendar(CommonHomeChild):
    """
    SQL-based implementation of L{ICalendar}.
    """
    implements(ICalendar)

    # structured tables.  (new, preferred)
    _homeSchema = schema.CALENDAR_HOME
    _bindSchema = schema.CALENDAR_BIND
    _homeChildSchema = schema.CALENDAR
    _homeChildMetaDataSchema = schema.CALENDAR_METADATA
    _revisionsSchema = schema.CALENDAR_OBJECT_REVISIONS
    _objectSchema = schema.CALENDAR_OBJECT
    _timeRangeSchema = schema.TIME_RANGE

    # string mappings (old, removing)
    _bindTable = CALENDAR_BIND_TABLE
    _homeChildTable = CALENDAR_TABLE
    _homeChildBindTable = CALENDAR_AND_CALENDAR_BIND
    _revisionsTable = CALENDAR_OBJECT_REVISIONS_TABLE
    _revisionsBindTable = CALENDAR_OBJECT_REVISIONS_AND_BIND_TABLE
    _objectTable = CALENDAR_OBJECT_TABLE

    _supportedComponents = None

    def __init__(self, *args, **kw):
        """
        Initialize a calendar pointing at a record in a database.
        """
        super(Calendar, self).__init__(*args, **kw)
        if self.name() == 'inbox':
            self._index = PostgresLegacyInboxIndexEmulator(self)
        else:
            self._index = PostgresLegacyIndexEmulator(self)


    @classmethod
    def metadataColumns(cls):
        """
        Return a list of column name for retrieval of metadata. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        # Common behavior is to have created and modified

        return (
            cls._homeChildMetaDataSchema.CREATED,
            cls._homeChildMetaDataSchema.MODIFIED,
            cls._homeChildMetaDataSchema.SUPPORTED_COMPONENTS,
        )


    @classmethod
    def metadataAttributes(cls):
        """
        Return a list of attribute names for retrieval of metadata. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        # Common behavior is to have created and modified

        return (
            "_created",
            "_modified",
            "_supportedComponents",
        )


    @property
    def _calendarHome(self):
        return self._home


    # FIXME: resource type is DAV.  This doesn't belong in the data store.  -wsv
    def resourceType(self):
        return ResourceType.calendar # @UndefinedVariable

    ownerCalendarHome = CommonHomeChild.ownerHome
    viewerCalendarHome = CommonHomeChild.viewerHome
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


    @inlineCallbacks
    def setSupportedComponents(self, supported_components):
        """
        Update the database column with the supported components. Technically this should only happen once
        on collection creation, but for migration we may need to change after the fact - hence a separate api.
        """

        cal = self._homeChildMetaDataSchema
        yield Update(
            {
                cal.SUPPORTED_COMPONENTS : supported_components
            },
            Where=(cal.RESOURCE_ID == self._resourceID)
        ).on(self._txn)
        self._supportedComponents = supported_components

        queryCacher = self._txn._queryCacher
        if queryCacher is not None:
            cacheKey = queryCacher.keyForHomeChildMetaData(self._resourceID)
            yield queryCacher.invalidateAfterCommit(self._txn, cacheKey)


    def getSupportedComponents(self):
        return self._supportedComponents


    def isSupportedComponent(self, componentType):
        if self._supportedComponents:
            return componentType.upper() in self._supportedComponents.split(",")
        else:
            return True


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


    # FIXME: this is DAV-ish.  Data store calendar objects don't have
    # mime types.  -wsv
    def contentType(self):
        """
        The content type of Calendar objects is text/calendar.
        """
        return MimeType.fromString("text/calendar; charset=utf-8")


    @inlineCallbacks
    def splitCollectionByComponentTypes(self):
        """
        If the calendar contains iCalendar data with different component types, then split it into separate collections
        each containing only one component type. When doing this make sure properties and sharing state are preserved
        on any new calendars created. Also restrict the new calendars to only the one appropriate component type. Return
        the number of splits done.
        """

        # First see how many different component types there are
        split_count = 0
        components = yield self._countComponentTypes()
        if len(components) <= 1:

            # Restrict calendar to single component type
            component = components[0][0] if components else "VEVENT"
            yield self.setSupportedComponents(component.upper())

            returnValue(split_count)

        # We will leave the component type with the highest count in the current calendar and create new calendars
        # for the others which will be moved over
        maxComponent = max(components, key=lambda x: x[1])[0]

        for component, _ignore_count in components:
            if component == maxComponent:
                continue
            split_count += 1
            yield self._splitComponentType(component)

        # Restrict calendar to single component type
        yield self.setSupportedComponents(maxComponent.upper())

        returnValue(split_count)


    @inlineCallbacks
    def _countComponentTypes(self):
        """
        Count each component type in this calendar.

        @return: a C{tuple} of C{tuple} containing the component type name and count.
        """

        ob = self._objectSchema
        _componentsQuery = Select(
            [ob.ICALENDAR_TYPE, Count(ob.ICALENDAR_TYPE)],
            From=ob,
            Where=ob.CALENDAR_RESOURCE_ID == Parameter('calID'),
            GroupBy=ob.ICALENDAR_TYPE
        )

        rows = yield _componentsQuery.on(self._txn, calID=self._resourceID)
        result = tuple([(componentType, componentCount) for componentType, componentCount in sorted(rows, key=lambda x:x[0])])
        returnValue(result)


    @inlineCallbacks
    def _splitComponentType(self, component):
        """
        Create a new calendar and move all components of the specified component type into the new one.
        Make sure properties and sharing state is preserved on the new calendar.

        @param component: Component type to split out
        @type component: C{str}
        """

        # Create the new calendar
        try:
            newcalendar = yield self._home.createCalendarWithName("%s-%s" % (self._name, component.lower(),))
        except HomeChildNameAlreadyExistsError:
            # If the name we want exists, try repeating with up to ten more
            for ctr in range(10):
                try:
                    newcalendar = yield self._home.createCalendarWithName("%s-%s-%d" % (self._name, component.lower(), ctr + 1,))
                except HomeChildNameAlreadyExistsError:
                    continue
            else:
                # At this point we are stuck
                raise HomeChildNameNotAllowedError

        # Restrict calendar to single component type
        yield newcalendar.setSupportedComponents(component.upper())

        # Transfer properties over
        yield newcalendar._properties.copyAllProperties(self._properties)

        # Transfer sharing
        yield self._transferSharingDetails(newcalendar, component)

        # Now move calendar data over
        yield self._transferCalendarObjects(newcalendar, component)


    @inlineCallbacks
    def _transferSharingDetails(self, newcalendar, component):
        """
        If the current calendar is shared, make the new calendar shared in the same way, but tweak the name.
        """

        cb = self._bindSchema
        columns = [ColumnSyntax(item) for item in self._bindSchema.model.columns]
        _bindQuery = Select(
            columns,
            From=cb,
            Where=(cb.CALENDAR_RESOURCE_ID == Parameter('calID')).And(
                cb.CALENDAR_HOME_RESOURCE_ID != Parameter('homeID'))
        )

        rows = yield _bindQuery.on(
            self._txn,
            calID=self._resourceID,
            homeID=self._home._resourceID,
        )

        if len(rows) == 0:
            returnValue(None)

        for row in rows:
            columnMap = dict(zip(columns, row))
            columnMap[cb.CALENDAR_RESOURCE_ID] = newcalendar._resourceID
            columnMap[cb.CALENDAR_RESOURCE_NAME] = "%s-%s" % (columnMap[cb.CALENDAR_RESOURCE_NAME], component.lower(),)
            yield Insert(columnMap).on(self._txn)


    @inlineCallbacks
    def _transferCalendarObjects(self, newcalendar, component):
        """
        Move all calendar components of the specified type to the specified calendar.
        """

        # Find resource-ids for all matching components
        ob = self._objectSchema
        _componentsQuery = Select(
            [ob.RESOURCE_ID],
            From=ob,
            Where=(ob.CALENDAR_RESOURCE_ID == Parameter('calID')).And(
                ob.ICALENDAR_TYPE == Parameter('componentType'))
        )

        rows = yield _componentsQuery.on(
            self._txn,
            calID=self._resourceID,
            componentType=component,
        )

        if len(rows) == 0:
            returnValue(None)

        for row in rows:
            resourceID = row[0]
            child = yield self.objectResourceWithID(resourceID)
            yield self.moveObjectResource(child, newcalendar)


    @classproperty
    def _moveTimeRangeUpdateQuery(cls): # @NoSelf
        """
        DAL query to update a child to be in a new parent.
        """
        tr = cls._timeRangeSchema
        return Update(
            {tr.CALENDAR_RESOURCE_ID: Parameter("newParentID")},
            Where=tr.CALENDAR_OBJECT_RESOURCE_ID == Parameter("resourceID")
        )


    @inlineCallbacks
    def _movedObjectResource(self, child, newparent):
        """
        Make sure time range entries have the new parent resource id.
        """
        yield self._moveTimeRangeUpdateQuery.on(
            self._txn,
            newParentID=newparent._resourceID,
            resourceID=child._resourceID
        )


    def unshare(self):
        """
        Unshares a collection, regardless of which "direction" it was shared.
        """
        return super(Calendar, self).unshare(ECALENDARTYPE)


    def creatingResourceCheckAttachments(self, component):
        """
        When component data is created or changed we need to look for changes related to managed attachments.

        @param component: the new calendar data
        @type component: L{Component}
        """
        return CalendarObject.creatingResourceCheckAttachments(self._txn, self, component)


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
accesstype_to_accessMode = dict([(v, k) for k, v in accessMode_to_type.items()])

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

        validateCalendarComponent(self, self._calendar, component, inserting, self._txn._migrating)

        yield self.updateDatabase(component, inserting=inserting)

        if inserting:
            yield self._calendar._insertRevision(self._name)
        else:
            yield self._calendar._updateRevision(self._name)

        yield self._calendar.notifyChanged()


    @inlineCallbacks
    def updateDatabase(self, component, expand_until=None, reCreate=False,
                       inserting=False, txn=None):
        """
        Update the database tables for the new data being written. Occasionally we might need to do an update to
        time-range data via a separate transaction, so we allow that to be passed in. Note that in that case
        access to the parent resources will not occur in this method, so the queries on the new txn won't depend
        on any parent objects having the same txn set.

        @param component: calendar data to store
        @type component: L{Component}
        """

        # Setup appropriate txn
        txn = txn if txn is not None else self._txn

        # inbox does things slightly differently
        isInboxItem = self._parentCollection.name() == "inbox"

        # In some cases there is no need to remove/rebuild the instance index because we know no time or
        # freebusy related properties have changed (e.g. an attendee reply and refresh). In those cases
        # the component will have a special attribute present to let us know to suppress the instance indexing.
        instanceIndexingRequired = not hasattr(component, "noInstanceIndexing") or inserting or reCreate

        if instanceIndexingRequired:

            # Decide how far to expand based on the component. doInstanceIndexing will indicate whether we
            # store expanded instance data immediately, or wait until a re-expand is triggered by some later
            # operation.
            doInstanceIndexing = False
            master = component.masterComponent()
            if (master is None or not component.isRecurring()):
                # When there is no master we have a set of overridden components -
                #   index them all.
                # When there is one instance - index it.
                expand = PyCalendarDateTime(2100, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
                doInstanceIndexing = True
            else:

                # If migrating or re-creating or config option for delayed indexing is off, always index
                if reCreate or txn._migrating or (not config.FreeBusyIndexDelayedExpand and not isInboxItem):
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

            if config.FreeBusyIndexLowerLimitDays:
                truncateLowerLimit = PyCalendarDateTime.getToday()
                truncateLowerLimit.offsetDay(-config.FreeBusyIndexLowerLimitDays)
            else:
                truncateLowerLimit = None

            # Always do recurrence expansion even if we do not intend to index - we need this to double-check the
            # validity of the iCalendar recurrence data.
            try:
                instances = component.expandTimeRanges(expand, lowerLimit=truncateLowerLimit, ignoreInvalidInstances=reCreate)
                recurrenceLimit = instances.limit
                recurrenceLowerLimit = instances.lowerLimit
            except InvalidOverriddenInstanceError, e:
                self.log_error("Invalid instance %s when indexing %s in %s" %
                               (e.rid, self._name, self._calendar,))

                if txn._migrating:
                    # TODO: fix the data here by re-writing component then re-index
                    instances = component.expandTimeRanges(expand, lowerLimit=truncateLowerLimit, ignoreInvalidInstances=True)
                    recurrenceLimit = instances.limit
                    recurrenceLowerLimit = instances.lowerLimit
                else:
                    raise

            # Now coerce indexing to off if needed
            if not doInstanceIndexing:
                instances = None
                recurrenceLowerLimit = None
                recurrenceLimit = PyCalendarDateTime(1900, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))

        co = schema.CALENDAR_OBJECT
        tr = schema.TIME_RANGE

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
            self._md5 = hashlib.md5(componentText + (self._schedule_tag if self._schedule_tag else "")).hexdigest()
            self._size = len(componentText)

            # Special - if migrating we need to preserve the original md5
            if txn._migrating and hasattr(component, "md5"):
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
                co.ACCESS                          : self._access,
                co.SCHEDULE_OBJECT                 : self._schedule_object,
                co.SCHEDULE_TAG                    : self._schedule_tag,
                co.SCHEDULE_ETAGS                  : self._schedule_etags,
                co.PRIVATE_COMMENTS                : self._private_comments,
                co.MD5                             : self._md5
            }

            # Only needed if indexing being changed
            if instanceIndexingRequired:
                values[co.RECURRANCE_MIN] = pyCalendarTodatetime(normalizeForIndex(recurrenceLowerLimit)) if recurrenceLowerLimit else None
                values[co.RECURRANCE_MAX] = pyCalendarTodatetime(normalizeForIndex(recurrenceLimit)) if recurrenceLimit else None

            if inserting:
                self._resourceID, self._created, self._modified = (
                    yield Insert(
                        values,
                        Return=(co.RESOURCE_ID, co.CREATED, co.MODIFIED)
                    ).on(txn)
                )[0]
            else:
                values[co.MODIFIED] = utcNowSQL
                self._modified = (
                    yield Update(
                        values, Return=co.MODIFIED,
                        Where=co.RESOURCE_ID == self._resourceID
                    ).on(txn)
                )[0][0]

                # Need to wipe the existing time-range for this and rebuild if required
                if instanceIndexingRequired:
                    yield Delete(
                        From=tr,
                        Where=tr.CALENDAR_OBJECT_RESOURCE_ID == self._resourceID
                    ).on(txn)
        else:
            # Keep MODIFIED the same when doing an index-only update
            values = {
                co.RECURRANCE_MIN : pyCalendarTodatetime(normalizeForIndex(recurrenceLowerLimit)) if recurrenceLowerLimit else None,
                co.RECURRANCE_MAX : pyCalendarTodatetime(normalizeForIndex(recurrenceLimit)) if recurrenceLimit else None,
                co.MODIFIED : self._modified,
            }

            yield Update(
                values,
                Where=co.RESOURCE_ID == self._resourceID
            ).on(txn)

            # Need to wipe the existing time-range for this and rebuild
            yield Delete(
                From=tr,
                Where=tr.CALENDAR_OBJECT_RESOURCE_ID == self._resourceID
            ).on(txn)

        if instanceIndexingRequired and doInstanceIndexing:
            yield self._addInstances(component, instances, truncateLowerLimit, txn)


    @inlineCallbacks
    def _addInstances(self, component, instances, truncateLowerLimit, txn):
        """
        Add the set of supplied instances to the store.

        @param component: the component whose instances are being added
        @type component: L{Component}
        @param instances: the set of instances to add
        @type instances: L{InstanceList}
        @param truncateLowerLimit: the lower limit for instances
        @type truncateLowerLimit: L{PyCalendarDateTime}
        @param txn: transaction to use
        @type txn: L{Transaction}
        """

        # TIME_RANGE table update
        lowerLimitApplied = False
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            floating = instance.start.floating()
            transp = instance.component.propertyValue("TRANSP") == "TRANSPARENT"
            fbtype = instance.component.getFBType()
            start.setTimezoneUTC(True)
            end.setTimezoneUTC(True)

            # Ignore if below the lower limit
            if truncateLowerLimit and end < truncateLowerLimit:
                lowerLimitApplied = True
                continue

            yield self._addInstanceDetails(component, instance.rid, start, end, floating, transp, fbtype, txn)

        # For truncated items we insert a tomb stone lower bound so that a time-range
        # query with just an end bound will match
        if lowerLimitApplied or instances.lowerLimit and len(instances.instances) == 0:
            start = PyCalendarDateTime(1901, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
            end = PyCalendarDateTime(1901, 1, 1, 1, 0, 0, tzid=PyCalendarTimezone(utc=True))
            yield self._addInstanceDetails(component, None, start, end, False, True, "UNKNOWN", txn)

        # Special - for unbounded recurrence we insert a value for "infinity"
        # that will allow an open-ended time-range to always match it.
        # We also need to add the "infinity" value if the event was bounded but
        # starts after the future expansion cut-off limit.
        if component.isRecurringUnbounded() or instances.limit and len(instances.instances) == 0:
            start = PyCalendarDateTime(2100, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
            end = PyCalendarDateTime(2100, 1, 1, 1, 0, 0, tzid=PyCalendarTimezone(utc=True))
            yield self._addInstanceDetails(component, None, start, end, False, True, "UNKNOWN", txn)


    @inlineCallbacks
    def _addInstanceDetails(self, component, rid, start, end, floating, transp, fbtype, txn):

        tr = schema.TIME_RANGE
        tpy = schema.TRANSPARENCY

        instanceid = (yield Insert({
            tr.CALENDAR_RESOURCE_ID        : self._calendar._resourceID,
            tr.CALENDAR_OBJECT_RESOURCE_ID : self._resourceID,
            tr.FLOATING                    : floating,
            tr.START_DATE                  : pyCalendarTodatetime(start),
            tr.END_DATE                    : pyCalendarTodatetime(end),
            tr.FBTYPE                      : icalfbtype_to_indexfbtype.get(fbtype, icalfbtype_to_indexfbtype["FREE"]),
            tr.TRANSPARENT                 : transp,
        }, Return=tr.INSTANCE_ID).on(txn))[0][0]
        peruserdata = component.perUserTransparency(rid)
        for useruid, usertransp in peruserdata:
            if usertransp != transp:
                (yield Insert({
                    tpy.TIME_RANGE_INSTANCE_ID : instanceid,
                    tpy.USER_ID                : useruid,
                    tpy.TRANSPARENT            : usertransp,
                }).on(txn))


    @inlineCallbacks
    def component(self):
        """
        Read calendar data and validate/fix it. Do not raise a store error here
        if there are unfixable errors as that could prevent the overall request
        to fail. Instead we will hand bad data off to the caller - that is not
        ideal but in theory we should have checked everything on the way in and
        only allowed in good data.
        """

        text = yield self._text()

        try:
            component = VComponent.fromString(text)
        except InvalidICalendarDataError, e:
            # This is a really bad situation, so do raise
            raise InternalDataStoreError(
                "Data corruption detected (%s) in id: %s"
                % (e, self._resourceID)
            )

        # Fix any bogus data we can
        fixed, unfixed = component.validCalendarData(doFix=True, doRaise=False)

        if unfixed:
            self.log_error("Calendar data id=%s had unfixable problems:\n  %s" %
                           (self._resourceID, "\n  ".join(unfixed),))

        if fixed:
            self.log_error("Calendar data id=%s had fixable problems:\n  %s" %
                           (self._resourceID, "\n  ".join(fixed),))

        returnValue(component)


    @inlineCallbacks
    def remove(self):
        # Need to also remove attachments
        if self._dropboxID:
            yield DropBoxAttachment.resourceRemoved(self._txn, self._resourceID, self._dropboxID)
        yield ManagedAttachment.resourceRemoved(self._txn, self._resourceID)
        yield super(CalendarObject, self).remove()


    @classproperty
    def _recurrenceMinMaxByIDQuery(cls): # @NoSelf
        """
        DAL query to load RECURRANCE_MIN, RECURRANCE_MAX via an object's resource ID.
        """
        co = schema.CALENDAR_OBJECT
        return Select(
            [co.RECURRANCE_MIN, co.RECURRANCE_MAX, ],
            From=co,
            Where=co.RESOURCE_ID == Parameter("resourceID"),
        )


    @inlineCallbacks
    def recurrenceMinMax(self, txn=None):
        """
        Get the RECURRANCE_MIN, RECURRANCE_MAX value from the database. Occasionally we might need to do an
        update to time-range data via a separate transaction, so we allow that to be passed in.

        @return: L{PyCalendarDateTime} result
        """
        # Setup appropriate txn
        txn = txn if txn is not None else self._txn

        rMin, rMax = (
            yield self._recurrenceMinMaxByIDQuery.on(txn,
                                         resourceID=self._resourceID)
        )[0]
        returnValue((
            parseSQLDateToPyCalendar(rMin) if rMin is not None else None,
            parseSQLDateToPyCalendar(rMax) if rMax is not None else None,
        ))


    @classproperty
    def _instanceQuery(cls): # @NoSelf
        """
        DAL query to load TIME_RANGE data via an object's resource ID.
        """
        tr = schema.TIME_RANGE
        return Select(
            [
                tr.INSTANCE_ID,
                tr.START_DATE,
                tr.END_DATE,
            ],
            From=tr,
            Where=tr.CALENDAR_OBJECT_RESOURCE_ID == Parameter("resourceID"),
        )


    @inlineCallbacks
    def instances(self, txn=None):
        """
        Get the set of instances from the database.

        @return: C{list} result
        """
        # Setup appropriate txn
        txn = txn if txn is not None else self._txn

        instances = (
            yield self._instanceQuery.on(txn,
                                         resourceID=self._resourceID)
        )
        returnValue(tuple(instances))


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
    def _preProcessAttachmentsOnResourceChange(self, component, inserting):
        """
        When component data is created or changed we need to look for changes related to managed attachments.

        @param component: the new calendar data
        @type component: L{Component}
        @param inserting: C{True} if resource is being created
        @type inserting: C{bool}
        """
        if inserting:
            self._copyAttachments = (yield self.creatingResourceCheckAttachments(component))
            self._removeAttachments = None
        else:
            self._copyAttachments, self._removeAttachments = (yield self.updatingResourceCheckAttachments(component))


    @classmethod
    @inlineCallbacks
    def creatingResourceCheckAttachments(cls, txn, parent, component):
        """
        A new component is going to be stored. Check any ATTACH properties that may be present
        to verify they owned by the organizer/owner of the resource and re-write the managed-ids.

        @param component: calendar component about to be stored
        @type component: L{Component}
        """

        # Retrieve all ATTACH properties with a MANAGED-ID
        attached = collections.defaultdict(list)
        attachments = component.getAllPropertiesInAnyComponent("ATTACH", depth=1,)
        for attachment in attachments:
            managed_id = attachment.parameterValue("MANAGED-ID")
            if managed_id is not None:
                attached[managed_id].append(attachment)

        # Punt if no managed attachments
        if len(attached) == 0:
            returnValue(None)

        changes = yield cls._addingManagedIDs(txn, parent, attached, component.resourceUID())
        returnValue(changes)


    @inlineCallbacks
    def updatingResourceCheckAttachments(self, component):
        """
        A component is being changed. Check any ATTACH properties that may be present
        to verify they owned by the organizer/owner of the resource and re-write the managed-ids.

        @param component: calendar component about to be stored
        @type component: L{Component}
        """

        # Retrieve all ATTACH properties with a MANAGED-ID in new data
        newattached = collections.defaultdict(list)
        newattachments = component.getAllPropertiesInAnyComponent("ATTACH", depth=1,)
        for attachment in newattachments:
            managed_id = attachment.parameterValue("MANAGED-ID")
            if managed_id is not None:
                newattached[managed_id].append(attachment)

        # Retrieve all ATTACH properties with a MANAGED-ID in old data
        oldcomponent = (yield self.component())
        oldattached = collections.defaultdict(list)
        oldattachments = oldcomponent.getAllPropertiesInAnyComponent("ATTACH", depth=1,)
        for attachment in oldattachments:
            managed_id = attachment.parameterValue("MANAGED-ID")
            if managed_id is not None:
                oldattached[managed_id].append(attachment)

        # Punt if no managed attachments
        if len(newattached) + len(oldattached) == 0:
            returnValue((None, None,))

        newattached_keys = set(newattached.keys())
        oldattached_keys = set(oldattached.keys())

        # Determine what was removed
        removed = set(oldattached_keys) - set(newattached_keys)

        # Determine what was added
        added = set(newattached_keys) - set(oldattached_keys)
        changed = {}
        for managed_id in added:
            changed[managed_id] = newattached[managed_id]

        changes = yield self._addingManagedIDs(self._txn, self._parentCollection, changed, component.resourceUID())

        # Make sure existing data is not changed
        same = oldattached_keys & newattached_keys
        for managed_id in same:
            newattachment = newattached[managed_id]
            oldattachment = oldattached[managed_id][0]
            for newattachment in newattached[managed_id]:
                if newattachment != oldattachment:
                    newattachment.setParameter("MTAG", oldattachment.parameterValue("MTAG"))
                    newattachment.setParameter("FMTTYPE", oldattachment.parameterValue("FMTTYPE"))
                    newattachment.setParameter("FILENAME", oldattachment.parameterValue("FILENAME"))
                    newattachment.setParameter("SIZE", oldattachment.parameterValue("SIZE"))
                    newattachment.setValue(oldattachment.value())

        returnValue((changes, removed,))


    @classmethod
    @inlineCallbacks
    def _addingManagedIDs(cls, txn, parent, attached, newuid):
        # Now check each managed-id
        changes = []
        for managed_id, attachments in attached.items():

            # Must be in the same home as this resource
            details = (yield ManagedAttachment.usedManagedID(txn, managed_id))
            if len(details) == 0:
                raise AttachmentStoreValidManagedID
            if len(details) != 1:
                # This is a bad store error - there should be only one home associated with a managed-id
                raise InternalDataStoreError
            home_id, _ignore_resource_id, uid = details[0]

            # Policy:
            #
            # 1. If Managed-ID is re-used in a resource with the same UID - it is fine - just rewrite the details
            # 2. If Managed-ID is re-used in a different resource but owned by the same user - change managed-id to new one
            # 3. Otherwise, strip off the managed-id property and treat as unmanaged.

            # 1. UID check
            if uid == newuid:
                yield cls._syncAttachmentProperty(txn, managed_id, attachments)

            # 2. Same home
            elif home_id == parent.ownerHome()._resourceID:

                # Need to rewrite the managed-id, value in the properties
                new_id = str(uuid.uuid4())
                yield cls._syncAttachmentProperty(txn, managed_id, attachments, new_id)
                changes.append((managed_id, new_id,))

            else:
                cls._stripAttachmentProperty(attachments)

        returnValue(changes)


    @classmethod
    @inlineCallbacks
    def _syncAttachmentProperty(cls, txn, managed_id, attachments, new_id=None):
        """
        Make sure the supplied set of attach properties are all sync'd with the current value of the
        matching managed-id attachment.

        @param managed_id: Managed-Id to sync with
        @type managed_id: C{str}
        @param attachments: list of attachment properties
        @type attachments: C{list} of L{twistedcaldav.ical.Property}
        @param new_id: Value of new Managed-ID to use
        @type new_id: C{str}
        """
        original_attachment = (yield ManagedAttachment.load(txn, managed_id))
        for attachment in attachments:
            attachment.setParameter("MANAGED-ID", managed_id if new_id is None else new_id)
            attachment.setParameter("MTAG", original_attachment.md5())
            attachment.setParameter("FMTTYPE", "%s/%s" % (original_attachment.contentType().mediaType, original_attachment.contentType().mediaSubtype))
            attachment.setParameter("FILENAME", original_attachment.name())
            attachment.setParameter("SIZE", str(original_attachment.size()))
            attachment.setValue((yield original_attachment.location(new_id)))


    @classmethod
    def _stripAttachmentProperty(cls, attachments):
        """
        Strip off managed-id related properties from an attachment.
        """
        for attachment in attachments:
            attachment.removeParameter("MANAGED-ID")
            attachment.removeParameter("MTAG")


    @inlineCallbacks
    def copyResourceAttachments(self, attached):
        """
        Copy an attachment reference for some other resource and link it to this resource.

        @param attached: tuple of old, new managed ids for the attachments to copy
        @type attached: C{tuple}
        """
        for old_id, new_id in attached:
            yield ManagedAttachment.copyManagedID(self._txn, old_id, new_id, self._resourceID)


    @inlineCallbacks
    def removeResourceAttachments(self, attached):
        """
        Remove an attachment reference for this resource.

        @param attached: managed-ids to remove
        @type attached: C{tuple}
        """
        for managed_id in attached:
            yield self.removeManagedAttachmentWithID(managed_id)


    @inlineCallbacks
    def addAttachment(self, rids, content_type, filename, stream, calendar):

        # First write the data stream

        # We need to know the resource_ID of the home collection of the owner
        # (not sharee) of this event
        try:
            attachment = (yield self.createManagedAttachment())
            t = attachment.store(content_type, filename)
            yield readStream(stream, t.write)
        except Exception, e:
            self.log_error("Unable to store attachment: %s" % (e,))
            raise AttachmentStoreFailed
        yield t.loseConnection()

        # Now try and adjust the actual calendar data
        #calendar = (yield self.component())

        location = (yield attachment.location())
        attach = Property("ATTACH", location, params={
            "MANAGED-ID": attachment.managedID(),
            "MTAG": attachment.md5(),
            "FMTTYPE": "%s/%s" % (attachment.contentType().mediaType, attachment.contentType().mediaSubtype),
            "FILENAME": attachment.name(),
            "SIZE": str(attachment.size()),
        }, valuetype=PyCalendarValue.VALUETYPE_URI)
        if rids is None:
            calendar.addPropertyToAllComponents(attach)
        else:
            # TODO - per-recurrence attachments
            pass

        # TODO: Here is where we want to store data implicitly - for now we have to let app layer deal with it
        #yield self.setComponent(calendar)

        returnValue((attachment, location,))


    @inlineCallbacks
    def updateAttachment(self, managed_id, content_type, filename, stream, calendar):

        # First check the supplied managed-id is associated with this resource
        cobjs = (yield ManagedAttachment.referencesTo(self._txn, managed_id))
        if self._resourceID not in cobjs:
            raise AttachmentStoreValidManagedID

        # Next write the data stream to existing attachment

        # We need to know the resource_ID of the home collection of the owner
        # (not sharee) of this event
        try:
            # Check that this is a proper update
            oldattachment = (yield self.attachmentWithManagedID(managed_id))
            if oldattachment is None:
                self.log_error("Missing managed attachment even though ATTACHMENT_CALENDAR_OBJECT indicates it is present: %s" % (managed_id,))
                raise AttachmentStoreFailed

            # We actually create a brand new attachment object for the update, but with the same managed-id. That way, other resources
            # referencing the old attachment data will still see that.
            attachment = (yield self.updateManagedAttachment(managed_id, oldattachment))
            t = attachment.store(content_type, filename)
            yield readStream(stream, t.write)
        except Exception, e:
            self.log_error("Unable to store attachment: %s" % (e,))
            raise AttachmentStoreFailed
        yield t.loseConnection()

        # Now try and adjust the actual calendar data
        #calendar = (yield self.component())

        location = self._txn._store.attachmentsURIPattern % {
            "home": self._parentCollection.ownerHome().name(),
            "name": attachment.managedID(),
        }
        attach = Property("ATTACH", location, params={
            "MANAGED-ID": attachment.managedID(),
            "MTAG": attachment.md5(),
            "FMTTYPE": "%s/%s" % (attachment.contentType().mediaType, attachment.contentType().mediaSubtype),
            "FILENAME": attachment.name(),
            "SIZE": str(attachment.size()),
        }, valuetype=PyCalendarValue.VALUETYPE_URI)
        calendar.replaceAllPropertiesWithParameterMatch(attach, "MANAGED-ID", managed_id)

        # TODO: Here is where we want to store data implicitly - for now we have to let app layer deal with it
        #yield self.setComponent(calendar)

        returnValue((attachment, location,))


    @inlineCallbacks
    def removeAttachment(self, rids, managed_id, calendar):

        # First check the supplied managed-id is associated with this resource
        cobjs = (yield ManagedAttachment.referencesTo(self._txn, managed_id))
        if self._resourceID not in cobjs:
            raise AttachmentStoreValidManagedID

        # Now try and adjust the actual calendar data
        all_removed = False
        #calendar = (yield self.component())
        if rids is None:
            calendar.removeAllPropertiesWithParameterMatch("ATTACH", "MANAGED-ID", managed_id)
            all_removed = True
        else:
            # TODO: per-recurrence removal
            pass

        # TODO: Here is where we want to store data implicitly - for now we have to let app layer deal with it
        #yield self.setComponent(calendar)

        # Remove it - this will take care of actually removing it from the store if there are
        # no more references to the attachment
        if all_removed:
            yield self.removeManagedAttachmentWithID(managed_id)


    @inlineCallbacks
    def createManagedAttachment(self):

        # We need to know the resource_ID of the home collection of the owner
        # (not sharee) of this event
        sharerHomeID = (yield self._parentCollection.sharerHomeID())
        managedID = str(uuid.uuid4())
        returnValue((
            yield ManagedAttachment.create(
                self._txn, managedID, sharerHomeID, self._resourceID,
            )
        ))


    @inlineCallbacks
    def updateManagedAttachment(self, managedID, oldattachment):

        # We need to know the resource_ID of the home collection of the owner
        # (not sharee) of this event
        sharerHomeID = (yield self._parentCollection.sharerHomeID())
        returnValue((
            yield ManagedAttachment.update(
                self._txn, managedID, sharerHomeID, self._resourceID, oldattachment._attachmentID,
            )
        ))


    def attachmentWithManagedID(self, managed_id):
        return ManagedAttachment.load(self._txn, managed_id)


    @inlineCallbacks
    def removeManagedAttachmentWithID(self, managed_id):
        attachment = (yield self.attachmentWithManagedID(managed_id))
        if attachment._objectResourceID == self._resourceID:
            yield attachment.removeFromResource(self._resourceID)


    @inlineCallbacks
    def createAttachmentWithName(self, name):

        # We need to know the resource_ID of the home collection of the owner
        # (not sharee) of this event
        sharerHomeID = (yield self._parentCollection.sharerHomeID())
        dropboxID = (yield self.dropboxID())
        returnValue((
            yield DropBoxAttachment.create(
                self._txn, dropboxID, name, sharerHomeID,
            )
        ))


    @inlineCallbacks
    def removeAttachmentWithName(self, name):
        attachment = (yield self.attachmentWithName(name))
        yield attachment.remove()


    def attachmentWithName(self, name):
        return DropBoxAttachment.load(self._txn, self._dropboxID, name)


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

    _TEMPORARY_UPLOADS_DIRECTORY = "Temporary"

    def __init__(self, attachment, contentType, dispositionName, creating=False):
        super(AttachmentStorageTransport, self).__init__(
            attachment, contentType, dispositionName)

        fileDescriptor, fileName = self._temporaryFile()
        # Wrap the file descriptor in a file object we can write to
        self._file = os.fdopen(fileDescriptor, "w")
        self._path = CachingFilePath(fileName)
        self._hash = hashlib.md5()
        self._creating = creating

        self._txn.postAbort(self.aborted)


    def _temporaryFile(self):
        """
        Returns a (file descriptor, absolute path) tuple for a temporary file within
        the Attachments/Temporary directory (creating the Temporary subdirectory
        if it doesn't exist).  It is the caller's responsibility to remove the
        file.
        """
        attachmentRoot = self._txn._store.attachmentsPath
        tempUploadsPath = attachmentRoot.child(self._TEMPORARY_UPLOADS_DIRECTORY)
        if not tempUploadsPath.exists():
            tempUploadsPath.createDirectory()
        return tempfile.mkstemp(dir=tempUploadsPath.path)


    @property
    def _txn(self):
        return self._attachment._txn


    def aborted(self):
        """
        Transaction aborted - clean up temp files.
        """
        if self._path.exists():
            self._path.remove()


    def write(self, data):
        if isinstance(data, buffer):
            data = str(data)
        self._file.write(data)
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
        newSize = self._file.tell()
        self._file.close()
        allowed = home.quotaAllowedBytes()
        if allowed is not None and allowed < ((yield home.quotaUsedBytes())
                                              + (newSize - oldSize)):
            self._path.remove()
            if self._creating:
                yield self._attachment._internalRemove()
            raise QuotaExceeded()

        self._path.moveTo(self._attachment._path)

        yield self._attachment.changed(
            self._contentType,
            self._dispositionName,
            self._hash.hexdigest(),
            newSize
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

    def __init__(self, txn, a_id, dropboxID, name, ownerHomeID=None, justCreated=False):
        self._txn = txn
        self._attachmentID = a_id
        self._ownerHomeID = ownerHomeID
        self._dropboxID = dropboxID
        self._contentType = None
        self._size = 0
        self._md5 = None
        self._created = None
        self._modified = None
        self._name = name
        self._justCreated = justCreated


    def _attachmentPathRoot(self):
        return self._txn._store.attachmentsPath


    @inlineCallbacks
    def initFromStore(self):
        """
        Execute necessary SQL queries to retrieve attributes.

        @return: C{True} if this attachment exists, C{False} otherwise.
        """
        att = schema.ATTACHMENT
        if self._dropboxID is not None:
            where = (att.DROPBOX_ID == self._dropboxID).And(
                   att.PATH == self._name)
        else:
            where = (att.ATTACHMENT_ID == self._attachmentID)
        rows = (yield Select(
            [
                att.ATTACHMENT_ID,
                att.DROPBOX_ID,
                att.CALENDAR_HOME_RESOURCE_ID,
                att.CONTENT_TYPE,
                att.SIZE,
                att.MD5,
                att.CREATED,
                att.MODIFIED,
                att.PATH,
            ],
            From=att,
            Where=where
        ).on(self._txn))

        if not rows:
            returnValue(None)

        row_iter = iter(rows[0])
        self._attachmentID = row_iter.next()
        self._dropboxID = row_iter.next()
        self._ownerHomeID = row_iter.next()
        self._contentType = MimeType.fromString(row_iter.next())
        self._size = row_iter.next()
        self._md5 = row_iter.next()
        self._created = sqltime(row_iter.next())
        self._modified = sqltime(row_iter.next())
        self._name = row_iter.next()

        returnValue(self)


    def dropboxID(self):
        return self._dropboxID


    def isManaged(self):
        return self._dropboxID == "."


    def name(self):
        return self._name


    def properties(self):
        pass # stub


    def store(self, contentType, dispositionName=None):
        return AttachmentStorageTransport(self, contentType, dispositionName, self._justCreated)


    def retrieve(self, protocol):
        return AttachmentRetrievalTransport(self._path).start(protocol)


    def changed(self, contentType, dispositionName, md5, size):
        raise NotImplementedError

    _removeStatement = Delete(
        From=schema.ATTACHMENT,
        Where=(schema.ATTACHMENT.ATTACHMENT_ID == Parameter("attachmentID"))
    )


    @inlineCallbacks
    def remove(self):
        oldSize = self._size
        self._txn.postCommit(self.removePaths)
        yield self._internalRemove()
        # Adjust quota
        home = (yield self._txn.calendarHomeWithResourceID(self._ownerHomeID))
        if home:
            yield home.adjustQuotaUsedBytes(-oldSize)

            # Send change notification to home
            yield home.notifyChanged()


    def removePaths(self):
        """
        Remove the actual file and up to attachment parent directory if empty.
        """
        self._path.remove()
        parent = self._path.parent()
        toppath = self._attachmentPathRoot().path
        while parent.path != toppath:
            if len(parent.listdir()) == 0:
                parent.remove()
                parent = parent.parent()
            else:
                break


    def _internalRemove(self):
        """
        Just delete the row; don't do any accounting / bookkeeping.  (This is
        for attachments that have failed to be created due to errors during
        storage.)
        """
        return self._removeStatement.on(self._txn, attachmentID=self._attachmentID)


    @classmethod
    @inlineCallbacks
    def removedHome(cls, txn, homeID):
        """
        A calendar home is being removed so all of its attachments must go too. When removing,
        we don't care about quota adjustment as there will be no quota once the home is removed.

        TODO: this needs to be transactional wrt the actual file deletes.
        """
        att = schema.ATTACHMENT
        attco = schema.ATTACHMENT_CALENDAR_OBJECT

        rows = (yield Select(
            [att.ATTACHMENT_ID, att.DROPBOX_ID, ],
            From=att,
            Where=(
                att.CALENDAR_HOME_RESOURCE_ID == homeID
            ),
        ).on(txn))

        for attachmentID, dropboxID in rows:
            if dropboxID:
                attachment = DropBoxAttachment(txn, attachmentID, None, None)
            else:
                attachment = ManagedAttachment(txn, attachmentID, None, None)
            attachment = (yield attachment.initFromStore())
            if attachment._path.exists():
                attachment.removePaths()

        yield Delete(
            From=attco,
            Where=(
                attco.ATTACHMENT_ID.In(Select(
                    [att.ATTACHMENT_ID, ],
                    From=att,
                    Where=(
                        att.CALENDAR_HOME_RESOURCE_ID == homeID
                    ),
                ))
            ),
        ).on(txn)

        yield Delete(
            From=att,
            Where=(
                att.CALENDAR_HOME_RESOURCE_ID == homeID
            ),
        ).on(txn)


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



class DropBoxAttachment(Attachment):

    @classmethod
    @inlineCallbacks
    def create(cls, txn, dropboxID, name, ownerHomeID):
        """
        Create a new Attachment object.

        @param txn: The transaction to use
        @type txn: L{CommonStoreTransaction}
        @param dropboxID: the identifier for the attachment (dropbox id or managed id)
        @type dropboxID: C{str}
        @param name: the name of the attachment
        @type name: C{str}
        @param ownerHomeID: the resource-id of the home collection of the attachment owner
        @type ownerHomeID: C{int}
        """

        # Now create the DB entry
        att = schema.ATTACHMENT
        rows = (yield Insert({
            att.CALENDAR_HOME_RESOURCE_ID : ownerHomeID,
            att.DROPBOX_ID                : dropboxID,
            att.CONTENT_TYPE              : "",
            att.SIZE                      : 0,
            att.MD5                       : "",
            att.PATH                      : name,
        }, Return=(att.ATTACHMENT_ID, att.CREATED, att.MODIFIED)).on(txn))

        row_iter = iter(rows[0])
        a_id = row_iter.next()
        created = sqltime(row_iter.next())
        modified = sqltime(row_iter.next())

        attachment = cls(txn, a_id, dropboxID, name, ownerHomeID, True)
        attachment._created = created
        attachment._modified = modified

        # File system paths need to exist
        try:
            attachment._path.parent().makedirs()
        except:
            pass

        returnValue(attachment)


    @classmethod
    @inlineCallbacks
    def load(cls, txn, dropboxID, name):
        attachment = cls(txn, None, dropboxID, name)
        attachment = (yield attachment.initFromStore())
        returnValue(attachment)


    @property
    def _path(self):
        # Use directory hashing scheme based on MD5 of dropboxID
        hasheduid = hashlib.md5(self._dropboxID).hexdigest()
        attachmentRoot = self._attachmentPathRoot().child(hasheduid[0:2]).child(hasheduid[2:4]).child(hasheduid)
        return attachmentRoot.child(self.name())


    @classmethod
    @inlineCallbacks
    def resourceRemoved(cls, txn, resourceID, dropboxID):
        """
        Remove all attachments referencing the specified resource.
        """

        # See if any other resources still reference this dropbox ID
        co = schema.CALENDAR_OBJECT
        rows = (yield Select(
            [co.RESOURCE_ID, ],
            From=co,
            Where=(co.DROPBOX_ID == dropboxID).And(
                co.RESOURCE_ID != resourceID)
        ).on(txn))

        if not rows:
            # Find each attachment with matching dropbox ID
            att = schema.ATTACHMENT
            rows = (yield Select(
                [att.PATH],
                From=att,
                Where=(att.DROPBOX_ID == dropboxID)
            ).on(txn))
            for name in rows:
                name = name[0]
                attachment = yield cls.load(txn, dropboxID, name)
                yield attachment.remove()


    @inlineCallbacks
    def changed(self, contentType, dispositionName, md5, size):
        """
        Dropbox attachments never change their path - ignore dispositionName.
        """

        self._contentType = contentType
        self._md5 = md5
        self._size = size

        att = schema.ATTACHMENT
        self._created, self._modified = map(
            sqltime,
            (yield Update(
                {
                    att.CONTENT_TYPE    : generateContentType(self._contentType),
                    att.SIZE            : self._size,
                    att.MD5             : self._md5,
                    att.MODIFIED        : utcNowSQL,
                },
                Where=(att.ATTACHMENT_ID == self._attachmentID),
                Return=(att.CREATED, att.MODIFIED)).on(self._txn))[0]
        )



class ManagedAttachment(Attachment):

    @classmethod
    @inlineCallbacks
    def _create(cls, txn, managedID, ownerHomeID):
        """
        Create a new Attachment object.

        @param txn: The transaction to use
        @type txn: L{CommonStoreTransaction}
        @param managedID: the identifier for the attachment
        @type managedID: C{str}
        @param ownerHomeID: the resource-id of the home collection of the attachment owner
        @type ownerHomeID: C{int}
        """

        # Now create the DB entry
        att = schema.ATTACHMENT
        rows = (yield Insert({
            att.CALENDAR_HOME_RESOURCE_ID : ownerHomeID,
            att.DROPBOX_ID                : ".",
            att.CONTENT_TYPE              : "",
            att.SIZE                      : 0,
            att.MD5                       : "",
            att.PATH                      : "",
        }, Return=(att.ATTACHMENT_ID, att.CREATED, att.MODIFIED)).on(txn))

        row_iter = iter(rows[0])
        a_id = row_iter.next()
        created = sqltime(row_iter.next())
        modified = sqltime(row_iter.next())

        attachment = cls(txn, a_id, managedID, None, ownerHomeID, True)
        attachment._managedID = managedID
        attachment._created = created
        attachment._modified = modified

        # File system paths need to exist
        try:
            attachment._path.parent().makedirs()
        except:
            pass

        returnValue(attachment)


    @classmethod
    @inlineCallbacks
    def create(cls, txn, managedID, ownerHomeID, referencedBy):
        """
        Create a new Attachment object.

        @param txn: The transaction to use
        @type txn: L{CommonStoreTransaction}
        @param managedID: the identifier for the attachment
        @type managedID: C{str}
        @param ownerHomeID: the resource-id of the home collection of the attachment owner
        @type ownerHomeID: C{int}
        @param referencedBy: the resource-id of the calendar object referencing the attachment
        @type referencedBy: C{int}
        """

        # Now create the DB entry
        attachment = (yield cls._create(txn, managedID, ownerHomeID))

        # Create the attachment<->calendar object relationship for managed attachments
        attco = schema.ATTACHMENT_CALENDAR_OBJECT
        yield Insert({
            attco.ATTACHMENT_ID               : attachment._attachmentID,
            attco.MANAGED_ID                  : managedID,
            attco.CALENDAR_OBJECT_RESOURCE_ID : referencedBy,
        }).on(txn)

        returnValue(attachment)


    @classmethod
    @inlineCallbacks
    def update(cls, txn, managedID, ownerHomeID, referencedBy, oldAttachmentID):
        """
        Create a new Attachment object.

        @param txn: The transaction to use
        @type txn: L{CommonStoreTransaction}
        @param managedID: the identifier for the attachment
        @type managedID: C{str}
        @param ownerHomeID: the resource-id of the home collection of the attachment owner
        @type ownerHomeID: C{int}
        @param referencedBy: the resource-id of the calendar object referencing the attachment
        @type referencedBy: C{int}
        @param oldAttachmentID: the attachment-id of the existing attachment being updated
        @type oldAttachmentID: C{int}
        """

        # Now create the DB entry
        attachment = (yield cls._create(txn, managedID, ownerHomeID))

        # Update the attachment<->calendar object relationship for managed attachments
        attco = schema.ATTACHMENT_CALENDAR_OBJECT
        yield Update(
            {
                attco.ATTACHMENT_ID    : attachment._attachmentID,
            },
            Where=(attco.MANAGED_ID == managedID).And(
                attco.CALENDAR_OBJECT_RESOURCE_ID == referencedBy
            ),
        ).on(txn)

        # Now check whether old attachmentID is still referenced - if not delete it
        rows = (yield Select(
            [attco.ATTACHMENT_ID, ],
            From=attco,
            Where=(attco.ATTACHMENT_ID == oldAttachmentID),
        ).on(txn))
        aids = [row[0] for row in rows] if rows is not None else ()
        if len(aids) == 0:
            oldattachment = ManagedAttachment(txn, oldAttachmentID, None, None)
            oldattachment = (yield oldattachment.initFromStore())
            yield oldattachment.remove()

        returnValue(attachment)


    @classmethod
    @inlineCallbacks
    def load(cls, txn, managedID):
        attco = schema.ATTACHMENT_CALENDAR_OBJECT
        rows = (yield Select(
            [attco.ATTACHMENT_ID, attco.CALENDAR_OBJECT_RESOURCE_ID, ],
            From=attco,
            Where=(attco.MANAGED_ID == managedID),
        ).on(txn))
        if len(rows) == 0:
            returnValue(None)
        elif len(rows) != 1:
            raise AttachmentStoreValidManagedID

        attachment = cls(txn, rows[0][0], None, None)
        attachment = (yield attachment.initFromStore())
        attachment._managedID = managedID
        attachment._objectResourceID = rows[0][1]
        returnValue(attachment)


    @classmethod
    @inlineCallbacks
    def referencesTo(cls, txn, managedID):
        """
        Find all the calendar object resourceIds referenced by this supplied managed-id.
        """
        attco = schema.ATTACHMENT_CALENDAR_OBJECT
        rows = (yield Select(
            [attco.CALENDAR_OBJECT_RESOURCE_ID, ],
            From=attco,
            Where=(attco.MANAGED_ID == managedID),
        ).on(txn))
        cobjs = set([row[0] for row in rows]) if rows is not None else set()
        returnValue(cobjs)


    @classmethod
    @inlineCallbacks
    def usedManagedID(cls, txn, managedID):
        """
        Return the "owner" home and referencing resource is, and UID for a managed-id.
        """
        att = schema.ATTACHMENT
        attco = schema.ATTACHMENT_CALENDAR_OBJECT
        co = schema.CALENDAR_OBJECT
        rows = (yield Select(
            [
                att.CALENDAR_HOME_RESOURCE_ID,
                attco.CALENDAR_OBJECT_RESOURCE_ID,
                co.ICALENDAR_UID,
            ],
            From=att.join(
                attco, att.ATTACHMENT_ID == attco.ATTACHMENT_ID, "left outer"
            ).join(co, co.RESOURCE_ID == attco.CALENDAR_OBJECT_RESOURCE_ID),
            Where=(attco.MANAGED_ID == managedID),
        ).on(txn))
        returnValue(rows)


    @classmethod
    @inlineCallbacks
    def resourceRemoved(cls, txn, resourceID):
        """
        Remove all attachments referencing the specified resource.
        """

        # Find all reference attachment-ids and dereference
        attco = schema.ATTACHMENT_CALENDAR_OBJECT
        rows = (yield Select(
            [attco.MANAGED_ID, ],
            From=attco,
            Where=(attco.CALENDAR_OBJECT_RESOURCE_ID == resourceID),
        ).on(txn))
        mids = set([row[0] for row in rows]) if rows is not None else set()
        for managedID in mids:
            attachment = (yield ManagedAttachment.load(txn, managedID))
            (yield attachment.removeFromResource(resourceID))


    @classmethod
    @inlineCallbacks
    def copyManagedID(cls, txn, oldManagedID, newManagedID, referencedBy):
        """
        Copy a managed-ID to a new ID and associate the original attachment with the
        new resource.
        """

        # Find all reference attachment-ids and dereference
        attco = schema.ATTACHMENT_CALENDAR_OBJECT
        aid = (yield Select(
            [attco.ATTACHMENT_ID, ],
            From=attco,
            Where=(attco.MANAGED_ID == oldManagedID),
        ).on(txn))[0][0]

        yield Insert({
            attco.ATTACHMENT_ID               : aid,
            attco.MANAGED_ID                  : newManagedID,
            attco.CALENDAR_OBJECT_RESOURCE_ID : referencedBy,
        }).on(txn)


    def managedID(self):
        return self._managedID


    @inlineCallbacks
    def objectResource(self):
        """
        Return the calendar object resource associated with this attachment.
        """

        home = (yield self._txn.calendarHomeWithResourceID(self._ownerHomeID))
        obj = (yield home.objectResourceWithID(self._objectResourceID))
        returnValue(obj)


    @property
    def _path(self):
        # Use directory hashing scheme based on MD5 of attachmentID
        hasheduid = hashlib.md5(str(self._attachmentID)).hexdigest()
        return self._attachmentPathRoot().child(hasheduid[0:2]).child(hasheduid[2:4]).child(hasheduid)


    @inlineCallbacks
    def location(self, new_id=None):
        """
        Return the URI location of the attachment. Use a different managed-id if one is passed in. That is used
        when creating a reference to an existing attachment via a new Managed-ID.
        """
        if not hasattr(self, "_ownerName"):
            home = (yield self._txn.calendarHomeWithResourceID(self._ownerHomeID))
            self._ownerName = home.name()
        location = self._txn._store.attachmentsURIPattern % {
            "home": self._ownerName,
            "name": self._managedID if new_id is None else new_id,
        }
        returnValue(location)


    @inlineCallbacks
    def changed(self, contentType, dispositionName, md5, size):
        """
        Always update name to current disposition name.
        """

        self._contentType = contentType
        self._name = dispositionName
        self._md5 = md5
        self._size = size
        att = schema.ATTACHMENT
        self._created, self._modified = map(
            sqltime,
            (yield Update(
                {
                    att.CONTENT_TYPE    : generateContentType(self._contentType),
                    att.SIZE            : self._size,
                    att.MD5             : self._md5,
                    att.MODIFIED        : utcNowSQL,
                    att.PATH            : self._name,
                },
                Where=(att.ATTACHMENT_ID == self._attachmentID),
                Return=(att.CREATED, att.MODIFIED)).on(self._txn))[0]
        )


    @inlineCallbacks
    def removeFromResource(self, resourceID):

        # Delete the reference
        attco = schema.ATTACHMENT_CALENDAR_OBJECT
        yield Delete(
            From=attco,
            Where=(attco.ATTACHMENT_ID == self._attachmentID).And(
                   attco.CALENDAR_OBJECT_RESOURCE_ID == resourceID),
        ).on(self._txn)

        # References still exist - if not remove actual attachment
        rows = (yield Select(
            [attco.CALENDAR_OBJECT_RESOURCE_ID, ],
            From=attco,
            Where=(attco.ATTACHMENT_ID == self._attachmentID),
        ).on(self._txn))
        if len(rows) == 0:
            yield self.remove()


Calendar._objectResourceClass = CalendarObject
