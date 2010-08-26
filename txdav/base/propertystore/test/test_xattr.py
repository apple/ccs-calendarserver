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
from twext.web2.dav.element.base import WebDAVTextElement

"""
Property store tests.
"""

from twext.python.filepath import CachingFilePath as FilePath

from txdav.base.propertystore.base import PropertyName

from txdav.base.propertystore.test import base

try:
    from txdav.base.propertystore.xattr import PropertyStore
    from xattr import xattr
except ImportError, e:
    PropertyStore = None
    importErrorMessage = str(e)


class PropertyStoreTest(base.PropertyStoreTest):
    def setUp(self):
        tempDir = FilePath(self.mktemp())
        tempDir.makedirs()
        tempFile = tempDir.child("test")
        tempFile.touch()
        self.propertyStore = self.propertyStore1 = PropertyStore(
            "user01", lambda : tempFile
        )
        self.propertyStore2 = PropertyStore("user01", lambda : tempFile)
        self.propertyStore2._setPerUserUID("user02")

    def test_init(self):
        store = self.propertyStore
        self.failUnless(isinstance(store.attrs, xattr))
        self.assertEquals(store.removed, set())
        self.assertEquals(store.modified, {})

    def test_abort(self):
        super(PropertyStoreTest, self).test_abort()
        store = self.propertyStore
        self.assertEquals(store.removed, set())
        self.assertEquals(store.modified, {})

    def test_compress(self):

        class DummyProperty (WebDAVTextElement):
            namespace = "http://calendarserver.org/ns/"
            name = "dummy"

        name = PropertyName.fromElement(DummyProperty)
        compressedKey = self.propertyStore._encodeKey((name, self.propertyStore._defaultuser))
        uncompressedKey = self.propertyStore._encodeKey((name, self.propertyStore._defaultuser), compressNamespace=False)

        self.propertyStore[name] = DummyProperty.fromString("data")
        self.propertyStore.flush()
        self.assertEqual(self.propertyStore[name], DummyProperty.fromString("data"))
        self.assertTrue(compressedKey in self.propertyStore.attrs)
        self.assertFalse(uncompressedKey in self.propertyStore.attrs)

    def test_compress_upgrade(self):

        class DummyProperty (WebDAVTextElement):
            namespace = "http://calendarserver.org/ns/"
            name = "dummy"

        name = PropertyName.fromElement(DummyProperty)
        uncompressedKey = self.propertyStore._encodeKey((name, self.propertyStore._defaultuser), compressNamespace=False)
        self.propertyStore.attrs[uncompressedKey] = DummyProperty.fromString("data").toxml()
        self.assertEqual(self.propertyStore[name], DummyProperty.fromString("data"))
        self.assertRaises(KeyError, lambda:self.propertyStore.attrs[uncompressedKey])

if PropertyStore is None:
    PropertyStoreTest.skip = importErrorMessage


def propertyName(name):
    return PropertyName("http://calendarserver.org/ns/test/", name)
