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
from twisted.internet.defer import inlineCallbacks

from txdav.common.icommondatastore import NotFoundError

from calendarserver.tools.shell.cmd import CommandsBase
from calendarserver.tools.shell.vfs import RootFolder


class TestCommandsBase(twisted.trial.unittest.TestCase):

    @inlineCallbacks
    def test_getTargetNone(self):
        cmd = CommandsBase(RootFolder(None))
        target = (yield cmd.getTarget([]))
        self.assertEquals(target, cmd.wd)

    def test_getTargetMissing(self):
        cmd = CommandsBase(RootFolder(None))
        self.assertFailure(cmd.getTarget(["/foo"]), NotFoundError)

    @inlineCallbacks
    def test_getTargetOne(self):
        cmd = CommandsBase(RootFolder(None))
        target = (yield cmd.getTarget(["users"]))
        match = (yield cmd.wd.locate(["users"]))
        self.assertEquals(target, match)

    @inlineCallbacks
    def test_getTargetSome(self):
        cmd = CommandsBase(RootFolder(None))
        target = (yield cmd.getTarget(["users", "blah"]))
        match = (yield cmd.wd.locate(["users"]))
        self.assertEquals(target, match)

    def test_commandsNone(self):
        cmd = CommandsBase(RootFolder(None))
        commands = cmd.commands()

        self.assertEquals(sorted(commands), [])

    def test_commandsSome(self):
        class SomeCommands(CommandsBase):
            def cmd_a(self, tokens):
                pass
            def cmd_b(self, tokens):
                pass
            def cmd_hidden(self, tokens):
                pass
            cmd_hidden.hidden = "Hidden"

        cmd = SomeCommands(RootFolder(None))
        commands = cmd.commands()

        self.assertEquals(
            sorted(commands),
            [ ("a", cmd.cmd_a), ("b", cmd.cmd_b) ]
        )

    def test_complete(self):
        items = (
            "foo",
            "bar",
            "foobar",
            "baz",
            "quux",
        )

        def c(word):
            return sorted(CommandsBase.complete(word, items))

        self.assertEquals(c("f"      ), ["oo", "oobar"])
        self.assertEquals(c("foo"    ), ["", "bar"])
        self.assertEquals(c("foobar" ), [""])
        self.assertEquals(c("foobars"), [])
        self.assertEquals(c("baz"    ), [""])
        self.assertEquals(c("q"      ), ["uux"])
        self.assertEquals(c("xyzzy"  ), [])
