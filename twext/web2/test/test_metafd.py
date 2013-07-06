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


"""
Tests for twext.web2.metafd.
"""

from socket import error as SocketError, AF_INET
from errno import ENOTCONN

from twext.internet import sendfdport
from twext.web2 import metafd
from twext.web2.channel.http import HTTPChannel
from twext.web2.metafd import ReportingHTTPService, ConnectionLimiter
from twisted.internet.tcp import Server
from twisted.application.service import Service

from twext.internet.test.test_sendfdport import ReaderAdder
from twisted.trial.unittest import TestCase


class FakeSocket(object):
    """
    A fake socket for testing.
    """
    def __init__(self, test):
        self.test = test


    def fileno(self):
        return "not a socket"


    def setblocking(self, blocking):
        return


    def getpeername(self):
        if self.test.peerNameSucceed:
            return ("4.3.2.1", 4321)
        else:
            raise SocketError(ENOTCONN, "Transport endpoint not connected")


    def getsockname(self):
        return ("4.3.2.1", 4321)


class InheritedPortForTesting(sendfdport.InheritedPort):
    """
    L{sendfdport.InheritedPort} subclass that prevents certain I/O operations
    for better unit testing.
    """

    def startReading(self):
        "Do nothing."


    def stopReading(self):
        "Do nothing."


    def startWriting(self):
        "Do nothing."


    def stopWriting(self):
        "Do nothing."



class ServerTransportForTesting(Server):
    """
    tcp.Server replacement for testing purposes.
    """

    def startReading(self):
        "Do nothing."

    def stopReading(self):
        "Do nothing."

    def startWriting(self):
        "Do nothing."

    def stopWriting(self):
        "Do nothing."

    def __init__(self, *a, **kw):
        super(ServerTransportForTesting, self).__init__(*a, **kw)
        self.reactor = None



class ReportingHTTPServiceTests(TestCase):
    """
    Tests for L{ReportingHTTPService}
    """

    peerNameSucceed = True

    def setUp(self):
        def fakefromfd(fd, addressFamily, socketType):
            return FakeSocket(self)
        def fakerecvfd(fd):
            return "not an fd", "not a description"
        def fakeclose(fd):
            ""
        def fakegetsockfam(fd):
            return AF_INET
        self.patch(sendfdport, 'recvfd', fakerecvfd)
        self.patch(sendfdport, 'fromfd', fakefromfd)
        self.patch(sendfdport, 'close', fakeclose)
        self.patch(sendfdport, 'getsockfam', fakegetsockfam)
        self.patch(metafd, 'InheritedPort', InheritedPortForTesting)
        self.patch(metafd, 'Server', ServerTransportForTesting)
        # This last stubbed out just to prevent dirty reactor warnings.
        self.patch(HTTPChannel, "callLater", lambda *a, **k: None)
        self.svc = ReportingHTTPService(None, None, None)
        self.svc.startService()


    def test_quickClosedSocket(self):
        """
        If a socket is closed very quickly after being {accept()}ed, requesting
        its peer (or even host) address may fail with C{ENOTCONN}.  If this
        happens, its transport should be supplied with a dummy peer address.
        """
        self.peerNameSucceed = False
        self.svc.reportingFactory.inheritedPort.doRead()
        channels = self.svc.reportingFactory.connectedChannels
        self.assertEqual(len(channels), 1)
        self.assertEqual(list(channels)[0].transport.getPeer().host, "0.0.0.0")



class ConnectionLimiterTests(TestCase):
    """
    Tests for L{ConnectionLimiter}
    """

    def test_loadReducedStartsReadingAgain(self):
        """
        L{ConnectionLimiter.statusesChanged} determines whether the current
        "load" of all subprocesses - that is, the total outstanding request
        count - is high enough that the listening ports attached to it should
        be suspended.
        """
        builder = LimiterBuilder(self)
        builder.fillUp()
        self.assertEquals(builder.port.reading, False) # sanity check
        builder.loadDown()
        self.assertEquals(builder.port.reading, True)


    def test_processRestartedStartsReadingAgain(self):
        """
        L{ConnectionLimiter.statusesChanged} determines whether the current
        number of outstanding requests is above the limit, and either stops or
        resumes reading on the listening port.
        """
        builder = LimiterBuilder(self)
        builder.fillUp()
        self.assertEquals(builder.port.reading, False)
        builder.processRestart()
        self.assertEquals(builder.port.reading, True)



class LimiterBuilder(object):
    """
    A L{LimiterBuilder} can build a L{ConnectionLimiter} and associated objects
    for a given unit test.
    """

    def __init__(self, test, maxReq=3):
        self.limiter = ConnectionLimiter(2, maxRequests=maxReq)
        self.dispatcher = self.limiter.dispatcher
        self.dispatcher.reactor = ReaderAdder()
        self.service = Service()
        self.limiter.addPortService("TCP", 4321, "127.0.0.1", 5,
                                    self.serverServiceMakerMaker(self.service))
        self.dispatcher.addSocket()
        # Has to be running in order to add stuff.
        self.limiter.startService()
        self.port = self.service.myPort


    def serverServiceMakerMaker(self, s):
        """
        Make a serverServiceMaker for use with
        L{ConnectionLimiter.addPortService}.
        """
        class NotAPort(object):
            def startReading(self):
                self.reading = True
            def stopReading(self):
                self.reading = False

        def serverServiceMaker(port, factory, *a, **k):
            s.factory = factory
            s.myPort = NotAPort()
            s.myPort.startReading() # TODO: technically, should wait for startService
            factory.myServer = s
            return s
        return serverServiceMaker


    def fillUp(self):
        """
        Fill up all the slots on the connection limiter.
        """
        for x in range(self.limiter.maxRequests):
            self.dispatcher.sendFileDescriptor(None, "SSL")
            self.dispatcher.statusMessage(
                self.dispatcher._subprocessSockets[0], "+"
            )


    def processRestart(self):
        self.dispatcher.statusMessage(
            self.dispatcher._subprocessSockets[0], "0"
        )


    def loadDown(self):
        self.dispatcher.statusMessage(
            self.dispatcher._subprocessSockets[0], "-"
        )
