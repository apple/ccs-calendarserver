# -*- test-case-name: twext.who.test.test_expression -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
Directory query expressions.
"""

__all__ = [
    "CompoundExpression",

    "MatchType",
    "MatchFlags",
    "MatchExpression",
]

from twisted.python.constants import Names, NamedConstant
from twisted.python.constants import Flags, FlagConstant



#
# Compound expression
#

class CompoundExpression(object):
    """
    An expression that groups multiple expressions with an operand.

    @ivar expressions: An iterable of expressions.

    @ivar operand: A L{NamedConstant} specifying an operand.
    """

    def __init__(self, expressions, operand):
        self.expressions = expressions
        self.operand = operand


#
# Match expression
#

class MatchType(Names):
    """
    Query match types.
    """
    equals     = NamedConstant()
    startsWith = NamedConstant()
    contains   = NamedConstant()

    equals.description     = u"equals"
    startsWith.description = u"starts with"
    contains.description   = u"contains"



class MatchFlags(Flags):
    """
    Match expression flags.
    """
    NOT = FlagConstant()
    NOT.description = u"not"

    caseInsensitive = FlagConstant()
    caseInsensitive.description = u"case insensitive"



class MatchExpression(object):
    """
    Query for a matching value in a given field.

    @ivar fieldName: A L{NamedConstant} specifying the field.

    @ivar fieldValue: A value to match.

    @ivar matchType: A L{NamedConstant} specifying the match algorithm.

    @ivar flags: A L{NamedConstant} specifying additional options.
    """

    def __init__(
        self,
        fieldName, fieldValue,
        matchType=MatchType.equals, flags=None
    ):
        self.fieldName  = fieldName
        self.fieldValue = fieldValue
        self.matchType  = matchType
        self.flags      = flags


    def __repr__(self):
        def describe(constant):
            return getattr(constant, "description", unicode(constant))

        if self.flags is None:
            flags = ""
        else:
            flags = " ({0})".format(describe(self.flags))

        return (
            "<{self.__class__.__name__}: {fieldName!r} "
            "{matchType} {fieldValue!r}{flags}>"
            .format(
                self=self,
                fieldName=describe(self.fieldName),
                matchType=describe(self.matchType),
                fieldValue=describe(self.fieldValue),
                flags=flags,
            )
        )
