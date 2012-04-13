##
# Copyright (c) 2011-2012 Apple Inc. All rights reserved.
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
Data store commands.
"""

__all__ = [
    "UsageError",
    "UnknownArguments",
    "CommandsBase",
    "Commands",
]

#from twisted.python import log
from twisted.internet.defer import succeed
from twisted.internet.defer import inlineCallbacks, returnValue

from twisted.conch.manhole import ManholeInterpreter

from txdav.common.icommondatastore import NotFoundError

from calendarserver.tools.tables import Table
from calendarserver.tools.shell.vfs import Folder, RootFolder
from calendarserver.tools.shell.directory import findRecords, summarizeRecords, recordInfo


class UsageError(Exception):
    """
    Usage error.
    """


class UnknownArguments(UsageError):
    """
    Unknown arguments.
    """
    def __init__(self, arguments):
        Exception.__init__(self, "Unknown arguments: %s" % (arguments,))
        self.arguments = arguments


class CommandsBase(object):
    def __init__(self, protocol):
        self.protocol = protocol

        self.wd = RootFolder(protocol.service)

    @property
    def terminal(self):
        return self.protocol.terminal

    #
    # Utilities
    #

    def getTarget(self, tokens):
        if tokens:
            return self.wd.locate(tokens.pop(0).split("/"))
        else:
            return succeed(self.wd)

    @inlineCallbacks
    def getTargets(self, tokens):
        """
        For each given C{token}, locate a File to operate on.
        @return: iterable of File objects.
        """
        if tokens:
            result = []
            for token in tokens:
                result.append((yield self.wd.locate(token.split("/"))))
            returnValue(result)
        else:
            returnValue((self.wd,))

    def commands(self, showHidden=False):
        """
        @return: an iterable of C{(name, method)} tuples, where
        C{name} is the name of the command and C{method} is the method
        that implements it.
        """
        for attr in dir(self):
            if attr.startswith("cmd_"):
                m = getattr(self, attr)
                if showHidden or not hasattr(m, "hidden"):
                    yield (attr[4:], m)

    @staticmethod
    def complete(word, items):
        """
        List completions for the given C{word} from the given
        C{items}.

        Completions are the remaining portions of words in C{items}
        that start with C{word}.

        For example, if C{"foobar"} and C{"foo"} are in C{items}, then
        C{""} and C{"bar"} are completions when C{word} C{"foo"}.

        @return: an iterable of completions.
        """
        for item in items:
            if item.startswith(word):
                yield item[len(word):]

    def complete_commands(self, word):
        """
        @return: an iterable of command name completions.
        """
        def complete(showHidden):
            return self.complete(
                word,
                (name for name, method in self.commands(showHidden=showHidden))
            )

        completions = tuple(complete(False))

        # If no completions are found, try hidden commands.
        if not completions:
            completions = complete(True)

        return completions

    @inlineCallbacks
    def complete_files(self, tokens, filter=None):
        """
        @return: an iterable of C{File} path completions.
        """
        if filter is None:
            filter = lambda item: True

        files = (
            entry.toString()
            for entry in (yield self.wd.list())
            if filter(entry)
        )

        if len(tokens) == 0:
            returnValue(files)
        elif len(tokens) == 1:
            returnValue(self.complete(tokens[0], files))
        else:
            returnValue(())


class Commands(CommandsBase):
    """
    Data store commands.
    """

    #
    # Basic CLI tools
    #

    def cmd_exit(self, tokens):
        """
        Exit the shell.

        usage: exit
        """
        if tokens:
            raise UnknownArguments(tokens)

        self.protocol.exit()


    def cmd_help(self, tokens):
        """
        Show help.

        usage: help [command]
        """
        if tokens:
            command = tokens.pop(0)
        else:
            command = None

        if tokens:
            raise UnknownArguments(tokens)

        if command:
            m = getattr(self, "cmd_%s" % (command,), None)
            if m:
                doc = m.__doc__.split("\n")

                # Throw out first and last line if it's empty
                if doc:
                    if not doc[0].strip():
                        doc.pop(0)
                    if not doc[-1].strip():
                        doc.pop()

                if doc:
                    # Get length of indentation
                    i = len(doc[0]) - len(doc[0].lstrip())

                    for line in doc:
                        self.terminal.write(line[i:])
                        self.terminal.nextLine()

                else:
                    self.terminal.write("(No documentation available for %s)\n" % (command,))
            else:
                raise NotFoundError("Unknown command: %s" % (command,))
        else:
            self.terminal.write("Available commands:\n")

            result = []
            max_len = 0

            for name, m in self.commands():
                for line in m.__doc__.split("\n"):
                    line = line.strip()
                    if line:
                        doc = line
                        break
                else:
                    doc = "(no info available)"

                if len(name) > max_len:
                    max_len = len(name)

                result.append((name, doc))

            format = "  %%%ds - %%s\n" % (max_len,)

            for info in sorted(result):
                self.terminal.write(format % (info))

    def complete_help(self, tokens):
        if len(tokens) == 0:
            return (name for name, method in self.commands())
        elif len(tokens) == 1:
            return self.complete_commands(tokens[0])
        else:
            return ()


    def cmd_emulate(self, tokens):
        """
        Emulate editor behavior.
        The only correct argument is: emacs
        Other choices include: none

        usage: emulate editor
        """
        if not tokens:
            if self.protocol.emulate:
                self.terminal.write("Emulating %s.\n" % (self.protocol.emulate,))
            else:
                self.terminal.write("Emulation disabled.\n")
            return

        editor = tokens.pop(0).lower()

        if tokens:
            raise UnknownArguments(tokens)

        if editor == "none":
            self.terminal.write("Disabling emulation.\n")
            editor = None
        elif editor in self.protocol.emulation_modes:
            self.terminal.write("Emulating %s.\n" % (editor,))
        else:
            raise UsageError("Unknown editor: %s" % (editor,))

        self.protocol.emulate = editor

        # FIXME: Need to update key registrations

    cmd_emulate.hidden = "incomplete"

    def complete_emulate(self, tokens):
        if len(tokens) == 0:
            return self.protocol.emulation_modes
        elif len(tokens) == 1:
            return self.complete(tokens[0], self.protocol.emulation_modes)
        else:
            return ()


    def cmd_log(self, tokens):
        """
        Enable logging.

        usage: log [file]
        """
        if hasattr(self, "_logFile"):
            self.terminal.write("Already logging to file: %s\n" % (self._logFile,))
            return

        if tokens:
            fileName = tokens.pop(0)
        else:
            fileName = "/tmp/shell.log"

        if tokens:
            raise UnknownArguments(tokens)

        from twisted.python.log import startLogging
        try:
            f = open(fileName, "w")
        except (IOError, OSError), e:
            self.terminal.write("Unable to open file %s: %s\n" % (fileName, e))
            return

        startLogging(f)

        self._logFile = fileName

    cmd_log.hidden = "debug tool"


    #
    # Filesystem tools
    #

    def cmd_pwd(self, tokens):
        """
        Print working folder.

        usage: pwd
        """
        if tokens:
            raise UnknownArguments(tokens)

        self.terminal.write("%s\n" % (self.wd,))


    @inlineCallbacks
    def cmd_cd(self, tokens):
        """
        Change working folder.

        usage: cd [folder]
        """
        if tokens:
            dirname = tokens.pop(0)
        else:
            return

        if tokens:
            raise UnknownArguments(tokens)

        wd = (yield self.wd.locate(dirname.split("/")))

        if not isinstance(wd, Folder):
            raise NotFoundError("Not a folder: %s" % (wd,))

       #log.msg("wd -> %s" % (wd,))
        self.wd = wd


    @inlineCallbacks
    def complete_cd(self, tokens):
        returnValue((yield self.complete_files(
            tokens,
            filter = lambda item: True #issubclass(item[0], Folder)
        )))


    @inlineCallbacks
    def cmd_ls(self, tokens):
        """
        List folder contents.

        usage: ls [folder]
        """
        targets = (yield self.getTargets(tokens))
        multiple = len(targets) > 0

        for target in targets:
            entries = (yield target.list())
            #
            # FIXME: this can be ugly if, for example, there are zillions
            # of entries to output. Paging would be good.
            #
            table = Table()
            for entry in entries:
                table.addRow(entry.toFields())

            if multiple:
                self.terminal.write("%s:\n" % (target,))
            if table.rows:
                table.printTable(self.terminal)
            self.terminal.nextLine()

    complete_ls = CommandsBase.complete_files


    @inlineCallbacks
    def cmd_info(self, tokens):
        """
        Print information about a folder.

        usage: info [folder]
        """
        target = (yield self.getTarget(tokens))

        if tokens:
            raise UnknownArguments(tokens)

        description = (yield target.describe())
        self.terminal.write(description)
        self.terminal.nextLine()

    complete_info = CommandsBase.complete_files


    @inlineCallbacks
    def cmd_cat(self, tokens):
        """
        Show contents of target.

        usage: cat target [target ...]
        """
        for target in (yield self.getTargets(tokens)):
            if hasattr(target, "text"):
                text = (yield target.text())
                self.terminal.write(text)

    complete_cat = CommandsBase.complete_files


    #
    # Principal tools
    #

    @inlineCallbacks
    def cmd_find_principals(self, tokens):
        """
        Search for matching principals

        usage: find_principal term
        """
        if not tokens:
            raise UsageError("No search term")

        directory = self.protocol.service.directory

        records = (yield findRecords(directory, tokens))

        if records:
            self.terminal.write((yield summarizeRecords(directory, records)))
        else:
            self.terminal.write("No matching principals found.")

        self.terminal.nextLine()


    @inlineCallbacks
    def cmd_print_principal(self, tokens):
        """
        Print information about a principal

        usage: print_principal uid
        """
        if tokens:
            uid = tokens.pop(0)
        else:
            raise UsageError("UID required")

        if tokens:
            raise UnknownArguments(tokens)

        directory = self.protocol.service.directory

        record = directory.recordWithUID(uid)

        if record:
            self.terminal.write((yield recordInfo(directory, record)))
        else:
            self.terminal.write("No such principal.")

        self.terminal.nextLine()


    #
    # Python prompt, for the win
    #

    def cmd_python(self, tokens):
        """
        Switch to a python prompt.

        usage: python
        """
        if tokens:
            raise UnknownArguments(tokens)

        if not hasattr(self, "_interpreter"):
            # Bring in some helpful local variables.
            from txdav.common.datastore.sql_tables import schema
            from twext.enterprise.dal import syntax

            localVariables = dict(
                self   = self,
                store  = self.protocol.service.store,
                schema = schema,
            )

            # FIXME: Use syntax.__all__, which needs to be defined
            for key, value in syntax.__dict__.items():
                if not key.startswith("_"):
                    localVariables[key] = value

            class Handler(object):
                def addOutput(innerSelf, bytes, async=False):
                    """
                    This is a delegate method, called by ManholeInterpreter.
                    """
                    if async:
                        self.terminal.write("... interrupted for Deferred ...\n")
                    self.terminal.write(bytes)
                    if async:
                        self.terminal.write("\n")
                        self.protocol.drawInputLine()

            self._interpreter = ManholeInterpreter(Handler(), localVariables)

        def evalSomePython(line):
            if line == "exit":
                # Return to normal command mode.
                del self.protocol.lineReceived
                del self.protocol.ps
                try:
                    del self.protocol.pn
                except AttributeError:
                    pass
                self.protocol.drawInputLine()
                return

            more = self._interpreter.push(line)
            self.protocol.pn = bool(more)

            lw = self.terminal.lastWrite
            if not (lw.endswith("\n") or lw.endswith("\x1bE")):
                self.terminal.write("\n")
            self.protocol.drawInputLine()

        self.protocol.lineReceived = evalSomePython
        self.protocol.ps = (">>> ", "... ")

    cmd_python.hidden = "debug tool"


    #
    # SQL prompt, for not as winning
    #

    def cmd_sql(self, tokens):
        """
        Switch to an SQL prompt.

        usage: sql
        """
        if tokens:
            raise UnknownArguments(tokens)

        raise NotImplementedError("")

    cmd_sql.hidden = "not implemented"


    #
    # Test tools
    #

    def cmd_raise(self, tokens):
        raise RuntimeError(" ".join(tokens))

    cmd_raise.hidden = "test tool"
