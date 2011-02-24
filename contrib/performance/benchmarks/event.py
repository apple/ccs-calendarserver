##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Benchmark a server's handling of event creation.
"""

from itertools import count
from uuid import uuid4
from datetime import datetime, timedelta

from _event_create import formatDate, measure as _measure

# XXX Represent these as vobjects?  Would make it easier to add more vevents.
event = """\
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
END:VTIMEZONE
%(VEVENTS)s\
END:VCALENDAR
"""

attendee = """\
ATTENDEE;CN=User %(SEQUENCE)02d;CUTYPE=INDIVIDUAL;EMAIL=user%(SEQUENCE)02d@example.com;PARTSTAT=NE
 EDS-ACTION;ROLE=REQ-PARTICIPANT;RSVP=TRUE:urn:uuid:user%(SEQUENCE)02d
"""

organizer = """\
ORGANIZER;CN=User %(SEQUENCE)02d;EMAIL=user%(SEQUENCE)02d@example.com:urn:uuid:user%(SEQUENCE)02d
ATTENDEE;CN=User %(SEQUENCE)02d;EMAIL=user%(SEQUENCE)02d@example.com;PARTSTAT=ACCEPTE
 D:urn:uuid:user%(SEQUENCE)02d
"""

def makeOrganizer(sequence):
    return organizer % {'SEQUENCE': sequence}

def makeAttendees(count):
    return ''.join([
            attendee % {'SEQUENCE': n} for n in range(2, count + 2)])


SUMMARY = "STUFF IS THINGS"

def makeEvent(i, organizerSequence, attendeeCount):
    s = """\
BEGIN:VEVENT
UID:%(UID)s
DTSTART;TZID=America/Los_Angeles:%(START)s
DTEND;TZID=America/Los_Angeles:%(END)s
CREATED:20100729T193912Z
DTSTAMP:20100729T195557Z
%(ORGANIZER)s\
%(ATTENDEES)s\
SEQUENCE:0
SUMMARY:%(summary)s
TRANSP:OPAQUE
END:VEVENT
"""
    base = datetime(2010, 7, 30, 11, 15, 00)
    interval = timedelta(0, 5)
    duration = timedelta(0, 3)
    return event % {
        'VEVENTS': s % {
            'UID': uuid4(),
            'START': formatDate(base + i * interval),
            'END': formatDate(base + i * interval + duration),
            'ORGANIZER': makeOrganizer(organizerSequence),
            'ATTENDEES': makeAttendees(attendeeCount),
            'summary': SUMMARY,
            },
        }


def measure(host, port, dtrace, attendeeCount, samples):
    calendar = "event-creation-benchmark"
    organizerSequence = 1

    # An infinite stream of VEVENTs to PUT to the server.
    events = ((i, makeEvent(i, organizerSequence, attendeeCount)) for i in count(2))

    return _measure(
        calendar, organizerSequence, events,
        host, port, dtrace, samples)
