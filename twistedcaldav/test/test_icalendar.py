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

import os
from difflib import unified_diff
import itertools

from twisted.trial.unittest import SkipTest

from twistedcaldav.config import config
from twistedcaldav.ical import Component, Property, InvalidICalendarDataError
from twistedcaldav.instance import InvalidOverriddenInstanceError
import twistedcaldav.test.util

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone
from twistedcaldav.ical import iCalendarProductID
from pycalendar.duration import PyCalendarDuration

class iCalendar (twistedcaldav.test.util.TestCase):
    """
    iCalendar support tests
    """
    data_dir = os.path.join(os.path.dirname(__file__), "data")

    def test_component(self):
        """
        Properties in components
        """
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays.ics")))
        if calendar.name() != "VCALENDAR": self.fail("Calendar is not a VCALENDAR")

        for subcomponent in calendar.subcomponents():
            if subcomponent.name() == "VEVENT":
                if not subcomponent.propertyValue("UID")[8:] == "-1ED0-11D9-A5E0-000A958A3252":
                    self.fail("Incorrect UID in component: %r" % (subcomponent,))
                if not subcomponent.propertyValue("DTSTART"):
                    self.fail("No DTSTART in component: %r" % (subcomponent,))
            else:
                SkipTest("test unimplemented")


    def test_newCalendar(self):
        """
        L{Component.newCalendar} creates a new VCALENDAR L{Component} with
        appropriate version and product identifiers, and no subcomponents.
        """
        calendar = Component.newCalendar()
        version = calendar.getProperty("VERSION")
        prodid = calendar.getProperty("PRODID")
        self.assertEqual(version.value(), "2.0")
        self.assertEqual(prodid.value(), iCalendarProductID)
        self.assertEqual(list(calendar.subcomponents()), [])


    def test_component_equality(self):
#        for filename in (
#            os.path.join(self.data_dir, "Holidays", "C318A4BA-1ED0-11D9-A5E0-000A958A3252.ics"),
#            os.path.join(self.data_dir, "Holidays.ics"),
#        ):
#            data = file(filename).read()
#
#            calendar1 = Component.fromString(data)
#            calendar2 = Component.fromString(data)
#
#            self.assertEqual(calendar1, calendar2)
            
        data1 = (
            (
                "1.1 Switch property order",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:COUNT=400;FREQ=DAILY
EXDATE:20080602T120000Z
EXDATE:20080603T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:COUNT=400;FREQ=DAILY
EXDATE:20080603T120000Z
EXDATE:20080602T120000Z
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "1.2 Switch component order",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:COUNT=400;FREQ=DAILY
EXDATE:20080602T120000Z
EXDATE:20080603T120000Z
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T130000Z
DTEND:20080602T140000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T130000Z
DTEND:20080602T140000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:COUNT=400;FREQ=DAILY
EXDATE:20080603T120000Z
EXDATE:20080602T120000Z
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "1.3 Switch VALARM order",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:COUNT=400;FREQ=DAILY
EXDATE:20080602T120000Z
EXDATE:20080603T120000Z
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test-2
TRIGGER;RELATED=START:-PT5M
END:VALARM
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:COUNT=400;FREQ=DAILY
EXDATE:20080603T120000Z
EXDATE:20080602T120000Z
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test-2
TRIGGER;RELATED=START:-PT5M
END:VALARM
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
        )
        
        for description, item1, item2, result in data1:
            if "1.3" not in description:
                continue
            calendar1 = Component.fromString(item1)
            calendar2 = Component.fromString(item2)
            (self.assertEqual if result else self.assertNotEqual)(
                calendar1, calendar2, "%s" % (description,)
            )

    def test_component_validate(self):
        """
        CalDAV resource validation.
        """
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays.ics")))
        try:
            calendar.validCalendarData()
            calendar.validCalendarForCalDAV(methodAllowed=False)
        except ValueError:
            pass
        else:
            self.fail("Monolithic iCalendar shouldn't validate for CalDAV")

        resource_dir = os.path.join(self.data_dir, "Holidays")
        for filename in resource_dir:
            if os.path.splitext(filename)[1] != ".ics": continue
            filename = os.path.join(resource_dir, filename)

            calendar = Component.fromStream(file(filename))
            try:
                calendar.validCalendarData()
                calendar.validCalendarForCalDAV(methodAllowed=False)
            except ValueError:
                self.fail("Resource iCalendar %s didn't validate for CalDAV" % (filename,))

    def test_component_validate_and_fix(self):
        """
        CalDAV resource validation and fixing.
        """
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Computer\, Inc//iCal 2.0//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20110105T191945Z
UID:5D70FD7E-3DFA-4981-8B91-E9E6CD5FCE28
DTEND;TZID=America/Los_Angeles:20110107T141500
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL=20110121
TRANSP:OPAQUE
SUMMARY:test
DTSTART;TZID=America/Los_Angeles:20110107T123000
DTSTAMP:20110105T192229Z
END:VEVENT
END:VCALENDAR
"""
        # Ensure it starts off invalid
        calendar = Component.fromString(data)
        try:
            calendar.validCalendarData(doFix=False)
        except InvalidICalendarDataError:
            pass
        else:
            self.fail("Shouldn't validate for CalDAV")

        # Fix it
        calendar.validCalendarData(doFix=True)
        self.assertTrue("RRULE:FREQ=DAILY;UNTIL=20110121T203000Z\r\n"
            in str(calendar))

        # Now it should pass without fixing
        calendar.validCalendarData(doFix=False)

        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Computer\, Inc//iCal 2.0//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTART;VALUE=DATE:20110107
DTEND;VALUE=DATE:20110108
DTSTAMP:20110106T231917Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL=20110131T123456
SUMMARY:test
CREATED:20110105T191945Z
UID:5D70FD7E-3DFA-4981-8B91-E9E6CD5FCE28
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""
        # Ensure it starts off invalid
        calendar = Component.fromString(data)
        try:
            calendar.validCalendarData(doFix=False)
        except InvalidICalendarDataError:
            pass
        else:
            self.fail("Shouldn't validate for CalDAV")

        # Fix it
        calendar.validCalendarData(doFix=True)
        self.assertTrue("RRULE:FREQ=DAILY;UNTIL=20110131\r\n" in str(calendar))

        # Now it should pass without fixing
        calendar.validCalendarData(doFix=False)

        # Test invalid occurrences
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 5.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20111206T203543Z
UID:5F7FF5FB-2253-4895-8BF1-76E8ED868B4C
DTEND;TZID=America/Los_Angeles:20111207T153000
RRULE:FREQ=WEEKLY;COUNT=400
TRANSP:OPAQUE
SUMMARY:bogus instance
DTSTART;TZID=America/Los_Angeles:20111207T143000
DTSTAMP:20111206T203553Z
SEQUENCE:3
END:VEVENT
BEGIN:VEVENT
CREATED:20111206T203543Z
UID:5F7FF5FB-2253-4895-8BF1-76E8ED868B4C
DTEND;TZID=America/Los_Angeles:20111221T124500
TRANSP:OPAQUE
SUMMARY:bogus instance
DTSTART;TZID=America/Los_Angeles:20111221T114500
DTSTAMP:20111206T203632Z
SEQUENCE:5
RECURRENCE-ID;TZID=America/Los_Angeles:20111221T143000
END:VEVENT
BEGIN:VEVENT
CREATED:20111206T203543Z
UID:5F7FF5FB-2253-4895-8BF1-76E8ED868B4C
DTEND;TZID=America/Los_Angeles:20111214T163000
TRANSP:OPAQUE
SUMMARY:bogus instance
DTSTART;TZID=America/Los_Angeles:20111214T153000
DTSTAMP:20111206T203606Z
SEQUENCE:4
RECURRENCE-ID;TZID=America/Los_Angeles:20111215T143000
END:VEVENT
END:VCALENDAR
"""
        # Ensure it starts off invalid
        calendar = Component.fromString(data)
        try:
            calendar.validCalendarData(doFix=False, validateRecurrences=True)
        except InvalidICalendarDataError:
            pass
        else:
            self.fail("Shouldn't validate for CalDAV")

        # Fix it
        calendar.validCalendarData(doFix=True, validateRecurrences=True)
        self.assertTrue("RDATE;TZID=America/Los_Angeles:20111215T143000\r\n" in str(calendar))

        # Now it should pass without fixing
        calendar.validCalendarData(doFix=False, validateRecurrences=True)


        # Test EXDATEs *prior* to master (as the result of client splitting a
        # a recurring event and copying *all* EXDATEs to new event):
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 5.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20120213T224430Z
UID:BD84E32F-15A4-4354-9A72-EA240657734B
DTEND;TZID=US/Pacific:20120218T160000
RRULE:FREQ=DAILY;COUNT=396
TRANSP:OPAQUE
SUMMARY:RECUR
DTSTART;TZID=US/Pacific:20120218T140000
EXDATE;TZID=US/Pacific:20120201T113000,20120202T113000
EXDATE;TZID=US/Pacific:20120214T113000,20120225T113000,20120215T113000
EXDATE;TZID=US/Pacific:20120216T113000
EXDATE;TZID=US/Pacific:20120220T113000
DTSTAMP:20120213T224523Z
SEQUENCE:3
END:VEVENT
BEGIN:VEVENT
CREATED:20120213T224430Z
UID:BD84E32F-15A4-4354-9A72-EA240657734B
DTEND;TZID=US/Pacific:20120221T134500
TRANSP:OPAQUE
SUMMARY:RECUR
DTSTART;TZID=US/Pacific:20120221T114500
DTSTAMP:20120214T000440Z
SEQUENCE:4
RECURRENCE-ID;TZID=US/Pacific:20120221T140000
END:VEVENT
END:VCALENDAR
"""
        # Ensure it starts off invalid
        calendar = Component.fromString(data)
        try:
            calendar.validCalendarData(doFix=False, validateRecurrences=True)
        except InvalidICalendarDataError:
            pass
        else:
            self.fail("Shouldn't validate for CalDAV")

        # Fix it
        fixed, unfixed = calendar.validCalendarData(doFix=True,
            validateRecurrences=True)
        self.assertEquals(fixed,
            ["Removed earlier EXDATE: 20120201T113000",
            "Removed earlier EXDATE: 20120202T113000",
            "Removed earlier EXDATE: 20120214T113000",
            "Removed earlier EXDATE: 20120215T113000",
            "Removed earlier EXDATE: 20120216T113000"]
        )
        self.assertEquals(unfixed, [])

        # These five old EXDATES are removed
        self.assertTrue("EXDATE;TZID=US/Pacific:20120201T113000\r\n" not in str(calendar))
        self.assertTrue("EXDATE;TZID=US/Pacific:20120202T113000\r\n" not in str(calendar))
        self.assertTrue("EXDATE;TZID=US/Pacific:20120214T113000\r\n" not in str(calendar))
        self.assertTrue("EXDATE;TZID=US/Pacific:20120215T113000\r\n" not in str(calendar))
        self.assertTrue("EXDATE;TZID=US/Pacific:20120216T113000\r\n" not in str(calendar))
        # These future EXDATEs remain (one of which used to be in a multi-value EXDATE)
        self.assertTrue("EXDATE;TZID=US/Pacific:20120220T113000\r\n" in str(calendar))
        self.assertTrue("EXDATE;TZID=US/Pacific:20120225T113000\r\n" in str(calendar))

        # Now it should pass without fixing
        calendar.validCalendarData(doFix=False, validateRecurrences=True)


    def test_component_timeranges(self):
        """
        Component time range query.
        """
        #
        # This event is the Independence Day
        #
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays", "C318A4BA-1ED0-11D9-A5E0-000A958A3252.ics")))

        year = 2004

        instances = calendar.expandTimeRanges(PyCalendarDateTime(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            self.assertEqual(start, PyCalendarDateTime(year, 7, 4))
            self.assertEqual(end  , PyCalendarDateTime(year, 7, 5))
            if year == 2050: break
            year += 1

        self.assertEqual(year, 2050)

        #
        # This event is the Thanksgiving holiday (2 days)
        #
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays", "C318ABFE-1ED0-11D9-A5E0-000A958A3252.ics")))
        results = {
            2004: (11, 25, 27),
            2005: (11, 24, 26),
            2006: (11, 23, 25),
            2007: (11, 22, 24),
            2008: (11, 27, 29),
        }
        year = 2004

        instances = calendar.expandTimeRanges(PyCalendarDateTime(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            if year in results:
                self.assertEqual(start, PyCalendarDateTime(year, results[year][0], results[year][1]))
                self.assertEqual(end  , PyCalendarDateTime(year, results[year][0], results[year][2]))
            if year == 2050: break
            year += 1

        self.assertEqual(year, 2050)

        #
        # This event is Father's Day
        #
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays", "C3186426-1ED0-11D9-A5E0-000A958A3252.ics")))
        results = {
            2002: (6, 16, 17),
            2003: (6, 15, 16),
            2004: (6, 20, 21),
            2005: (6, 19, 20),
            2006: (6, 18, 19),
        }
        year = 2002

        instances = calendar.expandTimeRanges(PyCalendarDateTime(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            if year in results:
                self.assertEqual(start, PyCalendarDateTime(year, results[year][0], results[year][1]))
                self.assertEqual(end  , PyCalendarDateTime(year, results[year][0], results[year][2]))
            if year == 2050: break
            year += 1

        self.assertEqual(year, 2050)

    def test_component_timerange(self):
        """
        Component summary time range query.
        """
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays", "C318ABFE-1ED0-11D9-A5E0-000A958A3252.ics")))

        instances = calendar.expandTimeRanges(PyCalendarDateTime(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            self.assertEqual(start, PyCalendarDateTime(2004, 11, 25))
            self.assertEqual(end, PyCalendarDateTime(2004, 11, 27))
            break;

    #test_component_timerange.todo = "recurrence expansion should give us no end date here"

    def test_parse_date(self):
        """
        parse_date()
        """
        self.assertEqual(PyCalendarDateTime.parseText("19970714"), PyCalendarDateTime(1997, 7, 14))

    def test_parse_datetime(self):
        """
        parse_datetime()
        """
        dt = PyCalendarDateTime.parseText("19980118T230000")
        self.assertEqual(dt, PyCalendarDateTime(1998, 1, 18, 23, 0, 0))
        self.assertTrue(dt.floating())

        dt = PyCalendarDateTime.parseText("19980119T070000Z")
        self.assertEqual(dt, PyCalendarDateTime(1998, 1, 19, 7, 0, 0, tzid=PyCalendarTimezone(utc=True)))

    def test_parse_date_or_datetime(self):
        """
        parse_date_or_datetime()
        """
        self.assertEqual(PyCalendarDateTime.parseText("19970714"), PyCalendarDateTime(1997, 7, 14))

        dt = PyCalendarDateTime.parseText("19980118T230000")
        self.assertEqual(dt, PyCalendarDateTime(1998, 1, 18, 23, 0, 0))
        self.assertTrue(dt.floating())

        dt = PyCalendarDateTime.parseText("19980119T070000Z")
        self.assertEqual(dt, PyCalendarDateTime(1998, 1, 19, 7, 0, 0, tzid=PyCalendarTimezone(utc=True)))

    def test_parse_duration(self):
        """
        parse_duration()
        """
        self.assertEqual(PyCalendarDuration.parseText( "P15DT5H0M20S"), PyCalendarDuration(days= 15, hours= 5, minutes=0, seconds= 20))
        self.assertEqual(PyCalendarDuration.parseText("+P15DT5H0M20S"), PyCalendarDuration(days= 15, hours= 5, minutes=0, seconds= 20))
        self.assertEqual(PyCalendarDuration.parseText("-P15DT5H0M20S"), PyCalendarDuration(days=-15, hours=-5, minutes=0, seconds=-20))

        self.assertEqual(PyCalendarDuration.parseText("P7W"), PyCalendarDuration(weeks=7))

    def test_correct_attendee_properties(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Computer\, Inc//iCal 2.0//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
"""

        component = Component.fromString(data)
        self.assertEqual([p.value() for p in component.getAttendeeProperties(("mailto:user2@example.com",))], ["mailto:user2@example.com",])

    def test_empty_attendee_properties(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
DTSTART:20071114T000000Z
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
"""

        component = Component.fromString(data)
        self.assertEqual(component.getAttendeeProperties(("user3@example.com",)), [])

    def test_organizers_by_instance(self):
        
        data = (
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, None),
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", None),
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ORGANIZER:mailto:user2@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                ()
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", None),
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)))
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20091114T000000Z
DTSTART:20071114T020000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user3@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", None),
                    ("mailto:user3@example.com", PyCalendarDateTime(2009, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)))
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20091114T000000Z
DTSTART:20071114T020000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user3@example.com
ORGANIZER:mailto:user4@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", None),
                )
            ),
        )
        
        for caldata, result in data:
            component = Component.fromString(caldata)
            self.assertEqual(component.getOrganizersByInstance(), result)

    def test_attendees_by_instance(self):
        
        data = (
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                False,
                ()
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                (
                    ("mailto:user2@example.com", None),
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                (
                    ("mailto:user2@example.com", None),
                    ("mailto:user3@example.com", None),
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE;SCHEDULE-AGENT=NONE:mailto:user2@example.com
ATTENDEE;SCHEDULE-AGENT=CLIENT:mailto:user3@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                (
                    ("mailto:user2@example.com", None),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)))
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE;SCHEDULE-AGENT=NONE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
                (
                    ("mailto:user3@example.com", None),
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE;SCHEDULE-AGENT=SERVER:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE;SCHEDULE-AGENT=NONE:mailto:user2@example.com
ATTENDEE;SCHEDULE-AGENT=CLIENT:mailto:user3@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
                (
                    ("mailto:user2@example.com", None),
                )
            ),
        )
        
        for caldata, checkScheduleAgent, result in data:
            component = Component.fromString(caldata)
            self.assertEqual(component.getAttendeesByInstance(onlyScheduleAgentServer=checkScheduleAgent), result)

    def test_set_parameter_value(self):
        data = (
            # ATTENDEE - no existing parameter
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;SCHEDULE-STATUS=2.0:mailto:user02@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    "SCHEDULE-STATUS",
                    "2.0",
                    "ATTENDEE",
                    "mailto:user02@example.com",
                ),
            ),
            # ATTENDEE - existing parameter
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;SCHEDULE-STATUS=5.0:mailto:user02@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;SCHEDULE-STATUS=2.0:mailto:user02@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    "SCHEDULE-STATUS",
                    "2.0",
                    "ATTENDEE",
                    "mailto:user02@example.com",
                ),
            ),
            # ORGANIZER - no existing parameter
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
DTSTAMP:20080601T120000Z
ORGANIZER;SCHEDULE-STATUS=2.0:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    "SCHEDULE-STATUS",
                    "2.0",
                    "ORGANIZER",
                    "mailto:user01@example.com",
                ),
            ),
            # ORGANIZER - existing parameter
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
DTSTAMP:20080601T120000Z
ORGANIZER;SCHEDULE-STATUS=5.0:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
DTSTAMP:20080601T120000Z
ORGANIZER;SCHEDULE-STATUS=2.0:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    "SCHEDULE-STATUS",
                    "2.0",
                    "ORGANIZER",
                    "mailto:user01@example.com",
                ),
            ),
        )

        for original, result, args in data:
            component = Component.fromString(original)
            component.setParameterToValueForPropertyWithValue(*args)
            self.assertEqual(result, str(component).replace("\r", ""))        

    def test_add_property(self):
        data = (
            # Simple component
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
REQUEST-STATUS:2.0;Success
END:VEVENT
END:VCALENDAR
""",
            ),
            # Complex component
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T020000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
REQUEST-STATUS:2.0;Success
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T020000Z
DTSTAMP:20080601T120000Z
REQUEST-STATUS:2.0;Success
END:VEVENT
END:VCALENDAR
""",
            ),
        )

        for original, result in data:
            component = Component.fromString(original)
            component.addPropertyToAllComponents(Property("REQUEST-STATUS", ["2.0", "Success"]))
            self.assertEqual(result, str(component).replace("\r", ""))        

    def test_attendees_views(self):
        
        data = (
            (
                "1.1 Simple component, no Attendees - no filtering",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ()
            ),

            (
                "1.2 Simple component, no Attendees - filtering",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user01@example.com",)
            ),

            (
                "1.3 Simple component, with one attendee - filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            (
                "1.4 Simple component, with one attendee - no filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),

            (
                "2.1 Recurring component with one instance, each with one attendee - filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            (
                "2.2 Recurring component with one instance, each with one attendee - no filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),        

            (
                "2.3 Recurring component with one instance, master with one attendee, instance without attendee - filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
EXDATE:20081114T000000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            (
                "2.4 Recurring component with one instance, master with one attendee, instance without attendee - no filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),

            (
                "2.5 Recurring component with one instance, master without attendee, instance with attendee - filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            (
                "2.6 Recurring component with one instance, master without attendee, instance with attendee - no filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),

            (
                "3.1 Simple component, no Attendees - no filtering",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                False,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ()
            ),

            (
                "3.2 Simple component, no Attendees - filtering",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                True,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user01@example.com",)
            ),

            (
                "3.3 Simple component, with one attendee - filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            (
                "3.4 Simple component, with one attendee - filtering match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE;SCHEDULE-AGENT=SERVER:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE;SCHEDULE-AGENT=SERVER:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            (
                "3.5 Simple component, with one attendee - filtering match - no schedule-agent match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE;SCHEDULE-AGENT=CLIENT:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            (
                "3.6 Simple component, with one attendee - filtering match - no schedule-agent match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE;SCHEDULE-AGENT=NONE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

        )
        
        for description, original, checkScheduleAgent, filtered, attendees in data:
            component = Component.fromString(original)
            component.attendeesView(attendees, onlyScheduleAgentServer=checkScheduleAgent)
            self.assertEqual(filtered, str(component).replace("\r", ""), "Failed: %s" % (description,))

    def test_all_but_one_attendee(self):
        
        data = (
            # One component, no attendees
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                "mailto:user02@example.com",
            ),

            # One component, one attendee - removed
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                "mailto:user1@example.com",
            ),

            # One component, one attendee - left
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                "mailto:user2@example.com",
            ),

            # One component, two attendees - none left
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                "mailto:user1@example.com",
            ),

            # One component, two attendees - one left
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-5
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-5
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                "mailto:user2@example.com",
            ),

        )
        
        for original, result, attendee in data:
            component = Component.fromString(original)
            component.removeAllButOneAttendee(attendee)
            self.assertEqual(result, str(component).replace("\r", ""))

    def test_filter_properties_keep(self):
        
        data = (
            # One component
            (
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
SUMMARY:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("UID", "RECURRENCE-ID", "SEQUENCE", "DTSTAMP", "ORGANIZER", "ATTENDEE",),
            ),

            # Multiple components
            (
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("UID", "RECURRENCE-ID", "SEQUENCE", "DTSTAMP", "ORGANIZER", "ATTENDEE",),
            ),

        )
        
        for original, result, keep_properties in data:
            component = Component.fromString(original)
            component.filterProperties(keep=keep_properties)
            self.assertEqual(result, str(component).replace("\r", ""))

    def test_filter_properties_remove(self):
        
        data = (
            # One component
            (
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
SUMMARY:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("DTSTART", "SUMMARY",),
            ),

            # Multiple components
            (
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("DTSTART", "SUMMARY",),
            ),

        )
        
        for original, result, remove_properties in data:
            component = Component.fromString(original)
            component.filterProperties(remove=remove_properties)
            self.assertEqual(result, str(component).replace("\r", ""))

    def test_remove_alarms(self):
        
        data = (
            # One component, no alarms
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
            ),

            # One component, one alarm
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
            ),

            # Multiple components, one alarm
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
            ),

            # Multiple components, multiple alarms
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
            ),
        )
        
        for original, result in data:
            component = Component.fromString(original)
            component.removeAlarms()
            self.assertEqual(result, str(component).replace("\r", ""))

    def test_expand_instances(self):
        
        data = (
            (
                "Non recurring",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""",
                False,
                (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),)
            ),
            (
                "Simple recurring",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
END:VCALENDAR
""",
                False,
                (
                    PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                )
            ),
            (
                "Recurring with RDATE",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=2
RDATE:20071116T010000Z
END:VEVENT
END:VCALENDAR
""",
                False,
                (
                    PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2007, 11, 16, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                )
            ),
            (
                "Recurring with EXDATE",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=3
EXDATE:20071115T000000Z
END:VEVENT
END:VCALENDAR
""",
                False,
                (
                    PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2007, 11, 16, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                )
            ),
            (
                "Recurring with EXDATE on DTSTART",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=3
EXDATE:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                False,
                (
                    PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2007, 11, 16, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                )
            ),
            (
                "Recurring with override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DTSTAMP:20080601T120000Z
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""",
                False,
                (
                    PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2007, 11, 15, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                )
            ),
            (
                "Recurring with invalid override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T010000Z
DTSTART:20071115T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                False,
                None
            ),
            (
                "Recurring with invalid override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T010000Z
DTSTART:20071115T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                True,
                (
                    PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                )
            ),
        )
        
        for description, original, ignoreInvalidInstances, results in data:
            component = Component.fromString(original)
            if results is None:
                self.assertRaises(InvalidOverriddenInstanceError, component.expandTimeRanges, PyCalendarDateTime(2100, 1, 1), ignoreInvalidInstances)
            else:
                instances = component.expandTimeRanges(PyCalendarDateTime(2100, 1, 1), ignoreInvalidInstances)
                self.assertTrue(len(instances.instances) == len(results), "%s: wrong number of instances" % (description,))
                for instance in instances:
                    self.assertTrue(instances[instance].start in results, "%s: %s missing" % (description, instance,))
       
    def test_has_property_in_any_component(self):
        
        data = (
            (
                "Single component - True",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ("DTSTART",),
                True,
            ),
            (
                "Single component - False",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ("DTEND",),
                False,
            ),
            (
                "Multiple components - True in both",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ("DTSTART",),
                True,
            ),
            (
                "Multiple components - True in one",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ("RECURRENCE-ID",),
                True,
            ),
            (
                "Multiple components - False",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ("DTEND",),
                False,
            ),
            (
                "Multiple components/propnames - True in both",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ("DTSTART", "RECURRENCE-ID",),
                True,
            ),
            (
                "Multiple components - True in one",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                ("STATUS", "RECURRENCE-ID",),
                True,
            ),
            (
                "Multiple components - False",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DTSTAMP:20080601T120000Z
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""",
                ("STATUS", "DTEND",),
                False,
            ),
        )
        
        for description, caldata, propnames, result in data:
            component = Component.fromString(caldata)
            self.assertTrue(component.hasPropertyInAnyComponent(propnames) == result, "Property name match incorrect: %s" % (description,))
       
    def test_transfer_properties(self):
        
        data = (
            (
                "Non recurring - one property",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:True
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM2:True
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:True
X-ITEM2:True
END:VEVENT
END:VCALENDAR
""",
            ("X-ITEM2",),
            ),
            (
                "Non recurring - two properties",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:True
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM2:True
X-ITEM3:True
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:True
X-ITEM2:True
X-ITEM3:True
END:VEVENT
END:VCALENDAR
""",
            ("X-ITEM2","X-ITEM3",),
            ),
            (
                "Non recurring - two properties - one overlap",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:True
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM2:True
X-ITEM1:False
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:True
X-ITEM2:True
X-ITEM1:False
END:VEVENT
END:VCALENDAR
""",
            ("X-ITEM2","X-ITEM1",),
            ),
            (
                "Non recurring - one property",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
X-ITEM1:True
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:False
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
X-ITEM2:True
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM2:False
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
X-ITEM1:True
X-ITEM2:True
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:False
X-ITEM2:False
END:VEVENT
END:VCALENDAR
""",
            ("X-ITEM2",),
            ),
            (
                "Non recurring - new override, one property",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
X-ITEM1:True
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:False
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
X-ITEM2:True
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
X-ITEM1:True
X-ITEM2:True
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DURATION:PT1H
DTSTAMP:20080601T120000Z
X-ITEM1:False
X-ITEM2:True
END:VEVENT
END:VCALENDAR
""",
            ("X-ITEM2",),
            ),
        )
        
        for description, transfer_to, transfer_from, result, propnames in data:
            component_to = Component.fromString(transfer_to)
            component_from = Component.fromString(transfer_from)
            component_result = Component.fromString(result)
            component_to.transferProperties(component_from, propnames)
            self.assertEqual(str(component_to), str(component_result), "%s: mismatch" % (description,))

    def test_normalize_all(self):
        
        data = (
            (
                "1.1",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114T000000Z
DTSTAMP:20080601T120000Z
SEQUENCE:0
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.2",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114T000000Z
DTSTAMP:20080601T120000Z
TRANSP:OPAQUE
ORGANIZER:mailto:user01@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user03@example.com
ATTENDEE;RSVP=FALSE:mailto:user04@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;RSVP=TRUE:mailto:user02@example.com
ATTENDEE:mailto:user03@example.com
ATTENDEE:mailto:user04@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.3",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY;WKST=SU;INTERVAL=1;BYDAY=MO,WE,FR
TRANSP:OPAQUE
ORGANIZER:mailto:user01@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user03@example.com
ATTENDEE;RSVP=FALSE:mailto:user04@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;RSVP=TRUE:mailto:user02@example.com
ATTENDEE:mailto:user03@example.com
ATTENDEE:mailto:user04@example.com
RRULE:BYDAY=MO,WE,FR;FREQ=WEEKLY;INTERVAL=1;WKST=SU
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.4",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;TZID=US/Pacific:20071114T000000
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY;WKST=SU;INTERVAL=1;BYDAY=MO,WE,FR
TRANSP:OPAQUE
ORGANIZER:mailto:user01@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user03@example.com
ATTENDEE;RSVP=FALSE:mailto:user04@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;_TZID=US/Pacific:20071114T080000Z
DTSTAMP:20080601T120000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;RSVP=TRUE:mailto:user02@example.com
ATTENDEE:mailto:user03@example.com
ATTENDEE:mailto:user04@example.com
RRULE:BYDAY=MO,WE,FR;FREQ=WEEKLY;INTERVAL=1;WKST=SU
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
            ),
        )
        
        for title, original, result in data:
            ical1 = Component.fromString(original)
            ical1.normalizeAll()
            ical1 = str(ical1)
            ical2 = Component.fromString(result)
            ical2 = str(ical2)
            diff = "\n".join(unified_diff(ical1.split("\n"), ical2.split("\n")))
            self.assertEqual(str(ical1), str(ical2), "Failed comparison: %s\n%s" % (title, diff,))

    def test_normalize_attachments(self):
        
        data = (
            (
                "1.1 - no attach",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.2 - attach with no dropbox",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114
ATTACH:http://example.com/file.txt
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114
ATTACH:http://example.com/file.txt
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.3 - attach with dropbox",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114
ATTACH:http://example.com/calendars/user.dropbox/file.txt
DTSTAMP:20080601T120000Z
X-APPLE-DROPBOX:/calendars/user.dropbox
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114
DTSTAMP:20080601T120000Z
X-APPLE-DROPBOX:/calendars/user.dropbox
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.4 - attach with different dropbox",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114
ATTACH:http://example.com/calendars/user.dropbox/file.txt
DTSTAMP:20080601T120000Z
X-APPLE-DROPBOX:/calendars/user1.dropbox
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE-TIME:20071114
ATTACH:http://example.com/calendars/user.dropbox/file.txt
DTSTAMP:20080601T120000Z
X-APPLE-DROPBOX:/calendars/user1.dropbox
END:VEVENT
END:VCALENDAR
""",
            ),
        )
        
        for title, original, result in data:
            ical1 = Component.fromString(original)
            ical1.normalizeAttachments()
            ical1 = str(ical1)
            ical2 = Component.fromString(result)
            ical2 = str(ical2)
            diff = "\n".join(unified_diff(ical1.split("\n"), ical2.split("\n")))
            self.assertEqual(str(ical1), str(ical2), "Failed comparison: %s\n%s" % (title, diff,))

    def test_recurring_unbounded(self):
        
        data = (
            (
                "1.1 - non-recurring",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T000000Z
DTEND:20090102T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                False
            ),
            (
                "1.2 - recurring bounded COUNT",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T000000Z
DTEND:20090102T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
END:VCALENDAR
""",
                False
            ),
            (
                "1.3 - recurring bounded UNTIL",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T000000Z
DTEND:20090102T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY;UNTIL=20090108T000000Z
END:VEVENT
END:VCALENDAR
""",
                False
            ),
            (
                "1.4 - recurring unbounded",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T000000Z
DTEND:20090102T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                True
            ),
        )
        
        for title, calendar, expected in data:
            ical = Component.fromString(calendar)
            result = ical.isRecurringUnbounded()
            self.assertEqual(result, expected, "Failed recurring unbounded test: %s" % (title,))

    def test_derive_instance(self):
        
        data = (
            (
                "1.1 - simple",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 2, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090102T080000Z
DTSTART:20090102T080000Z
DTEND:20090102T090000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
            ),
            (
                "1.2 - simple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20090102T180000Z
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 2, 18, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090102T180000Z
DTSTART:20090102T180000Z
DTEND:20090102T190000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
            ),
            (
                "1.3 - multiple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20090102T180000Z,20090103T180000Z
RDATE:20090104T180000Z
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 3, 18, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090103T180000Z
DTSTART:20090103T180000Z
DTEND:20090103T190000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
            ),
            (
                "2.1 - invalid simple",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 2, 9, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                None,
            ),
            (
                "2.2 - invalid simple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20090102T180000Z
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 2, 19, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                None,
            ),
            (
                "2.3 - invalid multiple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20090102T180000Z,20090103T180000Z
RDATE:20090104T180000Z
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 3, 19, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                None,
            ),
            (
                "3.1 - simple all-day",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE:20090101
DTEND;VALUE=DATE:20090102
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 8),
                """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID;VALUE=DATE:20090108
DTSTART;VALUE=DATE:20090108
DTEND;VALUE=DATE:20090109
DTSTAMP:20080601T120000Z
END:VEVENT
""",
            ),
            (
                "3.2 - simple all-day rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE:20090101
DTEND;VALUE=DATE:20090102
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY
RDATE;VALUE=DATE:20090103
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 3),
                """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID;VALUE=DATE:20090103
DTSTART;VALUE=DATE:20090103
DTEND;VALUE=DATE:20090104
DTSTAMP:20080601T120000Z
END:VEVENT
""",
            ),
            (
                "3.3 - multiple all-day rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE:20090101
DTEND;VALUE=DATE:20090102
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY
RDATE;VALUE=DATE:20090103,20090110
RDATE;VALUE=DATE:20090118
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 10),
                """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID;VALUE=DATE:20090110
DTSTART;VALUE=DATE:20090110
DTEND;VALUE=DATE:20090111
DTSTAMP:20080601T120000Z
END:VEVENT
""",
            ),
            (
                "4.1 - invalid all-day simple",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE:20090101
DTEND;VALUE=DATE:20090102
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 3),
                None,
            ),
            (
                "4.2 - invalid all-day simple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE:20090101
DTEND;VALUE=DATE:20090102
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY
RDATE;VALUE=DATE:20090104
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 5),
                None,
            ),
            (
                "4.3 - invalid all-day multiple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART;VALUE=DATE:20090101
DTEND;VALUE=DATE:20090102
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY
RDATE;VALUE=DATE:20090104,20090111
RDATE;VALUE=DATE:20090118
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 19),
                None,
            ),
        )
        
        for title, calendar, rid, result in data:
            ical = Component.fromString(calendar)
            derived = ical.deriveInstance(rid)
            derived = str(derived).replace("\r", "") if derived else None
            self.assertEqual(derived, result, "Failed derive instance test: %s" % (title,))

    def test_derive_instance_multiple(self):
        
        data = (
            (
                "1.1 - simple",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                (
                    PyCalendarDateTime(2009, 1, 2, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2009, 1, 4, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                ),
                (
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090102T080000Z
DTSTART:20090102T080000Z
DTEND:20090102T090000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090104T080000Z
DTSTART:20090104T080000Z
DTEND:20090104T090000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                ),
            ),
            (
                "1.2 - simple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20090102T180000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    PyCalendarDateTime(2009, 1, 2, 18, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2009, 1, 4, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                ),
                (
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090102T180000Z
DTSTART:20090102T180000Z
DTEND:20090102T190000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090104T080000Z
DTSTART:20090104T080000Z
DTEND:20090104T090000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                ),
            ),
            (
                "1.3 - multiple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20090102T180000Z,20090103T180000Z
RDATE:20090104T180000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    PyCalendarDateTime(2009, 1, 3, 18, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2009, 1, 5, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                ),
                (
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090103T180000Z
DTSTART:20090103T180000Z
DTEND:20090103T190000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090105T080000Z
DTSTART:20090105T080000Z
DTEND:20090105T090000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                ),
            ),
            (
                "2.1 - invalid simple",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                (
                    PyCalendarDateTime(2009, 1, 2, 9, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2009, 1, 3, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                ),
                (
                    None,
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090103T080000Z
DTSTART:20090103T080000Z
DTEND:20090103T090000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                ),
            ),
            (
                "2.2 - invalid simple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20090102T180000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    PyCalendarDateTime(2009, 1, 2, 19, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2009, 1, 3, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                ),
                (
                    None,
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090103T080000Z
DTSTART:20090103T080000Z
DTEND:20090103T090000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                ),
            ),
            (
                "2.3 - invalid multiple rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20090102T180000Z,20090103T180000Z
RDATE:20090104T180000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    PyCalendarDateTime(2009, 1, 3, 19, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                    PyCalendarDateTime(2009, 1, 3, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                ),
                (
                    None,
                    """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090103T080000Z
DTSTART:20090103T080000Z
DTEND:20090103T090000Z
DTSTAMP:20080601T120000Z
END:VEVENT
""",
                ),
            ),
        )
        
        for title, calendar, rids, results in data:
            ical = Component.fromString(calendar)
            for rid, result in itertools.izip(rids, results):
                derived = ical.deriveInstance(rid)
                derived = str(derived).replace("\r", "") if derived else None
                self.assertEqual(derived, result, "Failed derive instance test: %s" % (title,))

    def test_derive_instance_with_cancel(self):
        """
        Test that derivation of cancelled instances works and only results in one STATUS property present.
        """
        
        data = (
            (
                "1.1 - simple no existing STATUS",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
EXDATE:20090102T080000Z
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 2, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090102T080000Z
DTSTART:20090102T080000Z
DTEND:20090102T090000Z
DTSTAMP:20080601T120000Z
STATUS:CANCELLED
END:VEVENT
""",
            ),
            (
                "1.2 - simple with existing STATUS",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20090101T080000Z
DTEND:20090101T090000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
EXDATE:20090102T080000Z
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
""",
                PyCalendarDateTime(2009, 1, 2, 8, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                """BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20090102T080000Z
DTSTART:20090102T080000Z
DTEND:20090102T090000Z
DTSTAMP:20080601T120000Z
STATUS:CANCELLED
END:VEVENT
""",
            ),
        )
        
        for title, calendar, rid, result in data:
            ical = Component.fromString(calendar)
            derived = ical.deriveInstance(rid, allowCancelled=True)
            derived = str(derived).replace("\r", "") if derived else None
            self.assertEqual(derived, result, "Failed derive instance test: %s" % (title,))

    def test_truncate_recurrence(self):
        
        data = (
            (
                "1.1 - no recurrence",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                None,
            ),
            (
                "1.2 - no truncation - count",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY;COUNT=2
END:VEVENT
END:VCALENDAR
""",
                None,
            ),
            (
                "1.3 - no truncation - until",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY;UNTIL=20071128T000000Z
END:VEVENT
END:VCALENDAR
""",
                None,
            ),
            (
                "1.4 - truncation - count",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY;COUNT=2000
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:COUNT=400;FREQ=WEEKLY
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.5 - truncation - until",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY;UNTIL=20471128T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:COUNT=400;FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.6 - no truncation - unbounded yearly",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=WEEKLY;UNTIL=20071128T000000Z
END:VEVENT
END:VCALENDAR
""",
                None,
            ),
            (
                "1.7 - truncation - unbounded daily",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:COUNT=400;FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
            ),
        )
        
        for title, original, result in data:
            ical1 = Component.fromString(original)
            changed = ical1.truncateRecurrence(400)
            ical1.normalizeAll()
            ical1 = str(ical1)
            if result is not None:
                if not changed:
                    self.fail("Truncation did not happen when expected: %s" % (title,))
                else:
                    ical2 = Component.fromString(result)
                    ical2 = str(ical2)
    
                    diff = "\n".join(unified_diff(ical1.split("\n"), ical2.split("\n")))
                    self.assertEqual(str(ical1), str(ical2), "Failed comparison: %s\n%s" % (title, diff,))
            elif changed:
                self.fail("Truncation happened when not expected: %s" % (title,))

    def test_valid_recurrence(self):
        
        data = (
            (
                "1.1 - no recurrence",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, True),
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.2 - rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RDATE:20091004T000000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, True),
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 5, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.3 - rrule no overrides",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, True),
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.4 - rrule no overrides + rdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20091004T010000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, True),
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 2, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.5 - rrule no overrides + rdate + exdate",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20091004T010000Z
EXDATE:20091003T000000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, True),
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 2, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                    (PyCalendarDateTime(2009, 10, 3, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.6 - rrule with override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, True),
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2007, 11, 15, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                    (PyCalendarDateTime(2009, 10, 4, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.7 - rrule + rdate with override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
RDATE:20071115T010000Z
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T010000Z
DTSTART:20071115T020000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, True),
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2007, 11, 15, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2007, 11, 15, 2, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                    (PyCalendarDateTime(2009, 10, 4, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.8 - override only",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T010000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, False),
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                    (PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                    (PyCalendarDateTime(2009, 10, 4, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.9 - no recurrence one test master",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (None, True),
                )
            ),
            (
                "1.10 - no recurrence one test master",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (PyCalendarDateTime(2007, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), True),
                )
            ),
            (
                "1.11 - no recurrence one test missing",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
            (
                "1.12 - fake master OK",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071114T000000Z
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    (PyCalendarDateTime(2007, 11, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), False),
                )
            ),
        )
        
        for clear_cache in (True, False):
            for title, calendar, tests in data:
                ical = Component.fromString(calendar)
                for ctr, item in enumerate(tests):
                    rid, result = item
                    self.assertEqual(ical.validInstance(rid, clear_cache=clear_cache), result, "Failed comparison: %s #%d" % (title, ctr+1,))

        for title, calendar, tests in data:
            ical = Component.fromString(calendar)
            rids = set([rid for rid, result in tests])
            expected_results = set([rid for rid, result in tests if result==True])
            actual_results = ical.validInstances(rids)
            self.assertEqual(actual_results, expected_results, "Failed comparison: %s %s" % (title, actual_results,))

    def test_valid_recurrence_ids(self):
        
        data = (
            (
                "1.1 - fake master",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071114T000000Z
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
RDATE:20071114T000000Z
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071114T000000Z
DTSTART:20071114T000000Z
DTSTAMP:20080601T120000Z
END:VEVENT
END:VCALENDAR
""",
            1, 0,
            ),
        )
        
        for title, calendar, result_calendar, result_fixed, result_unfixed in data:
            ical = Component.fromString(calendar)
            fixed, unfixed = ical.validRecurrenceIDs(doFix=True)
            self.assertEqual(str(ical), result_calendar.replace("\n", "\r\n"), "Failed comparison: %s %s" % (title, str(ical),))
            self.assertEqual(len(fixed), result_fixed, "Failed fixed comparison: %s %s" % (title, fixed,))
            self.assertEqual(len(unfixed), result_unfixed, "Failed unfixed: %s %s" % (title, unfixed,))

    def test_mismatched_until(self):
        invalid = (
            """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 3.0//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:FB81D520-ED27-4DBA-8894-45B7612A7621
DTSTART;TZID=US/Pacific:20090705T100000
DTEND;TZID=US/Pacific:20090730T103000
CREATED:20090604T225706Z
DTSTAMP:20090604T230500Z
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL=20090706
SEQUENCE:1
SUMMARY:TEST
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:FB81D520-ED27-4DBA-8894-45B7612A7621
RECURRENCE-ID;TZID=US/Pacific:20090705T100000
DTSTART;TZID=US/Pacific:20090705T114500
DTEND;TZID=US/Pacific:20090705T121500
CREATED:20090604T225706Z
DTSTAMP:20090604T230504Z
SEQUENCE:2
SUMMARY:TEST
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""",
            """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.2//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100311T234221Z
UID:D0151FAD-4739-4B61-96EB-9289FF1F7716
DTEND;VALUE=DATE:20100316
RRULE:FREQ=WEEKLY;INTERVAL=1;UNTIL=20110604T225706Z
TRANSP:TRANSPARENT
SUMMARY:ALL DAY
DTSTART;VALUE=DATE:20100315
DTSTAMP:20100312T002640Z
SEQUENCE:5
END:VEVENT
END:VCALENDAR
""",
        )

        valid = (
            """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.2//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100311T234221Z
UID:D0151FAD-4739-4B61-96EB-9289FF1F7716
DTEND;VALUE=DATE:20100316
RRULE:FREQ=WEEKLY;INTERVAL=1;UNTIL=20110316
TRANSP:TRANSPARENT
SUMMARY:ALL DAY
DTSTART;VALUE=DATE:20100315
DTSTAMP:20100312T002640Z
SEQUENCE:5
END:VEVENT
END:VCALENDAR
""",
        )


        for text in invalid:
            calendar = Component.fromString(text)
            self.assertRaises(InvalidICalendarDataError, calendar.validCalendarData, doFix=False)
        for text in valid:
            calendar = Component.fromString(text)
            try:
                calendar.validCalendarData()
                calendar.validCalendarForCalDAV(methodAllowed=False)
            except:
                self.fail("Valid calendar should validate")

    def test_allperuseruids(self):
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user01
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
TRANSP:OPAQUE
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user02
BEGIN:X-CALENDARSERVER-PERINSTANCE
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
""".replace("\n", "\r\n")

        calendar = Component.fromString(data)
        self.assertEqual(calendar.allPerUserUIDs(), set((
            "user01",
            "user02",
        )))

    def test_perUserTransparency(self):
        data = (
                    (
                        "No per-user, not recurring 1.1",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", True,),
                                ),
                            ),
                        ),
                    ),
                    (
                        "Single user, not recurring 1.2",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user01
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
TRANSP:OPAQUE
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", False,),
                                    ("user01", False,),
                                ),
                            ),
                        ),
                    ),
                    (
                        "Two users, not recurring 1.3",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user01
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
TRANSP:OPAQUE
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user02
BEGIN:X-CALENDARSERVER-PERINSTANCE
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", False,),
                                    ("user01", False,),
                                    ("user02", True,),
                                ),
                            ),
                        ),
                    ),
                    (
                        "No per-user, simple recurring 2.1",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", False,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 2, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                ),
                            ),
                        ),
                    ),
                    (
                        "Single user, simple recurring 2.2",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user01
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
TRANSP:OPAQUE
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", False,),
                                    ("user01", False,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 2, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                    ("user01", False,),
                                ),
                            ),
                        ),
                    ),
                    (
                        "Two users, simple recurring 2.3",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user01
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
TRANSP:OPAQUE
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user02
BEGIN:X-CALENDARSERVER-PERINSTANCE
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", False,),
                                    ("user01", False,),
                                    ("user02", True,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 2, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                    ("user01", False,),
                                    ("user02", True,),
                                ),
                            ),
                        ),
                    ),
                    (
                        "No per-user, complex recurring 3.1",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=DAILY
TRANSP:TRANSPARENT
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTAMP:20080601T120000Z
DTSTART:20080602T130000Z
DTEND:20080602T140000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", True,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 2, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 3, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", True,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 4, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", True,),
                                ),
                            ),
                        ),
                    ),
                    (
                        "Single user, complex recurring 3.2",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTAMP:20080601T120000Z
DTSTART:20080602T130000Z
DTEND:20080602T140000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user01
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
TRANSP:OPAQUE
END:X-CALENDARSERVER-PERINSTANCE
BEGIN:X-CALENDARSERVER-PERINSTANCE
RECURRENCE-ID:20080602T120000Z
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
BEGIN:X-CALENDARSERVER-PERINSTANCE
RECURRENCE-ID:20080603T120000Z
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", False,),
                                    ("user01", False,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 2, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                    ("user01", True,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 3, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                    ("user01", True,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 4, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                    ("user01", False,),
                                ),
                            ),
                        ),
                    ),
                    (
                        "Two users, complex recurring 3.3",
                        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTAMP:20080601T120000Z
DTSTART:20080602T130000Z
DTEND:20080602T140000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user01
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
TRANSP:OPAQUE
END:X-CALENDARSERVER-PERINSTANCE
BEGIN:X-CALENDARSERVER-PERINSTANCE
RECURRENCE-ID:20080602T120000Z
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
BEGIN:X-CALENDARSERVER-PERINSTANCE
RECURRENCE-ID:20080603T120000Z
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user02
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
BEGIN:X-CALENDARSERVER-PERINSTANCE
RECURRENCE-ID:20080602T120000Z
TRANSP:OPAQUE
END:X-CALENDARSERVER-PERINSTANCE
BEGIN:X-CALENDARSERVER-PERINSTANCE
RECURRENCE-ID:20080604T120000Z
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
""".replace("\n", "\r\n"),
                        (
                            (
                                None,
                                (
                                    ("", False,),
                                    ("user01", False,),
                                    ("user02", True,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 2, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                    ("user01", True,),
                                    ("user02", False,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 3, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                    ("user01", True,),
                                    ("user02", True,),
                                ),
                            ),
                            (
                                PyCalendarDateTime(2008, 6, 4, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                                (
                                    ("", False,),
                                    ("user01", False,),
                                    ("user02", True,),
                                ),
                            ),
                        ),
                    ),
                )

        for title, text, results in data:
            calendar = Component.fromString(text)
            for rid, result in results:
                self.assertEqual(calendar.perUserTransparency(rid), result, "Failed comparison: %s %s" % (title, rid,))

    def test_needsiTIPSequenceChange(self):

        data = (
            (
                "Simple old < new",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:1
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "Simple old == new",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:1
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:1
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "Simple old > new",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:2
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:1
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "Recurring same instances all old < new",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
SUMMARY:Test
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
SEQUENCE:1
SUMMARY:Test
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:2
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "Recurring same instances some old == new",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
SUMMARY:Test
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:2
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
SEQUENCE:1
SUMMARY:Test
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:2
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "Recurring derived instance all old < new",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
SEQUENCE:1
SUMMARY:Test
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:2
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "Recurring derived instance some old == new",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
SEQUENCE:2
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
RRULE:FREQ=DAILY
SEQUENCE:2
SUMMARY:Test
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SEQUENCE:2
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
        )

        for title, old_txt, new_txt, result in data:
            ical_old = Component.fromString(old_txt)
            ical_new = Component.fromString(new_txt)
            self.assertEqual(ical_new.needsiTIPSequenceChange(ical_old), result, "Failed: %s" % (title,))

    def test_bumpiTIPInfo(self):

        data = (
            (
                "Simple no sequence, no sequence change",
                None,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "Simple sequence, no sequence change",
                None,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "Simple no sequence, sequence change",
                None,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "Simple sequence, sequence change",
                None,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "Simple sequence, sequence change, old calendar",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:3
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "Recurring override no sequence, no sequence change",
                None,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "Recurring override vary sequence, no sequence change",
                None,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "Recurring override no sequence, sequence change",
                None,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "Recurring override vary sequence, sequence change",
                None,
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
SEQUENCE:3
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:3
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "Recurring override vary sequence, sequence change, old calendar",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:3
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
RRULE:FREQ=DAILY
SEQUENCE:4
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T120000Z
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
DTSTAMP:20080601T120000Z
SUMMARY:Test
SEQUENCE:4
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
        )
        
        for title, old_txt, ical_txt, result_txt, doSequence in data:
            old = Component.fromString(old_txt) if old_txt else None
            ical = Component.fromString(ical_txt)
            result = Component.fromString(result_txt)
            ical.bumpiTIPInfo(oldcalendar=old, doSequence=doSequence)
            
            ical1 = str(ical).split("\n")
            ical2 = str(result).split("\n")
            
            # Check without DTSTAMPs which we expect to be different
            ical1_withoutDTSTAMP = [item for item in ical1 if not item.startswith("DTSTAMP:")]
            ical2_withoutDTSTAMP = [item for item in ical2 if not item.startswith("DTSTAMP:")]

            diff = "\n".join(unified_diff(ical1_withoutDTSTAMP, ical2_withoutDTSTAMP))
            self.assertEqual("\n".join(ical1_withoutDTSTAMP), "\n".join(ical2_withoutDTSTAMP), "Failed comparison: %s\n%s" % (title, diff,))

            # Check that all DTSTAMPs changed    
            dtstamps1 = set([item for item in ical1 if item.startswith("DTSTAMP:")])
            dtstamps2 = set([item for item in ical2 if item.startswith("DTSTAMP:")])
            
            diff = "\n".join(unified_diff(ical1, ical2))
            self.assertEqual(len(dtstamps1 & dtstamps2), 0, "Failed comparison: %s\n%s" % (title, diff,))


    def test_hasInstancesAfter(self):
        data = (
            ("In the past (single)", False,
"""BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:8EF0EB56-186E-4A77-9753-9B5D1D067CB5
DTSTART;TZID=America/Los_Angeles:20111123T140000
DTEND;TZID=America/Los_Angeles:20111123T150000
CREATED:20111129T183822Z
DTSTAMP:20111129T183845Z
SEQUENCE:3
SUMMARY:In the past (single)
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""",
            ),
            ("In the past (repeating)", False,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:5812AF81-AB8E-484C-BE72-94DBB43C7E71
DTSTART;TZID=America/Los_Angeles:20111123T150000
DTEND;TZID=America/Los_Angeles:20111123T160000
CREATED:20111129T183850Z
DTSTAMP:20111129T184251Z
RRULE:FREQ=DAILY;COUNT=4
SEQUENCE:5
SUMMARY:In the past (repeating)
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:5812AF81-AB8E-484C-BE72-94DBB43C7E71
RECURRENCE-ID;TZID=America/Los_Angeles:20111125T150000
DTSTART;TZID=America/Los_Angeles:20111125T153000
DTEND;TZID=America/Los_Angeles:20111125T163000
CREATED:20111129T183850Z
DTSTAMP:20111129T184305Z
SEQUENCE:6
SUMMARY:In the past (repeating)
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""",
            ),
            ("Straddling (repeating)", True,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:60C25FF1-70EF-40EC-BBBB-F78F0A5FE45E
DTSTART;TZID=America/Los_Angeles:20111129T143000
DTEND;TZID=America/Los_Angeles:20111129T153000
CREATED:20111129T184427Z
DTSTAMP:20111129T184538Z
RRULE:FREQ=DAILY;COUNT=4
SEQUENCE:10
SUMMARY:Straddling (repeating)
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:60C25FF1-70EF-40EC-BBBB-F78F0A5FE45E
RECURRENCE-ID;TZID=America/Los_Angeles:20111201T143000
DTSTART;TZID=America/Los_Angeles:20111201T150000
DTEND;TZID=America/Los_Angeles:20111201T160000
CREATED:20111129T184427Z
DTSTAMP:20111129T184556Z
SEQUENCE:11
SUMMARY:Straddling (repeating)
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""",
            ),
            ("Future (single)", True,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:B79B392D-ADCC-4C61-A472-6E24BE0D72EF
DTSTART;TZID=America/Los_Angeles:20111201T140000
DTEND;TZID=America/Los_Angeles:20111201T150000
CREATED:20111129T184650Z
DTSTAMP:20111129T184655Z
SEQUENCE:2
SUMMARY:Future (single)
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""",
            ),
            ("Future (repeating)", True,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:E65FF863-D670-4C70-9537-6880739E0D34
DTSTART;TZID=America/Los_Angeles:20111202T133000
DTEND;TZID=America/Los_Angeles:20111202T143000
CREATED:20111129T184745Z
DTSTAMP:20111129T184803Z
RRULE:FREQ=DAILY;COUNT=4
SEQUENCE:5
SUMMARY:Future (repeating)
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:E65FF863-D670-4C70-9537-6880739E0D34
RECURRENCE-ID;TZID=America/Los_Angeles:20111204T133000
DTSTART;TZID=America/Los_Angeles:20111204T140000
DTEND;TZID=America/Los_Angeles:20111204T150000
CREATED:20111129T184745Z
DTSTAMP:20111129T184809Z
SEQUENCE:6
SUMMARY:Future (repeating)
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""",
            ),
            ("On the day (single)", True,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:94BAE82D-58E4-4511-9AB5-558F4873DA34
DTSTART;TZID=America/Los_Angeles:20111130T100000
DTEND;TZID=America/Los_Angeles:20111130T110000
CREATED:20111129T214043Z
DTSTAMP:20111129T214052Z
SEQUENCE:1
SUMMARY:On the day
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""",
            ),
            ("Long non-all-day straddling (single)", True,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:74B0B0A9-662F-4E2F-A0DF-ABEE1A311B92
DTSTART;TZID=America/Los_Angeles:20111129T073000
DTEND;TZID=America/Los_Angeles:20111202T083000
CREATED:20111129T214210Z
DTSTAMP:20111129T214230Z
SEQUENCE:4
SUMMARY:Long non-all-day straddling
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""",
            ),
            ("All Day in the past (repeating)", False,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VEVENT
UID:A2351816-49BD-4C5D-9399-CF5A3DBA0667
DTSTART;VALUE=DATE:20111126
DTEND;VALUE=DATE:20111127
CREATED:20111129T211012Z
DTSTAMP:20111129T211102Z
RRULE:FREQ=DAILY;COUNT=3
SEQUENCE:5
SUMMARY:All day in the past
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
            ),
            ("Straddling All Day (repeating)", True,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VEVENT
UID:B327F71E-43D5-442D-B8F4-06AC588C490A
DTSTART;VALUE=DATE:20111129
DTEND;VALUE=DATE:20111130
CREATED:20111129T212257Z
DTSTAMP:20111129T212314Z
RRULE:FREQ=DAILY;COUNT=4
SEQUENCE:5
SUMMARY:All day repeated straddling
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
            ),
            ("Straddling All Day (single multiday)", True,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VEVENT
UID:7A887675-8021-4432-A7C6-9E912339D415
DTSTART;VALUE=DATE:20111129
DTEND;VALUE=DATE:20111202
CREATED:20111129T210711Z
DTSTAMP:20111129T210734Z
SEQUENCE:3
SUMMARY:All Day Straddling
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
            ),
            ("Future All Day (single)", True,
"""
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 5.0.1//EN
BEGIN:VEVENT
UID:DE1605D9-9BD8-4382-9E12-561332455748
DTSTART;VALUE=DATE:20111203
DTEND;VALUE=DATE:20111204
CREATED:20111129T211219Z
DTSTAMP:20111129T211224Z
SEQUENCE:2
SUMMARY:Future all day
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
            ),
        )
        cutoff = PyCalendarDateTime(2011, 11, 30, 0, 0, 0)
        for title, expected, body in data:
            ical = Component.fromString(body)
            self.assertEquals(expected, ical.hasInstancesAfter(cutoff))


    def test_normalizeCalendarUserAddressesFromUUID(self):
        """
        Ensure mailto is preferred, followed by path form, then http form.
        If CALENDARSERVER-OLD-CUA parameter is present, restore that value.
        """

        data = """BEGIN:VCALENDAR
VERSION:2.0
DTSTART:20071114T000000Z
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:urn:uuid:foo
ATTENDEE:urn:uuid:bar
ATTENDEE:urn:uuid:baz
ATTENDEE;CALENDARSERVER-OLD-CUA="http://example.com/principals/users/buz":urn:uuid:buz
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
"""

        component = Component.fromString(data)

        def lookupFunction(cuaddr, ignored1, ignored2):
            return {
                "urn:uuid:foo" : (
                    "Foo",
                    "foo",
                    ("urn:uuid:foo", "http://example.com/foo", "/foo")
                ),
                "urn:uuid:bar" : (
                    "Bar",
                    "bar",
                    ("urn:uuid:bar", "mailto:bar@example.com", "http://example.com/bar", "/bar")
                ),
                "urn:uuid:baz" : (
                    "Baz",
                    "baz",
                    ("urn:uuid:baz", "http://example.com/baz")
                ),
                "urn:uuid:buz" : (
                    "Buz",
                    "buz",
                    ("urn:uuid:buz",)
                ),
            }[cuaddr]

        component.normalizeCalendarUserAddresses(lookupFunction, None, toUUID=False)

        self.assertEquals("mailto:bar@example.com",
            component.getAttendeeProperty(("mailto:bar@example.com",)).value())
        self.assertEquals("/foo",
            component.getAttendeeProperty(("/foo",)).value())
        self.assertEquals("http://example.com/baz",
            component.getAttendeeProperty(("http://example.com/baz",)).value())
        self.assertEquals("http://example.com/principals/users/buz",
            component.getAttendeeProperty(("http://example.com/principals/users/buz",)).value())


    def test_normalizeCalendarUserAddressesToUUID(self):
        """
        Ensure http(s) and /path CUA values are tucked away into the property
        using CALENDARSERVER-OLD-CUA parameter.
        """

        data = """BEGIN:VCALENDAR
VERSION:2.0
DTSTART:20071114T000000Z
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:/principals/users/foo
ATTENDEE:http://example.com/principals/users/buz
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
"""

        component = Component.fromString(data)

        def lookupFunction(cuaddr, ignored1, ignored2):
            return {
                "/principals/users/foo" : (
                    "Foo",
                    "foo",
                    ("urn:uuid:foo", )
                ),
                "http://example.com/principals/users/buz" : (
                    "Buz",
                    "buz",
                    ("urn:uuid:buz", )
                ),
            }[cuaddr]

        self.patch(config.Scheduling.Options, "V1Compatibility", True)
        component.normalizeCalendarUserAddresses(lookupFunction, None, toUUID=True)

        # /principal CUAs are not stored in CALENDARSERVER-OLD-CUA
        prop = component.getAttendeeProperty(("urn:uuid:foo",))
        self.assertEquals("urn:uuid:foo", prop.value())
        self.assertEquals(prop.parameterValue("CALENDARSERVER-OLD-CUA"),
            "/principals/users/foo")

        # http CUAs are stored in CALENDARSERVER-OLD-CUA
        prop = component.getAttendeeProperty(("urn:uuid:buz",))
        self.assertEquals("urn:uuid:buz", prop.value())
        self.assertEquals(prop.parameterValue("CALENDARSERVER-OLD-CUA"),
            "http://example.com/principals/users/buz")
