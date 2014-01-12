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


from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from twisted.trial.unittest import TestCase

from twistedcaldav.vcard import Component as VCard, Component
from twext.python.clsprop import classproperty
from txdav.common.datastore.test.util import CommonCommonTests, buildStore
from txdav.common.datastore.sql_tables import _BIND_MODE_READ, \
    _BIND_STATUS_INVITED, _BIND_MODE_DIRECT, _BIND_STATUS_ACCEPTED, \
    _BIND_MODE_WRITE



class BaseSharingTests(CommonCommonTests, TestCase):
    """
    Test store-based address book sharing.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(BaseSharingTests, self).setUp()
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

    # Data to populate
    card1 = """BEGIN:VCARD
VERSION:3.0
UID:card1
FN:Card 1
N:card1;;;;
END:VCARD
"""

    card2 = """BEGIN:VCARD
VERSION:3.0
UID:card2
FN:Card 2
N:card2;;;;
END:VCARD
"""

    card3 = """BEGIN:VCARD
VERSION:3.0
UID:card3
FN:Card 3
N:card3;;;;
END:VCARD
"""

    group1 = """BEGIN:VCARD
VERSION:3.0
UID:group1
FN:Group 1
N:group1;;;;
X-ADDRESSBOOKSERVER-KIND:group
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:card1
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:card2
END:VCARD
"""

    group2 = """BEGIN:VCARD
VERSION:3.0
UID:group2
FN:Group 2
N:group2;;;;
X-ADDRESSBOOKSERVER-KIND:group
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:card1
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:card3
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:foreign
END:VCARD
"""


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "addressbook": {
                "card1.vcf": cls.card1,
                "card2.vcf": cls.card2,
                "card3.vcf": cls.card3,
                "group1.vcf": cls.group1,
                "group2.vcf": cls.group2,
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

    fully_shared_children = ["addressbook.vcf", "group1.vcf", "group2.vcf", "card1.vcf", "card2.vcf", "card3.vcf", ]
    all_children = ["group1.vcf", "group2.vcf", "card1.vcf", "card2.vcf", "card3.vcf", ]
    group1_children = ["group1.vcf", "card1.vcf", "card2.vcf", ]
    group2_children = ["group2.vcf", "card1.vcf", "card3.vcf", ]


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlStore


    @inlineCallbacks
    def _createShare(self, mode=_BIND_MODE_READ):
        inviteUID = yield self._inviteShare(mode)
        sharedName = yield self._acceptShare(inviteUID)
        returnValue(sharedName)


    @inlineCallbacks
    def _inviteShare(self, mode=_BIND_MODE_READ):
        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield addressbook.inviteUserToShare("user02", mode, "summary")
        inviteUID = shareeView.shareUID()
        yield self.commit()

        returnValue(inviteUID)


    @inlineCallbacks
    def _acceptShare(self, inviteUID):
        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        shareeView = yield shareeHome.acceptShare(inviteUID)
        sharedName = shareeView.name()
        yield self.commit()

        returnValue(sharedName)


    @inlineCallbacks
    def _createGroupShare(self, groupname="group1.vcf", mode=_BIND_MODE_READ):
        inviteUID = yield self._inviteGroupShare(groupname, mode)
        sharedName = yield self._acceptGroupShare(inviteUID)
        returnValue(sharedName)


    @inlineCallbacks
    def _inviteGroupShare(self, groupname="group1.vcf", mode=_BIND_MODE_READ):
        # Invite
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name=groupname)
        shareeView = yield group.inviteUserToShare("user02", mode, "summary")
        inviteUID = shareeView.shareUID()
        yield self.commit()

        returnValue(inviteUID)


    @inlineCallbacks
    def _acceptGroupShare(self, inviteUID):
        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)
        yield self.commit()

        returnValue(inviteUID)


    @inlineCallbacks
    def _check_notifications(self, home, items):
        notifyHome = yield self.transactionUnderTest().notificationsWithUID(home)
        notifications = yield notifyHome.listNotificationObjects()
        self.assertEqual(set(notifications), set(items))


    @inlineCallbacks
    def _check_addressbook(self, home, addressbook_name, child_names):
        sharedParent = yield self.addressbookUnderTest(home=home, name=addressbook_name)
        self.assertTrue(sharedParent is not None, msg="Missing parent:{}".format(addressbook_name))

        children = yield sharedParent.listAddressBookObjects()
        self.assertEqual(set(children), set(child_names))

        number = yield sharedParent.countAddressBookObjects()
        self.assertEqual(number, len(child_names))

        for child in child_names:
            shared = yield self.addressbookObjectUnderTest(home=home, addressbook_name=addressbook_name, name=child)
            self.assertTrue(shared is not None, msg="Missing child:{}".format(child))


    @inlineCallbacks
    def _check_read_only(self, home, addressbook_name, child_names):
        for child in child_names:
            shared = yield self.addressbookObjectUnderTest(home=home, addressbook_name=addressbook_name, name=child)
            rw_mode = yield shared.readWriteAccess()
            self.assertFalse(rw_mode)


    @inlineCallbacks
    def _check_read_write(self, home, addressbook_name, child_names):
        for child in child_names:
            shared = yield self.addressbookObjectUnderTest(home=home, addressbook_name=addressbook_name, name=child)
            rw_mode = yield shared.readWriteAccess()
            self.assertTrue(rw_mode, msg="Wrong mode: {}".format(child))



class AddressBookSharing(BaseSharingTests):
    """
    Test store-based address book sharing.
    """
    @inlineCallbacks
    def test_no_shares(self):
        """
        Test that initially there are no shares.
        """

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(addressbook.isShared())


    @inlineCallbacks
    def test_invite_sharee(self):
        """
        Test invite/uninvite creates/removes shares and notifications.
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(addressbook.isShared())

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].uid, shareeView.shareUID())
        self.assertEqual(invites[0].ownerUID, "user01")
        self.assertEqual(invites[0].shareeUID, "user02")
        self.assertEqual(invites[0].mode, _BIND_MODE_READ)
        self.assertEqual(invites[0].status, _BIND_STATUS_INVITED)
        self.assertEqual(invites[0].summary, "summary")
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        yield self._check_notifications("user02", [inviteUID, ])

        self.assertTrue(addressbook.isShared())

        yield self.commit()

        # Uninvite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertTrue(addressbook.isShared())

        yield addressbook.uninviteUserFromShare("user02")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        yield self._check_notifications("user02", [])

        self.assertTrue(addressbook.isShared())

        yield self.commit()

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertFalse(addressbook.isShared())


    @inlineCallbacks
    def test_accept_share(self):
        """
        Test that invite+accept creates shares and notifications.
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(addressbook.isShared())

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        yield self._check_notifications("user02", [inviteUID, ])

        self.assertTrue(addressbook.isShared())

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertTrue(addressbook.isShared())

        yield self.commit()

        # Re-accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertTrue(addressbook.isShared())


    @inlineCallbacks
    def test_decline_share(self):
        """
        Test that invite+decline does not create shares but does create notifications.
        """

        # Invite
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(addressbook.isShared())

        shareeView = yield addressbook.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        yield self._check_notifications("user02", [inviteUID, ])

        self.assertTrue(addressbook.isShared())

        yield self.commit()

        # Decline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertTrue(addressbook.isShared())

        yield self.commit()

        # Redecline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertTrue(addressbook.isShared())


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

        yield self._check_notifications("user02", [inviteUID, ])

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        yield self.commit()

        # Decline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        yield self._check_notifications("user01", [inviteUID + "-reply", ])


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

        yield self._check_notifications("user02", [inviteUID, ])

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        yield self.commit()

        # Delete
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        yield shared.deleteShare()

        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is None)

        yield self._check_notifications("user01", [inviteUID + "-reply", ])


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
        self.assertEqual(invites[0].mode, _BIND_MODE_DIRECT)
        self.assertEqual(invites[0].status, _BIND_STATUS_ACCEPTED)

        sharedName = shareeView.name()
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        self.assertTrue(shared is not None)

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_notifications("user02", [])

        yield self.commit()

        # Remove
        shared = yield self.addressbookUnderTest(home="user02", name=sharedName)
        yield shared.deleteShare()

        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        invites = yield addressbook.sharingInvites()
        self.assertEqual(len(invites), 0)

        yield self._check_notifications("user02", [])


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



class GroupSharing(BaseSharingTests):
    """
    Test store-based group book sharing.
    """

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
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(group.isShared())

        shareeView = yield group.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].uid, shareeView.shareUID())
        self.assertEqual(invites[0].ownerUID, "user01")
        self.assertEqual(invites[0].shareeUID, "user02")
        self.assertEqual(invites[0].mode, _BIND_MODE_READ)
        self.assertEqual(invites[0].status, _BIND_STATUS_INVITED)
        self.assertEqual(invites[0].summary, "summary")
        inviteUID = shareeView.shareUID()

        self.assertTrue(group.isShared())

        yield self.commit()

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user02", [inviteUID, ])

        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        self.assertTrue(group.isShared())

        yield self.commit()

        # Uninvite
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 1)
        self.assertTrue(group.isShared())

        yield group.uninviteUserFromShare("user02")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertTrue(group.isShared())

        yield self._check_notifications("user02", [])

        yield self.commit()

        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        self.assertFalse(group.isShared())


    @inlineCallbacks
    def test_accept_share(self):
        """
        Test that invite+accept creates shares and notifications.
        """

        # Invite
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(group.isShared())

        shareeView = yield group.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user02", [inviteUID, ])

        self.assertTrue(group.isShared())

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        yield self._check_addressbook("user02", "user01", self.group1_children)
        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        self.assertTrue(group.isShared())

        yield self.commit()

        # Re-accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        yield self._check_addressbook("user02", "user01", self.group1_children)
        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        self.assertTrue(group.isShared())


    @inlineCallbacks
    def test_decline_share(self):
        """
        Test that invite+decline does not create shares but does create notifications.
        """

        # Invite
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(group.isShared())

        shareeView = yield group.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user02", [inviteUID, ])

        self.assertTrue(group.isShared())

        yield self.commit()

        # Decline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        self.assertTrue(group.isShared())

        yield self.commit()

        # Re-decline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        self.assertTrue(group.isShared())


    @inlineCallbacks
    def test_accept_decline_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the home.
        """

        # Invite
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 0)
        self.assertFalse(group.isShared())

        shareeView = yield group.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user02", [inviteUID, ])

        self.assertTrue(group.isShared())

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        yield self._check_addressbook("user02", "user01", self.group1_children)
        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        self.assertTrue(group.isShared())

        yield self.commit()

        # Decline
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID)

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        self.assertTrue(group.isShared())


    @inlineCallbacks
    def test_accept_remove_share(self):
        """
        Test that invite+accept/decline creates/removes shares and notifications.
        Decline via the shared collection (removal).
        """

        # Invite
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 0)

        shareeView = yield group.inviteUserToShare("user02", _BIND_MODE_READ, "summary")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 1)
        inviteUID = shareeView.shareUID()

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user02", [inviteUID, ])

        yield self.commit()

        # Accept
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.acceptShare(inviteUID)

        yield self._check_addressbook("user02", "user01", self.group1_children)
        yield self._check_notifications("user01", [inviteUID + "-reply", ])

        yield self.commit()

        # Delete
        group = yield self.addressbookObjectUnderTest(home="user02", addressbook_name="user01", name="group1.vcf")
        yield group.deleteShare()

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)

        yield self._check_notifications("user01", [inviteUID + "-reply", ])


    @inlineCallbacks
    def test_accept_two_groups(self):
        """
        Test that accept of two groups works.
        """

        # Two shares
        inviteUID1 = yield self._createGroupShare(groupname="group1.vcf")
        inviteUID2 = yield self._createGroupShare(groupname="group2.vcf")

        yield self._check_addressbook("user02", "user01", self.all_children)
        yield self._check_notifications("user01", [inviteUID1 + "-reply", inviteUID2 + "-reply", ])


    @inlineCallbacks
    def test_accept_uninvite_two_groups(self):
        """
        Test that accept of two groups works, then uninvite each one.
        """

        # Two shares
        inviteUID1 = yield self._createGroupShare(groupname="group1.vcf")
        inviteUID2 = yield self._createGroupShare(groupname="group2.vcf")

        yield self._check_addressbook("user02", "user01", self.all_children)
        yield self._check_notifications("user01", [inviteUID1 + "-reply", inviteUID2 + "-reply", ])

        yield self.commit()

        # Uninvite one
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        yield group.uninviteUserFromShare("user02")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 0)

        yield self._check_addressbook("user02", "user01", self.group2_children)

        shared = yield self.addressbookObjectUnderTest(home="user02", addressbook_name="user01", name="group1.vcf")
        self.assertTrue(shared is None)
        shared = yield self.addressbookObjectUnderTest(home="user02", addressbook_name="user01", name="card2.vcf")
        self.assertTrue(shared is None)

        yield self.commit()

        # Uninvite other
        group = yield self.addressbookObjectUnderTest(home="user02", addressbook_name="user01", name="group2.vcf")
        yield group.uninviteUserFromShare("user02")
        invites = yield group.sharingInvites()
        self.assertEqual(len(invites), 0)

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)


    @inlineCallbacks
    def test_accept_decline_two_groups(self):
        """
        Test that accept of two groups works, then decline each one.
        """

        # Two shares
        inviteUID1 = yield self._createGroupShare(groupname="group1.vcf")
        inviteUID2 = yield self._createGroupShare(groupname="group2.vcf")

        yield self._check_addressbook("user02", "user01", self.all_children)
        yield self._check_notifications("user01", [inviteUID1 + "-reply", inviteUID2 + "-reply", ])

        yield self.commit()

        # Decline one
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID1)

        yield self._check_addressbook("user02", "user01", self.group2_children)

        shared = yield self.addressbookObjectUnderTest(home="user02", addressbook_name="user01", name="group1.vcf")
        self.assertTrue(shared is None)
        shared = yield self.addressbookObjectUnderTest(home="user02", addressbook_name="user01", name="card2.vcf")
        self.assertTrue(shared is None)

        yield self.commit()

        # Decline other
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID2)

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)


    @inlineCallbacks
    def test_accept_two_groups_different_access(self):
        """
        Test that accept of two groups works, then uninvite each one.
        """

        # Two shares
        inviteUID1 = yield self._createGroupShare(groupname="group1.vcf")
        inviteUID2 = yield self._createGroupShare(groupname="group2.vcf", mode=_BIND_MODE_WRITE)

        yield self._check_addressbook("user02", "user01", self.all_children)
        yield self._check_notifications("user01", [inviteUID1 + "-reply", inviteUID2 + "-reply", ])

        # Read only for all, write for group2's items
        yield self._check_read_only("user02", "user01", ["group1.vcf", "card2.vcf", ])
        yield self._check_read_write("user02", "user01", ["group2.vcf", "card1.vcf", "card3.vcf", ])

        yield self.commit()

        # Decline one
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID2)

        yield self._check_addressbook("user02", "user01", self.group1_children)

        yield self._check_read_only("user02", "user01", ["group1.vcf", "card1.vcf", "card2.vcf", ])

        shared = yield self.addressbookObjectUnderTest(home="user02", addressbook_name="user01", name="group2.vcf")
        self.assertTrue(shared is None)
        shared = yield self.addressbookObjectUnderTest(home="user02", addressbook_name="user01", name="card3.vcf")
        self.assertTrue(shared is None)

        yield self.commit()

        # Decline other
        shareeHome = yield self.addressbookHomeUnderTest(name="user02")
        yield shareeHome.declineShare(inviteUID1)

        sharedParent = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertTrue(sharedParent is None)



class MixedSharing(BaseSharingTests):
    """
    Test store-based combined address book and group book sharing.
    """

    @inlineCallbacks
    def test_addressbook_ro_then_groups(self):

        # Share address book read-only
        shareeName = yield self._createShare()
        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", self.all_children)
        yield self._check_read_write("user02", "user01", [])
        yield self._check_notifications("user02", [shareeName, ])

        # Add group1 read-write
        inviteUID1 = yield self._createGroupShare(groupname="group1.vcf", mode=_BIND_MODE_WRITE)

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", ["group2.vcf", "card3.vcf", ])
        yield self._check_read_write("user02", "user01", ["group1.vcf", "card1.vcf", "card2.vcf", ])
        yield self._check_notifications("user02", [shareeName, inviteUID1, ])

        # Add group2 read-write
        inviteUID2 = yield self._createGroupShare(groupname="group2.vcf", mode=_BIND_MODE_WRITE)

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", [])
        yield self._check_read_write("user02", "user01", self.all_children)
        yield self._check_notifications("user02", [shareeName, inviteUID1, inviteUID2])

        # Uninvite group1
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        yield group.uninviteUserFromShare("user02")

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", ["group1.vcf", "card2.vcf", ])
        yield self._check_read_write("user02", "user01", ["group2.vcf", "card1.vcf", "card3.vcf", ])

        # Uninvite group2
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group2.vcf")
        yield group.uninviteUserFromShare("user02")

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", self.all_children)
        yield self._check_read_write("user02", "user01", [])


    @inlineCallbacks
    def test_addressbook_ro_then_group_no_accept(self):

        # Share address book read-only
        shareeName = yield self._createShare()
        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", self.all_children)
        yield self._check_read_write("user02", "user01", [])
        yield self._check_notifications("user02", [shareeName, ])

        # Add group1 read-write - but do not accept
        group = yield self.addressbookObjectUnderTest(home="user01", addressbook_name="addressbook", name="group1.vcf")
        invited = yield group.inviteUserToShare("user02", _BIND_MODE_WRITE, "summary")
        yield self._check_notifications("user02", [shareeName, invited.shareUID(), ])

        yield self._check_addressbook("user02", "user01", self.fully_shared_children)
        yield self._check_read_only("user02", "user01", self.all_children)
        yield self._check_read_write("user02", "user01", [])



class SharingRevisions(BaseSharingTests):
    """
    Test store-based sharing and interaction with revision table.
    """

    @inlineCallbacks
    def test_shareWithRevision(self):
        """
        Verify that bindRevision on addressbooks and shared addressbooks has the correct value.
        """
        yield self._createShare()

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherAB = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertNotEqual(otherAB._bindRevision, 0)


    @inlineCallbacks
    def test_shareGroupWithRevision(self):
        """
        Verify that bindRevision on addressbooks and shared groups has the correct value.
        """

        yield self._createGroupShare(groupname="group1.vcf")

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherAB = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertNotEqual(otherAB._bindRevision, 0)


    @inlineCallbacks
    def test_updateShareRevision(self):
        """
        Verify that bindRevision on addressbooks and shared addressbooks has the correct value.
        """
        newABShareUID = yield self._inviteShare()

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.addressbookHomeUnderTest(name="user02")
        otherAB = yield otherHome.anyObjectWithShareUID("user01")
        self.assertEqual(otherAB._bindRevision, 0)
        yield self.commit()

        yield self._acceptShare(newABShareUID)

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherAB = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertNotEqual(otherAB._bindRevision, 0)


    @inlineCallbacks
    def test_updateSharedGroupRevision(self):
        """
        Verify that bindRevision on addressbooks and shared addressbooks has the correct value.
        """
        newGroupShareUID = yield self._inviteGroupShare(groupname="group1.vcf")

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.addressbookHomeUnderTest(name="user02")
        otherAB = yield otherHome.anyObjectWithShareUID("user01")
        self.assertEqual(otherAB._bindRevision, 0)
        yield self.commit()

        yield self._acceptGroupShare(newGroupShareUID)

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherAB = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertNotEqual(otherAB._bindRevision, 0)


    @inlineCallbacks
    def test_sharedRevisions(self):
        """
        Verify that resourceNamesSinceRevision returns all resources after initial bind and sync.
        """

        yield self._createShare()

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherAB = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertNotEqual(otherAB._bindRevision, 0)

        changed, deleted, invalid = yield otherAB.resourceNamesSinceRevision(0)
        self.assertNotEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        changed, deleted, invalid = yield otherAB.resourceNamesSinceRevision(otherAB._bindRevision)
        self.assertEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        otherHome = yield self.addressbookHomeUnderTest(name="user02")
        for depth in ("1", "infinity",):
            changed, deleted, invalid = yield otherHome.resourceNamesSinceRevision(0, depth)
            self.assertNotEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 0)

            changed, deleted, invalid = yield otherHome.resourceNamesSinceRevision(otherAB._bindRevision, depth)
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 0)


    @inlineCallbacks
    def test_sharedGroupRevisions(self):
        """
        Verify that resourceNamesSinceRevision returns all resources after initial bind and sync.
        """

        yield self._createGroupShare("group1.vcf")

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherAB = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertNotEqual(otherAB._bindRevision, 0)

        changed, deleted, invalid = yield otherAB.resourceNamesSinceRevision(0)
        self.assertEqual(set(changed), set(['card1.vcf', 'card2.vcf', 'group1.vcf']))
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        changed, deleted, invalid = yield otherAB.resourceNamesSinceRevision(otherAB._bindRevision)
        self.assertEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        for depth, result in (
            ("1", ['addressbook/',
                   'user01/', ]
            ),
            ("infinity", ['addressbook/',
                             'user01/',
                             'user01/card1.vcf',
                             'user01/card2.vcf',
                             'user01/group1.vcf']
             )):
            changed, deleted, invalid = yield otherAB.viewerHome().resourceNamesSinceRevision(0, depth)
            self.assertEqual(set(changed), set(result))
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 0)

            changed, deleted, invalid = yield otherAB.viewerHome().resourceNamesSinceRevision(otherAB._bindRevision, depth)
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 0)


    @inlineCallbacks
    def test_addressbookRevisionChangeConcurrency(self):
        """
        Test that two concurrent attempts to add resources in two separate
        calendar homes does not deadlock on the revision table update.
        """

        # Create first events in different addressbook homes
        txn1 = self._sqlStore.newTransaction()
        txn2 = self._sqlStore.newTransaction()

        addressbook_uid1_in_txn1 = yield self.addressbookUnderTest(txn1, "addressbook", "user01")
        addressbook_uid2_in_txn2 = yield self.addressbookUnderTest(txn2, "addressbook", "user02")

        data = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:data%(ctr)s
FN:Data %(ctr)s
N:Sub Group;;;;
REV:20120503T194243Z
END:VCARD

"""

        component = Component.fromString(data % {"ctr": 1})
        yield addressbook_uid1_in_txn1.createAddressBookObjectWithName("data1.ics", component)

        component = Component.fromString(data % {"ctr": 2})
        yield addressbook_uid2_in_txn2.createAddressBookObjectWithName("data2.ics", component)

        # Setup deferreds to run concurrently and create second events in the calendar homes
        # previously used by the other transaction - this could create the deadlock.
        @inlineCallbacks
        def _defer_uid3():
            addressbook_uid1_in_txn2 = yield self.addressbookUnderTest(txn2, "addressbook", "user01")
            component = Component.fromString(data % {"ctr": 3})
            yield addressbook_uid1_in_txn2.createAddressBookObjectWithName("data3.ics", component)
            yield txn2.commit()
        d1 = _defer_uid3()

        @inlineCallbacks
        def _defer_uid4():
            addressbook_uid2_in_txn1 = yield self.addressbookUnderTest(txn1, "addressbook", "user02")
            component = Component.fromString(data % {"ctr": 4})
            yield addressbook_uid2_in_txn1.createAddressBookObjectWithName("data4.ics", component)
            yield txn1.commit()
        d2 = _defer_uid4()

        # Now do the concurrent provision attempt
        yield DeferredList([d1, d2])

        # Verify we did not have a deadlock and all resources have been created.
        vcarddata1 = yield self.addressbookObjectUnderTest(name="data1.ics", addressbook_name="addressbook", home="user01")
        vcarddata2 = yield self.addressbookObjectUnderTest(name="data2.ics", addressbook_name="addressbook", home="user02")
        vcarddata3 = yield self.addressbookObjectUnderTest(name="data3.ics", addressbook_name="addressbook", home="user01")
        vcarddata4 = yield self.addressbookObjectUnderTest(name="data4.ics", addressbook_name="addressbook", home="user02")
        self.assertNotEqual(vcarddata1, None)
        self.assertNotEqual(vcarddata2, None)
        self.assertNotEqual(vcarddata3, None)
        self.assertNotEqual(vcarddata4, None)
