##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav.http import ErrorResponse
from twext.web2.http import HTTPError
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.scheduling import addressmapping
from twistedcaldav.scheduling.cuaddress import RemoteCalendarUser
from twistedcaldav.scheduling.scheduler import RemoteScheduler, \
    ScheduleResponseQueue
import itertools
import socket


"""
L{IMIPScheduler} - handles deliveries for scheduling messages being POSTed to the iMIP inbox.
"""

__all__ = [
    "IMIPScheduler",
]

log = Logger()

class IMIPScheduler(RemoteScheduler):

    scheduleResponse = ScheduleResponseQueue

    errorResponse = ErrorResponse

    errorElements = {
        "originator-missing": (caldav_namespace, "originator-specified"),
        "originator-invalid": (caldav_namespace, "originator-allowed"),
        "originator-denied": (caldav_namespace, "originator-allowed"),
        "recipient-missing": (caldav_namespace, "recipient-specified"),
        "recipient-invalid": (caldav_namespace, "recipient-exists"),
        "organizer-denied": (caldav_namespace, "organizer-allowed"),
        "attendee-denied": (caldav_namespace, "attendee-allowed"),
        "invalid-calendar-data-type": (caldav_namespace, "supported-calendar-data"),
        "invalid-calendar-data": (caldav_namespace, "valid-calendar-data"),
        "invalid-scheduling-message": (caldav_namespace, "valid-calendar-data"),
        "max-recipients": (caldav_namespace, "recipient-limit"),
    }

    def checkAuthorization(self):
        pass


    @inlineCallbacks
    def checkOriginator(self):
        """
        Check the validity of the Originator header.
        """

        # For remote requests we do not allow the originator to be a local user or one within our domain.
        originatorPrincipal = self.resource.principalForCalendarUserAddress(self.originator)
        localUser = (yield addressmapping.mapper.isCalendarUserInMyDomain(self.originator))
        if originatorPrincipal or localUser:
            log.err("Cannot use originator that is on this server: %s" % (self.originator,))
            raise HTTPError(self.errorResponse(
                responsecode.FORBIDDEN,
                self.errorElements["originator-denied"],
                "Originator cannot be local to server",
            ))
        else:
            self.originator = RemoteCalendarUser(self.originator)


    def checkOrganizerAsOriginator(self):
        pass


    def checkAttendeeAsOriginator(self):
        pass


    def securityChecks(self):
        """
        Check that the connection is from the mail gateway
        """
        allowed = config.Scheduling['iMIP']['MailGatewayServer']
        # Get the request IP and map to hostname.
        clientip = self.request.remoteAddr.host
        host, aliases, _ignore_ips = socket.gethostbyaddr(clientip)
        for host in itertools.chain((host, clientip), aliases):
            if host == allowed:
                break
        else:
            log.err("Only %s is allowed to submit internal scheduling requests, not %s" % (allowed, host))
            # TODO: verify this is the right response:
            raise HTTPError(self.errorResponse(
                responsecode.FORBIDDEN,
                self.errorElements["originator-denied"],
                "Originator server not allowed to send to this server",
            ))
