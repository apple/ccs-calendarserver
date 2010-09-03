
"""
Benchmark a server's handling of event deletion.
"""

from itertools import count
from urllib2 import HTTPDigestAuthHandler

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from httpauth import AuthHandlerAgent
from httpclient import StringProducer

from benchlib import initialize, sample
from event import makeEvent

@inlineCallbacks
def measure(host, port, dtrace, attendeeCount, samples):
    user = password = "user01"
    root = "/"
    principal = "/"
    calendar = "event-deletion-benchmark"

    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://%s:%d/" % (host, port),
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # Set up the calendar first
    yield initialize(agent, host, port, user, password, root, principal, calendar)

    # An infinite stream of VEVENTs to PUT to the server.
    events = ((i, makeEvent(i, attendeeCount)) for i in count(2))

    # Create enough events to delete
    uri = 'http://%s:%d/calendars/__uids__/%s/%s/foo-%%d.ics' % (
        host, port, user, calendar)
    headers = Headers({"content-type": ["text/calendar"]})
    urls = []
    for i, body in events:
        urls.append(uri % (i,))
        yield agent.request(
            'PUT', urls[-1], headers, StringProducer(body))
        if len(urls) == samples:
            break

    # Now delete them all
    samples = yield sample(
        dtrace, samples,
        agent, (('DELETE', url) for url in urls).next)
    returnValue(samples)

