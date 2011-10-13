# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
from twext.web2.dav.element.parser import WebDAVDocument
from twisted.internet.defer import inlineCallbacks
from twistedcaldav import caldavxml
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.upgrade.sql.util import rowsForProperty,\
    removeProperty

"""
Data upgrade from database version 5 to 6
"""

@inlineCallbacks
def doUpgrade(sqlTxn):
    """
    Need to move all the CalDAV:supported-component-set properties in the RESOURCE_PROPERTY
    table to the new CALENDAR table column, extracting the new format value from the XML property.
    """

    rows = (yield rowsForProperty(sqlTxn, caldavxml.SupportedCalendarComponentSet))
    for calendar_rid, value in rows:
        prop = WebDAVDocument.fromString(value).root_element
        supported_components = ",".join(sorted([comp.attributes["name"].upper() for comp in prop.children]))

        cal = schema.CALENDAR
        yield Update(
            {
                cal.SUPPORTED_COMPONENTS : supported_components
            },
            Where=(cal.RESOURCE_ID == calendar_rid)
        ).on(sqlTxn)

    yield removeProperty(sqlTxn, caldavxml.SupportedCalendarComponentSet)
