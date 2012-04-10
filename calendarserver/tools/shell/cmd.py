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

#from twisted.python import log
from twisted.internet.defer import succeed
from twisted.internet.defer import inlineCallbacks, returnValue

from twisted.conch.manhole import ManholeInterpreter

from txdav.common.icommondatastore import NotFoundError

from calendarserver.tools.tables import Table
from calendarserver.tools.shell.vfs import Folder

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
    def __init__(self, wd):
        self.wd = wd

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
        if tokens:
            result = []
            for token in tokens:
                result.append((yield self.wd.locate(token.split("/"))))
            returnValue(result)
        else:
            returnValue((self.wd,))

    def commands(self):
        for attr in dir(self):
            if attr.startswith("cmd_"):
                m = getattr(self, attr)
                if not hasattr(m, "hidden"):
                    yield (attr[4:], m)

    @staticmethod
    def complete(word, items):
        for item in items:
            if item.startswith(word):
                yield item[len(word):]

    def complete_commands(self, word):
        return self.complete(word, (name for name, method in self.commands()))

    @inlineCallbacks
    def complete_files(self, tokens, filter=None):
        if filter is None:
            filter = lambda items: True

        files = (
            self.listEntryToString(item)
            for item in (yield self.wd.list())
            if filter(item)
        )

        if len(tokens) == 0:
            returnValue(files)
        elif len(tokens) == 1:
            returnValue(self.complete(tokens[0], files))
        else:
            returnValue(())

    @staticmethod
    def listEntryToString(entry):
        klass = entry[0]
        name  = entry[1]

        if issubclass(klass, Folder):
            return "%s/" % (name,)
        else:
            return name


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

        self.exit()


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
            if self.emulate:
                self.terminal.write("Emulating %s.\n" % (self.emulate,))
            else:
                self.terminal.write("Emulation disabled.\n")
            return

        editor = tokens.pop(0).lower()

        if tokens:
            raise UnknownArguments(tokens)

        if editor == "none":
            self.terminal.write("Disabling emulation.\n")
            editor = None
        elif editor in self.emulation_modes:
            self.terminal.write("Emulating %s.\n" % (editor,))
        else:
            raise UsageError("Unknown editor: %s" % (editor,))

        self.emulate = editor

        # FIXME: Need to update key registrations

    cmd_emulate.hidden = "Incomplete"

    def complete_emulate(self, tokens):
        if len(tokens) == 0:
            return self.emulation_modes
        elif len(tokens) == 1:
            return self.complete(tokens[0], self.emulation_modes)
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

    cmd_log.hidden = "Debug tool"


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
        if not tokens:
            return

        dirname = tokens.pop(0)

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
            filter = lambda item: issubclass(item[0], Folder)
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
            rows = (yield target.list())
            #
            # FIXME: this can be ugly if, for example, there are zillions
            # of entries to output. Paging would be good.
            #
            table = Table()
            for row in rows:
                table.addRow((self.listEntryToString(row),) + tuple(row[2:]))

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
                store  = self.service.store,
                schema = schema,
            )

            # FIXME: Use syntax.__all__, which needs to be defined
            for key, value in syntax.__dict__.items():
                if not key.startswith("_"):
                    localVariables[key] = value

            self._interpreter = ManholeInterpreter(self, localVariables)

        def evalSomePython(line):
            if line == "exit":
                # Return to normal command mode.
                del self.lineReceived
                del self.ps
                del self.pn
                self.drawInputLine()
                return

            more = self._interpreter.push(line)
            self.pn = bool(more)
            lw = self.terminal.lastWrite
            if not (lw.endswith("\n") or lw.endswith("\x1bE")):
                self.terminal.write("\n")
            self.drawInputLine()

        self.lineReceived = evalSomePython
        self.ps = (">>> ", "... ")

    cmd_python.hidden = "Still experimental / untested."


    def addOutput(self, bytes, async=False):
        """
        This is a delegate method, called by ManholeInterpreter.
        """
        if async:
            self.terminal.write("... interrupted for Deferred ...\n")
        self.terminal.write(bytes)
        if async:
            self.terminal.write("\n")
            self.drawInputLine()


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

    cmd_sql.hidden = "Not implemented."
