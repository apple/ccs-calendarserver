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

from twisted.internet.defer import inlineCallbacks, DeferredList
from twisted.internet.protocol import ClientCreator

from twisted.python.failure import Failure

from twisted.web2 import responsecode
from twisted.web2.client.http import ClientRequest
from twisted.web2.client.http import HTTPClientProtocol
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.util import davXMLFromStream
from twisted.web2.http import HTTPError
from twisted.web2.http_headers import Headers
from twisted.web2.http_headers import MimeType

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.log import Logger
from twistedcaldav.scheduling.delivery import DeliveryService
from twistedcaldav.scheduling.ischeduleservers import IScheduleServers

"""
Server to server utility functions and client requests.
"""

__all__ = [
    "ScheduleViaISchedule",
]

log = Logger()

class ScheduleViaISchedule(DeliveryService):
    
    @classmethod
    def serviceType(cls):
        return DeliveryService.serviceType_ischedule

    @classmethod
    def matchCalendarUserAddress(cls, cuaddr):

        # TODO: here is where we would attempt service discovery based on the cuaddr.
        
        # Do default match
        return super(ScheduleViaISchedule, cls).matchCalendarUserAddress(cuaddr)

    def generateSchedulingResponses(self):
        """
        Generate scheduling responses for remote recipients.
        """
        
        # Group recipients by server so that we can do a single request with multiple recipients
        # to each different server.
        groups = {}
        servermgr = IScheduleServers()
        for recipient in self.recipients:
            # Map the recipient's domain to a server
            server = servermgr.mapDomain(recipient.domain)
            if not server:
                # Cannot do server-to-server for this recipient.
                err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-allowed")))
                self.responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="5.3;No scheduling support for user")
            
                # Process next recipient
                continue
            
            if not server.allow_to:
                # Cannot do server-to-server outgoing requests for this server.
                err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-allowed")))
                self.responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="5.1;Service unavailable")
            
                # Process next recipient
                continue
            
            groups.setdefault(server, []).append(recipient)
        
        if len(groups) == 0:
            return

        # Now we process each server: let's use a DeferredList to aggregate all the Deferred's
        # we will generate for each request. That way we can have parallel requests in progress
        # rather than serialize them.
        deferreds = []
        for server, recipients in groups.iteritems():
            requestor = IScheduleRequest(self.scheduler, server, recipients, self.responses)
            deferreds.append(requestor.doRequest())

        return DeferredList(deferreds)

class IScheduleRequest(object):
    
    def __init__(self, scheduler, server, recipients, responses):

        self.scheduler = scheduler
        self.server = server
        self.recipients = recipients
        self.responses = responses
        
        self._generateHeaders()
        self._prepareData()
        
    @inlineCallbacks
    def doRequest(self):
        
        # Generate an HTTP client request
        try:
            from twisted.internet import reactor
            if self.server.ssl:
                from twistedcaldav.tap import ChainingOpenSSLContextFactory
                context = ChainingOpenSSLContextFactory(config.SSLPrivateKey, config.SSLCertificate, certificateChainFile=config.SSLAuthorityChain)
                proto = (yield ClientCreator(reactor, HTTPClientProtocol).connectSSL(self.server.host, self.server.port, context))
            else:
                proto = (yield ClientCreator(reactor, HTTPClientProtocol).connectTCP(self.server.host, self.server.port))
            
            request = ClientRequest("POST", self.server.path, self.headers, self.data)
            yield log.logRequest("debug", "Sending server-to-server POST request:", request)
            response = (yield proto.submitRequest(request))
    
            yield log.logResponse("debug", "Received server-to-server POST response:", response)
            xml = (yield davXMLFromStream(response.stream))
    
            self._parseResponse(xml)

        except Exception, e:
            # Generated failed responses for each recipient
            log.err("Could not do server-to-server request : %s %s" % (self, e))
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
