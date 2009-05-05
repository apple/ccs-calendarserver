##
# Copyright (c) 2008-2009 Apple Inc. All rights reserved.
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

from random import randint

from twisted.internet import protocol
from twisted.python import log
from twisted.web2.channel.http import HTTPFactory, HTTPChannelRequest,\
    HTTPChannel
from twistedcaldav import accounting
import time

__all__ = [
    "HTTP503LoggingFactory",
]

class OverloadedLoggingServerProtocol (protocol.Protocol):
    def __init__(self, retryAfter, outstandingRequests):
        self.retryAfter = retryAfter
        self.outstandingRequests = outstandingRequests

    def connectionMade(self):
        log.msg(overloaded=self)

        self.transport.write(
            "HTTP/1.0 503 Service Unavailable\r\n"
            "Content-Type: text/html\r\n"
        )

        if self.retryAfter:
            self.transport.write(
                "Retry-After: %s\r\n" % (self.retryAfter,)
            )

        self.transport.write(
            "Connection: close\r\n\r\n"
            "<html><head><title>Service Unavailable</title></head>"
            "<body><h1>Service Unavailable</h1>"
            "The server is currently overloaded, "
            "please try again later.</body></html>"
        )
        self.transport.loseConnection()

class HTTP503LoggingFactory (HTTPFactory):
    """
    Factory for HTTP server which emits a 503 response when overloaded.
    """
    def __init__(self, requestFactory, maxRequests=600, retryAfter=0, vary=False, **kwargs):
        self.retryAfter = retryAfter
        self.vary = vary
        HTTPFactory.__init__(self, requestFactory, maxRequests, **kwargs)

    def buildProtocol(self, addr):
        if self.vary:
            retryAfter = randint(int(self.retryAfter * 1/2), int(self.retryAfter * 3/2))
        else:
            retryAfter = self.retryAfter

        if self.outstandingRequests >= self.maxRequests:
            return OverloadedLoggingServerProtocol(retryAfter, self.outstandingRequests)

        p = protocol.ServerFactory.buildProtocol(self, addr)

        for arg,value in self.protocolArgs.iteritems():
            setattr(p, arg, value)

        return p

class HTTPLoggingChannelRequest(HTTPChannelRequest):
    
    class TransportLoggingWrapper(object):
        
        def __init__(self, transport, logData):
            
            self.transport = transport
            self.logData = logData
            
        def write(self, data):
            if self.logData is not None and data:
                self.logData.append(data)
            self.transport.write(data)
            
        def writeSequence(self, seq):
            if self.logData is not None and seq:
                self.logData.append(''.join(seq))
            self.transport.writeSequence(seq)

        def __getattr__(self, attr):
            return getattr(self.__dict__['transport'], attr)

    class LogData(object):
        def __init__(self):
            self.request = []
            self.response = []
            
    def __init__(self, channel, queued=0):
        super(HTTPLoggingChannelRequest, self).__init__(channel, queued)

        if accounting.accountingEnabledForCategory("HTTP"):
            self.logData = LogData()
            self.transport = HTTPLoggingChannelRequest.TransportLoggingWrapper(self.transport, self.logData.response)
        else:
            self.logData = None

    def gotInitialLine(self, initialLine):
        if self.logData is not None:
            self.startTime = time.time()
            self.logData.request.append(">>>> Request starting at: %.3f\r\n\r\n" % (self.startTime,))
            self.logData.request.append("%s\r\n" % (initialLine,))
        super(HTTPLoggingChannelRequest, self).gotInitialLine(initialLine)

    def lineReceived(self, line):
        
        if self.logData is not None:
            # We don't want to log basic credentials
            loggedLine = line
            if line.lower().startswith("authorization:"):
                bits = line[14:].strip().split(" ")
                if bits[0].lower() == "basic" and len(bits) == 2:
                    loggedLine = "%s %s %s" % (line[:14], bits[0], "X" * len(bits[1]))
            self.logData.request.append("%s\r\n" % (loggedLine,))
        super(HTTPLoggingChannelRequest, self).lineReceived(line)

    def handleContentChunk(self, data):
        
        if self.logData is not None:
            self.logData.request.append(data)
        super(HTTPLoggingChannelRequest, self).handleContentChunk(data)
        
    def handleContentComplete(self):
        
        if self.logData is not None:
            doneTime = time.time()
            self.logData.request.append("\r\n\r\n>>>> Request complete at: %.3f (elapsed: %.1f ms)" % (doneTime, 1000 * (doneTime - self.startTime),))
        super(HTTPLoggingChannelRequest, self).handleContentComplete()

    def writeHeaders(self, code, headers):
        if self.logData is not None:
            doneTime = time.time()
            self.logData.response.append("\r\n\r\n<<<< Response sending at: %.3f (elapsed: %.1f ms)\r\n\r\n" % (doneTime, 1000 * (doneTime - self.startTime),))
        super(HTTPLoggingChannelRequest, self).writeHeaders(code, headers)

    def finish(self):
        
        super(HTTPLoggingChannelRequest, self).finish()

        if self.logData is not None:
            doneTime = time.time()
            self.logData.response.append("\r\n\r\n<<<< Response complete at: %.3f (elapsed: %.1f ms)\r\n" % (doneTime, 1000 * (doneTime - self.startTime),))
            accounting.emitAccounting("HTTP", "all", "".join(self.logData.request) + "".join(self.logData.response))

HTTPChannel.chanRequestFactory = HTTPLoggingChannelRequest
