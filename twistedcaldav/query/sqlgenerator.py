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
SQL statement generator from query expressions.
"""

__version__ = "0.0"

__all__ = [
    "sqlgenerator",
]

from twistedcaldav.query import expression

import cStringIO as StringIO

class sqlgenerator(object):
    
    FROM          =" from "
    WHERE         =" where "
    RESOURCEDB    = "RESOURCE"
    TIMESPANDB    = "TIMESPAN"
    NOTOP         = "NOT "
    ANDOP         = " AND "
    OROP          = " OR "
    CONTAINSOP    = " GLOB "
    NOTCONTAINSOP = " NOT GLOB "
    ISOP          = " == "
    ISNOTOP       = " != "
    INOP          = " IN "
    NOTINOP       = " NOT IN "

    TIMESPANTEST  = "((TIMESPAN.FLOAT == 'N' AND TIMESPAN.START < %s AND TIMESPAN.END > %s) OR (TIMESPAN.FLOAT == 'Y' AND TIMESPAN.START < %s AND TIMESPAN.END > %s)) AND TIMESPAN.NAME == RESOURCE.NAME"

    def __init__(self, expr):
        self.expression = expr
        self.usedtimespan = False
        
    def generate(self):
        """
        Generate the actual SQL 'where ...' expression from the passed in expression tree.
        
        @return: a C{tuple} of (C{str}, C{list}), where the C{str} is the partial SQL statement,
            and the C{list} is the list of argument substitutions to use with the SQL API execute method.
        """
        
        # Init state
        self.sout = StringIO.StringIO()
        self.arguments = []
        self.usedtimespan = False
        
        # Generate ' where ...' partial statement
        self.sout.write(self.WHERE)
        self.generateExpression(self.expression)

        # Prefix with ' from ...' partial statement
        select = self.FROM + self.RESOURCEDB
        if self.usedtimespan:
            select += ", " + self.TIMESPANDB
        select += self.sout.getvalue()
        return select, self.arguments
        
    def generateExpression(self, expr):
        """
        Generate an expression and all it's subexpressions.
        
        @param expr: the L{baseExpression} derived class to write out.
        @return: C{True} if the TIMESPAN table is used, C{False} otherwise.
        """
        
        # Generate based on each type of expression we might encounter
        
        # ALL
        if isinstance(expr, expression.allExpression):
            # Wipe out the ' where ...' clause so everything is matched
            self.sout.truncate(0)
            self.arguments = []
            self.usedtimespan = False
        
        # NOT
        elif isinstance(expr, expression.notExpression):
            self.sout.write(self.NOTOP)
            self.generateSubExpression(expr.expressions[0])
        
        # AND
        elif isinstance(expr, expression.andExpression):
            first = True
            for e in expr.expressions:
                if first:
                    first = False
                else:
                    self.sout.write(self.ANDOP)
                self.generateSubExpression(e)
        
        # OR
        elif isinstance(expr, expression.orExpression):
            first = True
            for e in expr.expressions:
                if first:
                    first = False
                else:
                    self.sout.write(self.OROP)
                self.generateSubExpression(e)
        
        # time-range
        elif isinstance(expr, expression.timerangeExpression):
            arg1 = self.setArgument(expr.end)
            arg2 = self.setArgument(expr.start)
            arg3 = self.setArgument(expr.endfloat)
            arg4 = self.setArgument(expr.startfloat)
            test = self.TIMESPANTEST % (arg1, arg2, arg3, arg4)
            self.sout.write(test)
            self.usedtimespan = True
        
        # CONTAINS
        elif isinstance(expr, expression.containsExpression):
            self.sout.write(expr.field)
            self.sout.write(self.CONTAINSOP)
            self.addArgument(expr.text)
        
        # NOT CONTAINS
        elif isinstance(expr, expression.notcontainsExpression):
            self.sout.write(expr.field)
            self.sout.write(self.NOTCONTAINSOP)
            self.addArgument(expr.text)
        
        # IS
        elif isinstance(expr, expression.isExpression):
            self.sout.write(expr.field)
            self.sout.write(self.ISOP)
            self.addArgument(expr.text)
        
        # IS NOT
        elif isinstance(expr, expression.isnotExpression):
            self.sout.write(expr.field)
            self.sout.write(self.ISNOTOP)
            self.addArgument(expr.text)
        
        # IN
        elif isinstance(expr, expression.inExpression):
            self.sout.write(expr.field)
            self.sout.write(self.INOP)
            self.sout.write("(")
            for count, item in enumerate(expr.text):
                if count != 0:
                    self.sout.write(", ")
                self.addArgument(item)
            self.sout.write(")")
        
        # NOT IN
        elif isinstance(expr, expression.notinExpression):
            self.sout.write(expr.field)
            self.sout.write(self.NOTINOP)
            self.sout.write("(")
            for count, item in enumerate(expr.text):
                if count != 0:
                    self.sout.write(", ")
                self.addArgument(item)
            self.sout.write(")")

    def generateSubExpression(self, expression):
        """
        Generate an SQL expression possibly in paranethesis if its a compound expression.

        @param expression: the L{baseExpression} to write out.
        @return: C{True} if the TIMESPAN table is used, C{False} otherwise.
        """
       
        if expression.multi():
            self.sout.write("(")
        self.generateExpression(expression)
        if expression.multi():
            self.sout.write(")")
    
    def addArgument(self, arg):
        """
        
        @param arg: the C{str} of the argument to add
        """
        
        # Append argument to the list and add the appropriate substituion string to the output stream.
        self.arguments.append(arg)
        self.sout.write(":" + str(len(self.arguments)))
    
    def setArgument(self, arg):
        """
        
        @param arg: the C{str} of the argument to add
        @return: C{str} for argument substitution text
        """
        
        # Append argument to the list and add the appropriate substituion string to the output stream.
        self.arguments.append(arg)
        return ":" + str(len(self.arguments))


if __name__ == "__main__":
    
    e1 = expression.isExpression("TYPE", "VEVENT", False)
    e2 = expression.timerangeExpression("20060101T120000Z", "20060101T130000Z", "20060101T080000Z", "20060101T090000Z")
    e3 = expression.notcontainsExpression("SUMMARY", "help", True)
    e5 = expression.andExpression([e1, e2, e3])
    print e5
    sql = sqlgenerator(e5)
    print sql.generate()
    e6 = expression.inExpression("TYPE", ("VEVENT", "VTODO",), False)
    print e6
    sql = sqlgenerator(e6)
    print sql.generate()
    e7 = expression.notinExpression("TYPE", ("VEVENT", "VTODO",), False)
    print e7
    sql = sqlgenerator(e7)
    print sql.generate()
