##
# Copyright (c) 2005-2016 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks
from twisted.names import client
from twisted.python.modules import getModule
from twisted.trial import unittest
from twistedcaldav.stdconfig import config
from txdav.caldav.datastore.scheduling.ischedule import utils
from txdav.caldav.datastore.scheduling.ischedule.delivery import ScheduleViaISchedule, \
    IScheduleRequest
from txdav.caldav.datastore.scheduling.ischedule.remoteservers import IScheduleServerRecord
from txdav.caldav.datastore.scheduling.cuaddress import CalendarUser
from txdav.common.datastore.test.util import CommonCommonTests
import txweb2.dav.test.util
from twistedcaldav.ical import Component

class TestiSchedule (unittest.TestCase):
    """
    txdav.caldav.datastore.scheduling.ischedule tests
    """

    def tearDown(self):
        """
        By setting the resolver to None, it will be recreated next time a name
        lookup is done.
        """
        client.theResolver = None
        utils.DebugResolver = None


    @inlineCallbacks
    def test_matchCalendarUserAddress(self):
        """
        Make sure we do an exact comparison on EmailDomain
        """

        self.patch(config.Scheduling.iSchedule, "Enabled", True)
        self.patch(config.Scheduling.iSchedule, "RemoteServers", "")

        # Only mailtos:
        result = yield ScheduleViaISchedule.matchCalendarUserAddress("http://example.com/principal/user")
        self.assertFalse(result)

        # Need to setup a fake resolver
        module = getModule(__name__)
        dataPath = module.filePath.sibling("data")
        bindPath = dataPath.child("db.example.com")
        self.patch(config.Scheduling.iSchedule, "DNSDebug", bindPath.path)
        utils.DebugResolver = None
        utils._initResolver()

        result = yield ScheduleViaISchedule.matchCalendarUserAddress("mailto:user@example.com")
        self.assertTrue(result)
        result = yield ScheduleViaISchedule.matchCalendarUserAddress("mailto:user@example.org")
        self.assertFalse(result)
        result = yield ScheduleViaISchedule.matchCalendarUserAddress("mailto:user@example.org?subject=foobar")
        self.assertFalse(result)
        result = yield ScheduleViaISchedule.matchCalendarUserAddress("mailto:user")
        self.assertFalse(result)

        # Test when not enabled
        ScheduleViaISchedule.domainServerMap = {}
        self.patch(config.Scheduling.iSchedule, "Enabled", False)
        result = yield ScheduleViaISchedule.matchCalendarUserAddress("mailto:user@example.com")
        self.assertFalse(result)



class TestIScheduleRequest (CommonCommonTests, txweb2.dav.test.util.TestCase):
    """
    txdav.caldav.datastore.scheduling.ischedule tests
    """

    class FakeScheduler(object):
        def __init__(self, txn, organizer, caldata=None):
            self.txn = txn
            self.organizer = CalendarUser(organizer)
            self.calendar = Component.fromString(caldata) if caldata else None
            self.isiTIPRequest = True
            self.isfreebusy = False


    @inlineCallbacks
    def setUp(self):
        yield super(TestIScheduleRequest, self).setUp()
        yield self.buildStoreAndDirectory()


    @inlineCallbacks
    def test_prepareHeaders_podding(self):
        """
        Make sure Originator header is properly re-written.
        """

        txn = self.transactionUnderTest()
        server = IScheduleServerRecord("https://calendar.example.com", rewriteCUAddresses=False, podding=True)
        request = IScheduleRequest(
            self.FakeScheduler(txn, "urn:x-uid:user01"),
            server,
            (CalendarUser("urn:x-uid:user02"),),
            None, False,
        )
        _ignore_ssl, host, port, _ignore_path = server.details()
        yield request._prepareHeaders(host, port, "VEVENT", "REQUEST")
        yield txn.commit()

        self.assertEqual(request.headers.getRawHeaders("Originator")[0], "urn:x-uid:user01")
        self.assertEqual(request.headers.getRawHeaders("Recipient")[0], "urn:x-uid:user02")


    @inlineCallbacks
    def test_prepareHeaders_podding_with_rewrite(self):
        """
        Make sure Originator header is properly re-written.
        """

        txn = self.transactionUnderTest()
        server = IScheduleServerRecord("https://calendar.example.com", rewriteCUAddresses=True, podding=True)
        request = IScheduleRequest(
            self.FakeScheduler(txn, "urn:x-uid:user01"),
            server,
            (CalendarUser("urn:x-uid:user02"),),
            None, False,
        )
        _ignore_ssl, host, port, _ignore_path = server.details()
        yield request._prepareHeaders(host, port, "VEVENT", "REQUEST")
        yield txn.commit()

        self.assertEqual(request.headers.getRawHeaders("Originator")[0], "urn:uuid:user01")
        self.assertEqual(request.headers.getRawHeaders("Recipient")[0], "urn:uuid:user02")


    @inlineCallbacks
    def test_prepareHeaders_nopodding_with_rewrite(self):
        """
        Make sure Originator header is properly re-written.
        """

        txn = self.transactionUnderTest()
        server = IScheduleServerRecord("https://calendar.example.com", rewriteCUAddresses=True, podding=False)
        request = IScheduleRequest(
            self.FakeScheduler(txn, "urn:x-uid:user01"),
            server,
            (CalendarUser("mailto:user02@example.com"),),
            None, False,
        )
        _ignore_ssl, host, port, _ignore_path = server.details()
        yield request._prepareHeaders(host, port, "VEVENT", "REQUEST")
        yield txn.commit()

        self.assertEqual(request.headers.getRawHeaders("Originator")[0], "mailto:user01@example.com")
        self.assertEqual(request.headers.getRawHeaders("Recipient")[0], "mailto:user02@example.com")


    @inlineCallbacks
    def test_prepareData_podding(self):
        """
        Make sure Originator header is properly re-written.
        """

        txn = self.transactionUnderTest()
        server = IScheduleServerRecord("https://calendar.example.com", rewriteCUAddresses=False, podding=True)
        request = IScheduleRequest(
            self.FakeScheduler(
                txn, "urn:x-uid:user01",
                """BEGIN:VCALENDAR
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
ORGANIZER:urn:x-uid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""",
            ),
            server,
            (), None, False,
        )
        yield request._prepareData()
        yield txn.commit()

        ical = Component.fromString(request.data)
        self.assertEqual(ical.masterComponent().getOrganizer(), "urn:x-uid:user01")
        self.assertEqual(
            set([attendee.value() for attendee in ical.getAllAttendeeProperties()]),
            set(("urn:x-uid:user01", "urn:x-uid:user02")),
        )


    @inlineCallbacks
    def test_prepareData_podding_with_rewrite(self):
        """
        Make sure Originator header is properly re-written.
        """

        txn = self.transactionUnderTest()
        server = IScheduleServerRecord("https://calendar.example.com", rewriteCUAddresses=True, podding=True)
        request = IScheduleRequest(
            self.FakeScheduler(
                txn, "urn:x-uid:user01",
                """BEGIN:VCALENDAR
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
ORGANIZER:urn:x-uid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""",
            ),
            server,
            (), None, False,
        )
        yield request._prepareData()
        yield txn.commit()

        ical = Component.fromString(request.data)
        self.assertEqual(ical.masterComponent().getOrganizer(), "urn:uuid:user01")
        self.assertEqual(
            set([attendee.value() for attendee in ical.getAllAttendeeProperties()]),
            set(("urn:uuid:user01", "urn:uuid:user02")),
        )


    @inlineCallbacks
    def test_prepareData_nopodding_with_rewrite(self):
        """
        Make sure Originator header is properly re-written.
        """

        txn = self.transactionUnderTest()
        server = IScheduleServerRecord("https://calendar.example.com", rewriteCUAddresses=True, podding=False)
        request = IScheduleRequest(
            self.FakeScheduler(
                txn, "urn:x-uid:user01",
                """BEGIN:VCALENDAR
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
ORGANIZER:urn:x-uid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""",
            ),
            server,
            (), None, False,
        )
        yield request._prepareData()
        yield txn.commit()

        ical = Component.fromString(request.data)
        self.assertEqual(ical.masterComponent().getOrganizer(), "mailto:user01@example.com")
        self.assertEqual(
            set([attendee.value() for attendee in ical.getAllAttendeeProperties()]),
            set(("mailto:user01@example.com", "mailto:user02@example.com")),
        )
