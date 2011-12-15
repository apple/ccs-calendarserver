#!/usr/bin/env python
##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
Interactive shell for navigating the data store.
"""

import string
import os
import sys
import tty
import termios
from shlex import shlex
from cStringIO import StringIO

from twisted.python import log
from twisted.python.log import startLogging
from twisted.python.text import wordWrap
from twisted.python.usage import Options, UsageError
from twisted.internet.defer import succeed, Deferred
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.stdio import StandardIO
from twisted.conch.recvline import HistoricRecvLine as ReceiveLineProtocol
from twisted.conch.insults.insults import ServerProtocol
from twisted.application.service import Service

from txdav.common.icommondatastore import NotFoundError

from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE

from calendarserver.tools.cmdline import utilityMain
from calendarserver.tools.util import getDirectory
from calendarserver.tools.tables import Table


def usage(e=None):
    if e:
        print e
        print ""
    try:
        ShellOptions().opt_help()
    except SystemExit:
        pass
    if e:
        sys.exit(64)
    else:
        sys.exit(0)


class ShellOptions(Options):
    """
    Command line options for "calendarserver_shell".
    """
    synopsis = "\n".join(
        wordWrap(
            """
            Usage: calendarserver_shell [options]\n
            """ + __doc__,
            int(os.environ.get("COLUMNS", "80"))
        )
    )

    optParameters = [
        ["config", "f", DEFAULT_CONFIG_FILE, "Specify caldavd.plist configuration path."],
    ]

    def __init__(self):
        super(ShellOptions, self).__init__()


class ShellService(Service, object):
    def __init__(self, store, directory, options, reactor, config):
        super(ShellService, self).__init__()
        self.store      = store
        self.directory  = directory
        self.options    = options
        self.reactor    = reactor
        self.config     = config
        self.terminalFD = None
        self.protocol   = None

    def startService(self):
        """
        Start the service.
        """
        # For debugging
        f = open("/tmp/shell.log", "w")
        startLogging(f)

        super(ShellService, self).startService()

        # Set up the terminal for interactive action
        self.terminalFD = sys.__stdin__.fileno()
        self._oldTerminalSettings = termios.tcgetattr(self.terminalFD)
        tty.setraw(self.terminalFD)

        self.protocol = ServerProtocol(lambda: ShellProtocol(self))
        StandardIO(self.protocol)

    def stopService(self):
        """
        Stop the service.
        """
        # Restore terminal settings
        termios.tcsetattr(self.terminalFD, termios.TCSANOW, self._oldTerminalSettings)
        os.write(self.terminalFD, "\r\x1bc\r")


class UsageError (Exception):
    """
    Usage error.
    """

class UnknownArguments (UsageError):
    """
    Unknown arguments.
    """
    def __init__(self, arguments):
        Exception.__init__(self, "Unknown arguments: %s" % (arguments,))
        self.arguments = arguments


EMULATE_EMACS = object()
EMULATE_VI    = object()

class ShellProtocol(ReceiveLineProtocol):
    """
    Data store shell protocol.
    """

    # FIXME:
    # * Received lines are being echoed; find out why and stop it.
    # * Backspace transposes characters in the terminal.

    ps = ("ds% ", "... ")

    def __init__(self, service):
        ReceiveLineProtocol.__init__(self)
        self.service = service
        self.wd = RootFolder(service)
        self.inputLines = []
        self.activeCommand = None
        self.emulate = EMULATE_EMACS

    def connectionMade(self):
        ReceiveLineProtocol.connectionMade(self)

        self.keyHandlers['\x03'] = self.handle_INT   # Control-C
        self.keyHandlers['\x04'] = self.handle_EOF   # Control-D
        self.keyHandlers['\x1c'] = self.handle_QUIT  # Control-\
        self.keyHandlers['\x0c'] = self.handle_FF    # Control-L
       #self.keyHandlers['\t'  ] = self.handle_TAB   # Tab

        if self.emulate == EMULATE_EMACS:
            # EMACS key bindinds
            self.keyHandlers['\x10'] = self.handle_UP     # Control-P
            self.keyHandlers['\x0e'] = self.handle_DOWN   # Control-N
            self.keyHandlers['\x02'] = self.handle_LEFT   # Control-B
            self.keyHandlers['\x06'] = self.handle_RIGHT  # Control-F
            self.keyHandlers['\x01'] = self.handle_HOME   # Control-A
            self.keyHandlers['\x05'] = self.handle_END    # Control-E

    def handle_INT(self):
        """
        Handle ^C as an interrupt keystroke by resetting the current input
        variables to their initial state.
        """
        self.pn = 0
        self.lineBuffer = []
        self.lineBufferIndex = 0

        self.terminal.nextLine()
        self.terminal.write("KeyboardInterrupt")
        self.terminal.nextLine()
        self.exit()

    def handle_EOF(self):
        if self.lineBuffer:
            if self.emulate == EMULATE_EMACS:
                self.handle_DELETE()
            else:
                self.terminal.write('\a')
        else:
            self.handle_QUIT()

    def handle_FF(self):
        """
        Handle a 'form feed' byte - generally used to request a screen
        refresh/redraw.
        """
        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.drawInputLine()

    def handle_QUIT(self):
        self.exit()

    def handle_TAB(self):
        # Tokenize the text before the cursor
        tokens = self.tokenize("".join(self.lineBuffer[:self.lineBufferIndex]))

        if tokens:
            if len(tokens) == 1 and self.lineBuffer[-1] in string.whitespace:
                word = ""
            else:
                word = tokens[-1]
            cmd  = tokens.pop(0)
        else:
            word = cmd = ""

        if cmd and (tokens or word == ""):
            # Completing arguments

            m = getattr(self, "complete_%s" % (cmd,), None)
            if not m:
                return
            completions = tuple(m(tokens))

            log.msg("COMPLETIONS: %r" % (completions,))
        else:
            # Completing command name
            completions = tuple(self._complete_commands(cmd))

        if len(completions) == 1:
            for completion in completions:
                break
            for c in completion:
                self.characterReceived(c, True)
            self.characterReceived(" ", False)
        else:
            self.terminal.nextLine()
            for completion in completions:
                # FIXME Emitting these in columns would be swell
                self.terminal.write("%s%s\n" % (word, completion))
            self.drawInputLine()

    def exit(self):
        self.terminal.loseConnection()
        self.service.reactor.stop()

    @staticmethod
    def tokenize(line):
        lexer = shlex(line)
        lexer.whitespace_split = True

        tokens = []
        while True:
            token = lexer.get_token()
            if not token:
                break
            tokens.append(token)

        return tokens

    def lineReceived(self, line):
        if self.activeCommand is not None:
            self.inputLines.append(line)
            return

        tokens = self.tokenize(line)

        if tokens:
            cmd = tokens.pop(0)
            #print "Arguments: %r" % (tokens,)

            m = getattr(self, "cmd_%s" % (cmd,), None)
            if m:
                def handleUsageError(f):
                    f.trap(UsageError)
                    self.terminal.write("%s\n" % (f.value,))

                def handleException(f):
                    self.terminal.write("Error: %s\n" % (f.value,))
                    if not f.check(NotImplementedError, NotFoundError):
                        log.msg("-"*80 + "\n")
                        log.msg(f.getTraceback())
                        log.msg("-"*80 + "\n")

                def next(_):
                    self.activeCommand = None
                    self.drawInputLine()
                    if self.inputLines:
                        line = self.inputLines.pop(0)
                        self.lineReceived(line)

                d = self.activeCommand = Deferred()
                d.addCallback(lambda _: m(tokens))
                if True:
                    d.callback(None)
                else:
                    # Add time to test callbacks
                    self.service.reactor.callLater(4, d.callback, None)
                d.addErrback(handleUsageError)
                d.addErrback(handleException)
                d.addCallback(next)
            else:
                self.terminal.write("Unknown command: %s\n" % (cmd,))
                self.drawInputLine()
        else:
            self.drawInputLine()

    def _getTarget(self, tokens):
        if tokens:
            return self.wd.locate(tokens.pop(0).split("/"))
        else:
            return succeed(self.wd)

    @inlineCallbacks
    def _getTargets(self, tokens):
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
    def _complete(word, items):
        for item in items:
            if item.startswith(word):
                yield item[len(word):]

    def _complete_commands(self, word):
        return self._complete(word, (name for name, method in self.commands()))

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
            return self._complete_commands(tokens[0])
        else:
            return ()

    def cmd_emulate(self, tokens):
        """
        Emulate editor behavior.
        The only correct argument is: emacs
        Other choices include: vi, none

        usage: emulate editor
        """
        if not tokens:
            raise UsageError("Editor not specified.")

        editor = tokens.pop(0).lower()

        if tokens:
            raise UnknownArguments(tokens)

        if editor == "emacs":
            self.terminal.write("Emulating EMACS.")
            self.emulate = EMULATE_EMACS
        elif editor == "vi":
            self.terminal.write("Seriously?!?!?")
            self.emulate = EMULATE_VI
        elif editor == "none":
            self.terminal.write("Disabling emulation.")
            self.emulate = None
        else:
            raise UsageError("Unknown editor: %s" % (editor,))
        self.terminal.nextLine()

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

        log.msg("wd -> %s" % (wd,))
        self.wd = wd

    @inlineCallbacks
    def cmd_ls(self, tokens):
        """
        List folder contents.

        usage: ls [folder]
        """
        targets = (yield self._getTargets(tokens))
        multiple = len(targets) > 0

        for target in targets:
            rows = (yield target.list())
            #
            # FIXME: this can be ugly if, for example, there are zillions
            # of entries to output. Paging would be good.
            #
            table = Table()
            for row in rows:
                klass = row[0]
                row = list(row[1:])
                if issubclass(klass, Folder):
                    row[0] = "%s/" % (row[0],)
                table.addRow(row)

            if multiple:
                self.terminal.write("%s:\n" % (target,))
            if table.rows:
                table.printTable(self.terminal)
            self.terminal.nextLine()

    @inlineCallbacks
    def cmd_info(self, tokens):
        """
        Print information about a folder.

        usage: info [folder]
        """
        target = (yield self._getTarget(tokens))

        if tokens:
            raise UnknownArguments(tokens)

        description = (yield target.describe())
        self.terminal.write(description)
        self.terminal.nextLine()

    @inlineCallbacks
    def cmd_cat(self, tokens):
        """
        Show contents of target.

        usage: cat target [target ...]
        """
        for target in (yield self._getTargets(tokens)):
            if hasattr(target, "text"):
                text = (yield target.text())
                self.terminal.write(text)

    def cmd_exit(self, tokens):
        """
        Exit the shell.

        usage: exit
        """
        self.exit()

    def cmd_python(self, tokens):
        """
        Switch to a python prompt.

        usage: python
        """
        # Crazy idea #19568: switch to an interactive python prompt
        # with self exposed in globals.
        raise NotImplementedError()

    cmd_python.hidden = "Not implemented"


class File(object):
    """
    Object in virtual data hierarchy.
    """
    def __init__(self, service, path):
        assert type(path) is tuple

        self.service = service
        self.path    = path

    def __str__(self):
        return "/" + "/".join(self.path)

    def describe(self):
        return succeed("%s (%s)" % (self, self.__class__.__name__))

    def list(self):
        return succeed((File, str(self)))


class Folder(File):
    """
    Location in virtual data hierarchy.
    """
    def __init__(self, service, path):
        File.__init__(self, service, path)

        self._children = {}
        self._childClasses = {}

    @inlineCallbacks
    def locate(self, path):
        if not path:
            returnValue(RootFolder(self.service))

        name = path[0]
        if name:
            target = (yield self.child(name))
            if len(path) > 1:
                target = (yield target.locate(path[1:]))
        else:
            target = (yield RootFolder(self.service).locate(path[1:]))

        returnValue(target)

    @inlineCallbacks
    def child(self, name):
        # FIXME: Move this logic to locate()
        #if not name:
        #    return succeed(self)
        #if name == ".":
        #    return succeed(self)
        #if name == "..":
        #    path = self.path[:-1]
        #    if not path:
        #        path = "/"
        #    return RootFolder(self.service).locate(path)

        if name in self._children:
            returnValue(self._children[name])

        if name in self._childClasses:
            child = (yield self._childClasses[name](self.service, self.path + (name,)))
            self._children[name] = child
            returnValue(child)

        raise NotFoundError("Folder %r has no child %r" % (str(self), name))

    def list(self):
        result = set()
        for name in self._children:
            result.add((self._children[name].__class__, name))
        for name in self._childClasses:
            result.add((self._childClasses[name], name))
        return succeed(result)


class RootFolder(Folder):
    """
    Root of virtual data hierarchy.

    Hierarchy:
      /                    RootFolder
        uids/              UIDsFolder
          <uid>/           PrincipalHomeFolder
            calendars/     CalendarHomeFolder
              <name>/      CalendarFolder
                <uid>      CalendarObject
            addressbooks/  AddressBookHomeFolder
              <name>/      AddressBookFolder
                <uid>      AddressBookObject
        users/             UsersFolder
          <name>/          PrincipalHomeFolder
            ...
        locations/         LocationsFolder
          <name>/          PrincipalHomeFolder
            ...
        resources/         ResourcesFolder
          <name>/          PrincipalHomeFolder
            ...
    """
    def __init__(self, service):
        Folder.__init__(self, service, ())

        self._childClasses["uids"     ] = UIDsFolder
        self._childClasses["users"    ] = UsersFolder
        self._childClasses["locations"] = LocationsFolder
        self._childClasses["resources"] = ResourcesFolder


class UIDsFolder(Folder):
    """
    Folder containing all principals by UID.
    """
    def child(self, name):
        return PrincipalHomeFolder(self.service, self.path + (name,), name)

    @inlineCallbacks
    def list(self):
        result = set()

        # FIXME: This should be the merged total of calendar homes and address book homes.
        # FIXME: Merge in directory UIDs also?
        # FIXME: Add directory info (eg. name) to listing

        for txn, home in (yield self.service.store.eachCalendarHome()):
            result.add((PrincipalHomeFolder, home.uid()))

        returnValue(result)



class RecordFolder(Folder):
    def _recordForName(self, name):
        recordTypeAttr = "recordType_" + self.recordType
        recordType = getattr(self.service.directory, recordTypeAttr)

        log.msg("Record type = %s" % (recordType,))

        return self.service.directory.recordWithShortName(recordType, name)

    def child(self, name):
        record = self._recordForName(name)
        log.msg("Record = %s" % (record,))
        return PrincipalHomeFolder(
            self.service,
            self.path + (record.uid,),
            record.uid,
            record=record
        )

    @inlineCallbacks
    def list(self):
        result = set()

        # FIXME ...

        returnValue(result)


class UsersFolder(RecordFolder):
    """
    Folder containing all user principals by name.
    """
    recordType = "users"


class LocationsFolder(RecordFolder):
    """
    Folder containing all location principals by name.
    """
    recordType = "locations"


class ResourcesFolder(RecordFolder):
    """
    Folder containing all resource principals by name.
    """
    recordType = "resources"


class PrincipalHomeFolder(Folder):
    """
    Folder containing everything related to a given principal.
    """
    def __init__(self, service, path, uid, record=None):
        Folder.__init__(self, service, path)

        if record is not None:
            assert uid == record.uid

        self.uid = uid
        self.record = record

    @inlineCallbacks
    def _initChildren(self):
        if not hasattr(self, "_didInitChildren"):
            txn  = self.service.store.newTransaction()

            if (
                self.record is not None and
                self.service.config.EnableCalDAV and 
                self.record.enabledForCalendaring
            ):
                create = True
            else:
                create = False

            home = (yield txn.calendarHomeWithUID(self.uid, create=create))
            if home:
                self._children["calendars"] = CalendarHomeFolder(
                    self.service,
                    self.path + ("calendars",),
                    home,
                )

            if (
                self.record is not None and
                self.service.config.EnableCardDAV and 
                self.record.enabledForAddressBooks
            ):
                create = True
            else:
                create = False

            home = (yield txn.addressbookHomeWithUID(self.uid))
            if home:
                self._children["addressbooks"] = AddressBookHomeFolder(
                    self.service,
                    self.path + ("addressbooks",),
                    home,
                )

        self._didInitChildren = True

    def _needsChildren(m):
        def decorate(self, *args, **kwargs):
            d = self._initChildren()
            d.addCallback(lambda _: m(self, *args, **kwargs))
            return d
        return decorate

    @_needsChildren
    def child(self, name):
        return Folder.child(self, name)

    @_needsChildren
    def list(self):
        return Folder.list(self)


class CalendarHomeFolder(Folder):
    """
    Calendar home folder.
    """
    def __init__(self, service, path, home):
        Folder.__init__(self, service, path)

        self.home = home

    @inlineCallbacks
    def child(self, name):
        calendar = (yield self.home.calendarWithName(name))
        if calendar:
            returnValue(CalendarFolder(self.service, self.path + (name,), calendar))
        else:
            raise NotFoundError("Calendar home %r has no calendar %r" % (self, name))

    @inlineCallbacks
    def list(self):
        calendars = (yield self.home.calendars())
        returnValue(((CalendarFolder, c.name()) for c in calendars))

    @inlineCallbacks
    def describe(self):
        # created() -> int
        # modified() -> int
        # properties -> IPropertyStore

        uid          = (yield self.home.uid())
        created      = (yield self.home.created())
        modified     = (yield self.home.modified())
        quotaUsed    = (yield self.home.quotaUsedBytes())
        quotaAllowed = (yield self.home.quotaAllowedBytes())
        properties   = (yield self.home.properties())

        result = []
        result.append("Calendar home for UID: %s" % (uid,))

        #
        # Attributes
        #
        rows = []
        if created is not None:
            # FIXME: convert to formatted string
            rows.append(("Created", str(created)))
        if modified is not None:
            # FIXME: convert to formatted string
            rows.append(("Last modified", str(modified)))
        if quotaUsed is not None:
            rows.append((
                "Quota",
                "%s of %s (%.2s%%)"
                % (quotaUsed, quotaAllowed, quotaUsed / quotaAllowed)
            ))

        if len(rows):
            result.append("\nAttributes:")
            result.append(tableString(rows, header=("Name", "Value")))

        #
        # Properties
        #
        if properties:
            result.append("\Properties:")
            result.append(tableString(
                ((name, properties[name]) for name in sorted(properties)),
                header=("Name", "Value")
            ))

        returnValue("\n".join(result))


class CalendarFolder(Folder):
    """
    Calendar.
    """
    def __init__(self, service, path, calendar):
        Folder.__init__(self, service, path)

        self.calendar = calendar

    @inlineCallbacks
    def _childWithObject(self, object):
        name = (yield object.uid())
        returnValue(CalendarObject(self.service, self.path + (name,), object))

    @inlineCallbacks
    def child(self, name):
        object = (yield self.calendar.calendarObjectWithUID(name))

        if not object:
            raise NotFoundError("Calendar %r has no object %r" % (str(self), name))

        child = (yield self._childWithObject(object))
        returnValue(child)

    @inlineCallbacks
    def list(self):
        result = []

        for object in (yield self.calendar.calendarObjects()):
            object = (yield self._childWithObject(object))
            items = (yield object.list())
            result.append(items[0])

        returnValue(result)


class CalendarObject(File):
    """
    Calendar object.
    """
    def __init__(self, service, path, calendarObject):
        File.__init__(self, service, path)

        self.object = calendarObject

    @inlineCallbacks
    def lookup(self):
        if not hasattr(self, "component"):
            component = (yield self.object.component())
            mainComponent = component.mainComponent()

            self.componentType = mainComponent.name()
            self.uid           = mainComponent.propertyValue("UID")
            self.summary       = mainComponent.propertyValue("SUMMARY")
            self.mainComponent = mainComponent
            self.component     = component

    @inlineCallbacks
    def list(self):
        (yield self.lookup())
        returnValue(((CalendarObject, self.uid, self.componentType, self.summary),))

    @inlineCallbacks
    def text(self):
        (yield self.lookup())
        returnValue(str(self.component))

    @inlineCallbacks
    def describe(self):
        (yield self.lookup())

        rows = []

        rows.append(("UID", self.uid))
        rows.append(("Type", self.componentType))
        rows.append(("Summary", self.summary))
        
        organizer = self.mainComponent.getProperty("ORGANIZER")
        if organizer:
            organizerName = organizer.parameterValue("CN")
            organizerEmail = organizer.parameterValue("EMAIL")

            name  = " (%s)" % (organizerName ,) if organizerName  else ""
            email = " <%s>" % (organizerEmail,) if organizerEmail else ""

            rows.append(("Organizer", "%s%s%s" % (organizer.value(), name, email)))

        #
        # Attachments
        #
#       attachments = (yield self.object.attachments())
#       log.msg("%r" % (attachments,))
#       for attachment in attachments:
#           log.msg("%r" % (attachment,))
#           # FIXME: Not getting any results here


        returnValue("Calendar object:\n%s" % tableString(rows))

class AddressBookHomeFolder(Folder):
    """
    Address book home folder.
    """
    # FIXME


def tableString(rows, header=None):
    table = Table()
    if header:
        table.addHeader(header)
    for row in rows:
        table.addRow(row)

    output = StringIO()
    table.printTable(os=output)
    return output.getvalue()


def main(argv=sys.argv, stderr=sys.stderr, reactor=None):
    if reactor is None:
        from twisted.internet import reactor

    options = ShellOptions()
    try:
        options.parseOptions(argv[1:])
    except UsageError, e:
        usage(e)

    def makeService(store):
        from twistedcaldav.config import config
        directory = getDirectory()
        return ShellService(store, directory, options, reactor, config)

    print "Initializing shell..."

    utilityMain(options["config"], makeService, reactor)
