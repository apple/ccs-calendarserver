##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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
from twext.web2 import responsecode
from twext.web2.test.test_server import SimpleRequest
from twisted.internet.defer import succeed, inlineCallbacks
from twistedcaldav.ical import Component
from twistedcaldav.scheduling.implicit import ImplicitScheduler
from twistedcaldav.scheduling.scheduler import ScheduleResponseQueue
from twistedcaldav.test.util import HomeTestCase
import twistedcaldav.test.util
from twext.web2.http import HTTPError

class FakeScheduler(object):
    """
    A fake CalDAVScheduler that does nothing except track who messages were sent to.
    """

    def __init__(self, recipients):
        self.recipients = recipients


    def doSchedulingViaPUT(self, originator, recipients, calendar, internal_request=False):
        self.recipients.extend(recipients)
        return succeed(ScheduleResponseQueue("FAKE", responsecode.OK))



class FakePrincipal(object):

    def __init__(self, cuaddr):
        self.cuaddr = cuaddr


    def calendarUserAddresses(self):
        return (self.cuaddr,)



class Implicit (twistedcaldav.test.util.TestCase):
    """
    iCalendar support tests
    """

    def test_removed_attendees(self):

        data = (
            (
                "#1.1 Simple component, no change",
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
                (),
            ),
            (
                "#1.2 Simple component, one removal",
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
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                (("mailto:user2@example.com", None),),
            ),
            (
                "#1.3 Simple component, two removals",
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
ATTENDEE:mailto:user3@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user2@example.com", None),
                    ("mailto:user3@example.com", None),
                ),
            ),
            (
                "#2.1 Simple recurring component, two removals",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user2@example.com", None),
                    ("mailto:user3@example.com", None),
                ),
            ),
            (
                "#2.2 Simple recurring component, add exdate",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
EXDATE:20080801T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
            (
                "#2.3 Simple recurring component, add multiple comma exdates",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
EXDATE:20080801T120000Z,20080901T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 9, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 9, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 9, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
            (
                "#2.3 Simple recurring component, add multiple comma/property exdates",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
EXDATE:20080801T120000Z,20080901T120000Z
EXDATE:20081201T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 9, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 9, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 9, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 12, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 12, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 12, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
            (
                "#3.1 Complex recurring component with same attendees, no change",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
END:VEVENT
END:VCALENDAR
""",
                (),
            ),
            (
                "#3.2 Complex recurring component with same attendees, change master/override",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user3@example.com", None),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
            (
                "#3.3 Complex recurring component with same attendees, change override",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
            (
                "#3.4 Complex recurring component with same attendees, change master",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user3@example.com", None),
                ),
            ),
            (
                "#3.5 Complex recurring component with same attendees, remove override - no exdate",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
END:VCALENDAR
""",
                (),
            ),
            (
                "#3.6 Complex recurring component with same attendees, remove override - exdate",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
EXDATE:20080801T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user3@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
            (
                "#4.1 Complex recurring component with different attendees, change master/override",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user4@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user3@example.com", None),
                    ("mailto:user4@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
            (
                "#4.2 Complex recurring component with different attendees, remove override - no exdate",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user4@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user4@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
            (
                "#4.3 Complex recurring component with different attendees, remove override - exdate",
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
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080801T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user4@example.com
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
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
RRULE:FREQ=MONTHLY
EXDATE:20080801T120000Z
END:VEVENT
END:VCALENDAR
""",
                (
                    ("mailto:user1@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user2@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                    ("mailto:user4@example.com", PyCalendarDateTime(2008, 8, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True))),
                ),
            ),
        )

        for description, calendar1, calendar2, result in data:
            scheduler = ImplicitScheduler()
            scheduler.resource = None
            scheduler.request = None
            scheduler.oldcalendar = Component.fromString(calendar1)
            scheduler.oldAttendeesByInstance = scheduler.oldcalendar.getAttendeesByInstance(True, onlyScheduleAgentServer=True)
            scheduler.oldInstances = set(scheduler.oldcalendar.getComponentInstances())
            scheduler.calendar = Component.fromString(calendar2)
            scheduler.extractCalendarData()
            scheduler.findRemovedAttendees()
            self.assertEqual(scheduler.cancelledAttendees, set(result), msg=description)


    @inlineCallbacks
    def test_process_request_excludes_includes(self):
        """
        Test that processRequests correctly excludes or includes the specified attendees.
        """

        data = (
            ((), None, 3, ("mailto:user2@example.com", "mailto:user3@example.com", "mailto:user4@example.com",),),
            (("mailto:user2@example.com",), None, 2, ("mailto:user3@example.com", "mailto:user4@example.com",),),
            ((), ("mailto:user2@example.com", "mailto:user4@example.com",) , 2, ("mailto:user2@example.com", "mailto:user4@example.com",),),
        )

        calendar = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTENDEE:mailto:user3@example.com
ATTENDEE:mailto:user4@example.com
END:VEVENT
END:VCALENDAR
"""

        for excludes, includes, result_count, result_set in data:
            scheduler = ImplicitScheduler()
            scheduler.resource = None
            scheduler.request = None
            scheduler.calendar = Component.fromString(calendar)
            scheduler.state = "organizer"
            scheduler.action = "modify"
            scheduler.calendar_owner = None
            scheduler.internal_request = True
            scheduler.except_attendees = excludes
            scheduler.only_refresh_attendees = includes
            scheduler.changed_rids = None
            scheduler.reinvites = None

            # Get some useful information from the calendar
            yield scheduler.extractCalendarData()
            scheduler.organizerPrincipal = FakePrincipal(scheduler.organizer)

            recipients = []

            def makeFakeScheduler():
                return FakeScheduler(recipients)
            scheduler.makeScheduler = makeFakeScheduler

            count = (yield scheduler.processRequests())
            self.assertEqual(count, result_count)
            self.assertEqual(len(recipients), result_count)
            self.assertEqual(set(recipients), set(result_set))



class ImplicitRequests (HomeTestCase):
    """
    Test twistedcaldav.scheduyling.implicit with a Request object.
    """

    @inlineCallbacks
    def test_testImplicitSchedulingPUT_ScheduleState(self):
        """
        Test that checkImplicitState() always returns True for any organizer, valid or not.
        """

        data = (
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
""",
                False,
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:wsanchez@example.com
ATTENDEE:mailto:wsanchez@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
            (
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:bogus@bogus.com
ATTENDEE:mailto:wsanchez@example.com
ATTENDEE:mailto:bogus@bogus.com
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
        )

        for calendar, result in data:
            calendar = Component.fromString(calendar)

            request = SimpleRequest(self.site, "PUT", "/calendar/1.ics")
            calresource = yield request.locateResource("/calendar/1.ics")
            self.assertEqual(calresource.isScheduleObject, None)

            scheduler = ImplicitScheduler()
            doAction, isScheduleObject = (yield scheduler.testImplicitSchedulingPUT(request, calresource, "/calendar/1.ics", calendar, False))
            self.assertEqual(doAction, result)
            self.assertEqual(isScheduleObject, result)
            request._newStoreTransaction.abort()


    @inlineCallbacks
    def test_testImplicitSchedulingPUT_FixScheduleState(self):
        """
        Test that testImplicitSchedulingPUT will fix an old cached schedule object state by
        re-evaluating the calendar data.
        """

        request = SimpleRequest(self.site, "PUT", "/calendar/1.ics")
        calresource = yield request.locateResource("/calendar/1.ics")
        self.assertEqual(calresource.isScheduleObject, None)
        calresource.isScheduleObject = False

        calendarOld = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 02":mailto:user2@example.com
ATTENDEE:mailto:wsanchez@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""")

        calendarNew = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 02":mailto:user2@example.com
ATTENDEE:mailto:wsanchez@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""")

        calresource.exists = lambda : True
        calresource.iCalendarForUser = lambda request: succeed(calendarOld)

        scheduler = ImplicitScheduler()
        try:
            doAction, isScheduleObject = (yield scheduler.testImplicitSchedulingPUT(request, calresource, "/calendars/users/user01/calendar/1.ics", calendarNew, False))
        except:
            self.fail("Exception must not be raised")
        self.assertTrue(doAction)
        self.assertTrue(isScheduleObject)


    @inlineCallbacks
    def test_testImplicitSchedulingPUT_NoChangeScheduleState(self):
        """
        Test that testImplicitSchedulingPUT will prevent attendees from changing the
        schedule object state.
        """

        request = SimpleRequest(self.site, "PUT", "/calendar/1.ics")
        calresource = yield request.locateResource("/calendar/1.ics")
        self.assertEqual(calresource.isScheduleObject, None)
        calresource.isScheduleObject = False

        calendarOld = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
""")

        calendarNew = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 02":mailto:user2@example.com
ATTENDEE:mailto:wsanchez@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""")

        calresource.exists = lambda : True
        calresource.iCalendarForUser = lambda request: succeed(calendarOld)

        scheduler = ImplicitScheduler()
        try:
            yield scheduler.testImplicitSchedulingPUT(request, calresource, "/calendars/users/user01/calendar/1.ics", calendarNew, False)
        except HTTPError:
            pass
        except:
            self.fail("HTTPError exception must be raised")
        else:
            self.fail("Exception must be raised")
        request._newStoreTransaction.abort()
