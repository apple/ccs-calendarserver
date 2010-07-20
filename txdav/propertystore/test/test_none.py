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
Property store tests.
"""

from txdav.propertystore.none import PropertyStore

from txdav.propertystore.test import base

class PropertyStoreTest(base.PropertyStoreTest):
    def setUp(self):
        self.propertyStore = self.propertyStore1 = PropertyStore("user01", "user01")
        self.propertyStore2 = PropertyStore("user02", "user01")

    def test_abort(self):
        super(PropertyStoreTest, self).test_abort()
        store = self.propertyStore
        self.assertEquals(store.removed, set())
        self.assertEquals(store.modified, {})
