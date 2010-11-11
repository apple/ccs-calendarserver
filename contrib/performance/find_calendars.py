
from itertools import count
from urllib2 import HTTPDigestAuthHandler

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from httpauth import AuthHandlerAgent
from httpclient import StringProducer

from benchlib import CalDAVAccount, sample

PROPFIND = """\
<?xml version="1.0" encoding="utf-8"?>
<x0:propfind xmlns:x0="DAV:" xmlns:x3="http://apple.com/ns/ical/" xmlns:x1="http://calendarserver.org/ns/" xmlns:x2="urn:ietf:params:xml:ns:caldav">
 <x0:prop>
  <x1:xmpp-server/>
  <x1:xmpp-uri/>
  <x1:getctag/>
  <x0:displayname/>
  <x2:calendar-description/>
  <x3:calendar-color/>
  <x3:calendar-order/>
  <x2:supported-calendar-component-set/>
  <x0:resourcetype/>
  <x0:owner/>
  <x2:calendar-free-busy-set/>
  <x2:schedule-calendar-transp/>
  <x2:schedule-default-calendar-URL/>
  <x0:quota-available-bytes/>
  <x0:quota-used-bytes/>
  <x2:calendar-timezone/>
  <x0:current-user-privilege-set/>
  <x1:source/>
  <x1:subscribed-strip-alarms/>
  <x1:subscribed-strip-attachments/>
  <x1:subscribed-strip-todos/>
  <x3:refreshrate/>
  <x1:push-transports/>
  <x1:pushkey/>
  <x1:publish-url/>
 </x0:prop>
</x0:propfind>
"""

@inlineCallbacks
def measure(host, port, dtrace, numCalendars, samples):
    # There's already the "calendar" calendar
    numCalendars -= 1

    user = password = "user10"
    root = "/"
    principal = "/"

    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://%s:%d/" % (host, port),
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # Create the number of calendars necessary
    account = CalDAVAccount(
        agent,
        "%s:%d" % (host, port),
        user=user, password=password,
        root=root, principal=principal)
    cal = "/calendars/users/%s/propfind-%%d/" % (user,)
    for i in range(numCalendars):
        yield account.makeCalendar(cal % (i,))

    body = StringProducer(PROPFIND)
    params = (
        ('PROPFIND', 'http://%s:%d/calendars/__uids__/%s/' % (host, port, user),
         Headers({"depth": ["1"], "content-type": ["text/xml"]}), body)
        for i in count(1))

    samples = yield sample(dtrace, samples, agent, params.next)

    # Delete the calendars we created to leave the server in roughly
    # the same state as we found it.
    for i in range(numCalendars):
        yield account.deleteResource(cal % (i,))

    returnValue(samples)
