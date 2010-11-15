import pickle
from time import time

from twisted.internet.defer import (
    DeferredSemaphore, inlineCallbacks, returnValue, gatherResults)
# from twisted.internet.task import deferLater
from twisted.web.http_headers import Headers
# from twisted.internet import reactor
from twisted.python.log import msg

from stats import Duration
from httpclient import StringProducer, readBody


class CalDAVAccount(object):
    def __init__(self, agent, netloc, user, password, root, principal):
        self.agent = agent
        self.netloc = netloc
        self.user = user
        self.password = password
        self.root = root
        self.principal = principal


    def deleteResource(self, url):
        return self.agent.request('DELETE', 'http://%s%s' % (self.netloc, url))


    def makeCalendar(self, url):
        return self.agent.request(
            'MKCALENDAR', 'http://%s%s' % (self.netloc, url))


    def writeData(self, url, data, contentType):
        return self.agent.request(
            'PUT',
            'http://%s%s' % (self.netloc, url),
            Headers({'content-type': [contentType]}),
            StringProducer(data))



@inlineCallbacks
def _serial(fs):
     for (f, args) in fs:
         yield f(*args)
     returnValue(None)



def initialize(agent, host, port, user, password, root, principal, calendar):
    """
    If the specified calendar exists, delete it.  Then re-create it empty.
    """
    account = CalDAVAccount(
        agent,
        "%s:%d" % (host, port),
        user=user, password=password,
        root=root, principal=principal)
    cal = "/calendars/users/%s/%s/" % (user, calendar)
    d = _serial([
            (account.deleteResource, (cal,)),
            (account.makeCalendar, (cal,))])
    d.addCallback(lambda ignored: account)
    return d


@inlineCallbacks
def sample(dtrace, samples, agent, paramgen, concurrency=1):
    sem = DeferredSemaphore(concurrency)

    urlopen = Duration('HTTP')
    data = {urlopen: []}

    def once():
        msg('emitting request')
        before = time()
        d = agent.request(*paramgen())
        def cbResponse(response):
            d = readBody(response)
            def cbBody(ignored):
                after = time()
                msg('response received')

                # Give things a moment to settle down.  This is a hack
                # to try to collect the last of the dtrace output
                # which may still be sitting in the write buffer of
                # the dtrace process.  It would be nice if there were
                # a more reliable way to know when we had it all, but
                # no luck on that front so far.  The implementation of
                # mark is supposed to take care of that, but the
                # assumption it makes about ordering of events appears
                # to be invalid.

                # XXX Disabled until I get a chance to seriously
                # measure what affect, if any, it has.
                # d = deferLater(reactor, 0.5, dtrace.mark)
                d = dtrace.mark()

                def cbStats(stats):
                    msg('stats collected')
                    for k, v in stats.iteritems():
                        data.setdefault(k, []).append(v)
                    data[urlopen].append(after - before)
                d.addCallback(cbStats)
                return d
            d.addCallback(cbBody)
            return d
        d.addCallback(cbResponse)
        return d

    msg('starting dtrace')
    yield dtrace.start()
    msg('dtrace started')
    l = []
    for i in range(samples):
        l.append(sem.run(once))
    yield gatherResults(l)

    msg('stopping dtrace')
    leftOver = yield dtrace.stop()
    msg('dtrace stopped')
    for (k, v) in leftOver.items():
        if v:
            print 'Extra', k, ':', v
    returnValue(data)


def select(statistics, benchmark, parameter, statistic):
    for stat, samples in statistics[benchmark][int(parameter)].iteritems():
        if stat.name == statistic:
            return (stat, samples)
    raise ValueError("Unknown statistic %r" % (statistic,))


def load_stats(statfiles):
    data = []
    for fname in statfiles:
        fname, bench, param, stat = fname.split(',')
        stats, samples = select(
            pickle.load(file(fname)), bench, param, stat)
        data.append((stats, samples))
        if data:
            assert len(samples) == len(data[0][1])
    return data
