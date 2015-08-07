##
# Copyright (c) 2012-2015 Apple Inc. All rights reserved.
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

from pycalendar.datetime import DateTime
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav.ical import Component
from txdav.caldav.datastore.scheduling.ischedule.delivery import IScheduleRequest
from txdav.caldav.datastore.scheduling.ischedule.resource import IScheduleInboxResource
from txdav.common.datastore.podding.test.util import MultiStoreConduitTest
from txweb2.dav.test.util import SimpleRequest
from twext.internet.gaiendpoint import MultiFailure
from twisted.python.failure import Failure
from twisted.internet.error import ConnectionRefusedError
from twext.enterprise.jobs.jobitem import JobItem

class TestCrossPodScheduling (MultiStoreConduitTest):


    now = {
        "now": DateTime.getToday().getYear(),
        "now1": DateTime.getToday().getYear() + 1,
    }

    @inlineCallbacks
    def setUp(self):
        """
        Setup fake hook-up between pods
        """
        @inlineCallbacks
        def _fakeSubmitRequest(iself, ssl, host, port, request):

            if self.refuseConnection:
                raise MultiFailure((Failure(ConnectionRefusedError()),))
            else:
                pod = (port - 8008) / 100
                inbox = IScheduleInboxResource(self.site.resource, self.theStoreUnderTest(pod), podding=True)
                response = yield inbox.http_POST(SimpleRequest(
                    self.site,
                    "POST",
                    "http://{host}:{port}/podding".format(host=host, port=port),
                    request.headers,
                    request.stream.mem,
                ))
                returnValue(response)

        self.refuseConnection = False
        self.patch(IScheduleRequest, "_submitRequest", _fakeSubmitRequest)
        yield super(TestCrossPodScheduling, self).setUp()


    def configure(self):
        super(TestCrossPodScheduling, self).configure()

        # Enable the queue and make it slow
        self.patch(self.config.Scheduling.Options.WorkQueues, "Enabled", True)
        self.patch(self.config.Scheduling.Options.WorkQueues, "RequestDelaySeconds", 0.1)
        self.patch(self.config.Scheduling.Options.WorkQueues, "ReplyDelaySeconds", 0.1)
        self.patch(self.config.Scheduling.Options.WorkQueues, "AttendeeRefreshBatchDelaySeconds", 0.1)
        self.patch(self.config.Scheduling.Options.WorkQueues, "TemporaryFailureDelay", 5)


    @inlineCallbacks
    def test_simpleInvite(self):
        data_organizer = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data
DTSTART:{now1:04d}0102T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:data01_2
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:puser02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**self.now)

        # Organizer schedules
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        calendar = yield home.childWithName("calendar")
        yield calendar.createCalendarObjectWithName("1.ics", Component.fromString(data_organizer))
        yield self.commitTransaction(0)

        yield self.waitAllEmpty()

        # Data for user02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user02", create=True)
        calendar = yield home.childWithName("calendar")
        cobjs = yield calendar.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        self.assertEqual(cobjs[0].uid(), "uid_data")
        yield self.commitTransaction(0)

        # Data for puser02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name="puser02", create=True)
        calendar = yield home.childWithName("calendar")
        cobjs = yield calendar.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        self.assertEqual(cobjs[0].uid(), "uid_data")
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_connectionRefusedForOrganizer(self):
        data_organizer = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data
DTSTART:{now1:04d}0102T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:data01_2
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:puser02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**self.now)

        # Stop cross-pod connection from working
        self.refuseConnection = True

        # Organizer schedules
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        calendar = yield home.childWithName("calendar")
        yield calendar.createCalendarObjectWithName("1.ics", Component.fromString(data_organizer))
        yield self.commitTransaction(0)

        while True:
            jobs = yield JobItem.all(self.theTransactionUnderTest(0))
            yield self.commitTransaction(0)
            if len(jobs) == 1 and jobs[0].failed > 0:
                break

        # Data for user02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user02", create=True)
        calendar = yield home.childWithName("calendar")
        cobjs = yield calendar.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        self.assertEqual(cobjs[0].uid(), "uid_data")
        yield self.commitTransaction(0)

        # Data for puser02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name="puser02", create=True)
        calendar = yield home.childWithName("calendar")
        cobjs = yield calendar.calendarObjects()
        self.assertEqual(len(cobjs), 0)
        yield self.commitTransaction(1)

        # Now allow cross-pod to work
        self.refuseConnection = False

        yield self.waitAllEmpty()

        # Data for puser02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name="puser02", create=True)
        calendar = yield home.childWithName("calendar")
        cobjs = yield calendar.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        self.assertEqual(cobjs[0].uid(), "uid_data")
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_connectionRefusedForAttendee(self):
        data_organizer = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data
DTSTART:{now1:04d}0102T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:data01_2
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:puser02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**self.now)

        data_attendee = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data
DTSTART:{now1:04d}0102T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:data01_2
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:puser02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**self.now)

        # Organizer schedules
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        calendar = yield home.childWithName("calendar")
        yield calendar.createCalendarObjectWithName("1.ics", Component.fromString(data_organizer))
        yield self.commitTransaction(0)

        yield self.waitAllEmpty()

        # Data for user02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user02", create=True)
        calendar = yield home.childWithName("calendar")
        cobjs = yield calendar.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        self.assertEqual(cobjs[0].uid(), "uid_data")
        yield self.commitTransaction(0)

        # Data for puser02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name="puser02", create=True)
        calendar = yield home.childWithName("calendar")
        cobjs = yield calendar.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        self.assertEqual(cobjs[0].uid(), "uid_data")
        yield self.commitTransaction(1)

        # Stop cross-pod connection from working
        self.refuseConnection = True

        # Attendee changes
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name="puser02", create=True)
        calendar = yield home.childWithName("calendar")
        cobjs = yield calendar.calendarObjects()
        yield cobjs[0].setComponent(Component.fromString(data_attendee))
        yield self.commitTransaction(1)

        while True:
            jobs = yield JobItem.all(self.theTransactionUnderTest(1))
            yield self.commitTransaction(1)
            if len(jobs) == 1 and jobs[0].failed > 0:
                break

        # Organizer data unchanged
        cobj = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics")
        comp = yield cobj.componentForUser()
        self.assertTrue("DECLINED" not in str(comp))
        yield self.commitTransaction(0)

        # Now allow cross-pod to work
        self.refuseConnection = False

        yield self.waitAllEmpty()

        # Organizer data changed
        cobj = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics")
        comp = yield cobj.componentForUser()
        self.assertTrue("DECLINED" in str(comp))
        yield self.commitTransaction(0)
