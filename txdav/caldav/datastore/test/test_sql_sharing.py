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


from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase

from twext.python.clsprop import classproperty
from txdav.common.datastore.test.util import CommonCommonTests, \
    populateCalendarsFrom
from txdav.common.datastore.sql_tables import _BIND_MODE_READ, \
    _BIND_STATUS_INVITED, _BIND_MODE_DIRECT, _BIND_STATUS_ACCEPTED
from txdav.base.propertystore.base import PropertyName
from txdav.xml.base import WebDAVTextElement
from twistedcaldav import customxml
from txdav.xml.element import registerElement, registerElementClass


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

        shareeView = yield calendar.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
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

        shareeView = yield calendar.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
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

        yield calendar.uninviteUserFromShare("user02")
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

        shareeView = yield calendar.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
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

        shareeView = yield calendar.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
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

        shareeView = yield calendar.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
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

        shareeView = yield calendar.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
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

        shareeView = yield calendar.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
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
