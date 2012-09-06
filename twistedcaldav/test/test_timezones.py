##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

import twistedcaldav.test.util
from twistedcaldav.ical import Component
from twistedcaldav.timezones import TimezoneCache, TimezoneException
from twistedcaldav.timezones import readTZ, listTZs
from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone

import os

class TimezoneProblemTest (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

    data_dir = os.path.join(os.path.dirname(__file__), "data")

    def tearDown(self):
        TimezoneCache.clear()
        TimezoneCache.create()
        
    def doTest(self, filename, dtstart, dtend, testEqual=True):
        
        if testEqual:
            testMethod = self.assertEqual
        else:
            testMethod = self.assertNotEqual

        calendar = Component.fromStream(file(os.path.join(self.data_dir, filename)))
        if calendar.name() != "VCALENDAR": self.fail("Calendar is not a VCALENDAR")

        instances = calendar.expandTimeRanges(PyCalendarDateTime(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            testMethod(start, dtstart)
            testMethod(end, dtend)
            break;

    def test_truncatedApr(self):
        """
        Properties in components
        """
        
        TimezoneCache.create("")
        TimezoneCache.clear()

        self.doTest(
            "TruncatedApr01.ics",
            PyCalendarDateTime(2007, 04, 01, 16, 0, 0, PyCalendarTimezone(utc=True)),
            PyCalendarDateTime(2007, 04, 01, 17, 0, 0, PyCalendarTimezone(utc=True))
        )

    def test_truncatedDec(self):
        """
        Properties in components
        """
        TimezoneCache.create("")
        TimezoneCache.clear()

        self.doTest(
            "TruncatedDec10.ics",
            PyCalendarDateTime(2007, 12, 10, 17, 0, 0, PyCalendarTimezone(utc=True)),
            PyCalendarDateTime(2007, 12, 10, 18, 0, 0, PyCalendarTimezone(utc=True))
        )

    def test_truncatedAprThenDecFail(self):
        """
        Properties in components
        """

        TimezoneCache.create("")
        TimezoneCache.clear()

        self.doTest(
            "TruncatedApr01.ics",
            PyCalendarDateTime(2007, 04, 01, 16, 0, 0, PyCalendarTimezone(utc=True)),
            PyCalendarDateTime(2007, 04, 01, 17, 0, 0, PyCalendarTimezone(utc=True)),
        )
        self.doTest(
            "TruncatedDec10.ics",
            PyCalendarDateTime(2007, 12, 10, 17, 0, 0, PyCalendarTimezone(utc=True)),
            PyCalendarDateTime(2007, 12, 10, 18, 0, 0, PyCalendarTimezone(utc=True)),
            testEqual=False
        )

    def test_truncatedAprThenDecOK(self):
        """
        Properties in components
        """
        TimezoneCache.create()

        self.doTest(
            "TruncatedApr01.ics",
            PyCalendarDateTime(2007, 04, 01, 16, 0, 0, PyCalendarTimezone(utc=True)),
            PyCalendarDateTime(2007, 04, 01, 17, 0, 0, PyCalendarTimezone(utc=True)),
        )
        self.doTest(
            "TruncatedDec10.ics",
            PyCalendarDateTime(2007, 12, 10, 17, 0, 0, PyCalendarTimezone(utc=True)),
            PyCalendarDateTime(2007, 12, 10, 18, 0, 0, PyCalendarTimezone(utc=True)),
        )

    def test_truncatedDecThenApr(self):
        """
        Properties in components
        """
        TimezoneCache.create("")
        TimezoneCache.clear()

        self.doTest(
            "TruncatedDec10.ics",
            PyCalendarDateTime(2007, 12, 10, 17, 0, 0, PyCalendarTimezone(utc=True)),
            PyCalendarDateTime(2007, 12, 10, 18, 0, 0, PyCalendarTimezone(utc=True))
        )
        self.doTest(
            "TruncatedApr01.ics",
            PyCalendarDateTime(2007, 04, 01, 16, 0, 0, PyCalendarTimezone(utc=True)),
            PyCalendarDateTime(2007, 04, 01, 17, 0, 0, PyCalendarTimezone(utc=True))
        )

class TimezoneCacheTest (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

    data_dir = os.path.join(os.path.dirname(__file__), "data")

    def test_basic(self):
        
        TimezoneCache.create()
        self.assertTrue(readTZ("America/New_York"))
        self.assertTrue(readTZ("US/Eastern"))

    def test_not_in_cache(self):
        
        TimezoneCache.create()

        data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VTIMEZONE
TZID:US-Eastern
LAST-MODIFIED:19870101T000000Z
BEGIN:STANDARD
DTSTART:19671029T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:Eastern Standard Time (US & Canada)
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19870405T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:Eastern Daylight Time (US & Canada)
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:12345-67890
DTSTART;TZID="US-Eastern":20071225T000000
DTEND;TZID="US-Eastern":20071225T010000
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
"""

        calendar = Component.fromString(data)
        if calendar.name() != "VCALENDAR": self.fail("Calendar is not a VCALENDAR")
        instances = calendar.expandTimeRanges(PyCalendarDateTime(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            self.assertEqual(start, PyCalendarDateTime(2007, 12, 25, 05, 0, 0, PyCalendarTimezone(utc=True)))
            self.assertEqual(end, PyCalendarDateTime(2007, 12, 25, 06, 0, 0, PyCalendarTimezone(utc=True)))
            break;

class TimezonePackageTest (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

    def setUp(self):
        TimezoneCache.clear()
        TimezoneCache.create()
        
    def test_ReadTZ(self):
        
        self.assertTrue(readTZ("America/New_York").find("TZID:America/New_York") != -1)
        self.assertRaises(TimezoneException, readTZ, "America/Pittsburgh")

    def test_ReadTZCached(self):
        
        self.assertTrue(readTZ("America/New_York").find("TZID:America/New_York") != -1)
        self.assertTrue(readTZ("America/New_York").find("TZID:America/New_York") != -1)
        self.assertRaises(TimezoneException, readTZ, "America/Pittsburgh")
        self.assertRaises(TimezoneException, readTZ, "America/Pittsburgh")

    def test_ListTZs(self):
        
        results = listTZs()
        self.assertTrue("America/New_York" in results)
        self.assertTrue("Europe/London" in results)
        self.assertTrue("GB" in results)

    def test_ListTZsCached(self):
        
        results = listTZs()
        self.assertTrue("America/New_York" in results)
        self.assertTrue("Europe/London" in results)
        self.assertTrue("GB" in results)
        
