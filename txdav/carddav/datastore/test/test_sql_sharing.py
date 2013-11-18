##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twistedcaldav.vcard import Component as VCard
from twext.python.clsprop import classproperty
from txdav.common.datastore.test.util import CommonCommonTests, buildStore
from txdav.common.datastore.sql_tables import _BIND_MODE_READ, \
    _BIND_STATUS_INVITED, _BIND_MODE_DIRECT, _BIND_STATUS_ACCEPTED


class CalendarSharing(CommonCommonTests, TestCase):
    """
    Test twistedcaldav.scheduyling.implicit with a Request object.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(CalendarSharing, self).setUp()
        self._sqlStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        populateTxn = self.storeUnderTest().newTransaction()
        for homeUID in self.requirements:
            addressbooks = self.requirements[homeUID]
            if addressbooks is not None:
                home = yield populateTxn.addressbookHomeWithUID(homeUID, True)
                addressbook = home.addressbook()

                addressbookObjNames = addressbooks[addressbook.name()]
                if addressbookObjNames is not None:
                    for objectName in addressbookObjNames:
                        objData = addressbookObjNames[objectName]
                        yield addressbook.createAddressBookObjectWithName(
                            objectName, VCard.fromString(objData)
                        )

        yield populateTxn.commit()
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "addressbook": {
            },
        },
        "user02": {
            "addressbook": {
            },
        },
        "user03": {
            "addressbook": {
            },
        },
    }


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlStore


    @inlineCallbacks
    def _createShare(self):
        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        inviteUID = shareeView.shareUID()
        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        shareeView = yield shareeHome.acceptShare(inviteUID)
        sharedName = shareeView.name()
        yield self.commit()

        returnValue(sharedName)


    @inlineCallbacks
    def test_no_shares(self):
        """
        Test that initially there are no shares.
        """

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)


    @inlineCallbacks
    def test_invite_sharee(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].uid, shareeView.shareUID())
        self.assertEqual(invites[0].ownerUID, "user01")
        self.assertEqual(invites[0].shareeUID, "user02")
        self.assertEqual(invites[0].shareeName, shareeView.name())
        self.assertEqual(invites[0].mode, _BIND_MODE_READ)
        self.assertEqual(invites[0].status, _BIND_STATUS_INVITED)
        self.assertEqual(invites[0].summary, "summary")
        inviteUID = shareeView.shareUID()

        self.assertEqual(invites[0].shareeName, "user01")

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID, ])

        yield self.commit()

        # Uninvite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)

        yield addressbook.uninviteUserFromShare("user02")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [])


    @inlineCallbacks
    def test_accept_share(self):
        """
        Test that invite+accept creates shares and notifications.
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        yield self.commit()

        # Re-accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])


    @inlineCallbacks
    def test_decline_share(self):
        """
        Test that invite+accept creates shares and notifications.
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)

        yield self.commit()

        # Decline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        yield self.commit()

        # Redecline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])


    @inlineCallbacks
    def test_accept_decline_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the home.
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        yield self.commit()

        # Decline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])


    @inlineCallbacks
    def test_accept_remove_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the shared collection (removal).
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 1)

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])

        yield self.commit()

        # Delete
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        yield shared.deleteShare()

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user01")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(notifications, [inviteUID + "-reply", ])


    @inlineCallbacks
    def test_direct_sharee(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield addressbook.directShareWithUser("user02")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].uid, shareeView.shareUID())
        self.assertEqual(invites[0].ownerUID, "user01")
        self.assertEqual(invites[0].shareeUID, "user02")
        self.assertEqual(invites[0].shareeName, shareeView.name())
        self.assertEqual(invites[0].mode, _BIND_MODE_DIRECT)
        self.assertEqual(invites[0].status, _BIND_STATUS_ACCEPTED)

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 0)

        yield self.commit()

        # Remove
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        yield shared.deleteShare()

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        notifyHome = yield self.transactionUnderTest().notificationsWithUID("user02")
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(len(notifications), 0)


    @inlineCallbacks
    def test_sharedNotifierID(self):
        shared_name = yield self._createShare()

        home = yield self.addressbookHomeUnderTest(name="user01")
        self.assertEquals(home.notifierID(), ("CardDAV", "user01",))
        addressbook = yield home.addressbookWithName("addressbook")
        self.assertEquals(addressbook.notifierID(), ("CardDAV", "user01/addressbook",))
        yield self.commit()

        home = yield self.addressbookHomeUnderTest(name="user02")
        self.assertEquals(home.notifierID(), ("CardDAV", "user02",))
        addressbook = yield home.addressbookWithName(shared_name)
        self.assertEquals(addressbook.notifierID(), ("CardDAV", "user01/addressbook",))
        yield self.commit()
