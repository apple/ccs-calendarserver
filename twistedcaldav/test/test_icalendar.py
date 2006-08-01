##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

import os
import datetime

from twisted.trial.unittest import SkipTest
from twisted.web2.dav import davxml

from twistedcaldav.ical import *
import twistedcaldav.test.util

from vobject.icalendar import utc

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

    def test_component_equality(self):
        for filename in (
            os.path.join(self.data_dir, "Holidays", "C318A4BA-1ED0-11D9-A5E0-000A958A3252.ics"),
            os.path.join(self.data_dir, "Holidays.ics"),
        ):
            data = file(filename).read()

            calendar1 = Component.fromString(data)
            calendar2 = Component.fromString(data)

            self.assertEqual(calendar1, calendar2)

    def test_component_validate(self):
        """
        CalDAV resource validation.
        """
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays.ics")))
        try: calendar.validateForCalDAV()
        except ValueError: pass
        else: self.fail("Monolithic iCalendar shouldn't validate for CalDAV")

        resource_dir = os.path.join(self.data_dir, "Holidays")
        for filename in resource_dir:
            if os.path.splitext(filename)[1] != ".ics": continue
            filename = os.path.join(resource_dir, filename)

            calendar = Component.fromStream(file(filename))
            try: calendar.validateForCalDAV()
            except ValueError: self.fail("Resource iCalendar %s didn't validate for CalDAV" % (filename,))

    def test_component_timeranges(self):
        """
        Component time range query.
        """
        #
        # This event is the Independence Day
        #
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays", "C318A4BA-1ED0-11D9-A5E0-000A958A3252.ics")))

        year = 2004

        instances = calendar.expandTimeRanges(datetime.date(2100, 0, 0))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            # FIXME: This logic is wrong
            self.assertEqual(start, datetime.datetime(year, 7, 4))
            self.assertEqual(end  , datetime.datetime(year, 7, 5))
            if year == 2050: break
            year += 1

        self.assertEqual(year, 2050)

        #
        # This event is the Thanksgiving holiday (2 days)
        #
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays", "C318ABFE-1ED0-11D9-A5E0-000A958A3252.ics")))

        year = 2004

        instances = calendar.expandTimeRanges(datetime.date(2100, 0, 0))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            # FIXME: This logic is wrong: we want the 3rd Thursday and Friday
            self.assertEqual(start, datetime.datetime(year, 11, 25))
            self.assertEqual(end  , datetime.datetime(year, 11, 27))
            if year == 2050: break
            year += 1

        self.assertEqual(year, 2050)

        #
        # This event is Father's Day
        #
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays", "C3186426-1ED0-11D9-A5E0-000A958A3252.ics")))

        year = 2002

        instances = calendar.expandTimeRanges(datetime.date(2100, 0, 0))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            # FIXME: This logic is wrong: we want the 3rd Sunday of June
            self.assertEqual(start, datetime.datetime(year, 6, 16))
            self.assertEqual(end  , datetime.datetime(year, 6, 17))
            if year == 2050: break
            year += 1

        self.assertEqual(year, 2050)

    test_component_timeranges.todo = "recurrance expansion should give us annual date pairs here"

    def test_component_timerange(self):
        """
        Component summary time range query.
        """
        calendar = Component.fromStream(file(os.path.join(self.data_dir, "Holidays", "C318ABFE-1ED0-11D9-A5E0-000A958A3252.ics")))

        instances = calendar.expandTimeRanges(datetime.date(2100, 0, 0))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            self.assertEqual(start, datetime.datetime(2004, 11, 25))
            self.assertEqual(end, datetime.datetime(2004, 11, 27))
            break;

    test_component_timerange.todo = "recurrance expansion should give us no end date here"

    def test_parse_date(self):
        """
        parse_date()
        """
        self.assertEqual(parse_date("19970714"), datetime.date(1997, 7, 14))

    def test_parse_datetime(self):
        """
        parse_datetime()
        """
        try: parse_datetime("19980119T2300")
        except ValueError: pass
        else: self.fail("Invalid DATE-TIME should raise ValueError")

        dt = parse_datetime("19980118T230000")
        self.assertEqual(dt, datetime.datetime(1998, 1, 18, 23, 0))
        self.assertNot(dt.tzinfo)

        dt = parse_datetime("19980119T070000Z")
        self.assertEqual(dt, datetime.datetime(1998, 1, 19, 07, 0, tzinfo=utc))

    def test_parse_date_or_datetime(self):
        """
        parse_date_or_datetime()
        """
        self.assertEqual(parse_date_or_datetime("19970714"), datetime.date(1997, 7, 14))

        try: parse_date_or_datetime("19980119T2300")
        except ValueError: pass
        else: self.fail("Invalid DATE-TIME should raise ValueError")

        dt = parse_date_or_datetime("19980118T230000")
        self.assertEqual(dt, datetime.datetime(1998, 1, 18, 23, 0))
        self.assertNot(dt.tzinfo)

        dt = parse_date_or_datetime("19980119T070000Z")
        self.assertEqual(dt, datetime.datetime(1998, 1, 19, 07, 0, tzinfo=utc))

    def test_parse_duration(self):
        """
        parse_duration()
        """
        self.assertEqual(parse_duration( "P15DT5H0M20S"), datetime.timedelta(days= 15, hours= 5, minutes=0, seconds= 20))
        self.assertEqual(parse_duration("+P15DT5H0M20S"), datetime.timedelta(days= 15, hours= 5, minutes=0, seconds= 20))
        self.assertEqual(parse_duration("-P15DT5H0M20S"), datetime.timedelta(days=-15, hours=-5, minutes=0, seconds=-20))

        self.assertEqual(parse_duration("P7W"), datetime.timedelta(weeks=7))
