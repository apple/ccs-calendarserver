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

from twext.enterprise.dal.syntax import Update, Select, Delete, Parameter

from twisted.internet.defer import inlineCallbacks

from twistedcaldav import caldavxml, customxml

from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.upgrade.sql.upgrades.util import rowsForProperty, updateDataVersion
from txdav.xml.parser import WebDAVDocument

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

    # Always bump the DB value
    yield updateDataVersion(sqlStore, "CALENDAR-DATAVERSION", UPGRADE_TO_VERSION)



@inlineCallbacks
def moveDefaultCalendarProperties(sqlStore):
    """
    Need to move all the CalDAV:default-calendar and CS:default-tasks properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_HOME_METADATA table columns, extracting
    the new value from the XML property.
    """

    meta = schema.CALENDAR_HOME_METADATA
    yield _processProperty(sqlStore, caldavxml.ScheduleDefaultCalendarURL, meta.DEFAULT_EVENTS)
    yield _processProperty(sqlStore, customxml.ScheduleDefaultTasksURL, meta.DEFAULT_TASKS)



@inlineCallbacks
def _processProperty(sqlStore, propname, colname):
    """
    Move the specified property value to the matching CALENDAR_HOME_METADATA table column.

    Since the number of calendar homes may well be large, we need to do this in batches.
    """

    meta = schema.CALENDAR_HOME_METADATA
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

                                    yield Update(
                                        {colname : calendar.id(), },
                                        Where=(meta.RESOURCE_ID == calendarHome.id())
                                    ).on(sqlTxn)

                # Always delete the row so that batch processing works correctly
                yield Delete(
                    From=rp,
                    Where=(rp.RESOURCE_ID.In(Parameter("ids", len(delete_ids)))).And
                          (rp.NAME == PropertyName.fromElement(propname).toString()),
                ).on(sqlTxn, ids=delete_ids)

            yield sqlTxn.commit()

    except RuntimeError:
        yield sqlTxn.abort()
        raise
