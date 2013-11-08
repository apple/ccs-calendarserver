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

from twisted.internet.defer import inlineCallbacks

from twistedcaldav import caldavxml, customxml

from txdav.base.propertystore.base import PropertyName
from txdav.caldav.icalendarstore import InvalidDefaultCalendar
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.upgrade.sql.upgrades.util import updateCalendarDataVersion, \
    removeProperty, cleanPropertyStore, logUpgradeStatus, doToEachHomeNotAtVersion
from txdav.xml import element
from twistedcaldav.config import config

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
    yield updateCalendarHomes(sqlStore, config.UpgradeHomePrefix)

    # Don't do remaining upgrade if we are only process a subset of the homes
    if not config.UpgradeHomePrefix:
        yield removeResourceType(sqlStore)

        # Always bump the DB value
        yield updateCalendarDataVersion(sqlStore, UPGRADE_TO_VERSION)



@inlineCallbacks
def updateCalendarHomes(sqlStore, prefix=None):
    """
    For each calendar home, update the associated properties on the home or its owned calendars.
    """

    yield doToEachHomeNotAtVersion(sqlStore, schema.CALENDAR_HOME, UPGRADE_TO_VERSION, updateCalendarHome, "Update Calendar Home", filterOwnerUID=prefix)



@inlineCallbacks
def updateCalendarHome(txn, homeResourceID):
    """
    For this calendar home, update the associated properties on the home or its owned calendars.
    """

    home = yield txn.calendarHomeWithResourceID(homeResourceID)
    yield moveDefaultCalendarProperties(home)
    yield moveCalendarTranspProperties(home)
    yield moveDefaultAlarmProperties(home)
    yield cleanPropertyStore()



@inlineCallbacks
def moveDefaultCalendarProperties(home):
    """
    Need to move any the CalDAV:default-calendar and CS:default-tasks properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_HOME_METADATA table columns, extracting
    the new value from the XML property.
    """

    yield _processDefaultCalendarProperty(home, caldavxml.ScheduleDefaultCalendarURL)
    yield _processDefaultCalendarProperty(home, customxml.ScheduleDefaultTasksURL)



@inlineCallbacks
def _processDefaultCalendarProperty(home, propname):
    """
    Move the specified property value to the matching CALENDAR_HOME_METADATA table column.
    """

    inbox = (yield home.calendarWithName("inbox"))
    if inbox is not None:
        prop = inbox.properties().get(PropertyName.fromElement(propname))
        if prop is not None:
            defaultCalendar = str(prop.children[0])
            parts = defaultCalendar.split("/")
            if len(parts) == 5:

                calendarName = parts[-1]
                calendarHomeUID = parts[-2]
                if calendarHomeUID == home.uid():

                    calendar = (yield home.calendarWithName(calendarName))
                    if calendar is not None:
                        try:
                            if propname == caldavxml.ScheduleDefaultCalendarURL:
                                ctype = "VEVENT"
                            elif propname == customxml.ScheduleDefaultTasksURL:
                                ctype = "VTODO"
                            yield home.setDefaultCalendar(
                                calendar, ctype
                            )
                        except InvalidDefaultCalendar:
                            # Ignore these - the server will recover
                            pass

            del inbox.properties()[PropertyName.fromElement(propname)]



@inlineCallbacks
def moveCalendarTranspProperties(home):
    """
    Need to move all the CalDAV:schedule-calendar-transp properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_BIND table columns, extracting
    the new value from the XML property.
    """

    # Iterate over each calendar (both owned and shared)
    calendars = (yield home.loadChildren())
    for calendar in calendars:
        if calendar.isInbox():
            prop = calendar.properties().get(PropertyName.fromElement(caldavxml.CalendarFreeBusySet))
            if prop is not None:
                del calendar.properties()[PropertyName.fromElement(caldavxml.CalendarFreeBusySet)]
        prop = calendar.properties().get(PropertyName.fromElement(caldavxml.ScheduleCalendarTransp))
        if prop is not None:
            yield calendar.setUsedForFreeBusy(prop == caldavxml.ScheduleCalendarTransp(caldavxml.Opaque()))
            del calendar.properties()[PropertyName.fromElement(caldavxml.ScheduleCalendarTransp)]



@inlineCallbacks
def moveDefaultAlarmProperties(home):
    """
    Need to move all the CalDAV:default-calendar and CS:default-tasks properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_HOME_METADATA table columns, extracting
    the new value from the XML property.
    """

    yield _processDefaultAlarmProperty(
        home,
        caldavxml.DefaultAlarmVEventDateTime,
        True,
        True,
    )
    yield _processDefaultAlarmProperty(
        home,
        caldavxml.DefaultAlarmVEventDate,
        True,
        False,
    )
    yield _processDefaultAlarmProperty(
        home,
        caldavxml.DefaultAlarmVToDoDateTime,
        False,
        True,
    )
    yield _processDefaultAlarmProperty(
        home,
        caldavxml.DefaultAlarmVToDoDate,
        False,
        False,
    )



@inlineCallbacks
def _processDefaultAlarmProperty(home, propname, vevent, timed):
    """
    Move the specified property value to the matching CALENDAR_HOME_METADATA or CALENDAR_BIND table column.

    Since the number of properties may well be large, we need to do this in batches.
    """

    # Check the home first
    prop = home.properties().get(PropertyName.fromElement(propname))
    if prop is not None:
        alarm = str(prop.children[0]) if prop.children else None
        yield home.setDefaultAlarm(alarm, vevent, timed)
        del home.properties()[PropertyName.fromElement(propname)]

    # Now each child
    calendars = (yield home.loadChildren())
    for calendar in calendars:
        if calendar.isInbox():
            continue
        prop = calendar.properties().get(PropertyName.fromElement(propname))
        if prop is not None:
            alarm = str(prop.children[0]) if prop.children else None
            yield calendar.setDefaultAlarm(alarm, vevent, timed)
            del calendar.properties()[PropertyName.fromElement(propname)]



@inlineCallbacks
def removeResourceType(sqlStore):
    logUpgradeStatus("Starting Calendar Remove Resource Type")

    sqlTxn = sqlStore.newTransaction()
    yield removeProperty(sqlTxn, PropertyName.fromElement(element.ResourceType))
    yield sqlTxn.commit()
    yield cleanPropertyStore()

    logUpgradeStatus("End Calendar Remove Resource Type")
