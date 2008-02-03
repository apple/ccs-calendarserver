##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
Server to server utility functions and client requests.
"""

__all__ = [
    "ServerToServer",
    "ServerToServerRequest",
]


from twisted.internet.defer import deferredGenerator
from twisted.internet.defer import waitForDeferred
from twisted.internet.protocol import ClientCreator
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.web2 import responsecode
from twisted.web2.client.http import ClientRequest
from twisted.web2.client.http import HTTPClientProtocol
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.util import davXMLFromStream
from twisted.web2.http import HTTPError
from twisted.web2.http_headers import Headers
from twisted.web2.http_headers import MimeType

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.servertoserverparser import ServerToServerParser
from twistedcaldav import caldavxml
from twistedcaldav import logging

class ServerToServer(object):
    
    _fileInfo = None
    _xmlFile = None
    _servers = None
    _domainMap = None
    
    def __init__(self):
        
        self._loadConfig()

    def _loadConfig(self):
        if ServerToServer._servers is None:
            ServerToServer._xmlFile = FilePath(config.ServerToServer["Servers"])
        ServerToServer._xmlFile.restat()
        fileInfo = (ServerToServer._xmlFile.getmtime(), ServerToServer._xmlFile.getsize())
        if fileInfo != ServerToServer._fileInfo:
            parser = ServerToServerParser(ServerToServer._xmlFile)
            ServerToServer._servers = parser.servers
            self._mapDomains()
            ServerToServer._fileInfo = fileInfo
        
    def _mapDomains(self):
        ServerToServer._domainMap = {}
        for server in ServerToServer._servers:
            for domain in server.domains:
                ServerToServer._domainMap[domain] = server
    
    def mapDomain(self, domain):
        """
        Map a calendar user address domain to a suitable server that can
        handle server-to-server requests for that user.
        """
        return ServerToServer._domainMap.get(domain)

class ServerToServerRequest(object):
    
    def __init__(self, scheduler, server, recipients, responses):

        self.scheduler = scheduler
        self.server = server
        self.recipients = recipients
        self.responses = responses
        
        self._generateHeaders()
        self._prepareData()
        
    @deferredGenerator
    def doRequest(self):
        
        # Generate an HTTP client request
        try:
            from twisted.internet import reactor
            if self.server.ssl:
                from tap import ChainingOpenSSLContextFactory
                context = ChainingOpenSSLContextFactory(config.SSLPrivateKey, config.SSLCertificate, certificateChainFile=config.SSLAuthorityChain)
                d = waitForDeferred(ClientCreator(reactor, HTTPClientProtocol).connectSSL(self.server.host, self.server.port, context))
            else:
                d = waitForDeferred(ClientCreator(reactor, HTTPClientProtocol).connectTCP(self.server.host, self.server.port))
            yield d
            proto = d.getResult()
            
            request = ClientRequest("POST", self.server.path, self.headers, self.data)
            if logging.canLog("debug"):
                d = waitForDeferred(logging.logRequest("Sending server-to-server POST request:", request, system="Server-to-server Send"))
                yield d
                d.getResult()
            d = waitForDeferred(proto.submitRequest(request))
            yield d
            response = d.getResult()
    
            if logging.canLog("debug"):
                d = waitForDeferred(logging.logResponse("Received server-to-server POST response:", response, system="Server-to-server Send"))
                yield d
                d.getResult()
            d = waitForDeferred(davXMLFromStream(response.stream))
            yield d
            xml = d.getResult()
    
            self._parseResponse(xml)
        except Exception, e:
            # Generated failed responses for each recipient
            logging.err("Could not do server-to-server request : %s %s" % (self, e), system="Server-to-server Send")
            for recipient in self.recipients:
                err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-failed")))
                self.responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="5.1;Service unavailable")

    def _generateHeaders(self):
        self.headers = Headers()
        self.headers.setHeader('Host', self.server.host + ":%s" % (self.server.port,))
        self.headers.addRawHeader('Originator', self.scheduler.originator.cuaddr)
        self._doAuthentication()
        for recipient in self.recipients:
            self.headers.addRawHeader('Recipient', recipient.cuaddr)
        self.headers.setHeader('Content-Type', MimeType("text", "calendar", params={"charset":"utf-8"}))

    def _doAuthentication(self):
        if self.server.authentication and self.server.authentication[0] == "basic":
            self.headers.setHeader(
                'Authorization',
                ('Basic', ("%s:%s" % (self.server.authentication[1], self.server.authentication[2],)).encode('base64')[:-1])
            )

    def _prepareData(self):
        self.data = str(self.scheduler.calendar)

    def _parseResponse(self, xml):

        # Check for correct root element
        schedule_response = xml.root_element
        if not isinstance(schedule_response, caldavxml.ScheduleResponse) or not schedule_response.children:
            raise HTTPError(responsecode.BAD_REQUEST)
        
        # Parse each response - do this twice: once looking for errors that will
        # result in all recipients shown as failures; the second loop adds all the
        # valid responses to the actual result.
        for response in schedule_response.children:
            if not isinstance(response, caldavxml.Response) or not response.children:
                raise HTTPError(responsecode.BAD_REQUEST)
            recipient = response.childOfType(caldavxml.Recipient)
            request_status = response.childOfType(caldavxml.RequestStatus)
            if not recipient or not request_status:
                raise HTTPError(responsecode.BAD_REQUEST)
        for response in schedule_response.children:
            self.responses.clone(response)
