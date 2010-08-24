"""
Benchmark a server's handling of VFREEBUSY requests.
"""

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
TZID:America/New_York
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
END:VTIMEZONE
%(VEVENTS)s\
END:VCALENDAR
"""

vfreebusy = """\
BEGIN:VCALENDAR
CALSCALE:GREGORIAN
VERSION:2.0
METHOD:REQUEST
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VFREEBUSY
UID:81F582C8-4E7F-491C-85F4-E541864BE0FA
DTEND:20100730T150000Z
ATTENDEE:urn:uuid:user02
DTSTART:20100730T140000Z
X-CALENDARSERVER-MASK-UID:EC75A61B-08A3-44FD-BFBB-2457BBD0D490
DTSTAMP:20100729T174751Z
ORGANIZER:mailto:user01@example.com
SUMMARY:Availability for urn:uuid:user02
END:VFREEBUSY
END:VCALENDAR
"""

def formatDate(d):
    return ''.join(filter(str.isalnum, d.isoformat()))

def makeEvent(i):
    s = """\
BEGIN:VEVENT
UID:%(UID)s
DTSTART;TZID=America/New_York:%(START)s
DTEND;TZID=America/New_York:%(END)s
CREATED:20100729T193912Z
DTSTAMP:20100729T195557Z
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
            },
        }


def makeEvents(n):
    return [makeEvent(i) for i in range(n)]


@inlineCallbacks
def measure(host, port, dtrace, events, samples):
    user = password = "user01"
    root = "/"
    principal = "/"
    calendar = "vfreebusy-benchmark"

    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://%s:%d/" % (host, port),
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # First set things up
    account = yield initialize(
        agent, host, port, user, password, root, principal, calendar)

    base = "/calendars/users/%s/%s/foo-%%d.ics" % (user, calendar)
    for i, cal in enumerate(makeEvents(events)):
        yield account.writeData(base % (i,), cal, "text/calendar")

    method = 'POST'
    uri = 'http://%s:%d/calendars/__uids__/%s/outbox/' % (host, port, user)
    headers = Headers({"content-type": ["text/calendar"]})
    body = StringProducer(vfreebusy)

    samples = yield sample(
        dtrace, samples,
        agent, lambda: (method, uri, headers, body))
    returnValue(samples)

