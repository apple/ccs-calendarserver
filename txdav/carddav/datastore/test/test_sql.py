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
        self.addressbookStore = yield buildStore(self, self.notifierFactory)
        self.populate()

    def populate(self):
        populateTxn = self.addressbookStore.newTransaction()
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
        return self.addressbookStore


    @inlineCallbacks
    def test_homeProvisioningConcurrency(self):

        addressbookStore1 = yield buildStore(self, self.notifierFactory)
        addressbookStore2 = yield buildStore(self, self.notifierFactory)
        addressbookStore3 = yield buildStore(self, self.notifierFactory)

        txn1 = addressbookStore1.newTransaction()
        txn2 = addressbookStore2.newTransaction()
        txn3 = addressbookStore3.newTransaction()
        
        # Provision one home now
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
