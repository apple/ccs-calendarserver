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
from twext.web2.http import HTTPError

from twisted.internet.defer import succeed, inlineCallbacks

from twistedcaldav.ical import Component

from txdav.caldav.datastore.scheduling.implicit import ImplicitScheduler
from txdav.caldav.datastore.scheduling.scheduler import ScheduleResponseQueue

import twistedcaldav.test.util
from txdav.common.datastore.test.util import CommonCommonTests, buildStore, \
    populateCalendarsFrom
from twisted.trial.unittest import TestCase
from twext.python.clsprop import classproperty
from txdav.caldav.datastore.sql import CalendarPrincipal
import hashlib
from txdav.caldav.icalendarstore import AttendeeAllowedError
import sys

class FakeScheduler(object):
    """
    A fake CalDAVScheduler that does nothing except track who messages were sent to.
    """

    def __init__(self, recipients):
        self.recipients = recipients


    def doSchedulingViaPUT(self, originator, recipients, calendar, internal_request=False):
        self.recipients.extend(recipients)
        return succeed(ScheduleResponseQueue("FAKE", responsecode.OK))



class FakeCalendarHome(object):

    def principalForUID(self, uid):
        return CalendarPrincipal(uid, ("urn:uuid:%s" % (uid,), "mailto:%s@example.com" % (uid,),))



class Implicit (twistedcaldav.test.util.TestCase):
    """
    iCalendar support tests
    """

    @inlineCallbacks
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
            scheduler.oldcalendar = Component.fromString(calendar1)
            scheduler.oldAttendeesByInstance = scheduler.oldcalendar.getAttendeesByInstance(True, onlyScheduleAgentServer=True)
            scheduler.oldInstances = set(scheduler.oldcalendar.getComponentInstances())
            scheduler.calendar = Component.fromString(calendar2)

            scheduler.calendar_home = FakeCalendarHome()
            scheduler.calendar_owner = "user01"

            yield scheduler.extractCalendarData()
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
            scheduler.calendar = Component.fromString(calendar)
            scheduler.state = "organizer"
            scheduler.action = "modify"
            scheduler.internal_request = True
            scheduler.except_attendees = excludes
            scheduler.only_refresh_attendees = includes
            scheduler.changed_rids = None
            scheduler.reinvites = None

            scheduler.calendar_home = FakeCalendarHome()
            scheduler.calendar_owner = "user01"

            # Get some useful information from the calendar
            yield scheduler.extractCalendarData()
            scheduler.organizerPrincipal = CalendarPrincipal(scheduler.organizer, scheduler.organizer)

            recipients = []

            def makeFakeScheduler():
                return FakeScheduler(recipients)
            scheduler.makeScheduler = makeFakeScheduler

            count = (yield scheduler.processRequests())
            self.assertEqual(count, result_count)
            self.assertEqual(len(recipients), result_count)
            self.assertEqual(set(recipients), set(result_set))



class ImplicitRequests (CommonCommonTests, TestCase):
    """
    Test twistedcaldav.scheduyling.implicit with a Request object.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(ImplicitRequests, self).setUp()
        self._sqlCalendarStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user02": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
    }


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


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
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
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
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:bogus@bogus.com
END:VEVENT
END:VCALENDAR
""",
                True,
            ),
        )

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        for calendar, result in data:
            calendar = Component.fromString(calendar)

            scheduler = ImplicitScheduler()
            doAction, isScheduleObject = (yield scheduler.testImplicitSchedulingPUT(calendar_collection, None, calendar, False))
            self.assertEqual(doAction, result)
            self.assertEqual(isScheduleObject, result)


    @inlineCallbacks
    def test_testImplicitSchedulingPUT_FixScheduleState(self):
        """
        Test that testImplicitSchedulingPUT will fix an old cached schedule object state by
        re-evaluating the calendar data.
        """

        calendarOld = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""")

        calendarNew = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""")

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calresource = (yield calendar_collection.createCalendarObjectWithName(
            "1.ics", calendarOld
        ))
        calresource.isScheduleObject = False

        scheduler = ImplicitScheduler()
        try:
            doAction, isScheduleObject = (yield scheduler.testImplicitSchedulingPUT(calendar_collection, calresource, calendarNew, False))
        except Exception as e:
            print e
            self.fail("Exception must not be raised")
        self.assertTrue(doAction)
        self.assertTrue(isScheduleObject)


    @inlineCallbacks
    def test_testImplicitSchedulingPUT_NoChangeScheduleState(self):
        """
        Test that testImplicitSchedulingPUT will prevent attendees from changing the
        schedule object state.
        """

        calendarOld = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
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
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 02":mailto:user02@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""")

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calresource = (yield calendar_collection.createCalendarObjectWithName(
            "1.ics", calendarOld
        ))
        calresource.isScheduleObject = False

        scheduler = ImplicitScheduler()
        try:
            yield scheduler.testImplicitSchedulingPUT(calendar_collection, calresource, calendarNew, False)
        except HTTPError:
            pass
        except:
            self.fail("HTTPError exception must be raised")
        else:
            self.fail("Exception must be raised")


    @inlineCallbacks
    def test_doImplicitScheduling_NewOrganizerEvent(self):
        """
        Test that doImplicitScheduling delivers scheduling messages to attendees.
        """

        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        calendar_collection2 = (yield self.calendarUnderTest(home="user02"))
        items = (yield calendar_collection2.listCalendarObjects())
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].startswith(hashlib.md5("12345-67890").hexdigest()))
        inbox2 = (yield self.calendarUnderTest(name="inbox", home="user02"))
        items = (yield inbox2.listCalendarObjects())
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].startswith(hashlib.md5("12345-67890").hexdigest()))


    @inlineCallbacks
    def test_doImplicitScheduling_UpdateOrganizerEvent(self):
        """
        Test that doImplicitScheduling delivers scheduling messages to attendees.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""
        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T130000Z
DTEND:20080601T140000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01"))
        calendar = Component.fromString(data2)
        yield calendar_resource.setComponent(calendar)
        yield self.commit()

        calendar_collection2 = (yield self.calendarUnderTest(home="user02"))
        items = (yield calendar_collection2.listCalendarObjects())
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].startswith(hashlib.md5("12345-67890").hexdigest()))
        inbox2 = (yield self.calendarUnderTest(name="inbox", home="user02"))
        items = (yield inbox2.listCalendarObjects())
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0].startswith(hashlib.md5("12345-67890").hexdigest()))
        self.assertTrue(items[1].startswith(hashlib.md5("12345-67890").hexdigest()))


    @inlineCallbacks
    def test_doImplicitScheduling_DeleteOrganizerEvent(self):
        """
        Test that doImplicitScheduling delivers scheduling messages to attendees.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""
        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T120000Z
DTSTART:20080601T130000Z
DTEND:20080601T140000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01"))
        calendar = Component.fromString(data2)
        yield calendar_resource.remove()
        yield self.commit()

        calendar_collection2 = (yield self.calendarUnderTest(home="user02"))
        items = (yield calendar_collection2.listCalendarObjects())
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].startswith(hashlib.md5("12345-67890").hexdigest()))
        inbox2 = (yield self.calendarUnderTest(name="inbox", home="user02"))
        items = (yield inbox2.listCalendarObjects())
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0].startswith(hashlib.md5("12345-67890").hexdigest()))
        self.assertTrue(items[1].startswith(hashlib.md5("12345-67890").hexdigest()))


    @inlineCallbacks
    def test_doImplicitScheduling_AttendeeEventNoOrganizerEvent(self):
        """
        Test that doImplicitScheduling handles an attendee reply with no organizer event.
        """

        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-no-organizer
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""
        calendar_collection = (yield self.calendarUnderTest(home="user02"))
        calendar = Component.fromString(data)
        try:
            yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        except AttendeeAllowedError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
        yield self.commit()

        calendar_collection = (yield self.calendarUnderTest(home="user02"))
        calendar = Component.fromString(data)

        inbox1 = (yield self.calendarUnderTest(name="inbox", home="user01"))
        items = (yield inbox1.listCalendarObjects())
        self.assertEqual(len(items), 0)


    @inlineCallbacks
    def test_doImplicitScheduling_AttendeeReply(self):
        """
        Test that doImplicitScheduling delivers scheduling messages to attendees who can then reply.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""
        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar1 = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar1)
        yield self.commit()

        calendar_resource1 = (yield self.calendarObjectUnderTest(name="test.ics", home="user01"))
        calendar1 = (yield calendar_resource1.component())
        self.assertTrue("SCHEDULE-STATUS=1.2" in str(calendar1).replace("\r\n ", ""))

        inbox2 = (yield self.calendarUnderTest(name="inbox", home="user02"))
        items = (yield inbox2.listCalendarObjects())
        self.assertEqual(len(items), 1)
        yield self.commit()

        calendar_collection2 = (yield self.calendarUnderTest(home="user02"))
        items = (yield calendar_collection2.listCalendarObjects())
        calendar_resource2 = (yield self.calendarObjectUnderTest(name=items[0], home="user02",))
        calendar2 = Component.fromString(data2)
        yield calendar_resource2.setComponent(calendar2)
        yield self.commit()

        inbox1 = (yield self.calendarUnderTest(name="inbox", home="user01"))
        items = (yield inbox1.listCalendarObjects())
        self.assertEqual(len(items), 1)

        calendar_resource1 = (yield self.calendarObjectUnderTest(name="test.ics", home="user01"))
        calendar1 = (yield calendar_resource1.component())
        self.assertTrue("SCHEDULE-STATUS=2.0" in str(calendar1).replace("\r\n ", ""))
        self.assertTrue("PARTSTAT=ACCEPTED" in str(calendar1).replace("\r\n ", ""))
