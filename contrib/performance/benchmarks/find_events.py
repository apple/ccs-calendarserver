##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from itertools import count
from urllib2 import HTTPDigestAuthHandler

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, gatherResults
from twisted.internet.task import cooperate
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.web.http import MULTI_STATUS

from contrib.performance.httpauth import AuthHandlerAgent
from contrib.performance.httpclient import StringProducer

from contrib.performance.benchlib import CalDAVAccount, sample
from contrib.performance.benchmarks.event import makeEvent

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

def uploadEvents(numEvents, agent, uri, cal):
    def worker():
        for i in range(numEvents):
            event = makeEvent(i, 1, 0)
            yield agent.request(
                'PUT',
                '%s%s%d.ics' % (uri, cal, i),
                Headers({"content-type": ["text/calendar"]}),
                StringProducer(event))
    worker = worker()
    return gatherResults([
            cooperate(worker).whenDone() for i in range(3)])


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
    cal = "calendars/users/%s/find-events/" % (user,)
    yield account.makeCalendar("/" + cal)

    # Create the indicated number of events on the calendar
    yield uploadEvents(numEvents, agent, uri, cal)

    body = StringProducer(PROPFIND)
    params = (
        ('PROPFIND',
         '%scalendars/__uids__/%s/find-events/' % (uri, user),
         Headers({"depth": ["1"], "content-type": ["text/xml"]}), body)
        for i in count(1))

    samples = yield sample(dtrace, samples, agent, params.next, MULTI_STATUS)

    # Delete the calendar we created to leave the server in roughly
    # the same state as we found it.
    yield account.deleteResource("/" + cal)

    returnValue(samples)
