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

"""
Date/time Utilities
"""

__all__ = [
    "utc",
    "tzWithID",
    "dateordatetime",
    "timerange",
    "asTimeZone",
    "asUTC",
    "iCalendarString",
]

date     = __import__("datetime").date
datetime = __import__("datetime").datetime

from vobject.icalendar import dateTimeToString, dateToString
from vobject.icalendar import utc, getTzid as tzWithID


# FIXME, add constants for begining/end of time

class dateordatetime(object):
    def __init__(self, dateOrDatetime, defaultTZ=None):
        """
        @param dateOrDatetime: a L{date} or L{datetime}.
        """
        assert dateOrDatetime is not None, "dateOrDatetime is None"

        self._dateOrDatetime = dateOrDatetime
        if isinstance(dateOrDatetime, datetime):
            self._isDatetime = True
        else:
            assert isinstance(dateOrDatetime, date)
            self._isDatetime = False
        self.defaultTZ = defaultTZ

    def __repr__(self):
        return "dateordatetime(%r)" % (self._dateOrDatetime,)

    def _comparableDatetimes(self, other):
        if not isinstance(other, dateordatetime):
            other = dateordatetime(other)

        dt1, dt2 = self.datetime(), other.datetime()

        def getTZInfo(tz):
            for defaultTZ in (self.defaultTZ, other.defaultTZ):
                if defaultTZ is not None:
                    return defaultTZ
                return tz

        if dt1.tzinfo is None and dt2.tzinfo is not None:
            dt1 = dt1.replace(tzinfo=getTZInfo(dt2.tzinfo))
        elif dt1.tzinfo is not None and dt2.tzinfo is None:
            dt2 = dt2.replace(tzinfo=getTZInfo(dt1.tzinfo))

        return dt1, dt2

    def __eq__(self, other):
        if isinstance(other, dateordatetime):
            other = other.dateOrDatetime()
        dt1, dt2 = self._comparableDatetimes(other)
        return dt1 == dt2

    def __ne__(self, other):
        if isinstance(other, dateordatetime):
            other = other.dateOrDatetime()
        dt1, dt2 = self._comparableDatetimes(other)
        return dt1 != dt2

    def __lt__(self, other):
        if not isinstance(other, comparableTypes):
            return NotImplemented
        dt1, dt2 = self._comparableDatetimes(other)
        return dt1 < dt2

    def __le__(self, other):
        if not isinstance(other, comparableTypes):
            return NotImplemented
        dt1, dt2 = self._comparableDatetimes(other)
        return dt1 <= dt2

    def __gt__(self, other):
        if not isinstance(other, comparableTypes):
            return NotImplemented
        dt1, dt2 = self._comparableDatetimes(other)
        return dt1 > dt2

    def __ge__(self, other):
        if not isinstance(other, comparableTypes):
            return NotImplemented
        dt1, dt2 = self._comparableDatetimes(other)
        return dt1 >= dt2

    def __hash__(self):
        return self._dateOrDatetime.__hash__()

    def __sub__(self, other):
        if not isinstance(other, (date, datetime, dateordatetime)):
            return NotImplemented

        dt1, dt2 = self._comparableDatetimes(other)
        return dt1 - dt2

    def timetuple(self):
        #
        # This attribute is required in order to allow comparisions
        # against dates and datetimes in Python 2.x.
        #
        # See:
        #   http://bugs.python.org/issue8005#msg104333
        #   http://docs.python.org/library/datetime.html#datetime.date.timetuple
        #
        return self.datetime().timetuple()

    def date(self):
        if self._isDatetime:
            return self._dateOrDatetime.date()
        else:
            return self._dateOrDatetime

    def datetime(self):
        if self._isDatetime:
            return self._dateOrDatetime
        else:
            d = self._dateOrDatetime
            return datetime(d.year, d.month, d.day, tzinfo=self.defaultTZ)

    def dateOrDatetime(self):
        return self._dateOrDatetime

    def iCalendarString(self):
        if self._isDatetime:
            return dateTimeToString(self._dateOrDatetime)
        else:
            return dateToString(self._dateOrDatetime)

    def asTimeZone(self, tzinfo):
        if self._isDatetime:
            d = self._dateOrDatetime
            if d.tzinfo is None:
                return self
            else:
                return self.__class__(d.astimezone(tzinfo))
        else:
            return self

    def asUTC(self):
        return self.asTimeZone(utc)

comparableTypes = (date, datetime, dateordatetime)


class timerange(object):
    def __init__(self, start=None, end=None, duration=None):
        """
        @param start: a L{dateordatetime}, L{date} or L{datetime}
        @param end: a L{dateordatetime}, L{date} or L{datetime}
        @param duration: a L{timedelta}, L{date} or L{datetime}
        @param tzinfo: a L{tzinfo}
        """
        assert end is None or duration is None, "end or duration must be None"

        if start is None or isinstance(start, dateordatetime):
            self._start = start
        else:
            self._start = dateordatetime(start)

        if end is not None:
            if isinstance(end, dateordatetime):
                self._end = end
            else:
                self._end = dateordatetime(end)

        if duration is not None:
            self._duration = duration

    def __repr__(self):
        return "timerange(%r, %s)" % (self.start(), self.end())

    def __eq__(self, other):
        if not isinstance(other, timerange):
            return NotImplemented
        if self.start() != other.start():
            return False
        return self.end() == other.end()

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        if not isinstance(other, timerange):
            return NotImplemented
        if self.start() == other.start():
            return self.end() < other.end()
        else:
            return self.start() < other.start()

    def __le__(self, other):
        if not isinstance(other, timerange):
            return NotImplemented
        if self.start() == other.start():
            return self.end() <= other.end()
        else:
            return self.start() <= other.start()

    def __gt__(self, other):
        if not isinstance(other, timerange):
            return NotImplemented
        if self.start() == other.start():
            return self.end() > other.end()
        else:
            return self.start() > other.start()

    def __ge__(self, other):
        if not isinstance(other, timerange):
            return NotImplemented
        if self.start() == other.start():
            return self.end() >= other.end()
        else:
            return self.start() >= other.start()

    def __hash__(self, other):
        return hash((self.start(), self.end()))

    def start(self):
        return self._start

    def end(self):
        if getattr(self, "_end", None) is None:
            start = getattr(self, "_start", None)
            duration = getattr(self, "_duration", None)
            if start is None or duration is None:
                self._end = None
            else:
                self._end = dateordatetime(self._start.dateOrDatetime() + self._duration)
        return self._end

    def duration(self):
        if getattr(self, "_duration", None) is None:
            start = getattr(self, "_start", None)
            end = getattr(self, "_end", None)
            if start is None or end is None:
                self._duration = None
            else:
                self._duration = self._end - self._start
        return self._duration

    def overlapsWith(self, other):
        """
        Determine whether this time range overlaps with another.
        """
        if self.start() is not None and other.start() is not None:
            if self.end() is not None and other.end() is not None:
                return self.start() < other.end() and self.end() > other.start()
            elif self.end() is not None:
                return other.start() < self.end()
            elif other.end() is not None:
                return self.start() >= other.start() and self.start() < other.end()
            else:
                return False
        elif self.start() is not None:
            return self.start() < other.end()
        elif other.start() is not None:
            return self.end() < other.end() and self.end() > other.start()
        else:
            return False


##
# Convenience functions
##

def asTimeZone(dateOrDatetime, tzinfo):
    """
    Convert a L{date} or L{datetime} to the given time zone.
    """
    return dateordatetime(dateOrDatetime).asTimeZone(tzinfo).dateOrDatetime()

def asUTC(dateOrDatetime):
    """
    Convert a L{date} or L{datetime} to UTC.
    """
    return dateordatetime(dateOrDatetime).asUTC().dateOrDatetime()

def iCalendarString(dateOrDatetime):
    """
    Convert a L{date} or L{datetime} to a string appropriate for use
    in an iCalendar property.
    """
    return dateordatetime(dateOrDatetime).iCalendarString()
