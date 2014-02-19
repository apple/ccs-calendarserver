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


from txdav.common.datastore.work.inbox_cleanup import InboxCleanupWork, CleanupOneInboxWork
from txdav.common.datastore.test.util import CommonCommonTests, populateCalendarsFrom


from twext.enterprise.dal.syntax import Select, Update, Parameter
from twext.enterprise.queue import WorkItem
from twext.python.clsprop import classproperty
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from twistedcaldav.config import config
from txdav.caldav.datastore.test.util import buildCalendarStore
from txdav.common.datastore.sql_tables import schema
import datetime


class InboxCleanupTests(CommonCommonTests, TestCase):
    """
    Test store-based address book sharing.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(InboxCleanupTests, self).setUp()
        self._sqlStore = yield buildCalendarStore(self, self.notifierFactory)
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        calendarRequirements = self.requirements["calendar"]
        yield populateCalendarsFrom(calendarRequirements, self.storeUnderTest())

        self.notifierFactory.reset()

    cal1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid1
DTSTART:20131122T140000
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

    cal2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid2
DTSTART:20131122T140000
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:event 2
END:VEVENT
END:VCALENDAR
"""

    cal3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid3
DTSTART:20131122T140000
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:event 3
END:VEVENT
END:VCALENDAR
"""


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
            "calendar": {
                "user01": {
                    "calendar": {
                        "cal1.ics": (cls.cal1, None,),
                        "cal2.ics": (cls.cal2, None,),
                        "cal3.ics": (cls.cal3, None,),
                    },
                    "inbox": {
                        "cal1.ics": (cls.cal1, None,),
                        "cal2.ics": (cls.cal2, None,),
                        "cal3.ics": (cls.cal3, None,),
                    },
                },
                "user02": {
                    "calendar": {
                    },
                    "inbox": {
                    },
                },
            }
        }


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlStore


    @inlineCallbacks
    def test_inboxCleanupWorkQueueing(self):
        """
        Verify that InboxCleanupWork queues one CleanupOneInboxBoxWork per home
        """
        class FakeInboxCleanupWork(WorkItem):
            @classmethod
            def _schedule(cls, txn, seconds):
                pass

        self.patch(InboxCleanupWork, "_schedule", FakeInboxCleanupWork._schedule)

        class FakeCleanupOneInboxWork(WorkItem):
            scheduledHomeIDs = []

            @classmethod
            def _schedule(cls, txn, homeID, seconds):
                cls.scheduledHomeIDs.append(homeID)
                pass

        self.patch(CleanupOneInboxWork, "_schedule", FakeCleanupOneInboxWork._schedule)

        # do cleanup
        wp = yield self.transactionUnderTest().enqueue(InboxCleanupWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        ch = schema.CALENDAR_HOME
        workRows = yield Select(
            [ch.OWNER_UID],
            From=ch,
            Where=ch.RESOURCE_ID.In(Parameter("scheduledHomeIDs", len(FakeCleanupOneInboxWork.scheduledHomeIDs))),
        ).on(self.transactionUnderTest(), scheduledHomeIDs=FakeCleanupOneInboxWork.scheduledHomeIDs)
        homeUIDs = [workRow[0] for workRow in workRows]
        self.assertEqual(set(homeUIDs), set(['user01', 'user02'])) # two homes


    @inlineCallbacks
    def test_orphans(self):
        """
        Verify that orphaned Inbox items are removed
        """
        self.patch(config, "InboxItemLifetimeDays", -1)
        self.patch(config, "InboxItemLifetimePastEventEndDays", -1)

        #create orphans by deleting events
        inbox = yield self.calendarUnderTest(home="user01", name="inbox")
        for item in (yield inbox.objectResourcesWithNames(["cal1.ics", "cal3.ics"])):
            yield item.remove()

        # do cleanup
        wp = yield self.transactionUnderTest().enqueue(CleanupOneInboxWork, homeID=inbox.ownerHome()._resourceID, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # check that orphans are deleted
        inbox = yield self.calendarUnderTest(home="user01", name="inbox")
        items = yield inbox.objectResources()
        names = [item.name() for item in items]
        self.assertEqual(set(names), set(["cal2.ics"]))


    @inlineCallbacks
    def test_old(self):
        """
        Verify that old inbox items are removed
        """
        self.patch(config, "InboxItemLifetimePastEventEndDays", -1)

        # Predate some inbox items
        inbox = yield self.calendarUnderTest(home="user01", name="inbox")
        oldDate = datetime.datetime.utcnow() - datetime.timedelta(days=float(config.InboxItemLifetimeDays), seconds=10)

        itemsToPredate = ["cal2.ics", "cal3.ics"]
        co = schema.CALENDAR_OBJECT
        yield Update({co.CREATED: oldDate},
            Where=co.RESOURCE_NAME.In(Parameter("itemsToPredate", len(itemsToPredate))).And(
            co.CALENDAR_RESOURCE_ID == inbox._resourceID)).on(self.transactionUnderTest(), itemsToPredate=itemsToPredate)

        # do cleanup
        wp = yield self.transactionUnderTest().enqueue(CleanupOneInboxWork, homeID=inbox.ownerHome()._resourceID, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # check that old items are deleted
        inbox = yield self.calendarUnderTest(home="user01", name="inbox")
        items = yield inbox.objectResources()
        names = [item.name() for item in items]
        self.assertEqual(set(names), set(["cal1.ics"]))


    @inlineCallbacks
    def test_referenceOldEvent(self):
        """
        Verify that inbox items references old events are removed
        """
        # events are already too old, so make one event end now
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        cal3Event = yield calendar.objectResourceWithName("cal3.ics")

        tr = schema.TIME_RANGE
        yield Update({tr.END_DATE: datetime.datetime.utcnow()},
            Where=tr.CALENDAR_OBJECT_RESOURCE_ID == cal3Event._resourceID).on(
            self.transactionUnderTest())
        # do cleanup
        wp = yield self.transactionUnderTest().enqueue(CleanupOneInboxWork, homeID=calendar.ownerHome()._resourceID, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # check that old items are deleted
        inbox = yield self.calendarUnderTest(home="user01", name="inbox")
        items = yield inbox.objectResources()
        names = [item.name() for item in items]
        self.assertEqual(set(names), set(["cal3.ics"]))
