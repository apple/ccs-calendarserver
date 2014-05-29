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
    matchExpressionFromJSON,  # compoundExpressionFromJSON,
    # expressionFromJSON, expressionFromJSONText,
    from_json_text,  # to_json_text,
)

from twext.who.test.test_xml import xmlService
from twisted.trial import unittest



class SerializationTests(unittest.TestCase):
    """
    Tests for serialization to JSON.
    """

    def service(self, subClass=None, xmlData=None):
        return xmlService(self.mktemp())


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
            (MatchType.equals, "equals"),
            (MatchType.endsWith, "endsWith"),
            (MatchType.lessThanOrEqualTo, "lessThanOrEqualTo"),
        ):
            expression = MatchExpression(
                FieldName.uid, uid, matchType=matchType
            )
            json = matchExpressionAsJSON(expression)

            expected = {
                "type": "MatchExpression",
                "field": "uid",
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
                "{}"
            ),
            (
                MatchFlags.NOT,
                "NOT"
            ),
            (
                MatchFlags.caseInsensitive,
                "caseInsensitive"
            ),
            (
                MatchFlags.NOT | MatchFlags.caseInsensitive,
                "{NOT,caseInsensitive}"
            ),
        ):
            expression = MatchExpression(FieldName.uid, uid, flags=flags)
            json = matchExpressionAsJSON(expression)

            expected = {
                "type": "MatchExpression",
                "field": "uid",
                "match": "equals",
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
                "type": "CompoundExpression",
                "expressions": subExpressionsText,
                "operand": "AND",
            }

            self.assertEquals(json, expected)


    def test_compoundExpressionAsJSON_operands(self):
        """
        L{compoundExpressionAsJSON} with different operands.
        """
        for operand, operandText in (
            (Operand.AND, "AND"),
            (Operand.OR, "OR"),
        ):
            expression = CompoundExpression((), operand)
            json = compoundExpressionAsJSON(expression)

            expected = {
                "type": "CompoundExpression",
                "expressions": [],
                "operand": operandText,
            }

            self.assertEquals(json, expected)


    def test_matchExpressionFromJSON_basic(self):
        """
        L{test_matchExpressionFromJSON_basic} with default matching and flags.
        """
        service = self.service()
        uid = u"Some UID"
        jsonText = (
            """
            {{
                "type": "MatchExpression",
                "field": "uid",
                "value": "{uid}"
            }}
            """
        ).format(uid=uid)
        json = from_json_text(jsonText)

        expected = MatchExpression(FieldName.uid, uid)
        expression = matchExpressionFromJSON(service, json)

        self.assertEquals(expression, expected)


    def test_matchExpressionFromJSON_types(self):
        """
        L{matchExpressionFromJSON} with various match types.
        """
        service = self.service()
        uid = u"Some UID"

        for matchType, matchText in (
            (MatchType.equals, b"equals"),
            (MatchType.endsWith, b"endsWith"),
            (MatchType.lessThanOrEqualTo, b"lessThanOrEqualTo"),
        ):
            jsonText = (
                """
                {{
                    "type": "MatchExpression",
                    "field": "uid",
                    "match": "{matchType}",
                    "value": "{uid}",
                    "flags": "{{}}"
                }}
                """
            ).format(uid=uid, matchType=matchText)
            json = from_json_text(jsonText)

            expected = MatchExpression(FieldName.uid, uid, matchType=matchType)
            expression = matchExpressionFromJSON(service, json)

            self.assertEquals(expression, expected)


    def test_matchExpressionFromJSON_flags(self):
        """
        L{matchExpressionFromJSON} with various flags.
        """
        service = self.service()
        uid = u"Some UID"

        for flags, flagsText, in (
            (
                MatchFlags.none,
                "{}"
            ),
            (
                MatchFlags.NOT,
                "NOT"
            ),
            (
                MatchFlags.caseInsensitive,
                "caseInsensitive"
            ),
            (
                MatchFlags.NOT | MatchFlags.caseInsensitive,
                "{NOT,caseInsensitive}"
            ),
        ):
            jsonText = (
                """
                {{
                    "type": "MatchExpression",
                    "field": "uid",
                    "match": "equals",
                    "value": "{uid}",
                    "flags": "{flagsText}"
                }}
                """
            ).format(uid=uid, flagsText=flagsText)
            json = from_json_text(jsonText)

            expected = MatchExpression(FieldName.uid, uid, flags=flags)
            expression = matchExpressionFromJSON(service, json)

            self.assertEquals(expression, expected)
