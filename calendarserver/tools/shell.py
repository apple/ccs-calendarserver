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

from twisted.python.text import wordWrap
from twisted.python.usage import Options, UsageError
from twisted.internet.defer import succeed, maybeDeferred
from twisted.conch.stdio import runWithProtocol as shellWithProtocol
from twisted.conch.recvline import RecvLine as ReceiveLineProtocol
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


class UnknownArguments (Exception):
    """
    Unknown arguments.
    """
    def __init__(self, arguments):
        Exception.__init__(self, "Unknown arguments: %s" % (arguments,))
        self.arguments = arguments


class ShellProtocol(ReceiveLineProtocol):
    """
    Data store shell protocol.
    """

    # FIXME:
    # * Received lines are being echoed; find out why and stop it.
    # * Backspace transposes characters in the terminal.

    ps = ("ds% ", "... ")

    def __init__(self, store):
        ReceiveLineProtocol.__init__(self)
        self.wd = RootDirectory(store)

    def lineReceived(self, line):
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
                try:
                    m(tokens)
                except UnknownArguments, e:
                    self.terminal.write("%s\n" % (e,))
                except Exception, e:
                    print "Error: %s" % (e,)
                    print "-"*80
                    f.printTraceback()
                    print "-"*80

            else:
                self.terminal.write("Unknown command: %s\n" % (cmd,))

        self.drawInputLine()

    def cmd_pwd(self, tokens):
        """
        Print working directory.
        """
        if tokens:
            raise UnknownArguments(tokens)
            return
        self.terminal.write("%s\n" % (self.wd,))

    def cmd_cd(self, tokens):
        """
        Change working directory.
        """
        if tokens:
            dirname = tokens.pop(0)
        else:
            return

        if tokens:
            raise UnknownArguments(tokens)
            return

        path = dirname.split("/")

        def notFound(f):
            f.trap(NotFoundError)
            self.terminal.write("No such directory: %s\n" % (dirname,))

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
            raise UnknownArguments(tokens)
            return

        for name in self.wd.list():
            self.terminal.write("%s\n" % (name,))

    def cmd_info(self, tokens):
        """
        Print information about working directory.
        """
        if tokens:
            raise UnknownArguments(tokens)
            return

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
            return subdir.addCallback(lambda path: self.locate(path))
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
