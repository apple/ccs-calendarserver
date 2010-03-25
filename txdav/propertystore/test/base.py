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
from txdav.propertystore.base import PropertyName


class PropertyStoreTest(unittest.TestCase):
    # Subclass must define self.propertyStore in setUp().

    def test_interface(self):
        try:
            verifyObject(IPropertyStore, self.propertyStore)
        except BrokenMethodImplementation, e:
            self.fail(e)

    def test_set_get_contains(self):
        store = self.propertyStore

        name = propertyName("test")
        value = propertyValue("Hello, World!")

        store[name] = value
        self.assertEquals(store.get(name, None), value)
        self.failUnless(name in store)

    def test_delete_get_contains(self):
        store = self.propertyStore

        name = propertyName("test")
        value = propertyValue("Hello, World!")

        store[name] = value
        del store[name]
        self.assertEquals(store.get(name, None), None)
        self.failIf(name in store)

    def test_iteration(self):
        store = self.propertyStore

        value = propertyValue("Hello, World!")

        names = set(propertyName(str(i)) for i in (1,2,3,4))

        for name in names:
            store[name] = value

        self.assertEquals(set(store.keys()), names)
        self.assertEquals(len(store), len(names))

        # FIXME: Not done here



    def test_flush(self):
        store = self.propertyStore

        name = propertyName("test")
        value = propertyValue("Hello, World!")

        #
        # Set value flushes correctly
        #
        store[name] = value

        store.flush()
        store.abort()

        self.assertEquals(store.get(name, None), value)
        self.assertEquals(len(store), 1)

        #
        # Deleted value flushes correctly
        #
        del store[name]

        store.flush()
        store.abort()

        self.assertEquals(store.get(name, None), None)
        self.assertEquals(len(store), 0)

    def test_abort(self):
        store = self.propertyStore

        name = propertyName("test")
        value = propertyValue("Hello, World!")

        store[name] = value

        store.abort()

        self.assertEquals(store.get(name, None), None)
        self.assertEquals(len(store), 0)


def propertyName(name):
    return PropertyName("http://calendarserver.org/ns/test/", name)

def propertyValue(value):
    return davxml.ResponseDescription(value)
