##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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
from twisted.web2.channel.http import HTTPFactory, HTTPChannel
from twisted.web2.server import Request, Site
from twistedcaldav.inspection import Inspector

from twistedcaldav.config import config
from twisted.web2 import iweb

__all__ = ['HTTP503LoggingFactory', ]

class OverloadedLoggingServerProtocol(protocol.Protocol):
    
    def __init__(self, outstandingRequests):
        self.outstandingRequests = outstandingRequests

    def connectionMade(self):
        log.msg(overloaded=self)

        if config.HTTPRetryAfter:
            retryAfter = randint(int(config.HTTPRetryAfter * 1/2), int(config.HTTPRetryAfter * 3/2))
            retryAfter = "Retry-After: %s\r\n" % retryAfter
        else:
            retryAfter = ""

        self.transport.write(
            "HTTP/1.0 503 Service Unavailable\r\n"
            "Content-Type: text/html\r\n"
            "%(retryAfter)s"
            "Connection: close\r\n\r\n"
            "<html><head><title>503 Service Unavailable</title></head>"
            "<body><h1>Service Unavailable</h1>"
            "The server is currently overloaded, "
            "please try again later.</body></html>"
            % { "retryAfter": retryAfter }
        )

        self.transport.loseConnection()

class InspectableHTTPChannel(HTTPChannel):

    _inspection = None

    def connectionMade(self):
        if self._inspection:
            self._inspection.add("conn_made")

        return super(InspectableHTTPChannel, self).connectionMade()

    def connectionLost(self, reason):
        if self._inspection:
            self._inspection.add("conn_lost")
            self._inspection.complete()

        return super(InspectableHTTPChannel, self).connectionLost(reason)

    _firstChunkReceived = False

    def dataReceived(self, data):
        if not self._firstChunkReceived:
            self._firstChunkReceived = True
            if self._inspection:
                self._inspection.add("first_byte")

        return super(InspectableHTTPChannel, self).dataReceived(data)

    def requestReadFinished(self, request):
        if self._inspection:
            self._inspection.add("body_received")

        return super(InspectableHTTPChannel, self).requestReadFinished(request)

    def requestWriteFinished(self, request):
        if self._inspection:
            self._inspection.add("resp_finish")

        return super(InspectableHTTPChannel, self).requestWriteFinished(request)


class HTTP503LoggingFactory(HTTPFactory):
    """Factory for HTTP server."""

    protocol = InspectableHTTPChannel

    def __init__(self, requestFactory, maxRequests=600, **kwargs):
        HTTPFactory.__init__(self, requestFactory, maxRequests, **kwargs)
        self.channelCounter = 0
        
    def buildProtocol(self, addr):
        if self.outstandingRequests >= self.maxRequests:
            return OverloadedLoggingServerProtocol(self.outstandingRequests)
        
        p = protocol.ServerFactory.buildProtocol(self, addr)
        
        for arg,value in self.protocolArgs.iteritems():
            setattr(p, arg, value)

        self.channelCounter += 1
        if config.EnableInspection:
            p._inspection = Inspector.getInspection(self.channelCounter)

        return p


class LimitingHTTPChannel(InspectableHTTPChannel):

    def connectionMade(self):
        retVal = super(LimitingHTTPChannel, self).connectionMade()
        if self.factory.outstandingRequests >= self.factory.maxRequests:
            # log.msg("Overloaded")
            self.factory.myServer.myPort.stopReading()
        return retVal

    def connectionLost(self, reason):
        retVal = super(LimitingHTTPChannel, self).connectionLost(reason)
        if self.factory.outstandingRequests < self.factory.resumeRequests:
            # log.msg("Resuming")
            self.factory.myServer.myPort.startReading()
        return retVal


class LimitingHTTPFactory(HTTPFactory):

    protocol = LimitingHTTPChannel

    def __init__(self, requestFactory, maxRequests=600, maxAccepts=100, resumeRequests=550,
        **kwargs):
        HTTPFactory.__init__(self, requestFactory, maxRequests, **kwargs)
        self.maxAccepts = maxAccepts
        self.resumeRequests = resumeRequests
        self.channelCounter = 0

    def buildProtocol(self, addr):

        p = protocol.ServerFactory.buildProtocol(self, addr)
        for arg, value in self.protocolArgs.iteritems():
            setattr(p, arg, value)

        self.channelCounter += 1
        if config.EnableInspection:
            p._inspection = Inspector.getInspection(self.channelCounter)

        return p

class LimitingRequest(Request):

    def __init__(self, *args, **kwargs):
        Request.__init__(self, *args, **kwargs)
        self.extendedLogItems = {}
        channel = self.chanRequest.channel
        if config.EnableInspection and channel._inspection:
            channel._inspection.add("headers_received")
            self.extendedLogItems['insp'] = channel._inspection.id

    def writeResponse(self, response):
        channel = self.chanRequest.channel
        if config.EnableInspection and channel._inspection:
            channel._inspection.add("resp_start")

        Request.writeResponse(self, response)


class LimitingSite(Site):

    def __call__(self, *args, **kwargs):
        return LimitingRequest(site=self, *args, **kwargs)

