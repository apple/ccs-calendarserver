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

from twistedcaldav.log import Logger
from twistedcaldav.scheduling.delivery import DeliveryService

__all__ = [
    "LocalCalendarUser",
    "RemoteCalendarUser",
    "EmailCalendarUser",
    "InvalidCalendarUser",
]

log = Logger()

class CalendarUser(object):
    def __init__(self, cuaddr):
        self.cuaddr = cuaddr
        self.serviceType = None

class LocalCalendarUser(CalendarUser):
    def __init__(self, cuaddr, principal, inbox=None, inboxURL=None):
        self.cuaddr = cuaddr
        self.principal = principal
        self.inbox = inbox
        self.inboxURL = inboxURL
        self.serviceType = DeliveryService.serviceType_caldav
    
    def __str__(self):
        return "Local calendar user: %s" % (self.cuaddr,)

class RemoteCalendarUser(CalendarUser):
    def __init__(self, cuaddr):
        self.cuaddr = cuaddr
        self.extractDomain()
        self.serviceType = DeliveryService.serviceType_ischedule

    def __str__(self):
        return "Remote calendar user: %s" % (self.cuaddr,)
    
    def extractDomain(self):
        if self.cuaddr.startswith("mailto:"):
            splits = self.cuaddr[7:].split("?")
            self.domain = splits[0].split("@")[1]
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

