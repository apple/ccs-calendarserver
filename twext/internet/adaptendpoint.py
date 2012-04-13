# -*- test-case-name: twext.internet.test.test_adaptendpoint -*-
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
Adapter for old-style connectTCP/connectSSL code to use endpoints and be happy;
specifically, to receive the additional duplicate notifications that it wants to
receive, L{clientConnectionLost} and L{clientConnectionFailed} on the factory.
"""

from zope.interface import implements

from twisted.internet.interfaces import IConnector

from twisted.internet.protocol import Factory
from twisted.python import log
from twisted.python.util import FancyEqMixin



class _WrappedProtocol(object):
    """
    A wrapped protocol.
    """

    def __init__(self, wrapped, wrapper):
        self._wrapped = wrapped
        self._wrapper = wrapper


    def __getattr__(self, attr):
        """
        Relay all undefined methods to the wrapped protocol.
        """
        return getattr(self._wrapped, attr)


    def connectionLost(self, reason):
        try:
            self._wrapped.connectionLost(reason)
        except:
            log.err()
        self._wrapper.callClientConnectionLost(reason)



class LegacyConnector(FancyEqMixin, object):
    """
    Legacy IConnector interface implementation for stuff that uses endpoints.
    """
    implements(IConnector)

    compareAttributes = tuple(["wrapper"])


    def __init__(self, wrapper):
        self.wrapper = wrapper


    def getDestination(self):
        """
        I don't know, endpoints don't have a destination.
        """
        return self.wrapper.endpoint


    def connect(self):
        self.wrapper.startAttempt()


    def stopConnecting(self):
        self.wrapper._outstandingAttempt is not None


    def disconnect(self):
        self.wrapper.disconnect()



class LegacyClientFactoryWrapper(Factory):

    def __init__(self, legacyFactory, endpoint):
        self.currentlyConnecting = False
        self.legacyFactory = legacyFactory
        self.endpoint = endpoint
        self._connectedProtocol = None
        self._outstandingAttempt = None


    def buildProtocol(self, addr):
        return _WrappedProtocol(self.legacyFactory.buildProtocol(addr), self)


    def startAttempt(self):
        if self.wrapper._outstandingAttempt is not None:
            raise RuntimeError("connection already in progress")
        self.callStartedConnecting()
        d = self._outstandingAttempt = self.endpoint.connect(self)
        @d.addBoth
        def attemptDone(result):
            self._outstandingAttempt = None
            return result
        def rememberProto(proto):
            self._connectedProtocol = proto
            return proto
        d.addCallbacks(rememberProto, self.callClientConnectionFailed)


    def callStartedConnecting(self):
        self.legacyFactory.startedConnecting(LegacyConnector(self))


    def callClientConnectionLost(self, reason):
        self.legacyFactory.clientConnectionLost(LegacyConnector(self), reason)


    def callClientConnectionFailed(self, reason):
        self.legacyFactory.clientConnectionFailed(LegacyConnector(self), reason)


    def disconnect(self):
        if self._connectedProtocol is not None:
            self._connectedProtocol.transport.loseConnection()
        elif self._outstandingAttempt is not None:
            self._outstandingAttempt.cancel()



def connect(endpoint, clientFactory):
    """
    Connect a L{twisted.internet.protocol.ClientFactory} using the given
    L{twisted.internet.interfaces.IStreamClientEndpoint}.
    """
    wrap = LegacyClientFactoryWrapper(clientFactory, endpoint)
    wrap.startAttempt()
    return LegacyConnector(wrap)

