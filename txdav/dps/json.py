##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

from __future__ import absolute_import

"""
JSON serialization utilities.
"""

__all__ = [
    "expressionAsJSONText",
    "expressionFromJSONText",
]

from json import dumps, loads as from_json_text

from twext.who.expression import (
    CompoundExpression, Operand,
    MatchExpression, MatchType, MatchFlags,
)



def expressionAsJSONText(expression):
    return to_json_text(expressionAsJSON(expression))


def expressionAsJSON(expression):
    if isinstance(expression, CompoundExpression):
        return compoundExpressionAsJSON(expression)

    if isinstance(expression, MatchExpression):
        return matchExpressionAsJSON(expression)

    raise NotImplementedError(
        "Unknown expression type: {!r}".format(expression)
    )


def compoundExpressionAsJSON(expression):
    return dict(
        type=expression.__class__.__name__,
        operand=expression.operand.name,
        expressions=[expressionAsJSON(e) for e in expression.expressions],
    )


def matchExpressionAsJSON(expression):
    return dict(
        type=expression.__class__.__name__,
        field=expression.fieldName.name,
        value=expression.fieldValue,
        match=expression.matchType.name,
        flags=expression.flags.name,
    )
    raise NotImplementedError()


def expressionFromJSONText(jsonText):
    Operand
    MatchType, MatchFlags
    from_json_text
    raise NotImplementedError()



def to_json_text(obj):
    """
    Convert an object into JSON text.

    @param obj: An object that is serializable to JSON.
    @type obj: L{object}

    @return: JSON text.
    @rtype: L{unicode}
    """
    return dumps(obj, separators=(',', ':')).decode("UTF-8")
