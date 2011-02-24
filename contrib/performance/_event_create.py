##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
Various helpers for event-creation benchmarks.
"""

from urllib2 import HTTPDigestAuthHandler

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.http_headers import Headers
from twisted.web.http import CREATED
from twisted.web.client import Agent
from twisted.internet import reactor

from httpauth import AuthHandlerAgent
from benchlib import initialize, sample
from httpclient import StringProducer

def formatDate(d):
    return ''.join(filter(str.isalnum, d.isoformat()))


@inlineCallbacks
def measure(calendar, organizerSequence, events, host, port, dtrace, samples):
    """
    Benchmark event creation.
    """
    user = password = "user%02d" % (organizerSequence,)
    root = "/"
    principal = "/"

    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://%s:%d/" % (host, port),
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # First set things up
    yield initialize(agent, host, port, user, password, root, principal, calendar)

    method = 'PUT'
    uri = 'http://%s:%d/calendars/__uids__/%s/%s/foo-%%d.ics' % (
        host, port, user, calendar)
    headers = Headers({"content-type": ["text/calendar"]})

    # Sample it a bunch of times
    samples = yield sample(
        dtrace, samples, 
        agent, ((method, uri % (i,), headers, StringProducer(body))
                for (i, body)
                in events).next,
        CREATED)
    returnValue(samples)
