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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

import twistedcaldav.test.util
from twistedcaldav.ical import Component
from vobject.icalendar import utc
from vobject.icalendar import registerTzid
import datetime
import os

class Timezones (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

    data_dir = os.path.join(os.path.dirname(__file__), "data")

    def doTest(self, filename, dtstart, dtend):
        calendar = Component.fromStream(file(os.path.join(self.data_dir, filename)))
        if calendar.name() != "VCALENDAR": self.fail("Calendar is not a VCALENDAR")

        instances = calendar.expandTimeRanges(datetime.date(2100, 1, 1))
        for key in instances:
            instance = instances[key]
            start = instance.start
            end = instance.end
            self.assertEqual(start, dtstart)
            self.assertEqual(end, dtend)
            break;

    def test_truncatedApr(self):
        """
        Properties in components
        """
        
        registerTzid("America/New_York", None)
        self.doTest("TruncatedApr01.ics", datetime.datetime(2007, 04, 01, 16, 0, 0, tzinfo=utc), datetime.datetime(2007, 04, 01, 17, 0, 0, tzinfo=utc))

    def test_truncatedDec(self):
        """
        Properties in components
        """
        registerTzid("America/New_York", None)
        self.doTest("TruncatedDec10.ics", datetime.datetime(2007, 12, 10, 17, 0, 0, tzinfo=utc), datetime.datetime(2007, 12, 10, 18, 0, 0, tzinfo=utc))

    def test_truncatedAprThenDec(self):
        """
        Properties in components
        """
        registerTzid("America/New_York", None)
        self.doTest("TruncatedApr01.ics", datetime.datetime(2007, 04, 01, 16, 0, 0, tzinfo=utc), datetime.datetime(2007, 04, 01, 17, 0, 0, tzinfo=utc))
        self.doTest("TruncatedDec10.ics", datetime.datetime(2007, 12, 10, 17, 0, 0, tzinfo=utc), datetime.datetime(2007, 12, 10, 18, 0, 0, tzinfo=utc))

    def test_truncatedDecThenApr(self):
        """
        Properties in components
        """
        registerTzid("America/New_York", None)
        self.doTest("TruncatedDec10.ics", datetime.datetime(2007, 12, 10, 17, 0, 0, tzinfo=utc), datetime.datetime(2007, 12, 10, 18, 0, 0, tzinfo=utc))
        self.doTest("TruncatedApr01.ics", datetime.datetime(2007, 04, 01, 16, 0, 0, tzinfo=utc), datetime.datetime(2007, 04, 01, 17, 0, 0, tzinfo=utc))
