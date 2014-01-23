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
from txweb2.dav.http import ErrorResponse
from twisted.internet.defer import succeed
from twistedcaldav.caldavxml import caldav_namespace
from txdav.caldav.datastore.scheduling.cuaddress import RemoteCalendarUser
from txdav.caldav.datastore.scheduling.scheduler import RemoteScheduler
from txdav.caldav.datastore.scheduling.scheduler import ScheduleResponseQueue


"""
L{IMIPScheduler} - handles deliveries for scheduling messages retrieved via
mail
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


    def checkOriginator(self):
        """
        The originator always comes out of the tokens db
        """
        self.originator = RemoteCalendarUser(self.originator)
        return succeed(None)


    def checkOrganizerAsOriginator(self):
        pass


    def checkAttendeeAsOriginator(self):
        pass


    def securityChecks(self):
        pass
