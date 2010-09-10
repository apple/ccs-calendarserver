
"""
Benchmark a server's handling of event summary changes.
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
def measure(host, port, dtrace, attendeeCount, samples, fieldName, replacer):
    user = password = "user01"
    root = "/"
    principal = "/"
    calendar = "event-change-%s-benchmark" % (fieldName,)

    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://%s:%d/" % (host, port),
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # Set up the calendar first
    yield initialize(agent, host, port, user, password, root, principal, calendar)

    event = makeEvent(0, attendeeCount)
    url = 'http://%s:%s/calendars/__uids__/%s/%s/%s-change.ics' % (
        host, port, user, calendar, fieldName)
    headers = Headers({"content-type": ["text/calendar"]})

    # Create an event to mess around with.
    yield agent.request('PUT', url, headers, StringProducer(event))

    # Change the summary to a bunch of different things
    samples = yield sample(
        dtrace, samples,
        agent, (('PUT', url, headers, StringProducer(replacer(event, i)))
                for i
                in count()).next)
    returnValue(samples)
