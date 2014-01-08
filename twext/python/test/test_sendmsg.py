##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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

import socket
from os import pipe, read, close, environ
from twext.python.filepath import CachingFilePath as FilePath
import sys

from twisted.internet.defer import Deferred
from twisted.internet.error import ProcessDone
from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks
from twisted.internet import reactor

from twext.python.sendmsg import sendmsg, recvmsg
from twext.python.sendfd import sendfd
from twisted.internet.protocol import ProcessProtocol

class ExitedWithStderr(Exception):
    """
    A process exited with some stderr.
    """

    def __str__(self):
        """
        Dump the errors in a pretty way in the event of a subprocess traceback.
        """
        return '\n'.join([''] + list(self.args))


class StartStopProcessProtocol(ProcessProtocol):
    """
    An L{IProcessProtocol} with a Deferred for events where the subprocess
    starts and stops.
    """

    def __init__(self):
        self.started = Deferred()
        self.stopped = Deferred()
        self.output = ''
        self.errors = ''

    def connectionMade(self):
        self.started.callback(self.transport)

    def outReceived(self, data):
        self.output += data

    def errReceived(self, data):
        self.errors += data

    def processEnded(self, reason):
        if reason.check(ProcessDone):
            self.stopped.callback(self.output)
        else:
            self.stopped.errback(ExitedWithStderr(
                    self.errors, self.output))



def bootReactor():
    """
    Yield this from a trial test to bootstrap the reactor in order to avoid
    PotentialZombieWarning, for tests that use subprocesses.  This hack will no
    longer be necessary in Twisted 10.1, since U{the underlying bug was fixed
    <http://twistedmatrix.com/trac/ticket/2078>}.
    """
    d = Deferred()
    reactor.callLater(0, d.callback, None)
    return d



class SendmsgTestCase(TestCase):
    """
    Tests for sendmsg extension module and associated file-descriptor sending
    functionality in L{twext.python.sendfd}.
    """

    def setUp(self):
        """
        Create a pair of UNIX sockets.
        """
        self.input, self.output = socket.socketpair(socket.AF_UNIX)


    def tearDown(self):
        """
        Close the sockets opened by setUp.
        """
        self.input.close()
        self.output.close()


    def test_roundtrip(self):
        """
        L{recvmsg} will retrieve a message sent via L{sendmsg}.
        """
        sendmsg(self.input.fileno(), "hello, world!", 0)

        result = recvmsg(fd=self.output.fileno())
        self.assertEquals(result, ("hello, world!", 0, []))


    def test_wrongTypeAncillary(self):
        """
        L{sendmsg} will show a helpful exception message when given the wrong
        type of object for the 'ancillary' argument.
        """
        error = self.assertRaises(TypeError,
                                  sendmsg, self.input.fileno(),
                                  "hello, world!", 0, 4321)
        self.assertEquals(str(error),
                          "sendmsg argument 3 expected list, got int")


    def spawn(self, script):
        """
        Start a script that is a peer of this test as a subprocess.

        @param script: the module name of the script in this directory (no
            package prefix, no '.py')
        @type script: C{str}

        @rtype: L{StartStopProcessProtocol}
        """
        sspp = StartStopProcessProtocol()
        reactor.spawnProcess(
            sspp, sys.executable, [
                sys.executable,
                FilePath(__file__).sibling(script + ".py").path,
                str(self.output.fileno()),
            ],
            environ,
            childFDs={0: "w", 1: "r", 2: "r",
                      self.output.fileno(): self.output.fileno()}
        )
        return sspp


    @inlineCallbacks
    def test_sendSubProcessFD(self):
        """
        Calling L{sendsmsg} with SOL_SOCKET, SCM_RIGHTS, and a platform-endian
        packed file descriptor number should send that file descriptor to a
        different process, where it can be retrieved by using L{recvmsg}.
        """
        yield bootReactor()
        sspp = self.spawn("pullpipe")
        yield sspp.started
        pipeOut, pipeIn = pipe()
        self.addCleanup(close, pipeOut)
        sendfd(self.input.fileno(), pipeIn, "blonk")
        close(pipeIn)
        yield sspp.stopped
        self.assertEquals(read(pipeOut, 1024), "Test fixture data: blonk.\n")
        # Make sure that the pipe is actually closed now.
        self.assertEquals(read(pipeOut, 1024), "")

