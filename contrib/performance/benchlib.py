
from time import time

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.http_headers import Headers

from protocol.url import URL

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
        return self.agent.request('DELETE', 'http://%s%s' % (self.netloc, url.toString()))


    def makeCalendar(self, url):
        return self.agent.request('MKCALENDAR', 'http://%s%s' % (self.netloc, url.toString()))


    def writeData(self, url, data, contentType):
        return self.agent.request(
            'PUT', 
            'http://%s%s' % (self.netloc, url.toString()), 
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
    cal = URL("/calendars/users/%s/%s/" % (user, calendar))
    d = _serial([
            (account.deleteResource, (cal,)),
            (account.makeCalendar, (cal,))])
    d.addCallback(lambda ignored: account)
    return d


@inlineCallbacks
def sample(dtrace, samples, agent, paramgen):
    data = []
    yield dtrace.start()
    for i in range(samples):
        before = time()
        response = yield agent.request(*paramgen())
        yield readBody(response)
        after = time()
        data.append(after - before)
    stats = yield dtrace.stop()
    stats[Duration('urlopen time')] = data
    returnValue(stats)
