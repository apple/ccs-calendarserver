##
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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
from twistedcaldav.ical import Component
from twext.enterprise.jobqueue import JobItem, WorkItem
from txdav.common.datastore.sql_tables import scheduleActionFromSQL
from twisted.internet import reactor

"""
Tests for txdav.caldav.datastore.utils
"""

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from txdav.caldav.datastore.scheduling.work import ScheduleOrganizerWork, \
    ScheduleWorkMixin, ScheduleWork, ScheduleOrganizerSendWork
from txdav.common.datastore.test.util import populateCalendarsFrom, CommonCommonTests



class BaseWorkTests(CommonCommonTests, unittest.TestCase):
    """
    Tests for scheduling work.
    """
    @inlineCallbacks
    def setUp(self):

        yield super(BaseWorkTests, self).setUp()
        yield self.buildStoreAndDirectory()
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()

    requirements = {
        "user01": {
            "calendar": {
            },
            "inbox": {
            },
        },
        "user02": {
            "calendar": {
            },
            "inbox": {
            },
        },
        "user03": {
            "calendar": {
            },
            "inbox": {
            },
        },
    }


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore



class TestScheduleOrganizerWork(BaseWorkTests):
    """
    Test creation of L{ScheduleOrganizerWork} items.
    """

    calendar_old = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DURATION:PT1H
ORGANIZER:urn:uuid:user01
ATTENDEE:urn:uuid:user01
ATTENDEE:urn:uuid:user02
END:VEVENT
END:VCALENDAR
""")

    calendar_new = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER:urn:uuid:user01
ATTENDEE:urn:uuid:user01
ATTENDEE:urn:uuid:user02
END:VEVENT
END:VCALENDAR
""")


    @inlineCallbacks
    def test_create(self):
        """
        Test that jobs associated with L{txdav.caldav.datastore.scheduling.work.ScheduleOrganizerWork}
        can be created and correctly removed.
        """

        ScheduleWorkMixin._queued = 0
        txn = self.transactionUnderTest()
        home = yield self.homeUnderTest(name="user01")
        yield ScheduleOrganizerWork.schedule(
            txn,
            "12345-67890",
            "create",
            home,
            None,
            None,
            self.calendar_new,
            "urn:uuid:user01",
            2,
            True,
        )
        yield self.commit()
        self.assertEqual(ScheduleWorkMixin._queued, 1)

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 1)

        work = yield jobs[0].workItem()
        self.assertTrue(isinstance(work, ScheduleOrganizerWork))
        self.assertEqual(work.icalendarUid, "12345-67890")
        self.assertEqual(scheduleActionFromSQL[work.scheduleAction], "create")

        yield work.delete()
        yield jobs[0].delete()
        yield self.commit()

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 0)
        work = yield ScheduleOrganizerWork.all(self.transactionUnderTest())
        self.assertEqual(len(work), 0)
        baseWork = yield ScheduleWork.all(self.transactionUnderTest())
        self.assertEqual(len(baseWork), 0)


    @inlineCallbacks
    def test_cascade_delete_cleanup(self):
        """
        Test that when work associated with L{txdav.caldav.datastore.scheduling.work.ScheduleWork}
        is removed with the L{ScheduleWork} item being removed, the associated L{JobItem} runs and
        removes itself and the L{ScheduleWork}.
        """

        ScheduleWorkMixin._queued = 0
        txn = self.transactionUnderTest()
        home = yield self.homeUnderTest(name="user01")
        yield ScheduleOrganizerWork.schedule(
            txn,
            "12345-67890",
            "create",
            home,
            None,
            None,
            self.calendar_new,
            "urn:uuid:user01",
            2,
            True,
        )
        yield self.commit()
        self.assertEqual(ScheduleWorkMixin._queued, 1)

        jobs = yield JobItem.all(self.transactionUnderTest())
        work = yield jobs[0].workItem()
        yield WorkItem.delete(work)
        yield self.commit()

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 1)
        baseWork = yield ScheduleWork.all(self.transactionUnderTest())
        self.assertEqual(len(baseWork), 1)
        self.assertEqual(baseWork[0].jobID, jobs[0].jobID)

        work = yield jobs[0].workItem()
        self.assertTrue(work is None)
        yield self.commit()

        yield JobItem.waitEmpty(self.storeUnderTest().newTransaction, reactor, 60)

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 0)
        work = yield ScheduleOrganizerWork.all(self.transactionUnderTest())
        self.assertEqual(len(work), 0)
        baseWork = yield ScheduleWork.all(self.transactionUnderTest())
        self.assertEqual(len(baseWork), 0)



class TestScheduleOrganizerSendWork(BaseWorkTests):
    """
    Test creation of L{ScheduleOrganizerSendWork} items.
    """

    itip_new = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER:urn:x-uid:user01
{attendees}
END:VEVENT
END:VCALENDAR
""".format(attendees="\n".join(["ATTENDEE:urn:x-uid:user%02d" % i for i in range(1, 100)]))
)


    @inlineCallbacks
    def test_create(self):
        """
        Test that jobs associated with L{txdav.caldav.datastore.scheduling.work.ScheduleOrganizerSendWork}
        can be created and correctly removed.
        """

        txn = self.transactionUnderTest()
        home = yield self.homeUnderTest(name="user01")
        yield ScheduleOrganizerSendWork.schedule(
            txn,
            "create",
            home,
            None,
            "urn:x-uid:user01",
            "urn:x-uid:user02",
            self.itip_new,
            True,
            1000,
        )

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 1)

        work = yield jobs[0].workItem()
        yield work.doWork()

        home2 = yield self.calendarUnderTest(home="user02", name="calendar")
        cobjs = yield home2.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        #cal2 = yield cobjs[0].component()

        yield work.delete()
        yield jobs[0].delete()
        yield self.commit()
