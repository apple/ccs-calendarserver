##
# Copyright (c) 2006-2015 Apple Inc. All rights reserved.
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

from twistedcaldav.dateops import floatoffset, pyCalendarTodatetime

from txdav.caldav.datastore.query.filter import ComponentFilter, PropertyFilter, TextMatch, TimeRange
from txdav.common.datastore.query import expression


"""
SQL statement generator from query expressions.
"""

__all__ = [
    "buildExpression",
]



# SQL Index column (field) names

def buildExpression(filter, fields):
    """
    Convert the supplied calendar-query into an expression tree.

    @param filter: the L{Filter} for the calendar-query to convert.
    @return: a L{baseExpression} for the expression tree.
    """

    # Lets assume we have a valid filter from the outset.

    # Top-level filter contains exactly one comp-filter element
    assert filter.child is not None
    vcalfilter = filter.child
    assert isinstance(vcalfilter, ComponentFilter)
    assert vcalfilter.filter_name == "VCALENDAR"

    if len(vcalfilter.filters) > 0:
        # Determine logical expression grouping
        logical = expression.andExpression if vcalfilter.filter_test == "allof" else expression.orExpression

        # Only comp-filters are handled
        for _ignore in [x for x in vcalfilter.filters if not isinstance(x, ComponentFilter)]:
            raise ValueError

        return compfilterListExpression(vcalfilter.filters, fields, logical)
    else:
        return expression.allExpression()



def compfilterListExpression(compfilters, fields, logical):
    """
    Create an expression for a list of comp-filter elements.

    @param compfilters: the C{list} of L{ComponentFilter} elements.
    @return: a L{baseExpression} for the expression tree.
    """

    if len(compfilters) == 1:
        return compfilterExpression(compfilters[0], fields)
    else:
        return logical([compfilterExpression(c, fields) for c in compfilters])



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

    # Determine logical expression grouping
    logical = expression.andExpression if compfilter.filter_test == "allof" else expression.orExpression

    expressions = []
    if isinstance(compfilter.filter_name, str) or isinstance(compfilter.filter_name, unicode):
        expressions.append(expression.isExpression(fields["TYPE"], compfilter.filter_name, True))
    else:
        expressions.append(expression.inExpression(fields["TYPE"], compfilter.filter_name, True))

    # Handle time-range
    if compfilter.qualifier and isinstance(compfilter.qualifier, TimeRange):
        start, end, startfloat, endfloat = getTimerangeArguments(compfilter.qualifier)
        expressions.append(expression.timerangeExpression(start, end, startfloat, endfloat))

    # Handle properties - we can only do UID right now
    props = []
    for p in [x for x in compfilter.filters if isinstance(x, PropertyFilter)]:
        props.append(propfilterExpression(p, fields))
    if len(props) > 1:
        propsExpression = logical(props)
    elif len(props) == 1:
        propsExpression = props[0]
    else:
        propsExpression = None

    # Handle embedded components - we do not right now as our Index does not handle them
    comps = []
    for _ignore in [x for x in compfilter.filters if isinstance(x, ComponentFilter)]:
        raise ValueError
    if len(comps) > 1:
        compsExpression = logical(comps)
    elif len(comps) == 1:
        compsExpression = comps[0]
    else:
        compsExpression = None

    # Now build compound expression
    if ((propsExpression is not None) and (compsExpression is not None)):
        expressions.append(logical([propsExpression, compsExpression]))
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

    # Determine logical expression grouping
    logical = expression.andExpression if propfilter.filter_test == "allof" else expression.orExpression

    # Handle time-range - we cannot do this with our Index right now
    if propfilter.qualifier and isinstance(propfilter.qualifier, TimeRange):
        raise ValueError

    # Handle text-match
    tm = None
    if propfilter.qualifier and isinstance(propfilter.qualifier, TextMatch):
        if propfilter.qualifier.match_type == "equals":
            tm = expression.isnotExpression if propfilter.qualifier.negate else expression.isExpression
        elif propfilter.qualifier.match_type == "contains":
            tm = expression.notcontainsExpression if propfilter.qualifier.negate else expression.containsExpression
        elif propfilter.qualifier.match_type == "starts-with":
            tm = expression.notstartswithExpression if propfilter.qualifier.negate else expression.startswithExpression
        elif propfilter.qualifier.match_type == "ends-with":
            tm = expression.notendswithExpression if propfilter.qualifier.negate else expression.endswithExpression
        tm = tm(fields[propfilter.filter_name], propfilter.qualifier.text, propfilter.qualifier.caseless)

    # Handle embedded parameters - we do not right now as our Index does not handle them
    params = []
    for _ignore in propfilter.filters:
        raise ValueError
    if len(params) > 1:
        paramsExpression = logical(params)
    elif len(params) == 1:
        paramsExpression = params[0]
    else:
        paramsExpression = None

    # Now build return expression
    if (tm is not None) and (paramsExpression is not None):
        return logical([tm, paramsExpression])
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
