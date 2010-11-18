from itertools import count
from urllib2 import HTTPDigestAuthHandler

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from httpauth import AuthHandlerAgent
from httpclient import StringProducer

from benchlib import CalDAVAccount, sample
from event import makeEvent

PROPFIND = """\
<?xml version="1.0" encoding="utf-8"?>
<x0:propfind xmlns:x0="DAV:" xmlns:x1="http://calendarserver.org/ns/">
 <x0:prop>
  <x0:getetag/>
  <x0:resourcetype/>
  <x1:notificationtype/>
 </x0:prop>
</x0:propfind>
"""

@inlineCallbacks
def measure(host, port, dtrace, numEvents, samples):
    user = password = "user11"
    root = "/"
    principal = "/"

    uri = "http://%s:%d/" % (host, port)
    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri=uri,
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # Create the number of calendars necessary
    account = CalDAVAccount(
        agent,
        "%s:%d" % (host, port),
        user=user, password=password,
        root=root, principal=principal)
    cal = "/calendars/users/%s/find-events/" % (user,)
    yield account.makeCalendar(cal)

    # Create the indicated number of events on the calendar
    for i in range(numEvents):
        event = makeEvent(i, 1, 0)
        yield agent.request(
            'PUT',
            '%s%s%d.ics' % (uri, cal, i),
            Headers({"content-type": ["text/calendar"]}),
            StringProducer(event))

    body = StringProducer(PROPFIND)
    params = (
        ('PROPFIND',
         '%s/calendars/__uids__/%s/find-events/' % (uri, user),
         Headers({"depth": ["1"], "content-type": ["text/xml"]}), body)
        for i in count(1))

    samples = yield sample(dtrace, samples, agent, params.next)

    # Delete the calendar we created to leave the server in roughly
    # the same state as we found it.
    yield account.deleteResource(cal)

    returnValue(samples)
