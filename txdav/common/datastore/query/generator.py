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

from twext.enterprise.dal.syntax import Select, Parameter, Not
from txdav.common.datastore.query import expression

"""
SQL statement generator from query expressions.
"""

__all__ = [
    "SQLQueryGenerator",
]

class SQLQueryGenerator(object):

    def __init__(self, expr, collection, whereid):
        """

        @param expr: the query expression object model
        @type expr: L{expression}
        @param collection: the resource targeted by the query
        @type collection: L{CommonHomeChild}
        """
        self.expression = expr
        self.collection = collection
        self.whereid = whereid


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

        columns = [obj.RESOURCE_NAME, obj.UID]

        # For SQL data DB we need to restrict the query to just the targeted collection resource-id if provided
        if self.whereid:
            # AND the whole thing
            test = expression.isExpression(obj.PARENT_RESOURCE_ID, self.whereid, True)
            self.expression = test if isinstance(self.expression, expression.allExpression) else test.andWith(self.expression)

        # Generate ' where ...' partial statement
        where = self.generateExpression(self.expression)

        select = Select(
            columns,
            From=obj,
            Where=where,
            Distinct=True,
        )

        return select, self.arguments


    def generateExpression(self, expr):
        """
        Generate an expression and all it's subexpressions.

        @param expr: the L{baseExpression} derived class to write out.
        """

        # Generate based on each type of expression we might encounter
        partial = None

        # ALL
        if isinstance(expr, expression.allExpression):
            # Everything is matched
            partial = None
            self.arguments = {}

        # NOT
        elif isinstance(expr, expression.notExpression):
            partial = Not(self.generateExpression(expr.expressions[0]))

        # AND
        elif isinstance(expr, expression.andExpression):
            for e in expr.expressions:
                next = self.generateExpression(e)
                partial = partial.And(next) if partial is not None else next

        # OR
        elif isinstance(expr, expression.orExpression):
            for e in expr.expressions:
                next = self.generateExpression(e)
                partial = partial.Or(next) if partial is not None else next

        # CONTAINS
        elif isinstance(expr, expression.containsExpression):
            partial = expr.field.Contains(expr.text)

        # NOT CONTAINS
        elif isinstance(expr, expression.notcontainsExpression):
            partial = expr.field.NotContains(expr.text)

        # IS
        elif isinstance(expr, expression.isExpression):
            partial = expr.field == expr.text

        # IS NOT
        elif isinstance(expr, expression.isnotExpression):
            partial = expr.field != expr.text

        # STARTSWITH
        elif isinstance(expr, expression.startswithExpression):
            partial = expr.field.StartsWith(expr.text)

        # NOT STARTSWITH
        elif isinstance(expr, expression.notstartswithExpression):
            partial = expr.field.NotStartsWith(expr.text)

        # ENDSWITH
        elif isinstance(expr, expression.endswithExpression):
            partial = expr.field.EndsWith(expr.text)

        # NOT ENDSWITH
        elif isinstance(expr, expression.notendswithExpression):
            partial = expr.field.NotEndsWith(expr.text)

        # IN
        elif isinstance(expr, expression.inExpression):
            argname = self.addArgument(expr.text)
            partial = expr.field.In(Parameter(argname, len(expr.text)))

        # NOT IN
        elif isinstance(expr, expression.notinExpression):
            argname = self.addArgument(expr.text)
            partial = expr.field.NotIn(Parameter(argname, len(expr.text)))

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
