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


from twext.python.clsprop import classproperty
from twext.python.filepath import CachingFilePath as FilePath
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from twistedcaldav import customxml
from twistedcaldav.stdconfig import config
from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.sql_tables import _BIND_MODE_DIRECT
from txdav.common.datastore.sql_tables import _BIND_MODE_GROUP
from txdav.common.datastore.sql_tables import _BIND_MODE_READ
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE
from txdav.common.datastore.sql_tables import _BIND_STATUS_ACCEPTED
from txdav.common.datastore.sql_tables import _BIND_STATUS_INVITED
from txdav.common.datastore.test.util import CommonCommonTests
from txdav.common.datastore.test.util import populateCalendarsFrom
from txdav.xml.base import WebDAVTextElement
from txdav.xml.element import registerElement, registerElementClass
import os

class BaseSharingTests(CommonCommonTests, TestCase):
    """
    Test store-based calendar sharing.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(BaseSharingTests, self).setUp()
        yield self.buildStoreAndDirectory()
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
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

    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "calendar": {
                "cal1.ics": (cls.cal1, None,),
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


    @inlineCallbacks
    def _createShare(self):
        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield calendar.inviteUIDToShare("user02", _BIND_MODE_READ, "summary")
        inviteUID = shareeView.shareUID()
        yield self.commit()

        # Accept
        shareeHome = yield self.homeUnderTest(name="user02")
        shareeView = yield shareeHome.acceptShare(inviteUID)
        sharedName = shareeView.name()
        yield self.commit()

        returnValue(sharedName)



class CalendarSharing(BaseSharingTests):

    @inlineCallbacks
    def test_no_shares(self):
        """
        Test that initially there are no shares.
        """

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())


    @inlineCallbacks
    def test_invite_sharee(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeView = yield calendar.inviteUIDToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].uid, shareeView.shareUID())
        self.assertEqual(invites[0].ownerUID, "user01")
        self.assertEqual(invites[0].shareeUID, "user02")
        self.assertEqual(invites[0].mode, _BIND_MODE_READ)
        self.assertEqual(invites[0].status, _BIND_STATUS_INVITED)
        self.assertEqual(invites[0].summary, "summary")
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID, ])

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)

        yield calendar.uninviteUIDFromShare("user02")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [])

        self.assertTrue(calendar.isShared())

        yield self.commit()

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())
        yield calendar.setShared(False)
        self.assertFalse(calendar.isShared())


    @inlineCallbacks
    def test_accept_share(self):
        """
        Test that invite+accept creates shares and notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeView = yield calendar.inviteUIDToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Accept
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Re-accept
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())


    @inlineCallbacks
    def test_decline_share(self):
        """
        Test that invite+decline does not create shares but does create notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeView = yield calendar.inviteUIDToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Decline
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Redecline
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())


    @inlineCallbacks
    def test_accept_decline_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the home.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeView = yield calendar.inviteUIDToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Accept
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Decline
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())


    @inlineCallbacks
    def test_accept_remove_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the shared collection (removal).
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield calendar.inviteUIDToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)

        yield self.commit()

        # Accept
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        yield self.commit()

        # Delete
        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        yield shared.deleteShare()

        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])


    @inlineCallbacks
    def test_inviteProperties(self):

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.setUsedForFreeBusy(True)
        yield self.commit()

        shared_name = yield self._createShare()

        shared = yield self.calendarUnderTest(home="user02", name=shared_name)
        self.assertFalse(shared.isUsedForFreeBusy())


    @inlineCallbacks
    def test_direct_sharee(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeView = yield calendar.directShareWithUser("user02")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].uid, shareeView.shareUID())
        self.assertEqual(invites[0].ownerUID, "user01")
        self.assertEqual(invites[0].shareeUID, "user02")
        self.assertEqual(invites[0].mode, _BIND_MODE_DIRECT)
        self.assertEqual(invites[0].status, _BIND_STATUS_ACCEPTED)

        sharedName = shareeView.name()
        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 0)

        yield self.commit()

        # Remove
        shared = yield self.calendarUnderTest(home="user02", name=sharedName)
        yield shared.deleteShare()

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 0)


    @inlineCallbacks
    def test_sharedNotifierID(self):
        shared_name = yield self._createShare()

        home = yield self.homeUnderTest(name="user01")
        self.assertEquals(home.notifierID(), ("CalDAV", "user01",))
        calendar = yield home.calendarWithName("calendar")
        self.assertEquals(calendar.notifierID(), ("CalDAV", "user01/calendar",))
        yield self.commit()

        home = yield self.homeUnderTest(name="user02")
        self.assertEquals(home.notifierID(), ("CalDAV", "user02",))
        calendar = yield home.calendarWithName(shared_name)
        self.assertEquals(calendar.notifierID(), ("CalDAV", "user01/calendar",))
        yield self.commit()


    @inlineCallbacks
    def test_perUserSharedProxyCollectionProperties(self):
        """
        Test that sharees and proxies get their own per-user properties, with some being
        initialized based ont he owner value.
        """
        @registerElement
        @registerElementClass
        class DummySharingProperty (WebDAVTextElement):
            namespace = "http://calendarserver.org/ns/"
            name = "dummy-sharing"

        shared_name = yield self._createShare()

        # Add owner properties
        home = yield self.homeUnderTest(name="user01")
        calendar = yield home.calendarWithName("calendar")

        calendar.properties()[PropertyName.fromElement(DummySharingProperty)] = DummySharingProperty.fromString("user01")
        calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)] = customxml.CalendarColor.fromString("#000001")
        yield self.commit()

        # Check/add sharee properties
        home = yield self.homeUnderTest(name="user02")
        calendar = yield home.calendarWithName(shared_name)
        self.assertTrue(PropertyName.fromElement(DummySharingProperty) not in calendar.properties())
        self.assertTrue(PropertyName.fromElement(customxml.CalendarColor) not in calendar.properties())
        calendar.properties()[PropertyName.fromElement(DummySharingProperty)] = DummySharingProperty.fromString("user02")
        calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)] = customxml.CalendarColor.fromString("#000002")
        yield self.commit()

        # Check/add owner proxy properties
        txn = self.transactionUnderTest()
        txn._authz_uid = "user03"
        home = yield self.homeUnderTest(name="user01")
        calendar = yield home.calendarWithName("calendar")
        self.assertTrue(PropertyName.fromElement(DummySharingProperty) in calendar.properties())
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(DummySharingProperty)]), "user01")
        self.assertTrue(PropertyName.fromElement(customxml.CalendarColor) in calendar.properties())
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)]), "#000001")
        calendar.properties()[PropertyName.fromElement(DummySharingProperty)] = DummySharingProperty.fromString("user03")
        calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)] = customxml.CalendarColor.fromString("#000003")
        yield self.commit()

        # Check/add sharee proxy properties
        txn = self.transactionUnderTest()
        txn._authz_uid = "user04"
        home = yield self.homeUnderTest(name="user02")
        calendar = yield home.calendarWithName(shared_name)
        self.assertTrue(PropertyName.fromElement(DummySharingProperty) in calendar.properties())
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(DummySharingProperty)]), "user02")
        self.assertTrue(PropertyName.fromElement(customxml.CalendarColor) in calendar.properties())
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)]), "#000002")
        calendar.properties()[PropertyName.fromElement(DummySharingProperty)] = DummySharingProperty.fromString("user04")
        calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)] = customxml.CalendarColor.fromString("#000004")
        yield self.commit()

        # Validate all properties
        home = yield self.homeUnderTest(name="user01")
        calendar = yield home.calendarWithName("calendar")
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(DummySharingProperty)]), "user03")
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)]), "#000001")
        yield self.commit()

        home = yield self.homeUnderTest(name="user02")
        calendar = yield home.calendarWithName(shared_name)
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(DummySharingProperty)]), "user04")
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)]), "#000002")
        yield self.commit()

        txn = self.transactionUnderTest()
        txn._authz_uid = "user03"
        home = yield self.homeUnderTest(name="user01")
        calendar = yield home.calendarWithName("calendar")
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(DummySharingProperty)]), "user03")
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)]), "#000003")
        yield self.commit()

        txn = self.transactionUnderTest()
        txn._authz_uid = "user04"
        home = yield self.homeUnderTest(name="user02")
        calendar = yield home.calendarWithName(shared_name)
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(DummySharingProperty)]), "user04")
        self.assertEqual(str(calendar.properties()[PropertyName.fromElement(customxml.CalendarColor)]), "#000004")
        yield self.commit()



class GroupSharing(BaseSharingTests):
    """
    Test store-based group book sharing.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(BaseSharingTests, self).setUp()

        accountsFilePath = FilePath(
            os.path.join(os.path.dirname(__file__), "accounts")
        )
        yield self.buildStoreAndDirectory(
            accounts=accountsFilePath.child("groupShareeAccounts.xml"),
            #resources=accountsFilePath.child("resources.xml"),
        )
        yield self.populate()

        self.paths = {}


    def configure(self):
        super(GroupSharing, self).configure()
        config.Sharing.Enabled = True
        config.Sharing.Calendars.Enabled = True
        config.Sharing.Calendars.Groups.Enabled = True
        config.Sharing.Calendars.Groups.ReconciliationDelaySeconds = 0


    @inlineCallbacks
    def _check_notifications(self, uid, items):
        notifyHome = yield self.transactionUnderTest().notificationsWithUID(uid)
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(set(notifications), set(items))


    @inlineCallbacks
    def test_no_shares(self):
        """
        Test that initially there are no shares.
        """

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)


    @inlineCallbacks
    def test_invite_empty_group(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        yield self._check_notifications("user01", [])

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        yield self._check_notifications("user01", [])
        shareeViews = yield calendar.inviteUIDToShare("group01", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViews), 0)
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group01")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 0)

        yield self.commit()

        yield self._check_notifications("user01", [])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())
        yield calendar.setShared(False)
        self.assertFalse(calendar.isShared())


    @inlineCallbacks
    def test_invite_group(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViews), 3)
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        shareeViews = sorted(shareeViews, key=lambda shareeView: shareeView.viewerHome().uid())
        invites = sorted(invites, key=lambda invitee: invitee.shareeUID)
        for i in range(len(invites)):
            self.assertEqual(invites[i].uid, shareeViews[i].shareUID())
            self.assertEqual(invites[i].ownerUID, "user01")
            self.assertEqual(invites[i].shareeUID, shareeViews[i].viewerHome().uid())
            self.assertEqual(invites[i].mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeViews[i].effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invites[i].status, _BIND_STATUS_INVITED)
            self.assertEqual(invites[i].summary, "summary")
            yield self._check_notifications(invites[i].shareeUID, [invites[i].uid, ])

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        self.assertTrue(calendar.isShared())

        yield calendar.uninviteUIDFromShare("group02")
        uninvites = yield calendar.sharingInvites()
        self.assertEqual(len(uninvites), 0)
        self.assertTrue(calendar.isShared())

        for i in range(len(invites)):
            yield self._check_notifications(invites[i].shareeUID, [])

        yield self.commit()

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())
        yield calendar.setShared(False)
        self.assertFalse(calendar.isShared())


    @inlineCallbacks
    def test_accept_share(self):
        """
        Test that invite+accept creates shares and notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViews), 3)
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        shareeViews = sorted(shareeViews, key=lambda shareeView: shareeView.viewerHome().uid())
        invites = sorted(invites, key=lambda invitee: invitee.shareeUID)
        for i in range(len(invites)):
            self.assertEqual(invites[i].uid, shareeViews[i].shareUID())
            self.assertEqual(invites[i].ownerUID, "user01")
            self.assertEqual(invites[i].shareeUID, shareeViews[i].viewerHome().uid())
            self.assertEqual(invites[i].mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeViews[i].effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invites[i].status, _BIND_STATUS_INVITED)
            self.assertEqual(invites[i].summary, "summary")
            yield self._check_notifications(invites[i].shareeUID, [invites[i].uid, ])

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Accept
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.acceptShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Re-accept
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.acceptShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())


    @inlineCallbacks
    def test_decline_share(self):
        """
        Test that invite+decline does not create shares but does create notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViews), 3)
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        shareeViews = sorted(shareeViews, key=lambda shareeView: shareeView.viewerHome().uid())
        invites = sorted(invites, key=lambda invitee: invitee.shareeUID)
        for i in range(len(invites)):
            self.assertEqual(invites[i].uid, shareeViews[i].shareUID())
            self.assertEqual(invites[i].ownerUID, "user01")
            self.assertEqual(invites[i].shareeUID, shareeViews[i].viewerHome().uid())
            self.assertEqual(invites[i].mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeViews[i].effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invites[i].status, _BIND_STATUS_INVITED)
            self.assertEqual(invites[i].summary, "summary")
            yield self._check_notifications(invites[i].shareeUID, [invites[i].uid, ])

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Decline
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.declineShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Re-decline
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.declineShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())


    @inlineCallbacks
    def test_accept_decline_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the home.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViews), 3)
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        shareeViews = sorted(shareeViews, key=lambda shareeView: shareeView.viewerHome().uid())
        invites = sorted(invites, key=lambda invitee: invitee.shareeUID)
        for i in range(len(invites)):
            self.assertEqual(invites[i].uid, shareeViews[i].shareUID())
            self.assertEqual(invites[i].ownerUID, "user01")
            self.assertEqual(invites[i].shareeUID, shareeViews[i].viewerHome().uid())
            self.assertEqual(invites[i].mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeViews[i].effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invites[i].status, _BIND_STATUS_INVITED)
            self.assertEqual(invites[i].summary, "summary")
            yield self._check_notifications(invites[i].shareeUID, [invites[i].uid, ])

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Accept
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.acceptShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Decline
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.declineShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())


    @inlineCallbacks
    def test_accept_remove_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the shared collection (removal).
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViews), 3)
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        shareeViews = sorted(shareeViews, key=lambda shareeView: shareeView.viewerHome().uid())
        invites = sorted(invites, key=lambda invitee: invitee.shareeUID)
        for i in range(len(invites)):
            self.assertEqual(invites[i].uid, shareeViews[i].shareUID())
            self.assertEqual(invites[i].ownerUID, "user01")
            self.assertEqual(invites[i].shareeUID, shareeViews[i].viewerHome().uid())
            self.assertEqual(invites[i].mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeViews[i].effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invites[i].status, _BIND_STATUS_INVITED)
            self.assertEqual(invites[i].summary, "summary")
            yield self._check_notifications(invites[i].shareeUID, [invites[i].uid, ])

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Accept
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.acceptShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Delete
        for invite in invites:
            shareeCalendar = yield self.calendarUnderTest(home=invite.shareeUID, name=invite.uid)
            yield shareeCalendar.deleteShare()

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())


    @inlineCallbacks
    def test_accept_uninvite_group(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the shared collection (removal).
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViews = yield calendar.inviteUIDToShare("group02", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViews), 3)
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)
        shareeViews = sorted(shareeViews, key=lambda shareeView: shareeView.viewerHome().uid())
        invites = sorted(invites, key=lambda invitee: invitee.shareeUID)
        for i in range(len(invites)):
            self.assertEqual(invites[i].uid, shareeViews[i].shareUID())
            self.assertEqual(invites[i].ownerUID, "user01")
            self.assertEqual(invites[i].shareeUID, shareeViews[i].viewerHome().uid())
            self.assertEqual(invites[i].mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeViews[i].effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invites[i].status, _BIND_STATUS_INVITED)
            self.assertEqual(invites[i].summary, "summary")
            yield self._check_notifications(invites[i].shareeUID, [invites[i].uid, ])

        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Accept
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.acceptShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Uninvite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group02")
        noinvites = yield calendar.sharingInvites()
        self.assertEqual(len(noinvites), 0)

        yield self.commit()

        # no extra notifications
        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())


    @inlineCallbacks
    def test_accept_two_groups(self):
        """
        Test that accept of two groups works.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViewsGroup02 = yield calendar.inviteUIDToShare("group02", _BIND_MODE_WRITE, "summary")
        self.assertEqual(len(shareeViewsGroup02), 3)
        shareeViewsGroup03 = yield calendar.inviteUIDToShare("group03", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViewsGroup03), 3)
        shareeViews = dict([(shareeView.shareUID(), shareeView) for shareeView in shareeViewsGroup02 + shareeViewsGroup03]).values()
        self.assertEqual(len(shareeViews), 4)
        shareeViews = sorted(shareeViews, key=lambda shareeView: shareeView.viewerHome().uid())
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 4)
        invites = sorted(invites, key=lambda invitee: invitee.shareeUID)
        for i in range(len(invites)):
            shareeView = shareeViews[i]
            invite = invites[i]
            self.assertEqual(invite.uid, shareeView.shareUID())
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.shareeUID, shareeView.viewerHome().uid())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_WRITE if shareeView in shareeViewsGroup02 else _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, "summary")
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        yield self.commit()

        # accept
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.acceptShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()


    @inlineCallbacks
    def test_accept_uninvite_two_groups(self):
        """
        Test that accept of two groups works, then uninvite each one.
        """

        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isShared())

        shareeViewsGroup02 = yield calendar.inviteUIDToShare("group02", _BIND_MODE_WRITE, "summary")
        self.assertEqual(len(shareeViewsGroup02), 3)
        shareeViewsGroup03 = yield calendar.inviteUIDToShare("group03", _BIND_MODE_READ, "summary")
        self.assertEqual(len(shareeViewsGroup03), 3)
        shareeViews = dict([(shareeView.shareUID(), shareeView) for shareeView in shareeViewsGroup02 + shareeViewsGroup03]).values()
        self.assertEqual(len(shareeViews), 4)
        shareeViews = sorted(shareeViews, key=lambda shareeView: shareeView.viewerHome().uid())
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 4)
        invites = sorted(invites, key=lambda invitee: invitee.shareeUID)
        for i in range(len(invites)):
            shareeView = shareeViews[i]
            invite = invites[i]
            self.assertEqual(invite.uid, shareeView.shareUID())
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.shareeUID, shareeView.viewerHome().uid())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_WRITE if shareeView in shareeViewsGroup02 else _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_INVITED)
            self.assertEqual(invite.summary, "summary")
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        yield self.commit()

        # accept
        for invite in invites:
            shareeHome = yield self.homeUnderTest(name=invite.shareeUID)
            yield shareeHome.acceptShare(invite.uid)

        yield self._check_notifications("user01", [invite.uid + "-reply" for invite in invites])

        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertTrue(calendar.isShared())

        yield self.commit()

        # Uninvite one
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group02")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 3)

        for invite in invites:
            shareeView = yield self.calendarUnderTest(home=invite.shareeUID, name=invite.uid)
            self.assertNotEqual(shareeView, None)
            self.assertEqual(invite.ownerUID, "user01")
            self.assertEqual(invite.shareeUID, shareeView.viewerHome().uid())
            self.assertEqual(invite.mode, _BIND_MODE_GROUP)
            self.assertEqual((yield shareeView.effectiveShareMode()), _BIND_MODE_READ)
            self.assertEqual(invite.status, _BIND_STATUS_ACCEPTED)
            self.assertEqual(invite.summary, "summary")
            yield self._check_notifications(invite.shareeUID, [invite.uid, ])

        yield self.commit()

        # Uninvite other
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.uninviteUIDFromShare("group03")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)


    '''
    @inlineCallbacks
    def test_accept_decline_two_groups(self):
        """
        Test that accept of two groups works, then decline each one.
        """

        # Two shares
        inviteUID1 = yield self._createGroupShare(groupname="group1.vcf")
        inviteUID2 = yield self._createGroupShare(groupname="group2.vcf")

        yield self._check_calendar("user02", "user01", self.all_children)
        yield self._check_notifications("user01", [inviteUID1 + "-reply", inviteUID2 + "-reply", ])

        yield self.commit()

        # Decline one
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID1)

        yield self._check_calendar("user02", "user01", self.group2_children)

        shared = yield self.calendarObjectUnderTest(home="user02", calendar_name="user01", name="group1.vcf")
        self.assertTrue(shared is None)
        shared = yield self.calendarObjectUnderTest(home="user02", calendar_name="user01", name="card2.vcf")
        self.assertTrue(shared is None)

        yield self.commit()

        # Decline other
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID2)

        sharedParent = yield self.calendarUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)


    @inlineCallbacks
    def test_accept_two_groups_different_access(self):
        """
        Test that accept of two groups works, then uninvite each one.
        """

        # Two shares
        inviteUID1 = yield self._createGroupShare(groupname="group1.vcf")
        inviteUID2 = yield self._createGroupShare(groupname="group2.vcf", mode=_BIND_MODE_WRITE)

        yield self._check_calendar("user02", "user01", self.all_children)
        yield self._check_notifications("user01", [inviteUID1 + "-reply", inviteUID2 + "-reply", ])

        # Read only for all, write for group2's items
        yield self._check_read_only("user02", "user01", ["group1.vcf", "card2.vcf", ])
        yield self._check_read_write("user02", "user01", ["group2.vcf", "card1.vcf", "card3.vcf", ])

        yield self.commit()

        # Decline one
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID2)

        yield self._check_calendar("user02", "user01", self.group1_children)

        yield self._check_read_only("user02", "user01", ["group1.vcf", "card1.vcf", "card2.vcf", ])

        shared = yield self.calendarObjectUnderTest(home="user02", calendar_name="user01", name="group2.vcf")
        self.assertTrue(shared is None)
        shared = yield self.calendarObjectUnderTest(home="user02", calendar_name="user01", name="card3.vcf")
        self.assertTrue(shared is None)

        yield self.commit()

        # Decline other
        shareeHome = yield self.homeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID1)

        sharedParent = yield self.calendarUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)
        '''

'''
class MixedSharing(BaseSharingTests):
    """
    Test store-based combined address book and group book sharing.
    """

    @inlineCallbacks
    def test_calendar_ro_then_groups(self):

        # Share address book read-only
        shareeName = yield self._createShare()
        yield self._check_calendar("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", self.all_children)
        yield self._check_read_write("user02", "user01", [])
        yield self._check_notifications("user02", [shareeName, ])

        # Add group1 read-write
        inviteUID1 = yield self._createGroupShare(groupname="group1.vcf", mode=_BIND_MODE_WRITE)

        yield self._check_calendar("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", ["group2.vcf", "card3.vcf", ])
        yield self._check_read_write("user02", "user01", ["group1.vcf", "card1.vcf", "card2.vcf", ])
        yield self._check_notifications("user02", [shareeName, inviteUID1, ])

        # Add group2 read-write
        inviteUID2 = yield self._createGroupShare(groupname="group2.vcf", mode=_BIND_MODE_WRITE)

        yield self._check_calendar("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", [])
        yield self._check_read_write("user02", "user01", self.all_children)
        yield self._check_notifications("user02", [shareeName, inviteUID1, inviteUID2])

        # Uninvite group1
        group = yield self.calendarObjectUnderTest(home="user01", calendar_name="calendar", name="group1.vcf")
        yield group.uninviteUIDFromShare("user02")

        yield self._check_calendar("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", ["group1.vcf", "card2.vcf", ])
        yield self._check_read_write("user02", "user01", ["group2.vcf", "card1.vcf", "card3.vcf", ])

        # Uninvite group2
        group = yield self.calendarObjectUnderTest(home="user01", calendar_name="calendar", name="group2.vcf")
        yield group.uninviteUIDFromShare("user02")

        yield self._check_calendar("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", self.all_children)
        yield self._check_read_write("user02", "user01", [])


    @inlineCallbacks
    def test_calendar_ro_then_group_no_accept(self):

        # Share address book read-only
        shareeName = yield self._createShare()
        yield self._check_calendar("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", self.all_children)
        yield self._check_read_write("user02", "user01", [])
        yield self._check_notifications("user02", [shareeName, ])

        # Add group1 read-write - but do not accept
        group = yield self.calendarObjectUnderTest(home="user01", calendar_name="calendar", name="group1.vcf")
        invited = yield group.inviteUIDToShare("user02", _BIND_MODE_WRITE, "summary")
        yield self._check_notifications("user02", [shareeName, invited.shareUID(), ])

        yield self._check_calendar("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", self.all_children)
        yield self._check_read_write("user02", "user01", [])



class SharingRevisions(BaseSharingTests):
    """
    Test store-based sharing and interaction with revision table.
    """

    @inlineCallbacks
    def test_shareWithRevision(self):
        """
        Verify that bindRevision on calendars and shared calendars has the correct value.
        """
        sharedName = yield self._createShare()

        normalCal = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertEqual(normalCal._bindRevision, 0)
        otherCal = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertNotEqual(otherCal._bindRevision, 0)


    @inlineCallbacks
    def test_updateShareRevision(self):
        """
        Verify that bindRevision on calendars and shared calendars has the correct value.
        """
        # Invite
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield calendar.inviteUIDToShare("user02", _BIND_MODE_READ, "summary")
        newCalName = shareeView.shareUID()
        yield self.commit()

        normalCal = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertEqual(normalCal._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="user02")
        otherCal = yield otherHome.anyObjectWithShareUID(newCalName)
        self.assertEqual(otherCal._bindRevision, 0)
        yield self.commit()

        shareeHome = yield self.homeUnderTest(name="user02")
        shareeView = yield shareeHome.acceptShare(newCalName)
        sharedName = shareeView.name()
        yield self.commit()

        normalCal = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertEqual(normalCal._bindRevision, 0)
        otherCal = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertNotEqual(otherCal._bindRevision, 0)


    @inlineCallbacks
    def test_sharedRevisions(self):
        """
        Verify that resourceNamesSinceRevision returns all resources after initial bind and sync.
        """
        sharedName = yield self._createShare()

        normalCal = yield self.calendarUnderTest(home="user01", name="calendar")
        self.assertEqual(normalCal._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="user02")
        otherCal = yield self.calendarUnderTest(home="user02", name=sharedName)
        self.assertNotEqual(otherCal._bindRevision, 0)

        changed, deleted, invalid = yield otherCal.resourceNamesSinceRevision(0)
        self.assertNotEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        changed, deleted, invalid = yield otherCal.resourceNamesSinceRevision(otherCal._bindRevision)
        self.assertEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        for depth, result in (
            ("1", [otherCal.name() + '/',
                   'calendar/',
                   'inbox/'],
            ),
            ("infinity", [otherCal.name() + '/',
                         otherCal.name() + '/cal1.ics',
                         'calendar/',
                         'inbox/'],
             )):
            changed, deleted, invalid = yield otherHome.resourceNamesSinceRevision(0, depth)
            self.assertEqual(set(changed), set(result))
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 0)

            changed, deleted, invalid = yield otherHome.resourceNamesSinceRevision(otherCal._bindRevision, depth)
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 0)
'''
