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

from txdav.carddav.datastore.test.common import CommonTests as AddressBookCommonTests

from txdav.common.datastore.test.util import SQLStoreBuilder

from twisted.trial import unittest
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.vcard import Component as VCard


theStoreBuilder = SQLStoreBuilder()
buildStore = theStoreBuilder.buildStore

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

