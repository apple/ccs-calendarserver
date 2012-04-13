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


class AdaptEndpointTests(TestCase):
    """
    Tests for L{connect} and the objects that it coordinates.
    """

    def test_connectStartsConnection(self):
        """
        When used with a successful endpoint, L{connect} will simulate all
        aspects of the connection process; C{buildProtocol}, C{connectionMade},
        C{dataReceived}.
        """
        rcf = RecordingClientFactory()
        e = RecordingEndpoint()
        ctr = connect(e, rcf)
        self.assertIdentical(ctr.getDestination(), e)
        verifyObject(IConnector, ctr)
        self.assertEqual(rcf.starts, [ctr])
        self.assertEqual(len(e.attempts), 1)
        self.assertEqual(len(rcf.built), 0)
        proto = e.attempts[0].factory.buildProtocol(object)
        self.assertEqual(len(rcf.built), 1)
        made = rcf.built[0].protocol.made
        transport = object()
        self.assertEqual(len(made), 0)
        proto.makeConnection(transport)
        self.assertEqual(len(made), 1)
        self.assertIdentical(made[0], transport)


    def test_connectionLost(self):
        """
        When the connection is lost, both the protocol and the factory will be
        notified via C{connectionLost} and C{clientConnectionLost}.
        """
        rcf = RecordingClientFactory()
        e = RecordingEndpoint()
        connect(e, rcf)
        why = Failure(RuntimeError())
        proto = e.attempts[0].factory.buildProtocol(object)
        proto.makeConnection(object())
        proto.connectionLost(why)
        self.assertEquals(len(rcf.built), 1)
        self.assertEquals(rcf.built[0].protocol.lost, [why])
        self.assertEquals(len(rcf.lost), 1)
        self.assertIdentical(rcf.lost[0].reason, why)


    def test_connectionFailed(self):
        """
        When the L{Deferred} from the endpoint fails, the L{ClientFactory} gets
        notified via C{clientConnectionFailed}.
        """
        rcf = RecordingClientFactory()
        e = RecordingEndpoint()
        connect(e, rcf)
        why = Failure(RuntimeError())
        e.attempts[0].deferred.errback(why)
        self.assertEquals(len(rcf.fails), 1)
        self.assertIdentical(rcf.fails[0].reason, why)


    def test_disconnectWhileConnecting(self):
        """
        If the L{IConnector} is told to C{disconnect} before an in-progress
        L{Deferred} from C{connect} has fired, it will cancel that L{Deferred}.
        """
        rcf = RecordingClientFactory()
        e = RecordingEndpoint()
        connect(e, rcf)
        ctr = rcf.starts[0]
        ctr.disconnect()
        self.assertEqual(len(rcf.fails), 1)
        self.assertTrue(rcf.fails[0].reason.check(CancelledError))



