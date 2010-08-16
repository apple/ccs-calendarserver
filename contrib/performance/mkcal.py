"""
Make a new calendar using an existing user account on an already-running iCal
server.
"""

import sys

from subprocess import PIPE, Popen
from signal import SIGINT

from urllib2 import HTTPDigestAuthHandler
from uuid import uuid1, uuid4
from datetime import datetime, timedelta
from time import time
from StringIO import StringIO

import vobject

from client.account import CalDAVAccount
from protocol.url import URL

from zope.interface import implements

from twisted.internet.protocol import ProcessProtocol, Protocol
from twisted.internet.defer import (
    Deferred, inlineCallbacks, returnValue, succeed, gatherResults)
from twisted.internet import reactor
from twisted.web.iweb import IBodyProducer
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from httpauth import AuthHandlerAgent


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
def measure(pids, events, samples):
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
    with DTraceCollector(pids) as dtrace:
        for i in range(samples):
            before = time()
            response = yield agent.request(
                method, uri, headers, body)
            yield readBody(response)
            after = time()
            data.append(after - before)
    stats = {Duration('urlopen time'): data}
    stats.update((yield dtrace))
    returnValue(stats)


class _Statistic(object):
    def __init__(self, name):
        self.name = name


    def summarize(self, data):
        print 'mean', self.name, mean(data)
        print 'median', self.name, median(data)
        print 'stddev', self.name, stddev(data)
        print 'sum', self.name, sum(data)


    def write(self, basename, data):
        fObj = file(basename % (self.name,), 'w')
        fObj.write('\n'.join(map(str, data)) + '\n')
        fObj.close()



class Duration(_Statistic):
    pass



class Bytes(_Statistic):
    pass



class DTraceCollector(object):
    def __init__(self, pids):
        self.pids = pids
        self._read = []
        self._write = []
        self._execute = []
        self._iternext = []


    def stats(self):
        return {
            Bytes('read'): self._read,
            Bytes('write'): self._write,
            Duration('execute'): self._execute,
            Duration('iternext'): self._iternext,
            }


    def _parse(self, dtrace):
        file('dtrace.log', 'a').write(dtrace)


        start = None
        for L in dtrace.splitlines():
            parts = L.split(None)
            if len(parts) >= 4:
                event = parts[2]
                func, stage = event.split(':')
                value = int(parts[3])
                if stage == 'entry':
                    start = value
                elif stage == 'return':
                    if start is None:
                        print func, 'return without entry at', parts[3]
                        continue
                    end = int(parts[3])
                    diff = end - start
                    if func == '_pysqlite_query_execute':
                        accum = self._execute
                    elif func == 'pysqlite_cursor_iternext':
                        accum = self._iternext
                    else:
                        continue
                    if diff < 0:
                        print 'Completely bogus dealie', func, start, end
                    else:
                        accum.append(diff)
                    start = None
                else:
                    continue


    def __enter__(self):
        finished = []
        self.dtraces = {}
        for p in self.pids:
            d = Deferred()
            self.dtraces[p] = reactor.spawnProcess(
                IOMeasureConsumer(d),
                "/usr/sbin/dtrace",
                ["/usr/sbin/dtrace", "-q", "-p", str(p), "-s", "io_measure.d"])
            d.addCallback(self._cleanup, p)
            d.addCallback(self._parse)
            finished.append(d)
        return gatherResults(finished).addCallback(lambda ign: self.stats())


    def _cleanup(self, passthrough, pid):
        del self.dtraces[pid]
        return passthrough


    def __exit__(self, type, value, traceback):
        for proc in self.dtraces.itervalues():
            proc.signalProcess(SIGINT)



class IOMeasureConsumer(ProcessProtocol):
    def __init__(self, done):
        self.done = done


    def connectionMade(self):
        self.out = StringIO()


    def errReceived(self, bytes):
        print bytes

    def outReceived(self, bytes):
        self.out.write(bytes)


    def processEnded(self, reason):
        self.done.callback(self.out.getvalue())


def mean(samples):
    return sum(samples) / len(samples)


def median(samples):
    return sorted(samples)[len(samples) / 2]


def stddev(samples):
    m = mean(samples)
    variance = sum([(datum - m) ** 2 for datum in samples]) / len(samples)
    return variance ** 0.5

@inlineCallbacks
def main():
    # Figure out which pids we are benchmarking.
    pids = map(int, sys.argv[1:])

    for numEvents in [1, 100]: #, 1000]:#, 10000]:
        print 'Testing', numEvents, 'events'
        data = yield measure(pids, numEvents, 100)
        for k, v in data.iteritems():
            if v:
                k.summarize(v)
                k.write('vfreebusy.%%s.%d' % (numEvents,), v)


if __name__ == '__main__':
    from twisted.python.log import err
    d = main()
    d.addErrback(err)
    d.addCallback(lambda ign: reactor.stop())
    reactor.run()
