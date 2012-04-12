#!/usr/bin/env python
##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

import twisted.trial.unittest 
from twisted.internet.defer import succeed

from calendarserver.tools.shell.vfs import ListEntry
from calendarserver.tools.shell.vfs import File, Folder


class TestListEntry(twisted.trial.unittest.TestCase):
    def test_toString(self):
        self.assertEquals(ListEntry(File  , "thingo"           ).toString(), "thingo" )
        self.assertEquals(ListEntry(File  , "thingo", Foo="foo").toString(), "thingo" )
        self.assertEquals(ListEntry(Folder, "thingo"           ).toString(), "thingo/")
        self.assertEquals(ListEntry(Folder, "thingo", Foo="foo").toString(), "thingo/")

    def test_fieldNamesImplicit(self):
        # This test assumes File doesn't set list.fieldNames.
        assert not hasattr(File.list, "fieldNames")

        self.assertEquals(set(ListEntry(File, "thingo").fieldNames), set(("Name",)))

    def test_fieldNamesExplicit(self):
        def fieldNames(fileClass):
            return ListEntry(fileClass, "thingo", Flavor="Coconut", Style="Hard")

        # Full list
        class MyFile(File):
            def list(self): return succeed(())
            list.fieldNames = ("Name", "Flavor")
        self.assertEquals(fieldNames(MyFile).fieldNames, ("Name", "Flavor"))

        # Full list, different order
        class MyFile(File):
            def list(self): return succeed(())
            list.fieldNames = ("Flavor", "Name")
        self.assertEquals(fieldNames(MyFile).fieldNames, ("Flavor", "Name"))

        # Omits Name, which is implicitly added
        class MyFile(File):
            def list(self): return succeed(())
            list.fieldNames = ("Flavor",)
        self.assertEquals(fieldNames(MyFile).fieldNames, ("Name", "Flavor"))

        # Emtpy
        class MyFile(File):
            def list(self): return succeed(())
            list.fieldNames = ()
        self.assertEquals(fieldNames(MyFile).fieldNames, ("Name",))

    def test_toFieldsImplicit(self):
        # This test assumes File doesn't set list.fieldNames.
        assert not hasattr(File.list, "fieldNames")

        # Name first, rest sorted by field name
        self.assertEquals(
            tuple(ListEntry(File, "thingo", Flavor="Coconut", Style="Hard").toFields()),
            ("thingo", "Coconut", "Hard")
        )

    def test_toFieldsExplicit(self):
        def fields(fileClass):
            return tuple(ListEntry(fileClass, "thingo", Flavor="Coconut", Style="Hard").toFields())

        # Full list
        class MyFile(File):
            def list(self): return succeed(())
            list.fieldNames = ("Name", "Flavor")
        self.assertEquals(fields(MyFile), ("thingo", "Coconut"))

        # Full list, different order
        class MyFile(File):
            def list(self): return succeed(())
            list.fieldNames = ("Flavor", "Name")
        self.assertEquals(fields(MyFile), ("Coconut", "thingo"))

        # Omits Name, which is implicitly added
        class MyFile(File):
            def list(self): return succeed(())
            list.fieldNames = ("Flavor",)
        self.assertEquals(fields(MyFile), ("thingo", "Coconut"))

        # Emtpy
        class MyFile(File):
            def list(self): return succeed(())
            list.fieldNames = ()
        self.assertEquals(fields(MyFile), ("thingo",))
