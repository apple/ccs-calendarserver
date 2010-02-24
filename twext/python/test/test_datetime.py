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

from twisted.internet.defer import DeferredList

from twext.python.datetime import dateordatetime, timerange, utc, tzWithID

from twistedcaldav.test.util import TestCase, testUnimplemented

tzNYC = tzWithID("America/New_York")


def timezones(f):
    """
    Decorator for a test to be called with multiple timezones.
    """
    return lambda self: DeferredList([
        d for d in (
            f(self, tz) for tz in (utc, tzNYC)
        ) if d is not None
    ])

class DatetimeTests(TestCase):
    def test_date_date(self):
        d = date.today()
        dodt = dateordatetime(d)
        self.assertEquals(dodt.date(), d)

    @timezones
    def test_date_date_tz(self, tz):
        d = date.today()
        dodt = dateordatetime(d, defaultTZ=tz)
        self.assertEquals(dodt.date(), d)

    def test_date_datetime(self):
        d = date.today()
        dodt = dateordatetime(d)
        self.assertEquals(dodt.datetime(), datetime(d.year, d.month, d.day))

    @timezones
    def test_date_datetime_tz(self, tz):
        d = date.today()
        dodt = dateordatetime(d, defaultTZ=tz)
        self.assertEquals(dodt.datetime(), datetime(d.year, d.month, d.day, tzinfo=tz))

    def test_datetime_date(self):
        dt = datetime.now()
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.date(), dt.date())

    def test_datetime_datetime(self):
        dt = datetime.now()
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.datetime(), dt)

    @timezones
    def test_datetime_datetime_tz(self, tz):
        dt = datetime.now()
        dodt = dateordatetime(dt, defaultTZ=tz)
        self.assertEquals(dodt.datetime(), dt)

    def test_compare_date_date(self):
        return self._test_compare(date, date.today())

    def test_compare_date_datetime(self):
        return self._test_compare(date, datetime.now())

    @timezones
    def test_compare_date_datetime_tz(self, tz):
        return self._test_compare(date, datetime.now(), tz=tz)

    def test_compare_datetime_date(self):
        return self._test_compare(datetime, date.today())

    def test_compare_datetime_datetime(self):
        return self._test_compare(datetime, datetime.now())

    @timezones
    def test_compare_datetime_datetime_tz(self, tz):
        return self._test_compare(datetime, datetime.now(), tz=tz)

    def _test_compare(self, baseclass, now, tz=None):
        first  = dateordatetime(now + timedelta(days=0))
        second = dateordatetime(now + timedelta(days=1))
        third  = dateordatetime(now + timedelta(days=2))

        def base(dodt):
            if tz:
                return dodt.dateOrDatetime().replace(tzinfo=tz)
            else:
                return dodt.dateOrDatetime()

        #
        # date & datetime's comparators do not correctly return
        # NotImplemented when they should, which breaks comparison
        # operators if date/datetime is first.  Boo.  Seriously weak.
        #

        self.assertTrue (first        == base(first) )
       #self.assertTrue (base(first)  == first       ) # Bug in datetime
        self.assertTrue (first        == base(first) )
        self.assertTrue (first        != base(second))
        self.assertTrue (base(first)  != second      )
        self.assertTrue (first        != second      )
        self.assertTrue (first        <  second      )
        self.assertTrue (second       <  third       )
        self.assertTrue (first        <  base(second))
       #self.assertTrue (base(second) <  third       ) # Bug in datetime
        self.assertTrue (first        <  second      )
        self.assertTrue (second       <  third       )
       #self.assertTrue (base(first)  <  second      )
        self.assertTrue (second       <  base(third) ) # Bug in datetime
        self.assertTrue (first        <= second      )
        self.assertTrue (second       <= third       )
        self.assertTrue (first        <= base(second))
       #self.assertTrue (base(second) <= third       ) # Bug in datetime
        self.assertTrue (first        <= base(second))
       #self.assertTrue (base(second) <= third       ) # Bug in datetime
        self.assertTrue (first        <= second      )
        self.assertTrue (second       <= third       )
       #self.assertTrue (base(first)  <= second      ) # Bug in datetime
        self.assertTrue (second       <= base(third) )
        self.assertFalse(first        >  second      )
        self.assertFalse(second       >  third       )
        self.assertFalse(first        >  base(second))
       #self.assertFalse(base(second) >  third       ) # Bug in datetime
        self.assertFalse(first        >  second      )
        self.assertFalse(second       >  third       )
       #self.assertFalse(base(first)  >  second      ) # Bug in datetime
        self.assertFalse(second       >  base(third) )
        self.assertFalse(first        >= second      )
        self.assertFalse(second       >= third       )
        self.assertFalse(first        >= base(second))
       #self.assertFalse(base(second) >= third       ) # Bug in datetime
        self.assertFalse(first        >= second      )
        self.assertFalse(second       >= third       )
       #self.assertFalse(base(first)  >= second      ) # Bug in datetime
        self.assertFalse(second       >= base(third) )

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

    def test_datetime_iCalendarString_tz(self):
        dt = datetime(2010, 2, 22, 17, 44, 42, 98303, tzinfo=tzNYC)
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.iCalendarString(), "20100222T174442")

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
