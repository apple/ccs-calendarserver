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
    expressionAsJSON, expressionAsJSONText,
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

    def test_matchExpressionAsJSON_basic(
        self, serialize=matchExpressionAsJSON
    ):
        """
        L{matchExpressionAsJSON} with default matching and flags.
        """
        uid = u"Some UID"
        expression = MatchExpression(FieldName.uid, uid)
        json = serialize(expression)

        expected = {
            u"type": u"MatchExpression",
            u"field": u"uid",
            u"match": u"equals",
            u"value": uid,
            u"flags": u"{}",
        }

        self.assertEquals(json, expected)


    def test_matchExpressionAsJSON_types(
        self, serialize=matchExpressionAsJSON
    ):
        """
        L{matchExpressionAsJSON} with various match types.
        """
        uid = u"Some UID"

        for matchType, matchText in (
            (MatchType.equals, u"equals"),
            (MatchType.endsWith, u"endsWith"),
            (MatchType.lessThanOrEqualTo, u"lessThanOrEqualTo"),
        ):
            expression = MatchExpression(
                FieldName.uid, uid, matchType=matchType
            )
            json = serialize(expression)

            expected = {
                u"type": u"MatchExpression",
                u"field": u"uid",
                u"match": matchText,
                u"value": uid,
                u"flags": u"{}",
            }

            self.assertEquals(json, expected)


    def test_matchExpressionAsJSON_flags(
        self, serialize=matchExpressionAsJSON
    ):
        """
        L{matchExpressionAsJSON} with various flags.
        """
        uid = u"Some UID"

        for flags, flagsText, in (
            (
                MatchFlags.none,
                u"{}"
            ),
            (
                MatchFlags.NOT,
                u"NOT"
            ),
            (
                MatchFlags.caseInsensitive,
                u"caseInsensitive"
            ),
            (
                MatchFlags.NOT | MatchFlags.caseInsensitive,
                u"{NOT,caseInsensitive}"
            ),
        ):
            expression = MatchExpression(FieldName.uid, uid, flags=flags)
            json = serialize(expression)

            expected = {
                u"type": u"MatchExpression",
                u"field": u"uid",
                u"match": u"equals",
                u"value": uid,
                u"flags": flagsText,
            }

            self.assertEquals(json, expected)


    def test_compoundExpressionAsJSON_expressions(
        self, serialize=compoundExpressionAsJSON
    ):
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
                u"type": u"CompoundExpression",
                u"expressions": subExpressionsText,
                u"operand": u"AND",
            }

            self.assertEquals(json, expected)


    def test_compoundExpressionAsJSON_operands(
        self, serialize=compoundExpressionAsJSON
    ):
        """
        L{compoundExpressionAsJSON} with different operands.
        """
        for operand, operandText in (
            (Operand.AND, u"AND"),
            (Operand.OR, u"OR"),
        ):
            expression = CompoundExpression((), operand)
            json = compoundExpressionAsJSON(expression)

            expected = {
                u"type": u"CompoundExpression",
                u"expressions": [],
                u"operand": operandText,
            }

            self.assertEquals(json, expected)


    def test_expressionAsJSON_matchExpression(self):
        """
        L{expressionAsJSON} with match expression.
        """
        self.test_matchExpressionAsJSON_basic(expressionAsJSON)
        self.test_matchExpressionAsJSON_types(expressionAsJSON)
        self.test_matchExpressionAsJSON_flags(expressionAsJSON)


    def test_expressionAsJSON_compoundExpression(self):
        """
        L{expressionAsJSON} with compound expression.
        """
        self.test_compoundExpressionAsJSON_expressions(expressionAsJSON)
        self.test_compoundExpressionAsJSON_operands(expressionAsJSON)


    def test_expressionAsJSON_unknown(self):
        """
        L{expressionAsJSON} with compound expression.
        """
        self.assertRaises(TypeError, expressionAsJSON, object())


    def test_expressionAsJSONText(self):
        """
        L{expressionAsJSON} with compound expression.
        """
        uid = u"Some UID"
        expression = MatchExpression(FieldName.uid, uid)
        jsonText = expressionAsJSONText(expression)

        expected = (
            u"""
            {{
                "field": "uid",
                "flags": "{{}}",
                "match": "equals",
                "value": "{uid}",
                "type": "MatchExpression"
            }}
            """
        ).replace(" ", "").replace("\n", "").format(uid=uid)

        self.assertEquals(jsonText, expected)



class DeserializationTests(unittest.TestCase):
    """
    Tests for deserialization from JSON.
    """

    def service(self, subClass=None, xmlData=None):
        return xmlService(self.mktemp())


    def test_matchExpressionFromJSON_basic(self):
        """
        L{test_matchExpressionFromJSON_basic} with default matching and flags.
        """
        service = self.service()
        uid = u"Some UID"
        jsonText = (
            u"""
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
            (MatchType.equals, u"equals"),
            (MatchType.endsWith, u"endsWith"),
            (MatchType.lessThanOrEqualTo, u"lessThanOrEqualTo"),
        ):
            jsonText = (
                u"""
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
                u"{}"
            ),
            (
                MatchFlags.NOT,
                u"NOT"
            ),
            (
                MatchFlags.caseInsensitive,
                u"caseInsensitive"
            ),
            (
                MatchFlags.NOT | MatchFlags.caseInsensitive,
                u"{NOT,caseInsensitive}"
            ),
        ):
            jsonText = (
                u"""
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
