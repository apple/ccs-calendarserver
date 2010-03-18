##
# Copyright (c) 2009 Apple Inc. All rights reserved.
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

from twistedcaldav import caldavxml
from twistedcaldav.query import queryfilter
from twistedcaldav.query.calendarquery import sqlcalendarquery
import datetime
import twistedcaldav.test.util

class Tests(twistedcaldav.test.util.TestCase):

    def test_query(self):

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[caldavxml.ComponentFilter(
                    *[caldavxml.TimeRange(**{"start":"20060605T160000Z", "end":"20060605T170000Z"})],
                    **{"name":("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                )],
                **{"name":"VCALENDAR"}
            )
        )
        filter = queryfilter.Filter(filter)
    
        # A complete implementation of current DST rules for major US time zones.
        
        def first_sunday_on_or_after(dt):
            days_to_go = 6 - dt.weekday()
            if days_to_go:
                dt += datetime.timedelta(days_to_go)
            return dt
        
        # In the US, DST starts at 2am (standard time) on the first Sunday in April.
        DSTSTART = datetime.datetime(1, 4, 1, 2)
        # and ends at 2am (DST time; 1am standard time) on the last Sunday of Oct.
        # which is the first Sunday on or after Oct 25.
        DSTEND = datetime.datetime(1, 10, 25, 1)
        
        ZERO = datetime.timedelta(0)
        HOUR = datetime.timedelta(hours=1)
    
        class USTimeZone(datetime.tzinfo):
        
            def __init__(self, hours, reprname, stdname, dstname):
                self.stdoffset = datetime.timedelta(hours=hours)
                self.reprname = reprname
                self.stdname = stdname
                self.dstname = dstname
        
            def __repr__(self):
                return self.reprname
        
            def tzname(self, dt):
                if self.dst(dt):
                    return self.dstname
                else:
                    return self.stdname
        
            def utcoffset(self, dt):
                return self.stdoffset + self.dst(dt)
        
            def dst(self, dt):
                if dt is None or dt.tzinfo is None:
                    # An exception may be sensible here, in one or both cases.
                    # It depends on how you want to treat them.  The default
                    # fromutc() implementation (called by the default astimezone()
                    # implementation) passes a datetime with dt.tzinfo is self.
                    return ZERO
                assert dt.tzinfo is self
        
                # Find first Sunday in April & the last in October.
                start = first_sunday_on_or_after(DSTSTART.replace(year=dt.year))
                end = first_sunday_on_or_after(DSTEND.replace(year=dt.year))
        
                # Can't compare naive to aware objects, so strip the timezone from
                # dt first.
                if start <= dt.replace(tzinfo=None) < end:
                    return HOUR
                else:
                    return ZERO
    
        Eastern  = USTimeZone(-5, "Eastern",  "EST", "EDT")
        filter.child.settzinfo(Eastern)
        
        print sqlcalendarquery(filter)
        