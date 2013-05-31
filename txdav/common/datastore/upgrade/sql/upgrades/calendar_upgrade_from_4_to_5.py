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
from twisted.python.failure import Failure

from twistedcaldav import caldavxml, customxml

from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.sql_tables import schema, _BIND_MODE_OWN
from txdav.common.datastore.upgrade.sql.upgrades.util import rowsForProperty, updateCalendarDataVersion, \
    updateAllCalendarHomeDataVersions, removeProperty, cleanPropertyStore
from txdav.xml import element
from txdav.xml.parser import WebDAVDocument
from twext.web2.dav.resource import TwistedQuotaUsedProperty, \
    TwistedGETContentMD5

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
    yield moveCalendarTimezoneProperties(sqlStore)
    yield moveCalendarAvailabilityProperties(sqlStore)
    yield removeOtherProperties(sqlStore)

    # Always bump the DB value
    yield updateCalendarDataVersion(sqlStore, UPGRADE_TO_VERSION)
    yield updateAllCalendarHomeDataVersions(sqlStore, UPGRADE_TO_VERSION)



@inlineCallbacks
def moveCalendarTimezoneProperties(sqlStore):
    """
    Need to move all the CalDAV:calendar-timezone properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_BIND table columns, extracting
    the new value from the XML property.
    """

    cb = schema.CALENDAR_BIND
    rp = schema.RESOURCE_PROPERTY

    try:
        calendars_for_id = {}
        while True:
            sqlTxn = sqlStore.newTransaction()
            rows = (yield rowsForProperty(sqlTxn, caldavxml.CalendarTimeZone, with_uid=True, batch=BATCH_SIZE))
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
                    yield calendar.setTimezone(prop.calendar())

            # Always delete the rows so that batch processing works correctly
            yield Delete(
                From=rp,
                Where=(rp.RESOURCE_ID.In(Parameter("ids", len(delete_ids)))).And
                      (rp.NAME == PropertyName.fromElement(caldavxml.CalendarTimeZone).toString()),
            ).on(sqlTxn, ids=delete_ids)

            yield sqlTxn.commit()

        yield cleanPropertyStore()

    except RuntimeError:
        f = Failure()
        yield sqlTxn.abort()
        f.raiseException()



@inlineCallbacks
def moveCalendarAvailabilityProperties(sqlStore):
    """
    Need to move all the CS:calendar-availability properties in the
    RESOURCE_PROPERTY table to the new CALENDAR_BIND table columns, extracting
    the new value from the XML property.
    """

    cb = schema.CALENDAR_BIND
    rp = schema.RESOURCE_PROPERTY

    try:
        while True:
            sqlTxn = sqlStore.newTransaction()
            rows = (yield rowsForProperty(sqlTxn, customxml.CalendarAvailability, batch=BATCH_SIZE))
            if len(rows) == 0:
                yield sqlTxn.commit()
                break

            # Map each calendar to a home id using a single query for efficiency
            calendar_ids = [row[0] for row in rows]

            home_map = yield Select(
                [cb.CALENDAR_RESOURCE_ID, cb.CALENDAR_HOME_RESOURCE_ID, ],
                From=cb,
                Where=(cb.CALENDAR_RESOURCE_ID.In(Parameter("ids", len(calendar_ids)))).And(cb.BIND_MODE == _BIND_MODE_OWN),
            ).on(sqlTxn, ids=calendar_ids)
            calendar_to_home = dict(home_map)

            # Move property to each home
            for calendar_rid, value in rows:
                if calendar_rid in calendar_to_home:
                    calendarHome = (yield sqlTxn.calendarHomeWithResourceID(calendar_to_home[calendar_rid]))

                    if calendarHome is not None:
                        prop = WebDAVDocument.fromString(value).root_element
                        yield calendarHome.setAvailability(prop.calendar())

            # Always delete the rows so that batch processing works correctly
            yield Delete(
                From=rp,
                Where=(rp.RESOURCE_ID.In(Parameter("ids", len(calendar_ids)))).And
                      (rp.NAME == PropertyName.fromElement(customxml.CalendarAvailability).toString()),
            ).on(sqlTxn, ids=calendar_ids)

            yield sqlTxn.commit()

        yield cleanPropertyStore()

    except RuntimeError:
        f = Failure()
        yield sqlTxn.abort()
        f.raiseException()



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
