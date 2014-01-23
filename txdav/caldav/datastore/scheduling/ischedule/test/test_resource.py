##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from txweb2 import http_headers, responsecode
from txweb2.test.test_server import SimpleRequest

from twisted.internet.defer import inlineCallbacks

from twistedcaldav.config import config
from twistedcaldav.memcachelock import MemcacheLock

from txdav.caldav.datastore.scheduling.ischedule.resource import IScheduleInboxResource
from txdav.caldav.datastore.scheduling.ischedule.remoteservers import IScheduleServerRecord, \
    IScheduleServers
from txdav.common.datastore.test.util import populateCalendarsFrom, \
    CommonCommonTests
from twext.python.clsprop import classproperty
import txweb2.dav.test.util
from txdav.caldav.datastore.test.util import buildCalendarStore

class iSchedulePOST (CommonCommonTests, txweb2.dav.test.util.TestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(iSchedulePOST, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        self.directory = self._sqlCalendarStore.directoryService()

        self.site.resource.putChild("ischedule", IScheduleInboxResource(self.site.resource, self.storeUnderTest()))

        yield self.populate()


    def storeUnderTest(self):
        """
        Return a store for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user02": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user03": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
    }


    @inlineCallbacks
    def test_deadlock(self):
        """
        Make calendar
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/ischedule",
            headers=http_headers.Headers(rawHeaders={
                "Originator": ("mailto:wsanchez@example.com",),
                "Recipient": ("mailto:cdaboo@example.com",),
                "Content-Type": "text/calendar",
            }),
            content="""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20060101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:deadlocked
ORGANIZER:mailto:wsanchez@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:wsanchez@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:cdaboo@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        )

        # Lock the UID here to force a deadlock - but adjust the timeout so the test does not wait too long
        self.patch(config.Scheduling.Options, "UIDLockTimeoutSeconds", 1)
        lock = MemcacheLock("ImplicitUIDLock", "deadlocked", timeout=60, expire_time=60)
        yield lock.acquire()

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.CONFLICT)

    test_deadlock.skip = "Locking behavior is different now"


    @inlineCallbacks
    def test_receive(self):
        """
        Make calendar
        """

        IScheduleServers()
        server = IScheduleServerRecord("http://127.0.0.1")
        server.allow_from = True
        IScheduleServers._domainMap["example.org"] = server
        self.addCleanup(lambda : IScheduleServers._domainMap.pop("example.org")) #@UndefinedVariable

        request = SimpleRequest(
            self.site,
            "POST",
            "/ischedule",
            headers=http_headers.Headers(rawHeaders={
                "Originator": ("mailto:user01@example.org",),
                "Recipient": ("mailto:user02@example.com",),
                "Content-Type": ("text/calendar",)
            }),
            content="""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
METHOD:REQUEST
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20060101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:deadlocked
ORGANIZER:mailto:user01@example.org
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user01@example.org
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.OK)

        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user02"))
        count = (yield calendar.listCalendarObjects())
        self.assertEqual(len(count), 1)

        inbox = (yield self.calendarUnderTest(name="inbox", home="user02"))
        count = (yield inbox.listCalendarObjects())
        self.assertEqual(len(count), 1)
