##
# Copyright (c) 2011 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

"""
Benchmark a server's handling of events with a bounded recurrence.
"""

from uuid import uuid4
from itertools import count
from datetime import datetime, timedelta

from _event_create import formatDate, measure as _measure

DAILY_EVENT = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.3//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:EDT
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:EST
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20110223T184640Z
UID:%(UID)s
DTEND;TZID=America/New_York:%(DTEND)s
RRULE:FREQ=DAILY;INTERVAL=1;UNTIL=%(UNTIL)s
TRANSP:OPAQUE
SUMMARY:A meeting which occurs daily for several days.
DTSTART;TZID=America/New_York:%(DTSTART)s
DTSTAMP:20110223T184658Z
SEQUENCE:5
END:VEVENT
END:VCALENDAR
"""

def makeEvent(i):
    """
    Create a new half-hour long event that starts soon and recurs
    daily for the next five days.
    """
    now = datetime.now()
    start = now.replace(minute=15, second=0, microsecond=0) + timedelta(hours=i)
    end = start + timedelta(minutes=30)
    until = start + timedelta(days=5)
    return DAILY_EVENT % {
        'DTSTART': formatDate(start),
        'DTEND': formatDate(end),
        'UNTIL': formatDate(until),
        'UID': uuid4(),
        }


def measure(host, port, dtrace, attendeeCount, samples):
    calendar = "bounded-recurrence"
    organizerSequence = 1

    # An infinite stream of recurring VEVENTS to PUT to the server.
    events = ((i, makeEvent(i)) for i in count(2))

    return _measure(
        calendar, organizerSequence, events,
        host, port, dtrace, samples)
