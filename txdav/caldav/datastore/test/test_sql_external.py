##
# Copyright (c) 2013-2017 Apple Inc. All rights reserved.
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


from calendarserver.push.ipush import PushPriority

from operator import methodcaller

from twext.python.clsprop import classproperty

from twisted.internet.defer import inlineCallbacks

from twistedcaldav.ical import Component

from txdav.common.datastore.podding.base import FailedCrossPodRequestError
from txdav.common.datastore.podding.test.util import MultiStoreConduitTest
from txdav.common.datastore.sql_tables import _BIND_MODE_READ, \
    _BIND_STATUS_INVITED, _BIND_MODE_DIRECT, _BIND_STATUS_ACCEPTED, \
    _HOME_STATUS_EXTERNAL, _BIND_MODE_WRITE
from txdav.common.datastore.test.util import populateCalendarsFrom
from txdav.common.icommondatastore import ExternalShareFailed
from txdav.idav import ChangeCategory


class BaseSharingTests(MultiStoreConduitTest):

    """
    Test store-based calendar sharing.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(BaseSharingTests, self).setUp()
        yield self.populate()

    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.theStoreUnderTest(0))
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
DTSTART:20131123T140000
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:event 2
END:VEVENT
END:VCALENDAR
"""

    @classproperty(cache=False)
    def requirements(cls):  # @NoSelf
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


class CalendarSharing(BaseSharingTests):

    @inlineCallbacks
    def setUp(self):
        yield super(CalendarSharing, self).setUp()
        for store in self.theStores:
            store._poddingFailure = None
            store._poddingError = None

    @inlineCallbacks
    def test_no_shares(self):
        """
        Test that initially there are no shares.
        """

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isSharedByOwner())

    @inlineCallbacks
    def test_invite_sharee(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isSharedByOwner())

        shareeView = yield calendar.inviteUIDToShare("puser02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].uid, shareeView.shareUID())
        self.assertEqual(invites[0].ownerUID, "user01")
        self.assertEqual(invites[0].shareeUID, "puser02")
        self.assertEqual(invites[0].mode, _BIND_MODE_READ)
        self.assertEqual(invites[0].status, _BIND_STATUS_INVITED)
        self.assertEqual(invites[0].summary, "summary")

        inviteUID = shareeView.shareUID()
        sharedName = shareeView.name()

        self.assertTrue(calendar.isSharedByOwner())

        yield self.commitTransaction(0)

        shared = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(1), home="puser02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.theTransactionUnderTest(1).notificationsWithUID("puser02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + ".xml", ])
        yield self.commitTransaction(1)

        # Uninvite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)

        yield calendar.uninviteUIDFromShare("puser02")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        self.assertTrue(calendar.isSharedByOwner())

        yield self.commitTransaction(0)

        notifyHome = yield self.theTransactionUnderTest(1).notificationsWithUID("puser02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [])
        yield self.commitTransaction(1)

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertTrue(calendar.isSharedByOwner())
        yield calendar.setShared(False)
        self.assertFalse(calendar.isSharedByOwner())

    @inlineCallbacks
    def test_accept_share(self):
        """
        Test that invite+accept creates shares and notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isSharedByOwner())

        shareeView = yield calendar.inviteUIDToShare("puser02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)

        inviteUID = shareeView.shareUID()
        sharedName = shareeView.name()

        self.assertTrue(calendar.isSharedByOwner())

        yield self.commitTransaction(0)

        shared = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(1), home="puser02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.theTransactionUnderTest(1).notificationsWithUID("puser02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)
        yield self.commitTransaction(1)

        # Accept
        txn2 = self.theTransactionUnderTest(1)
        shareeHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is not None)
        yield self.commitTransaction(1)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply.xml", ])

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertTrue(calendar.isSharedByOwner())

        yield self.commitTransaction(0)

        # Re-accept
        txn2 = self.theTransactionUnderTest(1)
        shareeHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is not None)
        yield self.commitTransaction(1)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply.xml", ])

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertTrue(calendar.isSharedByOwner())

    @inlineCallbacks
    def test_decline_share(self):
        """
        Test that invite+decline does not create shares but does create notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isSharedByOwner())

        shareeView = yield calendar.inviteUIDToShare("puser02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)

        inviteUID = shareeView.shareUID()
        sharedName = shareeView.name()

        self.assertTrue(calendar.isSharedByOwner())

        yield self.commitTransaction(0)

        txn2 = self.theTransactionUnderTest(1)
        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield txn2.notificationsWithUID("puser02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)
        yield self.commitTransaction(1)

        # Decline
        txn2 = self.theTransactionUnderTest(1)
        shareeHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is None)
        yield self.commitTransaction(1)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply.xml", ])

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertTrue(calendar.isSharedByOwner())

        yield self.commitTransaction(0)

        # Redecline
        txn2 = self.theTransactionUnderTest(1)
        shareeHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is None)
        yield self.commitTransaction(1)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply.xml", ])

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertTrue(calendar.isSharedByOwner())

    @inlineCallbacks
    def test_accept_decline_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the home.
        """

        # Invite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isSharedByOwner())

        shareeView = yield calendar.inviteUIDToShare("puser02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()

        self.assertTrue(calendar.isSharedByOwner())

        yield self.commitTransaction(0)

        txn2 = self.theTransactionUnderTest(1)
        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield txn2.notificationsWithUID("puser02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)
        yield self.commitTransaction(1)

        # Accept
        txn2 = self.theTransactionUnderTest(1)
        shareeHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is not None)
        yield self.commitTransaction(1)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply.xml", ])

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertTrue(calendar.isSharedByOwner())

        yield self.commitTransaction(0)

        # Decline
        txn2 = self.theTransactionUnderTest(1)
        shareeHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is None)
        yield self.commitTransaction(1)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply.xml", ])

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertTrue(calendar.isSharedByOwner())

    @inlineCallbacks
    def test_accept_remove_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the shared collection (removal).
        """

        # Invite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield calendar.inviteUIDToShare("puser02", _BIND_MODE_READ, "summary")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)

        inviteUID = shareeView.shareUID()
        sharedName = shareeView.name()

        yield self.commitTransaction(0)

        txn2 = self.theTransactionUnderTest(1)
        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield txn2.notificationsWithUID("puser02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)
        yield self.commitTransaction(1)

        # Accept
        txn2 = self.theTransactionUnderTest(1)
        shareeHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is not None)
        yield self.commitTransaction(1)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply.xml", ])

        yield self.commitTransaction(0)

        # Delete
        txn2 = self.theTransactionUnderTest(1)
        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        yield shared.deleteShare()
        yield self.commitTransaction(1)

        txn2 = self.theTransactionUnderTest(1)
        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertTrue(shared is None)
        yield self.commitTransaction(1)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply.xml", ])

    @inlineCallbacks
    def test_accept_remove_accept(self):
        yield self.createShare()
        yield self.removeShare()
        shared_name = yield self.createShare()

        txn2 = self.theTransactionUnderTest(1)
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser02", name=shared_name)
        self.assertTrue(otherCal is not None)
        yield self.commitTransaction(1)

    @inlineCallbacks
    def test_accept_remove_accept_newcalendar(self):
        """
        Test that deleting and re-creating a share with the same sharer name works.
        """

        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        yield home.createCalendarWithName("shared")
        yield self.commitTransaction(0)

        shared_name = yield self.createShare(name="shared")

        txn2 = self.theTransactionUnderTest(1)
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser02", name=shared_name)
        self.assertTrue(otherCal is not None)
        yield self.commitTransaction(1)

        yield self.removeShare(name="shared")
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        yield home.removeCalendarWithName("shared")
        yield self.commitTransaction(0)

        txn2 = self.theTransactionUnderTest(1)
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser02", name=shared_name)
        self.assertTrue(otherCal is None)
        yield self.commitTransaction(1)

        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        yield home.createCalendarWithName("shared")
        yield self.commitTransaction(0)

        shared_name = yield self.createShare(name="shared")

        txn2 = self.theTransactionUnderTest(1)
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser02", name=shared_name)
        self.assertTrue(otherCal is not None)
        yield self.commitTransaction(1)

    @inlineCallbacks
    def test_inviteProperties(self):

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        yield calendar.setUsedForFreeBusy(True)
        yield self.commitTransaction(0)

        shared_name = yield self.createShare()

        txn2 = self.theTransactionUnderTest(1)
        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=shared_name)
        self.assertFalse(shared.isUsedForFreeBusy())

    @inlineCallbacks
    def test_direct_sharee(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        # Invite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isSharedByOwner())

        shareeView = yield calendar.directShareWithUser("puser02")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].uid, shareeView.shareUID())
        self.assertEqual(invites[0].ownerUID, "user01")
        self.assertEqual(invites[0].shareeUID, "puser02")
        self.assertEqual(invites[0].mode, _BIND_MODE_DIRECT)
        self.assertEqual(invites[0].status, _BIND_STATUS_ACCEPTED)

        sharedName = shareeView.name()

        yield self.commitTransaction(0)

        txn2 = self.theTransactionUnderTest(1)
        shared = yield self.calendarUnderTest(txn=txn2, home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield txn2.notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 0)
        yield self.commitTransaction(1)

        # Remove
        txn2 = self.theTransactionUnderTest(1)
        shared = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        yield shared.deleteShare()
        yield self.commitTransaction(1)

        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        notifyHome = yield self.theTransactionUnderTest(0).notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 0)

    test_direct_sharee.skip = True

    @inlineCallbacks
    def test_sharedNotifierID(self):
        shared_name = yield self.createShare()

        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01")
        self.assertEquals(home.notifierID(), ("CalDAV", "user01",))
        calendar = yield home.calendarWithName("calendar")
        self.assertEquals(calendar.notifierID(), ("CalDAV", "user01/calendar",))
        yield self.commitTransaction(0)

        txn2 = self.theTransactionUnderTest(1)
        home = yield self.homeUnderTest(txn=txn2, name="puser02")
        self.assertEquals(home.notifierID(), ("CalDAV", "puser02",))
        calendar = yield home.calendarWithName(shared_name)
        self.assertEquals(calendar.notifierID(), ("CalDAV", "user01/calendar",))

    @inlineCallbacks
    def test_sharedWithTwo(self):
        shared_name1 = yield self.createShare(shareeGUID="puser02")
        shared_name2 = yield self.createShare(shareeGUID="puser03")

        txn2 = self.theTransactionUnderTest(1)
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser02", name=shared_name1)
        self.assertTrue(otherCal is not None)
        yield self.commitTransaction(1)

        txn2 = self.theTransactionUnderTest(1)
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser03", name=shared_name2)
        self.assertTrue(otherCal is not None)
        yield self.commitTransaction(1)

    @inlineCallbacks
    def test_invite_sharee_failure(self):
        """
        Test invite fails gracefully when the other pod is down.
        """

        # Force store to generate 500 error
        self.patch(self.theStores[1], "_poddingFailure", ValueError)

        # Invite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(calendar.isSharedByOwner())

        yield self.assertFailure(calendar.inviteUIDToShare("puser02", _BIND_MODE_READ, "summary"), FailedCrossPodRequestError)

    @inlineCallbacks
    def test_uninvite_sharee_failure(self):
        """
        Test uninvite fails gracefully when the other pod is down.
        Also test that the sharee bind entry is removed when an invalid share is detected.
        """

        # Invite
        sharedName = yield self.createShare("user01", "puser02", "calendar")

        # Has external sharee bind entry
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(0), name="puser02", status=_HOME_STATUS_EXTERNAL
        )
        calendar = yield home.anyObjectWithShareUID(sharedName)
        self.assertTrue(calendar is not None)
        yield self.commitTransaction(0)

        # Force store to generate 500 error
        self.patch(self.theStores[1], "_poddingFailure", ValueError)

        yield self.removeShare("user01", "puser02", "calendar")

        # Store working again
        self.patch(self.theStores[1], "_poddingFailure", None)

        # No external sharee bind entry
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(0), name="puser02", status=_HOME_STATUS_EXTERNAL
        )
        calendar = yield home.anyObjectWithShareUID(sharedName)
        self.assertTrue(calendar is None)
        yield self.commitTransaction(0)

        # Has external sharer bind entry
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_EXTERNAL
        )
        calendar = yield home.anyObjectWithShareUID("calendar")
        self.assertTrue(calendar is not None)
        yield self.commitTransaction(1)

        # Has sharee bind entry
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="puser02"
        )
        calendar = yield home.anyObjectWithShareUID(sharedName)
        self.assertTrue(calendar is not None)
        yield self.commitTransaction(1)

        # Force clean-up of sharee calendar
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="puser02"
        )
        calendar = yield home.anyObjectWithShareUID(sharedName)
        yield self.assertFailure(calendar.syncTokenRevision(), ExternalShareFailed)
        yield self.commitTransaction(1)

        # External sharer bind entry gone
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_EXTERNAL
        )
        calendar = yield home.anyObjectWithShareUID("calendar")
        self.assertTrue(calendar is None)
        yield self.commitTransaction(1)

        # Sharee bind entry gone
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="puser02"
        )
        calendar = yield home.anyObjectWithShareUID(sharedName)
        self.assertTrue(calendar is None)
        yield self.commitTransaction(1)

    @inlineCallbacks
    def test_reply_sharee_failure(self):
        """
        Test sharee reply fails and cleans up when the share is invalid.
        """

        # Invite
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(0), name="user01", create=True
        )
        calendar = yield home.calendarWithName("calendar")
        yield calendar.inviteUIDToShare(
            "puser02", _BIND_MODE_WRITE, "shared", shareName="shared-calendar"
        )
        yield self.commitTransaction(0)

        # Has external sharee bind entry
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(0), name="puser02", status=_HOME_STATUS_EXTERNAL
        )
        calendar = yield home.anyObjectWithShareUID("shared-calendar")
        self.assertTrue(calendar is not None)
        yield self.commitTransaction(0)

        # Has external sharer bind entry
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_EXTERNAL
        )
        calendar = yield home.anyObjectWithShareUID("calendar")
        self.assertTrue(calendar is not None)
        yield self.commitTransaction(1)

        # Has sharee bind entry
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="puser02"
        )
        calendar = yield home.anyObjectWithShareUID("shared-calendar")
        self.assertTrue(calendar is not None)
        yield self.commitTransaction(1)

        # Force store to generate an error
        self.patch(self.theStores[0], "_poddingError", ExternalShareFailed)

        # ACK: home2 is None
        home2 = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="puser02"
        )
        yield self.assertFailure(home2.acceptShare("shared-calendar"), ExternalShareFailed)
        yield self.commitTransaction(1)

        # External sharer bind entry gone
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_EXTERNAL
        )
        calendar = yield home.anyObjectWithShareUID("calendar")
        self.assertTrue(calendar is None)
        yield self.commitTransaction(1)

        # Sharee bind entry gone
        home = yield self.homeUnderTest(
            txn=self.theTransactionUnderTest(1), name="puser02"
        )
        calendar = yield home.anyObjectWithShareUID("shared-calendar")
        self.assertTrue(calendar is None)
        yield self.commitTransaction(1)

    @inlineCallbacks
    def test_shared_notifications(self):
        shared_name_puser02 = yield self.createShare()
        shared_name_user02 = yield self.createShare(shareeGUID="user02", pod=0)

        map(methodcaller("reset"), self.theNotifiers)

        def _checkNotifications(priority=PushPriority.high):
            self.assertEqual(set(self.theNotifiers[0].history), set([("/CalDAV/example.com/user01/", priority), ("/CalDAV/example.com/user01/calendar/", priority)]))
            self.assertEqual(set(self.theNotifiers[1].history), set([("/CalDAV/example.com/user01/", priority), ("/CalDAV/example.com/user01/calendar/", priority)]))
            map(methodcaller("reset"), self.theNotifiers)

        # Change by owner
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01")
        self.assertEquals(home.notifierID(), ("CalDAV", "user01",))
        calendar = yield home.calendarWithName("calendar")
        yield calendar.createObjectResourceWithName("2.ics", Component.fromString(self.cal2))
        yield self.commitTransaction(0)
        _checkNotifications()

        # Change by sharee on other pod
        txn2 = self.theTransactionUnderTest(1)
        home = yield self.homeUnderTest(txn=txn2, name="puser02")
        self.assertEquals(home.notifierID(), ("CalDAV", "puser02",))
        calendar = yield home.calendarWithName(shared_name_puser02)
        cobj = yield calendar.calendarObjectWithName("2.ics")
        yield cobj.remove()
        yield self.commitTransaction(1)
        _checkNotifications()

        # Change by sharee on same pod
        txn2 = self.theTransactionUnderTest(0)
        home = yield self.homeUnderTest(txn=txn2, name="user02")
        self.assertEquals(home.notifierID(), ("CalDAV", "user02",))
        calendar = yield home.calendarWithName(shared_name_user02)
        yield calendar.createObjectResourceWithName("2_1.ics", Component.fromString(self.cal2))
        yield self.commitTransaction(0)
        _checkNotifications()

        # Different priority for owner change
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01")
        self.assertEquals(home.notifierID(), ("CalDAV", "user01",))
        calendar = yield home.calendarWithName("calendar")
        yield calendar.notifyChanged(category=ChangeCategory.attendeeITIPUpdate)
        yield self.commitTransaction(0)
        _checkNotifications(priority=PushPriority.medium)


class SharingRevisions(BaseSharingTests):
    """
    Test store-based sharing and interaction with revision table.
    """

    @inlineCallbacks
    def test_shareWithRevision(self):
        """
        Verify that bindRevision on calendars and shared calendars has the correct value.
        """
        sharedName = yield self.createShare()

        normalCal = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertEqual(normalCal._bindRevision, 0)

        txn2 = self.theTransactionUnderTest(1)
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertNotEqual(otherCal._bindRevision, 0)

    @inlineCallbacks
    def test_updateShareRevision(self):
        """
        Verify that bindRevision on calendars and shared calendars has the correct value.
        """
        # Invite
        calendar = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        invites = yield calendar.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield calendar.inviteUIDToShare("puser02", _BIND_MODE_READ, "summary")
        newCalName = shareeView.shareUID()
        yield self.commitTransaction(0)

        normalCal = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertEqual(normalCal._bindRevision, 0)
        yield self.commitTransaction(0)

        txn2 = self.theTransactionUnderTest(1)
        otherHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        otherCal = yield otherHome.anyObjectWithShareUID(newCalName)
        self.assertEqual(otherCal._bindRevision, 0)
        yield self.commitTransaction(1)

        txn2 = self.theTransactionUnderTest(1)
        shareeHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        shareeView = yield shareeHome.acceptShare(newCalName)
        sharedName = shareeView.name()
        yield self.commitTransaction(1)

        normalCal = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertEqual(normalCal._bindRevision, 0)

        txn2 = self.theTransactionUnderTest(1)
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertNotEqual(otherCal._bindRevision, 0)

    @inlineCallbacks
    def test_sharedRevisions(self):
        """
        Verify that resourceNamesSinceRevision returns all resources after initial bind and sync.
        """
        sharedName = yield self.createShare()

        normalCal = yield self.calendarUnderTest(txn=self.theTransactionUnderTest(0), home="user01", name="calendar")
        self.assertEqual(normalCal._bindRevision, 0)

        txn2 = self.theTransactionUnderTest(1)
        otherHome = yield self.homeUnderTest(txn=txn2, name="puser02")
        otherCal = yield self.calendarUnderTest(txn=txn2, home="puser02", name=sharedName)
        self.assertNotEqual(otherCal._bindRevision, 0)

        sync_token = yield otherCal.syncToken()
        revision = otherCal.revisionFromToken(sync_token)

        changed, deleted, invalid = yield otherCal.resourceNamesSinceRevision(0)
        self.assertNotEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        changed, deleted, invalid = yield otherCal.resourceNamesSinceRevision(revision)
        self.assertEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        sync_token = yield otherHome.syncToken()
        revision = otherHome.revisionFromToken(sync_token)

        for depth in ("1", "infinity",):
            changed, deleted, invalid = yield otherHome.resourceNamesSinceRevision(revision - 1, depth)
            self.assertEqual(len(changed), 0 if depth == "infinity" else 1)
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 1 if depth == "infinity" else 0)

            changed, deleted, invalid = yield otherHome.resourceNamesSinceRevision(revision, depth)
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 1 if depth == "infinity" else 0)

        yield self.commitTransaction(1)

        yield self.removeShare()

        txn2 = self.theTransactionUnderTest(1)
        otherHome = yield self.homeUnderTest(txn=txn2, name="puser02")

        for depth in ("1", "infinity",):
            changed, deleted, invalid = yield otherHome.resourceNamesSinceRevision(revision, depth)
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 1)
            self.assertEqual(len(invalid), 0)
