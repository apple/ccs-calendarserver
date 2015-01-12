##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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
from txdav.caldav.datastore.scheduling.ischedule.localservers import (
    ServersDB, Server
)


class iSchedulePOST (CommonCommonTests, txweb2.dav.test.util.TestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(iSchedulePOST, self).setUp()

        serversDB = ServersDB()
        a_server = Server("A", "http://localhost:8008", thisServer=True)
        serversDB.addServer(a_server)
        b_server = Server("B", "http://localhost:8108", thisServer=False)
        serversDB.addServer(b_server)
        yield self.buildStoreAndDirectory(serversDB=serversDB)

        self.site.resource.putChild("ischedule", IScheduleInboxResource(self.site.resource, self.storeUnderTest()))
        self.site.resource.putChild("podding", IScheduleInboxResource(self.site.resource, self.storeUnderTest(), podding=True))

        yield self.populate()

        # iSchedule server
        IScheduleServers()
        server = IScheduleServerRecord("http://127.0.0.1")
        server.allow_from = True
        IScheduleServers._domainMap["example.org"] = server
        self.addCleanup(lambda : IScheduleServers._domainMap.pop("example.org")) #@UndefinedVariable


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


    @inlineCallbacks
    def test_receive_reject_local_originator(self):
        """
        Make calendar
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/ischedule",
            headers=http_headers.Headers(rawHeaders={
                "Originator": ("mailto:user01@example.com",),
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
ORGANIZER:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user01@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.FORBIDDEN)

        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        count = (yield calendar.listCalendarObjects())
        self.assertEqual(len(count), 0)

        inbox = (yield self.calendarUnderTest(name="inbox", home="user01"))
        count = (yield inbox.listCalendarObjects())
        self.assertEqual(len(count), 0)

        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user02"))
        count = (yield calendar.listCalendarObjects())
        self.assertEqual(len(count), 0)

        inbox = (yield self.calendarUnderTest(name="inbox", home="user02"))
        count = (yield inbox.listCalendarObjects())
        self.assertEqual(len(count), 0)


    @inlineCallbacks
    def test_receive_reject_podded_originator(self):
        """
        Make calendar
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/ischedule",
            headers=http_headers.Headers(rawHeaders={
                "Originator": ("mailto:puser01@example.com",),
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
ORGANIZER:mailto:puser01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:puser01@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.FORBIDDEN)

        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user02"))
        count = (yield calendar.listCalendarObjects())
        self.assertEqual(len(count), 0)

        inbox = (yield self.calendarUnderTest(name="inbox", home="user02"))
        count = (yield inbox.listCalendarObjects())
        self.assertEqual(len(count), 0)


    @inlineCallbacks
    def test_receive_podding(self):
        """
        Make calendar
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/podding",
            headers=http_headers.Headers(rawHeaders={
                "Originator": ("mailto:puser01@example.com",),
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
ORGANIZER:mailto:puser01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:puser01@example.com
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


    @inlineCallbacks
    def test_receive_podding_reject_external_originator(self):
        """
        Make calendar
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/podding",
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
        self.assertEqual(response.code, responsecode.FORBIDDEN)

        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user02"))
        count = (yield calendar.listCalendarObjects())
        self.assertEqual(len(count), 0)

        inbox = (yield self.calendarUnderTest(name="inbox", home="user02"))
        count = (yield inbox.listCalendarObjects())
        self.assertEqual(len(count), 0)


    @inlineCallbacks
    def test_receive_podding_reject_same_pod_originator(self):
        """
        Make calendar
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/podding",
            headers=http_headers.Headers(rawHeaders={
                "Originator": ("mailto:user01@example.com",),
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
ORGANIZER:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user01@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.FORBIDDEN)

        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user02"))
        count = (yield calendar.listCalendarObjects())
        self.assertEqual(len(count), 0)

        inbox = (yield self.calendarUnderTest(name="inbox", home="user02"))
        count = (yield inbox.listCalendarObjects())
        self.assertEqual(len(count), 0)
