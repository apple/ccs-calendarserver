##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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
from vobject.icalendar import utc, getTzid
from twistedcaldav.dateops import normalizeStartEndDuration
from twistedcaldav.timezones import TimezoneCache
import datetime

#TODO: add tests for all the methods in dateops

class Tests_normalizeStartEndDuration (twistedcaldav.test.util.TestCase):
    """
    Test abstract SQL DB class
    """

    def setUp(self):
        super(Tests_normalizeStartEndDuration, self).setUp()
        
        TimezoneCache.create()
        TimezoneCache.activeCache.loadTimezone("America/New_York")

    def test_invalid(self):
        
        start = datetime.datetime(2008, 1, 1, 0, 0, 0, tzinfo=utc)
        end = datetime.datetime(2008, 1, 1, 1, 0, 0, tzinfo=utc)
        duration = end - start
        
        self.assertRaises(AssertionError, normalizeStartEndDuration, start, end, duration)

    def test_start_only_utc(self):
        
        start = datetime.datetime(2008, 1, 1, 0, 0, 0, tzinfo=utc)
        
        newstart, newend = normalizeStartEndDuration(start)
        self.assertEqual(newstart, start)
        self.assertTrue(newend is None)

    def test_start_only_float(self):
        start = datetime.datetime(2008, 1, 1, 0, 0, 0)
        
        newstart, newend = normalizeStartEndDuration(start)
        self.assertEqual(newstart, start)
        self.assertTrue(newend is None)

    def test_start_only_date(self):
        start = datetime.date(2008, 1, 1)
        
        newstart, newend = normalizeStartEndDuration(start)
        self.assertEqual(newstart, start)
        self.assertTrue(newend is None)

    def test_start_only_tzid(self):

        start = datetime.datetime(2008, 1, 1, 0, 0, 0, tzinfo=getTzid("America/New_York"))
        utcstart = datetime.datetime(2008, 1, 1, 5, 0, 0, tzinfo=utc)
        
        newstart, newend = normalizeStartEndDuration(start)
        self.assertEqual(newstart, utcstart)
        self.assertTrue(newend is None)

    def test_start_end_utc(self):

        start = datetime.datetime(2008, 1, 1, 0, 0, 0, tzinfo=utc)
        end = datetime.datetime(2008, 1, 1, 1, 0, 0, tzinfo=utc)
        
        newstart, newend = normalizeStartEndDuration(start, dtend=end)
        self.assertEqual(newstart, start)
        self.assertEqual(newend, end)

    def test_start_end_float(self):

        start = datetime.datetime(2008, 1, 1, 0, 0, 0)
        end = datetime.datetime(2008, 1, 1, 1, 0, 0)
        
        newstart, newend = normalizeStartEndDuration(start, dtend=end)
        self.assertEqual(newstart, start)
        self.assertEqual(newend, end)

    def test_start_end_date(self):

        start = datetime.date(2008, 1, 1)
        end = datetime.date(2008, 1, 2)
        
        newstart, newend = normalizeStartEndDuration(start, dtend=end)
        self.assertEqual(newstart, start)
        self.assertEqual(newend, end)

    def test_start_end_tzid(self):

        start = datetime.datetime(2008, 1, 1, 0, 0, 0, tzinfo=getTzid("America/New_York"))
        end = datetime.datetime(2008, 1, 1, 1, 0, 0, tzinfo=getTzid("America/New_York"))
        utcstart = datetime.datetime(2008, 1, 1, 5, 0, 0, tzinfo=utc)
        utcend = datetime.datetime(2008, 1, 1, 6, 0, 0, tzinfo=utc)
        
        newstart, newend = normalizeStartEndDuration(start, dtend=end)
        self.assertEqual(newstart, utcstart)
        self.assertEqual(newend, utcend)

    def test_start_duration_utc(self):

        start = datetime.datetime(2008, 1, 1, 0, 0, 0, tzinfo=utc)
        end = datetime.datetime(2008, 1, 1, 1, 0, 0, tzinfo=utc)
        duration = end - start
        
        newstart, newend = normalizeStartEndDuration(start, duration=duration)
        self.assertEqual(newstart, start)
        self.assertEqual(newend, end)

    def test_start_duration_float(self):

        start = datetime.datetime(2008, 1, 1, 0, 0, 0)
        end = datetime.datetime(2008, 1, 1, 1, 0, 0)
        duration = end - start
        
        newstart, newend = normalizeStartEndDuration(start, duration=duration)
        self.assertEqual(newstart, start)
        self.assertEqual(newend, end)

    def test_start_duration_date(self):

        start = datetime.date(2008, 1, 1)
        end = datetime.date(2008, 1, 2)
        duration = end - start
        
        newstart, newend = normalizeStartEndDuration(start, duration=duration)
        self.assertEqual(newstart, start)
        self.assertEqual(newend, end)

    def test_start_duration_tzid(self):
 
        start = datetime.datetime(2008, 1, 1, 0, 0, 0, tzinfo=getTzid("America/New_York"))
        end = datetime.datetime(2008, 1, 1, 1, 0, 0, tzinfo=getTzid("America/New_York"))
        utcstart = datetime.datetime(2008, 1, 1, 5, 0, 0, tzinfo=utc)
        utcend = datetime.datetime(2008, 1, 1, 6, 0, 0, tzinfo=utc)
        duration = end - start
        
        newstart, newend = normalizeStartEndDuration(start, duration=duration)
        self.assertEqual(newstart, utcstart)
        self.assertEqual(newend, utcend)

