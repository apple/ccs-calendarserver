##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
Test cases for L{twext.internet.gaiendpoint}
"""

from socket import getaddrinfo, AF_INET, SOCK_STREAM

from twext.internet.gaiendpoint import GAIEndpoint
from twisted.trial.unittest import TestCase
from twisted.internet.defer import Deferred
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.task import Clock


class FakeTCPEndpoint(object):
    def __init__(self, reactor, host, port, contextFactory):
        self._reactor = reactor
        self._host = host
        self._port = port
        self._attempt = None
        self._contextFactory = contextFactory


    def connect(self, factory):
        self._attempt = Deferred()
        self._factory = factory
        return self._attempt



class GAIEndpointTestCase(TestCase):
    """
    Test cases for L{GAIEndpoint}.
    """

    def makeEndpoint(self, host="abcd.example.com", port=4321):
        gaie = GAIEndpoint(self.clock, host, port)
        gaie.subEndpoint = self.subEndpoint
        gaie.deferToThread = self.deferToSomething
        return gaie


    def subEndpoint(self, reactor, host, port, contextFactory):
        ftcpe = FakeTCPEndpoint(reactor, host, port, contextFactory)
        self.fakeRealEndpoints.append(ftcpe)
        return ftcpe


    def deferToSomething(self, func, *a, **k):
        """
        Test replacement for L{deferToThread}, which can only call
        L{getaddrinfo}.
        """
        d = Deferred()
        if func is not getaddrinfo:
            self.fail("Only getaddrinfo should be invoked in a thread.")
        self.inThreads.append((d, func, a, k))
        return d


    def gaiResult(self, family, socktype, proto, canonname, sockaddr):
        """
        A call to L{getaddrinfo} has succeeded; invoke the L{Deferred} waiting
        on it.
        """
        d, f, a, k = self.inThreads.pop(0)
        d.callback([(family, socktype, proto, canonname, sockaddr)])


    def setUp(self):
        """
        Set up!
        """
        self.inThreads = []
        self.clock = Clock()
        self.fakeRealEndpoints = []
        self.makeEndpoint()


    def test_simpleSuccess(self):
        """
        If C{getaddrinfo} gives one L{GAIEndpoint.connect}.
        """
        gaiendpoint = self.makeEndpoint()
        protos = []
        f = Factory()
        f.protocol = Protocol
        gaiendpoint.connect(f).addCallback(protos.append)
        WHO_CARES = 0
        WHAT_EVER = ""
        self.gaiResult(AF_INET, SOCK_STREAM, WHO_CARES, WHAT_EVER,
                       ("1.2.3.4", 4321))
        self.clock.advance(1.0)
        attempt = self.fakeRealEndpoints[0]._attempt
        attempt.callback(self.fakeRealEndpoints[0]._factory.buildProtocol(None))
        self.assertEqual(len(protos), 1)

