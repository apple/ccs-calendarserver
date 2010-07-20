##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Tests for L{txcaldav.calendarstore.scheduling}.
"""

from twisted.trial.unittest import TestCase
from txcaldav.calendarstore.test.common import CommonTests
from txcaldav.calendarstore.test.test_file import setUpCalendarStore
from txcaldav.calendarstore.scheduling import ImplicitStore

simpleEvent = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
"""

class ImplicitStoreTests(CommonTests, TestCase):
    """
    Tests for L{ImplicitSchedulingStore}.
    """

    def storeUnderTest(self):
        setUpCalendarStore(self)
        self.implicitStore = ImplicitStore(self.calendarStore)
        return self.implicitStore
