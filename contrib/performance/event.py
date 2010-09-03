
"""
Benchmark a server's handling of event creation.
"""

from itertools import count
from urllib2 import HTTPDigestAuthHandler
from uuid import uuid4
from datetime import datetime, timedelta

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from httpauth import AuthHandlerAgent
from httpclient import StringProducer
from benchlib import initialize, sample

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
 EDS-ACTION;ROLE=REQ-PARTICIPANT;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:uuid:use
 r%(SEQUENCE)02d
"""

def makeAttendees(count):
    return '\n'.join([
            attendee % {'SEQUENCE': n} for n in range(2, count + 2)])


def formatDate(d):
    return ''.join(filter(str.isalnum, d.isoformat()))


def makeEvent(i, attendeeCount):
    s = """\
BEGIN:VEVENT
UID:%(UID)s
DTSTART;TZID=America/Los_Angeles:%(START)s
DTEND;TZID=America/Los_Angeles:%(END)s
%(ATTENDEES)s\
CREATED:20100729T193912Z
DTSTAMP:20100729T195557Z
ORGANIZER;CN=User 03;EMAIL=user03@example.com:urn:uuid:user03
SEQUENCE:%(SEQUENCE)s
SUMMARY:STUFF IS THINGS
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
            'SEQUENCE': i,
            'ATTENDEES': makeAttendees(attendeeCount),
            },
        }


@inlineCallbacks
def measure(host, port, dtrace, attendeeCount, samples):
    user = password = "user01"
    root = "/"
    principal = "/"
    calendar = "event-creation-benchmark"

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

    # An infinite stream of VEVENTs to PUT to the server.
    events = ((i, makeEvent(i, attendeeCount)) for i in count(2))

    # Sample it a bunch of times
    samples = yield sample(
        dtrace, samples, 
        agent, ((method, uri % (i,), headers, StringProducer(body))
                for (i, body)
                in events).next)
    returnValue(samples)

