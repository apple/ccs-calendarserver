# -*- test-case-name: twext.web2.test.test_metafd -*-
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
##

from twext.internet.sendfdport import (
    InheritedPort, InheritedSocketDispatcher, InheritingProtocolFactory)
from twext.internet.tcp import MaxAcceptTCPServer
from twext.python.log import Logger
from twext.web2.channel.http import HTTPFactory
from twisted.application.service import MultiService, Service
from twisted.internet import reactor
from twisted.internet.tcp import Server

log = Logger()



class JustEnoughLikeAPort(object):
    """
    Fake out just enough of L{tcp.Port} to be acceptable to
    L{tcp.Server}...
    """
    _realPortNumber = 'inherited'



class ReportingHTTPService(Service, object):
    """
    Service which starts up an HTTP server that can report back to its parent
    process via L{InheritedPort}.

    This is instantiated in the I{worker process}.

    @ivar site: a twext.web2 'site' object, i.e. a request factory

    @ivar fd: the file descriptor of a UNIX socket being used to receive
        connections from a master process calling accept()
    @type fd: C{int}

    @ivar contextFactory: A context factory for building SSL/TLS connections
        for inbound connections tagged with the string 'SSL' as their
        descriptive data, or None if SSL is not enabled for this server.
    @type contextFactory: L{twisted.internet.ssl.ContextFactory} or C{NoneType}
    """

    _connectionCount = 0

    def __init__(self, site, fd, contextFactory):
        self.contextFactory = contextFactory
        # Unlike other 'factory' constructions, config.MaxRequests and
        # config.MaxAccepts are dealt with in the master process, so we don't
        # need to propagate them here.
        self.site = site
        self.fd = fd


    def startService(self):
        """
        Start reading on the inherited port.
        """
        Service.startService(self)
        self.reportingFactory = ReportingHTTPFactory(self.site, vary=True)
        inheritedPort = self.reportingFactory.inheritedPort = InheritedPort(
            self.fd, self.createTransport, self.reportingFactory
        )
        inheritedPort.startReading()
        inheritedPort.reportStatus("0")


    def stopService(self):
        """
        Stop reading on the inherited port.

        @return: a Deferred which fires after the last outstanding request is
            complete.
        """
        Service.stopService(self)
        # XXX stopping should really be destructive, because otherwise we will
        # always leak a file descriptor; i.e. this shouldn't be restartable.
        self.reportingFactory.inheritedPort.stopReading()

        # Let any outstanding requests finish
        return self.reportingFactory.allConnectionsClosed()


    def createTransport(self, skt, peer, data, protocol):
        """
        Create a TCP transport, from a socket object passed by the parent.
        """
        self._connectionCount += 1
        transport = Server(skt, protocol, peer, JustEnoughLikeAPort,
                           self._connectionCount, reactor)
        if data == 'SSL':
            transport.startTLS(self.contextFactory)
        transport.startReading()
        return transport



class ReportingHTTPFactory(HTTPFactory):
    """
    An L{HTTPFactory} which reports its status to a
    L{InheritedPort<twext.internet.sendfdport.InheritedPort>}.

    Since this is processing application-level bytes, it is of course
    instantiated in the I{worker process}, as is
    L{InheritedPort<twext.internet.sendfdport.InheritedPort>}.

    @ivar inheritedPort: an L{InheritedPort} to report status (the current
        number of outstanding connections) to.  Since this - the
        L{ReportingHTTPFactory} - needs to be instantiated to be passed to
        L{InheritedPort}'s constructor, this attribute must be set afterwards
        but before any connections have occurred.
    """

    def _report(self, message):
        """
        Report a status message to the parent.
        """
        self.inheritedPort.reportStatus(message)


    def addConnectedChannel(self, channel):
        """
        Add the connected channel, and report the current number of open
        channels to the listening socket in the parent process.
        """
        HTTPFactory.addConnectedChannel(self, channel)
        self._report("+")


    def removeConnectedChannel(self, channel):
        """
        Remove the connected channel, and report the current number of open
        channels to the listening socket in the parent process.
        """
        HTTPFactory.removeConnectedChannel(self, channel)
        self._report("-")



class ConnectionLimiter(MultiService, object):
    """
    Connection limiter for use with L{InheritedSocketDispatcher}.

    This depends on statuses being reported by L{ReportingHTTPFactory}
    """

    def __init__(self, maxAccepts, maxRequests):
        """
        Create a L{ConnectionLimiter} with an associated dispatcher and
        list of factories.
        """
        MultiService.__init__(self)
        self.factories = []
        # XXX dispatcher needs to be a service, so that it can shut down its
        # sub-sockets.
        self.dispatcher = InheritedSocketDispatcher(self)
        self.maxAccepts = maxAccepts
        self.maxRequests = maxRequests


    def startService(self):
        """
        Start up multiservice, then start up the dispatcher.
        """
        super(ConnectionLimiter, self).startService()
        self.dispatcher.startDispatching()


    def addPortService(self, description, port, interface, backlog,
                       serverServiceMaker=MaxAcceptTCPServer):
        """
        Add a L{MaxAcceptTCPServer} to bind a TCP port to a socket description.
        """
        lipf = LimitingInheritingProtocolFactory(self, description)
        self.factories.append(lipf)
        serverServiceMaker(
            port, lipf,
            interface=interface,
            backlog=backlog
        ).setServiceParent(self)


    # implementation of implicit statusWatcher interface required by
    # InheritedSocketDispatcher

    def statusFromMessage(self, previousStatus, message):
        """
        Determine a subprocess socket's status from its previous status and a
        status message.
        """
        if message == '-':
            # A connection has gone away in a subprocess; we should start
            # accepting connections again if we paused (see
            # newConnectionStatus)
            result = self.intWithNoneAsZero(previousStatus) - 1
            if result < 0:
                log.error("metafd: trying to decrement status below zero")
                result = 0
        elif message == '0':
            # A new process just started accepting new connections; zero
            # out its expected load, but only if previous status is still
            # None
            result = 0 if previousStatus is None else previousStatus
            if previousStatus is None:
                result = 0
            else:
                log.error("metafd: trying to zero status that is not None")
                result = previousStatus
        else:
            # '+' is just an acknowledgement of newConnectionStatus, so we can
            # ignore it.
            result = self.intWithNoneAsZero(previousStatus)
        return result


    def newConnectionStatus(self, previousStatus):
        """
        Determine the effect of a new connection being sent on a subprocess
        socket.
        """
        result = self.intWithNoneAsZero(previousStatus) + 1
        return result


    def statusesChanged(self, statuses):
        """
        The L{InheritedSocketDispatcher} is reporting that the list of
        connection-statuses have changed.

        (The argument to this function is currently duplicated by the
        C{self.dispatcher.statuses} attribute, which is what
        C{self.outstandingRequests} uses to compute it.)
        """
        current = self.outstandingRequests + 1
        maximum = self.maxRequests
        overloaded = (current >= maximum)
        if overloaded:
            for f in self.factories:
                f.myServer.myPort.stopReading()
        else:
            for f in self.factories:
                f.myServer.myPort.startReading()


    def intWithNoneAsZero(self, x):
        """
        Convert 'x' to an C{int}, unless x is C{None}, in which case return 0.
        """
        if x is None:
            return 0
        else:
            return int(x)


    @property
    def outstandingRequests(self):
        outstanding = 0
        for status in self.dispatcher.statuses:
            outstanding += self.intWithNoneAsZero(status)
        return outstanding



class LimitingInheritingProtocolFactory(InheritingProtocolFactory):
    """
    An L{InheritingProtocolFactory} that supports the implicit factory contract
    required by L{MaxAcceptTCPServer}/L{MaxAcceptTCPPort}.

    Since L{InheritingProtocolFactory} is instantiated in the I{master
    process}, so is L{LimitingInheritingProtocolFactory}.

    @ivar outstandingRequests: a read-only property for the number of currently
        active connections.

    @ivar maxAccepts: The maximum number of times to call 'accept()' in a
        single reactor loop iteration.

    @ivar maxRequests: The maximum number of concurrent connections to accept
        at once - note that this is for the I{entire server}, whereas the value
        in the configuration file is for only a single process.
    """

    def __init__(self, limiter, description):
        super(LimitingInheritingProtocolFactory, self).__init__(
            limiter.dispatcher, description)
        self.limiter = limiter
        self.maxAccepts = limiter.maxAccepts
        self.maxRequests = limiter.maxRequests


    @property
    def outstandingRequests(self):
        return self.limiter.outstandingRequests
