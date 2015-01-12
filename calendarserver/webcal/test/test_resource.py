##
# Copyright (c) 2012-2015 Apple Inc. All rights reserved.
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

from twistedcaldav.test.util import TestCase
from twistedcaldav.config import config
import calendarserver.webcal.resource
from calendarserver.webcal.resource import getLocalTimezone, DEFAULT_TIMEZONE



class DefaultTimezoneTests(TestCase):

    def stubLookup(self):
        return self._storedLookup


    def stubHasTZ(self, ignored):
        return self._storedHasTZ.pop()


    def setUp(self):
        self.patch(
            calendarserver.webcal.resource, "lookupSystemTimezone",
            self.stubLookup
        )
        self.patch(
            calendarserver.webcal.resource, "hasTZ", self.stubHasTZ
        )


    def test_getLocalTimezone(self):

        # Empty config, system timezone known = use system timezone
        self.patch(config, "DefaultTimezone", "")
        self._storedLookup = "America/New_York"
        self._storedHasTZ = [True]
        self.assertEquals(getLocalTimezone(), "America/New_York")

        # Empty config, system timezone unknown = use DEFAULT_TIMEZONE
        self.patch(config, "DefaultTimezone", "")
        self._storedLookup = "Unknown/Unknown"
        self._storedHasTZ = [False]
        self.assertEquals(getLocalTimezone(), DEFAULT_TIMEZONE)

        # Known config value = use config value
        self.patch(config, "DefaultTimezone", "America/New_York")
        self._storedHasTZ = [True]
        self.assertEquals(getLocalTimezone(), "America/New_York")

        # Unknown config value, system timezone known = use system timezone
        self.patch(config, "DefaultTimezone", "Unknown/Unknown")
        self._storedLookup = "America/New_York"
        self._storedHasTZ = [True, False]
        self.assertEquals(getLocalTimezone(), "America/New_York")

        # Unknown config value, system timezone unknown = use DEFAULT_TIMEZONE
        self.patch(config, "DefaultTimezone", "Unknown/Unknown")
        self._storedLookup = "Unknown/Unknown"
        self._storedHasTZ = [False, False]
        self.assertEquals(getLocalTimezone(), DEFAULT_TIMEZONE)
