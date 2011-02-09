##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
    "normalizeForIndex",
    "floatoffset",
    "compareDateTime",
    "differenceDateTime",
    "timeRangesOverlap",
    "periodEnd",
    "normalizePeriodList",
    "clipPeriod"
]

import calendar
import datetime
from vobject.icalendar import utc

from twext.python.datetime import dateordatetime

def normalizeForIndex(dt):
    """
    Normalize a L{datetime.date} or L{datetime.datetime} object for use in the Index.
    If it's a L{datetime.date}, convert to L{datetime.datetime} with HH:MM:SS set to 00:00:00 in UTC.
    If it's a L{datetime.datetime}, convert to UTC.
    @param dt: a L{datetime.date} or L{datetime.datetime} object to normalize
    @return: the normalized date or datetime
    """
    if not isinstance(dt, datetime.date):
        raise TypeError("%r is not a datetime.date instance" % (dt,))
    
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

def compareDateTime(dt1, dt2, defaulttz=None):
    dt1 = dateordatetime(dt1, defaultTZ=defaulttz)
    dt2 = dateordatetime(dt2, defaultTZ=defaulttz)
    if dt1 == dt2:
        return 0
    elif dt1 < dt2:
        return -1
    else:
        return 1

def differenceDateTime(start, end, defaulttz = None):
    return dateordatetime(end, defaultTZ=defaulttz) - dateordatetime(start)

#def timeRangesOverlap(start1, end1, start2, end2, defaulttz = None):
#    def dodt(d):
#        if d is None:
#            return None
#        else:
#            return dateordatetime(d, defaulttz)
#
#    dodt1 = timerange(dodt(start1), dodt(end1))
#    dodt2 = timerange(dodt(start2), dodt(end2))
#
#    return dodt1.overlapsWith(dodt2)

def timeRangesOverlap(start1, end1, start2, end2, defaulttz = None):
    # Can't compare datetime.date and datetime.datetime objects, so normalize
    # to date if they are mixed.
    if isinstance(start1, datetime.datetime) and (start2 is not None) and not isinstance(start2, datetime.datetime): start1 = start1.date()
    if isinstance(start2, datetime.datetime) and (start1 is not None) and not isinstance(start1, datetime.datetime): start2 = start2.date()
    if isinstance(end1,   datetime.datetime) and (end2 is not None) and not isinstance(end2,   datetime.datetime): end1   = end1.date()
    if isinstance(end2,   datetime.datetime) and (end1 is not None) and not isinstance(end1,   datetime.datetime): end2   = end2.date()

    # Note that start times are inclusive and end times are not.
    if start1 is not None and start2 is not None:
        if end1 is not None and end2 is not None:
            return compareDateTime(start1, end2, defaulttz) < 0 and compareDateTime(end1, start2, defaulttz) > 0
        elif end1 is None:
            return compareDateTime(start1, start2, defaulttz) >= 0 and compareDateTime(start1, end2, defaulttz) < 0
        elif end2 is None:
            return compareDateTime(start2, end1, defaulttz) < 0
        else:
            return False
    elif start1 is not None:
        return compareDateTime(start1, end2, defaulttz) < 0
    elif start2 is not None:
        return compareDateTime(end1, end2, defaulttz) < 0 and compareDateTime(end1, start2, defaulttz) > 0
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

def parseSQLTimestamp(ts):
    
    # Handle case where fraction seconds may not be present
    if len(ts) < 20:
        ts += ".0"
    return datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")

def datetimeMktime(dt):

    assert isinstance(dt, datetime.date)
    
    if dt.tzinfo is None:
        dt.replace(tzinfo=utc)
    return calendar.timegm(dt.utctimetuple())
    