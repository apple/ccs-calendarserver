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

import os
import sys
import traceback
from shlex import shlex

#from twisted.python import log
from twisted.python.text import wordWrap
from twisted.python.usage import Options, UsageError
from twisted.internet.defer import succeed, maybeDeferred
from twisted.conch.stdio import runWithProtocol as shellWithProtocol
from twisted.conch.recvline import HistoricRecvLine
from twisted.application.service import Service

from txdav.common.icommondatastore import NotFoundError

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
        shellWithProtocol(lambda: ShellProtocol(self.store))
        self.reactor.stop()

    def stopService(self):
        """
        Stop the service.
        """


class ShellProtocol(HistoricRecvLine):
    """
    Data store shell protocol.
    """

    # FIXME:
    # * Received lines are being echoed; find out why and stop it.
    # * Backspace transposes characters in the terminal.

    ps = ("ds% ", "... ")

    def __init__(self, store):
        HistoricRecvLine.__init__(self)
        self.wd = RootDirectory(store)

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

    def prompt(self):
        pass

    def lineReceived(self, line):
        try:
            lexer = shlex(line)
            lexer.whitespace_split = True

            tokens = []
            while True:
                token = lexer.get_token()
                if not token:
                    break
                tokens.append(token)

            if tokens:
                cmd = tokens.pop(0)
                #print "Arguments: %r" % (tokens,)

                m = getattr(self, "cmd_%s" % (cmd,), None)
                if m:
                    def onError(f):
                        print "Error: %s" % (f.getErrorMessage(),)
                        print "-"*80
                        f.printTraceback()
                        print "-"*80

                    d = maybeDeferred(m, tokens)
                    d.addCallback(lambda _: self.prompt)
                    d.addErrback(onError)
                    return d
                else:
                    print "Unknown command: %s" % (cmd,)

        except Exception, e:
            print "Error: %s" % (e,)
            print "-"*80
            traceback.print_exc()
            print "-"*80

    def cmd_pwd(self, tokens):
        """
        Print working directory.
        """
        if tokens:
            print "Unknown arguments: %s" % (tokens,)
            return
        print self.wd

    def cmd_cd(self, tokens):
        """
        Change working directory.
        """
        if tokens:
            dirname = tokens.pop(0)
        else:
            return

        if tokens:
            print "Unknown arguments: %s" % (tokens,)
            return

        path = dirname.split("/")

        def notFound(f):
            f.trap(NotFoundError)
            print "No such directory: %s" % (dirname,)

        def setWD(wd):
            self.wd = wd

        d = self.wd.locate(path)
        d.addCallback(setWD)
        d.addErrback(notFound)
        return d

    def cmd_ls(self, tokens):
        """
        List working directory.
        """
        if tokens:
            print "Unknown arguments: %s" % (tokens,)
            return

        for name in self.wd.list():
            print name

    def cmd_info(self, tokens):
        """
        Print information about working directory.
        """
        d = self.wd.describe()
        d.addCallback(lambda x: sys.stdout.write(x))
        return d

    def cmd_exit(self, tokens):
        """
        Exit the shell.
        """
        self.terminal.loseConnection()
        # FIXME: This is insufficient.

    def cmd_python(self, tokens):
        """
        Switch to a python prompt.
        """
        # Crazy idea #19568: switch to an interactive python prompt
        # with self exposed in globals.
        raise NotImplementedError()


class Directory(object):
    """
    Location in virtual data hierarchy.
    """
    def __init__(self, store, path):
        assert type(path) is tuple

        self.store = store
        self.path = path

    def __str__(self):
        return "/" + "/".join(self.path)

    def describe(self):
        return succeed(str(self))

    def locate(self, path):
        if not path:
            return succeed(RootDirectory(self.store))

        name = path[0]
        if not name:
            return succeed(self.locate(path[1:]))

        path = list(path)

        if name.startswith("/"):
            path[0] = path[0][1:]
            subdir = succeed(RootDirectory(self.store))
        else:
            path.pop(0)
            subdir = self.subdir(name)

        if path:
            return subdir.addCallback(lambda path: locate(path))
        else:
            return subdir

    def subdir(self, name):
        if not name:
            return succeed(self)
        if name == ".":
            return succeed(self)
        if name == "..":
            return RootDirectory(self.store).locate(self.path[:-1])

        raise NotFoundError("Directory %r has no subdirectory %r" % (str(self), name))

    def list(self):
        return ()


class RootDirectory(Directory):
    """
    Root of virtual data hierarchy.
    """
    def __init__(self, store):
        Directory.__init__(self, store, ())

        self._children = {}

        self._childClasses = {
            "uids": UIDDirectory,
        }

    def subdir(self, name):
        if name in self._children:
            return succeed(self._children[name])

        if name in self._childClasses:
            self._children[name] = self._childClasses[name](self.store, self.path + (name,))
            return succeed(self._children[name])

        return Directory.subdir(self, name)

    def list(self):
        return ("%s/" % (n,) for n in self._childClasses)


class UIDDirectory(Directory):
    """
    Directory containing all principals by UID.
    """
    def subdir(self, name):
        txn = self.store.newTransaction()

        def gotHome(home):
            if home:
                return HomeDirectory(self.store, self.path + (name,), home)

            return Directory.subdir(self, name)

        d = txn.calendarHomeWithUID(name)
        d.addCallback(gotHome)
        return d

    def list(self):
        for (txn, home) in self.store.eachCalendarHome():
            yield home.uid()


class HomeDirectory(Directory):
    """
    Home directory.
    """
    def __init__(self, store, path, home):
        Directory.__init__(self, store, path)

        self.home = home

    def describe(self):
        return succeed(
            """Calendar home for UID: %(uid)s\n"""
            """Quota: %(quotaUsed)s of %(quotaMax)s (%(quotaPercent).2s%%)\n"""
            % {
                "uid"          : self.home.uid(),
                "quotaUsed"    : self.home.quotaUsed(),
                "quotaMax"     : self.home.quotaAllowedBytes(),
                "quotaPercent" : self.home.quotaUsed() / self.home.quotaAllowedBytes(),
            }
        )


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
