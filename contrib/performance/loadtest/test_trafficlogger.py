##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
#
##

from zope.interface import Interface, implements

from twisted.internet.protocol import ClientFactory, Protocol
from twisted.trial.unittest import TestCase
from twisted.test.proto_helpers import StringTransport, MemoryReactor
from twisted.protocols.wire import Discard

from contrib.performance.loadtest.trafficlogger import _TrafficLoggingFactory, loggedReactor


class IProbe(Interface):
    """
    An interface which can be used to verify some interface-related behavior of
    L{loggedReactor}.
    """
    def probe(): #@NoSelf
        pass


class Probe(object):
    implements(IProbe)

    _probed = False

    def __init__(self, result=None):
        self._result = result

    def probe(self):
        self._probed = True
        return self._result


class TrafficLoggingReactorTests(TestCase):
    """
    Tests for L{loggedReactor}.
    """
    def test_nothing(self):
        """
        L{loggedReactor} returns the object passed to it, if the object passed
        to it doesn't provide any interfaces.  This is mostly for testing
        convenience rather than a particularly useful feature.
        """
        probe = object()
        self.assertIdentical(probe, loggedReactor(probe))


    def test_interfaces(self):
        """
        The object returned by L{loggedReactor} provides all of the interfaces
        provided by the object passed to it.
        """
        probe = Probe()
        reactor = loggedReactor(probe)
        self.assertTrue(IProbe.providedBy(reactor))


    def test_passthrough(self):
        """
        Methods on interfaces on the object passed to L{loggedReactor} can be
        called by calling them on the object returned by L{loggedReactor}.
        """
        expected = object()
        probe = Probe(expected)
        reactor = loggedReactor(probe)
        result = reactor.probe()
        self.assertTrue(probe._probed)
        self.assertIdentical(expected, result)


    def test_connectTCP(self):
        """
        Called on the object returned by L{loggedReactor}, C{connectTCP} calls
        the wrapped reactor's C{connectTCP} method with the original factory
        wrapped in a L{_TrafficLoggingFactory}.
        """
        class RecordDataProtocol(Protocol):
            def dataReceived(self, data):
                self.data = data
        proto = RecordDataProtocol()
        factory = ClientFactory()
        factory.protocol = lambda: proto
        reactor = MemoryReactor()
        logged = loggedReactor(reactor)
        logged.connectTCP('192.168.1.2', 1234, factory, 21, '127.0.0.2')
        [(host, port, factory, timeout, bindAddress)] = reactor.tcpClients
        self.assertEqual('192.168.1.2', host)
        self.assertEqual(1234, port)
        self.assertIsInstance(factory, _TrafficLoggingFactory)
        self.assertEqual(21, timeout)
        self.assertEqual('127.0.0.2', bindAddress)

        # Verify that the factory and protocol specified are really being used
        protocol = factory.buildProtocol(None)
        protocol.makeConnection(None)
        protocol.dataReceived("foo")
        self.assertEqual(proto.data, "foo")


    def test_getLogFiles(self):
        """
        The reactor returned by L{loggedReactor} has a C{getLogFiles} method
        which returns a L{logstate} instance containing the active and
        completed log files tracked by the logging wrapper.
        """
        wrapped = ClientFactory()
        wrapped.protocol = Discard
        reactor = MemoryReactor()
        logged = loggedReactor(reactor)
        logged.connectTCP('127.0.0.1', 1234, wrapped)
        factory = reactor.tcpClients[0][2]

        finished = factory.buildProtocol(None)
        finished.makeConnection(StringTransport())
        finished.dataReceived('finished')
        finished.connectionLost(None)

        active = factory.buildProtocol(None)
        active.makeConnection(StringTransport())
        active.dataReceived('active')

        logs = logged.getLogFiles()
        self.assertEqual(1, len(logs.finished))
        self.assertIn('finished', logs.finished[0].getvalue())
        self.assertEqual(1, len(logs.active))
        self.assertIn('active', logs.active[0].getvalue())



class TrafficLoggingFactoryTests(TestCase):
    """
    Tests for L{_TrafficLoggingFactory}.
    """
    def setUp(self):
        self.wrapped = ClientFactory()
        self.wrapped.protocol = Discard
        self.factory = _TrafficLoggingFactory(self.wrapped)

        
    def test_receivedBytesLogged(self):
        """
        When bytes are delivered through a protocol created by
        L{_TrafficLoggingFactory}, they are added to a log kept on that
        factory.
        """
        protocol = self.factory.buildProtocol(None)

        # The factory should now have a new StringIO log file
        self.assertEqual(1, len(self.factory.logs))

        transport = StringTransport()
        protocol.makeConnection(transport)

        protocol.dataReceived("hello, world")
        self.assertEqual(
            "*\nC 0: 'hello, world'\n", self.factory.logs[0].getvalue())


    def test_finishedLogs(self):
        """
        When connections are lost, the corresponding log files are moved into
        C{_TrafficLoggingFactory.finishedLogs}.
        """
        protocol = self.factory.buildProtocol(None)
        transport = StringTransport()
        protocol.makeConnection(transport)
        logfile = self.factory.logs[0]
        protocol.connectionLost(None)
        self.assertEqual(0, len(self.factory.logs))
        self.assertEqual([logfile], self.factory.finishedLogs)


    def test_finishedLogsLimit(self):
        """
        Only the most recent C{_TrafficLoggingFactory.LOGFILE_LIMIT} logfiles
        are kept in C{_TrafficLoggingFactory.finishedLogs}.
        """
        self.factory.LOGFILE_LIMIT = 2
        first = self.factory.buildProtocol(None)
        first.makeConnection(StringTransport())
        second = self.factory.buildProtocol(None)
        second.makeConnection(StringTransport())
        third = self.factory.buildProtocol(None)
        third.makeConnection(StringTransport())

        second.connectionLost(None)
        first.connectionLost(None)
        third.connectionLost(None)

        self.assertEqual(
            [first.logfile, third.logfile], self.factory.finishedLogs)
