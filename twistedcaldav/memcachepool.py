##
# Copyright (c) 2008-2010 Apple Inc. All rights reserved.
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

from twisted.python.failure import Failure
from twisted.internet.address import IPv4Address
from twisted.internet.defer import Deferred, fail
from twisted.internet.protocol import ReconnectingClientFactory

from twext.python.log import LoggingMixIn
from twext.protocols.memcache import MemCacheProtocol, NoSuchCommand

class PooledMemCacheProtocol(MemCacheProtocol):
    """
    A MemCacheProtocol that will notify a connectionPool that it is ready
    to accept requests.

    @ivar factory: A L{MemCacheClientFactory} instance.
    """
    factory = None

    def connectionMade(self):
        """
        Notify our factory that we're ready to accept connections.
        """
        MemCacheProtocol.connectionMade(self)

        if self.factory.deferred is not None:
            self.factory.deferred.callback(self)
            self.factory.deferred = None



class MemCacheClientFactory(ReconnectingClientFactory, LoggingMixIn):
    """
    A client factory for MemCache that reconnects and notifies a pool of it's
    state.

    @ivar connectionPool: A managing connection pool that we notify of events.
    @ivar deferred: A L{Deferred} that represents the initial connection.
    @ivar _protocolInstance: The current instance of our protocol that we pass
        to our connectionPool.
    """
    protocol = PooledMemCacheProtocol
    connectionPool = None
    _protocolInstance = None


    def __init__(self):
        self.deferred = Deferred()


    def clientConnectionLost(self, connector, reason):
        """
        Notify the connectionPool that we've lost our connection.
        """

        if self.connectionPool.shutdown_requested:
            # The reactor is stopping; don't reconnect
            return

        self.log_error("MemCache connection lost: %s" % (reason,))
        if self._protocolInstance is not None:
            self.connectionPool.clientBusy(self._protocolInstance)

        ReconnectingClientFactory.clientConnectionLost(
            self,
            connector,
            reason)


    def clientConnectionFailed(self, connector, reason):
        """
        Notify the connectionPool that we're unable to connect
        """
        self.log_error("MemCache connection failed: %s" % (reason,))
        if self._protocolInstance is not None:
            self.connectionPool.clientBusy(self._protocolInstance)

        ReconnectingClientFactory.clientConnectionFailed(
            self,
            connector,
            reason)

    def buildProtocol(self, addr):
        """
        Attach the C{self.connectionPool} to the protocol so it can tell it,
        when we've connected.
        """
        if self._protocolInstance is not None:
            self.connectionPool.clientGone(self._protocolInstance)

        self._protocolInstance = self.protocol()
        self._protocolInstance.factory = self
        return self._protocolInstance



class MemCachePool(LoggingMixIn):
    """
    A connection pool for MemCacheProtocol instances.

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
    clientFactory = MemCacheClientFactory

    REQUEST_LOGGING_SIZE = 1024

    def __init__(self, serverAddress, maxClients=5, reactor=None):
        """
        @param serverAddress: An L{IPv4Address} indicating the server to
            connect to.
        @param maxClients: A C{int} indicating the maximum number of clients.
        @param reactor: An L{IReactorTCP{ provider used to initiate new
            connections.
        """
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

    def _newClientConnection(self):
        """
        Create a new client connection.

        @return: A L{Deferred} that fires with the L{IProtocol} instance.
        """
        self.log_debug("Initating new client connection to: %r" % (
                self._serverAddress,))
        self._logClientStats()

        self._pendingConnects += 1

        def _connected(client):
            self._pendingConnects -= 1

            return client

        factory = self.clientFactory()
        factory.noisy = False

        factory.connectionPool = self

        self._reactor.connectTCP(self._serverAddress.host,
                                 self._serverAddress.port,
                                 factory)
        d = factory.deferred

        d.addCallback(_connected)
        return d


    def _performRequestOnClient(self, client, command, *args, **kwargs):
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
        def _freeClientAfterRequest(result):
            self.clientFree(client)
            return result

        def _reportError(failure):
            """
            Upon memcache error, log the failed request along with the error
            message and free the client.
            """
            self.log_error("Memcache error: %s; request: %s %s" %
                (failure.value, command,
                " ".join(args)[:self.REQUEST_LOGGING_SIZE],))
            self.clientFree(client)

        self.clientBusy(client)
        method = getattr(client, command, None)
        if method is not None:
            d = method(*args, **kwargs)
        else:
            d = fail(Failure(NoSuchCommand()))

        d.addCallbacks(_freeClientAfterRequest, _reportError)

        return d


    def performRequest(self, command, *args, **kwargs):
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

        if len(self._freeClients) > 0:
            client = self._freeClients.pop()

            d = self._performRequestOnClient(
                client, command, *args, **kwargs)

        elif len(self._busyClients) + self._pendingConnects >= self._maxClients:
            d = Deferred()
            self._commands.append((d, command, args, kwargs))
            self.log_debug("Command queued: %s, %r, %r" % (
                    command, args, kwargs))
            self._logClientStats()

        else:
            d = self._newClientConnection()
            d.addCallback(self._performRequestOnClient,
                          command, *args, **kwargs)

        return d


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

            _ign_d = self.performRequest(
                command, *args, **kwargs)

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


    def get(self, *args, **kwargs):
        return self.performRequest('get', *args, **kwargs)

    def set(self, *args, **kwargs):
        return self.performRequest('set', *args, **kwargs)

    def checkAndSet(self, *args, **kwargs):
        return self.performRequest('checkAndSet', *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.performRequest('delete', *args, **kwargs)

    def add(self, *args, **kwargs):
        return self.performRequest('add', *args, **kwargs)

    def incr(self, *args, **kwargs):
        return self.performRequest('increment', *args, **kwargs)

    def decr(self, *args, **kwargs):
        return self.performRequest('decrement', *args, **kwargs)

    def flushAll(self, *args, **kwargs):
        return self.performRequest('flushAll', *args, **kwargs)



class CachePoolUserMixIn(object):
    """
    A mixin that returns a saved cache pool or fetches the default cache pool.

    @ivar _cachePool: A saved cachePool.
    """
    _cachePool = None
    _cachePoolHandle = "Default"

    def getCachePool(self):
        if self._cachePool is None:
            return defaultCachePool(self._cachePoolHandle)

        return self._cachePool



_memCachePools = {}         # Maps a name to a pool object
_memCachePoolHandler = {}   # Maps a handler id to a named pool

def installPools(pools, maxClients=5, reactor=None):
    
    for name, pool in pools.items():
        if pool["ClientEnabled"]:
            _installPool(
                name,
                pool["HandleCacheTypes"],
                IPv4Address(
                    "TCP",
                    pool["BindAddress"],
                    pool["Port"],
                ),
                maxClients,
                reactor,
            )

def _installPool(name, handleTypes, serverAddress, maxClients=5, reactor=None):

    pool = MemCachePool(serverAddress,
                                 maxClients=maxClients,
                                 reactor=None)
    _memCachePools[name] = pool

    for handle in handleTypes:
        _memCachePoolHandler[handle] = pool

def defaultCachePool(name):
    if name not in _memCachePoolHandler:
        name = "Default"
    return _memCachePoolHandler[name]
