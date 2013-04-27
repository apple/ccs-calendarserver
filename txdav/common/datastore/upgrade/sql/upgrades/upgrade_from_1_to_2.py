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

from twext.enterprise.dal.syntax import Update
from txdav.xml.parser import WebDAVDocument
from twisted.internet.defer import inlineCallbacks
from twistedcaldav import caldavxml
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.upgrade.sql.upgrades.util import rowsForProperty,\
    removeProperty, updateDataVersion, doToEachCalendarHomeNotAtVersion

"""
Data upgrade from database version 1 to 2
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
    yield updateDataVersion(sqlStore, "CALENDAR-DATAVERSION", UPGRADE_TO_VERSION)



@inlineCallbacks
def moveSupportedComponentSetProperties(sqlStore):
    """
    Need to move all the CalDAV:supported-component-set properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_METADATA table column,
    extracting the new format value from the XML property.
    """

    sqlTxn = sqlStore.newTransaction()
    try:
        rows = (yield rowsForProperty(sqlTxn, caldavxml.SupportedCalendarComponentSet))
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

        yield removeProperty(sqlTxn, caldavxml.SupportedCalendarComponentSet)
        yield sqlTxn.commit()
    except RuntimeError:
        yield sqlTxn.abort()
        raise



@inlineCallbacks
def splitCalendars(sqlStore):
    """
    Split all calendars by component type.
    """

    @inlineCallbacks
    def doIt(home):
        """
        Split each regular calendar in the home.
        """
        yield home.splitCalendars()

    # Do this to each calendar home not already at version 2
    yield doToEachCalendarHomeNotAtVersion(sqlStore, UPGRADE_TO_VERSION, doIt)
