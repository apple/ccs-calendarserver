
from itertools import count, cycle
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

    # Two calendars between which to move the event.
    fooCalendar = "event-move-foo-benchmark"
    barCalendar = "event-move-bar-benchmark"

    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://%s:%d/" % (host, port),
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # Set up the calendars first
    for calendar in [fooCalendar, barCalendar]:
        yield initialize(
            agent, host, port, user, password, root, principal, calendar)

    fooURI = 'http://%s:%d/calendars/__uids__/%s/%s/some-event.ics' % (
        host, port, user, fooCalendar)
    barURI = 'http://%s:%d/calendars/__uids__/%s/%s/some-event.ics' % (
        host, port, user, barCalendar)

    # Create the event that will move around
    headers = Headers({"content-type": ["text/calendar"]})
    yield agent.request(
        'PUT', fooURI, headers, StringProducer(makeEvent(attendeeCount, 1)))

    # Move it around sooo much
    source = cycle([fooURI, barURI])
    dest = cycle([barURI, fooURI])

    params = (
        ('MOVE', source.next(),
         Headers({"destination": [dest.next()], "overwrite": ["F"]}))
        for i in count(1))

    samples = yield sample(dtrace, samples, agent, params.next)
    returnValue(samples)
