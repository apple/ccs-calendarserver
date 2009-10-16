##
# Copyright (c) 2009 Apple Inc. All rights reserved.
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

__all__ = [
    "installPools",
    "installPool",
    "getReverseProxyPool",
]

from twext.internet.ssl import ChainingOpenSSLContextFactory
from twisted.internet.address import IPv4Address
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.web2 import responsecode
from twisted.web2.client.http import HTTPClientProtocol
from twisted.web2.http import StatusResponse, HTTPError
from twistedcaldav.config import config
from twistedcaldav.log import LoggingMixIn
import OpenSSL
import urlparse

class ReverseProxyClientFactory(ReconnectingClientFactory, LoggingMixIn):
    """
    A client factory for HTTPClient that reconnects and notifies a pool of it's
    state.

    @ivar connectionPool: A managing connection pool that we notify of events.
    @ivar deferred: A L{Deferred} that represents the initial connection.
    @ivar _protocolInstance: The current instance of our protocol that we pass
        to our connectionPool.
    """
    protocol = HTTPClientProtocol
    connectionPool = None
    maxRetries = 2

    def __init__(self, reactor, deferred):
        self.reactor = reactor
        self.instance = None
        self.deferred = deferred

    def clientConnectionLost(self, connector, reason):
        """
        Notify the connectionPool that we've lost our connection.
        """

        if self.connectionPool.shutdown_requested:
            # The reactor is stopping; don't reconnect
            return

        self.log_error("ReverseProxy connection lost: %s" % (reason,))
        if self.instance is not None:
            self.connectionPool.clientGone(self.instance)
#        if self.instance is not None:
#            self.connectionPool.clientBusy(self.instance)
#
#        ReconnectingClientFactory.clientConnectionLost(
#            self,
#            connector,
#            reason
#        )

    def clientConnectionFailed(self, connector, reason):
        """
        Notify the connectionPool that we're unable to connect
        """
        self.log_error("ReverseProxy connection failed: %s" % (reason,))
#        if self.instance is not None:
#            self.connectionPool.clientBusy(self.instance)

#        ReconnectingClientFactory.clientConnectionFailed(
#            self,
#            connector,
#            reason
#        )
        if hasattr(self, "deferred"):
            self.reactor.callLater(0, self.deferred.errback, reason)
            del self.deferred

    def buildProtocol(self, addr):
        if self.instance is not None:
            self.connectionPool.clientGone(self.instance)

        self.instance = self.protocol()
        self.reactor.callLater(0, self.deferred.callback, self.instance)
        del self.deferred
        return self.instance

class ReverseProxyPool(LoggingMixIn):
    """
    A connection pool for HTTPClientProtocol instances.

    @ivar clientFactory: The L{ClientFactory} implementation that will be used
        for each protocol.

    @ivar _maxClients: A C{int} indicating the maximum number of clients.
    @ivar _serverAddress: An L{IAddress} provider indicating the server to
        connect to.  (Only L{IPv4Address} currently supported.)
    @ivar _reactor: The L{IReactorTCP} provider used to initiate new
        connections.

    @ivar _busyClients: A C{set} that contains all currently busy clients.
    @ivar _freeClients: A C{set} that contains all currently free clients.
    @ivar _pendingConnects: A C{int} indicating how many connections are in
        progress.
    """
    clientFactory = ReverseProxyClientFactory

    def __init__(self, scheme, serverAddress, maxClients=5, reactor=None):
        """
        @param serverAddress: An L{IPv4Address} indicating the server to
            connect to.
        @param maxClients: A C{int} indicating the maximum number of clients.
        @param reactor: An L{IReactorTCP{ provider used to initiate new
            connections.
        """
        self._scheme = scheme
        self._serverAddress = serverAddress
        self._maxClients = maxClients

        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor

        self.shutdown_deferred = None
        self.shutdown_requested = False
        reactor.addSystemEventTrigger('before', 'shutdown', self._shutdownCallback)

        self._busyClients = set([])
        self._freeClients = set([])
        self._pendingConnects = 0
        self._commands = []

    def _isIdle(self):
        return (
            len(self._busyClients) == 0 and
            len(self._commands) == 0 and
            self._pendingConnects == 0
        )

    def _shutdownCallback(self):
        self.shutdown_requested = True
        if self._isIdle():
            return None
        self.shutdown_deferred = Deferred()
        return self.shutdown_deferred

    @inlineCallbacks
    def _newClientConnection(self):
        """
        Create a new client connection.

        @return: A L{Deferred} that fires with the L{IProtocol} instance.
        """
        self.log_debug("Initiating new client connection to: %s" % (self._serverAddress,))
        self._logClientStats()

        self._pendingConnects += 1

        def _connected(client):
            self._pendingConnects -= 1

            return client

        d = Deferred()
        factory = self.clientFactory(self._reactor, d)
        factory.noisy = False

        factory.connectionPool = self

        try:
            if self._scheme == "https":
                context = ChainingOpenSSLContextFactory(config.SSLPrivateKey, config.SSLCertificate, certificateChainFile=config.SSLAuthorityChain, sslmethod=getattr(OpenSSL.SSL, config.SSLMethod))
                self._reactor.connectSSL(self._serverAddress.host, self._serverAddress.port, factory, context)
            elif self._scheme == "http":
                self._reactor.connectTCP(self._serverAddress.host, self._serverAddress.port, factory)
            else:
                raise ValueError("URL scheme for client pool not supported")
            client = (yield d)
        except:
            raise HTTPError(StatusResponse(responsecode.BAD_GATEWAY, "Could not connect to reverse proxy host."))
        finally:
            self._pendingConnects -= 1
        returnValue(client)

    @inlineCallbacks
    def _performRequestOnClient(self, client, request, *args, **kwargs):
        """
        Perform the given request on the given client.

        @param client: A L{PooledMemCacheProtocol} that will be used to perform
            the given request.

        @param command: A C{str} representing an attribute of
            L{MemCacheProtocol}.
        @parma args: Any positional arguments that should be passed to
            C{command}.
        @param kwargs: Any keyword arguments that should be passed to
            C{command}.

        @return: A L{Deferred} that fires with the result of the given command.
        """

        self.clientBusy(client)
        try:
            response = (yield client.submitRequest(request, closeAfter=False))
        finally:
            self.clientFree(client)

        returnValue(response)

    @inlineCallbacks
    def submitRequest(self, request, *args, **kwargs):
        """
        Select an available client and perform the given request on it.

        @param command: A C{str} representing an attribute of
            L{MemCacheProtocol}.
        @parma args: Any positional arguments that should be passed to
            C{command}.
        @param kwargs: Any keyword arguments that should be passed to
            C{command}.

        @return: A L{Deferred} that fires with the result of the given command.
        """

        client = None
        if len(self._freeClients) > 0:
            client = self._freeClients.pop()

        elif len(self._busyClients) + self._pendingConnects >= self._maxClients:
            d = Deferred()
            self._commands.append((d, request, args, kwargs))
            self.log_debug("Request queued: %s, %r, %r" % (request, args, kwargs))
            self._logClientStats()
            response = (yield d)
        else:
            client = (yield self._newClientConnection())

        if client:
            response = (yield self._performRequestOnClient(client, request, *args, **kwargs))

        returnValue(response)

    def _logClientStats(self):
        self.log_debug("Clients #free: %d, #busy: %d, "
                       "#pending: %d, #queued: %d" % (
                len(self._freeClients),
                len(self._busyClients),
                self._pendingConnects,
                len(self._commands)))

    def clientGone(self, client):
        """
        Notify that the given client is to be removed from the pool completely.

        @param client: An instance of L{PooledMemCacheProtocol}.
        """
        if client in self._busyClients:
            self._busyClients.remove(client)

        elif client in self._freeClients:
            self._freeClients.remove(client)

        self.log_debug("Removed client: %r" % (client,))
        self._logClientStats()

    def clientBusy(self, client):
        """
        Notify that the given client is being used to complete a request.

        @param client: An instance of C{self.clientFactory}
        """

        if client in self._freeClients:
            self._freeClients.remove(client)

        self._busyClients.add(client)

        self.log_debug("Busied client: %r" % (client,))
        self._logClientStats()

    def clientFree(self, client):
        """
        Notify that the given client is free to handle more requests.

        @param client: An instance of C{self.clientFactory}
        """
        if client in self._busyClients:
            self._busyClients.remove(client)

        self._freeClients.add(client)

        if self.shutdown_deferred and self._isIdle():
            self.shutdown_deferred.callback(None)

        if len(self._commands) > 0:
            d, command, args, kwargs = self._commands.pop(0)

            self.log_debug("Performing Queued Command: %s, %r, %r" % (
                    command, args, kwargs))
            self._logClientStats()

            _ign_d = self.performRequest(command, *args, **kwargs)

            _ign_d.addCallback(d.callback)

        self.log_debug("Freed client: %r" % (client,))
        self._logClientStats()

    def suggestMaxClients(self, maxClients):
        """
        Suggest the maximum number of concurrently connected clients.

        @param maxClients: A C{int} indicating how many client connections we
            should keep open.
        """
        self._maxClients = maxClients

_clientPools = {}     # Maps a host:port to a pool object

def installPools(hosts, maxClients=5, reactor=None):
    
    for name, url in hosts:
        installPool(
            name,
            url,
            maxClients,
            reactor,
        )

def installPool(name, url, maxClients=5, reactor=None):

    parsedURL = urlparse.urlparse(url)
    pool = ReverseProxyPool(
        parsedURL.scheme,
        IPv4Address(
            "TCP",
            parsedURL.hostname,
            parsedURL.port,
        ),
        maxClients,
        reactor,
    )
    _clientPools[name] = pool

def getReverseProxyPool(name):
    return _clientPools[name]
