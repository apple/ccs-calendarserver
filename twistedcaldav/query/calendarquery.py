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
##

"""
Convert a calendar-query into an expression tree.
Convert a calendar-query into a partial SQL statement.
"""

__version__ = "0.0"

__all__ = [
    "calendarquery",
    "sqlcalendarquery",
]

from twistedcaldav.dateops import floatoffset
from twistedcaldav.query import sqlgenerator
from twistedcaldav.query import expression
from twistedcaldav import caldavxml

# SQL Index column (field) names

FIELD_TYPE = "RESOURCE.TYPE"
FIELD_UID  = "RESOURCE.UID"
#FIELD_RECURRENCE_ID = "RESOURCE.RECURRENCE-ID"
#FIELD_SUMMARY = "RESOURCE.SUMMARY"
#FIELD_DESCRIPTION = "RESOURCE.DESCRIPTION"
#FIELD_LOCATION = "RESOURCE.LOCATION"

def calendarquery(filter):
    """
    Convert the supplied calendar-query into an expression tree.

    @param filter: the L{Filter} for thw calendar-query to convert.
    @return: a L{baseExpression} for the expression tree.
    """
    
    # Lets assume we have a valid filter from the outset.
    
    # Top-level filter contains exactly one comp-filter element
    assert len(filter.children) == 1
    vcalfilter = filter.children[0]
    assert isinstance(vcalfilter, caldavxml.ComponentFilter)
    assert vcalfilter.filter_name == "VCALENDAR"
    
    if len(vcalfilter.children) > 0:
        return compfilterListExpression(vcalfilter.children)
    else:
        return expression.allExpression()

def compfilterListExpression(compfilters):
    """
    Create an expression for a list of comp-filter elements.
    
    @param compfilters: the C{list} of L{ComponentFilter} elements.
    @return: a L{baseExpression} for the expression tree.
    """
    
    if len(compfilters) == 1:
        return compfilterExpression(compfilters[0])
    else:
        return expression.orExpression([compfilterExpression(c) for c in compfilters])

def compfilterExpression(compfilter):
    """
    Create an expression for a single comp-filter element.
    
    @param compfilter: the L{ComponentFilter} element.
    @return: a L{baseExpression} for the expression tree.
    """
    
    # Handle is-not-defined case
    if not compfilter.defined:
        # Test for TYPE != <<component-type name>>
        return expression.isnotExpression(FIELD_TYPE, compfilter.filter_name, True)
        
    expressions = []
    if isinstance(compfilter.filter_name, str):
        expressions.append(expression.isExpression(FIELD_TYPE, compfilter.filter_name, True))
    else:
        expressions.append(expression.inExpression(FIELD_TYPE, compfilter.filter_name, True))
    
    # Handle time-range    
    if compfilter.qualifier and isinstance(compfilter.qualifier, caldavxml.TimeRange):
        start, end, startfloat, endfloat = getTimerangeArguments(compfilter.qualifier)
        expressions.append(expression.timerangeExpression(start, end, startfloat, endfloat))
        
    # Handle properties - we can only do UID right now
    props = []
    for p in [x for x in compfilter.filters if isinstance(x, caldavxml.PropertyFilter)]:
        props.append(propfilterExpression(p))
    if len(props) > 1:
        propsExpression = expression.orExpression[props]
    elif len(props) == 1:
        propsExpression = props[0]
    else:
        propsExpression = None
        
    # Handle embedded components - we do not right now as our Index does not handle them
    comps = []
    for c in [x for x in compfilter.filters if isinstance(x, caldavxml.ComponentFilter)]:
        raise ValueError
    if len(comps) > 1:
        compsExpression = expression.orExpression[comps]
    elif len(comps) == 1:
        compsExpression = comps[0]
    else:
        compsExpression = None

    # Now build compound expression
    if ((propsExpression is not None) and (compsExpression is not None)):
        expressions.append(expression.orExpression([propsExpression, compsExpression]))
    elif propsExpression is not None:
        expressions.append(propsExpression)
    elif compsExpression is not None:
        expressions.append(compsExpression)

    # Now build return expression
    return expression.andExpression(expressions)

def propfilterExpression(propfilter):
    """
    Create an expression for a single prop-filter element.
    
    @param propfilter: the L{PropertyFilter} element.
    @return: a L{baseExpression} for the expression tree.
    """
    
    # Only handle UID right now
    if propfilter.filter_name != "UID":
        raise ValueError

    # Handle is-not-defined case
    if not propfilter.defined:
        # Test for <<field>> != "*"
        return expression.isExpression(FIELD_UID, "", True)
    
    # Handle time-range - we cannot do this with our Index right now
    if propfilter.qualifier and isinstance(propfilter.qualifier, caldavxml.TimeRange):
        raise ValueError
    
    # Handle text-match
    tm = None
    if propfilter.qualifier and isinstance(propfilter.qualifier, caldavxml.TextMatch):
        if propfilter.qualifier.negate:
            tm = expression.notcontainsExpression(propfilter.filter_name, str(propfilter.qualifier), propfilter.qualifier)
        else:
            tm = expression.containsExpression(propfilter.filter_name, str(propfilter.qualifier), propfilter.qualifier)
    
    # Handle embedded parameters - we do not right now as our Index does not handle them
    params = []
    for p in propfilter.filters:
        raise ValueError
    if len(params) > 1:
        paramsExpression = expression.orExpression[params]
    elif len(params) == 1:
        paramsExpression = params[0]
    else:
        paramsExpression = None

    # Now build return expression
    if (tm is not None) and (paramsExpression is not None):
        return expression.andExpression([tm, paramsExpression])
    elif tm is not None:
        return tm
    elif paramsExpression is not None:
        return paramsExpression
    else:
        return None

def getTimerangeArguments(timerange):
    """
    Get start/end and floating start/end (adjusted for timezone offset) values from the
    supplied time-range test.
    
    @param timerange: the L{TimeRange} used in the query.
    @return: C{tuple} of C{str} for start, end, startfloat, endfloat
    """
    
    # Start/end in UTC
    start = timerange.start
    end = timerange.end
    
    # Get timezone
    tzinfo = timerange.tzinfo

    # Now force to floating UTC
    startfloat = floatoffset(start, tzinfo)
    endfloat = floatoffset(end, tzinfo)

    return str(start), str(end), str(startfloat), str(endfloat)

def sqlcalendarquery(filter):
    """
    Convert the supplied calendar-query into a oartial SQL statement.

    @param filter: the L{Filter} for thw calendar-query to convert.
    @return: a C{tuple} of (C{str}, C{list}), where the C{str} is the partial SQL statement,
            and the C{list} is the list of argument substitutions to use with the SQL API execute method.
            Or return C{None} if it is not possible to create an SQL query to fully match the calendar-query.
    """
    try:
        expression = calendarquery(filter)
        sql = sqlgenerator.sqlgenerator(expression)
        return sql.generate()
    except ValueError:
        return None


if __name__ == "__main__":
    import datetime

    filter = caldavxml.Filter(
                 caldavxml.ComponentFilter(
                     *[caldavxml.ComponentFilter(
                           *[caldavxml.TimeRange(**{"start":"20060605T160000Z", "end":"20060605T170000Z"})],
                           **{"name":("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                       )],
                     **{"name":"VCALENDAR"}
                 )
             )

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
    filter.children[0].settzinfo(Eastern)
    
    print sqlcalendarquery(filter)
