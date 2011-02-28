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
Various helpers for event-creation benchmarks.
"""

from urllib2 import HTTPDigestAuthHandler

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.http_headers import Headers
from twisted.web.http import CREATED
from twisted.web.client import Agent
from twisted.internet import reactor

from httpauth import AuthHandlerAgent
from benchlib import initialize, sample
from httpclient import StringProducer


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

vevent = """\
BEGIN:VEVENT
UID:%(UID)s
DTSTART;TZID=America/Los_Angeles:%(START)s
DTEND;TZID=America/Los_Angeles:%(END)s
%(RRULE)s\
CREATED:20100729T193912Z
DTSTAMP:20100729T195557Z
%(ORGANIZER)s\
%(ATTENDEES)s\
SEQUENCE:0
SUMMARY:Some random thing
TRANSP:OPAQUE
END:VEVENT
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
    return [
        attendee % {'SEQUENCE': n} for n in range(2, count + 2)]


def makeVCalendar(uid, start, end, recurrence, organizerSequence, attendees):
    if recurrence is None:
        rrule = ""
    else:
        rrule = recurrence + "\n"
    return event % {
        'VEVENTS': vevent % {
            'UID': uid,
            'START': formatDate(start),
            'END': formatDate(end),
            'ORGANIZER': makeOrganizer(organizerSequence),
            'ATTENDEES': ''.join(attendees),
            'RRULE': rrule,
            },
        }



def formatDate(d):
    return ''.join(filter(str.isalnum, d.isoformat()))


@inlineCallbacks
def measure(calendar, organizerSequence, events, host, port, dtrace, samples):
    """
    Benchmark event creation.
    """
    user = password = "user%02d" % (organizerSequence,)
    root = "/"
    principal = "/"

    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://%s:%d/" % (host, port),
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # First set things up
    yield initialize(agent, host, port, user, password, root, principal, calendar)

    method = 'PUT'
    uri = 'http://%s:%d/calendars/__uids__/%s/%s/foo-%%d.ics' % (
        host, port, user, calendar)
    headers = Headers({"content-type": ["text/calendar"]})

    # Sample it a bunch of times
    samples = yield sample(
        dtrace, samples, 
        agent, ((method, uri % (i,), headers, StringProducer(body))
                for (i, body)
                in events).next,
        CREATED)
    returnValue(samples)
