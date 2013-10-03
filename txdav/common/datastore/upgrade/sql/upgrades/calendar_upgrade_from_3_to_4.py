# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Select, Delete, Parameter

from twisted.internet.defer import inlineCallbacks

from twistedcaldav import caldavxml, customxml

from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.sql_tables import schema, _BIND_MODE_OWN
from txdav.common.datastore.upgrade.sql.upgrades.util import rowsForProperty, updateCalendarDataVersion, \
    updateAllCalendarHomeDataVersions, removeProperty, cleanPropertyStore
from txdav.xml.parser import WebDAVDocument
from txdav.xml import element
from twisted.python.failure import Failure

"""
Data upgrade from database version 3 to 4
"""

UPGRADE_TO_VERSION = 4
BATCH_SIZE = 100

@inlineCallbacks
def doUpgrade(sqlStore):
    """
    Do the required upgrade steps.
    """
    yield moveDefaultCalendarProperties(sqlStore)
    yield moveCalendarTranspProperties(sqlStore)
    yield moveDefaultAlarmProperties(sqlStore)
    yield removeResourceType(sqlStore)

    # Always bump the DB value
    yield updateCalendarDataVersion(sqlStore, UPGRADE_TO_VERSION)
    yield updateAllCalendarHomeDataVersions(sqlStore, UPGRADE_TO_VERSION)



@inlineCallbacks
def moveDefaultCalendarProperties(sqlStore):
    """
    Need to move all the CalDAV:default-calendar and CS:default-tasks properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_HOME_METADATA table columns, extracting
    the new value from the XML property.
    """

    meta = schema.CALENDAR_HOME_METADATA
    yield _processDefaultCalendarProperty(sqlStore, caldavxml.ScheduleDefaultCalendarURL, meta.DEFAULT_EVENTS)
    yield _processDefaultCalendarProperty(sqlStore, customxml.ScheduleDefaultTasksURL, meta.DEFAULT_TASKS)



@inlineCallbacks
def _processDefaultCalendarProperty(sqlStore, propname, colname):
    """
    Move the specified property value to the matching CALENDAR_HOME_METADATA table column.

    Since the number of calendar homes may well be large, we need to do this in batches.
    """

    cb = schema.CALENDAR_BIND
    rp = schema.RESOURCE_PROPERTY

    try:
        while True:
            sqlTxn = sqlStore.newTransaction()
            rows = (yield rowsForProperty(sqlTxn, propname, batch=BATCH_SIZE))
            if len(rows) == 0:
                yield sqlTxn.commit()
                break
            delete_ids = []
            for inbox_rid, value in rows:
                delete_ids.append(inbox_rid)
                ids = yield Select(
                    [cb.CALENDAR_HOME_RESOURCE_ID, ],
                    From=cb,
                    Where=cb.CALENDAR_RESOURCE_ID == inbox_rid,
                ).on(sqlTxn)
                if len(ids) > 0:

                    calendarHome = (yield sqlTxn.calendarHomeWithResourceID(ids[0][0]))
                    if calendarHome is not None:

                        prop = WebDAVDocument.fromString(value).root_element
                        defaultCalendar = str(prop.children[0])
                        parts = defaultCalendar.split("/")
                        if len(parts) == 5:

                            calendarName = parts[-1]
                            calendarHomeUID = parts[-2]
                            expectedHome = (yield sqlTxn.calendarHomeWithUID(calendarHomeUID))
                            if expectedHome is not None and expectedHome.id() == calendarHome.id():

                                calendar = (yield calendarHome.calendarWithName(calendarName))
                                if calendar is not None:
                                    yield calendarHome.setDefaultCalendar(
                                        calendar, tasks=(propname == customxml.ScheduleDefaultTasksURL)
                                    )

            # Always delete the rows so that batch processing works correctly
            yield Delete(
                From=rp,
                Where=(rp.RESOURCE_ID.In(Parameter("ids", len(delete_ids)))).And
                      (rp.NAME == PropertyName.fromElement(propname).toString()),
            ).on(sqlTxn, ids=delete_ids)

            yield sqlTxn.commit()

        yield cleanPropertyStore()

    except RuntimeError:
        f = Failure()
        yield sqlTxn.abort()
        f.raiseException()



@inlineCallbacks
def moveCalendarTranspProperties(sqlStore):
    """
    Need to move all the CalDAV:schedule-calendar-transp properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_BIND table columns, extracting
    the new value from the XML property.
    """

    cb = schema.CALENDAR_BIND
    rp = schema.RESOURCE_PROPERTY

    try:
        calendars_for_id = {}
        while True:
            sqlTxn = sqlStore.newTransaction()
            rows = (yield rowsForProperty(sqlTxn, caldavxml.ScheduleCalendarTransp, with_uid=True, batch=BATCH_SIZE))
            if len(rows) == 0:
                yield sqlTxn.commit()
                break
            delete_ids = []
            for calendar_rid, value, viewer in rows:
                delete_ids.append(calendar_rid)
                if calendar_rid not in calendars_for_id:
                    ids = yield Select(
                        [cb.CALENDAR_HOME_RESOURCE_ID, cb.BIND_MODE, ],
                        From=cb,
                        Where=cb.CALENDAR_RESOURCE_ID == calendar_rid,
                    ).on(sqlTxn)
                    calendars_for_id[calendar_rid] = ids

                if viewer:
                    calendarHome = (yield sqlTxn.calendarHomeWithUID(viewer))
                else:
                    calendarHome = None
                    for row in calendars_for_id[calendar_rid]:
                        home_id, bind_mode = row
                        if bind_mode == _BIND_MODE_OWN:
                            calendarHome = (yield sqlTxn.calendarHomeWithResourceID(home_id))
                            break

                if calendarHome is not None:
                    prop = WebDAVDocument.fromString(value).root_element
                    calendar = (yield calendarHome.childWithID(calendar_rid))
                    if calendar is not None:
                        yield calendar.setUsedForFreeBusy(prop == caldavxml.ScheduleCalendarTransp(caldavxml.Opaque()))

            # Always delete the rows so that batch processing works correctly
            yield Delete(
                From=rp,
                Where=(rp.RESOURCE_ID.In(Parameter("ids", len(delete_ids)))).And
                      (rp.NAME == PropertyName.fromElement(caldavxml.ScheduleCalendarTransp).toString()),
            ).on(sqlTxn, ids=delete_ids)

            yield sqlTxn.commit()

        sqlTxn = sqlStore.newTransaction()
        yield removeProperty(sqlTxn, PropertyName.fromElement(caldavxml.CalendarFreeBusySet))
        yield sqlTxn.commit()
        yield cleanPropertyStore()

    except RuntimeError:
        f = Failure()
        yield sqlTxn.abort()
        f.raiseException()



@inlineCallbacks
def moveDefaultAlarmProperties(sqlStore):
    """
    Need to move all the CalDAV:default-calendar and CS:default-tasks properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_HOME_METADATA table columns, extracting
    the new value from the XML property.
    """

    yield _processDefaultAlarmProperty(
        sqlStore,
        caldavxml.DefaultAlarmVEventDateTime,
        True,
        True,
    )
    yield _processDefaultAlarmProperty(
        sqlStore,
        caldavxml.DefaultAlarmVEventDate,
        True,
        False,
    )
    yield _processDefaultAlarmProperty(
        sqlStore,
        caldavxml.DefaultAlarmVToDoDateTime,
        False,
        True,
    )
    yield _processDefaultAlarmProperty(
        sqlStore,
        caldavxml.DefaultAlarmVToDoDate,
        False,
        False,
    )



@inlineCallbacks
def _processDefaultAlarmProperty(sqlStore, propname, vevent, timed):
    """
    Move the specified property value to the matching CALENDAR_HOME_METADATA or CALENDAR_BIND table column.

    Since the number of properties may well be large, we need to do this in batches.
    """

    hm = schema.CALENDAR_HOME_METADATA
    cb = schema.CALENDAR_BIND
    rp = schema.RESOURCE_PROPERTY

    try:
        calendars_for_id = {}
        while True:
            sqlTxn = sqlStore.newTransaction()
            rows = (yield rowsForProperty(sqlTxn, propname, with_uid=True, batch=BATCH_SIZE))
            if len(rows) == 0:
                yield sqlTxn.commit()
                break
            delete_ids = []
            for rid, value, viewer in rows:
                delete_ids.append(rid)

                prop = WebDAVDocument.fromString(value).root_element
                alarm = str(prop.children[0]) if prop.children else None

                # First check if the rid is a home - this is the most common case
                ids = yield Select(
                    [hm.RESOURCE_ID, ],
                    From=hm,
                    Where=hm.RESOURCE_ID == rid,
                ).on(sqlTxn)

                if len(ids) > 0:
                    # Home object
                    calendarHome = (yield sqlTxn.calendarHomeWithResourceID(ids[0][0]))
                    if calendarHome is not None:
                        yield calendarHome.setDefaultAlarm(alarm, vevent, timed)
                else:
                    # rid is a calendar - we need to find the per-user calendar for the resource viewer
                    if rid not in calendars_for_id:
                        ids = yield Select(
                            [cb.CALENDAR_HOME_RESOURCE_ID, cb.BIND_MODE, ],
                            From=cb,
                            Where=cb.CALENDAR_RESOURCE_ID == rid,
                        ).on(sqlTxn)
                        calendars_for_id[rid] = ids

                    if viewer:
                        calendarHome = (yield sqlTxn.calendarHomeWithUID(viewer))
                    else:
                        calendarHome = None
                        for row in calendars_for_id[rid]:
                            home_id, bind_mode = row
                            if bind_mode == _BIND_MODE_OWN:
                                calendarHome = (yield sqlTxn.calendarHomeWithResourceID(home_id))
                                break

                    if calendarHome is not None:
                        calendar = yield calendarHome.childWithID(rid)
                        if calendar is not None:
                            yield calendar.setDefaultAlarm(alarm, vevent, timed)

            # Always delete the rows so that batch processing works correctly
            yield Delete(
                From=rp,
                Where=(rp.RESOURCE_ID.In(Parameter("ids", len(delete_ids)))).And
                      (rp.NAME == PropertyName.fromElement(propname).toString()),
            ).on(sqlTxn, ids=delete_ids)

            yield sqlTxn.commit()

        yield cleanPropertyStore()

    except RuntimeError:
        f = Failure()
        yield sqlTxn.abort()
        f.raiseException()



@inlineCallbacks
def removeResourceType(sqlStore):
    sqlTxn = sqlStore.newTransaction()
    yield removeProperty(sqlTxn, PropertyName.fromElement(element.ResourceType))
    yield sqlTxn.commit()
    yield cleanPropertyStore()
