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
from dateutil.tz import tzstr

from twisted.internet.defer import DeferredList

from twext.python.datetime import dateordatetime, timerange, utc

from twistedcaldav.test.util import TestCase


tzUSEastern = tzstr("EST5EDT")


def timezones(f):
    """
    Decorator for a test to be called with multiple timezones.
    """
    return lambda self: DeferredList([
        d for d in (
            f(self, tz) for tz in (None, utc, tzUSEastern)
        ) if d is not None
    ])

def timeSeries(n):
    now = datetime.now()
    for i in range(0, n):
        dodt = dateordatetime(now + timedelta(days=i))
        dodt.n = "t%d" %(i+1,)
        yield dodt


class DatetimeTests(TestCase):
    @timezones
    def test_date_date(self, tz):
        d = date.today()
        dodt = dateordatetime(d, defaultTZ=tz)
        self.assertEquals(dodt.date(), d)

    @timezones
    def test_date_datetime(self, tz):
        d = date.today()
        dodt = dateordatetime(d, defaultTZ=tz)
        self.assertEquals(dodt.datetime(), datetime(d.year, d.month, d.day, tzinfo=tz))

    def test_datetime_date(self):
        dt = datetime.now()
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.date(), dt.date())

    @timezones
    def test_datetime_datetime(self, tz):
        dt = datetime.now()
        dodt = dateordatetime(dt, defaultTZ=tz)
        self.assertEquals(dodt.datetime(), dt)

    def test_compare_date_date(self):
        return self._test_compare(date, date.today())

    @timezones
    def test_compare_date_datetime(self, tz):
        return self._test_compare(date, datetime.now(), tz=tz)

    def test_compare_datetime_date(self):
        return self._test_compare(datetime, date.today())

    @timezones
    def test_compare_datetime_datetime(self, tz):
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
        dt = datetime(2010, 2, 22, 17, 44, 42, 98303, tzinfo=tzUSEastern)
        dodt = dateordatetime(dt)
        self.assertEquals(dodt.iCalendarString(), "20100222T174442")

    def test_asTimeZone(self):
        dt = datetime(2010, 2, 22, 17, 44, 42, 98303, tzinfo=utc)
        asUTC = dateordatetime(dt)
        asEast = asUTC.asTimeZone(tzUSEastern)
        self.assertEquals(asEast.datetime().tzinfo, tzUSEastern) # tz is changed
        self.assertEquals(asEast.datetime().hour, 12)            # hour is changed
        self.assertEquals(asUTC, asEast)                         # still equal

    def test_asUTC(self):
        dt = datetime(2010, 2, 22, 17, 44, 42, 98303, tzinfo=tzUSEastern)
        asEast = dateordatetime(dt)
        asUTC = asEast.asTimeZone(utc)
        self.assertEquals(asUTC.datetime().tzinfo, utc) # tz is changed
        self.assertEquals(asUTC.datetime().hour, 22)    # hour is changed
        self.assertEquals(asEast, asUTC)                # still equal


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

    def test_overlapsWith(self):
        t1, t2, t3, t4 = timeSeries(4)

        d1 = dateordatetime(t1.date()); d1.n = "d1"
        d2 = dateordatetime(t2.date()); d2.n = "d2"
        d3 = dateordatetime(t3.date()); d3.n = "d3"
        d4 = dateordatetime(t4.date()); d4.n = "d4"

        for start1, end1, start2, end2, overlaps in (
            # T-T-T-T

            (t1, t2, t1, t2, True ),
            (t1, t2, t1, t3, True ),
            (t1, t2, t2, t3, False),
            (t1, t2, t3, t4, False),

            (t1, t3, t1, t2, True ),
            (t1, t3, t2, t3, True ),

            (t2, t3, t1, t2, False),
            (t2, t3, t1, t3, True ),
            (t2, t3, t1, t4, True ),

            (t2, t4, t1, t3, True ),

            (t3, t4, t1, t2, False),

            # D-T-T-T

            (d1, t2, t1, t2, True ),
            (d1, t2, t1, t3, True ),
            (d1, t2, t2, t3, False),
            (d1, t2, t3, t4, False),

            (d1, t3, t1, t2, True ),
            (d1, t3, t2, t3, True ),

            (d2, t3, t1, t2, True ), # Different
            (d2, t3, t1, t3, True ),
            (d2, t3, t1, t4, True ),

            (d2, t4, t1, t3, True ),

            (d3, t4, t1, t2, False),

            # T-D-T-T

            (t1, d2, t1, t2, True ),
            (t1, d2, t1, t3, True ),
            (t1, d2, t2, t3, False),
            (t1, d2, t3, t4, False),

            (t1, d3, t1, t2, True ),
            (t1, d3, t2, t3, True ),

            (t2, d3, t1, t2, False),
            (t2, d3, t1, t3, True ),
            (t2, d3, t1, t4, True ),

            (t2, d4, t1, t3, True ),

            (t3, d4, t1, t2, False),

            # T-T-D-T

            (t1, t2, d1, t2, True ),
            (t1, t2, d1, t3, True ),
            (t1, t2, d2, t3, True ), # Different
            (t1, t2, d3, t4, False),

            (t1, t3, d1, t2, True ),
            (t1, t3, d2, t3, True ),

            (t2, t3, d1, t2, False),
            (t2, t3, d1, t3, True ),
            (t2, t3, d1, t4, True ),

            (t2, t4, d1, t3, True ),

            (t3, t4, d1, t2, False),

            # T-T-T-D

            (t1, t2, t1, d2, True ),
            (t1, t2, t1, d3, True ),
            (t1, t2, t2, d3, False),
            (t1, t2, t3, d4, False),

            (t1, t3, t1, d2, True ),
            (t1, t3, t2, d3, True ),

            (t2, t3, t1, d2, False),
            (t2, t3, t1, d3, True ),
            (t2, t3, t1, d4, True ),

            (t2, t4, t1, d3, True ),

            (t3, t4, t1, d2, False),

            # D-D-T-T

            (d1, d2, t1, t2, True ),
            (d1, d2, t1, t3, True ),
            (d1, d2, t2, t3, False),
            (d1, d2, t3, t4, False),

            (d1, d3, t1, t2, True ),
            (d1, d3, t2, t3, True ),

            (d2, d3, t1, t2, True ), # Different
            (d2, d3, t1, t3, True ),
            (d2, d3, t1, t4, True ),

            (d2, d4, t1, t3, True ),

            (d3, d4, t1, t2, False),

            # T-D-D-T

            (t1, d2, d1, t2, True ),
            (t1, d2, d1, t3, True ),
            (t1, d2, d2, t3, False),
            (t1, d2, d3, t4, False),

            (t1, d3, d1, t2, True ),
            (t1, d3, d2, t3, True ),

            (t2, d3, d1, t2, False),
            (t2, d3, d1, t3, True ),
            (t2, d3, d1, t4, True ),

            (t2, d4, d1, t3, True ),

            (t3, d4, d1, t2, False),

            # D-T-D-T

            (d1, t2, d1, t2, True ),
            (d1, t2, d1, t3, True ),
            (d1, t2, d2, t3, True ), # Different
            (d1, t2, d3, t4, False),

            (d1, t3, d1, t2, True ),
            (d1, t3, d2, t3, True ),

            (d2, t3, d1, t2, True ), # Different
            (d2, t3, d1, t3, True ),
            (d2, t3, d1, t4, True ),

            (d2, t4, d1, t3, True ),

            (d3, t4, d1, t2, False),

            # T-T-D-D

            (t1, t2, d1, d2, True ),
            (t1, t2, d1, d3, True ),
            (t1, t2, d2, d3, True ), # Different
            (t1, t2, d3, d4, False),

            (t1, t3, d1, d2, True ),
            (t1, t3, d2, d3, True ),

            (t2, t3, d1, d2, False), # Not different?
            (t2, t3, d1, d3, True ),
            (t2, t3, d1, d4, True ),

            (t2, t4, d1, d3, True ),

            (t3, t4, d1, d2, False),

            # D-D-D-D

            (d1, d2, d1, d2, True ),
            (d1, d2, d1, d3, True ),
            (d1, d2, d2, d3, False),
            (d1, d2, d3, d4, False),

            (d1, d3, d1, d2, True ),
            (d1, d3, d2, d3, True ),

            (d2, d3, d1, d2, False),
            (d2, d3, d1, d3, True ),
            (d2, d3, d1, d4, True ),

            (d2, d4, d1, d3, True ),

            (d3, d4, d1, d2, False),
        ):
            #print start1.n, end1.n, start2.n, end2.n, overlaps

            if overlaps:
                test = self.assertTrue
                error = "should overlap with"
            else:
                test = self.assertFalse
                error = "should not overlap with"

            tr1 = timerange(start1, end1)
            tr2 = timerange(start2, end2)

            test(
                tr1.overlapsWith(tr2),
                "%r (%s-%s) %s %r (%s-%s)" % (tr1, start1.n, end1.n, error, tr2, start2.n, end2.n)
            )
