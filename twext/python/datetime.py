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
    "DateTime",
    "Date",
    "TimeDelta",
    "DateOrDateTime",
    "TimeRange",
    "UTC",
]

from datetime import date as Date, datetime as DateTime, timedelta as TimeDelta
from vobject.icalendar import dateTimeToString, dateToString, utc as UTC


class DateOrDateTime (object):
    def __init__(self, dateOrDateTime, defaultTZ=None):
        self._dateOrDateTime = dateOrDateTime
        if isinstance(dateOrDateTime, DateTime):
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

    @property
    def date(self):
        if self._isDateTime:
            return self._dateOrDateTime.date()

    @property
    def dateTime(self):
        if not self._isDateTime:
            d = self._dateOrDateTime
            return DateTime(d.year, d.month, d.day, tzinfo=self.tz)

    def iCalendarString(self):
        if self._isDateTime:
            return dateTimeToString(self._dateOrDateTime)
        else:
            return dateToString(self._dateOrDateTime)

    def asUTC(self):
        if self._isDateTime:
            d = self._dateOrDateTime
            if d.tzinfo is None:
                return self
            else:
                return self.__class__(d.astimezone(UTC))
        else:
            return self


class TimeRange (object):
    def __init__(self, start=None, end=None, tz=None):
        self.start = start
        self.end = end

    def overlapsWith(self, other, tz=None):
        if self.start is not None and other.start is not None:
            if self.end is not None and other.end is not None:
                return self.start < other.end and self.end > other.start
            elif self.end is not None:
                return other.start < self.end
            elif other.end is not None:
                self.start >= other.start and self.start < other.end
            else:
                return False
        elif self.start is not None:
            return self.start < other.end
        elif other.start is not None:
            return self.end < other.end and self.end > other.start
        else:
            return False


def normalizeStartEndDuration(start, end=None, duration=None):
    """
    Given a start with a end or dureation (no neither), obtain a
    normalized tuple of start and end.
    """
    assert end is None or duration is None, "Cannot specify both dtend and duration"

    # FIXME: Ask Cyrus: Why UTC?
    if start is not None:
        start = start.asUTC()
    if end is not None:
        end = end.asUTC()
    elif duration:
        end = start + duration
    
    return (start, end)
