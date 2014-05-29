#
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

"""
Tests for txdav.dps.json.
"""

from twext.who.idirectory import FieldName
from twext.who.expression import MatchExpression, MatchType, MatchFlags
from twext.who.expression import CompoundExpression, Operand

from ..json import (
    matchExpressionAsJSON, compoundExpressionAsJSON,
    # expressionAsJSON, expressionAsJSONText,
    # matchExpressionFromJSON, compoundExpressionFromJSON,
    # expressionFromJSON, expressionFromJSONText,
)

from twisted.trial import unittest



class SerializationTests(unittest.TestCase):
    """
    Tests for serialization to JSON.
    """

    def test_matchExpressionAsJSON_basic(self):
        """
        L{matchExpressionAsJSON} with default matching and flags.
        """
        uid = u"Some UID"
        expression = MatchExpression(FieldName.uid, uid)
        json = matchExpressionAsJSON(expression)

        expected = {
            "type": "MatchExpression",
            "field": "uid",
            "match": "equals",
            "value": uid,
            "flags": "{}",
        }

        self.assertEquals(json, expected)


    def test_matchExpressionAsJSON_types(self):
        """
        L{matchExpressionAsJSON} with various match types.
        """
        uid = u"Some UID"

        for matchType, matchText in (
            (MatchType.equals, b"equals"),
            (MatchType.endsWith, b"endsWith"),
            (MatchType.lessThanOrEqualTo, b"lessThanOrEqualTo"),
        ):
            expression = MatchExpression(
                FieldName.uid, uid, matchType=matchType
            )
            json = matchExpressionAsJSON(expression)

            expected = {
                "type": b"MatchExpression",
                "field": b"uid",
                "match": matchText,
                "value": uid,
                "flags": "{}",
            }

            self.assertEquals(json, expected)


    def test_matchExpressionAsJSON_flags(self):
        """
        L{matchExpressionAsJSON} with various flags.
        """
        uid = u"Some UID"

        for flags, flagsText, in (
            (
                MatchFlags.none,
                b"{}"
            ),
            (
                MatchFlags.NOT,
                b"NOT"
            ),
            (
                MatchFlags.caseInsensitive,
                b"caseInsensitive"
            ),
            (
                MatchFlags.NOT | MatchFlags.caseInsensitive,
                b"{NOT,caseInsensitive}"
            ),
        ):
            expression = MatchExpression(FieldName.uid, uid, flags=flags)
            json = matchExpressionAsJSON(expression)

            expected = {
                "type": b"MatchExpression",
                "field": b"uid",
                "match": b"equals",
                "value": uid,
                "flags": flagsText,
            }

            self.assertEquals(json, expected)


    def test_compoundExpressionAsJSON_expressions(self):
        """
        L{compoundExpressionAsJSON} with 0, 1 and 2 sub-expressions.
        """
        for uids in (
            (), (u"UID1",), (u"UID1", u"UID2"),
        ):
            subExpressions = [
                MatchExpression(FieldName.uid, uid) for uid in uids
            ]
            subExpressionsText = [
                matchExpressionAsJSON(e) for e in subExpressions
            ]

            expression = CompoundExpression(subExpressions, Operand.AND)
            json = compoundExpressionAsJSON(expression)

            expected = {
                'type': 'CompoundExpression',
                'expressions': subExpressionsText,
                'operand': 'AND',
            }

            self.assertEquals(json, expected)
