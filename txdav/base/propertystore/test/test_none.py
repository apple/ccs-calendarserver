##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
Property store tests.
"""

from txdav.idav import PropertyChangeNotAllowedError
from txdav.base.propertystore.none import PropertyStore
from txdav.base.propertystore.test.base import propertyName, propertyValue

from txdav.base.propertystore.test import base


class PropertyStoreTest(base.NonePropertyStoreTest):
    def setUp(self):
        self.propertyStore = PropertyStore("user01")

    def test_set(self):
        def doSet():
            self.propertyStore[propertyName("foo")] = propertyValue("bar")
        self.assertRaises(PropertyChangeNotAllowedError, doSet)

    def test_get(self):
        self.assertRaises(KeyError, lambda: self.propertyStore[propertyName("foo")])

    def test_len(self):
        self.assertEquals(len(self.propertyStore), 0)

    def test_keys(self):
        self.assertEquals(self.propertyStore.keys(), ())

    def test_flush(self):
        self.propertyStore.flush()

    def test_abort(self):
        self.propertyStore.abort()
