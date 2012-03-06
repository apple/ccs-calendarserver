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

from twext.python.clsprop import classproperty
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
from twistedcaldav.ical import Component, InvalidICalendarDataError
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
from twext.enterprise.dal.syntax import Select, Count, ColumnSyntax
from twext.enterprise.dal.syntax import Insert
from twext.enterprise.dal.syntax import Update
from twext.enterprise.dal.syntax import Delete
from twext.enterprise.dal.syntax import Parameter
from twext.enterprise.dal.syntax import utcNowSQL
from twext.enterprise.dal.syntax import Len

from txdav.caldav.datastore.util import CalendarObjectBase
from txdav.caldav.icalendarstore import QuotaExceeded

from txdav.caldav.datastore.util import StorageTransportBase
from txdav.common.icommondatastore import IndexedSearchException,\
    InternalDataStoreError, HomeChildNameAlreadyExistsError,\
    HomeChildNameNotAllowedError

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.duration import PyCalendarDuration
from pycalendar.timezone import PyCalendarTimezone

from zope.interface.declarations import implements

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
        self._shares = SQLLegacyCalendarShares(self)


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
        chm = schema.CALENDAR_HOME_METADATA
        cor = schema.CALENDAR_OBJECT_REVISIONS

        yield Delete(
            From=chm,
            Where=chm.RESOURCE_ID == self._resourceID
        ).on(self._txn)

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

        yield self._cacher.delete(str(self._ownerUID))


    @inlineCallbacks
    def hasCalendarResourceUIDSomewhereElse(self, uid, ok_object, type):
        """
        Determine if this calendar home contains any calendar objects which
        would potentially conflict with the given UID for scheduling purposes.

        @param uid: The UID to search for.
        @type uid: C{str}

        @param ok_object: a calendar object with the given UID, that doesn't
            count as a potential conflict (since, for example, it is the one
            being updated).  May be C{None} if all objects potentially count.
        @type ok_object: L{CalendarObject} or C{NoneType}

        @param type: a string, indicating the mode to check for conflicts.  If
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
            matched_type = ("schedule" if objectResource.isScheduleObject
                            else "calendar")
            if type == "schedule" or matched_type == "schedule":
                returnValue(True)

        returnValue(False)


    @inlineCallbacks
    def getCalendarResourcesForUID(self, uid, allow_shared=False):

        results = []
        objectResources = (yield self.objectResourcesWithUID(uid, ["inbox"]))
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
            self.log_warn("  Calendar: '%s', split into %d" % (calendar.name(), split_count+1,))

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
                
class Calendar(CommonHomeChild):
    """
    File-based implementation of L{ICalendar}.
    """
    implements(ICalendar)

    # structured tables.  (new, preferred)
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
        
        self._supportedComponents = None


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
        maxComponent = max(components, key=lambda x:x[1])[0]
        
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
                    newcalendar = yield self._home.createCalendarWithName("%s-%s-%d" % (self._name, component.lower(), ctr+1,))
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
    def _moveTimeRangeUpdateQuery(cls): #@NoSelf
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

        validateCalendarComponent(self, self._calendar, component, inserting, self._txn._migrating)

        yield self.updateDatabase(component, inserting=inserting)
        if inserting:
            yield self._calendar._insertRevision(self._name)
        else:
            yield self._calendar._updateRevision(self._name)

        yield self._calendar.notifyChanged()


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
            self._md5 = hashlib.md5(componentText + (self._schedule_tag if self._schedule_tag else "")).hexdigest()
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

        # We need to know the resource_ID of the home collection of the owner
        # (not sharee) of this event
        sharerHomeID = (yield self._parentCollection.sharerHomeID())
        returnValue((
            yield Attachment.create(
                self._txn, (yield self.dropboxID()), name, sharerHomeID
            )
        ))

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

        allowed = home.quotaAllowedBytes()
        if allowed is not None and allowed < ((yield home.quotaUsedBytes())
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
                Where=(att.PATH == self._attachment.name()).And(
                    att.DROPBOX_ID == self._attachment._dropboxID
                ),
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


