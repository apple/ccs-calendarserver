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

import twistedcaldav.test.util
from twisted.internet.defer import inlineCallbacks
from twisted.python.modules import getModule
from twistedcaldav.config import config
from twistedcaldav.scheduling.ischedule import utils
from twisted.names import client
from txdav.caldav.datastore.scheduling.ischedule.delivery import ScheduleViaISchedule

class CalDAV (twistedcaldav.test.util.TestCase):
    """
    twistedcaldav.scheduling.caldav tests
    """

    def tearDown(self):
        """
        By setting the resolver to None, it will be recreated next time a name
        lookup is done.
        """
        client.theResolver = None
        utils.DebugResolver = None


    @inlineCallbacks
    def test_matchCalendarUserAddress(self):
        """
        Make sure we do an exact comparison on EmailDomain
        """

        self.patch(config.Scheduling.iSchedule, "RemoteServers", "")

        # Only mailtos:
        result = yield ScheduleViaISchedule.matchCalendarUserAddress("http://example.com/principal/user")
        self.assertFalse(result)

        # Need to setup a fake resolver
        module = getModule(__name__)
        dataPath = module.filePath.sibling("data")
        bindPath = dataPath.child("db.example.com")
        self.patch(config.Scheduling.iSchedule, "DNSDebug", bindPath.path)
        utils.DebugResolver = None
        utils._initResolver()

        result = yield ScheduleViaISchedule.matchCalendarUserAddress("mailto:user@example.com")
        self.assertTrue(result)
        result = yield ScheduleViaISchedule.matchCalendarUserAddress("mailto:user@example.org")
        self.assertFalse(result)
