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
Application container
"""

import sys
from collections import namedtuple

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



class MasterOptions(Options):
    """
    Options for a master process.
    """



class SpawningInheritingProtocolFactory(InheritingProtocolFactory):
    def __init__(self, dispatcher, spawningService, description):
        super(SpawningInheritingProtocolFactory, self).__init__(
            dispatcher, description
        )
        self.spawningService = spawningService


    def sendSocket(self, socketObject):
        self.spawningService.socketWillArrive()
        super(SpawningInheritingProtocolFactory, self).sendSocket(socketObject)



@implementer(IServiceMaker)
class MasterServiceMaker(object):
    def makeService(self, options):
        service = MultiService()

        port = 8000
        childProtocol = "twext.protocols.echo.EchoProtocol"

        # Dispatcher
        statusWatcher = StatusWatcher()
        dispatcher = InheritedSocketDispatcher(statusWatcher)

        # Child Processes
        spawningService = ChildSpawningService(dispatcher)
        spawningService.setServiceParent(service)

        # TCP Service
        description = bytes(childProtocol)  # UserInfo sent to the dispatcher
        tcpFactory = SpawningInheritingProtocolFactory(
            dispatcher, spawningService, description
        )
        tcpService = TCPServer(port, tcpFactory)

        tcpService.setServiceParent(service)

        return service



Child = namedtuple("Child", ("transport", "protocol"))



class ChildSpawningService(Service, object):
    log = Logger()

    def __init__(self, dispatcher, protocolName, maxProcessCount=8):
        """
        @param protocol: The name of the protocol for the child to use
            to handle connections.
        @type protocol: L{str} naming an L{IProtocol} implementer.
        """
        self.dispatcher = dispatcher
        self.protocolName = protocolName
        self.maxProcessCount = maxProcessCount


    def startService(self):
        assert not hasattr(self, "children")

        self.children = set()


    def stopService(self):
        del(self.children)


    def socketWillArrive(self):
        """
        This method is where this service makes sure that there are
        sufficient child processes available to handle additional
        connections.
        """
        if len(self.children) == 0:
            self.spawnChild()


    def spawnChild(self):
        """
        Spawn a child process to handle connections.
        """
        from twisted.internet import reactor

        inheritedSocket = self.dispatcher.addSocket()
        inheritedFD = inheritedSocket.fileno()

        processProtocol = ChildProcessProtocol(self, inheritedSocket)

        arguments = (
            sys.executable, b"-c",
            b"from twisted.scripts.twistd import run; run()",
            b"--inherited-fd", b"3",
            b"--protocol", self.protocolName,
        )

        transport = reactor.spawnProcess(
            processProtocol,
            sys.executable, arguments, env={},
            childFDs={0: b"w", 1: b"r", 2: b"r", 3: inheritedFD}
        )

        child = Child(transport, processProtocol)

        self.log.info(
            u"Spawned child process ({child.transport.pid}) "
            u"for protocol {protocol!r}: {arguments}",
            child=child, protocol=self.protocolName, arguments=arguments,
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



class ChildOptions (Options):
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


    def opt_protocol(self, value):
        """
        Protocol
        """
        try:
            protocol = namedClass(value)
        except (ValueError, AttributeError):
            raise UsageError("Unknown protocol: {0}".format(value))

        self["protocol"] = protocol


    def postOptions(self):
        for parameter in ("inherited-fd", "protocol"):
            if parameter not in self:
                raise UsageError("{0} parameter is required".format(parameter))



@implementer(IServiceMaker)
class ChildServiceMaker(object):
    def makeService(self, options):
        factory = ServerFactory.forProtocol(options["protocol"])
        service = ChildService(options["inherited-fd"], factory)
        return service



class ChildService(Service, object):
    def __init__(self, fd, protocolFactory):
        self.fd = fd
        self.protocolFactory = protocolFactory


    def startService(self):
        self.wrappedProtocolFactory = ReportingWrapperFactory(
            self.protocolFactory, self.fd, self.createTransport
        )
        return super(ChildService, self).startService()


    def stopService(self):
        return super(ChildService, self).stopService()


    def createTransport(self, socket, peer, data, protocol):
        """
        Create a TCP transport from a socket object passed by the parent.
        """
        from twisted.internet import reactor

        self.wrappedFactory.inheritedPort.reportStatus("+")

        socketFD = socket.fileno()
        return reactor.adoptStreamConnection(
            socketFD, getsockfam(socketFD), self.wrappedProtocolFactory
        )



class ReportingProtocolWrapper(ProtocolWrapper, object):
    def connectionLost(self, reason):
        self.factory.inheritedPort.reportStatus("-")
        return super(ReportingProtocolWrapper, self).connectionLost(reason)



class ReportingWrapperFactory(WrappingFactory, object):
    protocol = ReportingProtocolWrapper

    def __init__(self, wrappedFactory, fd, createTransport):
        self.inheritedPort = InheritedPort(fd, createTransport, self)
        super(ReportingWrapperFactory, self).__init__(wrappedFactory)



@implementer(IStatusWatcher)
class StatusWatcher(object):
    """
    This enabled the dispatcher to keep track of how many connections are in
    flight for each child.
    """
    @staticmethod
    def initialStatus():
        return Status(sentCount=0, ackedCount=0)


    @staticmethod
    def newConnectionStatus(previousStatus):
        return Status(
            sentCount=previousStatus.sentCount + 1,
            ackedCount=previousStatus.ackedCount,
        )


    @staticmethod
    def statusFromMessage(previousStatus, message):
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
        return (
            previousStatus.ackedCount,
            Status(
                sentCount=previousStatus.sentCount,
                ackedCount=0,
            )
        )



Status = namedtuple("Status", ("sentCount", "ackedCount"))
