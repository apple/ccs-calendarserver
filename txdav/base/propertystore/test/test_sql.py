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

from twisted.internet.defer import inlineCallbacks, returnValue

from txdav.common.datastore.test.util import buildStore, StubNotifierFactory

from txdav.base.propertystore.base import PropertyName
from txdav.base.propertystore.test import base

from twistedcaldav import memcacher
from twistedcaldav.config import config

try:
    from txdav.base.propertystore.sql import PropertyStore
except ImportError, e:
    PropertyStore = None
    importErrorMessage = str(e)



class PropertyStoreTest(base.PropertyStoreTest):


    @inlineCallbacks
    def setUp(self):
        self.patch(config.Memcached.Pools.Default, "ClientEnabled", False)
        self.patch(config.Memcached.Pools.Default, "ServerEnabled", False)
        self.patch(memcacher.Memcacher, "allowTestCache", True)

        self.notifierFactory = StubNotifierFactory()
        self.store = yield buildStore(self, self.notifierFactory)
        self.addCleanup(self.maybeCommitLast)
        self._txn = self.store.newTransaction()
        self.propertyStore = self.propertyStore1 = yield PropertyStore.load(
            "user01", self._txn, 1
        )
        self.propertyStore2 = yield PropertyStore.load("user01", self._txn, 1)
        self.propertyStore2._setPerUserUID("user02")


    @inlineCallbacks
    def maybeCommitLast(self):
        if hasattr(self, "_txn"):
            result = yield self._txn.commit()
            delattr(self, "_txn")
        else:
            result = None
        self.propertyStore = self.propertyStore1 = self.propertyStore2 = None
        returnValue(result)


    @inlineCallbacks
    def _changed(self, store):
        if hasattr(self, "_txn"):
            yield self._txn.commit()
            delattr(self, "_txn")
        self._txn = self.store.newTransaction()

        store = self.propertyStore1
        self.propertyStore = self.propertyStore1 = yield PropertyStore.load(
            "user01", self._txn, 1
        )
        self.propertyStore1._shadowableKeys = store._shadowableKeys
        self.propertyStore1._globalKeys = store._globalKeys

        store = self.propertyStore2
        self.propertyStore2 = yield PropertyStore.load("user01", self._txn, 1)
        self.propertyStore2._setPerUserUID("user02")
        self.propertyStore2._shadowableKeys = store._shadowableKeys
        self.propertyStore2._globalKeys = store._globalKeys


    @inlineCallbacks
    def _abort(self, store):
        if hasattr(self, "_txn"):
            yield self._txn.abort()
            delattr(self, "_txn")

        self._txn = self.store.newTransaction()

        store = self.propertyStore1
        self.propertyStore = self.propertyStore1 = yield PropertyStore.load(
            "user01", self._txn, 1
        )
        self.propertyStore1._shadowableKeys = store._shadowableKeys
        self.propertyStore1._globalKeys = store._globalKeys

        store = self.propertyStore2
        self.propertyStore2 = yield PropertyStore.load("user01", self._txn, 1)
        self.propertyStore2._setPerUserUID("user02")
        self.propertyStore2._shadowableKeys = store._shadowableKeys
        self.propertyStore2._globalKeys = store._globalKeys



if PropertyStore is None:
    PropertyStoreTest.skip = importErrorMessage


def propertyName(name):
    return PropertyName("http://calendarserver.org/ns/test/", name)
