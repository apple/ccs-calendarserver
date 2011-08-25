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

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone
from twistedcaldav.ical import Component
from twistedcaldav.scheduling.itip import iTipProcessing, iTipGenerator
import os
import twistedcaldav.test.util

class iTIPProcessing (twistedcaldav.test.util.TestCase):
    """
    iCalendar support tests
    """

    def test_update_attendee_partstat(self):
        
        data = (
            (
                "#1.1 Simple component, accepted",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False),),
            ),
            (
                "#1.2 Simple component, accepted",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False),),
            ),
            (
                "#1.3 Simple component, no change",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=NEEDS-ACTION;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (),
            ),
            (
                "#2.1 Recurring component, change master/override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ATTENDEE;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False), ("20080801T120000Z", True, False),),
            ),
            (
                "#2.2 Recurring component, change master only",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False),),
            ),
            (
                "#2.3 Recurring component, change override only",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ATTENDEE;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("20080801T120000Z", True, False),),
            ),
            (
                "#3.1 Recurring component, change master/override, new override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080901T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=TENTATIVE:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ATTENDEE;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080901T120000Z
DTSTART:20080901T120000Z
DTEND:20080901T130000Z
ATTENDEE;PARTSTAT=TENTATIVE;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False), ("20080801T120000Z", True, False), ("20080901T120000Z", True, False),),
            ),
            (
                "#3.2 Recurring component, change master, new override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080901T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=TENTATIVE:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080901T120000Z
DTSTART:20080901T120000Z
DTEND:20080901T130000Z
ATTENDEE;PARTSTAT=TENTATIVE;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False), ("20080901T120000Z", True, False),),
            ),
            (
                "#3.3 Recurring component, change override, new override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080901T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=TENTATIVE:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ATTENDEE;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080901T120000Z
DTSTART:20080901T120000Z
DTEND:20080901T130000Z
ATTENDEE;PARTSTAT=TENTATIVE;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("20080801T120000Z", True, False), ("20080901T120000Z", True, False),),
            ),
            (
                "#4.1 Recurring component, invalid override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
RRULE:FREQ=MONTHLY
EXDATE:20080801T120000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user1@example.com
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
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
EXDATE:20080801T120000Z
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
END:VCALENDAR
""",
                False, "", (),
            ),
            (
                "#5.1 Invalid iTIP",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
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
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False, "", (),
            ),
            (
                "#5.2 Recurring component, different attendees in components",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user1@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user2@example.com
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
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080801T123000Z
DTEND:20080801T133000Z
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                False, "", (),
            ),
            (
                "#6.1 REQUEST-STATUS",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user1@example.com
REQUEST-STATUS:2.0;Success
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
ATTENDEE;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False),),
            ),
            (
                "#6.2 Multiple REQUEST-STATUS",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user1@example.com
REQUEST-STATUS:2.1;Success but fallback taken on one or more property values
REQUEST-STATUS:2.2;Success, invalid property ignored
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
ATTENDEE;PARTSTAT=DECLINED;SCHEDULE-STATUS="2.1,2.2":mailto:user1@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False),),
            ),
            (
                "#6.3 Bad REQUEST-STATUS",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
METHOD:REPLY
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user1@example.com
REQUEST-STATUS:2.0\;Success
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
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                True, "mailto:user1@example.com", (("", True, False),),
            ),
        )

        for description, calendar_txt, itipmsg_txt, result, success, attendee, rids in data:
            calendar = Component.fromString(calendar_txt)
            itipmsg = Component.fromString(itipmsg_txt)
            reply_success, reply_processed = iTipProcessing.processReply(itipmsg, calendar)
#            if not description.startswith("#3.1"):
#                continue
#            print description
#            print str(calendar)
#            print str(result)
            self.assertEqual(
                str(calendar).replace("\r", "").replace("\n ", ""),
                str(result).replace("\n ", ""),
                msg=description
            )
            self.assertEqual(
                reply_success,
                success,
                msg=description
            )
            if success:
                reply_attendee, reply_rids, = reply_processed
                self.assertEqual(
                    reply_attendee,
                    attendee,
                    msg=description
                )
                self.assertEqual(
                    tuple(sorted(list(reply_rids), key=lambda x:x[0])),
                    rids,
                    msg=description
                )
            else:
                self.assertEqual(
                    reply_processed,
                    None,
                    msg=description
                )

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
            itipped = iTipGenerator.generateAttendeeRequest(component, attendees, None)
            itipped = str(itipped).replace("\r", "")
            itipped = "".join([line for line in itipped.splitlines(True) if not line.startswith("DTSTAMP:")])
            self.assertEqual(filtered, itipped)

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
DTSTART:20071114T000000Z
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
DTSTART:20071114T000000Z
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
DTSTART:20081114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (PyCalendarDateTime(2008, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), ),
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
DTSTART:20081114T010000Z
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
DTSTART:20081114T010000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (PyCalendarDateTime(2008, 11, 14, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)), ),
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
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
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
