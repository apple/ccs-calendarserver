#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_export -*-
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

import os
import sys
from shlex import shlex

#from twisted.python import log
from twisted.python.text import wordWrap
from twisted.python.usage import Options, UsageError
from twisted.conch.stdio import runWithProtocol as shellWithProtocol
from twisted.conch.recvline import HistoricRecvLine
from twisted.application.service import Service

from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE

from calendarserver.tools.cmdline import utilityMain


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
    def __init__(self, store, options, reactor, config):
        super(ShellService, self).__init__()
        self.store   = store
        self.options = options
        self.reactor = reactor
        self.config = config

    def startService(self):
        """
        Start the service.
        """
        super(ShellService, self).startService()
        shellWithProtocol(ShellProtocol)
        self.reactor.stop()

    def stopService(self):
        """
        Stop the service.
        """


class Directory(object):
    """
    Location in virtual data hierarchy.
    """
    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "/" + "/".join(self.path)


class RootDirectory(Directory):
    """
    Root of virtual data hierarchy.
    """
    def __init__(self):
        Directory.__init__(self, ())


class ShellProtocol(HistoricRecvLine):
    """
    Data store shell protocol.
    """

    # FIXME:
    # * Received lines are being echoed; find out why and stop it.
    # * Backspace transposes characters in the terminal.

    ps = ("ds% ", "... ")
    wd = RootDirectory()

    def connectionMade(self):
        HistoricRecvLine.connectionMade(self)

        CTRL_C         = "\x03"
        CTRL_D         = "\x04"
        CTRL_L         = "\x0c"
        CTRL_BACKSLASH = "\x1c"

        self.keyHandlers[CTRL_C        ] = self.handle_INT
        self.keyHandlers[CTRL_D        ] = self.handle_EOF
        self.keyHandlers[CTRL_L        ] = self.handle_FF
        self.keyHandlers[CTRL_BACKSLASH] = self.handle_QUIT

        wd = RootDirectory()

    def handle_INT(self):
        """
        Handle ^C as an interrupt keystroke by resetting the current input
        variables to their initial state.
        """
        self.pn = 0
        self.lineBuffer = []
        self.lineBufferIndex = 0
        self.interpreter.resetBuffer()

        self.terminal.nextLine()
        self.terminal.write("KeyboardInterrupt")
        self.terminal.nextLine()
        self.terminal.write(self.ps[self.pn])

    def handle_EOF(self):
        if self.lineBuffer:
            self.terminal.write("\a")
        else:
            self.handle_QUIT()

    def handle_FF(self):
        """
        Handle a "form feed" byte - generally used to request a screen
        refresh/redraw.
        """
        self.terminal.eraseDisplay()
        self.terminal.cursorHome()
        self.drawInputLine()

    def handle_QUIT(self):
        self.terminal.loseConnection()

    def lineReceived(self, line):
        print "-> %s" % (line,)

        lexer = shlex(line)
        tokens = []
        while True:
            token = lexer.get_token()
            if not token:
                break
            tokens.append(token)

        if tokens:
            cmd = tokens.pop()
            m = getattr(self, "cmd_%s" % (cmd,), None)
            if m:
                m(tokens)
            else:
                print "Unknown command: %s" % (cmd,)

    def cmd_pwd(self, tokens):
        if tokens:
            print "Unknown arguments: %s" % (tokens,)
            return
        print self.wd


def main(argv=sys.argv, stderr=sys.stderr, reactor=None):
    """
    Do the export.
    """
    if reactor is None:
        from twisted.internet import reactor

    options = ShellOptions()
    try:
        options.parseOptions(argv[1:])
    except UsageError, e:
        usage(e)

    def makeService(store):
        from twistedcaldav.config import config
        return ShellService(store, options, reactor, config)

    print "Initializing shell..."

    utilityMain(options["config"], makeService, reactor)
