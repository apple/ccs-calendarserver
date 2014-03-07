# -*- test-case-name: twext.internet.test.test_sendfdport -*-
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

"""
Tests for L{twext.internet.sendfdport}.
"""

import os
import fcntl

from zope.interface.verify import verifyClass
from zope.interface import implementer

from twext.internet.sendfdport import InheritedSocketDispatcher
from twext.internet.sendfdport import IStatusWatcher, IStatus

from twext.web2.metafd import ConnectionLimiter
from twisted.internet.interfaces import IReactorFDSet
from twisted.trial.unittest import TestCase

def verifiedImplementer(interface):
    def _(cls):
        result = implementer(interface)(cls)
        verifyClass(interface, result)
        return result
    return _



@verifiedImplementer(IReactorFDSet)
class ReaderAdder(object):

    def __init__(self):
        self.readers = []
        self.writers = []


    def addReader(self, reader):
        self.readers.append(reader)


    def getReaders(self):
        return self.readers[:]


    def addWriter(self, writer):
        self.writers.append(writer)


    def removeAll(self):
        self.__init__()


    def getWriters(self):
        return self.writers[:]


    def removeReader(self, reader):
        self.readers.remove(reader)


    def removeWriter(self, writer):
        self.writers.remove(writer)



def isNonBlocking(skt):
    """
    Determine if the given socket is blocking or not.

    @param skt: a socket.
    @type skt: L{socket.socket}

    @return: L{True} if the socket is non-blocking, L{False} if the socket is
        blocking.
    @rtype: L{bool}
    """
    return bool(fcntl.fcntl(skt.fileno(), fcntl.F_GETFL) & os.O_NONBLOCK)



@verifiedImplementer(IStatus)
class Status(object):
    def __init__(self):
        self.count = 0
        self.available = False


    def effective(self):
        return self.count


    def active(self):
        return self.available


    def start(self):
        self.available = False
        return self


    def restarted(self):
        self.available = True
        return self


    def stop(self):
        self.count = 0
        self.available = False
        return self



@verifiedImplementer(IStatusWatcher)
class Watcher(object):
    def __init__(self, q):
        self.q = q
        self._closeCounter = 1


    def newConnectionStatus(self, previous):
        previous.count += 1
        return previous


    def statusFromMessage(self, previous, message):
        previous.count -= 1
        return previous


    def statusesChanged(self, statuses):
        self.q.append([(status.count, status.available) for status in statuses])


    def initialStatus(self):
        return Status()


    def closeCountFromStatus(self, status):
        result = (self._closeCounter, status)
        self._closeCounter += 1
        return result



class InheritedSocketDispatcherTests(TestCase):
    """
    Inherited socket dispatcher tests.
    """
    def setUp(self):
        self.dispatcher = InheritedSocketDispatcher(ConnectionLimiter(2, 20))
        self.dispatcher.reactor = ReaderAdder()


    def test_closeSomeSockets(self):
        """
        L{InheritedSocketDispatcher} determines how many sockets to close from
        L{IStatusWatcher.closeCountFromStatus}.
        """
        self.dispatcher.statusWatcher = Watcher([])
        class SocketForClosing(object):
            blocking = True
            closed = False
            def setblocking(self, b):
                self.blocking = b
            def fileno(self):
                return object()
            def close(self):
                self.closed = True

        one = SocketForClosing()
        two = SocketForClosing()
        three = SocketForClosing()

        skt = self.dispatcher.addSocket(
            lambda: (SocketForClosing(), SocketForClosing())
        )
        skt.restarted()

        self.dispatcher.sendFileDescriptor(one, "one")
        self.dispatcher.sendFileDescriptor(two, "two")
        self.dispatcher.sendFileDescriptor(three, "three")
        def sendfd(unixSocket, tcpSocket, description):
            pass
        # Put something into the socket-close queue.
        self.dispatcher._subprocessSockets[0].doWrite(sendfd)
        # Nothing closed yet.
        self.assertEquals(one.closed, False)
        self.assertEquals(two.closed, False)
        self.assertEquals(three.closed, False)

        def recvmsg(fileno):
            return 'data', 0, 0
        self.dispatcher._subprocessSockets[0].doRead(recvmsg)
        # One socket closed.
        self.assertEquals(one.closed, True)
        self.assertEquals(two.closed, False)
        self.assertEquals(three.closed, False)


    def test_nonBlocking(self):
        """
        Creating a L{_SubprocessSocket} via
        L{InheritedSocketDispatcher.addSocket} results in a non-blocking
        L{socket.socket} object being assigned to its C{skt} attribute, as well
        as a non-blocking L{socket.socket} object being returned.
        """
        dispatcher = self.dispatcher
        dispatcher.startDispatching()
        inputSocket = dispatcher.addSocket()
        outputSocket = self.dispatcher.reactor.readers[-1]
        self.assertTrue(isNonBlocking(inputSocket), "Input is blocking.")
        self.assertTrue(isNonBlocking(outputSocket), "Output is blocking.")


    def test_addAfterStart(self):
        """
        Adding a socket to an L{InheritedSocketDispatcher} after it has already
        been started results in it immediately starting reading.
        """
        dispatcher = self.dispatcher
        dispatcher.startDispatching()
        dispatcher.addSocket()
        self.assertEquals(dispatcher.reactor.getReaders(),
                          dispatcher._subprocessSockets)


    def test_statusesChangedOnNewConnection(self):
        """
        L{InheritedSocketDispatcher.sendFileDescriptor} will update its
        C{statusWatcher} via C{statusesChanged}.
        """
        q = []
        dispatcher = self.dispatcher
        dispatcher.statusWatcher = Watcher(q)
        description = "whatever"
        # Need to have a socket that will accept the descriptors.
        skt = dispatcher.addSocket()
        skt.restarted()
        dispatcher.sendFileDescriptor(object(), description)
        dispatcher.sendFileDescriptor(object(), description)
        self.assertEquals(q, [[(0, True)], [(1, True)], [(2, True)]])


    def test_statusesChangedOnStatusMessage(self):
        """
        L{InheritedSocketDispatcher.sendFileDescriptor} will update its
        C{statusWatcher} will update its C{statusWatcher} via
        C{statusesChanged}.
        """
        q = []
        dispatcher = self.dispatcher
        dispatcher.statusWatcher = Watcher(q)
        message = "whatever"
        # Need to have a socket that will accept the descriptors.
        dispatcher.addSocket()
        subskt = dispatcher._subprocessSockets[0]
        dispatcher.statusMessage(subskt, message)
        dispatcher.statusMessage(subskt, message)
        self.assertEquals(q, [[(-1, False)], [(-2, False)]])


    def test_statusesChangedOnStartRestartStop(self):
        """
        L{_SubprocessSocket} will update its C{status} when state change.
        """
        q = []
        dispatcher = self.dispatcher
        dispatcher.statusWatcher = Watcher(q)
        message = "whatever"
        # Need to have a socket that will accept the descriptors.
        subskt = dispatcher.addSocket()
        subskt.start()
        subskt.restarted()
        dispatcher.sendFileDescriptor(subskt, message)
        subskt.stop()
        subskt.start()
        subskt.restarted()
        self.assertEquals(
            q,
            [
                [(0, False)],
                [(0, True)],
                [(1, True)],
                [(0, False)],
                [(0, False)],
                [(0, True)],
            ]
        )
