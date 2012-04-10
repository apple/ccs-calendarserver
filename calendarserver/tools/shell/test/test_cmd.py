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
from calendarserver.tools.shell.terminal import ShellProtocol


class TestCommandsBase(twisted.trial.unittest.TestCase):
    def setUp(self):
        self.protocol = ShellProtocol(None, commandsClass=CommandsBase)
        self.commands = self.protocol.commands

    @inlineCallbacks
    def test_getTargetNone(self):
        target = (yield self.commands.getTarget([]))
        self.assertEquals(target, self.commands.wd)

    def test_getTargetMissing(self):
        self.assertFailure(self.commands.getTarget(["/foo"]), NotFoundError)

    @inlineCallbacks
    def test_getTargetOne(self):
        target = (yield self.commands.getTarget(["users"]))
        match = (yield self.commands.wd.locate(["users"]))
        self.assertEquals(target, match)

    @inlineCallbacks
    def test_getTargetSome(self):
        target = (yield self.commands.getTarget(["users", "blah"]))
        match = (yield self.commands.wd.locate(["users"]))
        self.assertEquals(target, match)

    def test_commandsNone(self):
        allCommands = self.commands.commands()
        self.assertEquals(sorted(allCommands), [])

        allCommands = self.commands.commands(showHidden=True)
        self.assertEquals(sorted(allCommands), [])

    def test_commandsSome(self):
        protocol = ShellProtocol(None, commandsClass=SomeCommands)
        commands = protocol.commands

        allCommands = commands.commands()

        self.assertEquals(
            sorted(allCommands),
            [
                ("a", commands.cmd_a),
                ("b", commands.cmd_b),
            ]
        )

        allCommands = commands.commands(showHidden=True)

        self.assertEquals(
            sorted(allCommands),
            [
                ("a", commands.cmd_a),
                ("b", commands.cmd_b),
                ("hidden", commands.cmd_hidden),
            ]
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

        self.assertEquals(c(""       ), sorted(items))
        self.assertEquals(c("f"      ), ["oo", "oobar"])
        self.assertEquals(c("foo"    ), ["", "bar"])
        self.assertEquals(c("foobar" ), [""])
        self.assertEquals(c("foobars"), [])
        self.assertEquals(c("baz"    ), [""])
        self.assertEquals(c("q"      ), ["uux"])
        self.assertEquals(c("xyzzy"  ), [])

    def test_completeCommands(self):
        protocol = ShellProtocol(None, commandsClass=SomeCommands)
        commands = protocol.commands

        def c(word):
            return sorted(commands.complete_commands(word))

        self.assertEquals(c("" ), ["a", "b"])
        self.assertEquals(c("a"), [""])
        self.assertEquals(c("h"), ["idden"])
        self.assertEquals(c("f"), [])

    def test_completeFiles(self):
        protocol = ShellProtocol(None, commandsClass=SomeCommands)
        commands = protocol.commands

        def c(word):
            return sorted(commands.complete_files(word))

        raise NotImplementedError()

    test_completeFiles.todo = "Not implemented."

    def test_listEntryToString(self):
        raise NotImplementedError()
        self.assertEquals(CommandsBase.listEntryToString(file, "stuff"), "")

    test_listEntryToString.todo = "Not implemented"


class SomeCommands(CommandsBase):
    def cmd_a(self, tokens):
        pass
    def cmd_b(self, tokens):
        pass
    def cmd_hidden(self, tokens):
        pass
    cmd_hidden.hidden = "Hidden"
