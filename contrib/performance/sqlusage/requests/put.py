##
# Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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

from caldavclientlibrary.protocol.url import URL
from contrib.performance.sqlusage.requests.httpTests import HTTPTestBase
from pycalendar.datetime import PyCalendarDateTime
from twext.web2.dav.util import joinURL

ICAL = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VTIMEZONE
LAST-MODIFIED:20040110T032845Z
TZID:US/Eastern
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:%d0101T100000
DURATION:PT1H
SUMMARY:event 1
UID:put-ics
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

class PutTest(HTTPTestBase):
    """
    A PUT operation (non-invite)
    """

    def doRequest(self):
        """
        Execute the actual HTTP request.
        """

        now = PyCalendarDateTime.getNowUTC()
        href = joinURL(self.sessions[0].calendarHref, "put.ics")
        self.sessions[0].writeData(URL(path=href), ICAL % (now.getYear() + 1,), "text/calendar")


    def cleanup(self):
        """
        Do some cleanup after the real request.
        """
        # Remove created resources
        href = joinURL(self.sessions[0].calendarHref, "put.ics")
        self.sessions[0].deleteResource(URL(path=href))
