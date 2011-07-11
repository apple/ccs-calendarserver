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
Benchmark a server's handling of VFREEBUSY requests with a varying number of
attendees in the request.
"""

from urllib2 import HTTPDigestAuthHandler

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.http import OK
from twisted.web.http_headers import Headers
from twisted.web.client import Agent
from twisted.internet import reactor

from httpauth import AuthHandlerAgent
from httpclient import StringProducer
from benchlib import CalDAVAccount, sample

from benchmarks.vfreebusy import VFREEBUSY, makeEvent

@inlineCallbacks
def measure(host, port, dtrace, attendees, samples):
    user = password = "user01"
    root = "/"
    principal = "/"
    calendar = "vfreebusy-vary-attendees-benchmark"

    targets = range(2, attendees + 2)

    authinfo = HTTPDigestAuthHandler()

    # Set up authentication info for our own user and all the other users that
    # may need an event created on one of their calendars.
    for i in [1] + targets:
        targetUser = "user%02d" % (i,)
        for path in ["calendars/users/%s/" % (targetUser,),
                     "calendars/__uids__/%s/" % (targetUser,)]:
            authinfo.add_password(
                realm="Test Realm",
                uri="http://%s:%d/%s" % (host, port, path),
                user=targetUser, passwd=targetUser)

    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # Set up events on about half of the target accounts
    for i in targets[::2]:
        targetUser = "user%02d" % (i,)
        account = CalDAVAccount(
            agent,
            "%s:%d" % (host, port),
            user=targetUser, password=password,
            root=root, principal=principal)
        cal = "/calendars/users/%s/%s/" % (targetUser, calendar)
        yield account.deleteResource(cal)
        yield account.makeCalendar(cal)
        yield account.writeData(cal + "foo.ics", makeEvent(i), "text/calendar")

    # And now issue the actual VFREEBUSY request
    method = 'POST'
    uri = 'http://%s:%d/calendars/__uids__/%s/outbox/' % (host, port, user)
    headers = Headers({"content-type": ["text/calendar"]})
    body = StringProducer(VFREEBUSY % {
            "attendees": "".join([
                    "ATTENDEE:urn:uuid:user%02d\n" % (i,)
                    for i in targets])})

    samples = yield sample(
        dtrace, samples,
        agent, lambda: (method, uri, headers, body),
        OK)
    returnValue(samples)
