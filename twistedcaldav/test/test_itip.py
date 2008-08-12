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

from twistedcaldav.ical import Component
from twistedcaldav.itip import iTipGenerator
import twistedcaldav.test.util
from dateutil.tz import tzutc
import datetime
import os

class iTIPGenerator (twistedcaldav.test.util.TestCase):
    """
    iCalendar support tests
    """
    data_dir = os.path.join(os.path.dirname(__file__), "data")

    def test_request(self):
        
        data = (
            # Simple component, no Attendees - no filtering
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user01@example.com",)
            ),

            # Simple component, with one attendee - filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),

            # Recurring component with one instance, each with one attendee - filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),        

            # Recurring component with one instance, master with one attendee, instance without attendee - filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),

            # Recurring component with one instance, master without attendee, instance with attendee - filtering match
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""",
                ("mailto:user3@example.com",)
            ),
        )
        
        for original, filtered, attendees in data:
            component = Component.fromString(original)
            itipped = iTipGenerator.generateAttendeeRequest(component, attendees)
            self.assertEqual(filtered, str(itipped).replace("\r", ""))

    def test_cancel(self):
        
        data = (
            # Simple component, with two attendees - cancel one
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:CANCEL
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (None,),
            ),

            # Simple component, with two attendees - cancel two
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
ORGANIZER:mailto:user1@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:CANCEL
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2
ATTENDEE:mailto:user3@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user3@example.com", "mailto:user2@example.com",),
                (None,)
            ),

            # Recurring component with no instance, one attendee - cancel instance
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:CANCEL
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-3
RECURRENCE-ID:20081114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (datetime.datetime(2008, 11, 14, 0, 0, tzinfo=tzutc()), ),
            ),

            # Recurring component with one instance, each with one attendee - cancel instance
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-4
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:CANCEL
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
RECURRENCE-ID:20081114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (datetime.datetime(2008, 11, 14, 0, 0, tzinfo=tzutc()), ),
            ),

            # Recurring component with one instance, each with one attendee - cancel master
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-5
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-5
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:CANCEL
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-5
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (None, ),
            ),
        )
        
        for original, filtered, attendees, instances in data:
            component = Component.fromString(original)
            itipped = iTipGenerator.generateCancel(component, attendees, instances)
            itipped = str(itipped).replace("\r", "")
            itipped = "".join([line for line in itipped.splitlines(True) if not line.startswith("DTSTAMP:")])
            self.assertEqual(filtered, itipped)
