# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Update

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav import caldavxml

from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.upgrade.sql.upgrades.util import rowsForProperty,\
    removeProperty, updateCalendarDataVersion, doToEachHomeNotAtVersion, \
    logUpgradeStatus, logUpgradeError
from txdav.xml.parser import WebDAVDocument

"""
Calendar data upgrade from database version 1 to 2
"""

UPGRADE_TO_VERSION = 2

@inlineCallbacks
def doUpgrade(sqlStore):
    """
    Do the required upgrade steps.
    """
    yield moveSupportedComponentSetProperties(sqlStore)
    yield splitCalendars(sqlStore)

    # Always bump the DB value
    yield updateCalendarDataVersion(sqlStore, UPGRADE_TO_VERSION)



@inlineCallbacks
def moveSupportedComponentSetProperties(sqlStore):
    """
    Need to move all the CalDAV:supported-component-set properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_METADATA table column,
    extracting the new format value from the XML property.
    """

    logUpgradeStatus("Starting Move supported-component-set")

    sqlTxn = sqlStore.newTransaction()
    try:
        # Do not move the properties if migrating, as migration will do a split and set supported-components,
        # however we still need to remove the old properties.
        if not sqlStore._migrating:
            calendar_rid = None
            rows = (yield rowsForProperty(sqlTxn, caldavxml.SupportedCalendarComponentSet))
            total = len(rows)
            count = 0
            for calendar_rid, value in rows:
                prop = WebDAVDocument.fromString(value).root_element
                supported_components = ",".join(sorted([comp.attributes["name"].upper() for comp in prop.children]))
                meta = schema.CALENDAR_METADATA
                yield Update(
                    {
                        meta.SUPPORTED_COMPONENTS : supported_components
                    },
                    Where=(meta.RESOURCE_ID == calendar_rid)
                ).on(sqlTxn)
                count += 1
                logUpgradeStatus("Move supported-component-set", count, total)

        yield removeProperty(sqlTxn, caldavxml.SupportedCalendarComponentSet)
        yield sqlTxn.commit()

        logUpgradeStatus("End Move supported-component-set")
    except RuntimeError:
        yield sqlTxn.abort()
        logUpgradeError(
            "Move supported-component-set",
            "Last calendar: {}".format(calendar_rid)
        )
        raise



@inlineCallbacks
def splitCalendars(sqlStore):
    """
    Split all calendars by component type.
    """

    # This is already done when doing file->sql migration
    if sqlStore._migrating:
        returnValue(None)


    @inlineCallbacks
    def doIt(txn, homeResourceID):
        """
        Split each regular calendar in the home.
        """
        home = yield txn.calendarHomeWithResourceID(homeResourceID)
        yield home.splitCalendars()

    logUpgradeStatus("Starting Split Calendars")

    # Do this to each calendar home not already at version 2
    yield doToEachHomeNotAtVersion(sqlStore, schema.CALENDAR_HOME, UPGRADE_TO_VERSION, doIt, "Split Calendars")
