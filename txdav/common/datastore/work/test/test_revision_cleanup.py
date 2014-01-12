##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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



from twext.enterprise.dal.syntax import Select
from twext.python.clsprop import classproperty
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from twistedcaldav.config import config
from twistedcaldav.vcard import Component as VCard
from txdav.common.datastore.sql_tables import  schema, _BIND_MODE_READ
from txdav.common.datastore.test.util import buildStore, CommonCommonTests
from txdav.common.datastore.work.revision_cleanup import FindMinValidRevisionWork
from txdav.common.icommondatastore import SyncTokenValidException
import datetime


class RevisionCleanupTests(CommonCommonTests, TestCase):
    """
    Test store-based address book sharing.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(RevisionCleanupTests, self).setUp()
        self._sqlStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()
        self.patch(config, "SyncTokenLifetimeDays", 0)


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


    def test_CalendarObjectRevisions(self):
        pass


    def test_AddressBookObjectRevisions(self):
        pass


    def test_notificationObjectRevisions(self):
        pass


    @inlineCallbacks
    def test_addressbookMembersRevisions(self):
        """
        Verify that resourceNamesSinceRevision returns all resources after initial bind and sync.
        """

        #normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        groupObject = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group1.vcf", addressbook_name="addressbook", home="user01")
        print("test_addressbookMembersRevisions sharedGroupObject= %s" % (groupObject,))

        # Get revisions
        # get groups where this object was once a member and version info
        aboMembers = schema.ABO_MEMBERS
        groupRows = yield Select(
            [aboMembers.GROUP_ID,
             aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
            Where=aboMembers.GROUP_ID == groupObject._resourceID,
        ).on(self.transactionUnderTest())

        print("test_addressbookMembersRevisions groupRows= %s" % (groupRows,))

        group1Empty = """BEGIN:VCARD
VERSION:3.0
UID:group1
FN:Group 1
N:group1;;;;
X-ADDRESSBOOKSERVER-KIND:group
END:VCARD
"""
        groupEmptyVCard = VCard.fromString(group1Empty.replace("\n", "\r\n"))
        yield groupObject.setComponent(groupEmptyVCard)
        self.commit()

        yield self._createGroupShare(groupname="group1.vcf")

        #normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        groupObject = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group1.vcf", addressbook_name="addressbook", home="user01")
        print("test_addressbookMembersRevisions sharedGroupObject= %s" % (groupObject,))

        # Get revisions
        # get groups where this object was once a member and version info
        aboMembers = schema.ABO_MEMBERS
        groupRows = yield Select(
            [aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
            Where=aboMembers.GROUP_ID == groupObject._resourceID,
        ).on(self.transactionUnderTest())

        print("test_addressbookMembersRevisions groupRows= %s" % (groupRows,))

        group1vCard = VCard.fromString(self.group1.replace("\n", "\r\n"))
        yield groupObject.setComponent(group1vCard)
        self.commit()

        #normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        groupObject = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group1.vcf", addressbook_name="addressbook", home="user01")
        print("test_addressbookMembersRevisions sharedGroupObject= %s" % (groupObject,))

        # Get revisions
        # get groups where this object was once a member and version info
        aboMembers = schema.ABO_MEMBERS
        groupRows = yield Select(
            [aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
            Where=aboMembers.GROUP_ID == groupObject._resourceID,
        ).on(self.transactionUnderTest())

        print("test_addressbookMembersRevisions groupRows= %s" % (groupRows,))

        group1vCard = VCard.fromString(group1Empty.replace("\n", "\r\n"))
        yield groupObject.setComponent(group1vCard)
        self.commit()

        #normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        groupObject = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group1.vcf", addressbook_name="addressbook", home="user01")
        print("test_addressbookMembersRevisions sharedGroupObject= %s" % (groupObject,))

        # Get revisions
        # get groups where this object was once a member and version info
        aboMembers = schema.ABO_MEMBERS
        groupRows = yield Select(
            [aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
            Where=aboMembers.GROUP_ID == groupObject._resourceID,
        ).on(self.transactionUnderTest())

        print("test_addressbookMembersRevisions groupRows= %s" % (groupRows,))

        normalAB = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.assertEqual(normalAB._bindRevision, 0)
        otherAB = yield self.addressbookUnderTest(home="user02", name="user01")
        self.assertNotEqual(otherAB._bindRevision, 0)

        changed, deleted, invalid = yield otherAB.resourceNamesSinceRevision(otherAB._bindRevision)
        print("test_addressbookMembersRevisions changed=%s deleted=%s" % (changed, deleted,))
        self.assertEqual(changed, ["group1.vcf"])
        self.assertEqual(len(deleted), 0)
        self.assertEqual(len(invalid), 0)

        otherHome = yield self.addressbookHomeUnderTest(name="user02")
        for depth, result in (
            ("1", ['user01/', ]
            ),
            ("infinity", ['user01/',
                          'user01/group1.vcf']
             )):
            changed, deleted, invalid = yield otherAB.viewerHome().resourceNamesSinceRevision(otherAB._bindRevision, depth)
            print("test_addressbookMembersRevisions depth=%s, changed=%s deleted=%s" % (depth, changed, deleted,))
            self.assertEqual(set(changed), set(result))
            self.assertEqual(len(deleted), 0)
            self.assertEqual(len(invalid), 0)

        yield self.commit()

        # Get the minimum valid revision
        cs = schema.CALENDARSERVER
        minValidRevision = int((yield Select(
            [cs.VALUE],
            From=cs,
            Where=(cs.NAME == "MIN-VALID-REVISION")
        ).on(self.transactionUnderTest()))[0][0])
        print("test_addressbookMembersRevisions minValidRevision= %s" % (minValidRevision,))
        self.assertEqual(minValidRevision, 1)

        # queue work items
        wp = yield self.transactionUnderTest().enqueue(FindMinValidRevisionWork, notBefore=datetime.datetime.utcnow())

        yield self.commit()

        # Wait for it to complete
        yield wp.whenExecuted()

        # Get the minimum valid revision again
        cs = schema.CALENDARSERVER
        minValidRevision = int((yield Select(
            [cs.VALUE],
            From=cs,
            Where=(cs.NAME == "MIN-VALID-REVISION")
        ).on(self.transactionUnderTest()))[0][0])
        print("test_addressbookMembersRevisions minValidRevision= %s" % (minValidRevision,))
        self.assertNotEqual(minValidRevision, 1)

        otherHome = yield self.addressbookHomeUnderTest(name="user02")
        for depth in ("1", "infinity",):
            self.failUnlessFailure(otherHome.resourceNamesSinceRevision(otherAB._bindRevision, depth), SyncTokenValidException)
