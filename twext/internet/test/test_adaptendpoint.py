##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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
Tests for L{twext.internet.adaptendpoint}.
"""

from zope.interface.verify import verifyObject

from twext.internet.adaptendpoint import connect
from twisted.internet.defer import Deferred, CancelledError
from twisted.python.failure import Failure

from twisted.internet.protocol import ClientFactory, Protocol
from twisted.internet.interfaces import IConnector
from twisted.trial.unittest import TestCase

class names(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


class RecordingProtocol(Protocol, object):
    def __init__(self):
        super(RecordingProtocol, self).__init__()
        self.made = []
        self.data = []
        self.lost = []


    def connectionMade(self):
        self.made.append(self.transport)


    def dataReceived(self, data):
        self.data.append(data)


    def connectionLost(self, why):
        self.lost.append(why)



class RecordingClientFactory(ClientFactory):
    """
    L{ClientFactory} subclass that records the things that happen to it.
    """

    def __init__(self):
        """
        Create some records of things that are about to happen.
        """
        self.starts = []
        self.built = []
        self.fails = []
        self.lost = []


    def startedConnecting(self, ctr):
        self.starts.append(ctr)


    def clientConnectionFailed(self, ctr, reason):
        self.fails.append(names(connector=ctr, reason=reason))


    def clientConnectionLost(self, ctr, reason):
        self.lost.append(names(connector=ctr, reason=reason))


    def buildProtocol(self, addr):
        b =  RecordingProtocol()
        self.built.append(names(protocol=b, addr=addr))
        return b



class RecordingEndpoint(object):

    def __init__(self):
        self.attempts = []


    def connect(self, factory):
        d = Deferred()
        self.attempts.append(names(deferred=d, factory=factory))
        return d


class RecordingTransport(object):

    def __init__(self):
        self.lose = []


    def loseConnection(self):
        self.lose.append(self)



class AdaptEndpointTests(TestCase):
    """
    Tests for L{connect} and the objects that it coordinates.
    """

    def setUp(self):
        self.factory = RecordingClientFactory()
        self.endpoint = RecordingEndpoint()
        self.connector = connect(self.endpoint, self.factory)


    def connectionSucceeds(self, addr=object()):
        """
        The most recent connection attempt succeeds, returning the L{ITransport}
        provider produced by its success.
        """
        transport = RecordingTransport()
        attempt = self.endpoint.attempts[-1]
        proto = attempt.factory.buildProtocol(addr)
        proto.makeConnection(transport)
        transport.protocol = proto
        attempt.deferred.callback(proto)
        return transport


    def connectionFails(self, reason):
        """
        The most recent in-progress connection fails.
        """
        self.endpoint.attempts[-1].deferred.errback(reason)


    def test_connectStartsConnection(self):
        """
        When used with a successful endpoint, L{connect} will simulate all
        aspects of the connection process; C{buildProtocol}, C{connectionMade},
        C{dataReceived}.
        """
        self.assertIdentical(self.connector.getDestination(), self.endpoint)
        verifyObject(IConnector, self.connector)
        self.assertEqual(self.factory.starts, [self.connector])
        self.assertEqual(len(self.endpoint.attempts), 1)
        self.assertEqual(len(self.factory.built), 0)
        transport = self.connectionSucceeds()
        self.assertEqual(len(self.factory.built), 1)
        made = transport.protocol.made
        self.assertEqual(len(made), 1)
        self.assertIdentical(made[0], transport)


    def test_connectionLost(self):
        """
        When the connection is lost, both the protocol and the factory will be
        notified via C{connectionLost} and C{clientConnectionLost}.
        """
        why = Failure(RuntimeError())
        proto = self.connectionSucceeds().protocol
        proto.connectionLost(why)
        self.assertEquals(len(self.factory.built), 1)
        self.assertEquals(self.factory.built[0].protocol.lost, [why])
        self.assertEquals(len(self.factory.lost), 1)
        self.assertIdentical(self.factory.lost[0].reason, why)


    def test_connectionFailed(self):
        """
        When the L{Deferred} from the endpoint fails, the L{ClientFactory} gets
        notified via C{clientConnectionFailed}.
        """
        why = Failure(RuntimeError())
        self.connectionFails(why)
        self.assertEquals(len(self.factory.fails), 1)
        self.assertIdentical(self.factory.fails[0].reason, why)


    def test_disconnectWhileConnecting(self):
        """
        If the L{IConnector} is told to C{disconnect} before an in-progress
        L{Deferred} from C{connect} has fired, it will cancel that L{Deferred}.
        """
        self.connector.disconnect()
        self.assertEqual(len(self.factory.fails), 1)
        self.assertTrue(self.factory.fails[0].reason.check(CancelledError))


    def test_disconnectWhileConnected(self):
        """
        If the L{IConnector} is told to C{disconnect} while an existing
        connection is established, that connection will be dropped via
        C{loseConnection}.
        """
        transport = self.connectionSucceeds()
        self.factory.starts[0].disconnect()
        self.assertEqual(transport.lose, [transport])


    def test_connectAfterFailure(self):
        """
        If the L{IConnector} is told to C{connect} after a connection attempt
        has failed, a new connection attempt is started.
        """
        why = Failure(ZeroDivisionError())
        self.connectionFails(why)
        self.connector.connect()
        self.assertEqual(len(self.factory.starts), 2)
        self.assertEqual(len(self.endpoint.attempts), 2)
        self.connectionSucceeds()


    def test_reConnectTooSoon(self):
        """
        If the L{IConnector} is told to C{connect} while another attempt is
        still in flight, it synchronously raises L{RuntimeError}.
        """
        self.assertRaises(RuntimeError, self.connector.connect)
        self.assertEqual(len(self.factory.starts), 1)
        self.assertEqual(len(self.endpoint.attempts), 1)




