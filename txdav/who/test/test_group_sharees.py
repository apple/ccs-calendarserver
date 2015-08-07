##
# Copyright (c) 2014-2015 Apple Inc. All rights reserved.
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

"""
    group sharee tests
"""

from twext.enterprise.jobs.jobitem import JobItem
from twext.python.filepath import CachingFilePath as FilePath
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.trial import unittest
from twistedcaldav.config import config
from txdav.caldav.datastore.test.util import populateCalendarsFrom, CommonCommonTests
from txdav.who.directory import CalendarDirectoryRecordMixin
from txdav.who.groups import GroupCacher, GroupShareeReconciliationWork
import os
from txdav.common.datastore.sql_tables import _BIND_MODE_GROUP, _BIND_MODE_WRITE, \
    _BIND_MODE_GROUP_READ
from txdav.common.datastore.sql_tables import _BIND_MODE_READ
from txdav.common.datastore.sql_tables import _BIND_STATUS_INVITED


class GroupShareeTestBase(CommonCommonTests, unittest.TestCase):
    """
    GroupShareeReconciliation tests
    """

    @inlineCallbacks
    def setUp(self):
        yield super(GroupShareeTestBase, self).setUp()

        accountsFilePath = FilePath(
            os.path.join(os.path.dirname(__file__), "accounts")
        )
        yield self.buildStoreAndDirectory(
            accounts=accountsFilePath.child("groupAccounts.xml"),
        )
        yield self.populate()

        self.paths = {}


    def configure(self):
        super(GroupShareeTestBase, self).configure()
        config.Sharing.Enabled = True
        config.Sharing.Calendars.Enabled = True
        config.Sharing.Calendars.Groups.Enabled = True
        config.Sharing.Calendars.Groups.ReconciliationDelaySeconds = 0


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())

    requirements = {
        "user01" : None,
        "user02" : None,
        "user03" : None,
        "user06" : None,
        "user07" : None,
        "user08" : None,
        "user09" : None,
        "user10" : None,
    }

    @inlineCallbacks
    def _verifyObjectResourceCount(self, home, expected_count):
        cal6 = yield self.calendarUnderTest(name="calendar", home=home)
        count = yield cal6.countObjectResources()
        self.assertEqual(count, expected_count)


    @inlineCallbacks
    def _check_notifications(self, uid, items):
        notifyHome = yield self.transactionUnderTest().notificationsWithUID(uid, create=True)
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(set(notifications), set(items))


    @inlineCallbacks
    def shareeViewUnderTest(self, txn=None, shareUID="calendar_1", home="user01"):
        """
        Get the calendar detailed by C{requirements['home1']['calendar_1']}.
        """
        returnValue((
            yield (yield self.homeUnderTest(txn, home)).shareeView(shareUID)
        ))



class GroupShareeReconciliationTests(GroupShareeTestBase):

    @inlineCallbacks
    def test_group_change_invite_smaller(self):
        """
        Test that group shares are changed when the group changes.
        """

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group02" or self.uid == "group03":
                returnValue(frozenset())
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group04")
        self.assertEqual(len(wps), 0)

        yield self._check_notifications("user01", [])

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        yield self._check_notifications("user01", [])
        shareeViews = yield calendar.inviteUIDToShare("group04", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 5)
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 5)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)

        # 1 group member
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group04")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        for invite in invites:
            self.assertEqual(invite.shareeUID, "user10")
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        yield self._check_notifications("user01", [])

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group04")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 0)


    @inlineCallbacks
    def test_group_change_invite_larger(self):
        """
        Test that group shares are changed when the group changes.
        """

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group02" or self.uid == "group03":
                returnValue(frozenset())
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # 1 group member
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group04")
        self.assertEqual(len(wps), 0)

        yield self._check_notifications("user01", [])

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        yield self._check_notifications("user01", [])
        shareeViews = yield calendar.inviteUIDToShare("group04", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 1)
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        for invite in invites:
            self.assertEqual(invite.shareeUID, "user10")
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)

        # group members restored
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", unpatchedExpandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group04")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 5)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group04")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 0)


    @inlineCallbacks
    def test_group_member_removal_refresh_slow(self):
        """
        Test that the sharee list is still valid when a member is removed from a group, but
        sharee reconciliation has not yet occurred.
        """

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group02":
                returnValue(frozenset())
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # Prevent sharee reconciliation
        def _noop(self):
            return succeed(None)
        self.patch(GroupShareeReconciliationWork, "doWork", _noop)

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group02")
        self.assertEqual(len(wps), 0)

        yield self._check_notifications("user01", [])

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        yield self._check_notifications("user01", [])
        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 3)
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)

        # 0 group members
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group02")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        yield self._check_notifications("user01", [])

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group02")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 3)


    @inlineCallbacks
    def test_no_self_invite(self):
        """
        Test that group shares where the group includes the sharee work. Then remove
        the sharee from the group and make sure it works.
        """

        record02 = yield self.transactionUnderTest().directoryService().recordWithUID("user02")

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group05":
                returnValue(frozenset((record02,)))
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group05")
        self.assertEqual(len(wps), 0)

        yield self._check_notifications("user01", [])

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        yield self._check_notifications("user01", [])
        shareeViews = yield calendar.inviteUIDToShare("group05", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 1)
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        # 1 group members
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group05")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        yield self._check_notifications("user01", [])

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group05")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 0)


    @inlineCallbacks
    def test_no_self_invite_on_add(self):
        """
        Test that the sharee is not invited to their own share when they are added as a member
        of a group to whom the calendar is shared.
        """

        record01 = yield self.transactionUnderTest().directoryService().recordWithUID("user01")
        record02 = yield self.transactionUnderTest().directoryService().recordWithUID("user02")

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group06":
                returnValue(frozenset((record01, record02,)))
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group06")
        self.assertEqual(len(wps), 0)

        yield self._check_notifications("user01", [])

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        yield self._check_notifications("user01", [])
        shareeViews = yield calendar.inviteUIDToShare("group06", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 1)
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        # 1 group members
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group06")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        yield self._check_notifications("user01", [])

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group06")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 0)


    @inlineCallbacks
    def test_group_change_trashed_calendar(self):
        """
        Test that group shares are properly cleaned when a calendar is trashed.
        """

        self.patch(config, "EnableTrashCollection", True)

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group02":
                returnValue(frozenset())
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group02")
        self.assertEqual(len(wps), 0)

        yield self._check_notifications("user01", [])

        # New calendar for sharing
        home = yield self.homeUnderTest(name="user01")
        yield home.createCalendarWithName("shared")
        yield self.commit()

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="shared")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        yield self._check_notifications("user01", [])
        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 3)
        calendar = yield self.calendarUnderTest(home="user01", name="shared")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)
        yield self.commit()

        # Trash the collection
        calendar = yield self.calendarUnderTest(home="user01", name="shared")
        yield calendar.remove()
        self.assertTrue(calendar.isInTrash())
        trash_id = calendar.id()
        yield self.commit()

        home = yield self.homeUnderTest(name="user01")
        calendar = yield home.childWithID(trash_id, onlyInTrash=True)
        self.assertTrue(calendar.isInTrash())
        invitations = yield calendar.allInvitations()
        self.assertEqual(len(invitations), 0)
        yield self.commit()

        # 1 group member
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group02")
        self.assertEqual(len(wps), 0)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)


    @inlineCallbacks
    def test_group_change_removed_calendar(self):
        """
        Test that group shares are properly cleaned when a calendar is removed (and not trashed).
        """

        self.patch(config, "EnableTrashCollection", False)

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group02":
                returnValue(frozenset())
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group02")
        self.assertEqual(len(wps), 0)

        yield self._check_notifications("user01", [])

        # New calendar for sharing
        home = yield self.homeUnderTest(name="user01")
        yield home.createCalendarWithName("shared")
        yield self.commit()

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="shared")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        yield self._check_notifications("user01", [])
        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 3)
        calendar = yield self.calendarUnderTest(home="user01", name="shared")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)
        yield self.commit()

        # Remove the collection
        calendar = yield self.calendarUnderTest(home="user01", name="shared")
        remove_id = calendar.id()
        yield calendar.remove()
        yield self.commit()

        home = yield self.homeUnderTest(name="user01")
        calendar = yield home.childWithID(remove_id)
        self.assertTrue(calendar is None)
        calendar = yield home.childWithID(remove_id, onlyInTrash=True)
        self.assertTrue(calendar is None)
        yield self.commit()

        # 1 group member
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group02")
        self.assertEqual(len(wps), 0)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)


    @inlineCallbacks
    def test_multiple_groups_remove_from_one_group(self):
        """
        Test that a multi-group share each containing the same user still lists the user
        when they are removed from one group.
        """

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group05":
                returnValue(frozenset())
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group05")
        self.assertEqual(len(wps), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group06")
        self.assertEqual(len(wps), 0)

        # Invite
        calendar = yield self.calendarUnderTest(home="user03", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViews = yield calendar.inviteUIDToShare("group05", _BIND_MODE_WRITE)
        self.assertEqual(len(shareeViews), 2)
        shareeViews = yield calendar.inviteUIDToShare("group06", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 1)

        calendar = yield self.calendarUnderTest(home="user03", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 2)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user03")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_WRITE)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 2)

        # Change group membership
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group05")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        calendar = yield self.calendarUnderTest(home="user03", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        for invite in invites:
            self.assertEqual(invite.shareeUID, "user02")
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user03")
            self.assertEqual(invite.uid, shareeView.shareName())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user03", name="calendar")
        yield calendar.uninviteUIDFromShare("group05")
        yield calendar.uninviteUIDFromShare("group06")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 0)


    @inlineCallbacks
    def test_multiple_groups_with_individual_remove_from_one_group(self):
        """
        Test that a multi-group share each containing the same user still lists the user
        when they are removed from one group.
        """

        @inlineCallbacks
        def expandedMembers(self, records=None, seen=None):

            if self.uid == "group05":
                returnValue(frozenset())
            else:
                returnValue((yield unpatchedExpandedMembers(self, records, seen)))

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers

        # setup group cacher
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group05")
        self.assertEqual(len(wps), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group06")
        self.assertEqual(len(wps), 0)

        # Invite
        calendar = yield self.calendarUnderTest(home="user03", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeView = yield calendar.inviteUIDToShare("user01", _BIND_MODE_READ)
        self.assertTrue(shareeView is not None)
        shareeViews = yield calendar.inviteUIDToShare("group05", _BIND_MODE_WRITE)
        self.assertEqual(len(shareeViews), 2)
        shareeViews = yield calendar.inviteUIDToShare("group06", _BIND_MODE_READ)
        self.assertEqual(len(shareeViews), 1)

        calendar = yield self.calendarUnderTest(home="user03", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 2)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user03")
            self.assertEqual(invite.uid, shareeView.shareName())
            if invite.shareeUID == "user01":
                self.assertEqual(invite.mode, _BIND_MODE_GROUP_READ)
            else:
                self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_WRITE)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 2)

        # Change group membership
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "group05")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        calendar = yield self.calendarUnderTest(home="user03", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 2)
        for invite in invites:
            shareeView = yield calendar.shareeView(invite.shareeUID)
            self.assertEqual(invite.ownerUID, "user03")
            self.assertEqual(invite.uid, shareeView.shareName())
            if invite.shareeUID == "user01":
                self.assertEqual(invite.mode, _BIND_MODE_READ)
            else:
                self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, None)
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user03", name="calendar")
        yield calendar.uninviteUIDFromShare("user01")
        yield calendar.uninviteUIDFromShare("group05")
        yield calendar.uninviteUIDFromShare("group06")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 0)
