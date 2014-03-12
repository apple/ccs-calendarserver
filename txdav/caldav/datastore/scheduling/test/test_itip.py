##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
from __future__ import print_function

from pycalendar.datetime import DateTime
from pycalendar.timezone import Timezone

from twisted.trial import unittest

from twistedcaldav.stdconfig import config
from twistedcaldav.ical import Component

from txdav.caldav.datastore.scheduling.itip import iTipProcessing, iTipGenerator

import os

hasattr(config, "Scheduling")   # Quell pyflakes

class iTIPProcessing (unittest.TestCase):
    """
    iCalendar support tests
    """

    def test_processRequest_mergeAttendeePartstat(self):
        """
        Test iTIPProcessing.processRequest properly preserves attendee PARTSTAT when there is no date change
        """

        data = (
            (
                "1.1 Simple Request - summary change only, partstats match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test1
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
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test1
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.2 Simple Request - summary change only, partstat mismatch",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test1
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
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test1
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.3 Simple Request - date change, partstats match",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
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
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
            ),
            (
                "1.4 Simple Request - date change, partstat mismatch",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
            ),
        )

        for title, calendar_txt, itip_txt, changed_txt in data:
            calendar = Component.fromString(calendar_txt)
            itip = Component.fromString(itip_txt)
            changed = Component.fromString(changed_txt)

            result, _ignore = iTipProcessing.processRequest(itip, calendar, "mailto:user02@example.com")
            self.assertEqual(result, changed, msg="Calendar mismatch: %s" % (title,))


    def test_processRequest_scheduleAgentChange(self):
        """
        Test iTIPProcessing.processRequest properly replaces a SCHEDULE-AGENT=CLIENT component with a
        SCHEDULE-AGENT=SERVER one.
        """

        data = (
            (
                "1.1 Simple Reply - non recurring",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ORGANIZER;SCHEDULE-AGENT=CLIENT:mailto:user01@example.com
SUMMARY:Test - original
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test - update
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
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test - update
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
            ),
        )

        for title, calendar_txt, itip_txt, changed_txt in data:
            calendar = Component.fromString(calendar_txt)
            itip = Component.fromString(itip_txt)
            changed = Component.fromString(changed_txt)

            result, rids = iTipProcessing.processRequest(itip, calendar, "mailto:user02@example.com")
            self.assertEqual(len(rids), 0)
            self.assertEqual(result, changed, msg="Calendar mismatch: %s" % (title,))


    def test_processReply(self):
        """
        Test iTIPProcessing.processReply
        """

        data = (
            (
                "1.1 Simple Reply - non recurring",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "1.2 Simple Reply - recurring no overrides",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
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
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user02@example.com
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "1.3 Simple Reply - recurring with missing master",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071114T000000Z
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071114T000000Z
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071114T000000Z
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "1.4 Simple Reply - recurring with missing master, invalid override",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071114T000000Z
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071115T000000Z
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
ORGANIZER:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""",
                None,
                False,
            ),
        )

        for title, calendar_txt, itip_txt, changed_txt, expected in data:
            calendar = Component.fromString(calendar_txt)
            itip = Component.fromString(itip_txt)
            if expected:
                changed = Component.fromString(changed_txt)

            result, _ignore = iTipProcessing.processReply(itip, calendar)
            self.assertEqual(result, expected, msg="Result mismatch: %s" % (title,))
            if expected:
                self.assertEqual(changed, calendar, msg="Calendar mismatch: %s" % (title,))


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
                    tuple(sorted(list(reply_rids), key=lambda x: x[0])),
                    rids,
                    msg=description
                )
            else:
                self.assertEqual(
                    reply_processed,
                    None,
                    msg=description
                )


    def test_sequenceComparison(self):
        """
        Test iTIPProcessing.sequenceComparison
        """

        data = (
            (
                "1.1 Simple Update - SEQUENCE change",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "1.2 Simple Update - DTSTAMP change",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T010000Z
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "1.3 Simple Update - no change",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "2.1 Recurrence add changed SEQUENCE instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T010000Z
DTSTAMP:20071114T010000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "2.2 Recurrence add changed DTSTAMP instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "2.3 Recurrence add unchanged instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071115T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T000000Z
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "3.1 Recurrence master/no-master changed SEQUENCE instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:CANCEL
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "3.2 Recurrence master/no-master old SEQUENCE instance no prior instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:CANCEL
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "3.3 Recurrence master/no-master old SEQUENCE instance with prior instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
SEQUENCE:2
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:CANCEL
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "4.1 Recurrence no-master/master changed SEQUENCE master",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:0
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHID:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "4.2 Recurrence no-master/master changed DTSTAMP master",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T000000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHID:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T010000Z
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "4.3 Recurrence no-master/master old SEQUENCE instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHID:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                "4.4 Recurrence no-master/master changed SEQUENCE instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:0
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHID:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
DTSTART:20071114T000000Z
DTSTAMP:20071114T000000Z
RRULE:FREQ=DAILY
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "5.1 Recurrence no-masters changed SEQUENCE same instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:0
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHID:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "5.2 Recurrence no-masters changed DTSTAMP same instance",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:0
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHID:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T020000Z
SEQUENCE:0
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                "5.3 Recurrence no-masters changed SEQUENCE different instances",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071116T000000Z
DTSTART:20071116T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:0
END:VEVENT
END:VCALENDAR
""",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHID:REQUEST
BEGIN:VEVENT
UID:12345-67890-1
RECURRENCE-ID:20071117T000000Z
DTSTART:20071117T000000Z
DTSTAMP:20071114T010000Z
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
        )

        for title, calendar_txt, itip_txt, expected in data:
            calendar = Component.fromString(calendar_txt)
            itip = Component.fromString(itip_txt)

            result = iTipProcessing.sequenceComparison(itip, calendar)
            self.assertEqual(result, expected, msg="Result mismatch: %s" % (title,))



class iTIPGenerator (unittest.TestCase):
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
SEQUENCE:1
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
SEQUENCE:1
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
SEQUENCE:1
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
SEQUENCE:2
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
SEQUENCE:2
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
SEQUENCE:3
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
SEQUENCE:1
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
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (DateTime(2008, 11, 14, 0, 0, 0, tzid=Timezone(utc=True)),),
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
SEQUENCE:1
END:VEVENT
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
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (DateTime(2008, 11, 14, 0, 0, 0, tzid=Timezone(utc=True)),),
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
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-5
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T010000Z
ATTENDEE:mailto:user2@example.com
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
UID:12345-67890-5
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=YEARLY
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""",
                ("mailto:user2@example.com",),
                (None,),
            ),

            # Recurring component - cancel non-existent instance
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-4
DTSTART:20071114T000000Z
ATTENDEE:mailto:user2@example.com
ORGANIZER:mailto:user1@example.com
RRULE:FREQ=DAILY;COUNT=10
SEQUENCE:1
END:VEVENT
END:VCALENDAR
""",
                "",
                ("mailto:user2@example.com",),
                (DateTime(2008, 12, 14, 0, 0, 0, tzid=Timezone(utc=True)),),
            ),

        )

        for original, filtered, attendees, instances in data:
            component = Component.fromString(original)
            itipped = iTipGenerator.generateCancel(component, attendees, instances)
            itipped = str(itipped).replace("\r", "") if itipped else ""
            itipped = "".join([line for line in itipped.splitlines(True) if not line.startswith("DTSTAMP:")])
            self.assertEqual(filtered, itipped)


    def test_missingAttendee(self):
        """
        When generating a reply, remove all components that are missing
        the ATTENDEE
        """

        original = """BEGIN:VCALENDAR
VERSION:2.0
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
UID:04405DDD-C938-46FC-A4CE-8573613BEA39
DTEND;TZID=America/Los_Angeles:20100826T130000
TRANSP:TRANSPARENT
SUMMARY:Missing attendee in master
DTSTART;TZID=America/Los_Angeles:20100826T130000
DTSTAMP:20101115T160533Z
ORGANIZER;CN="The Organizer":mailto:organizer@example.com
SEQUENCE:0
END:VEVENT
BEGIN:VEVENT
DTEND;TZID=America/Los_Angeles:20101007T120000
TRANSP:OPAQUE
UID:04405DDD-C938-46FC-A4CE-8573613BEA39
DTSTAMP:20101005T213326Z
X-APPLE-NEEDS-REPLY:TRUE
SEQUENCE:24
RECURRENCE-ID;TZID=America/Los_Angeles:20100826T130000
SUMMARY:Missing attendee in master
DTSTART;TZID=America/Los_Angeles:20101007T113000
CREATED:20100820T235846Z
ORGANIZER;CN="The Organizer":mailto:organizer@example.com
ATTENDEE;CN="Attendee 1";CUTYPE=INDIVIDUAL;EMAIL="attendee1@example.com";
 PARTSTAT=NEEDS-ACTION;ROLE=OPT-PARTICIPANT;RSVP=TRUE:mailto:attendee1@ex
 ample.com
ATTENDEE;CN="Attendee 2";CUTYPE=INDIVIDUAL;EMAIL="attendee2@example.com";
 PARTSTAT=NEEDS-ACTION;ROLE=OPT-PARTICIPANT;RSVP=TRUE:mailto:attendee2@ex
 ample.com
ATTENDEE;CN="Missing Attendee";CUTYPE=INDIVIDUAL;EMAIL="missing@example.com";
 PARTSTAT=NEEDS-ACTION;ROLE=OPT-PARTICIPANT;RSVP=TRUE:mailto:missing@ex
 ample.com
END:VEVENT
END:VCALENDAR
"""

        filtered = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
UID:04405DDD-C938-46FC-A4CE-8573613BEA39
RECURRENCE-ID;TZID=America/Los_Angeles:20100826T130000
DTSTART;TZID=America/Los_Angeles:20101007T113000
DTEND;TZID=America/Los_Angeles:20101007T120000
ATTENDEE;CN=Missing Attendee;CUTYPE=INDIVIDUAL;EMAIL=missing@example.com;P
 ARTSTAT=DECLINED;ROLE=OPT-PARTICIPANT;RSVP=TRUE:mailto:missing@example.co
 m
ORGANIZER;CN=The Organizer:mailto:organizer@example.com
REQUEST-STATUS:2.0;Success
SEQUENCE:24
SUMMARY:Missing attendee in master
END:VEVENT
END:VCALENDAR
"""
        component = Component.fromString(original)
        itipped = iTipGenerator.generateAttendeeReply(component, "mailto:missing@example.com", force_decline=True)
        itipped = str(itipped).replace("\r", "")
        itipped = "".join([line for line in itipped.splitlines(True) if not line.startswith("DTSTAMP:")])
        self.assertEqual(filtered, itipped)
