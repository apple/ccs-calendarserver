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

from twisted.internet.defer import inlineCallbacks
from txdav.common.datastore.podding.test.util import MultiStoreConduitTest
from txdav.common.datastore.podding.migration.home_sync import CrossPodHomeSync
from pycalendar.datetime import DateTime
from twistedcaldav.ical import Component, normalize_iCalStr


class TestConduitAPI(MultiStoreConduitTest):
    """
    Test that the conduit api works.
    """

    nowYear = {"now": DateTime.getToday().getYear()}

    caldata1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid1
DTSTART:{now:04d}0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**nowYear)

    caldata1_changed = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid1
DTSTART:{now:04d}0102T150000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance changed
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**nowYear)

    caldata2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid2
DTSTART:{now:04d}0102T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**nowYear)

    caldata3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid3
DTSTART:{now:04d}0102T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**nowYear)

    @inlineCallbacks
    def test_remote_home(self):
        """
        Test that a remote home can be accessed.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        home = yield syncer._remoteHome(self.theTransactionUnderTest(1))
        self.assertTrue(home is not None)
        self.assertEqual(home.id(), home01.id())
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_prepare_home(self):
        """
        Test that L{prepareCalendarHome} creates a home.
        """

        # No home present
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name=syncer.migratingUid())
        self.assertTrue(home is None)
        yield self.commitTransaction(1)

        yield syncer.prepareCalendarHome()

        # Home is present
        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name=syncer.migratingUid())
        self.assertTrue(home is not None)
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_prepare_home_external_txn(self):
        """
        Test that L{prepareCalendarHome} creates a home.
        """

        # No home present
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name=syncer.migratingUid())
        self.assertTrue(home is None)
        yield self.commitTransaction(1)

        yield syncer.prepareCalendarHome(txn=self.theTransactionUnderTest(1))
        yield self.commitTransaction(1)

        # Home is present
        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name=syncer.migratingUid())
        self.assertTrue(home is not None)
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_get_calendar_sync_list(self):
        """
        Test that L{getCalendarSyncList} returns the correct results.
        """

        yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        yield self.commitTransaction(0)
        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01")
        self.assertTrue(home01 is not None)
        calendars01 = yield home01.loadChildren()
        results01 = {}
        for calendar in calendars01:
            if calendar.owned():
                sync_token = yield calendar.syncToken()
                results01[calendar.name()] = sync_token
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        results = yield syncer.getCalendarSyncList()
        self.assertEqual(results, results01)


    @inlineCallbacks
    def test_sync_calendar_initial_empty(self):
        """
        Test that L{syncCalendar} syncs an initially non-existent local calendar with
        an empty remote calendar.
        """

        home0 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        calendar0 = yield home0.childWithName("calendar")
        remote_sync_token = yield calendar0.syncToken()
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        yield syncer.prepareCalendarHome()

        # No local calendar exists yet
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        calendar1 = yield home1.childWithName("calendar")
        self.assertTrue(calendar1 is None)
        yield self.commitTransaction(1)

        # Trigger sync of the one calendar
        local_sync_state = {}
        remote_sync_state = {"calendar": remote_sync_token}
        yield syncer.syncCalendar(
            "calendar",
            local_sync_state,
            remote_sync_state,
        )
        self.assertTrue("calendar" in local_sync_state)
        self.assertEqual(local_sync_state["calendar"], remote_sync_state["calendar"])

        # Local calendar exists
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        calendar1 = yield home1.childWithName("calendar")
        self.assertTrue(calendar1 is not None)
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_sync_calendar_initial_with_data(self):
        """
        Test that L{syncCalendar} syncs an initially non-existent local calendar with
        a remote calendar containing data. Also check a change to one event is then
        sync'd the second time.
        """

        home0 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        calendar0 = yield home0.childWithName("calendar")
        yield calendar0.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar0.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield calendar0.createCalendarObjectWithName("3.ics", Component.fromString(self.caldata3))
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        yield syncer.prepareCalendarHome()

        # No local calendar exists yet
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        calendar1 = yield home1.childWithName("calendar")
        self.assertTrue(calendar1 is None)
        yield self.commitTransaction(1)

        # Trigger sync of the one calendar
        local_sync_state = {}
        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            "calendar",
            local_sync_state,
            remote_sync_state,
        )
        self.assertTrue("calendar" in local_sync_state)
        self.assertEqual(local_sync_state["calendar"], remote_sync_state["calendar"])

        # Local calendar exists
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        calendar1 = yield home1.childWithName("calendar")
        self.assertTrue(calendar1 is not None)
        children = yield calendar1.listObjectResources()
        self.assertEqual(set(children), set(("1.ics", "2.ics", "3.ics",)))
        yield self.commitTransaction(1)

        # Change one resource
        object0 = yield self.calendarObjectUnderTest(
            txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics"
        )
        yield object0.setComponent(Component.fromString(self.caldata1_changed))
        yield self.commitTransaction(0)

        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            "calendar",
            local_sync_state,
            remote_sync_state,
        )

        object1 = yield self.calendarObjectUnderTest(
            txn=self.theTransactionUnderTest(1), home=syncer.migratingUid(), calendar_name="calendar", name="1.ics"
        )
        caldata = yield object1.component()
        self.assertEqual(normalize_iCalStr(caldata), normalize_iCalStr(self.caldata1_changed))
        yield self.commitTransaction(1)

        # Remove one resource
        object0 = yield self.calendarObjectUnderTest(
            txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="2.ics"
        )
        yield object0.remove()
        yield self.commitTransaction(0)

        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            "calendar",
            local_sync_state,
            remote_sync_state,
        )

        calendar1 = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(1), home=syncer.migratingUid(), name="calendar")
        children = yield calendar1.listObjectResources()
        self.assertEqual(set(children), set(("1.ics", "3.ics",)))
        yield self.commitTransaction(1)
