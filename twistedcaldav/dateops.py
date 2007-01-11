##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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

"""
Date/time Utilities
"""

__all__ = [
    "normalizeToUTC",
    "normalizeForIndex",
    "compareDateTime",
    "differenceDateTime",
    "makeComparableDateTime",
    "timeRangesOverlap",
    "periodEnd",
    "normalizePeriodList",
    "clipPeriod"
]

import datetime
from vobject.icalendar import utc

def normalizeToUTC(dt):
    """
    Normalize a L{datetime.date} or L{datetime.datetime} object to UTC.
    If its a L{datetime.date}, just return it as-is.
    @param dt: a L{datetime.date} or L{datetime.datetime} object to normalize
    @return: the normalized date or datetime
    """
    if not isinstance(dt, datetime.date):
        raise TypeError("$r is not a datetime.date instance" % (dt,))
    
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is not None:
            return dt.astimezone(utc)
        else:
            return dt
    else:
        return dt

def normalizeForIndex(dt):
    """
    Normalize a L{datetime.date} or L{datetime.datetime} object for use in the Index.
    If it's a L{datetime.date}, convert to L{datetime.datetime} with HH:MM:SS set to 00:00:00 in UTC.
    If it's a L{datetime.datetime}, convert to UTC.
    @param dt: a L{datetime.date} or L{datetime.datetime} object to normalize
    @return: the normalized date or datetime
    """
    if not isinstance(dt, datetime.date):
        raise TypeError("$r is not a datetime.date instance" % (dt,))
    
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is not None:
            return dt.astimezone(utc)
        else:
            return dt
    else:
        return datetime.datetime.fromordinal(dt.toordinal())

def floatoffset(dt, tzinfo):
    """
    Apply the timezone offset to the supplied time, then force tz to utc. This gives the local
    date-time as if the local tz were UTC. It can be used in floating time comparisons with UTC date-times.
    
    @param dt: a L{datetime.datetime} object to normalize
    @param tzinfo: a L{datetime.tzinfo} object to apply offset from
    @return: the normalized datetime
    """
    
    if tzinfo is None:
        tzinfo = utc
    return dt.astimezone(tzinfo).replace(tzinfo=utc)

def compareDateTime(dt1, dt2, defaulttz = None):
    """
    Compare two L{datetime.date} or L{datetime.datetime} objects in
    a transparent manner that does not depend on the nature of the objects
    and whether timesones are set.
    @param dt1: a L{datetime.datetime} or L{datetime.date} specifying a date to test.
    @param dt2: a L{datetime.datetime} or L{datetime.date} specifying a date to test.
    @param defaulttz: a L{datetime.tzinfo} for the VTIMEZONE object to use if one of the
        datetime's is a date or floating.
    @return:  0 if dt1 == dt2,
        -1 if dt1 < dt2
        1 if dt1 > dt2
    """

    dt1, dt2 = makeComparableDateTime(dt1, dt2, defaulttz)

    if dt1 == dt2:
        return 0
    elif dt1 < dt2:
        return -1
    else:
        return 1

def differenceDateTime(start, end, defaulttz = None):
    """
    Determines the difference between start and end datetime's returning the duration.
    NB This handles the case where start and end are not of the same datetime type.
    
    @param start: a L{datetime.datetime} or L{datetime.date} specify the start time.
    @param end: a L{datetime.datetime} or L{datetime.date} specify the end time.
    @param defaulttz: a L{datetime.tzinfo} for the VTIMEZONE object to use if one of the
        datetime's is a date or floating.
    @return: the L{datetime.timedelta} for the difference between the two.
    """

    start, end = makeComparableDateTime(start, end, defaulttz)
    return end - start

def makeComparableDateTime(dt1, dt2, defaulttz = None):  
    """
    Ensure that the two datetime objects passed in are of a comparable type for arithemtic
    and comparison operations..
    
    @param start: a L{datetime.datetime} or L{datetime.date} specifying one time.
    @param end: a L{datetime.datetime} or L{datetime.date} specifying another time.
    @param defaulttz: a L{datetime.tzinfo} for the VTIMEZONE object to use if one of the
        datetime's is a date or floating.
    @return: a C{tuple} of two L{datetime.xx}'s for the comparable items.
    """

    for dt in (dt1, dt2):
        if not isinstance(dt, datetime.date):
            raise TypeError("$r is not a datetime.date instance" % (dt,))

    # Pick appropriate tzinfo
    tzi = [None]
    def getTzinfo(dtzi):
        if tzi[0] is None:
            if defaulttz is not None:
                tzi[0] = defaulttz
            else:
                return dtzi
        return tzi[0]

    # If any one argument is a datetime.date, convert that into a datetime.datetime
    # with the time set to midnight and the same timezone as the other argument
    if isinstance(dt1, datetime.datetime) and not isinstance(dt2, datetime.datetime):
        dt2 = datetime.datetime(dt2.year, dt2.month, dt2.day, 0, 0, 0, 0, getTzinfo(dt1.tzinfo))
    elif not isinstance(dt1, datetime.datetime) and isinstance(dt2, datetime.datetime):
        dt1 = datetime.datetime(dt1.year, dt1.month, dt1.day, 0, 0, 0, 0, getTzinfo(dt2.tzinfo))
    elif isinstance(dt1, datetime.datetime) and isinstance(dt2, datetime.datetime):
        # Ensure that they both have or have not a tzinfo
        if (dt1.tzinfo is not None and dt2.tzinfo is None):
            dt2 = dt2.replace(tzinfo=getTzinfo(dt1.tzinfo))
        elif (dt1.tzinfo is None and dt2.tzinfo is not None):
            dt1 = dt1.replace(tzinfo=getTzinfo(dt2.tzinfo))
    
    return (dt1, dt2)

def timeRangesOverlap(start1, end1, start2, end2, defaulttz = None):
    """
    Determines whether two time ranges overlap.
    @param start1: a L{datetime.datetime} or L{datetime.date} specifying the
        beginning of the first time span.
    @param end1: a L{datetime.datetime} or L{datetime.date} specifying the
        end of the first time span.  C{end} may be None, indicating that
        there is no end date.
    @param start2: a L{datetime.datetime} or L{datetime.date} specifying the
        beginning of the second time span.
    @param end2: a L{datetime.datetime} or L{datetime.date} specifying the
        end of the second time span.  C{end} may be None, indicating that
        there is no end date.
    @param defaulttz: a L{datetime.tzinfo} for the VTIMEZONE object to use if one of the
        datetime's is a date or floating.
    @return: True if the two given time spans overlap, False otherwise.
    """
    # Can't compare datetime.date and datetime.datetime objects, so normalize
    # to date if they are mixed.
    if isinstance(start1, datetime.datetime) and not isinstance(start2, datetime.datetime): start1 = start1.date()
    if isinstance(start2, datetime.datetime) and not isinstance(start1, datetime.datetime): start2 = start2.date()
    if isinstance(end1,   datetime.datetime) and (end2 is not None) and not isinstance(end2,   datetime.datetime): end1   = end1.date()
    if isinstance(end2,   datetime.datetime) and (end1 is not None) and not isinstance(end1,   datetime.datetime): end2   = end2.date()

    # Note that start times are inclusive and end times are not.
    if end1 is not None and end2 is not None:
        return compareDateTime(start1, end2, defaulttz) < 0 and compareDateTime(end1, start2, defaulttz) > 0
    elif end1 is None:
        return compareDateTime(start1, start2, defaulttz) >= 0 and compareDateTime(start1, end2, defaulttz) < 0
    elif end2 is None:
        return compareDateTime(start2, start1, defaulttz) >= 0 and compareDateTime(start2, end1, defaulttz) < 0
    else:
        return False

def periodEnd(p):
    """
    Calculate the end datetime of the period. Since a period is a
    tuple consisting of a pair of L{datetime.datetime}'s, or one
    L{datetime.datetime} and one L{datetime.timedelta}, we may need
    to add the duration to the start to get the actual end.
    @param p: the period whose end is to be determined.
    @return: the L{datetime.datetime} for the end.
    """
    assert len(p) == 2, "Period is not a tuple of two items: %r" % (p,)
    assert isinstance(p[0], datetime.datetime), "Period start is not a datetime: %r" % (p,)
    assert isinstance(p[1], datetime.datetime) or isinstance(p[1], datetime.timedelta), "Period end is not a datetime or timedelta: %r" % (p,)
    
    if isinstance(p[1], datetime.timedelta):
        return p[0] + p[1]
    else:
        return p[1]
    
def normalizePeriodList(list):
    """
    Normalize the list of periods by merging overlapping or consecutive ranges
    and sorting the list by each periods start.
    @param list: a list of tuples of L{datetime.datetime} pairs. The list is changed in place.
    """
    
    # First sort the list
    def sortPeriods(p1, p2):
        """
        Compare two periods. Sort by their start and then end times.
        A period is a tuple consisting of a pair of L{datetime.datetime}'s, or one
        L{datetime.datetime} and one L{datetime.timedelta}.
        @param p1: first period
        @param p2: second period
        @return: 1 if p1>p2, 0 if p1==p2, -1 if p1<p2
        """

        assert len(p1) == 2, "Period is not a tuple of two items: %r" % (p1,)
        assert isinstance(p1[0], datetime.datetime), "Period start is not a datetime: %r" % (p1,)
        assert isinstance(p1[1], datetime.datetime) or isinstance(p1[1], datetime.timedelta), "Period end is not a datetime or timedelta: %r" % (p1,)
        
        assert len(p2) == 2, "Period is not a tuple of two items: %r" % (p2,)
        assert isinstance(p2[0], datetime.datetime), "Period start is not a datetime: %r" % (p2,)
        assert isinstance(p2[1], datetime.datetime) or isinstance(p2[1], datetime.timedelta), "Period end is not a datetime or timedelta: %r" % (p2,)
        
        
        if p1[0] == p2[0]:
            cmp1 = periodEnd(p1)
            cmp2 = periodEnd(p2)
        else:
            cmp1 = p1[0]
            cmp2 = p2[0]
        
        return compareDateTime(cmp1, cmp2)

    list.sort(cmp=sortPeriods)
    
    # Now merge overlaps and consecutive periods
    index = None
    p = None
    pe = None
    for i in xrange(len(list)):
        if p is None:
            index = i
            p = list[i]
            pe = periodEnd(p)
            continue
        ie = periodEnd(list[i])
        if (pe >= list[i][0]):
            if ie > pe:
                list[index] = (list[index][0], ie)
                pe = ie
            list[i] = None
        else:
            index = i
            p = list[i]
            pe = periodEnd(p)
    list[:] = [x for x in list if x]

def clipPeriod(period, clipPeriod):
    """
    Clip the start/end period so that it lies entirely within the clip period.
    @param period: the (start, end) tuple for the period to be clipped.
    @param clipPeriod: the (start, end) tuple for the period to clip to.
    @return: the (start, end) tuple for the clipped period, or
             None if the period is outside the clip period
    """
    start = period[0]
    end = periodEnd(period)
    clipStart = clipPeriod[0]
    clipEnd = periodEnd(clipPeriod)

    if start < clipStart:
        start = clipStart
    
    if end > clipEnd:
        end = clipEnd
    
    if start > end:
        return None
    else:
        # Try to preserve use of duration in period
        if isinstance(period[1], datetime.timedelta):
            return (start, end - start)
        else:
            return (start, end)
 
