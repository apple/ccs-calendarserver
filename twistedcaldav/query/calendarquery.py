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
Convert a calendar-query into an expression tree.
Convert a calendar-query into a partial SQL statement.
"""

__version__ = "0.0"

__all__ = [
    "calendarquery",
    "sqlcalendarquery",
]

from twistedcaldav.dateops import floatoffset, pyCalendarTodatetime
from twistedcaldav.query import expression, sqlgenerator, calendarqueryfilter

# SQL Index column (field) names

def calendarquery(filter, fields):
    """
    Convert the supplied calendar-query into an expression tree.

    @param filter: the L{Filter} for the calendar-query to convert.
    @return: a L{baseExpression} for the expression tree.
    """
    
    # Lets assume we have a valid filter from the outset.
    
    # Top-level filter contains exactly one comp-filter element
    assert filter.child is not None
    vcalfilter = filter.child
    assert isinstance(vcalfilter, calendarqueryfilter.ComponentFilter)
    assert vcalfilter.filter_name == "VCALENDAR"
    
    if len(vcalfilter.filters) > 0:
        # Only comp-filters are handled
        for _ignore in [x for x in vcalfilter.filters if not isinstance(x, calendarqueryfilter.ComponentFilter)]:
            raise ValueError
        
        return compfilterListExpression(vcalfilter.filters, fields)
    else:
        return expression.allExpression()

def compfilterListExpression(compfilters, fields):
    """
    Create an expression for a list of comp-filter elements.
    
    @param compfilters: the C{list} of L{ComponentFilter} elements.
    @return: a L{baseExpression} for the expression tree.
    """
    
    if len(compfilters) == 1:
        return compfilterExpression(compfilters[0], fields)
    else:
        return expression.andExpression([compfilterExpression(c, fields) for c in compfilters])

def compfilterExpression(compfilter, fields):
    """
    Create an expression for a single comp-filter element.
    
    @param compfilter: the L{ComponentFilter} element.
    @return: a L{baseExpression} for the expression tree.
    """
    
    # Handle is-not-defined case
    if not compfilter.defined:
        # Test for TYPE != <<component-type name>>
        return expression.isnotExpression(fields["TYPE"], compfilter.filter_name, True)
        
    expressions = []
    if isinstance(compfilter.filter_name, str):
        expressions.append(expression.isExpression(fields["TYPE"], compfilter.filter_name, True))
    else:
        expressions.append(expression.inExpression(fields["TYPE"], compfilter.filter_name, True))
    
    # Handle time-range    
    if compfilter.qualifier and isinstance(compfilter.qualifier, calendarqueryfilter.TimeRange):
        start, end, startfloat, endfloat = getTimerangeArguments(compfilter.qualifier)
        expressions.append(expression.timerangeExpression(start, end, startfloat, endfloat))
        
    # Handle properties - we can only do UID right now
    props = []
    for p in [x for x in compfilter.filters if isinstance(x, calendarqueryfilter.PropertyFilter)]:
        props.append(propfilterExpression(p, fields))
    if len(props) > 1:
        propsExpression = expression.andExpression[props]
    elif len(props) == 1:
        propsExpression = props[0]
    else:
        propsExpression = None
        
    # Handle embedded components - we do not right now as our Index does not handle them
    comps = []
    for _ignore in [x for x in compfilter.filters if isinstance(x, calendarqueryfilter.ComponentFilter)]:
        raise ValueError
    if len(comps) > 1:
        compsExpression = expression.andExpression[comps]
    elif len(comps) == 1:
        compsExpression = comps[0]
    else:
        compsExpression = None

    # Now build compound expression
    if ((propsExpression is not None) and (compsExpression is not None)):
        expressions.append(expression.andExpression([propsExpression, compsExpression]))
    elif propsExpression is not None:
        expressions.append(propsExpression)
    elif compsExpression is not None:
        expressions.append(compsExpression)

    # Now build return expression
    return expression.andExpression(expressions)

def propfilterExpression(propfilter, fields):
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
        return expression.isExpression(fields["UID"], "", True)
    
    # Handle time-range - we cannot do this with our Index right now
    if propfilter.qualifier and isinstance(propfilter.qualifier, calendarqueryfilter.TimeRange):
        raise ValueError
    
    # Handle text-match
    tm = None
    if propfilter.qualifier and isinstance(propfilter.qualifier, calendarqueryfilter.TextMatch):
        if propfilter.qualifier.negate:
            tm = expression.notcontainsExpression(fields[propfilter.filter_name], propfilter.qualifier.text, propfilter.qualifier.caseless)
        else:
            tm = expression.containsExpression(fields[propfilter.filter_name], propfilter.qualifier.text, propfilter.qualifier.caseless)
    
    # Handle embedded parameters - we do not right now as our Index does not handle them
    params = []
    for _ignore in propfilter.filters:
        raise ValueError
    if len(params) > 1:
        paramsExpression = expression.andExpression[params]
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
    startfloat = floatoffset(start, tzinfo) if start else None
    endfloat = floatoffset(end, tzinfo) if end else None

    return (
        pyCalendarTodatetime(start) if start else None,
        pyCalendarTodatetime(end) if end else None,
        pyCalendarTodatetime(startfloat) if startfloat else None,
        pyCalendarTodatetime(endfloat) if endfloat else None,
    )

def sqlcalendarquery(filter, calendarid=None, userid=None, generator=sqlgenerator.sqlgenerator):
    """
    Convert the supplied calendar-query into a oartial SQL statement.

    @param filter: the L{Filter} for thw calendar-query to convert.
    @return: a C{tuple} of (C{str}, C{list}), where the C{str} is the partial SQL statement,
            and the C{list} is the list of argument substitutions to use with the SQL API execute method.
            Or return C{None} if it is not possible to create an SQL query to fully match the calendar-query.
    """
    try:
        expression = calendarquery(filter, generator.FIELDS)
        sql = generator(expression, calendarid, userid)
        return sql.generate()
    except ValueError:
        return None
