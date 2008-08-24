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

import os
import datetime
from dateutil.tz import tzutc

from twisted.trial.unittest import SkipTest

from twistedcaldav.ical import Component, parse_date, parse_datetime,\
    parse_date_or_datetime, parse_duration, Property
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

        instances = calendar.expandTimeRanges(datetime.date(2100, 1, 1))
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

        instances = calendar.expandTimeRanges(datetime.date(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            self.assertEqual(start, datetime.datetime(2004, 11, 25))
            self.assertEqual(end, datetime.datetime(2004, 11, 27))
            break;

    #test_component_timerange.todo = "recurrance expansion should give us no end date here"

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

    def test_correct_attendee_properties(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
"""

        component = Component.fromString(data)
        self.assertEqual([p.value() for p in component.getAttendeeProperties(("mailto:user2@example.com",))], ["mailto:user2@example.com",])

    def test_empty_attendee_properties(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
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
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", None),
                    ("mailto:user1@example.com", datetime.datetime(2008, 11, 14, 0, 0, tzinfo=tzutc()))
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20091114T000000Z
DTSTART:20071114T020000Z
ORGANIZER:mailto:user3@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", None),
                    ("mailto:user3@example.com", datetime.datetime(2009, 11, 14, 0, 0, tzinfo=tzutc()))
                )
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20091114T000000Z
DTSTART:20071114T020000Z
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
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
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
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
END:VEVENT
END:VCALENDAR
""",
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
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user2@example.com", None),
                    ("mailto:user2@example.com", datetime.datetime(2008, 11, 14, 0, 0, tzinfo=tzutc())),
                    ("mailto:user3@example.com", datetime.datetime(2008, 11, 14, 0, 0, tzinfo=tzutc()))
                )
            ),
        )
        
        for caldata, result in data:
            component = Component.fromString(caldata)
            self.assertEqual(component.getAttendeesByInstance(), result)

    def test_set_parameter_value(self):
        data = (
            # ATTENDEE - no existing parameter
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;SCHEDULE-STATUS="2.0;OK":mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    "SCHEDULE-STATUS",
                    "2.0;OK",
                    "ATTENDEE",
                    "mailto:user02@example.com",
                ),
            ),
            # ATTENDEE - existing parameter
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;SCHEDULE-STATUS="5.0;BAD":mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;SCHEDULE-STATUS="2.0;OK":mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    "SCHEDULE-STATUS",
                    "2.0;OK",
                    "ATTENDEE",
                    "mailto:user02@example.com",
                ),
            ),
            # ORGANIZER - no existing parameter
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ORGANIZER;SCHEDULE-STATUS="2.0;OK":mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    "SCHEDULE-STATUS",
                    "2.0;OK",
                    "ORGANIZER",
                    "mailto:user01@example.com",
                ),
            ),
            # ORGANIZER - existing parameter
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ORGANIZER;SCHEDULE-STATUS="5.0;BAD":mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ORGANIZER;SCHEDULE-STATUS="2.0;OK":mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    "SCHEDULE-STATUS",
                    "2.0;OK",
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
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
REQUEST-STATUS:2.0\;Success
END:VEVENT
END:VCALENDAR
""",
            ),
            # Complex component
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T020000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
REQUEST-STATUS:2.0\;Success
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T020000Z
REQUEST-STATUS:2.0\;Success
END:VEVENT
END:VCALENDAR
""",
            ),
        )

        for original, result in data:
            component = Component.fromString(original)
            component.addPropertyToAllComponents(Property("REQUEST-STATUS", "2.0;Success"))
            self.assertEqual(result, str(component).replace("\r", ""))        

    def test_attendees_views(self):
        
        data = (
            # Simple component, no Attendees - no filtering
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                ()
            ),

            # Simple component, no Attendees - filtering
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user01@example.com",)
            ),

            # Simple component, with one attendee - filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            # Simple component, with one attendee - no filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),

            # Recurring component with one instance, each with one attendee - filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            # Recurring component with one instance, each with one attendee - no filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),        

            # Recurring component with one instance, master with one attendee, instance without attendee - filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
EXDATE:20081114T000000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            # Recurring component with one instance, master with one attendee, instance without attendee - no filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),

            # Recurring component with one instance, master without attendee, instance with attendee - filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",)
            ),

            # Recurring component with one instance, master without attendee, instance with attendee - no filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),
        )
        
        for original, filtered, attendees in data:
            component = Component.fromString(original)
            component.attendeesView(attendees)
            self.assertEqual(filtered, str(component).replace("\r", ""))

    def test_all_but_one_attendee(self):
        
        data = (
            # One component, no attendees
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                "mailto:user02@example.com",
            ),

            # One component, one attendee - removed
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
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
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
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
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
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
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-5
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-5
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
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

    def test_remove_unwanted_properties(self):
        
        data = (
            # One component
            (
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
SUMMARY:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
ATTENDEE:mailto:user2@example.com
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
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
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
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
ATTENDEE:mailto:user2@example.com
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
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                ("UID", "RECURRENCE-ID", "SEQUENCE", "DTSTAMP", "ORGANIZER", "ATTENDEE",),
            ),

        )
        
        for original, result, keep_properties in data:
            component = Component.fromString(original)
            component.removeUnwantedProperties(keep_properties)
            self.assertEqual(result, str(component).replace("\r", ""))

    def test_remove_alarms(self):
        
        data = (
            # One component, no alarms
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
            ),

            # One component, one alarm
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
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
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
            ),

            # Multiple components, one alarm
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
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
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
            ),

            # Multiple components, multiple alarms
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
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
PRODID:-//PYVOBJECT//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
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
