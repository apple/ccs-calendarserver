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

# from twext.python.filepath import FilePath

# from txdav.propertystore.base import PropertyName
# from txdav.propertystore.test.base import propertyName

# from txdav.propertystore.test import base

# try:
#     from txdav.propertystore.xattr import PropertyStore
#     from xattr import xattr
# except ImportError, e:
#     PropertyStore = None
#     importErrorMessage = str(e)


# class PropertyStoreTest(base.PropertyStoreTest):
#     def setUp(self):
#         tempDir = FilePath(self.mktemp())
#         tempDir.makedirs()
#         tempFile = tempDir.child("test")
#         tempFile.touch()
#         self.propertyStore = PropertyStore(tempFile)

#     def test_init(self):
#         store = self.propertyStore
#         self.failUnless(isinstance(store.attrs, xattr))
#         self.assertEquals(store.removed, set())
#         self.assertEquals(store.modified, {})

#     def test_abort(self):
#         super(PropertyStoreTest, self).test_abort()
#         store = self.propertyStore
#         self.assertEquals(store.removed, set())
#         self.assertEquals(store.modified, {})


# if PropertyStore is None:
#     PropertyStoreTest.skip = importErrorMessage

# def propertyName(name):
#     return PropertyName("http://calendarserver.org/ns/test/", name)
