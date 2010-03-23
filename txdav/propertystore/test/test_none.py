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

# from txdav.idav import PropertyChangeNotAllowedError
# from txdav.propertystore.none import PropertyStore
# from txdav.propertystore.test.base import propertyName, propertyValue

# from txdav.propertystore.test import base


# class PropertyStoreTest(base.PropertyStoreTest):
#     def setUp(self):
#         self.propertyStore = PropertyStore()

#     def test_flush(self):
#         store = self.propertyStore

#         # Flushing no changes is ok
#         store.flush()

#         name = propertyName("test")
#         value = propertyValue("Hello, World!")

#         store[name] = value

#         # Flushing changes isn't allowed
#         self.assertRaises(PropertyChangeNotAllowedError, store.flush)

#         # Changes are still here
#         self.assertEquals(store.get(name, None), value)

#         # Flushing no changes is ok
#         del store[name]
#         store.flush()

#         self.assertEquals(store.get(name, None), None)

#     def test_abort(self):
#         super(PropertyStoreTest, self).test_abort()
#         self.assertEquals(self.propertyStore.modified, {})
