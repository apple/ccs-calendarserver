##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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
from twisted.trial.unittest import SkipTest
from pycalendar.datetime import PyCalendarDateTime
from twistedcaldav.dateops import parseSQLTimestampToPyCalendar,\
    parseSQLDateToPyCalendar, parseSQLTimestamp, pyCalendarTodatetime
import datetime
import dateutil

class Dateops(twistedcaldav.test.util.TestCase):
    """
    dateops.py tests
    """

    def test_normalizeForIndex(self):
        raise SkipTest("test unimplemented")

    def test_normalizeToUTC(self):
        raise SkipTest("test unimplemented")

    def test_floatoffset(self):
        raise SkipTest("test unimplemented")

    def test_adjustFloatingToTimezone(self):
        raise SkipTest("test unimplemented")

    def test_compareDateTime(self):
        raise SkipTest("test unimplemented")

    def test_differenceDateTime(self):
        raise SkipTest("test unimplemented")

    def test_timeRangesOverlap(self):
        raise SkipTest("test unimplemented")

    def test_normalizePeriodList(self):
        raise SkipTest("test unimplemented")

    def test_clipPeriod(self):
        raise SkipTest("test unimplemented")

    def test_pyCalendarTodatetime(self):
        """
        dateops.pyCalendarTodatetime
        """
        
        tests = (
            (PyCalendarDateTime(2012, 4, 4, 12, 34, 56), datetime.datetime(2012, 4, 4, 12, 34, 56, tzinfo=dateutil.tz.tzutc())),
            (PyCalendarDateTime(2012, 12, 31), datetime.date(2012, 12, 31)),
        )

        for pycal, result in tests:
            self.assertEqual(pyCalendarTodatetime(pycal), result)

    def test_parseSQLTimestamp(self):
        """
        dateops.parseSQLTimestamp
        """
        
        tests = (
            ("2012-04-04 12:34:56", datetime.datetime(2012, 4, 4, 12, 34, 56)),
            ("2012-12-31 01:01:01", datetime.datetime(2012, 12, 31, 1, 1, 1)),
        )

        for sqlStr, result in tests:
            self.assertEqual(parseSQLTimestamp(sqlStr), result)

    def test_parseSQLTimestampToPyCalendar(self):
        """
        dateops.parseSQLTimestampToPyCalendar
        """
        
        tests = (
            ("2012-04-04 12:34:56", PyCalendarDateTime(2012, 4, 4, 12, 34, 56)),
            ("2012-12-31 01:01:01", PyCalendarDateTime(2012, 12, 31, 1, 1, 1)),
        )

        for sqlStr, result in tests:
            self.assertEqual(parseSQLTimestampToPyCalendar(sqlStr), result)

    def test_parseSQLDateToPyCalendar(self):
        """
        dateops.parseSQLDateToPyCalendar
        """
        
        tests = (
            ("2012-04-04", PyCalendarDateTime(2012, 4, 4)),
            ("2012-12-31 00:00:00", PyCalendarDateTime(2012, 12, 31)),
        )

        for sqlStr, result in tests:
            self.assertEqual(parseSQLDateToPyCalendar(sqlStr), result)

    def test_datetimeMktime(self):
        raise SkipTest("test unimplemented")

