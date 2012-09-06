##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.log import Logger

from twistedcaldav.config import config
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.scheduling.caldav import ScheduleViaCalDAV
from twistedcaldav.scheduling.delivery import DeliveryService
from twistedcaldav.scheduling.imip import ScheduleViaIMip
from twistedcaldav.scheduling.ischedule import ScheduleViaISchedule
from twistedcaldav.scheduling.cuaddress import RemoteCalendarUser, EmailCalendarUser, InvalidCalendarUser,\
    calendarUserFromPrincipal

__all__ = [
    "ScheduleAddressMapper",
    "mapper",
]

log = Logger()

"""
Handle mapping a calendar user address to a schedule delivery type.
"""

class ScheduleAddressMapper(object):
    """
    Class that maps a calendar user address into a delivery service type.
    """
    
    def __init__(self):
        
        # We are going to cache mappings whilst running
        self.cache = Memcacher("ScheduleAddressMapper", no_invalidation=True)

    @inlineCallbacks
    def getCalendarUser(self, cuaddr, principal):
        
        # If we have a principal always treat the user as local or partitioned
        if principal:
            returnValue(calendarUserFromPrincipal(cuaddr, principal))

        # Get the type
        cuaddr_type = (yield self.getCalendarUserServiceType(cuaddr))
        if cuaddr_type == DeliveryService.serviceType_caldav:
            returnValue(InvalidCalendarUser(cuaddr))
        elif cuaddr_type == DeliveryService.serviceType_ischedule:
            returnValue(RemoteCalendarUser(cuaddr))
        elif cuaddr_type == DeliveryService.serviceType_imip:
            returnValue(EmailCalendarUser(cuaddr))
        else:
            returnValue(InvalidCalendarUser(cuaddr))

    @inlineCallbacks
    def getCalendarUserServiceType(self, cuaddr):

        # Try cache first
        cuaddr_type = (yield self.cache.get(str(cuaddr)))
        if cuaddr_type is None:
            
            serviceTypes = (ScheduleViaCalDAV,)
            if config.Scheduling[DeliveryService.serviceType_ischedule]["Enabled"]:
                serviceTypes += (ScheduleViaISchedule,)
            if config.Scheduling[DeliveryService.serviceType_imip]["Enabled"]:
                serviceTypes += (ScheduleViaIMip,)
            for service in serviceTypes:
                if service.matchCalendarUserAddress(cuaddr):
                    yield self.cache.set(str(cuaddr), service.serviceType())
                    returnValue(service.serviceType())

        returnValue(cuaddr_type)

    def isCalendarUserInMyDomain(self, cuaddr):

        # Check whether it is a possible local address
        def _gotResult(serviceType):
            return serviceType == DeliveryService.serviceType_caldav
            
        d = self.getCalendarUserServiceType(cuaddr)
        d.addCallback(_gotResult)
        return d

mapper = ScheduleAddressMapper()
