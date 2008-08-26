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

import datetime

from twistedcaldav.ical import Component
from twistedcaldav.scheduling.imip import ScheduleViaIMip
import twistedcaldav.test.util

class iMIP (twistedcaldav.test.util.TestCase):
    """
    iCalendar support tests
    """

    class DummyScheduler(object):
        def __init__(self, calendar):
            self.calendar = calendar

    def test_datetime_text(self):
        
        imip = ScheduleViaIMip(None, [], [], False)
        
        data = (
            (
                datetime.datetime(2008, 06, 01, 12, 0, 0),
                "America/New_York",
                "Sunday, June  1, 2008 12:00 PM (America/New_York)",
            ),
            (
                datetime.date(2008, 06, 02),
                "",
                "Monday, June  2, 2008",
            ),
        )
        
        for dt, tzid, result in data:
            self.assertEqual(imip._getDateTimeText(dt, tzid), result)
        
    def test_duration_text(self):
        
        imip = ScheduleViaIMip(None, [], [], False)
        
        data = (
            (
                datetime.timedelta(days=1),
                "1 day",
            ),
            (
                datetime.timedelta(days=2),
                "2 days",
            ),
            (
                datetime.timedelta(seconds=1*60*60),
                "1 hour",
            ),
            (
                datetime.timedelta(seconds=2*60*60),
                "2 hours",
            ),
            (
                datetime.timedelta(seconds=1*60),
                "1 minute",
            ),
            (
                datetime.timedelta(seconds=2*60),
                "2 minutes",
            ),
            (
                datetime.timedelta(seconds=1),
                "1 second",
            ),
            (
                datetime.timedelta(seconds=2),
                "2 seconds",
            ),
            (
                datetime.timedelta(days=1, seconds=1*60*60),
                "1 day, 1 hour",
            ),
            (
                datetime.timedelta(days=1, seconds=1*60),
                "1 day, 1 minute",
            ),
            (
                datetime.timedelta(days=1, seconds=1),
                "1 day, 1 second",
            ),
            (
                datetime.timedelta(days=1, seconds=1*60*60 + 2*60),
                "1 day, 1 hour, 2 minutes",
            ),
            (
                datetime.timedelta(seconds=2*60*60 + 15*60),
                "2 hours, 15 minutes",
            ),
        )
        
        for duration, result in data:
            self.assertEqual(imip._getDurationText(duration), result)

    def test_datetime_info(self):
        data = (
                   (
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
                        """Starts:      Sunday, June  1, 2008 12:00 PM (UTC)
Ends:        Sunday, June  1, 2008 01:00 PM (UTC)
Duration:    1 hour
""",
                    ),
                   (
                       """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART;VALUE=DATE:20080601
DTEND;VALUE=DATE:20080602
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                        """Starts:      Sunday, June  1, 2008
Ends:        Monday, June  2, 2008
Duration:    1 day
All Day
""",
                    ),
                   (
                       """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART;VALUE=DATE:20080601
DTEND;VALUE=DATE:20080602
RRULE:FREQ=YEARLY
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                        """Starts:      Sunday, June  1, 2008
Ends:        Monday, June  2, 2008
Duration:    1 day
All Day
Recurring
""",
                    ),
                )
        
        
        for data, result in data:
            imip = ScheduleViaIMip(self.DummyScheduler(Component.fromString(data)), [], [], False)
            self.assertEqual(imip._getDateTimeInfo(imip.scheduler.calendar.masterComponent()), result)
        
    def test_calendar_summary(self):
        data = (
                   (
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
SUMMARY:This is an event
END:VEVENT
END:VCALENDAR
""",
                        """---- Begin Calendar Event Summary ----

Organizer:   User 01 <mailto:user1@example.com>
Summary:     This is an event
Starts:      Sunday, June  1, 2008 12:00 PM (UTC)
Ends:        Sunday, June  1, 2008 01:00 PM (UTC)
Duration:    1 hour
Description: 

----  End Calendar Event Summary  ----
""",
                    ),
                   (
                       """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART;VALUE=DATE:20080601
DTEND;VALUE=DATE:20080602
ORGANIZER;CN="User 02":mailto:user2@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
SUMMARY:This is an event
DESCRIPTION:Testing iMIP from the calendar server.
END:VEVENT
END:VCALENDAR
""",
                        """---- Begin Calendar Event Summary ----

Organizer:   User 02 <mailto:user2@example.com>
Summary:     This is an event
Starts:      Sunday, June  1, 2008
Ends:        Monday, June  2, 2008
Duration:    1 day
All Day
Description: Testing iMIP from the calendar server.

----  End Calendar Event Summary  ----
""",
                    ),
                   (
                       """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART;VALUE=DATE:20080601
DTEND;VALUE=DATE:20080602
RRULE:FREQ=YEARLY
ORGANIZER;CN="User 03":mailto:user3@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
SUMMARY:This is an event
DESCRIPTION:Testing iMIP from the calendar server.
END:VEVENT
END:VCALENDAR
""",
                        """---- Begin Calendar Event Summary ----

Organizer:   User 03 <mailto:user3@example.com>
Summary:     This is an event
Starts:      Sunday, June  1, 2008
Ends:        Monday, June  2, 2008
Duration:    1 day
All Day
Recurring
Description: Testing iMIP from the calendar server.

----  End Calendar Event Summary  ----
""",
                    ),
                )
        
        
        for data, result in data:
            imip = ScheduleViaIMip(self.DummyScheduler(Component.fromString(data)), [], [], False)
            self.assertEqual(imip._generateCalendarSummary(imip.scheduler.calendar), result)
        
        
    def test_template_message(self):
        data = (
                   (
                       """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN=User 01:mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
SUMMARY:This is an event
END:VEVENT
END:VCALENDAR
""",
                        """From: ${fromaddress}
To: ${toaddress}
Subject: DO NOT REPLY: calendar invitation test
Mime-Version: 1.0
Content-Type: multipart/mixed;
    boundary="boundary"


--boundary
Content-Type: text/plain

Hi,
You've been invited to a cool event by CalendarServer's new iMIP processor.

---- Begin Calendar Event Summary ----

Organizer:   User 01 <mailto:user1@example.com>
Summary:     This is an event
Starts:      Sunday, June  1, 2008 12:00 PM (UTC)
Ends:        Sunday, June  1, 2008 01:00 PM (UTC)
Duration:    1 hour
Description: 

----  End Calendar Event Summary  ----


--boundary
Content-Type: text/calendar; charset=utf-8
Content-Transfer-Encoding: 7bit

BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
SUMMARY:This is an event
END:VEVENT
END:VCALENDAR

--boundary--
""",
                    ),
                   (
                       """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART;VALUE=DATE:20080601
DTEND;VALUE=DATE:20080602
ORGANIZER;CN=User 02:mailto:user2@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
SUMMARY:This is an event
DESCRIPTION:Testing iMIP from the calendar server.
END:VEVENT
END:VCALENDAR
""",
                        """From: ${fromaddress}
To: ${toaddress}
Subject: DO NOT REPLY: calendar invitation test
Mime-Version: 1.0
Content-Type: multipart/mixed;
    boundary="boundary"


--boundary
Content-Type: text/plain

Hi,
You've been invited to a cool event by CalendarServer's new iMIP processor.

---- Begin Calendar Event Summary ----

Organizer:   User 02 <mailto:user2@example.com>
Summary:     This is an event
Starts:      Sunday, June  1, 2008
Ends:        Monday, June  2, 2008
Duration:    1 day
All Day
Description: Testing iMIP from the calendar server.

----  End Calendar Event Summary  ----


--boundary
Content-Type: text/calendar; charset=utf-8
Content-Transfer-Encoding: 7bit

BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART;VALUE=DATE:20080601
DTEND;VALUE=DATE:20080602
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
DESCRIPTION:Testing iMIP from the calendar server.
ORGANIZER;CN=User 02:mailto:user2@example.com
SUMMARY:This is an event
END:VEVENT
END:VCALENDAR

--boundary--
""",
                    ),
                   (
                       """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART;VALUE=DATE:20080601
DTEND;VALUE=DATE:20080602
RRULE:FREQ=YEARLY
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 03:mailto:user3@example.com
SUMMARY:This is an event
DESCRIPTION:Testing iMIP from the calendar server.
END:VEVENT
END:VCALENDAR
""",
                        """From: ${fromaddress}
To: ${toaddress}
Subject: DO NOT REPLY: calendar invitation test
Mime-Version: 1.0
Content-Type: multipart/mixed;
    boundary="boundary"


--boundary
Content-Type: text/plain

Hi,
You've been invited to a cool event by CalendarServer's new iMIP processor.

---- Begin Calendar Event Summary ----

Organizer:   User 03 <mailto:user3@example.com>
Summary:     This is an event
Starts:      Sunday, June  1, 2008
Ends:        Monday, June  2, 2008
Duration:    1 day
All Day
Recurring
Description: Testing iMIP from the calendar server.

----  End Calendar Event Summary  ----


--boundary
Content-Type: text/calendar; charset=utf-8
Content-Transfer-Encoding: 7bit

BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART;VALUE=DATE:20080601
DTEND;VALUE=DATE:20080602
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
DESCRIPTION:Testing iMIP from the calendar server.
ORGANIZER;CN=User 03:mailto:user3@example.com
RRULE:FREQ=YEARLY
SUMMARY:This is an event
END:VEVENT
END:VCALENDAR

--boundary--
""",
                    ),
                )
        
        def _normalizeMessage(text):
            # First get rid of unwanted headers
            lines = text.split("\n")
            lines = [line for line in lines if line.split(":")[0] not in ("Date", "Message-ID",)]
            
            # Now get rid of boundary string
            boundary = None
            newlines = []
            for line in lines:
                if line.startswith("    boundary=\""):
                    boundary = line[len("    boundary=\""):-1]
                    line = line.replace(boundary, "boundary")
                if boundary and line.find(boundary) != -1:
                    line = line.replace(boundary, "boundary")
                newlines.append(line)
            return "\n".join(newlines)

        for data, result in data:
            imip = ScheduleViaIMip(self.DummyScheduler(Component.fromString(data)), [], [], False)
            self.assertEqual(_normalizeMessage(imip._generateTemplateMessage(imip.scheduler.calendar)), result)
        
