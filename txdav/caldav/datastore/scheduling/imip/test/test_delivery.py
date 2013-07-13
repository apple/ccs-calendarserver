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

from twext.web2 import responsecode

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from twistedcaldav.config import config
from twistedcaldav.ical import Component

from txdav.caldav.datastore.scheduling.cuaddress import RemoteCalendarUser
from txdav.caldav.datastore.scheduling.imip.delivery import ScheduleViaIMip
from txdav.caldav.datastore.scheduling.itip import iTIPRequestStatus
from txdav.caldav.datastore.scheduling.scheduler import ScheduleResponseQueue

class iMIPProcessing (unittest.TestCase):
    """
    iCalendar support tests
    """

    class FakeSchedule(object):

        def __init__(self, calendar):
            self.calendar = calendar


    @inlineCallbacks
    def test_no_freebusy(self):

        data = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VFREEBUSY
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VFREEBUSY
END:VCALENDAR
"""

        scheduler = iMIPProcessing.FakeSchedule(Component.fromString(data))
        recipients = (RemoteCalendarUser("mailto:user1@example.com"),)
        responses = ScheduleResponseQueue("REQUEST", responsecode.OK)

        delivery = ScheduleViaIMip(scheduler, recipients, responses, True)
        yield delivery.generateSchedulingResponses()

        self.assertEqual(len(responses.responses), 1)
        self.assertEqual(str(responses.responses[0].children[1]), iTIPRequestStatus.SERVICE_UNAVAILABLE)


    @inlineCallbacks
    def test_matchCalendarUserAddress(self):
        # iMIP not sensitive to case:
        self.patch(config.Scheduling[ScheduleViaIMip.serviceType()], "AddressPatterns", ["mailto:.*"])
        result = yield ScheduleViaIMip.matchCalendarUserAddress("mailto:user@xyzexample.com")
        self.assertTrue(result)
        result = ScheduleViaIMip.matchCalendarUserAddress("MAILTO:user@xyzexample.com")
        self.assertTrue(result)
