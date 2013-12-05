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

from zope.interface import implementer

from twisted.python.sendmsg import getsockfam
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass
from twisted.application.service import MultiService, Service
from twisted.application.service import IServiceMaker
from twisted.application.internet import TCPServer
from twisted.protocols.policies import WrappingFactory, ProtocolWrapper
from twisted.internet.protocol import ServerFactory
from twisted.internet.protocol import ProcessProtocol

from twext.python.log import Logger
from twext.internet.sendfdport import InheritingProtocolFactory
from twext.internet.sendfdport import InheritedSocketDispatcher
from twext.internet.sendfdport import IStatusWatcher
from twext.internet.sendfdport import InheritedPort

log = Logger()



class MasterOptions(Options):
    """
    Options for a master process.
    """

    def opt_protocol(self, value):
        """
        Protocol
        """
        try:
            namedClass(value)
        except (ValueError, AttributeError):
            raise UsageError("Unknown protocol: {0}".format(value))

        self["protocol"] = value


    def opt_port(self, value):
        """
        Inherited file descriptor
        """
        try:
            try:
                port = int(value)
            except ValueError:
                raise ValueError("not an integer")

            if port < 0:
                raise ValueError("must be >=0")

        except ValueError as e:
            raise UsageError(
                "Invalid port number {0!r}: {1}".format(value, e)
            )

        self["port"] = port


    def postOptions(self):
        for parameter in ("protocol", "port"):
            if parameter not in self:
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



@implementer(IServiceMaker)
class MasterServiceMaker(object):
    """
    Master process service maker.
    """

    def makeService(self, options):
        service = MultiService()

        # Dispatcher
        statusWatcher = StatusWatcher()
        dispatcher = InheritedSocketDispatcher(statusWatcher)

        # Child Processes
        spawningService = ChildSpawningService(dispatcher)
        spawningService.setServiceParent(service)

        # TCP Service
        tcpFactory = SpawningInheritingProtocolFactory(
            dispatcher, spawningService, options["protocol"]
        )
        tcpService = TCPServer(options["port"], tcpFactory)

        tcpService.setServiceParent(service)

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

    def makeService(self, options):
        factory = ServerFactory.forProtocol(options["protocol"])
        service = ChildService(options["inherited-fd"], factory)
        return service



class ChildService(Service, object):
    """
    Service for child processes.
    """

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

        factory.inheritedPort.stopReading()
        factory.allConnectionsClosed()

        return super(ChildService, self).stopService()


    def createTransport(self, socket, peer, data, protocol):
        """
        Create a TCP transport from a socket object passed by the parent.
        """
        from twisted.internet import reactor

        factory = self.wrappedProtocolFactory
        factory.inheritedPort.reportStatus("+")
        log.info("{factory.inheritedPort.statusQueue}", factory=factory)

        socketFD = socket.fileno()
        transport = reactor.adoptStreamConnection(
            socketFD, getsockfam(socketFD), factory
        )
        transport.startReading()

        return transport



class ReportingProtocolWrapper(ProtocolWrapper, object):
    def connectionLost(self, reason):
        log.info("CONNECTION LOST")
        self.factory.inheritedPort.reportStatus("-")
        return super(ReportingProtocolWrapper, self).connectionLost(reason)



class ReportingWrapperFactory(WrappingFactory, object):
    protocol = ReportingProtocolWrapper

    def __init__(self, wrappedFactory, fd, createTransport):
        self.inheritedPort = InheritedPort(fd, createTransport, self)
        super(ReportingWrapperFactory, self).__init__(wrappedFactory)



class Status(object):
    def __init__(self, sentCount, ackedCount):
        self.sentCount = sentCount
        self.ackedCount = ackedCount

    def __repr__(self):
        return "({self.sentCount},{self.ackedCount})".format(self=self)



@implementer(IStatusWatcher)
class StatusWatcher(object):
    """
    This enables the dispatcher to keep track of how many connections are in
    flight for each child.
    """
    @staticmethod
    def initialStatus():
        log.info("Status: init")
        return Status(sentCount=0, ackedCount=0)


    @staticmethod
    def newConnectionStatus(previousStatus):
        log.info("Status: {0} new".format(previousStatus))
        return Status(
            sentCount=previousStatus.sentCount + 1,
            ackedCount=previousStatus.ackedCount,
        )


    @staticmethod
    def statusFromMessage(previousStatus, message):
        log.info("Status: {0}{1!r}".format(previousStatus, message))
        if message == b"-":
            return Status(
                sentCount=previousStatus.sentCount - 1,
                ackedCount=previousStatus.ackedCount,
            )
        elif message == b"+":
            return Status(
                sentCount=previousStatus.sentCount,
                ackedCount=previousStatus.ackedCount + 1,
            )
        else:
            raise AssertionError("Unknown message: {}".format(message))


    @staticmethod
    def closeCountFromStatus(previousStatus):
        log.info("Status: {0} close".format(previousStatus))
        return (
            previousStatus.ackedCount,
            Status(
                sentCount=previousStatus.sentCount,
                ackedCount=0,
            )
        )


    @staticmethod
    def statusesChanged(statuses):
        log.info("Status changed: {0}".format(tuple(statuses)))
        # FIXME: This isn't in IStatusWatcher, but is called by
        # InheritedSocketDispatcher.
        pass
