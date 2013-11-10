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
    "Operand",
    "CompoundExpression",

    "MatchType",
    "MatchFlags",
    "MatchExpression",
]

from twisted.python.constants import Names, NamedConstant
from twisted.python.constants import Flags, FlagConstant

from twext.who.util import iterFlags, describe


#
# Compound expression
#

class Operand(Names):
    """
    Contants for common operands.
    """
    OR  = NamedConstant()
    AND = NamedConstant()

    OR.description  = u"or"
    AND.description = u"and"



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
    equals = NamedConstant()
    equals.description = u"equals"

    startsWith = NamedConstant()
    startsWith.description = u"starts with"

    contains = NamedConstant()
    contains.description = u"contains"



class MatchFlags(Flags):
    """
    Match expression flags.
    """
    NOT = FlagConstant()
    NOT.description = u"not"

    caseInsensitive = FlagConstant()
    caseInsensitive.description = u"case insensitive"


    @staticmethod
    def _setMatchFunctions(flags):
        """
        Compute a predicate and normalize functions for the given match
        expression flags.

        @param flags: Match expression flags.
        @type flags: L{MatchFlags}

        @return: Predicate and normalize functions.
        @rtype: L{tuple} of callables.
        """
        predicate = lambda x: x
        normalize = lambda x: x

        if flags is None:
            flags = FlagConstant()
        else:
            for flag in iterFlags(flags):
                if flag == MatchFlags.NOT:
                    predicate = lambda x: not x
                elif flag == MatchFlags.caseInsensitive:
                    normalize = lambda x: x.lower()
                else:
                    raise NotImplementedError(
                        "Unknown query flag: {0}".format(describe(flag))
                    )

        flags._predicate = predicate
        flags._normalize = normalize

        return flags


    @staticmethod
    def predicator(flags):
        """
        Determine a predicate function for the given flags.

        @param flags: Match expression flags.
        @type flags: L{MatchFlags}

        @return: a L{callable} that accepts an L{object} argument and returns a
        L{object} that has the opposite or same truth value as the argument,
        depending on whether L{MatchFlags.NOT} is or is not in C{flags}.
        @rtype: callable
        """
        if not hasattr(flags, "_predicate"):
            flags = MatchFlags._setMatchFunctions(flags)
        return flags._predicate


    @staticmethod
    def normalizer(flags):
        """
        Determine a predicate function for the given flags.

        @param flags: Match expression flags.
        @type flags: L{MatchFlags}

        @return: a L{callable} that accepts a L{unicode} and returns the same
        L{unicode} or a normalized L{unicode} that can be compared with other
        normalized L{unicode}s in a case-insensitive fashion, depending on
        whether L{MatchFlags.caseInsensitive} is not or is in C{flags}.
        @rtype: callable
        """
        if not hasattr(flags, "_normalize"):
            flags = MatchFlags._setMatchFunctions(flags)
        return flags._normalize



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
        self.fieldName = fieldName
        self.fieldValue = fieldValue
        self.matchType = matchType
        self.flags = flags


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
