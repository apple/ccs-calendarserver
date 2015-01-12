##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
events on the target's calendar.
"""

from urllib2 import HTTPDigestAuthHandler
from uuid import uuid4
from datetime import datetime, timedelta

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.web.http import OK

from contrib.performance.httpauth import AuthHandlerAgent
from contrib.performance.httpclient import StringProducer
from contrib.performance.benchlib import initialize, sample

# XXX Represent these as pycalendar objects?  Would make it easier to add more vevents.
event = """\
BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
END:VTIMEZONE
%(VEVENTS)s\
END:VCALENDAR
"""

VFREEBUSY = """\
BEGIN:VCALENDAR
CALSCALE:GREGORIAN
VERSION:2.0
METHOD:REQUEST
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VFREEBUSY
UID:81F582C8-4E7F-491C-85F4-E541864BE0FA
DTEND:%(end)s
%(attendees)sDTSTART:%(start)s
X-CALENDARSERVER-MASK-UID:EC75A61B-08A3-44FD-BFBB-2457BBD0D490
DTSTAMP:20100729T174751Z
ORGANIZER:mailto:user01@example.com
SUMMARY:Availability for urn:x-uid:user02
END:VFREEBUSY
END:VCALENDAR
"""

def formatDate(d):
    return ''.join(filter(str.isalnum, d.isoformat()))



def makeEvent(i):
    # Backwards compat interface, don't delete it for a little while.
    return makeEventNear(datetime(2010, 7, 30, 11, 15, 00), i)



def makeEventNear(base, i):
    s = """\
BEGIN:VEVENT
UID:%(UID)s
DTSTART;TZID=America/New_York:%(START)s
DTEND;TZID=America/New_York:%(END)s
CREATED:20100729T193912Z
DTSTAMP:20100729T195557Z
SEQUENCE:%(SEQUENCE)s
SUMMARY:STUFF IS THINGS
TRANSP:OPAQUE
END:VEVENT
"""
    interval = timedelta(hours=2)
    duration = timedelta(hours=1)
    data = event % {
        'VEVENTS': s % {
            'UID': uuid4(),
            'START': formatDate(base + i * interval),
            'END': formatDate(base + i * interval + duration),
            'SEQUENCE': i,
        },
    }
    return data.replace("\n", "\r\n")



def makeEvents(base, n):
    return [makeEventNear(base, i) for i in range(n)]



@inlineCallbacks
def measure(host, port, dtrace, events, samples):
    user = password = "user01"
    uid = "10000000-0000-0000-0000-000000000001"
    root = "/"
    principal = "/"
    calendar = "vfreebusy-benchmark"

    authinfo = HTTPDigestAuthHandler()
    authinfo.add_password(
        realm="Test Realm",
        uri="http://%s:%d/" % (host, port),
        user=user,
        passwd=password)
    agent = AuthHandlerAgent(Agent(reactor), authinfo)

    # First set things up
    account = yield initialize(
        agent, host, port, user, password, root, principal, calendar)

    base = "/calendars/users/%s/%s/foo-%%d.ics" % (user, calendar)
    baseTime = datetime.now().replace(hour=12, minute=15, second=0, microsecond=0)
    for i, cal in enumerate(makeEvents(baseTime, events)):
        yield account.writeData(base % (i,), cal, "text/calendar")

    method = 'POST'
    uri = 'http://%s:%d/calendars/__uids__/%s/outbox/' % (host, port, user)
    headers = Headers({
        "content-type": ["text/calendar"],
        "originator": ["mailto:%s@example.com" % (user,)],
        "recipient": ["urn:x-uid:%s, urn:x-uid:10000000-0000-0000-0000-000000000002" % (uid,)]})

    vfb = VFREEBUSY % {
        "attendees": "".join([
            "ATTENDEE:urn:x-uid:%s\n" % (uid,),
            "ATTENDEE:urn:x-uid:10000000-0000-0000-0000-000000000002\n"]),
        "start": formatDate(baseTime.replace(hour=0, minute=0)) + 'Z',
        "end": formatDate(
            baseTime.replace(hour=0, minute=0) + timedelta(days=1)) + 'Z'}
    body = StringProducer(vfb.replace("\n", "\r\n"))

    samples = yield sample(
        dtrace, samples,
        agent, lambda: (method, uri, headers, body),
        OK)
    returnValue(samples)
