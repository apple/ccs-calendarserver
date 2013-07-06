from twext.internet.sendfdport import IStatusWatcher
# -*- test-case-name: twext.internet.test.test_sendfdport -*-
##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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

from twext.internet.sendfdport import InheritedSocketDispatcher

from twext.web2.metafd import ConnectionLimiter
from twisted.internet.interfaces import IReactorFDSet
from twisted.trial.unittest import TestCase
from zope.interface import implementer

@implementer(IReactorFDSet)
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



from zope.interface.verify import verifyClass
from zope.interface import implementer

def verifiedImplementer(interface):
    def _(cls):
        result = implementer(interface)(cls)
        verifyClass(interface, result)
        return result
    return _



@verifiedImplementer(IStatusWatcher)
class Watcher(object):
    def __init__(self, q):
        self.q = q


    def newConnectionStatus(self, previous):
        return previous + 1


    def statusFromMessage(self, previous, message):
        return previous - 1


    def statusesChanged(self, statuses):
        self.q.append(list(statuses))


    def initialStatus(self):
        return 0



class InheritedSocketDispatcherTests(TestCase):
    """
    Inherited socket dispatcher tests.
    """
    def setUp(self):
        self.dispatcher = InheritedSocketDispatcher(ConnectionLimiter(2, 20))
        self.dispatcher.reactor = ReaderAdder()


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


    def test_sendFileDescriptorSorting(self):
        """
        Make sure InheritedSocketDispatcher.sendFileDescriptor sorts sockets
        with status None higher than those with int status values.
        """
        dispatcher = self.dispatcher
        dispatcher.addSocket()
        dispatcher.addSocket()
        dispatcher.addSocket()

        sockets = dispatcher._subprocessSockets[:]

        # Check that 0 is preferred over None
        sockets[0].status = 0
        sockets[1].status = 1
        sockets[2].status = None

        dispatcher.sendFileDescriptor(None, "")

        self.assertEqual(sockets[0].status, 1)
        self.assertEqual(sockets[1].status, 1)
        self.assertEqual(sockets[2].status, None)

        dispatcher.sendFileDescriptor(None, "")

        self.assertEqual(sockets[0].status, 1)
        self.assertEqual(sockets[1].status, 1)
        self.assertEqual(sockets[2].status, 1)

        # Check that after going to 1 and back to 0 that is still preferred
        # over None
        sockets[0].status = 0
        sockets[1].status = 1
        sockets[2].status = None

        dispatcher.sendFileDescriptor(None, "")

        self.assertEqual(sockets[0].status, 1)
        self.assertEqual(sockets[1].status, 1)
        self.assertEqual(sockets[2].status, None)

        sockets[1].status = 0

        dispatcher.sendFileDescriptor(None, "")

        self.assertEqual(sockets[0].status, 1)
        self.assertEqual(sockets[1].status, 1)
        self.assertEqual(sockets[2].status, None)


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
        dispatcher.addSocket()
        dispatcher.sendFileDescriptor(object(), description)
        dispatcher.sendFileDescriptor(object(), description)
        self.assertEquals(q, [[1], [2]])


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
        dispatcher.statusMessage(dispatcher._subprocessSockets[0], message)
        dispatcher.statusMessage(dispatcher._subprocessSockets[0], message)
        self.assertEquals(q, [[-1], [-2]])
