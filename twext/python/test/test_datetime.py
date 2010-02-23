##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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

from datetime import date, datetime, timedelta

from twext.python.datetime import dateordatetime, timerange, utc

from twistedcaldav.test.util import TestCase, testUnimplemented


class DatetimeTests(TestCase):
    def test_date_date(self):
        d = date.today()
        dodt = dateordatetime(d)
        self.assertEquals(dodt.date(), d)

    def test_date_date_tz(self):
        d = date.today()
        dodt = dateordatetime(d, defaultTZ=utc)
        self.assertEquals(dodt.date(), d)

    def test_date_datetime(self):
        d = date.today()
        dodt = dateordatetime(d)
        self.assertEquals(dodt.datetime(), datetime(d.year, d.month, d.day))

    def test_date_datetime_tz(self):
        d = date.today()
        dodt = dateordatetime(d, defaultTZ=utc)
        self.assertEquals(dodt.datetime(), datetime(d.year, d.month, d.day, tzinfo=utc))

    def test_datetime_date(self):
        dt = datetime.now()
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.date(), dt.date())

    def test_datetime_datetime(self):
        dt = datetime.now()
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.datetime(), dt)

    def test_datetime_datetime_tz(self):
        dt = datetime.now()
        dodt = dateordatetime(dt, defaultTZ=utc)
        self.assertEquals(dodt.datetime(), dt)

    def test_compare_datetime(self):
        now = datetime.now()

        first  = dateordatetime(now + timedelta(seconds=8*0))
        second = dateordatetime(now + timedelta(seconds=8*1))
        third  = dateordatetime(now + timedelta(seconds=8*2))

        #
        # date & datetime's comparators do not correctly return
        # NotImplemented when they should, which breaks comparison
        # operators if date/datetime is first.  Boo.  Seriously weak.
        #

        self.assertTrue (first             == first.datetime() )
       #self.assertTrue (first.datetime()  == first            ) # Bug in datetime
        self.assertTrue (first             == first.datetime() )
        self.assertTrue (first             != second.datetime())
        self.assertTrue (first.datetime()  != second           )
        self.assertTrue (first             != second           )
        self.assertTrue (first             <  second           )
        self.assertTrue (second            <  third            )
        self.assertTrue (first             <  second.datetime())
       #self.assertTrue (second.datetime() <  third            ) # Bug in datetime
        self.assertTrue (first             <  second           )
        self.assertTrue (second            <  third            )
       #self.assertTrue (first.datetime()  <  second           )
        self.assertTrue (second            <  third.datetime() ) # Bug in datetime
        self.assertTrue (first             <= second           )
        self.assertTrue (second            <= third            )
        self.assertTrue (first             <= second.datetime())
       #self.assertTrue (second.datetime() <= third            ) # Bug in datetime
        self.assertTrue (first             <= second.datetime())
       #self.assertTrue (second.datetime() <= third            ) # Bug in datetime
        self.assertTrue (first             <= second           )
        self.assertTrue (second            <= third            )
       #self.assertTrue (first.datetime()  <= second           ) # Bug in datetime
        self.assertTrue (second            <= third.datetime() )
        self.assertFalse(first             >  second           )
        self.assertFalse(second            >  third            )
        self.assertFalse(first             >  second.datetime())
       #self.assertFalse(second.datetime() >  third            ) # Bug in datetime
        self.assertFalse(first             >  second           )
        self.assertFalse(second            >  third            )
       #self.assertFalse(first.datetime()  >  second           ) # Bug in datetime
        self.assertFalse(second            >  third.datetime() )
        self.assertFalse(first             >= second           )
        self.assertFalse(second            >= third            )
        self.assertFalse(first             >= second.datetime())
       #self.assertFalse(second.datetime() >= third            ) # Bug in datetime
        self.assertFalse(first             >= second           )
        self.assertFalse(second            >= third            )
       #self.assertFalse(first.datetime()  >= second           ) # Bug in datetime
        self.assertFalse(second            >= third.datetime() )

    def test_date_iCalendarString(self):
        d = date(2010, 2, 22)
        dodt = dateordatetime(d)
        self.assertEquals(dodt.iCalendarString(), "20100222")

    def test_datetime_iCalendarString(self):
        dt = datetime(2010, 2, 22, 17, 44, 42, 98303)
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.iCalendarString(), "20100222T174442")

    def test_datetime_iCalendarString_utc(self):
        dt = datetime(2010, 2, 22, 17, 44, 42, 98303, tzinfo=utc)
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.iCalendarString(), "20100222T174442Z")

    @testUnimplemented
    def test_datetime_iCalendarString_tz(self):
        # Need to test a non-UTC timezone also
        raise NotImplementedError()

    @testUnimplemented
    def test_asTimeZone(self):
        raise NotImplementedError()

    @testUnimplemented
    def test_asUTC(self):
        raise NotImplementedError()

class TimerangeTests(TestCase):
    def test_start(self):
        start = datetime.now()
        tr = timerange(start=start)
        self.assertEquals(tr.start(), start)

    def test_start_none(self):
        tr = timerange()
        self.assertEquals(tr.start(), None)

    def test_end(self):
        end = datetime.now()
        tr = timerange(end=end)
        self.assertEquals(tr.end(), end)

    def test_end_none(self):
        tr = timerange()
        self.assertEquals(tr.end(), None)

    def test_end_none_duration(self):
        duration = timedelta(seconds=8)
        tr = timerange(duration=duration)
        self.assertEquals(tr.end(), None)

    def test_end_none_duration_start(self):
        start = datetime.now()
        duration = timedelta(seconds=8)
        tr = timerange(start=start, duration=duration)
        self.assertEquals(tr.end(), start + duration)

    def test_duration(self):
        duration = timedelta(seconds=8)
        tr = timerange(duration=duration)
        self.assertEquals(tr.duration(), duration)

    def test_duration_none(self):
        tr = timerange()
        self.assertEquals(tr.duration(), None)

    def test_duration_none_end(self):
        end = datetime.now()
        tr = timerange(end=end)
        self.assertEquals(tr.duration(), None)

    def test_duration_none_start_end(self):
        start = datetime.now()
        duration = timedelta(seconds=8)
        end = start + duration
        tr = timerange(start=start, end=end)
        self.assertEquals(tr.duration(), duration)

    @testUnimplemented
    def test_overlapsWith(self):
        # Need a few tests; combinations of:
        #  - start/end are None
        #  - overlapping and not
        #  - dates and datetimes
        #  - timezones
        raise NotImplementedError()
