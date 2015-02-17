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

from pycalendar.datetime import DateTime
from twext.enterprise.dal.syntax import Select
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.ical import Component, normalize_iCalStr
from txdav.caldav.datastore.sql import ManagedAttachment
from txdav.common.datastore.podding.migration.home_sync import CrossPodHomeSync
from txdav.common.datastore.podding.migration.migration_metadata import CalendarMigrationRecord
from txdav.common.datastore.podding.test.util import MultiStoreConduitTest
from txdav.common.datastore.sql_tables import schema
from txweb2.http_headers import MimeType
from txweb2.stream import MemoryStream


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

    caldata4 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid4
DTSTART:{now:04d}0102T180000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=DAILY
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
        children = yield home.listChildren()
        self.assertEqual(len(children), 0)
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
        children = yield home.listChildren()
        self.assertEqual(len(children), 0)
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
                results01[calendar.id()] = CalendarMigrationRecord.make(
                    calendarHomeResourceID=home01.id(),
                    remoteResourceID=calendar.id(),
                    localResourceID=0,
                    lastSyncToken=sync_token,
                )

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
        remote_id = calendar0.id()
        remote_sync_token = yield calendar0.syncToken()
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        syncer.homeId = yield syncer.prepareCalendarHome()

        # No local calendar exists yet
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        children = yield home1.listChildren()
        self.assertEqual(len(children), 0)
        yield self.commitTransaction(1)

        # Trigger sync of the one calendar
        local_sync_state = {}
        remote_sync_state = {remote_id: CalendarMigrationRecord.make(
            calendarHomeResourceID=home0.id(),
            remoteResourceID=remote_id,
            localResourceID=0,
            lastSyncToken=remote_sync_token,
        )}
        yield syncer.syncCalendar(
            remote_id,
            local_sync_state,
            remote_sync_state,
        )
        self.assertEqual(len(local_sync_state), 1)
        self.assertEqual(local_sync_state[remote_id].lastSyncToken, remote_sync_state[remote_id].lastSyncToken)

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
        o1 = yield calendar0.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        o2 = yield calendar0.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        o3 = yield calendar0.createCalendarObjectWithName("3.ics", Component.fromString(self.caldata3))
        remote_id = calendar0.id()
        mapping0 = dict([(o.name(), o.id()) for o in (o1, o2, o3)])
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        syncer.homeId = yield syncer.prepareCalendarHome()

        # No local calendar exists yet
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        calendar1 = yield home1.childWithName("calendar")
        self.assertTrue(calendar1 is None)
        yield self.commitTransaction(1)

        # Trigger sync of the one calendar
        local_sync_state = {}
        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            remote_id,
            local_sync_state,
            remote_sync_state,
        )
        self.assertEqual(len(local_sync_state), 1)
        self.assertEqual(local_sync_state[remote_id].lastSyncToken, remote_sync_state[remote_id].lastSyncToken)

        @inlineCallbacks
        def _checkCalendarObjectMigrationState(home, mapping1):
            com = schema.CALENDAR_OBJECT_MIGRATION
            mappings = yield Select(
                columns=[com.REMOTE_RESOURCE_ID, com.LOCAL_RESOURCE_ID],
                From=com,
                Where=(com.CALENDAR_HOME_RESOURCE_ID == home.id())
            ).on(self.theTransactionUnderTest(1))
            expected_mappings = dict([(mapping0[name], mapping1[name]) for name in mapping0.keys()])
            self.assertEqual(dict(mappings), expected_mappings)


        # Local calendar exists
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        calendar1 = yield home1.childWithName("calendar")
        self.assertTrue(calendar1 is not None)
        children = yield calendar1.objectResources()
        self.assertEqual(set([child.name() for child in children]), set(("1.ics", "2.ics", "3.ics",)))
        mapping1 = dict([(o.name(), o.id()) for o in children])
        yield _checkCalendarObjectMigrationState(home1, mapping1)
        yield self.commitTransaction(1)

        # Change one resource
        object0 = yield self.calendarObjectUnderTest(
            txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics"
        )
        yield object0.setComponent(Component.fromString(self.caldata1_changed))
        yield self.commitTransaction(0)

        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            remote_id,
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
        del mapping0["2.ics"]
        yield self.commitTransaction(0)

        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            remote_id,
            local_sync_state,
            remote_sync_state,
        )

        calendar1 = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(1), home=syncer.migratingUid(), name="calendar")
        children = yield calendar1.objectResources()
        self.assertEqual(set([child.name() for child in children]), set(("1.ics", "3.ics",)))
        mapping1 = dict([(o.name(), o.id()) for o in children])
        yield _checkCalendarObjectMigrationState(home1, mapping1)
        yield self.commitTransaction(1)

        # Add one resource
        calendar0 = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        o4 = yield calendar0.createCalendarObjectWithName("4.ics", Component.fromString(self.caldata4))
        mapping0[o4.name()] = o4.id()
        yield self.commitTransaction(0)

        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            remote_id,
            local_sync_state,
            remote_sync_state,
        )

        calendar1 = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(1), home=syncer.migratingUid(), name="calendar")
        children = yield calendar1.objectResources()
        self.assertEqual(set([child.name() for child in children]), set(("1.ics", "3.ics", "4.ics")))
        mapping1 = dict([(o.name(), o.id()) for o in children])
        yield _checkCalendarObjectMigrationState(home1, mapping1)
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_sync_calendars_add_remove(self):
        """
        Test that L{syncCalendar} syncs an initially non-existent local calendar with
        a remote calendar containing data. Also check a change to one event is then
        sync'd the second time.
        """

        home0 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        children0 = yield home0.loadChildren()
        details0 = dict([(child.id(), child.name()) for child in children0])
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        syncer.homeId = yield syncer.prepareCalendarHome()

        # No local calendar exists yet
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        children1 = yield home1.loadChildren()
        self.assertEqual(len(children1), 0)
        yield self.commitTransaction(1)

        # Trigger sync
        yield syncer.syncCalendarList()
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        children1 = yield home1.loadChildren()
        details1 = dict([(child.id(), child.name()) for child in children1])
        self.assertEqual(set(details1.values()), set(details0.values()))
        yield self.commitTransaction(1)

        # Add a calendar
        home0 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        newcalendar0 = yield home0.createCalendarWithName("new-calendar")
        details0[newcalendar0.id()] = newcalendar0.name()
        yield self.commitTransaction(0)

        # Trigger sync
        yield syncer.syncCalendarList()
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        children1 = yield home1.loadChildren()
        details1 = dict([(child.id(), child.name()) for child in children1])
        self.assertTrue("new-calendar" in details1.values())
        self.assertEqual(set(details1.values()), set(details0.values()))
        yield self.commitTransaction(1)

        # Remove a calendar
        home0 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        calendar0 = yield home0.childWithName("new-calendar")
        del details0[calendar0.id()]
        yield calendar0.remove()
        yield self.commitTransaction(0)

        # Trigger sync
        yield syncer.syncCalendarList()
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        children1 = yield home1.loadChildren()
        details1 = dict([(child.id(), child.name()) for child in children1])
        self.assertTrue("new-calendar" not in details1.values())
        self.assertEqual(set(details1.values()), set(details0.values()))
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_sync_attachments_add_remove(self):
        """
        Test that L{syncAttachments} syncs attachment data, then an update to the data,
        and finally a removal of the data.
        """


        home0 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        calendar0 = yield home0.childWithName("calendar")
        yield calendar0.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar0.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield calendar0.createCalendarObjectWithName("3.ics", Component.fromString(self.caldata3))
        remote_id = calendar0.id()
        mapping0 = dict()
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        syncer.homeId = yield syncer.prepareCalendarHome()

        # Trigger sync of the one calendar
        local_sync_state = {}
        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            remote_id,
            local_sync_state,
            remote_sync_state,
        )
        self.assertEqual(len(local_sync_state), 1)
        self.assertEqual(local_sync_state[remote_id].lastSyncToken, remote_sync_state[remote_id].lastSyncToken)

        # Sync attachments
        changed, removed = yield syncer.syncAttachments()
        self.assertEqual(changed, set())
        self.assertEqual(removed, set())

        @inlineCallbacks
        def _checkAttachmentObjectMigrationState(home, mapping1):
            am = schema.ATTACHMENT_MIGRATION
            mappings = yield Select(
                columns=[am.REMOTE_RESOURCE_ID, am.LOCAL_RESOURCE_ID],
                From=am,
                Where=(am.CALENDAR_HOME_RESOURCE_ID == home.id())
            ).on(self.theTransactionUnderTest(1))
            expected_mappings = dict([(mapping0[name], mapping1[name]) for name in mapping0.keys()])
            self.assertEqual(dict(mappings), expected_mappings)


        # Local calendar exists
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        calendar1 = yield home1.childWithName("calendar")
        self.assertTrue(calendar1 is not None)
        children = yield calendar1.objectResources()
        self.assertEqual(set([child.name() for child in children]), set(("1.ics", "2.ics", "3.ics",)))

        attachments = yield home1.getAllAttachments()
        mapping1 = dict([(o.md5(), o.id()) for o in attachments])
        yield _checkAttachmentObjectMigrationState(home1, mapping1)
        yield self.commitTransaction(1)

        # Add one attachment
        object1 = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics")
        attachment, _ignore_location = yield object1.addAttachment(None, MimeType.fromString("text/plain"), "test.txt", MemoryStream("Here is some text #1."))
        id0_1 = attachment.id()
        md50_1 = attachment.md5()
        managedid0_1 = attachment.managedID()
        mapping0[md50_1] = id0_1
        yield self.commitTransaction(0)

        # Sync attachments
        changed, removed = yield syncer.syncAttachments()
        self.assertEqual(changed, set((id0_1,)))
        self.assertEqual(removed, set())

        # Validate changes
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        attachments = yield home1.getAllAttachments()
        mapping1 = dict([(o.md5(), o.id()) for o in attachments])
        yield _checkAttachmentObjectMigrationState(home1, mapping1)

        # Add another attachment
        object1 = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="2.ics")
        attachment, _ignore_location = yield object1.addAttachment(None, MimeType.fromString("text/plain"), "test2.txt", MemoryStream("Here is some text #2."))
        id0_2 = attachment.id()
        md50_2 = attachment.md5()
        mapping0[md50_2] = id0_2
        yield self.commitTransaction(0)

        # Sync attachments
        changed, removed = yield syncer.syncAttachments()
        self.assertEqual(changed, set((id0_2,)))
        self.assertEqual(removed, set())

        # Validate changes
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        attachments = yield home1.getAllAttachments()
        mapping1 = dict([(o.md5(), o.id()) for o in attachments])
        yield _checkAttachmentObjectMigrationState(home1, mapping1)

        # Change original attachment (this is actually a remove and a create all in one)
        object1 = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics")
        attachment, _ignore_location = yield object1.updateAttachment(managedid0_1, MimeType.fromString("text/plain"), "test.txt", MemoryStream("Here is some text #1 - changed."))
        del mapping0[md50_1]
        id0_1_changed = attachment.id()
        md50_1_changed = attachment.md5()
        managedid0_1_changed = attachment.managedID()
        mapping0[md50_1_changed] = id0_1_changed
        yield self.commitTransaction(0)

        # Sync attachments
        changed, removed = yield syncer.syncAttachments()
        self.assertEqual(changed, set((id0_1_changed,)))
        self.assertEqual(removed, set((id0_1,)))

        # Validate changes
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        attachments = yield home1.getAllAttachments()
        mapping1 = dict([(o.md5(), o.id()) for o in attachments])
        yield _checkAttachmentObjectMigrationState(home1, mapping1)

        # Add original to a different resource
        object1 = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics")
        component = yield object1.componentForUser()
        attach = component.mainComponent().getProperty("ATTACH")

        object1 = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="3.ics")
        component = yield object1.componentForUser()
        attach = component.mainComponent().addProperty(attach)
        yield object1.setComponent(component)
        yield self.commitTransaction(0)

        # Sync attachments
        changed, removed = yield syncer.syncAttachments()
        self.assertEqual(changed, set())
        self.assertEqual(removed, set())

        # Validate changes
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        attachments = yield home1.getAllAttachments()
        mapping1 = dict([(o.md5(), o.id()) for o in attachments])
        yield _checkAttachmentObjectMigrationState(home1, mapping1)

        # Change original attachment in original resource (this creates a new one and does not remove the old)
        object1 = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics")
        attachment, _ignore_location = yield object1.updateAttachment(managedid0_1_changed, MimeType.fromString("text/plain"), "test.txt", MemoryStream("Here is some text #1 - changed again."))
        id0_1_changed_again = attachment.id()
        md50_1_changed_again = attachment.md5()
        mapping0[md50_1_changed_again] = id0_1_changed_again
        yield self.commitTransaction(0)

        # Sync attachments
        changed, removed = yield syncer.syncAttachments()
        self.assertEqual(changed, set((id0_1_changed_again,)))
        self.assertEqual(removed, set())

        # Validate changes
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        attachments = yield home1.getAllAttachments()
        mapping1 = dict([(o.md5(), o.id()) for o in attachments])
        yield _checkAttachmentObjectMigrationState(home1, mapping1)


    @inlineCallbacks
    def test_link_attachments(self):
        """
        Test that L{linkAttachments} links attachment data to the associated calendar object.
        """

        home0 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        calendar0 = yield home0.childWithName("calendar")
        object0_1 = yield calendar0.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        object0_2 = yield calendar0.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield calendar0.createCalendarObjectWithName("3.ics", Component.fromString(self.caldata3))
        remote_id = calendar0.id()

        attachment, _ignore_location = yield object0_1.addAttachment(None, MimeType.fromString("text/plain"), "test.txt", MemoryStream("Here is some text #1."))
        id0_1 = attachment.id()
        md50_1 = attachment.md5()
        managedid0_1 = attachment.managedID()
        pathID0_1 = ManagedAttachment.lastSegmentOfUriPath(managedid0_1, attachment.name())

        attachment, _ignore_location = yield object0_2.addAttachment(None, MimeType.fromString("text/plain"), "test2.txt", MemoryStream("Here is some text #2."))
        id0_2 = attachment.id()
        md50_2 = attachment.md5()
        managedid0_2 = attachment.managedID()
        pathID0_2 = ManagedAttachment.lastSegmentOfUriPath(managedid0_2, attachment.name())

        yield self.commitTransaction(0)

        # Add original to a different resource
        object1 = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="1.ics")
        component = yield object1.componentForUser()
        attach = component.mainComponent().getProperty("ATTACH")

        object1 = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(0), home="user01", calendar_name="calendar", name="3.ics")
        component = yield object1.componentForUser()
        attach = component.mainComponent().addProperty(attach)
        yield object1.setComponent(component)
        yield self.commitTransaction(0)

        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.loadRecord()
        syncer.homeId = yield syncer.prepareCalendarHome()

        # Trigger sync of the one calendar
        local_sync_state = {}
        remote_sync_state = yield syncer.getCalendarSyncList()
        yield syncer.syncCalendar(
            remote_id,
            local_sync_state,
            remote_sync_state,
        )
        self.assertEqual(len(local_sync_state), 1)
        self.assertEqual(local_sync_state[remote_id].lastSyncToken, remote_sync_state[remote_id].lastSyncToken)

        # Sync attachments
        changed, removed = yield syncer.syncAttachments()
        self.assertEqual(changed, set((id0_1, id0_2,)))
        self.assertEqual(removed, set())

        # Link attachments
        len_links = yield syncer.linkAttachments()
        self.assertEqual(len_links, 3)

        # Local calendar exists
        home1 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=syncer.migratingUid())
        calendar1 = yield home1.childWithName("calendar")
        self.assertTrue(calendar1 is not None)
        children = yield calendar1.objectResources()
        self.assertEqual(set([child.name() for child in children]), set(("1.ics", "2.ics", "3.ics",)))

        # Make sure calendar object is associated with attachment
        object1 = yield calendar1.objectResourceWithName("1.ics")
        attachments = yield object1.managedAttachmentList()
        self.assertEqual(attachments, [pathID0_1, ])

        attachment = yield object1.attachmentWithManagedID(managedid0_1)
        self.assertTrue(attachment is not None)
        self.assertEqual(attachment.md5(), md50_1)

        # Make sure calendar object is associated with attachment
        object1 = yield calendar1.objectResourceWithName("2.ics")
        attachments = yield object1.managedAttachmentList()
        self.assertEqual(attachments, [pathID0_2, ])

        attachment = yield object1.attachmentWithManagedID(managedid0_2)
        self.assertTrue(attachment is not None)
        self.assertEqual(attachment.md5(), md50_2)

        # Make sure calendar object is associated with attachment
        object1 = yield calendar1.objectResourceWithName("3.ics")
        attachments = yield object1.managedAttachmentList()
        self.assertEqual(attachments, [pathID0_1, ])

        attachment = yield object1.attachmentWithManagedID(managedid0_1)
        self.assertTrue(attachment is not None)
        self.assertEqual(attachment.md5(), md50_1)
