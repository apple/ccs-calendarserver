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

from txweb2.dav.resource import TwistedQuotaUsedProperty, TwistedGETContentMD5

from twisted.internet.defer import inlineCallbacks

from twistedcaldav import caldavxml, customxml
from twistedcaldav.config import config

from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.upgrade.sql.upgrades.util import updateCalendarDataVersion, \
    removeProperty, cleanPropertyStore, logUpgradeStatus, doToEachHomeNotAtVersion
from txdav.xml import element

"""
Data upgrade from database version 4 to 5
"""

UPGRADE_TO_VERSION = 5
BATCH_SIZE = 100

@inlineCallbacks
def doUpgrade(sqlStore):
    """
    Do the required upgrade steps.
    """
    yield updateCalendarHomes(sqlStore, config.UpgradeHomePrefix)

    # Don't do remaining upgrade if we are only process a subset of the homes
    if not config.UpgradeHomePrefix:
        yield removeOtherProperties(sqlStore)

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
    yield moveCalendarTimezoneProperties(home)
    yield moveCalendarAvailabilityProperties(home)
    yield cleanPropertyStore()



@inlineCallbacks
def moveCalendarTimezoneProperties(home):
    """
    Need to move all the CalDAV:calendar-timezone properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_BIND table columns, extracting
    the new value from the XML property.
    """

    # Iterate over each calendar (both owned and shared)
    calendars = (yield home.loadChildren())
    for calendar in calendars:
        if calendar.isInbox():
            continue
        prop = calendar.properties().get(PropertyName.fromElement(caldavxml.CalendarTimeZone))
        if prop is not None:
            yield calendar.setTimezone(prop.calendar())
            del calendar.properties()[PropertyName.fromElement(caldavxml.CalendarTimeZone)]



@inlineCallbacks
def moveCalendarAvailabilityProperties(home):
    """
    Need to move all the CS:calendar-availability properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_BIND table columns, extracting
    the new value from the XML property.
    """
    inbox = (yield home.calendarWithName("inbox"))
    if inbox is not None:
        prop = inbox.properties().get(PropertyName.fromElement(customxml.CalendarAvailability))
        if prop is not None:
            yield home.setAvailability(prop.calendar())
            del inbox.properties()[PropertyName.fromElement(customxml.CalendarAvailability)]



@inlineCallbacks
def removeOtherProperties(sqlStore):
    """
    Remove the following properties:

    DAV:acl
    DAV:getcontenttype
    DAV:resource-id
    {urn:ietf:params:xml:ns:caldav}originator
    {urn:ietf:params:xml:ns:caldav}recipient
    {urn:ietf:params:xml:ns:caldav}supported-calendar-component-set
    {http://calendarserver.org/ns/}getctag
    {http://twistedmatrix.com/xml_namespace/dav/private/}quota-used
    {http://twistedmatrix.com/xml_namespace/dav/}getcontentmd5
    {http://twistedmatrix.com/xml_namespace/dav/}schedule-auto-respond

    """
    logUpgradeStatus("Starting Calendar Remove Other Properties")

    sqlTxn = sqlStore.newTransaction()

    yield removeProperty(sqlTxn, PropertyName.fromElement(element.ACL))
    yield removeProperty(sqlTxn, PropertyName.fromElement(element.GETContentType))
    yield removeProperty(sqlTxn, PropertyName.fromElement(element.ResourceID))
    yield removeProperty(sqlTxn, PropertyName(caldavxml.caldav_namespace, "originator"))
    yield removeProperty(sqlTxn, PropertyName(caldavxml.caldav_namespace, "recipient"))
    yield removeProperty(sqlTxn, PropertyName.fromElement(caldavxml.SupportedCalendarComponentSet))
    yield removeProperty(sqlTxn, PropertyName.fromElement(customxml.GETCTag))
    yield removeProperty(sqlTxn, PropertyName.fromElement(TwistedQuotaUsedProperty))
    yield removeProperty(sqlTxn, PropertyName.fromElement(TwistedGETContentMD5))
    yield removeProperty(sqlTxn, PropertyName(element.twisted_dav_namespace, "schedule-auto-respond"))

    yield sqlTxn.commit()
    yield cleanPropertyStore()

    logUpgradeStatus("End Calendar Remove Other Properties")
