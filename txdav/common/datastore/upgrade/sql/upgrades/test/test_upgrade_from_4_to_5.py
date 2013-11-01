##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""

from twext.enterprise.dal.syntax import Update, Insert

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav import caldavxml, customxml
from twistedcaldav.config import config
from twistedcaldav.ical import Component

from txdav.base.propertystore.base import PropertyName
from txdav.caldav.datastore.test.util import CommonStoreTests
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE, schema
from txdav.common.datastore.upgrade.sql.upgrades.calendar_upgrade_from_4_to_5 import updateCalendarHomes, doUpgrade
from txdav.xml import element

class Upgrade_from_4_to_5(CommonStoreTests):
    """
    Tests for L{DefaultCalendarPropertyUpgrade}.
    """

    @inlineCallbacks
    def _calendarTimezoneUpgrade_setup(self):

        tz1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//calendarserver.org//Zonal//EN
BEGIN:VTIMEZONE
TZID:Etc/GMT+1
X-LIC-LOCATION:Etc/GMT+1
BEGIN:STANDARD
DTSTART:18000101T000000
RDATE:18000101T000000
TZNAME:GMT+1
TZOFFSETFROM:-0100
TZOFFSETTO:-0100
END:STANDARD
END:VTIMEZONE
END:VCALENDAR
""")
        tz2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//calendarserver.org//Zonal//EN
BEGIN:VTIMEZONE
TZID:Etc/GMT+2
X-LIC-LOCATION:Etc/GMT+2
BEGIN:STANDARD
DTSTART:18000101T000000
RDATE:18000101T000000
TZNAME:GMT+2
TZOFFSETFROM:-0200
TZOFFSETTO:-0200
END:STANDARD
END:VTIMEZONE
END:VCALENDAR
""")
        tz3 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//calendarserver.org//Zonal//EN
BEGIN:VTIMEZONE
TZID:Etc/GMT+3
X-LIC-LOCATION:Etc/GMT+3
BEGIN:STANDARD
DTSTART:18000101T000000
RDATE:18000101T000000
TZNAME:GMT+3
TZOFFSETFROM:-0300
TZOFFSETTO:-0300
END:STANDARD
END:VTIMEZONE
END:VCALENDAR
""")

        # Share user01 calendar with user03
        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        home3 = yield self.homeUnderTest(name="user03")
        shared_name = yield calendar.shareWith(home3, _BIND_MODE_WRITE)

        user_details = (
            ("user01", "calendar_1", tz1),
            ("user02", "calendar_1", tz2),
            ("user03", "calendar_1", None),
            ("user03", shared_name, tz3),
        )

        # Set dead properties on calendars
        for user, calname, tz in user_details:
            calendar = (yield self.calendarUnderTest(name=calname, home=user))
            if tz:
                calendar.properties()[PropertyName.fromElement(caldavxml.CalendarTimeZone)] = caldavxml.CalendarTimeZone.fromString(str(tz))

            # Force data version to previous
            home = (yield self.homeUnderTest(name=user))
            ch = home._homeSchema
            yield Update(
                {ch.DATAVERSION: 4},
                Where=ch.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

        yield self.commit()

        for user, calname, tz in user_details:
            calendar = (yield self.calendarUnderTest(name=calname, home=user))
            self.assertEqual(calendar.getTimezone(), None)
            self.assertEqual(PropertyName.fromElement(caldavxml.CalendarTimeZone) in calendar.properties(), tz is not None)
        yield self.commit()

        # Create "fake" entry for non-existent share
        txn = self.transactionUnderTest()
        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        rp = schema.RESOURCE_PROPERTY
        yield Insert(
            {
                rp.RESOURCE_ID: calendar._resourceID,
                rp.NAME: PropertyName.fromElement(caldavxml.CalendarTimeZone).toString(),
                rp.VALUE: caldavxml.CalendarTimeZone.fromString(str(tz3)).toxml(),
                rp.VIEWER_UID: "user04",
            }
        ).on(txn)
        yield self.commit()

        returnValue(user_details)


    @inlineCallbacks
    def _calendarTimezoneUpgrade_check(self, changed_users, unchanged_users, user_details):

        # Test results
        for user, calname, tz in user_details:
            if user in changed_users:
                home = (yield self.homeUnderTest(name=user))
                version = (yield home.dataVersion())
                self.assertEqual(version, 5)
                calendar = (yield self.calendarUnderTest(name=calname, home=user))
                self.assertEqual(calendar.getTimezone(), tz)
                self.assertTrue(PropertyName.fromElement(caldavxml.CalendarTimeZone) not in calendar.properties())
            else:
                home = (yield self.homeUnderTest(name=user))
                version = (yield home.dataVersion())
                self.assertEqual(version, 4)
                calendar = (yield self.calendarUnderTest(name=calname, home=user))
                self.assertEqual(calendar.getTimezone(), None)
                if tz:
                    self.assertTrue(PropertyName.fromElement(caldavxml.CalendarTimeZone) in calendar.properties())
                else:
                    self.assertTrue(PropertyName.fromElement(caldavxml.CalendarTimeZone) not in calendar.properties())


    @inlineCallbacks
    def test_calendarTimezoneUpgrade(self):
        user_details = yield self._calendarTimezoneUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore)
        yield self._calendarTimezoneUpgrade_check(("user01", "user02", "user03",), (), user_details)


    @inlineCallbacks
    def test_partialCalendarTimezoneUpgrade(self):
        user_details = yield self._calendarTimezoneUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore, "user01")
        yield self._calendarTimezoneUpgrade_check(("user01",), ("user02", "user03",), user_details)


    @inlineCallbacks
    def _calendarAvailabilityUpgrade_setup(self):

        av1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//calendarserver.org//Zonal//EN
BEGIN:VAVAILABILITY
ORGANIZER:mailto:user01@example.com
UID:1@example.com
DTSTAMP:20061005T133225Z
DTEND:20140101T000000Z
BEGIN:AVAILABLE
UID:1-1@example.com
DTSTAMP:20061005T133225Z
SUMMARY:Monday to Friday from 9:00 to 17:00
DTSTART:20130101T090000Z
DTEND:20130101T170000Z
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
END:AVAILABLE
END:VAVAILABILITY
END:VCALENDAR
""")
        av2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//calendarserver.org//Zonal//EN
BEGIN:VAVAILABILITY
ORGANIZER:mailto:user02@example.com
UID:2@example.com
DTSTAMP:20061005T133225Z
DTEND:20140101T000000Z
BEGIN:AVAILABLE
UID:2-1@example.com
DTSTAMP:20061005T133225Z
SUMMARY:Monday to Friday from 12:00 to 17:00
DTSTART:20130101T120000Z
DTEND:20130101T170000Z
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
END:AVAILABLE
END:VAVAILABILITY
END:VCALENDAR
""")

        user_details = (
            ("user01", av1),
            ("user02", av2),
            ("user03", None),
        )

        # Set dead properties on calendars
        for user, av in user_details:
            calendar = (yield self.calendarUnderTest(name="inbox", home=user))
            if av:
                calendar.properties()[PropertyName.fromElement(customxml.CalendarAvailability)] = customxml.CalendarAvailability.fromString(str(av))

            # Force data version to previous
            home = (yield self.homeUnderTest(name=user))
            ch = home._homeSchema
            yield Update(
                {ch.DATAVERSION: 4},
                Where=ch.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

        yield self.commit()

        for user, av in user_details:
            home = (yield self.homeUnderTest(name=user))
            calendar = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertEqual(home.getAvailability(), None)
            self.assertEqual(PropertyName.fromElement(customxml.CalendarAvailability) in calendar.properties(), av is not None)
        yield self.commit()

        returnValue(user_details)


    @inlineCallbacks
    def _calendarAvailabilityUpgrade_check(self, changed_users, unchanged_users, user_details):

        # Test results
        for user, av in user_details:
            if user in changed_users:
                home = (yield self.homeUnderTest(name=user))
                version = (yield home.dataVersion())
                self.assertEqual(version, 5)
                calendar = (yield self.calendarUnderTest(name="inbox", home=user))
                self.assertEqual(home.getAvailability(), av)
                self.assertTrue(PropertyName.fromElement(customxml.CalendarAvailability) not in calendar.properties())
            else:
                home = (yield self.homeUnderTest(name=user))
                version = (yield home.dataVersion())
                self.assertEqual(version, 4)
                calendar = (yield self.calendarUnderTest(name="inbox", home=user))
                self.assertEqual(home.getAvailability(), None)
                if av:
                    self.assertTrue(PropertyName.fromElement(customxml.CalendarAvailability) in calendar.properties())
                else:
                    self.assertTrue(PropertyName.fromElement(customxml.CalendarAvailability) not in calendar.properties())


    @inlineCallbacks
    def test_calendarAvailabilityUpgrade(self):
        user_details = yield self._calendarAvailabilityUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore)
        yield self._calendarAvailabilityUpgrade_check(("user01", "user02", "user03",), (), user_details)


    @inlineCallbacks
    def test_partialCalendarAvailabilityUpgrade(self):
        user_details = yield self._calendarAvailabilityUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore, "user01")
        yield self._calendarAvailabilityUpgrade_check(("user01",), ("user02", "user03",), user_details)


    @inlineCallbacks
    def test_combinedUpgrade(self):
        user_details1 = yield self._calendarTimezoneUpgrade_setup()
        user_details2 = yield self._calendarAvailabilityUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore)
        yield self._calendarTimezoneUpgrade_check(("user01", "user02", "user03",), (), user_details1)
        yield self._calendarAvailabilityUpgrade_check(("user01", "user02", "user03",), (), user_details2)


    @inlineCallbacks
    def test_partialCombinedUpgrade(self):
        user_details1 = yield self._calendarTimezoneUpgrade_setup()
        user_details2 = yield self._calendarAvailabilityUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore, "user01")
        yield self._calendarTimezoneUpgrade_check(("user01",), ("user02", "user03",), user_details1)
        yield self._calendarAvailabilityUpgrade_check(("user01",), ("user02", "user03",), user_details2)


    @inlineCallbacks
    def _removeOtherPropertiesUpgrade_setup(self):

        # Set dead property on calendar
        for user in ("user01", "user02",):
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            calendar.properties()[PropertyName.fromElement(element.ResourceID)] = element.ResourceID(element.HRef("urn:uuid:%s" % (user,)))
        yield self.commit()

        for user in ("user01", "user02",):
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertTrue(PropertyName.fromElement(element.ResourceID) in calendar.properties())

        yield self.transactionUnderTest().updateCalendarserverValue("CALENDAR-DATAVERSION", "4")

        yield self.commit()


    @inlineCallbacks
    def _removeOtherPropertiesUpgrade_check(self, full=True):

        # Test results
        for user in ("user01", "user02",):
            if full:
                calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
                self.assertTrue(PropertyName.fromElement(element.ResourceID) not in calendar.properties())
                version = yield self.transactionUnderTest().calendarserverValue("CALENDAR-DATAVERSION")
                self.assertEqual(int(version), 5)
            else:
                calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
                self.assertTrue(PropertyName.fromElement(element.ResourceID) in calendar.properties())
                version = yield self.transactionUnderTest().calendarserverValue("CALENDAR-DATAVERSION")
                self.assertEqual(int(version), 4)


    @inlineCallbacks
    def test_removeOtherPropertiesUpgrade(self):
        yield self._removeOtherPropertiesUpgrade_setup()
        yield doUpgrade(self._sqlCalendarStore)
        yield self._removeOtherPropertiesUpgrade_check()


    @inlineCallbacks
    def test_fullUpgrade(self):
        self.patch(config, "UpgradeHomePrefix", "")
        user_details1 = yield self._calendarTimezoneUpgrade_setup()
        user_details2 = yield self._calendarAvailabilityUpgrade_setup()
        yield self._removeOtherPropertiesUpgrade_setup()
        yield doUpgrade(self._sqlCalendarStore)
        yield self._calendarTimezoneUpgrade_check(("user01", "user02", "user03",), (), user_details1)
        yield self._calendarAvailabilityUpgrade_check(("user01", "user02", "user03",), (), user_details2)
        yield self._removeOtherPropertiesUpgrade_check()


    @inlineCallbacks
    def test_partialFullUpgrade(self):
        self.patch(config, "UpgradeHomePrefix", "user01")
        user_details1 = yield self._calendarTimezoneUpgrade_setup()
        user_details2 = yield self._calendarAvailabilityUpgrade_setup()
        yield self._removeOtherPropertiesUpgrade_setup()
        yield doUpgrade(self._sqlCalendarStore)
        yield self._calendarTimezoneUpgrade_check(("user01",), ("user02", "user03",), user_details1)
        yield self._calendarAvailabilityUpgrade_check(("user01",), ("user02", "user03",), user_details2)
        yield self._removeOtherPropertiesUpgrade_check(False)
