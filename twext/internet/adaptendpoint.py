# -*- test-case-name: twext.internet.test.test_adaptendpoint -*-
##
# Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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

__all__ = [
    "connect"
]



class _WrappedProtocol(object):
    """
    A protocol providing a thin wrapper that relays the connectionLost
    notification.
    """

    def __init__(self, wrapped, wrapper):
        """
        @param wrapped: the wrapped L{IProtocol} provider, to which all methods
            will be relayed.

        @param wrapper: The L{LegacyClientFactoryWrapper} that holds the
            relevant L{ClientFactory}.
        """
        self._wrapped = wrapped
        self._wrapper = wrapper


    def __getattr__(self, attr):
        """
        Relay all undefined methods to the wrapped protocol.
        """
        return getattr(self._wrapped, attr)


    def connectionLost(self, reason):
        """
        When the connection is lost, return the connection.
        """
        try:
            self._wrapped.connectionLost(reason)
        except:
            log.err()
        self._wrapper.legacyFactory.clientConnectionLost(self._wrapper, reason)



class LegacyClientFactoryWrapper(Factory):
    implements(IConnector)

    def __init__(self, legacyFactory, endpoint):
        self.currentlyConnecting = False
        self.legacyFactory = legacyFactory
        self.endpoint = endpoint
        self._connectedProtocol = None
        self._outstandingAttempt = None


    def getDestination(self):
        """
        Implement L{IConnector.getDestination}.

        @return: the endpoint being connected to as the destination.
        """
        return self.endpoint


    def buildProtocol(self, addr):
        """
        Implement L{Factory.buildProtocol} to return a wrapper protocol that
        will capture C{connectionLost} notifications.

        @return: a L{Protocol}.
        """
        return _WrappedProtocol(self.legacyFactory.buildProtocol(addr), self)


    def connect(self):
        """
        Implement L{IConnector.connect} to connect the endpoint.
        """
        if self._outstandingAttempt is not None:
            raise RuntimeError("connection already in progress")
        self.legacyFactory.startedConnecting(self)
        d = self._outstandingAttempt = self.endpoint.connect(self)
        @d.addBoth
        def attemptDone(result):
            self._outstandingAttempt = None
            return result
        def rememberProto(proto):
            self._connectedProtocol = proto
            return proto
        def callClientConnectionFailed(reason):
            self.legacyFactory.clientConnectionFailed(self, reason)
        d.addCallbacks(rememberProto, callClientConnectionFailed)


    def disconnect(self):
        """
        Implement L{IConnector.disconnect}.
        """
        if self._connectedProtocol is not None:
            self._connectedProtocol.transport.loseConnection()
        elif self._outstandingAttempt is not None:
            self._outstandingAttempt.cancel()


    def stopConnecting(self):
        """
        Implement L{IConnector.stopConnecting}.
        """
        if self._outstandingAttempt is None:
            raise RuntimeError("no connection attempt in progress")
        self.disconnect()



def connect(endpoint, clientFactory):
    """
    Connect a L{twisted.internet.protocol.ClientFactory} to a remote host using
    the given L{twisted.internet.interfaces.IStreamClientEndpoint}.  This relays
    C{clientConnectionFailed} and C{clientConnectionLost} notifications as
    legacy code using the L{ClientFactory} interface, such as,
    L{ReconnectingClientFactory} would expect.

    @param endpoint: The endpoint to connect to.
    @type endpoint: L{twisted.internet.interfaces.IStreamClientEndpoint}

    @param clientFactory: The client factory doing the connecting.
    @type clientFactory: L{twisted.internet.protocol.ClientFactory}

    @return: A connector object representing the connection attempt just
        initiated.
    @rtype: L{IConnector}
    """
    wrap = LegacyClientFactoryWrapper(clientFactory, endpoint)
    wrap.noisy = clientFactory.noisy # relay the noisy attribute to the wrapper
    wrap.connect()
    return wrap

