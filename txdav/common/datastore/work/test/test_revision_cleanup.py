##
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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
from twext.enterprise.jobqueue import WorkItem
from twext.python.clsprop import classproperty
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from twistedcaldav.config import config
from twistedcaldav.vcard import Component as VCard
from txdav.common.datastore.sql_tables import schema, _BIND_MODE_READ
from txdav.common.datastore.test.util import CommonCommonTests, populateCalendarsFrom
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
        yield self.buildStoreAndDirectory()
        yield self.populate()

        class FakeWork(WorkItem):
            @classmethod
            def _schedule(cls, txn, seconds):
                pass

        self.patch(FindMinValidRevisionWork, "_schedule", FakeWork._schedule)
        self.patch(RevisionCleanupWork, "_schedule", FakeWork._schedule)
        self.patch(config.RevisionCleanup, "SyncTokenLifetimeDays", 0)


    @inlineCallbacks
    def populate(self):
        populateTxn = self.storeUnderTest().newTransaction()
        addressookRequirements = self.requirements["addressbook"]
        for homeUID in addressookRequirements:
            addressbooks = addressookRequirements[homeUID]
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

        calendarRequirements = self.requirements["calendar"]
        yield populateCalendarsFrom(calendarRequirements, self.storeUnderTest())

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
DTSTART:20131122T140000
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:event 2
END:VEVENT
END:VCALENDAR
"""

    cal3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid3
DTSTART:20131122T140000
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:event 3
END:VEVENT
END:VCALENDAR
"""

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
            "addressbook": {
                "user01": {
                    "addressbook": {
                        "card1.vcf": cls.card1,
                        "card2.vcf": cls.card2,
                        "card3.vcf": cls.card3,
                        "group1.vcf": cls.group1,
                        "group2.vcf": cls.group2,
                    },
                },
            }, "calendar": {
                "user01": {
                    "calendar": {
                        "cal1.ics": (cls.cal1, None,),
                        "cal2.ics": (cls.cal2, None,),
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
            }
        }


    @inlineCallbacks
    def _createCalendarShare(self):
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


    @inlineCallbacks
    def test_calendarObjectRevisions(self):
        """
        Verify that all extra calendar object revisions are deleted by FindMinValidRevisionWork and RevisionCleanupWork
        """

        # get sync token
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        token = yield calendar.syncToken()

        #make changes
        cal1Object = yield self.calendarObjectUnderTest(self.transactionUnderTest(), name="cal1.ics", calendar_name="calendar", home="user01")
        yield cal1Object.remove()
        cal2Object = yield self.calendarObjectUnderTest(self.transactionUnderTest(), name="cal2.ics", calendar_name="calendar", home="user01")
        yield cal2Object.remove()

        # Get object revisions
        rev = schema.CALENDAR_OBJECT_REVISIONS
        revisionRows = yield Select(
            [rev.REVISION],
            From=rev,
        ).on(self.transactionUnderTest())
        self.assertNotEqual(len(revisionRows), 0)

        # do FindMinValidRevisionWork
        wp = yield self.transactionUnderTest().enqueue(FindMinValidRevisionWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # Get the minimum valid revision and check it
        minValidRevision = yield self.transactionUnderTest().calendarserverValue("MIN-VALID-REVISION")
        self.assertEqual(int(minValidRevision), max([row[0] for row in revisionRows]))

        # do RevisionCleanupWork
        wp = yield self.transactionUnderTest().enqueue(RevisionCleanupWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # Get group1 object revision
        rev = schema.CALENDAR_OBJECT_REVISIONS
        revisionRows = yield Select(
            [rev.REVISION],
            From=rev,
        ).on(self.transactionUnderTest())
        self.assertEqual(len(revisionRows), 1)  # deleteRevisionsBefore() leaves 1 revision behind

        # old sync token fails
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        self.failUnlessFailure(calendar.resourceNamesSinceToken(token), SyncTokenValidException)


    @inlineCallbacks
    def test_notificationObjectRevisions(self):
        """
        Verify that all extra notification object revisions are deleted by FindMinValidRevisionWork and RevisionCleanupWork
        """

        # get sync token
        home = yield self.homeUnderTest(name="user01")
        token = yield home.syncToken()

        #make notification changes as side effect of sharing
        yield self._createCalendarShare()

        # Get object revisions
        rev = schema.NOTIFICATION_OBJECT_REVISIONS
        revisionRows = yield Select(
            [rev.REVISION],
            From=rev,
        ).on(self.transactionUnderTest())
        self.assertNotEqual(len(revisionRows), 0)

        # do FindMinValidRevisionWork
        wp = yield self.transactionUnderTest().enqueue(FindMinValidRevisionWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # Get the minimum valid revision and check it
        minValidRevision = yield self.transactionUnderTest().calendarserverValue("MIN-VALID-REVISION")
        self.assertEqual(int(minValidRevision), max([row[0] for row in revisionRows]))

        # do RevisionCleanupWork
        wp = yield self.transactionUnderTest().enqueue(RevisionCleanupWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # Get group1 object revision
        rev = schema.NOTIFICATION_OBJECT_REVISIONS
        revisionRows = yield Select(
            [rev.REVISION],
            From=rev,
        ).on(self.transactionUnderTest())
        self.assertEqual(len(revisionRows), 1)  # deleteRevisionsBefore() leaves 1 revision behind

        # old sync token fails
        home = yield self.homeUnderTest(name="user01")
        self.failUnlessFailure(home.resourceNamesSinceToken(token, "1"), SyncTokenValidException)
        self.failUnlessFailure(home.resourceNamesSinceToken(token, "infinity"), SyncTokenValidException)


    @inlineCallbacks
    def test_addressbookObjectRevisions(self):
        """
        Verify that all extra addressbook object revisions are deleted by FindMinValidRevisionWork and RevisionCleanupWork
        """

        # get sync token
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        token = yield addressbook.syncToken()

        #make changes
        card1Object = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="card1.vcf", addressbook_name="addressbook", home="user01")
        yield card1Object.remove()
        card2Object = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="card2.vcf", addressbook_name="addressbook", home="user01")
        yield card2Object.remove()

        # Get object revisions
        rev = schema.ADDRESSBOOK_OBJECT_REVISIONS
        revisionRows = yield Select(
            [rev.REVISION],
            From=rev,
        ).on(self.transactionUnderTest())
        self.assertNotEqual(len(revisionRows), 0)

        # do FindMinValidRevisionWork
        wp = yield self.transactionUnderTest().enqueue(FindMinValidRevisionWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # Get the minimum valid revision and check it
        minValidRevision = yield self.transactionUnderTest().calendarserverValue("MIN-VALID-REVISION")
        self.assertEqual(int(minValidRevision), max([row[0] for row in revisionRows]))

        # do RevisionCleanupWork
        wp = yield self.transactionUnderTest().enqueue(RevisionCleanupWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # Get group1 object revision
        rev = schema.ADDRESSBOOK_OBJECT_REVISIONS
        revisionRows = yield Select(
            [rev.REVISION],
            From=rev,
        ).on(self.transactionUnderTest())
        self.assertEqual(len(revisionRows), 1)  # deleteRevisionsBefore() leaves 1 revision behind

        # old sync token fails
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.failUnlessFailure(addressbook.resourceNamesSinceToken(token), SyncTokenValidException)


    @inlineCallbacks
    def test_addressbookMembersRevisions(self):
        """
        Verify that all extra members revisions are deleted by FindMinValidRevisionWork and RevisionCleanupWork
        """

        # get sync token
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        token = yield addressbook.syncToken()

        # generate 3 revisions per member of group1
        group1Object = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group1.vcf", addressbook_name="addressbook", home="user01")
        yield group1Object.setComponent(VCard.fromString(self.group1Empty))
        yield self.commit()
        group1Object = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group1.vcf", addressbook_name="addressbook", home="user01")
        yield group1Object.setComponent(VCard.fromString(self.group1))
        yield self.commit()

        # generate 2 revisions per member of group2, and make max revision of group1 members < max valid revision
        group2Object = yield self.addressbookObjectUnderTest(self.transactionUnderTest(), name="group2.vcf", addressbook_name="addressbook", home="user01")
        yield group2Object.setComponent(VCard.fromString(self.group2Empty))
        yield self.commit()

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

        # do FindMinValidRevisionWork
        wp = yield self.transactionUnderTest().enqueue(FindMinValidRevisionWork, notBefore=datetime.datetime.utcnow())
        yield self.commit()
        yield wp.whenExecuted()

        # Get the minimum valid revision and check it
        minValidRevision = yield self.transactionUnderTest().calendarserverValue("MIN-VALID-REVISION")
        self.assertEqual(int(minValidRevision), max([row[3] for row in group1Rows + group2Rows]))

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

        # old sync token fails
        addressbook = yield self.addressbookUnderTest(home="user01", name="addressbook")
        self.failUnlessFailure(addressbook.resourceNamesSinceToken(token), SyncTokenValidException)
