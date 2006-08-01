##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Query Expression Elements. These are used to build a 'generic' query expression tree that can then
be used by different query language generators to produce the actual query syntax required (SQL, xpath eyc).
"""

__version__ = "0.0"

__all__ = [
    "notExpression",
    "andExpression",
    "orExpression",
    "timerangeExpression",
    "containsExpression",
    "isExpression",
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
    
class allExpression(object):
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
        Generate a suitable text descriptor of this epxression.
        
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

class orExpression(logicExpression):
    """
    Logical OR operation.
    """
    
    def __init__(self, expressions):
        super(orExpression, self).__init__(expressions)

    def operator(self):
        return "OR"

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
        return " does not contain"

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

if __name__ == "__main__":
    
    e1 = isExpression("type", "vevent", False)
    e2 = timerangeExpression("20060101T120000Z", "20060101T130000Z")
    e3 = containsExpression("summary", "help", True)
    e4 = notExpression(e3)
    e5 = andExpression([e1, e2, e4])
    print e5

