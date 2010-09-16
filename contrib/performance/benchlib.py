import pickle
from time import time

from twisted.internet.defer import DeferredSemaphore, inlineCallbacks, returnValue, gatherResults
from twisted.web.http_headers import Headers

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
        return self.agent.request('MKCALENDAR', 'http://%s%s' % (self.netloc, url))


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
        before = time()
        d = agent.request(*paramgen())
        def cbResponse(response):
            print response.code
            d = readBody(response)
            def cbBody(ignored):
                after = time()
                d = dtrace.mark()
                def cbStats(stats):
                    for k, v in stats.iteritems():
                        data.setdefault(k, []).append(v)
                    data[urlopen].append(after - before)
                d.addCallback(cbStats)
                return d
            d.addCallback(cbBody)
            return d
        d.addCallback(cbResponse)
        return d

    yield dtrace.start()
    l = []
    for i in range(samples):
        l.append(sem.run(once))
    yield gatherResults(l)

    leftOver = yield dtrace.stop()
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
