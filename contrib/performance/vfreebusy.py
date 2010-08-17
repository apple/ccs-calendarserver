"""
Benchmark a server's handling of VFREEBUSY requests.
"""

from urllib2 import HTTPDigestAuthHandler
from uuid import uuid4
from datetime import datetime, timedelta
from time import time

from client.account import CalDAVAccount
from protocol.url import URL

from zope.interface import implements

from twisted.internet.protocol import Protocol
from twisted.internet.defer import (
    Deferred, inlineCallbacks, returnValue, succeed)
from twisted.internet import reactor
from twisted.web.iweb import IBodyProducer
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from httpauth import AuthHandlerAgent
from stats import Duration


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


class _DiscardReader(Protocol):
    def __init__(self, finished):
        self.finished = finished


    def dataReceived(self, bytes):
        pass


    def connectionLost(self, reason):
        self.finished.callback(None)



def readBody(response):
    finished = Deferred()
    response.deliverBody(_DiscardReader(finished))
    return finished



class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self._body = body
        self.length = len(self._body)


    def startProducing(self, consumer):
        consumer.write(self._body)
        return succeed(None)


@inlineCallbacks
def measure(dtrace, events, samples):
    # First set things up
    account = CalDAVAccount(
        "localhost:8008", user="user01", pswd="user01", root="/", principal="/")
    account.session.deleteResource(
        URL("/calendars/users/user01/monkeys3/"))
    account.session.makeCalendar(
        URL("/calendars/users/user01/monkeys3/"))

    for i, cal in enumerate(makeEvents(events)):
        account.session.writeData(
            URL("/calendars/users/user01/monkeys3/foo-%d.ics" % (i,)),
            cal,
            "text/calendar")

    # CalDAVClientLibrary can't seem to POST things.
    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://localhost:8008/",
        user="user01",
        passwd="user01")

    agent = AuthHandlerAgent(Agent(reactor), authinfo)
    method = 'POST'
    uri = 'http://localhost:8008/calendars/__uids__/user01/outbox/'
    headers = Headers({"content-type": ["text/calendar"]})
    body = StringProducer(vfreebusy)

    # Now sample it a bunch of times
    data = []
    yield dtrace.start()
    for i in range(samples):
        before = time()
        response = yield agent.request(
            method, uri, headers, body)
        yield readBody(response)
        after = time()
        data.append(after - before)
    stats = yield dtrace.stop()
    stats[Duration('urlopen time')] = data
    returnValue(stats)
