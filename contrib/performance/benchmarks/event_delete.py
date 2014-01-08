##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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

"""
Benchmark a server's handling of event deletion.
"""

from itertools import count
from urllib2 import HTTPDigestAuthHandler

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.web.http import NO_CONTENT

from contrib.performance.httpauth import AuthHandlerAgent
from contrib.performance.httpclient import StringProducer

from contrib.performance.benchlib import initialize, sample
from contrib.performance.benchmarks.event import makeEvent

@inlineCallbacks
def measure(host, port, dtrace, attendeeCount, samples):
    organizerSequence = 1
    user = password = "user%02d" % (organizerSequence,)
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
    events = ((i, makeEvent(i, organizerSequence, attendeeCount))
              for i in count(2))

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
        agent, (('DELETE', url) for url in urls).next,
        NO_CONTENT)
    returnValue(samples)
