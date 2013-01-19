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

import re

from twext.python.log import Logger

from twistedcaldav.config import config
from twisted.internet.defer import succeed

__all__ = [
    "DeliveryService",
]

log = Logger()

class DeliveryService(object):
    """
    Abstract base class that defines a delivery method for a scheduling message.
    """

    # Known types

    serviceType_caldav = 'CalDAV'
    serviceType_ischedule = 'iSchedule'
    serviceType_imip = 'iMIP'

    def __init__(self, scheduler, recipients, responses, freebusy):

        self.scheduler = scheduler
        self.recipients = recipients
        self.responses = responses
        self.freebusy = freebusy


    @classmethod
    def serviceType(cls):
        raise NotImplementedError


    @classmethod
    def matchCalendarUserAddress(cls, cuaddr):
        """
        Determine whether the delivery service is able to handle the specified calendar user address.

        @param cuaddr: calendar user address to test
        @type cuaddr: C{str}

        @return: L{Deferred} with result C{True} or C{False}
        """

        cuaddr = cuaddr.lower()
        # Do the pattern match
        for pattern in config.Scheduling[cls.serviceType()]["AddressPatterns"]:
            try:
                if re.match(pattern, cuaddr) is not None:
                    return succeed(True)
            except re.error:
                log.error("Invalid regular expression for Scheduling configuration '%s/LocalAddresses': %s" % (cls.serviceType(), pattern,))

        return succeed(False)


    def generateSchedulingResponses(self):
        raise NotImplementedError
