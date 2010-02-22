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
    "dateordatetime",
    "timerange",
    "utc",
]

datetime = __import__("datetime").datetime
from vobject.icalendar import dateTimeToString, dateToString, utc


class dateordatetime(object):
    def __init__(self, dateOrDateTime, defaultTZ=None):
        """
        @param dateOrDateTime: a L{date} or L{datetime}.
        """
        self._dateOrDateTime = dateOrDateTime
        if isinstance(dateOrDateTime, datetime):
            self._isDateTime = True
        else:
            self._isDateTime = False
        self.defaultTZ = defaultTZ

    def _comparableDateTimes(self, other):
        dt1, dt2 = self.dateTime, other.dateTime

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

    def __cmp__(self, other):
        dt1, dt2 = self._comparableDateTimes(other)

        if dt1 == dt2:
            return 0
        elif dt1 < dt2:
            return -1
        else:
            return 1

    def __sub__(self, other):
        dt1, dt2 = self._comparableDateTimes(other)
        return dt1 - dt2

    def date(self):
        if self._isDateTime:
            return self._dateOrDateTime.date()
        else:
            return self._dateOrDateTime

    def datetime(self):
        if self._isDateTime:
            return self._dateOrDateTime
        else:
            d = self._dateOrDateTime
            return datetime(d.year, d.month, d.day, tzinfo=self.defaultTZ)

    def iCalendarString(self):
        if self._isDateTime:
            return dateTimeToString(self._dateOrDateTime)
        else:
            return dateToString(self._dateOrDateTime)

    def asTimeZone(self, tzinfo):
        if self._isDateTime:
            d = self._dateOrDateTime
            if d.tzinfo is None:
                return self
            else:
                return self.__class__(d.astimezone(tzinfo))
        else:
            return self

    def asUTC(self):
        return self.asTimeZone(self, utc)


class timerange(object):
    def __init__(self, start=None, end=None, duration=None):
        """
        @param start: a L{dateordatetime}
        @param end: a L{dateordatetime}
        @param duration: a L{timedelta}
        @param tzinfo: a L{tzinfo}
        """
        assert end is None or duration is None

        self._start = start
        if end is not None:
            self._end = end
        if duration is not None:
            self._duration = duration

    def start(self):
        return self._start

    def end(self):
        if getattr(self, "_end", None) is None:
            start = getattr(self, "_start", None)
            duration = getattr(self, "_duration", None)
            if start is None or duration is None:
                self._end = None
            else:
                self._end = self._start + self._duration
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
                self.start() >= other.start() and self.start() < other.end()
            else:
                return False
        elif self.start() is not None:
            return self.start() < other.end()
        elif other.start() is not None:
            return self.end() < other.end() and self.end() > other.start()
        else:
            return False
