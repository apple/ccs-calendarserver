##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
Extentions to twisted.internet.tcp.
"""

__all__ = [
    "MaxAcceptTCPServer",
    "MaxAcceptSSLServer",
]

import socket
from OpenSSL import SSL

from twisted.application import internet
from twisted.internet import tcp, ssl
from twisted.internet.defer import succeed

from twext.python.log import Logger

log = Logger()


class MaxAcceptPortMixin(object):
    """
    Mixin for resetting maxAccepts.
    """
    def doRead(self):
        self.numberAccepts = min(
            self.factory.maxRequests - self.factory.outstandingRequests,
            self.factory.maxAccepts
        )
        tcp.Port.doRead(self)



class MaxAcceptTCPPort(MaxAcceptPortMixin, tcp.Port):
    """
    Use for non-inheriting tcp ports.
    """



class MaxAcceptSSLPort(MaxAcceptPortMixin, ssl.Port):
    """
    Use for non-inheriting SSL ports.
    """



class InheritedTCPPort(MaxAcceptTCPPort):
    """
    A tcp port which uses an inherited file descriptor.
    """

    def __init__(self, fd, factory, reactor):
        tcp.Port.__init__(self, 0, factory, reactor=reactor)
        # MOR: careful because fromfd dup()'s the socket, so we need to
        # make sure we don't leak file descriptors
        self.socket = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        self._realPortNumber = self.port = self.socket.getsockname()[1]

    def createInternetSocket(self):
        return self.socket

    def startListening(self):
        log.info("%s starting on %s" % (self.factory.__class__, self._realPortNumber))
        self.factory.doStart()
        self.connected = 1
        self.fileno = self.socket.fileno
        self.numberAccepts = self.factory.maxRequests
        self.startReading()


class InheritedSSLPort(InheritedTCPPort):
    """
    An SSL port which uses an inherited file descriptor.
    """

    _socketShutdownMethod = 'sock_shutdown'

    transport = ssl.Server

    def __init__(self, fd, factory, ctxFactory, reactor):
        InheritedTCPPort.__init__(self, fd, factory, reactor)
        self.ctxFactory = ctxFactory
        self.socket = SSL.Connection(self.ctxFactory.getContext(), self.socket)

    def _preMakeConnection(self, transport):
        transport._startTLS()
        return tcp.Port._preMakeConnection(self, transport)


def _allConnectionsClosed(protocolFactory):
    """
    Check to see if protocolFactory implements allConnectionsClosed( ) and
    if so, call it.  Otherwise, return immediately.
    This allows graceful shutdown by waiting for all requests to be completed.

    @param protocolFactory: (usually) an HTTPFactory implementing allConnectionsClosed
        which returns a Deferred which fires when all connections are closed.
    @return: A Deferred firing None when all connections are closed, or immediately
        if the given factory does not track its connections (e.g.
        InheritingProtocolFactory)
    """
    if hasattr(protocolFactory, "allConnectionsClosed"):
        return protocolFactory.allConnectionsClosed()
    return succeed(None)


class MaxAcceptTCPServer(internet.TCPServer):
    """
    TCP server which will uses MaxAcceptTCPPorts (and optionally,
    inherited ports)

    @ivar myPort: When running, this is set to the L{IListeningPort} being
        managed by this service.
    """

    def __init__(self, *args, **kwargs):
        internet.TCPServer.__init__(self, *args, **kwargs)
        self.protocolFactory = self.args[1]
        self.protocolFactory.myServer = self
        self.inherit = self.kwargs.get("inherit", False)
        self.backlog = self.kwargs.get("backlog", None)
        self.interface = self.kwargs.get("interface", None)

    def _getPort(self):
        from twisted.internet import reactor

        if self.inherit:
            port = InheritedTCPPort(self.args[0], self.args[1], reactor)
        else:
            port = MaxAcceptTCPPort(self.args[0], self.args[1], self.backlog, self.interface, reactor)

        port.startListening()
        self.myPort = port
        return port

    def stopService(self):
        """
        Wait for outstanding requests to finish
        @return: a Deferred which fires when all outstanding requests are complete
        """
        internet.TCPServer.stopService(self)
        return _allConnectionsClosed(self.protocolFactory)


class MaxAcceptSSLServer(internet.SSLServer):
    """
    SSL server which will uses MaxAcceptSSLPorts (and optionally,
    inherited ports)
    """

    def __init__(self, *args, **kwargs):
        internet.SSLServer.__init__(self, *args, **kwargs)
        self.protocolFactory = self.args[1]
        self.protocolFactory.myServer = self
        self.inherit = self.kwargs.get("inherit", False)
        self.backlog = self.kwargs.get("backlog", None)
        self.interface = self.kwargs.get("interface", None)

    def _getPort(self):
        from twisted.internet import reactor

        if self.inherit:
            port = InheritedSSLPort(self.args[0], self.args[1], self.args[2], reactor)
        else:
            port = MaxAcceptSSLPort(self.args[0], self.args[1], self.args[2], self.backlog, self.interface, self.reactor)

        port.startListening()
        self.myPort = port
        return port

    def stopService(self):
        """
        Wait for outstanding requests to finish
        @return: a Deferred which fires when all outstanding requests are complete
        """
        internet.SSLServer.stopService(self)
        # TODO: check for an ICompletionWaiter interface
        return _allConnectionsClosed(self.protocolFactory)


