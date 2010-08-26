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
Generic property store tests.
"""

__all__ = [
    "PropertyStoreTest",
    "propertyName",
    "propertyValue",
]


from zope.interface.verify import verifyObject, BrokenMethodImplementation

from twisted.trial import unittest

from twext.web2.dav import davxml

from txdav.idav import IPropertyStore
from txdav.base.propertystore.base import PropertyName


class PropertyStoreTest(unittest.TestCase):
    # Subclass must define self.propertyStore in setUp().

    def _preTest(self):
        self.addCleanup(self._postTest)
    def _postTest(self):
        pass
    def _changed(self, store):
        store.flush()
    def _abort(self, store):
        store.abort()

    def test_interface(self):
        try:
            self._preTest()
            verifyObject(IPropertyStore, self.propertyStore)
        except BrokenMethodImplementation, e:
            self.fail(e)

    def test_set_get_contains(self):
        
        self._preTest()
        store = self.propertyStore

        name = propertyName("test")
        value = propertyValue("Hello, World!")

        # Test with commit after change
        store[name] = value
        self._changed(store)
        self.assertEquals(store.get(name, None), value)
        self.failUnless(name in store)

        # Test without commit after change
        value = propertyValue("Hello, Universe!")
        store[name] = value
        self.assertEquals(store.get(name, None), value)
        self.failUnless(name in store)

    def test_delete_get_contains(self):

        self._preTest()
        store = self.propertyStore

        # Test with commit after change
        name = propertyName("test")
        value = propertyValue("Hello, World!")

        store[name] = value
        self._changed(store)

        del store[name]
        self._changed(store)

        self.assertEquals(store.get(name, None), None)
        self.failIf(name in store)

        # Test without commit after change
        name = propertyName("test")
        value = propertyValue("Hello, Universe!")

        store[name] = value
        self._changed(store)

        del store[name]

        self.assertEquals(store.get(name, None), None)
        self.failIf(name in store)

    def test_peruser(self):

        self._preTest()
        store1 = self.propertyStore1
        store2 = self.propertyStore2

        name = propertyName("test")
        value1 = propertyValue("Hello, World1!")
        value2 = propertyValue("Hello, World2!")

        store1[name] = value1
        self._changed(store1)
        self.assertEquals(store1.get(name, None), value1)
        self.assertEquals(store2.get(name, None), None)
        self.failUnless(name in store1)
        self.failIf(name in store2)
        
        store2[name] = value2
        self._changed(store2)
        self.assertEquals(store1.get(name, None), value1)
        self.assertEquals(store2.get(name, None), value2)
        self.failUnless(name in store1)
        self.failUnless(name in store2)
        
        del store2[name]
        self._changed(store2)
        self.assertEquals(store1.get(name, None), value1)
        self.assertEquals(store2.get(name, None), None)
        self.failUnless(name in store1)
        self.failIf(name in store2)
        
        del store1[name]
        self._changed(store1)
        self.assertEquals(store1.get(name, None), None)
        self.assertEquals(store2.get(name, None), None)
        self.failIf(name in store1)
        self.failIf(name in store2)
        
    def test_peruser_shadow(self):

        self._preTest()
        store1 = self.propertyStore1
        store2 = self.propertyStore2

        name = propertyName("shadow")

        store1.setSpecialProperties((name,), ())
        store2.setSpecialProperties((name,), ())

        value1 = propertyValue("Hello, World1!")
        value2 = propertyValue("Hello, World2!")

        store1[name] = value1
        self._changed(store1)
        self.assertEquals(store1.get(name, None), value1)
        self.assertEquals(store2.get(name, None), value1)
        self.failUnless(name in store1)
        self.failUnless(name in store2)
        
        store2[name] = value2
        self._changed(store2)
        self.assertEquals(store1.get(name, None), value1)
        self.assertEquals(store2.get(name, None), value2)
        self.failUnless(name in store1)
        self.failUnless(name in store2)
        
        del store2[name]
        self._changed(store2)
        self.assertEquals(store1.get(name, None), value1)
        self.assertEquals(store2.get(name, None), value1)
        self.failUnless(name in store1)
        self.failUnless(name in store2)
        
        del store1[name]
        self._changed(store1)
        self.assertEquals(store1.get(name, None), None)
        self.assertEquals(store2.get(name, None), None)
        self.failIf(name in store1)
        self.failIf(name in store2)


    def test_peruser_global(self):

        self._preTest()
        store1 = self.propertyStore1
        store2 = self.propertyStore2

        name = propertyName("global")

        store1.setSpecialProperties((), (name,))
        store2.setSpecialProperties((), (name,))

        value1 = propertyValue("Hello, World1!")
        value2 = propertyValue("Hello, World2!")

        store1[name] = value1
        self._changed(store1)
        self.assertEquals(store1.get(name, None), value1)
        self.assertEquals(store2.get(name, None), value1)
        self.failUnless(name in store1)
        self.failUnless(name in store2)
        
        store2[name] = value2
        self._changed(store2)
        self.assertEquals(store1.get(name, None), value2)
        self.assertEquals(store2.get(name, None), value2)
        self.failUnless(name in store1)
        self.failUnless(name in store2)
        
        del store2[name]
        self._changed(store2)
        self.assertEquals(store1.get(name, None), None)
        self.assertEquals(store2.get(name, None), None)
        self.failIf(name in store1)
        self.failIf(name in store2)
        

    def test_iteration(self):

        self._preTest()
        store = self.propertyStore

        value = propertyValue("Hello, World!")

        names = set(propertyName(str(i)) for i in (1,2,3,4))

        for name in names:
            store[name] = value

        self.assertEquals(set(store.keys()), names)
        self.assertEquals(len(store), len(names))

    def test_delete_none(self):

        self._preTest()
        def doDelete():
            del self.propertyStore[propertyName("xyzzy")]

        self.assertRaises(KeyError, doDelete)

    def test_keyInPropertyName(self):

        self._preTest()
        store = self.propertyStore

        def doGet():
            store["xyzzy"]

        def doSet():
            store["xyzzy"] = propertyValue("Hello, World!")

        def doDelete():
            del store["xyzzy"]

        def doContains():
            return "xyzzy" in store

        self.assertRaises(TypeError, doGet)
        self.assertRaises(TypeError, doSet)
        self.assertRaises(TypeError, doDelete)
        self.assertRaises(TypeError, doContains)

    def test_flush(self):

        self._preTest()
        store = self.propertyStore

        name = propertyName("test")
        value = propertyValue("Hello, World!")

        #
        # Set value flushes correctly
        #
        store[name] = value

        self._changed(store)
        self._abort(store)

        self.assertEquals(store.get(name, None), value)
        self.assertEquals(len(store), 1)

        #
        # Deleted value flushes correctly
        #
        del store[name]

        self._changed(store)
        self._abort(store)

        self.assertEquals(store.get(name, None), None)
        self.assertEquals(len(store), 0)

    def test_abort(self):

        self._preTest()
        store = self.propertyStore

        name = propertyName("test")
        value = propertyValue("Hello, World!")

        store[name] = value

        self._abort(store)

        self.assertEquals(store.get(name, None), None)
        self.assertEquals(len(store), 0)


def propertyName(name):
    return PropertyName("http://calendarserver.org/ns/test/", name)

def propertyValue(value):
    return davxml.ResponseDescription(value)
