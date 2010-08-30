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

from twisted.internet.defer import inlineCallbacks

from txdav.caldav.datastore.test.common import StubNotifierFactory

from txdav.common.datastore.test.util import buildStore

from txdav.base.propertystore.base import PropertyName
from txdav.base.propertystore.test import base

try:
    from txdav.base.propertystore.sql import PropertyStore
except ImportError, e:
    PropertyStore = None
    importErrorMessage = str(e)



class PropertyStoreTest(base.PropertyStoreTest):

    def _preTest(self):
        self._txn = self.store.newTransaction()
        self.propertyStore = self.propertyStore1 = PropertyStore(
            "user01", self._txn, 1
        )
        self.propertyStore2 = PropertyStore("user01", self._txn, 1)
        self.propertyStore2._setPerUserUID("user02")
        
        self.addCleanup(self._postTest)

    def _postTest(self):
        if hasattr(self, "_txn"):
            self._txn.commit()
            delattr(self, "_txn")
        self.propertyStore = self.propertyStore1 = self.propertyStore2 = None

    def _changed(self, store):
        if hasattr(self, "_txn"):
            self._txn.commit()
            delattr(self, "_txn")
        self._txn = self.store.newTransaction()
        self.propertyStore1._txn = self._txn
        self.propertyStore2._txn = self._txn

    def _abort(self, store):
        if hasattr(self, "_txn"):
            self._txn.abort()
            delattr(self, "_txn")

        self._txn = self.store.newTransaction()
        self.propertyStore1._txn = self._txn
        self.propertyStore2._txn = self._txn

    @inlineCallbacks
    def setUp(self):
        self.notifierFactory = StubNotifierFactory()
        self.store = yield buildStore(self, self.notifierFactory)

if PropertyStore is None:
    PropertyStoreTest.skip = importErrorMessage


def propertyName(name):
    return PropertyName("http://calendarserver.org/ns/test/", name)
