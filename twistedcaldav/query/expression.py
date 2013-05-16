##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
from __future__ import print_function

"""
Query Expression Elements. These are used to build a 'generic' query
expression tree that can then be used by different query language
generators to produce the actual query syntax required (SQL, xpath
eyc).
"""

__version__ = "0.0"

__all__ = [
    "allExpression",
    "notExpression",
    "andExpression",
    "orExpression",
    "timerangeExpression",
    "textcompareExpression",
    "containsExpression",
    "notcontainsExpression",
    "isExpression",
    "isnotExpression",
    "startswithExpression",
    "notstartswithExpression",
    "endswithExpression",
    "notendswithExpression",
    "inExpression",
    "notinExpression",
]

class baseExpression(object):
    """
    The base class for all types of expression.
    """

    def __init__(self):
        pass


    def multi(self):
        """
        Indicate whether this expression is composed of multiple sub-expressions.

        @return: C{True} if this expressions contains multiple sub-expressions,
            C{False} otherwise.
        """

        return False


    def _collapsedExpression(self):
        return self


    def andWith(self, other):
        if isinstance(other, andExpression):
            return andExpression((self._collapsedExpression(),) + tuple(other.expressions))
        else:
            return andExpression((self._collapsedExpression(), other._collapsedExpression(),))


    def orWith(self, other):
        if isinstance(other, orExpression):
            return orExpression((self._collapsedExpression(),) + tuple(other.expressions))
        else:
            return orExpression((self._collapsedExpression(), other._collapsedExpression(),))



class allExpression(baseExpression):
    """
    Match everything.
    """

    def __init__(self):
        pass



class logicExpression(baseExpression):
    """
    An expression representing a logical operation (boolean).
    """

    def __init__(self, expressions):
        self.expressions = expressions


    def __str__(self):
        """
        Generate a suitable text descriptor of this expression.

        @return: a C{str} of the text for this expression.
        """

        result = ""
        for e in self.expressions:
            if len(result) != 0:
                result += " " + self.operator() + " "
            result += str(e)
        if len(result):
            result = "(" + result + ")"
        return result


    def multi(self):
        """
        Indicate whether this expression is composed of multiple expressions.

        @return: C{True} if this expressions contains multiple sub-expressions,
            C{False} otherwise.
        """

        return True


    def _collapsedExpression(self):
        if self.multi() and len(self.expressions) == 1:
            return self.expressions[0]._collapsedExpression()
        else:
            return self



class notExpression(logicExpression):
    """
    Logical NOT operation.
    """

    def __init__(self, expression):
        super(notExpression, self).__init__([expression])


    def operator(self):
        return "NOT"


    def __str__(self):
        result = self.operator() + " " + str(self.expressions[0])
        return result


    def multi(self):
        """
        Indicate whether this expression is composed of multiple expressions.

        @return: C{True} if this expressions contains multiple sub-expressions,
            C{False} otherwise.
        """

        return False



class andExpression(logicExpression):
    """
    Logical AND operation.
    """

    def __init__(self, expressions):
        super(andExpression, self).__init__(expressions)


    def operator(self):
        return "AND"


    def andWith(self, other):
        self.expressions = tuple(self.expressions) + (other._collapsedExpression(),)
        return self



class orExpression(logicExpression):
    """
    Logical OR operation.
    """

    def __init__(self, expressions):
        super(orExpression, self).__init__(expressions)


    def operator(self):
        return "OR"


    def orWith(self, other):
        self.expressions = tuple(self.expressions) + (other._collapsedExpression(),)
        return self



class timerangeExpression(baseExpression):
    """
    CalDAV time-range comparison expression.
    """

    def __init__(self, start, end, startfloat, endfloat):
        self.start = start
        self.end = end
        self.startfloat = startfloat
        self.endfloat = endfloat


    def __str__(self):
        return "timerange(" + str(self.start) + ", " + str(self.end) + ")"



class textcompareExpression(baseExpression):
    """
    Base class for text comparison expressions.
    """

    def __init__(self, field, text, caseless):
        self.field = field
        self.text = text
        self.caseless = caseless


    def __str__(self):
        return self.operator() + "(" + self.field + ", " + self.text + ", " + str(self.caseless) + ")"



class containsExpression(textcompareExpression):
    """
    Text CONTAINS (sub-string match) expression.
    """

    def __init__(self, field, text, caseless):
        super(containsExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "contains"



class notcontainsExpression(textcompareExpression):
    """
    Text NOT CONTAINS (sub-string match) expression.
    """

    def __init__(self, field, text, caseless):
        super(notcontainsExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "does not contain"



class isExpression(textcompareExpression):
    """
    Text IS (exact string match) expression.
    """

    def __init__(self, field, text, caseless):
        super(isExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "is"



class isnotExpression(textcompareExpression):
    """
    Text IS NOT (exact string match) expression.
    """

    def __init__(self, field, text, caseless):
        super(isnotExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "is not"



class startswithExpression(textcompareExpression):
    """
    Text STARTSWITH (sub-string match) expression.
    """

    def __init__(self, field, text, caseless):
        super(startswithExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "starts with"



class notstartswithExpression(textcompareExpression):
    """
    Text NOT STARTSWITH (sub-string match) expression.
    """

    def __init__(self, field, text, caseless):
        super(notstartswithExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "does not start with"



class endswithExpression(textcompareExpression):
    """
    Text STARTSWITH (sub-string match) expression.
    """

    def __init__(self, field, text, caseless):
        super(endswithExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "ends with"



class notendswithExpression(textcompareExpression):
    """
    Text NOT STARTSWITH (sub-string match) expression.
    """

    def __init__(self, field, text, caseless):
        super(notendswithExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "does not end with"



class inExpression(textcompareExpression):
    """
    Text IN (exact string match to one of the supplied items) expression.
    """

    def __init__(self, field, text_list, caseless):
        super(inExpression, self).__init__(field, text_list, caseless)


    def operator(self):
        return "in"


    def __str__(self):
        return self.operator() + "(" + self.field + ", " + str(self.text) + ", " + str(self.caseless) + ")"



class notinExpression(textcompareExpression):
    """
    Text NOT IN (exact string match to none of the supplied items) expression.
    """

    def __init__(self, field, text, caseless):
        super(notinExpression, self).__init__(field, text, caseless)


    def operator(self):
        return "not in"


    def __str__(self):
        return self.operator() + "(" + self.field + ", " + str(self.text) + ", " + str(self.caseless) + ")"



if __name__ == "__main__":

    e1 = isExpression("type", "vevent", False)
    e2 = timerangeExpression("20060101T120000Z", "20060101T130000Z", "20060101T120000Z", "20060101T130000Z")
    e3 = containsExpression("summary", "help", True)
    e4 = notExpression(e3)
    e5 = andExpression([e1, e2, e4])
    print(e5)
    e6 = inExpression("type", ("vevent", "vtodo",), False)
    print(e6)
    e7 = notinExpression("type", ("vevent", "vtodo",), False)
    print(e7)
