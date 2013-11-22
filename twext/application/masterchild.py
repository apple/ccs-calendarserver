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
from twisted.application.service import MultiService, Service
from twisted.application.service import IServiceMaker
from twisted.application.internet import TCPServer
from twisted.protocols.policies import WrappingFactory, ProtocolWrapper

from twisted.internet.protocol import ProcessProtocol
from twext.internet.sendfdport import InheritingProtocolFactory
from twext.internet.sendfdport import InheritedSocketDispatcher
from twext.internet.sendfdport import IStatusWatcher
from twext.internet.sendfdport import InheritedPort



class MasterOptions (Options):
    optParameters = [[
        #"config", "f", DEFAULT_CONFIG_FILE, "Path to configuration file."
    ]]

    # def __init__(self, *args, **kwargs):
    #     super(Options, self).__init__(*args, **kwargs)



@implementer(IServiceMaker)
class MasterServiceMaker(object):
    def makeService(self, options):
        service = MultiService()

        port = 8000

        # Dispatcher
        statusWatcher = StatusWatcher()
        dispatcher = InheritedSocketDispatcher(statusWatcher)

        # Child Processes
        spawningService = ChildSpawningService(dispatcher)
        spawningService.setServiceParent(service)

        # TCP Service
        description = b""  # UserInfo sent to the dispatcher
        tcpFactory = InheritingProtocolFactory(dispatcher, description)
        tcpService = TCPServer(port, tcpFactory)

        tcpService.setServiceParent(service)

        return service


#########
# Subclass InheritingProtocolFactory
# override sendSocket to decide when to spawn a child


# @implementer(IServiceMaker)
# class ChildSpawningServiceMaker(object):
#     def makeService(self, options):
#         service = ChildSpawningService(args)
#         return service



class ChildSpawningService(Service, object):
    def __init__(self, dispatcher, maxProcessCount=8):
        self.dispatcher = dispatcher
        self.maxProcessCount = maxProcessCount


    def startService(self):
        assert not hasattr(self, "children")

        self.children = set()


    def stopService(self):
        del(self.children)


    def spawnChild(self, arguments):
        from twisted.internet import reactor

        inheritedSocket = self.dispatcher.addSocket()
        inheritedFD = inheritedSocket.fileno()

        processProtocol = ChildProcessProtocol(self, inheritedSocket)

        reactor.spawnProcess(
            processProtocol,
            sys.executable,
            args=(
                sys.executable, b"-c",
                b"from twisted.scripts.twistd import run; run()",
                b"--inherited-fd", b"3",
            ) + tuple(arguments),
            env={},
            childFDs={0: b"w", 1: b"r", 2: b"r", 3: inheritedFD}
        )

        self.children.add(processProtocol)


    def childDidExit(self, child):
        self.children.remove(child)
        self.dispatcher.removeSocket(child.inheritedSocket)



class ChildProcessProtocol(ProcessProtocol, object):
    def __init__(self, service, inheritedSocket):
        self.service = service
        self.inheritedSocket = inheritedSocket


    def outReceived(self, data):
        super(ChildProcessProtocol, self).outReceived(data)
        # FIXME: log...


    def errReceived(self, data):
        super(ChildProcessProtocol, self).errReceived(data)
        # FIXME: log...


    def processExited(self, reason):
        self.service.childDidExit(self)



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


    def postOptions(self):
        if "inherited-fd" not in self:
            raise UsageError("inherited-fd paramater is required")



@implementer(IServiceMaker)
class ChildServiceMaker(object):
    def makeService(self, options):
        service = ChildService(options["inherited-fd"], self.protocolFactory)
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



class ReportingWrapperFactory(WrappingFactory):
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



Status = namedtuple(
    "Status",
    ("sentCount", "ackedCount")
)
