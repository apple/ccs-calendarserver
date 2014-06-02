##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

from txdav.caldav.datastore.scheduling.delivery import DeliveryService
from txdav.caldav.datastore.scheduling.utils import extractEmailDomain

__all__ = [
    "LocalCalendarUser",
    "PartitionedCalendarUser",
    "OtherServerCalendarUser",
    "RemoteCalendarUser",
    "EmailCalendarUser",
    "InvalidCalendarUser",
    "normalizeCUAddr",
]

log = Logger()

class CalendarUser(object):

    def __init__(self, cuaddr):
        self.cuaddr = cuaddr
        self.serviceType = None


    def hosted(self):
        """
        Is this user hosted on this service (this pod or any other)
        """
        return False



class LocalCalendarUser(CalendarUser):

    def __init__(self, cuaddr, principal, inbox=None):
        self.cuaddr = cuaddr
        self.principal = principal
        self.inbox = inbox
        self.serviceType = DeliveryService.serviceType_caldav


    def __str__(self):
        return "Local calendar user: %s" % (self.cuaddr,)


    def hosted(self):
        """
        Is this user hosted on this service (this pod or any other)
        """
        return True



class PartitionedCalendarUser(CalendarUser):

    def __init__(self, cuaddr, principal):
        self.cuaddr = cuaddr
        self.principal = principal
        self.serviceType = DeliveryService.serviceType_ischedule


    def __str__(self):
        return "Partitioned calendar user: %s" % (self.cuaddr,)


    def hosted(self):
        """
        Is this user hosted on this service (this pod or any other)
        """
        return True



class OtherServerCalendarUser(CalendarUser):

    def __init__(self, cuaddr, principal):
        self.cuaddr = cuaddr
        self.principal = principal
        self.serviceType = DeliveryService.serviceType_ischedule


    def __str__(self):
        return "Other server calendar user: %s" % (self.cuaddr,)


    def hosted(self):
        """
        Is this user hosted on this service (this pod or any other)
        """
        return True



class RemoteCalendarUser(CalendarUser):

    def __init__(self, cuaddr):
        self.cuaddr = cuaddr
        self.extractDomain()
        self.serviceType = DeliveryService.serviceType_ischedule


    def __str__(self):
        return "Remote calendar user: %s" % (self.cuaddr,)


    def extractDomain(self):
        if self.cuaddr.startswith("mailto:"):
            self.domain = extractEmailDomain(self.cuaddr)
        elif self.cuaddr.startswith("http://") or self.cuaddr.startswith("https://"):
            splits = self.cuaddr.split(":")[1][2:].split("/")
            self.domain = splits[0]
        else:
            self.domain = ""



class EmailCalendarUser(CalendarUser):

    def __init__(self, cuaddr):
        self.cuaddr = cuaddr
        self.serviceType = DeliveryService.serviceType_imip


    def __str__(self):
        return "Email/iMIP calendar user: %s" % (self.cuaddr,)



class InvalidCalendarUser(CalendarUser):

    def __str__(self):
        return "Invalid calendar user: %s" % (self.cuaddr,)



def normalizeCUAddr(addr):
    """
    Normalize a cuaddr string by lower()ing it if it's a mailto:, or
    removing trailing slash if it's a URL.
    @param addr: a cuaddr string to normalize
    @return: normalized string
    """
    lower = addr.lower()
    if lower.startswith("mailto:"):
        addr = lower
    if (addr.startswith("/") or
        addr.startswith("http:") or
        addr.startswith("https:")):
        return addr.rstrip("/")
    else:
        return addr



def calendarUserFromPrincipal(recipient, principal, inbox=None):
    """
    Get the appropriate calendar user address class for the provided principal.
    """

    if principal.locallyHosted():
        return LocalCalendarUser(recipient, principal, inbox)
    elif principal.thisServer():
        return PartitionedCalendarUser(recipient, principal)
    else:
        return OtherServerCalendarUser(recipient, principal)
