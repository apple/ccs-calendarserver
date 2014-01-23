##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Select

from txdav.common.datastore.query import expression
from txdav.common.datastore.query.generator import SQLQueryGenerator
from txdav.common.datastore.sql_tables import schema

"""
SQL statement generator from query expressions.
"""

__all__ = [
    "CalDAVSQLQueryGenerator",
]

class CalDAVSQLQueryGenerator(SQLQueryGenerator):

    _timerange = schema.TIME_RANGE
    _transparency = schema.TRANSPARENCY

    def __init__(self, expr, collection, whereid, userid=None, freebusy=False):
        """

        @param expr: the query expression object model
        @type expr: L{expression}
        @param collection: the resource targeted by the query
        @type collection: L{CommonHomeChild}
        @param userid: user for whom query is being done - query will be scoped to that user's privileges and their transparency
        @type userid: C{str}
        @param freebusy: whether or not a freebusy query is being done - if it is, additional time range and transparency information is returned
        @type freebusy: C{bool}
        """
        super(CalDAVSQLQueryGenerator, self).__init__(expr, collection, whereid)
        self.userid = userid if userid else ""
        self.freebusy = freebusy
        self.usedtimerange = False


    def generate(self):
        """
        Generate the actual SQL statement from the passed in expression tree.

        @return: a C{tuple} of (C{str}, C{list}), where the C{str} is the partial SQL statement,
            and the C{list} is the list of argument substitutions to use with the SQL API execute method.
        """

        # Init state
        self.arguments = {}
        self.argcount = 0
        obj = self.collection._objectSchema

        columns = [obj.RESOURCE_NAME, obj.ICALENDAR_UID, obj.ICALENDAR_TYPE]
        if self.freebusy:
            columns.extend([
                obj.ORGANIZER,
                self._timerange.FLOATING,
                self._timerange.START_DATE,
                self._timerange.END_DATE,
                self._timerange.FBTYPE,
                self._timerange.TRANSPARENT,
                self._transparency.TRANSPARENT,
            ])

        # For SQL data DB we need to restrict the query to just the targeted calendar resource-id if provided
        if self.whereid:

            test = expression.isExpression(obj.CALENDAR_RESOURCE_ID, self.whereid, True)

            # Since timerange expression already have the calendar resource-id test in them, do not
            # add the additional term to those. When the additional term is added, add it as the first
            # component in the AND expression to hopefully get the DB to use its index first

            # Top-level timerange expression already has calendar resource-id restriction in it
            if isinstance(self.expression, expression.timerangeExpression):
                pass

            # Top-level OR - check each component
            elif isinstance(self.expression, expression.orExpression):

                def _hasTopLevelTimerange(testexpr):
                    if isinstance(testexpr, expression.timerangeExpression):
                        return True
                    elif isinstance(testexpr, expression.andExpression):
                        return any([isinstance(expr, expression.timerangeExpression) for expr in testexpr.expressions])
                    else:
                        return False

                hasTimerange = any([_hasTopLevelTimerange(expr) for expr in self.expression.expressions])

                if hasTimerange:
                    # timerange expression forces a join on calendarid
                    pass
                else:
                    # AND the whole thing with calendarid
                    self.expression = test.andWith(self.expression)

            # Top-level AND - only add additional expression if timerange not present
            elif isinstance(self.expression, expression.andExpression):
                hasTimerange = any([isinstance(expr, expression.timerangeExpression) for expr in self.expression.expressions])
                if not hasTimerange:
                    # AND the whole thing
                    self.expression = test.andWith(self.expression)

            # Just use the id test
            elif isinstance(self.expression, expression.allExpression):
                self.expression = test

            # Just AND the entire thing
            else:
                self.expression = test.andWith(self.expression)

        # Generate ' where ...' partial statement
        where = self.generateExpression(self.expression)

        if self.usedtimerange:
            where = where.And(self._timerange.CALENDAR_OBJECT_RESOURCE_ID == obj.RESOURCE_ID).And(self._timerange.CALENDAR_RESOURCE_ID == self.whereid)

        # Set of tables depends on use of timespan and fb use
        if self.usedtimerange:
            if self.freebusy:
                tables = obj.join(
                    self._timerange.join(
                        self._transparency,
                        on=(self._timerange.INSTANCE_ID == self._transparency.TIME_RANGE_INSTANCE_ID).And(self._transparency.USER_ID == self.userid),
                        type="left outer"
                    ),
                    type=","
                )
            else:
                tables = obj.join(self._timerange, type=",")
        else:
            tables = obj

        select = Select(
            columns,
            From=tables,
            Where=where,
            Distinct=True,
        )

        return select, self.arguments, self.usedtimerange


    def generateExpression(self, expr):
        """
        Generate an expression and all it's subexpressions.

        @param expr: the L{baseExpression} derived class to write out.
        """

        # Generate based on each type of expression we might encounter
        partial = None

        # time-range
        if isinstance(expr, expression.timerangeExpression):
            if expr.start and expr.end:
                partial = (
                    (self._timerange.FLOATING == False).And(self._timerange.START_DATE < expr.end).And(self._timerange.END_DATE > expr.start)
                ).Or(
                    (self._timerange.FLOATING == True).And(self._timerange.START_DATE < expr.endfloat).And(self._timerange.END_DATE > expr.startfloat)
                )
            elif expr.start and expr.end is None:
                partial = (
                    (self._timerange.FLOATING == False).And(self._timerange.END_DATE > expr.start)
                ).Or(
                    (self._timerange.FLOATING == True).And(self._timerange.END_DATE > expr.startfloat)
                )
            elif not expr.start and expr.end:
                partial = (
                    (self._timerange.FLOATING == False).And(self._timerange.START_DATE < expr.end)
                ).Or(
                    (self._timerange.FLOATING == True).And(self._timerange.START_DATE < expr.endfloat)
                )
            self.usedtimerange = True

        else:
            partial = super(CalDAVSQLQueryGenerator, self).generateExpression(expr)

        return partial


    def addArgument(self, arg):
        """

        @param arg: the C{str} of the argument to add
        """

        # Append argument to the list and add the appropriate substitution string to the output stream.
        self.argcount += 1
        argname = "arg{}".format(self.argcount)
        self.arguments[argname] = arg
        return argname
