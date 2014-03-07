# -*- test-case-name: txweb2.test.test_metafd -*-
##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
Implementation of dispatching HTTP connections to child processes using
L{twext.internet.sendfdport.InheritedSocketDispatcher}.
"""
from __future__ import print_function

from zope.interface import implementer

from twext.internet.sendfdport import (
    InheritedPort, InheritedSocketDispatcher, InheritingProtocolFactory,
    IStatus)
from twext.internet.tcp import MaxAcceptTCPServer
from twext.python.log import Logger
from txweb2.channel.http import HTTPFactory
from twisted.application.service import MultiService, Service
from twisted.internet import reactor
from twisted.python.util import FancyStrMixin
from twisted.internet.tcp import Server
from twext.internet.sendfdport import IStatusWatcher

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

    @ivar site: a txweb2 'site' object, i.e. a request factory

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



@implementer(IStatus)
class WorkerStatus(FancyStrMixin, object):
    """
    The status of a worker process.
    """

    showAttributes = ("acknowledged unacknowledged total started abandoned unclosed starting stopped"
                      .split())

    def __init__(
        self,
        acknowledged=0,
        unacknowledged=0,
        total=0,
        started=0,
        abandoned=0,
        unclosed=0,
        starting=1,
        stopped=0
    ):
        """
        Create a L{ConnectionStatus} with a number of sent connections and a
        number of un-acknowledged connections.

        @param acknowledged: the number of connections which we know the
            subprocess to be presently processing; i.e. those which have been
            transmitted to the subprocess.

        @param unacknowledged: The number of connections which we have sent to
            the subprocess which have never received a status response (a
            "C{+}" status message).

        @param total: The total number of acknowledged connections over
            the lifetime of this socket.

        @param started: The number of times this worker has been started.

        @param abandoned: The number of connections which have been sent to
            this worker, but were not acknowledged at the moment that the
            worker was stopped.

        @param unclosed: The number of sockets which have been sent to the
            subprocess but not yet closed.

        @param starting: The process that owns this socket is starting. Do not
            dispatch to it until we receive the started message.

        @param stopped: The process that owns this socket has stopped. Do not
            dispatch to it.
        """
        self.acknowledged = acknowledged
        self.unacknowledged = unacknowledged
        self.total = total
        self.started = started
        self.abandoned = abandoned
        self.unclosed = unclosed
        self.starting = starting
        self.stopped = stopped


    def effective(self):
        """
        The current effective load.
        """
        return self.acknowledged + self.unacknowledged


    def active(self):
        """
        Is the subprocess associated with this socket available to dispatch to.
        i.e, this socket is neither stopped nor starting
        """
        return self.starting == 0 and self.stopped == 0


    def start(self):
        """
        The child process for this L{WorkerStatus} is about to (re)start. Reset the status to indicate it
        is starting - that should prevent any new connections being dispatched.
        """
        return self.reset(
            starting=1,
            stopped=0,
        )


    def restarted(self):
        """
        The child process for this L{WorkerStatus} has indicated it is now available to accept
        connections, so reset the starting status so this socket will be available for dispatch.
        """
        return self.reset(
            started=self.started + 1,
            starting=0,
        )


    def stop(self):
        """
        The child process for this L{WorkerStatus} has stopped. Stop the socket and clear out
        existing counters, but track abandoned connections.
        """
        return self.reset(
            acknowledged=0,
            unacknowledged=0,
            abandoned=self.abandoned + self.unacknowledged,
            starting=0,
            stopped=1,
        )


    def adjust(self, **kwargs):
        """
        Update the L{WorkerStatus} by adding the supplied values to the specified attributes.
        """
        for k, v in kwargs.items():
            newval = getattr(self, k) + v
            setattr(self, k, max(newval, 0))
        return self


    def reset(self, **kwargs):
        """
        Reset the L{WorkerStatus} by setting the supplied values in the specified attributes.
        """
        for k, v in kwargs.items():
            setattr(self, k, v)
        return self



@implementer(IStatusWatcher)
class ConnectionLimiter(MultiService, object):
    """
    Connection limiter for use with L{InheritedSocketDispatcher}.

    This depends on statuses being reported by L{ReportingHTTPFactory}
    """

    _outstandingRequests = 0

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
        self.overloaded = False


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


    # IStatusWatcher

    def initialStatus(self):
        """
        The status of a new worker added to the pool.
        """
        return WorkerStatus()


    def statusFromMessage(self, previousStatus, message):
        """
        Determine a subprocess socket's status from its previous status and a
        status message.
        """
        if message == '-':
            # A connection has gone away in a subprocess; we should start
            # accepting connections again if we paused (see
            # newConnectionStatus)
            return previousStatus.adjust(acknowledged=-1)

        elif message == '0':
            # A new process just started accepting new connections.
            return previousStatus.restarted()

        else:
            # '+' acknowledges that the subprocess has taken on the work.
            return previousStatus.adjust(
                acknowledged=1,
                unacknowledged=-1,
                total=1,
                unclosed=1,
            )


    def closeCountFromStatus(self, status):
        """
        Determine the number of sockets to close from the current status.
        """
        toClose = status.unclosed
        return (toClose, status.adjust(unclosed=-toClose))


    def newConnectionStatus(self, previousStatus):
        """
        A connection was just sent to the process, but not yet acknowledged.
        """
        return previousStatus.adjust(unacknowledged=1)


    def statusesChanged(self, statuses):
        """
        The L{InheritedSocketDispatcher} is reporting that the list of
        connection-statuses have changed. Check to see if we are overloaded
        or if there are no active processes left. If so, stop the protocol
        factory from processing more requests until capacity is back.

        (The argument to this function is currently duplicated by the
        C{self.dispatcher.statuses} attribute, which is what
        C{self.outstandingRequests} uses to compute it.)
        """
        current = sum(status.effective()
                      for status in self.dispatcher.statuses)
        self._outstandingRequests = current # preserve for or= field in log
        maximum = self.maxRequests
        overloaded = (current >= maximum)
        available = len(filter(lambda x: x.active(), self.dispatcher.statuses))
        self.overloaded = (overloaded or available == 0)
        for f in self.factories:
            if self.overloaded:
                f.loadAboveMaximum()
            else:
                f.loadNominal()


    @property # make read-only
    def outstandingRequests(self):
        return self._outstandingRequests



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


    def loadAboveMaximum(self):
        """
        The current server load has exceeded the maximum allowable.
        """
        self.myServer.myPort.stopReading()


    def loadNominal(self):
        """
        The current server load is nominal; proceed with reading requests.
        """
        self.myServer.myPort.startReading()


    @property
    def outstandingRequests(self):
        return self.limiter.outstandingRequests
