##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks

from twistedcaldav.config import config

from txdav.caldav.datastore.scheduling.caldav.delivery import ScheduleViaCalDAV

import twistedcaldav.test.util

class CalDAV (twistedcaldav.test.util.TestCase):
    """
    txdav.caldav.datastore.scheduling.caldav tests
    """

    @inlineCallbacks
    def test_matchCalendarUserAddress(self):
        """
        Make sure we do an exact comparison on EmailDomain
        """
        self.patch(config.Scheduling[ScheduleViaCalDAV.serviceType()], "EmailDomain", "example.com")
        result = yield ScheduleViaCalDAV.matchCalendarUserAddress("mailto:user@example.com")
        self.assertTrue(result)
        result = yield ScheduleViaCalDAV.matchCalendarUserAddress("mailto:user@foo.example.com")
        self.assertFalse(result)
        result = yield ScheduleViaCalDAV.matchCalendarUserAddress("mailto:user@xyzexample.com")
        self.assertFalse(result)
        result = yield ScheduleViaCalDAV.matchCalendarUserAddress("mailto:user@xyzexample.com?subject=foobar")
        self.assertFalse(result)
        result = yield ScheduleViaCalDAV.matchCalendarUserAddress("mailto:user")
        self.assertFalse(result)
