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

from twisted.python.failure import Failure
from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.log import Logger
from twext.web2.dav.http import ErrorResponse

from twext.web2 import responsecode
from twext.web2.http import HTTPError
from twisted.web import client

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.util import AuthorizedHTTPGetter
from twistedcaldav.scheduling.delivery import DeliveryService
from twistedcaldav.scheduling.itip import iTIPRequestStatus

"""
Class that handles delivery of scheduling messages via iMIP.
"""

__all__ = [
    "ScheduleViaIMip",
]

log = Logger()

class ScheduleViaIMip(DeliveryService):
    
    @classmethod
    def serviceType(cls):
        return DeliveryService.serviceType_imip

    @inlineCallbacks
    def generateSchedulingResponses(self):
        
        # Generate an HTTP client request
        try:
            # We do not do freebusy requests via iMIP
            if self.freebusy:
                raise ValueError("iMIP VFREEBUSY REQUESTs not supported.")

            method = self.scheduler.calendar.propertyValue("METHOD") 
            if method not in (
                "PUBLISH",
                "REQUEST",
                "REPLY",
                "ADD",
                "CANCEL",
                "DECLINE_COUNTER",
            ):
                log.info("Could not do server-to-imip method: %s" % (method,))
                for recipient in self.recipients:
                    err = HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "recipient-failed"),
                        "iMIP method not allowed: %s" % (method,),
                    ))
                    self.responses.add(
                        recipient.cuaddr,
                        Failure(exc_value=err),
                        reqstatus=iTIPRequestStatus.NO_USER_SUPPORT
                    )
                returnValue(None)

            caldata = str(self.scheduler.calendar)

            for recipient in self.recipients:
                try:
                    toAddr = str(recipient.cuaddr)
                    if not toAddr.lower().startswith("mailto:"):
                        raise ValueError("ATTENDEE address '%s' must be mailto: for iMIP operation." % (toAddr,))

                    fromAddr = str(self.scheduler.originator.cuaddr)

                    log.debug("POSTing iMIP message to gateway...  To: '%s', From :'%s'\n%s" % (toAddr, fromAddr, caldata,))
                    yield self.postToGateway(fromAddr, toAddr, caldata)
        
                except Exception, e:
                    # Generated failed response for this recipient
                    log.err("Could not do server-to-imip request : %s %s" % (self, e))
                    err = HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "recipient-failed"),
                        "iMIP request failed",
                    ))
                    self.responses.add(
                        recipient.cuaddr,
                        Failure(exc_value=err),
                        reqstatus=iTIPRequestStatus.SERVICE_UNAVAILABLE
                    )
                
                else:
                    self.responses.add(
                        recipient.cuaddr,
                        responsecode.OK,
                        reqstatus=iTIPRequestStatus.MESSAGE_SENT
                    )

        except Exception, e:
            # Generated failed responses for each recipient
            log.err("Could not do server-to-imip request : %s %s" % (self, e))
            for recipient in self.recipients:
                err = HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "recipient-failed"),
                    "iMIP request failed",
                ))
                self.responses.add(
                    recipient.cuaddr,
                    Failure(exc_value=err),
                    reqstatus=iTIPRequestStatus.SERVICE_UNAVAILABLE
                )

    def postToGateway(self, fromAddr, toAddr, caldata, reactor=None):
        if reactor is None:
            from twisted.internet import reactor

        mailGatewayServer = config.Scheduling['iMIP']['MailGatewayServer']
        mailGatewayPort = config.Scheduling['iMIP']['MailGatewayPort']
        url = "http://%s:%d/inbox" % (mailGatewayServer, mailGatewayPort)
        headers = {
            'Content-Type' : 'text/calendar',
            'Originator' : fromAddr,
            'Recipient' : toAddr,
            config.Scheduling.iMIP.Header : config.Scheduling.iMIP.Password,
        }
        factory = client.HTTPClientFactory(url, method='POST', headers=headers,
            postdata=caldata, agent="CalDAV server")

        factory.noisy = False
        factory.protocol = AuthorizedHTTPGetter
        reactor.connectTCP(mailGatewayServer, mailGatewayPort, factory)
        return factory.deferred

