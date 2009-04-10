##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
from vobject.icalendar import utc, getTzid
from vobject.icalendar import registerTzid
from twistedcaldav.timezones import TimezoneCache, TimezoneException
from twistedcaldav.timezones import readTZ, listTZs
import datetime
import os

class TimezoneProblemTest (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

    data_dir = os.path.join(os.path.dirname(__file__), "data")

    def doTest(self, filename, dtstart, dtend, testEqual=True):
        
        if testEqual:
            testMethod = self.assertEqual
        else:
            testMethod = self.assertNotEqual

        calendar = Component.fromStream(file(os.path.join(self.data_dir, filename)))
        if calendar.name() != "VCALENDAR": self.fail("Calendar is not a VCALENDAR")

        instances = calendar.expandTimeRanges(datetime.date(2100, 1, 1))
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
        
        oldtzid = getTzid("America/New_York")
        try:
            registerTzid("America/New_York", None)
            self.doTest("TruncatedApr01.ics", datetime.datetime(2007, 04, 01, 16, 0, 0, tzinfo=utc), datetime.datetime(2007, 04, 01, 17, 0, 0, tzinfo=utc))
        finally:
            registerTzid("America/New_York", oldtzid)

    def test_truncatedDec(self):
        """
        Properties in components
        """
        oldtzid = getTzid("America/New_York")
        try:
            registerTzid("America/New_York", None)
            self.doTest("TruncatedDec10.ics", datetime.datetime(2007, 12, 10, 17, 0, 0, tzinfo=utc), datetime.datetime(2007, 12, 10, 18, 0, 0, tzinfo=utc))
        finally:
            registerTzid("America/New_York", oldtzid)

    def test_truncatedAprThenDecFail(self):
        """
        Properties in components
        """
        if TimezoneCache.activeCache:
            TimezoneCache.activeCache.unregister()

        oldtzid = getTzid("America/New_York")
        try:
            registerTzid("America/New_York", None)
            self.doTest(
                "TruncatedApr01.ics",
                datetime.datetime(2007, 04, 01, 16, 0, 0, tzinfo=utc),
                datetime.datetime(2007, 04, 01, 17, 0, 0, tzinfo=utc),
            )
            self.doTest(
                "TruncatedDec10.ics",
                datetime.datetime(2007, 12, 10, 17, 0, 0, tzinfo=utc),
                datetime.datetime(2007, 12, 10, 18, 0, 0, tzinfo=utc),
                testEqual=False
            )
        finally:
            registerTzid("America/New_York", oldtzid)

    def test_truncatedAprThenDecOK(self):
        """
        Properties in components
        """
        oldtzid = getTzid("America/New_York")
        try:
            registerTzid("America/New_York", None)
            tzcache = TimezoneCache()
            tzcache.register()
            self.doTest(
                "TruncatedApr01.ics",
                datetime.datetime(2007, 04, 01, 16, 0, 0, tzinfo=utc),
                datetime.datetime(2007, 04, 01, 17, 0, 0, tzinfo=utc),
            )
            self.doTest(
                "TruncatedDec10.ics",
                datetime.datetime(2007, 12, 10, 17, 0, 0, tzinfo=utc),
                datetime.datetime(2007, 12, 10, 18, 0, 0, tzinfo=utc),
            )
            tzcache.unregister()
        finally:
            registerTzid("America/New_York", oldtzid)

    def test_truncatedDecThenApr(self):
        """
        Properties in components
        """
        oldtzid = getTzid("America/New_York")
        try:
            registerTzid("America/New_York", None)
            self.doTest("TruncatedDec10.ics", datetime.datetime(2007, 12, 10, 17, 0, 0, tzinfo=utc), datetime.datetime(2007, 12, 10, 18, 0, 0, tzinfo=utc))
            self.doTest("TruncatedApr01.ics", datetime.datetime(2007, 04, 01, 16, 0, 0, tzinfo=utc), datetime.datetime(2007, 04, 01, 17, 0, 0, tzinfo=utc))
        finally:
            registerTzid("America/New_York", oldtzid)

class TimezoneCacheTest (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

    data_dir = os.path.join(os.path.dirname(__file__), "data")

    def test_basic(self):
        
        registerTzid("America/New_York", None)
        registerTzid("US/Eastern", None)

        tzcache = TimezoneCache()
        tzcache.register()
        self.assertTrue(tzcache.loadTimezone("America/New_York"))
        self.assertTrue(tzcache.loadTimezone("US/Eastern"))
        tzcache.unregister()

    def test_not_in_cache(self):
        
        tzcache = TimezoneCache()
        tzcache.register()

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
        instances = calendar.expandTimeRanges(datetime.date(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            self.assertEqual(start, datetime.datetime(2007, 12, 25, 05, 0, 0, tzinfo=utc))
            self.assertEqual(end, datetime.datetime(2007, 12, 25, 06, 0, 0, tzinfo=utc))
            break;
        tzcache.unregister()

class TimezonePackageTest (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

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
        results = listTZs()
        self.assertTrue("America/New_York" in results)
        self.assertTrue("Europe/London" in results)
        self.assertTrue("GB" in results)
        
