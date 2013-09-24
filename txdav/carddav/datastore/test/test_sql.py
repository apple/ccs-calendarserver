##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
Tests for L{txdav.carddav.datastore.sql}, mostly based on
L{txdav.carddav.datastore.test.common}.
"""

from twext.enterprise.dal.syntax import Select, Parameter

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from twisted.internet.task import deferLater

from twisted.trial import unittest

from twistedcaldav import carddavxml
from twistedcaldav.vcard import Component as VCard
from twistedcaldav.vcard import Component as VComponent

from txdav.base.propertystore.base import PropertyName

from txdav.carddav.datastore.test.common import CommonTests as AddressBookCommonTests, \
    vcard4_text
from txdav.carddav.datastore.test.test_file import setUpAddressBookStore
from txdav.carddav.datastore.util import _migrateAddressbook, migrateHome

from txdav.common.icommondatastore import NoSuchObjectResourceError
from txdav.common.datastore.sql import EADDRESSBOOKTYPE, CommonObjectResource
from txdav.common.datastore.sql_tables import  _ABO_KIND_PERSON, _ABO_KIND_GROUP, \
    schema, _BIND_MODE_DIRECT, _BIND_STATUS_ACCEPTED, _BIND_MODE_WRITE, \
    _BIND_STATUS_INVITED
from txdav.common.datastore.test.util import buildStore

from txdav.xml.rfc2518 import GETContentLanguage, ResourceType



class AddressBookSQLStorageTests(AddressBookCommonTests, unittest.TestCase):
    """
    AddressBook SQL storage tests.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(AddressBookSQLStorageTests, self).setUp()
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


    def storeUnderTest(self):
        """
        Create and return a L{AddressBookStore} for testing.
        """
        return self._sqlStore


    @inlineCallbacks
    def assertAddressbooksSimilar(self, a, b, bAddressbookFilter=None):
        """
        Assert that two addressbooks have a similar structure (contain the same
        events).
        """
        @inlineCallbacks
        def namesAndComponents(x, filter=lambda x: x.component()):
            fromObjs = yield x.addressbookObjects()
            returnValue(dict([(fromObj.name(), (yield filter(fromObj)))
                              for fromObj in fromObjs]))
        if bAddressbookFilter is not None:
            extra = [bAddressbookFilter]
        else:
            extra = []
        self.assertEquals((yield namesAndComponents(a)),
                          (yield namesAndComponents(b, *extra)))


    def assertPropertiesSimilar(self, a, b, disregard=[]):
        """
        Assert that two objects with C{properties} methods have similar
        properties.

        @param disregard: a list of L{PropertyName} keys to discard from both
            input and output.
        """
        def sanitize(x):
            result = dict(x.properties().items())
            for key in disregard:
                result.pop(key, None)
            return result
        self.assertEquals(sanitize(a), sanitize(b))


    def fileTransaction(self):
        """
        Create a file-backed addressbook transaction, for migration testing.
        """
        setUpAddressBookStore(self)
        fileStore = self.addressbookStore
        txn = fileStore.newTransaction()
        self.addCleanup(txn.commit)
        return txn


    @inlineCallbacks
    def test_migrateAddressbookFromFile(self):
        """
        C{_migrateAddressbook()} can migrate a file-backed addressbook to a
        database- backed addressbook.
        """
        fromAddressbook = yield self.fileTransaction().addressbookHomeWithUID(
            "home1").addressbookWithName("addressbook")
        toHome = yield self.transactionUnderTest().addressbookHomeWithUID(
            "new-home", create=True)
        toAddressbook = yield toHome.addressbookWithName("addressbook")
        yield _migrateAddressbook(fromAddressbook, toAddressbook,
                                  lambda x: x.component())
        yield self.assertAddressbooksSimilar(fromAddressbook, toAddressbook)


    @inlineCallbacks
    def test_migrateBadAddressbookFromFile(self):
        """
        C{_migrateAddressbook()} can migrate a file-backed addressbook to a
        database-backed addressbook. We need to test what happens when there
        is "bad" address data present in the file-backed addressbook.
        """
        fromAddressbook = yield self.fileTransaction().addressbookHomeWithUID(
            "home_bad").addressbookWithName("addressbook")
        toHome = yield self.transactionUnderTest().addressbookHomeWithUID(
            "new-home", create=True)
        toAddressbook = yield toHome.addressbookWithName("addressbook")
        ok, bad = (yield _migrateAddressbook(fromAddressbook, toAddressbook,
                                  lambda x: x.component()))
        self.assertEqual(ok, 1)
        self.assertEqual(bad, 1)


    @inlineCallbacks
    def test_migrateHomeFromFile(self):
        """
        L{migrateHome} will migrate an L{IAddressbookHome} provider from one
        backend to another; in this specific case, from the file-based backend
        to the SQL-based backend.
        """
        fromHome = yield self.fileTransaction().addressbookHomeWithUID("home1")

        # Populate an arbitrary / unused dead properties so there's something
        # to verify against.

        key = PropertyName.fromElement(GETContentLanguage)
        fromHome.properties()[key] = GETContentLanguage("C")
        (yield fromHome.addressbookWithName("addressbook")).properties()[
            key] = (
            GETContentLanguage("pig-latin")
        )
        (yield fromHome.addressbookWithName("addressbook")).properties()[
            PropertyName.fromElement(ResourceType)] = (
            carddavxml.ResourceType.addressbook
        )
        toHome = yield self.transactionUnderTest().addressbookHomeWithUID(
            "new-home", create=True
        )
        yield migrateHome(fromHome, toHome, lambda x: x.component())
        toAddressbooks = yield toHome.addressbooks()
        self.assertEquals(set([c.name() for c in toAddressbooks]),
                          set([k for k in self.requirements['home1'].keys()
                               if self.requirements['home1'][k] is not None]))
        fromAddressbooks = yield fromHome.addressbooks()
        for c in fromAddressbooks:
            self.assertPropertiesSimilar(
                c, (yield toHome.addressbookWithName(c.name())),
            )
        self.assertPropertiesSimilar(fromHome, toHome,)


    def test_addressBookHomeVersion(self):
        """
        The DATAVERSION column for new addressbook homes must match the
        ADDRESSBOOK-DATAVERSION value.
        """

        home = yield self.transactionUnderTest().addressbookHomeWithUID("home_version")
        self.assertTrue(home is not None)
        yield self.transactionUnderTest().commit

        txn = yield self.transactionUnderTest()
        version = yield txn.calendarserverValue("ADDRESSBOOK-DATAVERSION")[0][0]
        ch = schema.ADDRESSBOOK_HOME
        homeVersion = yield Select(
            [ch.DATAVERSION, ],
            From=ch,
            Where=ch.OWNER_UID == "home_version",
        ).on(txn)[0][0]
        self.assertEqual(int(homeVersion, version))


    @inlineCallbacks
    def test_homeProvisioningConcurrency(self):
        """
        Test that two concurrent attempts to provision a addressbook home do not
        cause a race-condition whereby the second commit results in a second
        C{INSERT} that violates a unique constraint. Also verify that, while
        the two provisioning attempts are happening and doing various lock
        operations, that we do not block other reads of the table.
        """

        addressbookStore = self._sqlStore

        txn1 = addressbookStore.newTransaction()
        txn2 = addressbookStore.newTransaction()
        txn3 = addressbookStore.newTransaction()

        # Provision one home now - we will use this to later verify we can do
        # reads of existing data in the table
        home_uid2 = yield txn3.homeWithUID(EADDRESSBOOKTYPE, "uid2", create=True)
        self.assertNotEqual(home_uid2, None)
        yield txn3.commit()

        home_uid1_1 = yield txn1.homeWithUID(
            EADDRESSBOOKTYPE, "uid1", create=True
        )

        @inlineCallbacks
        def _defer_home_uid1_2():
            home_uid1_2 = yield txn2.homeWithUID(
                EADDRESSBOOKTYPE, "uid1", create=True
            )
            yield txn2.commit()
            returnValue(home_uid1_2)
        d1 = _defer_home_uid1_2()

        @inlineCallbacks
        def _pause_home_uid1_1():
            yield deferLater(reactor, 1.0, lambda : None)
            yield txn1.commit()
        d2 = _pause_home_uid1_1()

        # Verify that we can still get to the existing home - i.e. the lock
        # on the table allows concurrent reads
        txn4 = addressbookStore.newTransaction()
        home_uid2 = yield txn4.homeWithUID(EADDRESSBOOKTYPE, "uid2", create=True)
        self.assertNotEqual(home_uid2, None)
        yield txn4.commit()

        # Now do the concurrent provision attempt
        yield d2
        home_uid1_2 = yield d1

        self.assertNotEqual(home_uid1_1, None)
        self.assertNotEqual(home_uid1_2, None)


    @inlineCallbacks
    def test_putConcurrency(self):
        """
        Test that two concurrent attempts to PUT different address book object resources to the
        same address book home does not cause a deadlock.
        """
        addressbookStore = yield buildStore(self, self.notifierFactory)

        # Provision the home and addressbook now
        txn = addressbookStore.newTransaction()
        home = yield txn.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        self.assertNotEqual(home, None)
        adbk = yield home.addressbookWithName("addressbook")
        self.assertNotEqual(adbk, None)
        yield txn.commit()

        txn1 = addressbookStore.newTransaction()
        txn2 = addressbookStore.newTransaction()

        home1 = yield txn1.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        home2 = yield txn2.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)

        adbk1 = yield home1.addressbookWithName("addressbook")
        adbk2 = yield home2.addressbookWithName("addressbook")

        @inlineCallbacks
        def _defer1():
            yield adbk1.createAddressBookObjectWithName("1.vcf", VCard.fromString(
                """BEGIN:VCARD
VERSION:3.0
N:Thompson;Default1;;;
FN:Default1 Thompson
EMAIL;type=INTERNET;type=WORK;type=pref:lthompson1@example.com
TEL;type=WORK;type=pref:1-555-555-5555
TEL;type=CELL:1-444-444-4444
item1.ADR;type=WORK;type=pref:;;1245 Test;Sesame Street;California;11111;USA
item1.X-ABADR:us
UID:uid1
END:VCARD
""".replace("\n", "\r\n")
            ))
            yield txn1.commit()  # FIXME: CONCURRENT
        d1 = _defer1()

        @inlineCallbacks
        def _defer2():
            yield adbk2.createAddressBookObjectWithName("2.vcf", VCard.fromString(
                """BEGIN:VCARD
VERSION:3.0
N:Thompson;Default2;;;
FN:Default2 Thompson
EMAIL;type=INTERNET;type=WORK;type=pref:lthompson2@example.com
TEL;type=WORK;type=pref:1-555-555-5556
TEL;type=CELL:1-444-444-4445
item1.ADR;type=WORK;type=pref:;;1234 Test;Sesame Street;California;11111;USA
item1.X-ABADR:us
UID:uid2
END:VCARD
""".replace("\n", "\r\n")
            ))
            yield txn2.commit()  # FIXME: CONCURRENT
        d2 = _defer2()

        yield d1
        yield d2


    @inlineCallbacks
    def test_notificationsProvisioningConcurrency(self):
        """
        Test that two concurrent attempts to provision a notifications collection do not
        cause a race-condition whereby the second commit results in a second
        C{INSERT} that violates a unique constraint.
        """

        addressbookStore = self._sqlStore

        txn1 = addressbookStore.newTransaction()
        txn2 = addressbookStore.newTransaction()

        notification_uid1_1 = yield txn1.notificationsWithUID(
           "uid1",
        )

        @inlineCallbacks
        def _defer_notification_uid1_2():
            notification_uid1_2 = yield txn2.notificationsWithUID(
                "uid1",
            )
            yield txn2.commit()
            returnValue(notification_uid1_2)
        d1 = _defer_notification_uid1_2()

        @inlineCallbacks
        def _pause_notification_uid1_1():
            yield deferLater(reactor, 1.0, lambda : None)
            yield txn1.commit()
        d2 = _pause_notification_uid1_1()

        # Now do the concurrent provision attempt
        yield d2
        notification_uid1_2 = yield d1

        self.assertNotEqual(notification_uid1_1, None)
        self.assertNotEqual(notification_uid1_2, None)


    @inlineCallbacks
    def test_addressbookObjectUID(self):
        """
        Test that kind property UID is stored correctly in database
        """
        addressbookStore = yield buildStore(self, self.notifierFactory)

        # Provision the home and addressbook, one user and one group
        txn = addressbookStore.newTransaction()
        home = yield txn.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        self.assertNotEqual(home, None)
        adbk = yield home.addressbookWithName("addressbook")
        self.assertNotEqual(adbk, None)

        person = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
N:Thompson;Default;;;
FN:Default Thompson
EMAIL;type=INTERNET;type=WORK;type=pref:lthompson@example.com
TEL;type=WORK;type=pref:1-555-555-5555
TEL;type=CELL:1-444-444-4444
item1.ADR;type=WORK;type=pref:;;1245 Test;Sesame Street;California;11111;USA
item1.X-ABADR:us
UID:uid1
END:VCARD
""".replace("\n", "\r\n")
            )
        self.assertEqual(person.resourceUID(), "uid1")
        abObject = yield adbk.createAddressBookObjectWithName("1.vcf", person)
        self.assertEqual(abObject.uid(), "uid1")
        yield txn.commit()

        txn = addressbookStore.newTransaction()
        home = yield txn.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        adbk = yield home.addressbookWithName("addressbook")

        abObject = yield adbk.objectResourceWithName("1.vcf")
        person = yield abObject.component()
        self.assertEqual(person.resourceUID(), "uid1")

        yield home.removeAddressBookWithName("addressbook")

        yield txn.commit()


    @inlineCallbacks
    def test_addressbookObjectKind(self):
        """
        Test that kind property vCard is stored correctly in database
        """
        addressbookStore = yield buildStore(self, self.notifierFactory)

        # Provision the home and addressbook, one user and one group
        txn = addressbookStore.newTransaction()
        home = yield txn.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        self.assertNotEqual(home, None)
        adbk = yield home.addressbookWithName("addressbook")
        self.assertNotEqual(adbk, None)

        person = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
N:Thompson;Default;;;
FN:Default Thompson
EMAIL;type=INTERNET;type=WORK;type=pref:lthompson@example.com
TEL;type=WORK;type=pref:1-555-555-5555
TEL;type=CELL:1-444-444-4444
item1.ADR;type=WORK;type=pref:;;1245 Test;Sesame Street;California;11111;USA
item1.X-ABADR:us
UID:uid1
END:VCARD
""".replace("\n", "\r\n")
            )
        self.assertEqual(person.resourceKind(), None)
        abObject = yield adbk.createAddressBookObjectWithName("p.vcf", person)
        self.assertEqual(abObject.kind(), _ABO_KIND_PERSON)

        group = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:uid2
FN:Top Group
N:Top Group;;;;
REV:20120503T194243Z
X-ADDRESSBOOKSERVER-KIND:group
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:uid1
END:VCARD
""".replace("\n", "\r\n")
            )
        abObject = self.assertEqual(group.resourceKind(), "group")
        abObject = yield adbk.createAddressBookObjectWithName("g.vcf", group)
        self.assertEqual(abObject.kind(), _ABO_KIND_GROUP)

        badgroup = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:uid3
FN:Bad Group
N:Bad Group;;;;
REV:20120503T194243Z
X-ADDRESSBOOKSERVER-KIND:badgroup
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:uid1
END:VCARD
""".replace("\n", "\r\n")
            )
        abObject = self.assertEqual(badgroup.resourceKind(), "badgroup")
        abObject = yield adbk.createAddressBookObjectWithName("bg.vcf", badgroup)
        self.assertEqual(abObject.kind(), _ABO_KIND_PERSON)

        yield txn.commit()

        txn = addressbookStore.newTransaction()
        home = yield txn.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        adbk = yield home.addressbookWithName("addressbook")

        abObject = yield adbk.objectResourceWithName("p.vcf")
        person = yield abObject.component()
        self.assertEqual(person.resourceKind(), None)
        self.assertEqual(abObject.kind(), _ABO_KIND_PERSON)

        abObject = yield adbk.objectResourceWithName("g.vcf")
        group = yield abObject.component()
        self.assertEqual(group.resourceKind(), "group")
        self.assertEqual(abObject.kind(), _ABO_KIND_GROUP)

        abObject = yield adbk.objectResourceWithName("bg.vcf")
        badgroup = yield abObject.component()
        self.assertEqual(badgroup.resourceKind(), "badgroup")
        self.assertEqual(abObject.kind(), _ABO_KIND_PERSON)

        yield home.removeAddressBookWithName("addressbook")
        yield txn.commit()


    @inlineCallbacks
    def test_addressbookObjectMembers(self):
        """
        Test that kind property vCard is stored correctly in database
        """
        addressbookStore = yield buildStore(self, self.notifierFactory)

        # Provision the home and addressbook, one user and one group
        txn = addressbookStore.newTransaction()
        home = yield txn.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        self.assertNotEqual(home, None)
        adbk = yield home.addressbookWithName("addressbook")
        self.assertNotEqual(adbk, None)

        person = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
N:Thompson;Default;;;
FN:Default Thompson
EMAIL;type=INTERNET;type=WORK;type=pref:lthompson@example.com
TEL;type=WORK;type=pref:1-555-555-5555
TEL;type=CELL:1-444-444-4444
item1.ADR;type=WORK;type=pref:;;1245 Test;Sesame Street;California;11111;USA
item1.X-ABADR:us
UID:uid1
END:VCARD
""".replace("\n", "\r\n")
            )
        self.assertEqual(person.resourceKind(), None)
        personObject = yield adbk.createAddressBookObjectWithName("p.vcf", person)

        group = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:uid2
FN:Top Group
N:Top Group;;;;
REV:20120503T194243Z
X-ADDRESSBOOKSERVER-KIND:group
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:uid3
END:VCARD
""".replace("\n", "\r\n")
            )
        groupObject = yield adbk.createAddressBookObjectWithName("g.vcf", group)

        aboMembers = schema.ABO_MEMBERS
        memberRows = yield Select([aboMembers.GROUP_ID, aboMembers.MEMBER_ID], From=aboMembers, Where=aboMembers.REMOVED == False).on(txn)
        self.assertEqual(memberRows, [])

        aboForeignMembers = schema.ABO_FOREIGN_MEMBERS
        foreignMemberRows = yield Select([aboForeignMembers.GROUP_ID, aboForeignMembers.MEMBER_ADDRESS], From=aboForeignMembers).on(txn)
        self.assertEqual(foreignMemberRows, [[groupObject._resourceID, "urn:uuid:uid3"]])

        subgroup = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:uid3
FN:Sub Group
N:Sub Group;;;;
REV:20120503T194243Z
X-ADDRESSBOOKSERVER-KIND:group
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:uid1
END:VCARD
""".replace("\n", "\r\n")
            )
        subgroupObject = yield adbk.createAddressBookObjectWithName("sg.vcf", subgroup)

        memberRows = yield Select([aboMembers.GROUP_ID, aboMembers.MEMBER_ID], From=aboMembers, Where=aboMembers.REMOVED == False).on(txn)
        self.assertEqual(sorted(memberRows), sorted([
                                                     [groupObject._resourceID, subgroupObject._resourceID],
                                                     [subgroupObject._resourceID, personObject._resourceID],
                                                    ]))

        foreignMemberRows = yield Select([aboForeignMembers.GROUP_ID, aboForeignMembers.MEMBER_ADDRESS], From=aboForeignMembers).on(txn)
        self.assertEqual(foreignMemberRows, [])

        yield subgroupObject.remove()
        memberRows = yield Select([aboMembers.GROUP_ID, aboMembers.MEMBER_ID], From=aboMembers, Where=aboMembers.REMOVED == False).on(txn)
        self.assertEqual(memberRows, [])

        foreignMemberRows = yield Select([aboForeignMembers.GROUP_ID, aboForeignMembers.MEMBER_ADDRESS], From=aboForeignMembers,
                                                 #Where=(aboForeignMembers.GROUP_ID == groupObject._resourceID),
                                                 ).on(txn)
        self.assertEqual(foreignMemberRows, [[groupObject._resourceID, "urn:uuid:uid3"]])

        yield home.removeAddressBookWithName("addressbook")
        yield txn.commit()


    @inlineCallbacks
    def test_removeAddressBookPropertiesOnDelete(self):
        """
        L{IAddressBookHome.removeAddressBookWithName} clears an address book that already
        exists and makes sure added properties are also removed.
        """

        prop = schema.RESOURCE_PROPERTY
        _allWithID = Select([prop.NAME, prop.VIEWER_UID, prop.VALUE],
                        From=prop,
                        Where=prop.RESOURCE_ID == Parameter("resourceID"))

        # Create address book and add a property
        home = yield self.homeUnderTest()
        addressbook = home.addressbook()
        resourceID = home._addressbookPropertyStoreID

        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)

        addressbookProperties = addressbook.properties()
        prop = carddavxml.AddressBookDescription.fromString("Address Book prop to be removed")
        addressbookProperties[PropertyName.fromElement(prop)] = prop
        yield self.commit()

        # Check that two properties are present
        home = yield self.homeUnderTest()
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 1)
        yield self.commit()

        # Remove address book and check for no properties
        home = yield self.homeUnderTest()
        yield home.removeAddressBookWithName(addressbook.name())
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()

        # Recheck it
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()


    @inlineCallbacks
    def test_removeAddressBookObjectPropertiesOnDelete(self):
        """
        L{IAddressBookHome.removeAddressBookWithName} removes an address book object that already
        exists and makes sure properties are also removed (which is always the case as right
        now address book objects never have properties).
        """

        # Create address book object
        adbk1 = yield self.addressbookUnderTest()
        name = "4.vcf"
        component = VComponent.fromString(vcard4_text)
        addressobject = yield adbk1.createAddressBookObjectWithName(name, component, options={})
        resourceID = addressobject._resourceID

        prop = schema.RESOURCE_PROPERTY
        _allWithID = Select([prop.NAME, prop.VIEWER_UID, prop.VALUE],
                        From=prop,
                        Where=prop.RESOURCE_ID == Parameter("resourceID"))

        # No properties on existing address book object
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)

        yield self.commit()

        # Remove address book object and check for no properties
        adbk1 = yield self.addressbookUnderTest()
        obj1 = yield adbk1.addressbookObjectWithName(name)
        yield obj1.remove()
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()

        # Recheck it
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()


    @inlineCallbacks
    def test_directShareCreateConcurrency(self):
        """
        Test that two concurrent attempts to create a direct shared addressbook
        work concurrently without an exception.
        """

        addressbookStore = self._sqlStore

        # Provision the home and addressbook now
        txn = addressbookStore.newTransaction()
        sharerHome = yield txn.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        self.assertNotEqual(sharerHome, None)
        ab = yield sharerHome.addressbookWithName("addressbook")
        self.assertNotEqual(ab, None)
        shareeHome = yield txn.homeWithUID(EADDRESSBOOKTYPE, "uid2", create=True)
        self.assertNotEqual(shareeHome, None)
        yield txn.commit()

        txn1 = addressbookStore.newTransaction()
        txn2 = addressbookStore.newTransaction()

        sharerHome1 = yield txn1.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        self.assertNotEqual(sharerHome1, None)
        ab1 = yield sharerHome1.addressbookWithName("addressbook")
        self.assertNotEqual(ab1, None)
        shareeHome1 = yield txn1.homeWithUID(EADDRESSBOOKTYPE, "uid2", create=True)
        self.assertNotEqual(shareeHome1, None)

        sharerHome2 = yield txn2.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
        self.assertNotEqual(sharerHome2, None)
        ab2 = yield sharerHome2.addressbookWithName("addressbook")
        self.assertNotEqual(ab2, None)
        shareeHome2 = yield txn1.homeWithUID(EADDRESSBOOKTYPE, "uid2", create=True)
        self.assertNotEqual(shareeHome2, None)

        @inlineCallbacks
        def _defer1():
            yield ab1.shareWith(shareeHome=sharerHome1, mode=_BIND_MODE_DIRECT, status=_BIND_STATUS_ACCEPTED, message="Shared Wiki AddressBook")
            yield txn1.commit()
        d1 = _defer1()

        @inlineCallbacks
        def _defer2():
            yield ab2.shareWith(shareeHome=sharerHome2, mode=_BIND_MODE_DIRECT, status=_BIND_STATUS_ACCEPTED, message="Shared Wiki AddressBook")
            yield txn2.commit()
        d2 = _defer2()

        yield d1
        yield d2


    @inlineCallbacks
    def test_resourceLock(self):
        """
        Test CommonObjectResource.lock to make sure it locks, raises on missing resource,
        and raises when locked and wait=False used.
        """

        # Valid object
        resource = yield self.addressbookObjectUnderTest()

        # Valid lock
        yield resource.lock()
        self.assertTrue(resource._locked)

        # Setup a new transaction to verify the lock and also verify wait behavior
        newTxn = self._sqlStore.newTransaction()
        newResource = yield self.addressbookObjectUnderTest(txn=newTxn)
        try:
            yield newResource.lock(wait=False)
        except:
            pass  # OK
        else:
            self.fail("Expected an exception")
        self.assertFalse(newResource._locked)
        yield newTxn.abort()

        # Commit existing transaction and verify we can get the lock using
        yield self.commit()

        resource = yield self.addressbookObjectUnderTest()
        yield resource.lock()
        self.assertTrue(resource._locked)

        # Setup a new transaction to verify the lock but pass in an alternative txn directly
        newTxn = self._sqlStore.newTransaction()

        # FIXME: not sure why, but without this statement here, this portion of the test fails in a funny way.
        # Basically the query in the try block seems to execute twice, failing each time, one of which is caught,
        # and the other not - causing the test to fail. Seems like some state on newTxn is not being initialized?
        yield self.addressbookObjectUnderTest(txn=newTxn, name="2.vcf")

        try:
            yield resource.lock(wait=False, useTxn=newTxn)
        except:
            pass  # OK
        else:
            self.fail("Expected an exception")
        self.assertTrue(resource._locked)

        # Test missing resource
        resource2 = yield self.addressbookObjectUnderTest(name="2.vcf")
        resource2._resourceID = 123456789
        try:
            yield resource2.lock()
        except NoSuchObjectResourceError:
            pass  # OK
        except:
            self.fail("Expected a NoSuchObjectResourceError exception")
        else:
            self.fail("Expected an exception")
        self.assertFalse(resource2._locked)


    @inlineCallbacks
    def test_loadObjectResourcesWithName(self):
        """
        L{CommonHomeChild.objectResourcesWithNames} returns the correct set of object resources
        properly configured with a loaded property store. make sure batching works.
        """

        @inlineCallbacks
        def _tests(ab):
            resources = yield ab.objectResourcesWithNames(("1.vcf",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("1.vcf",)))

            resources = yield ab.objectResourcesWithNames(("1.vcf", "2.vcf",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("1.vcf", "2.vcf",)))

            resources = yield ab.objectResourcesWithNames(("1.vcf", "2.vcf", "3.vcf",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("1.vcf", "2.vcf", "3.vcf",)))

            resources = yield ab.objectResourcesWithNames(("bogus1.vcf",))
            self.assertEqual(set([resource.name() for resource in resources]), set())

            resources = yield ab.objectResourcesWithNames(("bogus1.vcf", "2.vcf",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("2.vcf",)))

        # Basic load tests
        ab = yield self.addressbookUnderTest()
        yield _tests(ab)

        # Adjust batch size and try again
        self.patch(CommonObjectResource, "BATCH_LOAD_SIZE", 2)
        yield _tests(ab)

        yield self.commit()


    @inlineCallbacks
    def test_objectResourceWithID(self):
        """
        L{IAddressBookHome.objectResourceWithID} will return the addressbook object..
        """
        home = yield self.homeUnderTest()
        addressbookObject = (yield home.objectResourceWithID(9999))
        self.assertEquals(addressbookObject, None)

        obj = (yield self.addressbookObjectUnderTest())
        addressbookObject = (yield home.objectResourceWithID(obj._resourceID))
        self.assertNotEquals(addressbookObject, None)


    @inlineCallbacks
    def test_shareWithRevision(self):
        """
        Verify that bindRevision on addressbooks and shared addressbooks has the correct value.
        """
        ab = yield self.addressbookUnderTest()
        self.assertEqual(ab._bindRevision, 0)
        other = yield self.homeUnderTest(name="home2")
        newABShareUID = yield ab.shareWith(other, _BIND_MODE_WRITE)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest()
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="home2")
        otherAB = yield otherHome.objectWithShareUID(newABShareUID)
        self.assertNotEqual(otherAB._bindRevision, 0)


    @inlineCallbacks
    def test_shareGroupWithRevision(self):
        """
        Verify that bindRevision on addressbooks and shared groups has the correct value.
        """
        ab = yield self.addressbookUnderTest(home="home3")
        self.assertEqual(ab._bindRevision, 0)
        group = yield ab.objectResourceWithName("4.vcf")
        other = yield self.homeUnderTest(name="home2")
        newGroupShareUID = yield group.shareWith(other, _BIND_MODE_WRITE)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest(home="home3")
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="home2")
        otherGroup = yield otherHome.objectWithShareUID(newGroupShareUID)
        self.assertNotEqual(otherGroup._bindRevision, 0)
        otherAB = otherGroup.addressbook()
        self.assertEqual(otherAB._bindRevision, None)


    @inlineCallbacks
    def test_updateShareRevision(self):
        """
        Verify that bindRevision on addressbooks and shared addressbooks has the correct value.
        """
        ab = yield self.addressbookUnderTest()
        self.assertEqual(ab._bindRevision, 0)
        other = yield self.homeUnderTest(name="home2")
        newABShareUID = yield ab.shareWith(other, _BIND_MODE_WRITE, status=_BIND_STATUS_INVITED)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest()
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="home2")
        otherAB = yield otherHome.invitedObjectWithShareUID(newABShareUID)
        self.assertEqual(otherAB._bindRevision, 0)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest()
        otherHome = yield self.homeUnderTest(name="home2")
        otherAB = yield otherHome.invitedObjectWithShareUID(newABShareUID)
        yield normalAB.updateShare(otherAB, status=_BIND_STATUS_ACCEPTED)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest()
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="home2")
        otherAB = yield otherHome.objectWithShareUID(newABShareUID)
        self.assertNotEqual(otherAB._bindRevision, 0)


    @inlineCallbacks
    def test_updateSharedGroupRevision(self):
        """
        Verify that bindRevision on addressbooks and shared addressbooks has the correct value.
        """
        ab = yield self.addressbookUnderTest(home="home3")
        self.assertEqual(ab._bindRevision, 0)
        group = yield ab.objectResourceWithName("4.vcf")
        other = yield self.homeUnderTest(name="home2")
        newGroupShareUID = yield group.shareWith(other, _BIND_MODE_WRITE, status=_BIND_STATUS_INVITED)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest(home="home3")
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="home2")
        otherGroup = yield otherHome.invitedObjectWithShareUID(newGroupShareUID)
        self.assertEqual(otherGroup._bindRevision, 0)
        otherAB = otherGroup.addressbook()
        self.assertEqual(otherAB._bindRevision, None)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest(home="home3")
        normalGroup = yield normalAB.objectResourceWithName("4.vcf")
        otherHome = yield self.homeUnderTest(name="home2")
        otherGroup = yield otherHome.invitedObjectWithShareUID(newGroupShareUID)
        yield normalGroup.updateShare(otherGroup, status=_BIND_STATUS_ACCEPTED)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest(home="home3")
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="home2")
        otherGroup = yield otherHome.objectWithShareUID(newGroupShareUID)
        self.assertNotEqual(otherGroup._bindRevision, 0)
        otherAB = otherGroup.addressbook()
        self.assertEqual(otherAB._bindRevision, None)


    @inlineCallbacks
    def test_sharedRevisions(self):
        """
        Verify that resourceNamesSinceRevision returns all resources after initial bind and sync.
        """
        ab = yield self.addressbookUnderTest()
        self.assertEqual(ab._bindRevision, 0)
        other = yield self.homeUnderTest(name="home2")
        newABShareUID = yield ab.shareWith(other, _BIND_MODE_WRITE)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest()
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="home2")
        otherAB = yield otherHome.objectWithShareUID(newABShareUID)
        self.assertNotEqual(otherAB._bindRevision, 0)

        changed, deleted = yield otherAB.resourceNamesSinceRevision(0)
        self.assertNotEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)

        changed, deleted = yield otherAB.resourceNamesSinceRevision(otherAB._bindRevision)
        self.assertEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)

        for depth in ("1", "infinity",):
            changed, deleted = yield otherHome.resourceNamesSinceRevision(0, depth)
            self.assertNotEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)

            changed, deleted = yield otherHome.resourceNamesSinceRevision(otherAB._bindRevision, depth)
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)


    @inlineCallbacks
    def test_sharedGroupRevisions(self):
        """
        Verify that resourceNamesSinceRevision returns all resources after initial bind and sync.
        """
        ab = yield self.addressbookUnderTest(home="home3")
        self.assertEqual(ab._bindRevision, 0)
        group = yield ab.objectResourceWithName("4.vcf")
        other = yield self.homeUnderTest(name="home2")
        newGroupShareUID = yield group.shareWith(other, _BIND_MODE_WRITE)
        yield self.commit()

        normalAB = yield self.addressbookUnderTest(home="home3")
        self.assertEqual(normalAB._bindRevision, 0)
        otherHome = yield self.homeUnderTest(name="home2")
        otherGroup = yield otherHome.objectWithShareUID(newGroupShareUID)
        self.assertNotEqual(otherGroup._bindRevision, 0)
        otherAB = otherGroup.addressbook()
        self.assertEqual(otherAB._bindRevision, None)

        changed, deleted = yield otherAB.resourceNamesSinceRevision(0)
        print("revision=%s, changed=%s, deleted=%s" % (0, changed, deleted,))
        self.assertEqual(set(changed), set(['1.vcf', '4.vcf', '2.vcf', ]))
        self.assertEqual(len(deleted), 0)

        changed, deleted = yield otherAB.resourceNamesSinceRevision(otherGroup._bindRevision)
        print("revision=%s, changed=%s, deleted=%s" % (otherGroup._bindRevision, changed, deleted,))
        self.assertEqual(len(changed), 0)
        self.assertEqual(len(deleted), 0)

        for depth, result in (
            ("1", ['addressbook/',
                   'home3/', ]
            ),
            ("infinity", ['addressbook/',
                          'addressbook/1.vcf',
                          'addressbook/2.vcf',
                          'addressbook/3.vcf',
                          'addressbook/4.vcf',
                          'addressbook/5.vcf',
                          'home3/',
                          'home3/1.vcf',
                          'home3/2.vcf',
                          'home3/4.vcf', ]
             )):
            changed, deleted = yield otherHome.resourceNamesSinceRevision(0, depth)
            print("revision=%s, depth=%s, changed=%s, deleted=%s" % (0, depth, changed, deleted,))
            self.assertEqual(set(changed), set(result))
            self.assertEqual(len(deleted), 0)

            changed, deleted = yield otherHome.resourceNamesSinceRevision(otherGroup._bindRevision, depth)
            print("revision=%s, depth=%s, changed=%s, deleted=%s" % (otherGroup._bindRevision, depth, changed, deleted,))
            self.assertEqual(len(changed), 0)
            self.assertEqual(len(deleted), 0)


    @inlineCallbacks
    def test_addressbookRevisionChangeConcurrency(self):
        """
        Test that two concurrent attempts to add resources in two separate
        calendar homes does not deadlock on the revision table update.
        """

        # Make sure homes are provisioned
        txn = self.transactionUnderTest()
        home_uid1 = yield txn.homeWithUID(EADDRESSBOOKTYPE, "user01", create=True)
        home_uid2 = yield txn.homeWithUID(EADDRESSBOOKTYPE, "user02", create=True)
        self.assertNotEqual(home_uid1, None)
        self.assertNotEqual(home_uid2, None)
        yield self.commit()

        # Create first events in different calendar homes
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

        component = VComponent.fromString(data % {"ctr": 1})
        yield addressbook_uid1_in_txn1.createAddressBookObjectWithName("data1.ics", component)

        component = VComponent.fromString(data % {"ctr": 2})
        yield addressbook_uid2_in_txn2.createAddressBookObjectWithName("data2.ics", component)

        # Setup deferreds to run concurrently and create second events in the calendar homes
        # previously used by the other transaction - this could create the deadlock.
        @inlineCallbacks
        def _defer_uid3():
            addressbook_uid1_in_txn2 = yield self.addressbookUnderTest(txn2, "addressbook", "user01")
            component = VComponent.fromString(data % {"ctr": 3})
            yield addressbook_uid1_in_txn2.createAddressBookObjectWithName("data3.ics", component)
            yield txn2.commit()
        d1 = _defer_uid3()

        @inlineCallbacks
        def _defer_uid4():
            addressbook_uid2_in_txn1 = yield self.addressbookUnderTest(txn1, "addressbook", "user02")
            component = VComponent.fromString(data % {"ctr": 4})
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
