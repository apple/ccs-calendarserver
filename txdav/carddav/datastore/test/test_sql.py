##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Tests for txdav.caldav.datastore.postgres, mostly based on
L{txdav.caldav.datastore.test.common}.
"""

import time

from txdav.carddav.datastore.test.common import CommonTests as AddressBookCommonTests

from txdav.common.datastore.sql import EADDRESSBOOKTYPE
from txdav.common.datastore.test.util import buildStore
from txdav.carddav.datastore.test.test_file import setUpAddressBookStore
from twext.web2.dav.element.rfc2518 import GETContentLanguage, ResourceType
from txdav.base.propertystore.base import PropertyName
from txdav.carddav.datastore.util import _migrateAddressbook, migrateHome

from twisted.trial import unittest
from twisted.internet.defer import inlineCallbacks
from twisted.internet.threads import deferToThread
from twistedcaldav.vcard import Component as VCard


class AddressBookSQLStorageTests(AddressBookCommonTests, unittest.TestCase):
    """
    AddressBook SQL storage tests.
    """

    @inlineCallbacks
    def setUp(self):
        super(AddressBookSQLStorageTests, self).setUp()
        self._sqlStore = yield buildStore(self, self.notifierFactory)
        self.populate()

    def populate(self):
        populateTxn = self.storeUnderTest().newTransaction()
        for homeUID in self.requirements:
            addressbooks = self.requirements[homeUID]
            if addressbooks is not None:
                home = populateTxn.addressbookHomeWithUID(homeUID, True)
                # We don't want the default addressbook to appear unless it's
                # explicitly listed.
                home.removeAddressBookWithName("addressbook")
                for addressbookName in addressbooks:
                    addressbookObjNames = addressbooks[addressbookName]
                    if addressbookObjNames is not None:
                        home.createAddressBookWithName(addressbookName)
                        addressbook = home.addressbookWithName(addressbookName)
                        for objectName in addressbookObjNames:
                            objData = addressbookObjNames[objectName]
                            addressbook.createAddressBookObjectWithName(
                                objectName, VCard.fromString(objData)
                            )

        populateTxn.commit()
        self.notifierFactory.reset()



    def storeUnderTest(self):
        """
        Create and return a L{AddressBookStore} for testing.
        """
        return self._sqlStore


    def assertAddressbooksSimilar(self, a, b, bAddressbookFilter=None):
        """
        Assert that two addressbooks have a similar structure (contain the same
        events).
        """
        def namesAndComponents(x, filter=lambda x:x.component()):
            return dict([(fromObj.name(), filter(fromObj))
                         for fromObj in x.addressbookObjects()])
        if bAddressbookFilter is not None:
            extra = [bAddressbookFilter]
        else:
            extra = []
        self.assertEquals(namesAndComponents(a), namesAndComponents(b, *extra))


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


    def test_migrateAddressbookFromFile(self):
        """
        C{_migrateAddressbook()} can migrate a file-backed addressbook to a
        database- backed addressbook.
        """
        fromAddressbook = self.fileTransaction().addressbookHomeWithUID(
            "home1").addressbookWithName("addressbook_1")
        toHome = self.transactionUnderTest().addressbookHomeWithUID(
            "new-home", create=True)
        toAddressbook = toHome.addressbookWithName("addressbook")
        _migrateAddressbook(fromAddressbook, toAddressbook,
                            lambda x: x.component())
        self.assertAddressbooksSimilar(fromAddressbook, toAddressbook)


    def test_migrateHomeFromFile(self):
        """
        L{migrateHome} will migrate an L{IAddressbookHome} provider from one
        backend to another; in this specific case, from the file-based backend
        to the SQL-based backend.
        """
        fromHome = self.fileTransaction().addressbookHomeWithUID("home1")

        builtinProperties = [PropertyName.fromElement(ResourceType)]

        # Populate an arbitrary / unused dead properties so there's something
        # to verify against.

        key = PropertyName.fromElement(GETContentLanguage)
        fromHome.properties()[key] = GETContentLanguage("C")
        fromHome.addressbookWithName("addressbook_1").properties()[key] = (
            GETContentLanguage("pig-latin")
        )
        toHome = self.transactionUnderTest().addressbookHomeWithUID(
            "new-home", create=True
        )
        migrateHome(fromHome, toHome, lambda x: x.component())
        self.assertEquals(set([c.name() for c in toHome.addressbooks()]),
                          set([k for k in self.requirements['home1'].keys()
                               if self.requirements['home1'][k] is not None]))
        for c in fromHome.addressbooks():
            self.assertPropertiesSimilar(
                c, toHome.addressbookWithName(c.name()),
                builtinProperties
            )
        self.assertPropertiesSimilar(fromHome, toHome, builtinProperties)


    def test_eachAddressbookHome(self):
        """
        L{IAddressbookStore.eachAddressbookHome} is currently stubbed out by
        L{txdav.common.datastore.sql.CommonDataStore}.
        """
        return super(AddressBookSQLStorageTests, self).test_eachAddressbookHome()


    test_eachAddressbookHome.todo = (
        "stubbed out, as migration only needs to go from file->sql currently")


    @inlineCallbacks
    def test_homeProvisioningConcurrency(self):
        """
        Test that two concurrent attempts to provision an addressbook home do
        not cause a race-condition whereby the second commit results in a
        second INSERT that violates a unique constraint. Also verify that,
        whilst the two provisioning attempts are happening and doing various
        lock operations, that we do not block other reads of the table.
        """

        addressbookStore1 = yield buildStore(self, self.notifierFactory)
        addressbookStore2 = yield buildStore(self, self.notifierFactory)
        addressbookStore3 = yield buildStore(self, self.notifierFactory)

        txn1 = addressbookStore1.newTransaction()
        txn2 = addressbookStore2.newTransaction()
        txn3 = addressbookStore3.newTransaction()

        # Provision one home now - we will use this to later verify we can do reads of
        # existing data in the table
        home_uid2 = txn3.homeWithUID(EADDRESSBOOKTYPE, "uid2", create=True)
        self.assertNotEqual(home_uid2, None)
        txn3.commit()

        home_uid1_1 = txn1.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)

        def _defer_home_uid1_2():
            home_uid1_2 = txn2.homeWithUID(EADDRESSBOOKTYPE, "uid1", create=True)
            txn2.commit()
            return home_uid1_2
        d1 = deferToThread(_defer_home_uid1_2)

        def _pause_home_uid1_1():
            time.sleep(1)
            txn1.commit()
        d2 = deferToThread(_pause_home_uid1_1)

        # Verify that we can still get to the existing home - i.e. the lock
        # on the table allows concurrent reads
        txn4 = addressbookStore3.newTransaction()
        home_uid2 = txn4.homeWithUID(EADDRESSBOOKTYPE, "uid2", create=True)
        self.assertNotEqual(home_uid2, None)
        txn4.commit()

        # Now do the concurrent provision attempt
        yield d2
        home_uid1_2 = yield d1

        self.assertNotEqual(home_uid1_1, None)
        self.assertNotEqual(home_uid1_2, None)
