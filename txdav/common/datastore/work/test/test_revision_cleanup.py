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
from twext.enterprise.queue import WorkItem
from twext.python.clsprop import classproperty
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from twistedcaldav.config import config
from twistedcaldav.vcard import Component as VCard
from txdav.common.datastore.sql_tables import  schema
from txdav.common.datastore.test.util import buildStore, CommonCommonTests
from txdav.common.datastore.work.revision_cleanup import FindMinValidRevisionWork, RevisionCleanupWork
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

        class FakeWork(WorkItem):
            @classmethod
            def _schedule(cls, txn, seconds):
                pass

        self.patch(FindMinValidRevisionWork, "_schedule", FakeWork._schedule)
        self.patch(RevisionCleanupWork, "_schedule", FakeWork._schedule)
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

    group1Empty = """BEGIN:VCARD
VERSION:3.0
UID:group1
FN:Group 1
N:group1;;;;
X-ADDRESSBOOKSERVER-KIND:group
END:VCARD
"""

    group2Empty = """BEGIN:VCARD
VERSION:3.0
UID:group2
FN:Group 2
N:group2;;;;
X-ADDRESSBOOKSERVER-KIND:group
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


    def test_calendarObjectRevisions(self):
        pass


    def test_notificationObjectRevisions(self):
        pass


    def test_addressbookObjectRevisions(self):
        pass


    @inlineCallbacks
    def test_addressbookMembersRevisions(self):
        """
        Verify that resourceNamesSinceRevision returns all resources after initial bind and sync.
        """

        # get sync token
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        token = yield addressbook.syncToken()

        # generate 3 revisions per member of group1
        group1Object = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group1.vcf", addressbook_name="addressbook", home="user01")
        yield group1Object.setComponent(VCard.fromString(self.group1Empty))
        self.commit()
        group1Object = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group1.vcf", addressbook_name="addressbook", home="user01")
        yield group1Object.setComponent(VCard.fromString(self.group1))
        self.commit()

        # generate 2 revisions per member of group2, and make max revision of group1 members < max revision used
        group2Object = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group2.vcf", addressbook_name="addressbook", home="user01")
        yield group2Object.setComponent(VCard.fromString(self.group2Empty))
        self.commit()

        # Get group1 revisions
        aboMembers = schema.ABO_MEMBERS
        group1Rows = yield Select(
            [aboMembers.GROUP_ID,
             aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
            Where=aboMembers.GROUP_ID == group1Object._resourceID,
        ).on(self.transactionUnderTest())
        self.assertEqual(len(group1Rows), 6)  # 2 members x 3 revisions each

        # Get group2 revisions
        group2Rows = yield Select(
            [aboMembers.GROUP_ID,
             aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
            Where=aboMembers.GROUP_ID == group2Object._resourceID,
        ).on(self.transactionUnderTest())
        self.assertEqual(len(group2Rows), 4)  # 2 members x 2 revisions each

        # Get the minimum valid revision
        cs = schema.CALENDARSERVER
        minValidRevision = int((yield Select(
            [cs.VALUE],
            From=cs,
            Where=(cs.NAME == "MIN-VALID-REVISION")
        ).on(self.transactionUnderTest()))[0][0])
        self.assertEqual(minValidRevision, 1)

        # do FindMinValidRevisionWork
        wp = yield self.transactionUnderTest().enqueue(FindMinValidRevisionWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # Get the minimum valid revision and check it
        cs = schema.CALENDARSERVER
        minValidRevision = int((yield Select(
            [cs.VALUE],
            From=cs,
            Where=(cs.NAME == "MIN-VALID-REVISION")
        ).on(self.transactionUnderTest()))[0][0])
        self.assertEqual(minValidRevision, max([row[3] for row in group1Rows + group2Rows]))

        # old sync token fails
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.failUnlessFailure(addressbook.resourceNamesSinceToken(token), SyncTokenValidException)

        # do RevisionCleanupWork
        wp = yield self.transactionUnderTest().enqueue(RevisionCleanupWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        group1Rows = yield Select(
            [aboMembers.GROUP_ID,
             aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
            Where=aboMembers.GROUP_ID == group1Object._resourceID,
        ).on(self.transactionUnderTest())
        self.assertEqual(len(group1Rows), 2)  # 2 members x 1 revision each
        self.assertTrue(max([row[3] for row in group1Rows]) < minValidRevision) # < min revision but still around

        group2Rows = yield Select(
            [aboMembers.GROUP_ID,
             aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
            Where=aboMembers.GROUP_ID == group2Object._resourceID,
        ).on(self.transactionUnderTest())
        self.assertEqual(len(group2Rows), 0)  # 0 members
