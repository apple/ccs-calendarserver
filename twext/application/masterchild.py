##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
Application container for a service consisting of a master process that
accepts connections and dispatches them via inherited file descriptors to
child processes.
"""

# python -c 'from twisted.scripts.twistd import run; run()' \
#   -n -l - master --protocol=twext.protocols.echo.EchoProtocol --port=8080

from __future__ import print_function


__all__ = [
    "MasterOptions",
    "MasterServiceMaker",
    "ChildOptions",
    "ChildServiceMaker",
]


import sys
from os import close, unlink
from tempfile import mkstemp
from functools import total_ordering

from zope.interface import implementer

from twisted.python.sendmsg import getsockfam
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass
from twisted.python.util import FancyStrMixin
from twisted.application.service import MultiService, Service
from twisted.application.service import IServiceMaker
from twisted.application.internet import TCPServer
from twisted.protocols.policies import WrappingFactory, ProtocolWrapper
from twisted.internet.protocol import Protocol
from twisted.internet.protocol import ServerFactory
from twisted.internet.protocol import ProcessProtocol

from twext.python.log import Logger
from twext.internet.sendfdport import InheritingProtocolFactory
from twext.internet.sendfdport import InheritedSocketDispatcher
from twext.internet.sendfdport import IStatusWatcher
from twext.internet.sendfdport import InheritedPort



class MasterOptions(Options):
    """
    Options for a master process.
    """

    def opt_protocol(self, value):
        """
        Protocol and port (specify as proto:port).
        """
        try:
            protocol, port = value.split(":")
        except ValueError:
            if ":" in value:
                raise UsageError("Invalid protocol argument.")
            else:
                raise UsageError("Port is required in protocol argument.")

        # Validate protocol name
        try:
            protocolClass = namedClass(protocol)
        except (ValueError, AttributeError):
            raise UsageError("Unknown protocol: {0}".format(protocol))

        try:
            if not issubclass(protocolClass, Protocol):
                raise TypeError()
        except TypeError:
            raise UsageError("Not a protocol: {0}".format(protocol))

        # Validate port number
        try:
            try:
                port = int(port)
            except ValueError:
                raise ValueError("not an integer")

            if port < 0:
                raise ValueError("must be >=0")

        except ValueError as e:
            raise UsageError(
                "Invalid port number {0}: {1}".format(port, e)
            )

        protocols = self.setdefault("protocols", [])

        for (otherProtocol, otherPort) in protocols:
            # FIXME: Raise here because we don't properly handle multiple
            # protocols yet.
            raise UsageError("Only one protocol may be specified.")

            if otherPort == port:
                if otherProtocol == protocol:
                    return

                raise UsageError(
                    "Port {0} cannot be registered more than once "
                    "for different protocols: ({1}, {2})",
                    otherProtocol, protocol
                )

        protocols.append((protocol, port))


    def postOptions(self):
        for (parameter, key) in [("protocol", "protocols")]:
            if key not in self:
                raise UsageError("{0} parameter is required".format(parameter))



class SpawningInheritingProtocolFactory(InheritingProtocolFactory):
    """
    Protocol factory for a spawning service.
    """

    def __init__(self, dispatcher, spawningService, description):
        super(SpawningInheritingProtocolFactory, self).__init__(
            dispatcher, description
        )
        self.spawningService = spawningService


    def sendSocket(self, socketObject):
        self.spawningService.socketWillArriveForProtocol(self.description)
        super(SpawningInheritingProtocolFactory, self).sendSocket(socketObject)



@implementer(IStatusWatcher)
class MasterService(MultiService, object):
    """
    Service for master processes.
    """

    log = Logger()


    def __init__(self):
        MultiService.__init__(self)

        # Dispatcher
        self.dispatcher = InheritedSocketDispatcher(self)

        # Child Processes
        self.log.info("Setting up master/child spawning service...")
        self.spawningService = ChildSpawningService(self.dispatcher)
        self.spawningService.setServiceParent(self)


    def addProtocol(self, protocol, port):
        self.log.info(
            "Setting service for protocol {protocol!r} on port {port}...",
            protocol=protocol, port=port,
        )

        # TCP Service
        tcpFactory = SpawningInheritingProtocolFactory(
            self.dispatcher, self.spawningService, protocol
        )
        tcpService = TCPServer(port, tcpFactory)

        tcpService.setServiceParent(self)


    def startService(self):
        """
        Start up multiservice, then start up the dispatcher.
        """
        super(MasterService, self).startService()
        self.dispatcher.startDispatching()


    # IStatusWatcher

    @staticmethod
    def initialStatus():
        return ChildStatus()


    @staticmethod
    def newConnectionStatus(previousStatus):
        return previousStatus + ChildStatus(unacknowledged=1)


    @staticmethod
    def statusFromMessage(previousStatus, message):
        if message == "-":
            # A connection has gone away in a subprocess; we should start
            # accepting connections again if we paused (see
            # newConnectionStatus)
            return previousStatus - ChildStatus(acknowledged=1)

        elif message == "0":
            # A new process just started accepting new connections.  It might
            # still have some unacknowledged connections, but any connections
            # that it acknowledged working on are now completed.  (We have no
            # way of knowing whether the acknowledged connections were acted
            # upon or dropped, so we have to treat that number with a healthy
            # amount of skepticism.)

            # Do some sanity checks... no attempt to fix, but log critically
            # if there are unexpected connection counts, as that means we
            # don't know what's going on with our connection management.

            def checkForWeirdness(what, expected):
                n = getattr(previousStatus, what)
                if n != expected:
                    # Upgrade to critical when logging is updated
                    MasterService.log.critical(
                        "New process has {count} {type} connections, "
                        "expected {expected}."
                        .format(count=n, type=what, expected=expected)
                    )

            checkForWeirdness("acknowledged", 0)
            checkForWeirdness("unacknowledged", 1)
            checkForWeirdness("unclosed", 1)

            return previousStatus

        elif message == "+":
            # Acknowledges that the subprocess has taken on the work.
            return (
                previousStatus +
                ChildStatus(acknowledged=1, unacknowledged=-1, unclosed=1)
            )

        else:
            raise AssertionError("Unknown message: {0}".format(message))


    @staticmethod
    def closeCountFromStatus(previousStatus):
        toClose = previousStatus.unclosed
        return (toClose, previousStatus - ChildStatus(unclosed=toClose))


    def statusesChanged(self, statuses):
        # FIXME: This isn't in IStatusWatcher, but is called by
        # InheritedSocketDispatcher.

        self.log.info("Status changed: {0}".format(tuple(statuses)))

        # current = sum(
        #     status.effective()
        #     for status in self.dispatcher.statuses
        # )

        # maximum = self.maxRequests
        # overloaded = (current >= maximum)

        # for f in self.factories:
        #     if overloaded:
        #         f.loadAboveMaximum()
        #     else:
        #         f.loadNominal()



@implementer(IServiceMaker)
class MasterServiceMaker(object):
    """
    Master process service maker.
    """
    log = Logger()


    def __init__(self):
        self.tapname = "master"
        self.description = self.__class__.__doc__
        self.options = MasterOptions


    def makeService(self, options):
        service = MasterService()

        for protocol, port in options["protocols"]:
            service.addProtocol(protocol, port)

        return service



class ChildProcess(object):
    """
    Child process.
    """

    def __init__(self, transport, protocol):
        self.transport = transport
        self.protocol = protocol



class ChildSpawningService(Service, object):
    """
    Service that spawns children as necessary.
    """

    log = Logger()

    pluginName = b"child"


    def __init__(self, dispatcher, maxProcessCount=8):
        """
        @param protocol: The name of the protocol for the child to use
            to handle connections.
        @type protocol: L{str} naming an L{IProtocol} implementer.
        """
        self.dispatcher = dispatcher
        self.maxProcessCount = maxProcessCount


    def startService(self):
        assert not hasattr(self, "children")

        self.children = set()


    def stopService(self):
        del(self.children)


    def socketWillArriveForProtocol(self, protocolName):
        """
        This method is where this service makes sure that there are
        sufficient child processes available to handle additional
        connections.
        """
        if len(self.children) == 0:
            self.spawnChild(protocolName)


    def spawnChild(self, protocolName):
        """
        Spawn a child process to handle connections.
        """
        from twisted.internet import reactor

        inheritedSocket = self.dispatcher.addSocket()
        inheritedFD = inheritedSocket.fileno()

        processProtocol = ChildProcessProtocol(self, inheritedSocket)

        # Annoyingly, twistd *has* to make a pid file.
        pidFileFD, pidFileName = mkstemp()
        close(pidFileFD)
        unlink(pidFileName)

        arguments = (
            sys.executable, b"-c",
            b"from twisted.scripts.twistd import run; run()",
            b"--pidfile", pidFileName,
            b"--nodaemon", b"--logfile", b"-",
            self.pluginName,
            b"--inherited-fd=3",
            b"--protocol", protocolName,
        )

        self.log.debug(
            u"Spawning child process for protocol {protocol!r} "
            u"with arguments: {arguments}",
            protocol=protocolName, arguments=arguments,
        )

        transport = reactor.spawnProcess(
            processProtocol,
            sys.executable, arguments, env={
                b"PYTHONPATH": b":".join(sys.path),
            },
            childFDs={0: b"w", 1: b"r", 2: b"r", 3: inheritedFD}
        )

        child = ChildProcess(transport, processProtocol)

        self.log.info(
            u"Spawned child process #{child.transport.pid} "
            u"for protocol {protocol!r}",
            child=child, protocol=protocolName, arguments=arguments,
        )

        self.children.add(child)


    def childDidExit(self, processProtocol, reason):
        """
        Called by L{ChildProcessProtocol} to alert this service that a
        child process has exited.

        @param processProtocol: The processProtocol for the child that
            exited.
        @type processProtocol: L{ChildProcessProtocol}

        @param reason: The reason that the child exited.
        @type reason: L{Failure}
        """
        for child in self.children:
            if child.protocol == processProtocol:
                self.log.info(
                    u"Child process ({child.transport.pid}) exited: "
                    u"{reason}",
                    child=child, reason=reason,
                )
                self.children.remove(child)
                break
        else:
            self.log.error(
                u"No child for for process protocol",
                processProtocol=processProtocol
            )

        try:
            self.dispatcher.removeSocket(processProtocol.inheritedSocket)
        except ValueError:
            self.log.error(
                u"No socket found for process protocol",
                processProtocol=processProtocol
            )



class ChildProcessProtocol(ProcessProtocol, object):
    """
    Process protocol for child processes.
    """

    log = Logger()


    def __init__(self, service, inheritedSocket):
        self.service = service
        self.inheritedSocket = inheritedSocket


    def outReceived(self, data):
        self.log.info(u"{data}", data=data)


    def errReceived(self, data):
        super(ChildProcessProtocol, self).errReceived(data)
        self.log.error(u"{data}", data=data)


    def processExited(self, reason):
        self.service.childDidExit(self, reason)



class ChildOptions(Options):
    """
    Options for a child process.
    """

    def opt_protocol(self, value):
        """
        Protocol
        """
        try:
            protocol = namedClass(value)
        except (ValueError, AttributeError):
            raise UsageError("Unknown protocol: {0}".format(value))

        self["protocol"] = protocol


    def opt_inherited_fd(self, value):
        """
        Inherited file descriptor
        """
        try:
            try:
                fd = int(value)
            except ValueError:
                raise ValueError("not an integer")

            if fd < 0:
                raise ValueError("must be >=0")

        except ValueError as e:
            raise UsageError(
                "Invalid file descriptor {0!r}: {1}".format(value, e)
            )

        self["inherited-fd"] = fd


    def postOptions(self):
        for parameter in ("protocol", "inherited-fd"):
            if parameter not in self:
                raise UsageError("{0} parameter is required".format(parameter))



@implementer(IServiceMaker)
class ChildServiceMaker(object):
    """
    Child process service maker.
    """

    def __init__(self):
        self.tapname = "child"
        self.description = self.__class__.__doc__
        self.options = ChildOptions


    def makeService(self, options):
        factory = ServerFactory.forProtocol(options["protocol"])
        service = ChildService(options["inherited-fd"], factory)
        return service



class ChildService(Service, object):
    """
    Service for child processes.
    """

    log = Logger()


    def __init__(self, fd, protocolFactory):
        self.fd = fd
        self.protocolFactory = protocolFactory


    def startService(self):
        factory = ReportingWrapperFactory(
            self.protocolFactory, self.fd, self.createTransport
        )
        self.wrappedProtocolFactory = factory

        factory.inheritedPort.startReading()
        factory.inheritedPort.reportStatus("0")

        return super(ChildService, self).startService()


    def stopService(self):
        factory = self.wrappedProtocolFactory

        # Halt connection inflow
        factory.inheritedPort.stopReading()

        # Wait for existing connections to close
        factory.allConnectionsClosed()

        return super(ChildService, self).stopService()


    def createTransport(self, socket, peer, data, protocol):
        """
        Create a TCP transport from a socket object passed by the parent.
        """
        from twisted.internet import reactor

        factory = self.wrappedProtocolFactory
        factory.inheritedPort.reportStatus("+")
        self.log.info("{factory.inheritedPort.statusQueue}", factory=factory)

        socketFD = socket.fileno()
        transport = reactor.adoptStreamConnection(
            socketFD, getsockfam(socketFD), factory
        )
        transport.startReading()

        return transport



class ReportingProtocolWrapper(ProtocolWrapper, object):
    log = Logger()


    def connectionLost(self, reason):
        self.factory.inheritedPort.reportStatus("-")
        return super(ReportingProtocolWrapper, self).connectionLost(reason)



class ReportingWrapperFactory(WrappingFactory, object):
    protocol = ReportingProtocolWrapper

    def __init__(self, wrappedFactory, fd, createTransport):
        self.inheritedPort = InheritedPort(fd, createTransport, self)
        super(ReportingWrapperFactory, self).__init__(wrappedFactory)



@total_ordering
class ChildStatus(FancyStrMixin, object):
    """
    The status of a child process.
    """

    showAttributes = (
        "acknowledged",
        "unacknowledged",
        "unclosed",
    )


    def __init__(self, acknowledged=0, unacknowledged=0, unclosed=0):
        """
        Create a L{ConnectionStatus} with a number of sent connections and a
        number of un-acknowledged connections.

        @param acknowledged: the number of connections which we know the
            subprocess to be presently processing; i.e. those which have been
            transmitted to the subprocess.

        @param unacknowledged: The number of connections which we have sent to
            the subprocess which have never received a status response (a
            "C{+}" status message).

        @param unclosed: The number of sockets which have been sent to the
            subprocess but not yet closed.
        """
        self.acknowledged = acknowledged
        self.unacknowledged = unacknowledged
        self.unclosed = unclosed


    def effectiveLoad(self):
        """
        The current effective load.
        """
        return self.acknowledged + self.unacknowledged


    def _tuplify(self):
        return tuple(getattr(self, attr) for attr in self.showAttributes)


    def __lt__(self, other):
        if not isinstance(other, ChildStatus):
            return NotImplemented

        return self.effectiveLoad() < other.effectiveLoad()


    def __eq__(self, other):
        if not isinstance(other, ChildStatus):
            return NotImplemented

        return self._tuplify() == other._tuplify()


    def __add__(self, other):
        if not isinstance(other, ChildStatus):
            return NotImplemented

        a = self._tuplify()
        b = other._tuplify()
        sum = [a1 + b1 for (a1, b1) in zip(a, b)]

        return self.__class__(*sum)


    def __sub__(self, other):
        if not isinstance(other, ChildStatus):
            return NotImplemented

        return self + self.__class__(*[-x for x in other._tuplify()])
