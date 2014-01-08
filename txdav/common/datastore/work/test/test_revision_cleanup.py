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
import datetime


class AddressBookSharedGroupRevisionCleanupTests(CommonCommonTests, TestCase):
    """
    Test store-based address book sharing.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(AddressBookSharedGroupRevisionCleanupTests, self).setUp()
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

        changed, deleted = yield otherAB.resourceNamesSinceRevision(0)
        self.assertNotEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)

        changed, deleted = yield otherAB.resourceNamesSinceRevision(otherAB._bindRevision)
        self.assertEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)

        # TODO:  Change the groups

        otherHome = yield self.addressbookHomeUnderTest(name="user02")
        for depth in ("1", "infinity",):
            changed, deleted = yield otherHome.resourceNamesSinceRevision(0, depth)
            self.assertNotEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)

            changed, deleted = yield otherHome.resourceNamesSinceRevision(otherAB._bindRevision, depth)
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)

        # Get the minimum valid revision
        cs = schema.CALENDARSERVER
        minValidRevision = int((yield Select(
            [cs.VALUE],
            From=cs,
            Where=(cs.NAME == "MIN-VALID-REVISION")
        ).on(self.transactionUnderTest()))[0][0])
        self.assertEqual(minValidRevision, 1)

        # queue work items
        work = yield self.transactionUnderTest().enqueue(FindMinValidRevisionWork, notBefore=datetime.datetime.utcnow())

        yield self.abort()

        # Wait for it to complete
        yield work.whenExecuted()

        # Get the minimum valid revision again
        cs = schema.CALENDARSERVER
        minValidRevision = int((yield Select(
            [cs.VALUE],
            From=cs,
            Where=(cs.NAME == "MIN-VALID-REVISION")
        ).on(self.transactionUnderTest()))[0][0])
        print("test_sharedRevisions minValidRevision=%s" % (minValidRevision,))
        self.assertNotEqual(minValidRevision, 1)


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

        changed, deleted = yield otherAB.resourceNamesSinceRevision(0)
        self.assertEqual(set(changed), set(['card1.vcf', 'card2.vcf', 'group1.vcf']))
        self.assertEqual(len(deleted), 0)

        changed, deleted = yield otherAB.resourceNamesSinceRevision(otherAB._bindRevision)
        self.assertEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)

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
            changed, deleted = yield otherAB.viewerHome().resourceNamesSinceRevision(0, depth)
            self.assertEqual(set(changed), set(result))
            self.assertEqual(len(deleted), 0)

            changed, deleted = yield otherAB.viewerHome().resourceNamesSinceRevision(otherAB._bindRevision, depth)
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)


'''
class CalendarObjectSplitting(CommonCommonTests, unittest.TestCase):
    """
    CalendarObject splitting tests
    """

    @inlineCallbacks
    def setUp(self):
        yield super(CalendarObjectSplitting, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)

        # Make sure homes are provisioned
        txn = self.transactionUnderTest()
        for ctr in range(1, 5):
            home_uid = yield txn.homeWithUID(ECALENDARTYPE, "user%02d" % (ctr,), create=True)
            self.assertNotEqual(home_uid, None)
        yield self.commit()

        self.subs = {}

        self.patch(config, "SyncTokenLifetimeDays", 0)


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def test_calendarObjectSplit_external(self):
        """
        Test that splitting of calendar objects works.
        """
        self.patch(config.Scheduling.Options.Splitting, "Enabled", True)
        self.patch(config.Scheduling.Options.Splitting, "Size", 1024)
        self.patch(config.Scheduling.Options.Splitting, "PastDays", 14)
        self.patch(config.Scheduling.Options.Splitting, "Delay", 2)

        # Create one event that will split
        calendar = yield self.calendarUnderTest(name="calendar", home="user01")

        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:%(now_back30)s
DURATION:PT1H
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER:mailto:user01@example.com
RRULE:FREQ=DAILY
SUMMARY:1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:%(now_back25)s
DTSTART:%(now_back25)s
DURATION:PT1H
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER:mailto:user01@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:%(now_back24)s
DTSTART:%(now_back24)s
DURATION:PT1H
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
DTSTAMP:20051222T210507Z
ORGANIZER:mailto:user01@example.com
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:%(now_fwd10)s
DTSTART:%(now_fwd10)s
DURATION:PT1H
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user01@example.com
ATTENDEE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
"""

        data_future = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:%(now_back14)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:uuid:user02
ATTENDEE;RSVP=TRUE;SCHEDULE-STATUS=3.7:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
RRULE:FREQ=DAILY
SEQUENCE:1
SUMMARY:1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:%(now_fwd10)s
DTSTART:%(now_fwd10)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;RSVP=TRUE;SCHEDULE-STATUS=3.7:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
SEQUENCE:1
END:VEVENT
END:VCALENDAR
"""

        data_past = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:%(relID)s
DTSTART:%(now_back30)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:uuid:user02
ATTENDEE;RSVP=TRUE;SCHEDULE-STATUS=3.7:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
RRULE:FREQ=DAILY;UNTIL=%(now_back14_1)s
SEQUENCE:1
SUMMARY:1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
END:VEVENT
BEGIN:VEVENT
UID:%(relID)s
RECURRENCE-ID:%(now_back25)s
DTSTART:%(now_back25)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:uuid:user02
ATTENDEE;RSVP=TRUE;SCHEDULE-STATUS=3.7:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:%(relID)s
RECURRENCE-ID:%(now_back24)s
DTSTART:%(now_back24)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:uuid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
SEQUENCE:1
END:VEVENT
END:VCALENDAR
"""

        data_future2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:%(now_back14)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:uuid:user02
ATTENDEE;RSVP=TRUE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
EXDATE:%(now_fwd10)s
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
RRULE:FREQ=DAILY
SEQUENCE:1
SUMMARY:1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:12345-67890
X-CALENDARSERVER-PERUSER-UID:user02
BEGIN:X-CALENDARSERVER-PERINSTANCE
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
"""

        data_past2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:%(relID)s
DTSTART:%(now_back30)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:uuid:user02
ATTENDEE;RSVP=TRUE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
RRULE:FREQ=DAILY;UNTIL=%(now_back14_1)s
SEQUENCE:1
SUMMARY:1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
END:VEVENT
BEGIN:VEVENT
UID:%(relID)s
RECURRENCE-ID:%(now_back25)s
DTSTART:%(now_back25)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:uuid:user02
ATTENDEE;RSVP=TRUE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
SEQUENCE:1
END:VEVENT
BEGIN:VEVENT
UID:%(relID)s
RECURRENCE-ID:%(now_back24)s
DTSTART:%(now_back24)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:uuid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
SEQUENCE:1
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
UID:%(relID)s
X-CALENDARSERVER-PERUSER-UID:user02
BEGIN:X-CALENDARSERVER-PERINSTANCE
TRANSP:TRANSPARENT
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
"""

        data_inbox2 = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:%(now_back14)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:uuid:user02
ATTENDEE;RSVP=TRUE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
EXDATE:%(now_fwd10)s
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
RRULE:FREQ=DAILY
SEQUENCE:1
SUMMARY:1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
END:VEVENT
END:VCALENDAR
"""

        data_future_external = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
X-CALENDARSERVER-SPLIT-OLDER-UID:%(relID)s
X-CALENDARSERVER-SPLIT-RID;VALUE=DATE-TIME:%(now_back14)s
BEGIN:VEVENT
UID:12345-67890
DTSTART:%(now_back14)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:uuid:user02
ATTENDEE;RSVP=TRUE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
RRULE:FREQ=DAILY
SEQUENCE:1
SUMMARY:1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:%(now_fwd10)s
DTSTART:%(now_fwd10)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;RSVP=TRUE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
SEQUENCE:1
END:VEVENT
END:VCALENDAR
"""

        data_past_external = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
X-CALENDARSERVER-SPLIT-NEWER-UID:12345-67890
X-CALENDARSERVER-SPLIT-RID;VALUE=DATE-TIME:%(now_back14)s
BEGIN:VEVENT
UID:%(relID)s
DTSTART:%(now_back30)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:uuid:user02
ATTENDEE;RSVP=TRUE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
EXDATE:%(now_back24)s
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
RRULE:FREQ=DAILY;UNTIL=%(now_back14_1)s
SEQUENCE:1
SUMMARY:1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
 1234567890123456789012345678901234567890
END:VEVENT
BEGIN:VEVENT
UID:%(relID)s
RECURRENCE-ID:%(now_back25)s
DTSTART:%(now_back25)s
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:uuid:user02
ATTENDEE;RSVP=TRUE:mailto:cuser01@example.org
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
RELATED-TO;RELTYPE=X-CALENDARSERVER-RECURRENCE-SET:%(relID)s
SEQUENCE:1
END:VEVENT
END:VCALENDAR
"""

        # Patch CalDAVScheduler to trap external schedules
        details = []
        def _doSchedulingViaPUT(self, originator, recipients, calendar, internal_request=False, suppress_refresh=False):
            details.append((originator, recipients, calendar,))

            responses = ScheduleResponseQueue("REQUEST", responsecode.OK)
            for recipient in recipients:
                responses.add(recipient, responsecode.OK, reqstatus=iTIPRequestStatus.MESSAGE_DELIVERED)
            return succeed(responses)

        component = Component.fromString(data % self.subs)
        cobj = yield calendar.createCalendarObjectWithName("data1.ics", component)
        self.assertTrue(hasattr(cobj, "_workItems"))
        work = cobj._workItems[0]
        yield self.commit()

        self.patch(CalDAVScheduler, "doSchedulingViaPUT", _doSchedulingViaPUT)

        w = schema.CALENDAR_OBJECT_SPLITTER_WORK
        rows = yield Select(
            [w.RESOURCE_ID, ],
            From=w
        ).on(self.transactionUnderTest())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], cobj._resourceID)
        yield self.abort()

        # Wait for it to complete
        yield work.whenExecuted()

        rows = yield Select(
            [w.RESOURCE_ID, ],
            From=w
        ).on(self.transactionUnderTest())
        self.assertEqual(len(rows), 0)
        yield self.abort()

        # Get the existing and new object data
        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="user01")
        self.assertTrue(cobj1.isScheduleObject)
        ical1 = yield cobj1.component()
        newUID = ical1.masterComponent().propertyValue("RELATED-TO")

        cobj2 = yield self.calendarObjectUnderTest(name="%s.ics" % (newUID,), calendar_name="calendar", home="user01")
        self.assertTrue(cobj2 is not None)
        self.assertTrue(cobj2.isScheduleObject)

        ical_future = yield cobj1.component()
        ical_past = yield cobj2.component()

        # Verify user01 data
        title = "user01"
        relsubs = dict(self.subs)
        relsubs["relID"] = newUID
        self.assertEqual(normalize_iCalStr(ical_future), normalize_iCalStr(data_future) % relsubs, "Failed future: %s\n%s" % (title, diff_iCalStrs(ical_future, data_future % relsubs),))
        self.assertEqual(normalize_iCalStr(ical_past), normalize_iCalStr(data_past) % relsubs, "Failed past: %s\n%s" % (title, diff_iCalStrs(ical_past, data_past % relsubs),))

        # Get user02 data
        cal = yield self.calendarUnderTest(name="calendar", home="user02")
        cobjs = yield cal.calendarObjects()
        self.assertEqual(len(cobjs), 2)
        for cobj in cobjs:
            ical = yield cobj.component()
            if ical.resourceUID() == "12345-67890":
                ical_future = ical
            else:
                ical_past = ical

        cal = yield self.calendarUnderTest(name="inbox", home="user02")
        cobjs = yield cal.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        ical_inbox = yield cobjs[0].component()

        # Verify user02 data
        title = "user02"
        self.assertEqual(normalize_iCalStr(ical_future), normalize_iCalStr(data_future2) % relsubs, "Failed future: %s\n%s" % (title, diff_iCalStrs(ical_future, data_future2 % relsubs),))
        self.assertEqual(normalize_iCalStr(ical_past), normalize_iCalStr(data_past2) % relsubs, "Failed past: %s\n%s" % (title, diff_iCalStrs(ical_past, data_past2 % relsubs),))
        self.assertEqual(normalize_iCalStr(ical_inbox), normalize_iCalStr(data_inbox2) % relsubs, "Failed past: %s\n%s" % (title, diff_iCalStrs(ical_inbox, data_inbox2 % relsubs),))

        # Verify cuser02 data
        self.assertEqual(len(details), 2)
        self.assertEqual(details[0][0], "urn:uuid:user01")
        self.assertEqual(details[0][1], ("mailto:cuser01@example.org",))
        self.assertEqual(normalize_iCalStr(details[0][2]), normalize_iCalStr(data_future_external) % relsubs, "Failed future: %s\n%s" % (title, diff_iCalStrs(details[0][2], data_future_external % relsubs),))

        self.assertEqual(details[1][0], "urn:uuid:user01")
        self.assertEqual(details[1][1], ("mailto:cuser01@example.org",))
        self.assertEqual(normalize_iCalStr(details[1][2]), normalize_iCalStr(data_past_external) % relsubs, "Failed past: %s\n%s" % (title, diff_iCalStrs(details[1][2], data_past_external % relsubs),))
'''
