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
from twisted.trial.unittest import SkipTest
from pycalendar.datetime import PyCalendarDateTime

from twistedcaldav.dateops import parseSQLTimestampToPyCalendar, \
    parseSQLDateToPyCalendar, pyCalendarTodatetime, \
    normalizeForExpand, normalizeForIndex, normalizeToUTC, timeRangesOverlap

import datetime
import dateutil
from pycalendar.timezone import PyCalendarTimezone
from twistedcaldav.timezones import TimezoneCache

class Dateops(twistedcaldav.test.util.TestCase):
    """
    dateops.py tests
    """

    def setUp(self):
        super(Dateops, self).setUp()
        TimezoneCache.create()


    def test_normalizeForIndex(self):
        """
        Test that dateops.normalizeForIndex works correctly on all four types of date/time: date only, floating, UTC and local time.
        """

        data = (
            (PyCalendarDateTime(2012, 1, 1), PyCalendarDateTime(2012, 1, 1, 0, 0, 0)),
            (PyCalendarDateTime(2012, 1, 1, 10, 0, 0), PyCalendarDateTime(2012, 1, 1, 10, 0, 0)),
            (PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)), PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True))),
            (PyCalendarDateTime(2012, 1, 1, 12, 0, 0, tzid=PyCalendarTimezone(tzid="America/New_York")), PyCalendarDateTime(2012, 1, 1, 17, 0, 0, tzid=PyCalendarTimezone(utc=True))),
        )

        for value, result in data:
            self.assertEqual(normalizeForIndex(value), result)


    def test_normalizeToUTC(self):
        """
        Test that dateops.normalizeToUTC works correctly on all four types of date/time: date only, floating, UTC and local time.
        """

        data = (
            (PyCalendarDateTime(2012, 1, 1), PyCalendarDateTime(2012, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))),
            (PyCalendarDateTime(2012, 1, 1, 10, 0, 0), PyCalendarDateTime(2012, 1, 1, 10, 0, 0, tzid=PyCalendarTimezone(utc=True))),
            (PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)), PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True))),
            (PyCalendarDateTime(2012, 1, 1, 12, 0, 0, tzid=PyCalendarTimezone(tzid="America/New_York")), PyCalendarDateTime(2012, 1, 1, 17, 0, 0, tzid=PyCalendarTimezone(utc=True))),
        )

        for value, result in data:
            self.assertEqual(normalizeToUTC(value), result)


    def test_normalizeForExpand(self):
        """
        Test that dateops.normalizeForExpand works correctly on all four types of date/time: date only, floating, UTC and local time.
        """

        data = (
            (PyCalendarDateTime(2012, 1, 1), PyCalendarDateTime(2012, 1, 1)),
            (PyCalendarDateTime(2012, 1, 1, 10, 0, 0), PyCalendarDateTime(2012, 1, 1, 10, 0, 0)),
            (PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)), PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True))),
            (PyCalendarDateTime(2012, 1, 1, 12, 0, 0, tzid=PyCalendarTimezone(tzid="America/New_York")), PyCalendarDateTime(2012, 1, 1, 17, 0, 0, tzid=PyCalendarTimezone(utc=True))),
        )

        for value, result in data:
            self.assertEqual(normalizeForExpand(value), result)


    def test_floatoffset(self):
        raise SkipTest("test unimplemented")


    def test_adjustFloatingToTimezone(self):
        raise SkipTest("test unimplemented")


    def test_compareDateTime(self):
        raise SkipTest("test unimplemented")


    def test_differenceDateTime(self):
        raise SkipTest("test unimplemented")


    def test_timeRangesOverlap(self):

        data = (
            # Timed
            (
                "Start within, end within - overlap",
                PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                True,
            ),
            (
                "Start before, end before - no overlap",
                PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 3, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                False,
            ),
            (
                "Start before, end right before - no overlap",
                PyCalendarDateTime(2012, 1, 1, 23, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 3, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                False,
            ),
            (
                "Start before, end within - overlap",
                PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 3, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                True,
            ),
            (
                "Start after, end after - no overlap",
                PyCalendarDateTime(2012, 1, 2, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                False,
            ),
            (
                "Start right after, end after - no overlap",
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 1, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                False,
            ),
            (
                "Start within, end after - overlap",
                PyCalendarDateTime(2012, 1, 1, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 12, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                True,
            ),
            (
                "Start before, end after - overlap",
                PyCalendarDateTime(2012, 1, 1, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 3, 11, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 2, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 3, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                True,
            ),

            # All day
            (
                "All day: Start within, end within - overlap",
                PyCalendarDateTime(2012, 1, 9),
                PyCalendarDateTime(2012, 1, 10),
                PyCalendarDateTime(2012, 1, 8, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                True,
            ),
            (
                "All day: Start before, end before - no overlap",
                PyCalendarDateTime(2012, 1, 1),
                PyCalendarDateTime(2012, 1, 2),
                PyCalendarDateTime(2012, 1, 8, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                False,
            ),
            (
                "All day: Start before, end right before - no overlap",
                PyCalendarDateTime(2012, 1, 7),
                PyCalendarDateTime(2012, 1, 8),
                PyCalendarDateTime(2012, 1, 8, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                False,
            ),
            (
                "All day: Start before, end within - overlap",
                PyCalendarDateTime(2012, 1, 7),
                PyCalendarDateTime(2012, 1, 9),
                PyCalendarDateTime(2012, 1, 8, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                True,
            ),
            (
                "All day: Start after, end after - no overlap",
                PyCalendarDateTime(2012, 1, 16),
                PyCalendarDateTime(2012, 1, 17),
                PyCalendarDateTime(2012, 1, 8, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                False,
            ),
            (
                "All day: Start right after, end after - no overlap",
                PyCalendarDateTime(2012, 1, 15),
                PyCalendarDateTime(2012, 1, 16),
                PyCalendarDateTime(2012, 1, 8, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                False,
            ),
            (
                "All day: Start within, end after - overlap",
                PyCalendarDateTime(2012, 1, 14),
                PyCalendarDateTime(2012, 1, 16),
                PyCalendarDateTime(2012, 1, 8, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                True,
            ),
            (
                "All day: Start before, end after - overlap",
                PyCalendarDateTime(2012, 1, 7),
                PyCalendarDateTime(2012, 1, 16),
                PyCalendarDateTime(2012, 1, 8, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                PyCalendarDateTime(2012, 1, 15, 0, 0, 0, tzid=PyCalendarTimezone(utc=True)),
                True,
            ),
        )

        for title, start1, end1, start2, end2, result in data:
            self.assertEqual(timeRangesOverlap(start1, end1, start2, end2), result, msg="Failed: %s" % (title,))


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
