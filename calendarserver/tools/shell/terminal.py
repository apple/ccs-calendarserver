#!/usr/bin/env python
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
Interactive shell for terminals.
"""

import string
import os
import sys
import tty
import termios
from shlex import shlex

from twisted.python import log
from twisted.python.text import wordWrap
from twisted.python.usage import Options, UsageError
from twisted.internet.defer import Deferred
from twisted.internet.defer import inlineCallbacks
from twisted.internet.stdio import StandardIO
from twisted.conch.recvline import HistoricRecvLine as ReceiveLineProtocol
from twisted.conch.insults.insults import ServerProtocol
from twisted.application.service import Service

from txdav.common.icommondatastore import NotFoundError

from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE

from calendarserver.tools.cmdline import utilityMain
from calendarserver.tools.util import getDirectory
from calendarserver.tools.shell.cmd import Commands, UsageError as CommandUsageError
from calendarserver.tools.shell.vfs import Folder, RootFolder


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
        if True:
            from twisted.python.log import startLogging
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


class ShellProtocol(ReceiveLineProtocol, Commands):
    """
    Data store shell protocol.
    """

    # FIXME:
    # * Received lines are being echoed; find out why and stop it.
    # * Backspace transposes characters in the terminal.

    ps = ("ds% ", "... ")

    emulation_modes = ("emacs", "none")

    def __init__(self, service):
        ReceiveLineProtocol.__init__(self)
        Commands.__init__(self, RootFolder(service))
        self.service = service
        self.inputLines = []
        self.activeCommand = None
        self.emulate = "emacs"

    #
    # Input handling
    #

    def connectionMade(self):
        ReceiveLineProtocol.connectionMade(self)

        self.keyHandlers['\x03'] = self.handle_INT   # Control-C
        self.keyHandlers['\x04'] = self.handle_EOF   # Control-D
        self.keyHandlers['\x1c'] = self.handle_QUIT  # Control-\
        self.keyHandlers['\x0c'] = self.handle_FF    # Control-L
       #self.keyHandlers['\t'  ] = self.handle_TAB   # Tab

        if self.emulate == "emacs":
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
            if self.emulate == "emacs":
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

    @inlineCallbacks
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
            completions = tuple((yield m(tokens)))

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

    #
    # Utilities
    #

    def exit(self):
        self.terminal.loseConnection()
        self.service.reactor.stop()

    @staticmethod
    def _listEntryToString(entry):
        klass = entry[0]
        name  = entry[1]

        if issubclass(klass, Folder):
            return "%s/" % (name,)
        else:
            return name

    #
    # Command dispatch
    #

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
                    f.trap(CommandUsageError)
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
