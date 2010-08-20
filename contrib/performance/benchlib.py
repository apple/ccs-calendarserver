
from time import time

from twisted.internet.defer import inlineCallbacks, returnValue

from client.account import CalDAVAccount
from protocol.url import URL

from stats import Duration
from httpclient import readBody

def initialize(host, port, user, password, root, principal, calendar):
    """
    If the specified calendar exists, delete it.  Then re-create it empty.
    """
    account = CalDAVAccount(
        "%s:%d" % (host, port),
        user=user, pswd=password,
        root=root, principal=principal)
    cal = "/calendars/users/%s/%s/" % (user, calendar)
    account.session.deleteResource(URL(cal))
    account.session.makeCalendar(URL(cal))
    return account


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
