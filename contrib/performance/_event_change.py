
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
def measure(host, port, dtrace, attendeeCount, samples, fieldName,
            replacer, eventPerSample=False):
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

    if eventPerSample:
        # Create an event for each sample that will be taken, so that no event
        # is used for two different samples.
        f = _selfish_sample
    else:
        # Just create one event and re-use it for all samples.
        f = _generous_sample

    data = yield f(
        dtrace, replacer, agent, host, port, user, calendar, fieldName,
        attendeeCount, samples)
    returnValue(data)



@inlineCallbacks
def _selfish_sample(dtrace, replacer, agent, host, port, user, calendar, fieldName, attendeeCount, samples):
    url = 'http://%s:%s/calendars/__uids__/%s/%s/%s-change-%%d.ics' % (
        host, port, user, calendar, fieldName)

    headers = Headers({"content-type": ["text/calendar"]})

    events = [
        (makeEvent(i, attendeeCount), url % (i,))
        for i in range(samples)]

    for (event, url) in events:
        yield agent.request('PUT', url, headers, StringProducer(event))


    # Sample changing the event according to the replacer.
    samples = yield sample(
        dtrace, samples,
        agent, (('PUT', url, headers, StringProducer(replacer(event, i)))
                for i, (event, url)
                in enumerate(events)).next)
    returnValue(samples)



@inlineCallbacks
def _generous_sample(dtrace, replacer, agent, host, port, user, calendar, fieldName, attendeeCount, samples):
    url = 'http://%s:%s/calendars/__uids__/%s/%s/%s-change.ics' % (
        host, port, user, calendar, fieldName)

    headers = Headers({"content-type": ["text/calendar"]})

    event = makeEvent(0, attendeeCount)

    yield agent.request('PUT', url, headers, StringProducer(event))

    # Sample changing the event according to the replacer.
    samples = yield sample(
        dtrace, samples,
        agent, (('PUT', url, headers, StringProducer(replacer(event, i)))
                for i in count(1)).next)
    returnValue(samples)
