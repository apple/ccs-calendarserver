##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
#
##
from __future__ import print_function

"""
Compound query builder. We do this in Python to avoid having to mess
with pass a complex Python object hierarchy into C. These classes allow us to
build the query in Python and generate the compound query string that the directory
service C api requires.
"""

import dsattributes

class match(object):
    """
    Represents and attribute/value match operation.
    """

    def __init__(self, attribute, value, matchType):
        self.attribute = attribute
        self.value = value
        self.matchType = matchType


    def generate(self):
        return {
            dsattributes.eDSExact: "(%s=%s)",
            dsattributes.eDSStartsWith: "(%s=%s*)",
            dsattributes.eDSEndsWith: "(%s=*%s)",
            dsattributes.eDSContains: "(%s=*%s*)",
            dsattributes.eDSLessThan: "(%s<%s)",
            dsattributes.eDSGreaterThan : "(%s>%s)",
        }.get(self.matchType, "(%s=*%s*)") % (self.attribute, self.value,)



class expression(object):
    """
    Represents a query expression that includes a boolean operator, and a list
    of sub-expressions operated on. The sub-expressions can either be another expression
    object or a match object.
    """

    AND = "&"
    OR = "|"
    NOT = "!"

    def __init__(self, operator, subexpressions):
        assert(operator == expression.AND or operator == expression.OR or operator == expression.NOT)
        self.operator = operator
        self.subexpressions = subexpressions


    def generate(self):
        result = ""
        if self.operator == expression.NOT:
            result += "("
            result += self.operator
            result += self.subexpressions.generate()
            result += ")"
        else:
            if len(self.subexpressions) > 1:
                result += "("
                result += self.operator
            for sub in self.subexpressions:
                result += sub.generate()
            if len(self.subexpressions) > 1:
                result += ")"
        return result


# Do some tests
if __name__ == '__main__':
    exprs = (
        (expression(
            expression.AND, (
                expression(expression.OR, (match("ResourceType", "xyz", dsattributes.eDSExact), match("ResourceType", "abc", dsattributes.eDSExact))),
                match("ServicesLocator", "GUID:VGUID:calendar", dsattributes.eDSStartsWith),
            )
        ), "(&(|(ResourceType=xyz)(ResourceType=abc))(ServicesLocator=GUID:VGUID:calendar*))"),
        (expression(
            expression.AND, (
                expression(expression.OR, (match("ResourceType", "xyz", dsattributes.eDSStartsWith), match("ResourceType", "abc", dsattributes.eDSEndsWith))),
                match("ServicesLocator", "GUID:VGUID:calendar", dsattributes.eDSContains),
            )
        ), "(&(|(ResourceType=xyz*)(ResourceType=*abc))(ServicesLocator=*GUID:VGUID:calendar*))"),
        (expression(
            expression.AND, (
                expression(expression.AND, (match("ResourceType", "xyz", dsattributes.eDSLessThan), match("ResourceType", "abc", dsattributes.eDSGreaterThan))),
                match("ServicesLocator", "GUID:VGUID:calendar", 0xBAD),
            )
        ), "(&(&(ResourceType<xyz)(ResourceType>abc))(ServicesLocator=*GUID:VGUID:calendar*))"),
        (expression(
            expression.AND, (
                match("ServicesLocator", "GUID:VGUID:calendar", 0xBAD),
            )
        ), "(ServicesLocator=*GUID:VGUID:calendar*)"),
        (expression(
            expression.NOT, match(dsattributes.kDSNAttrNickName, "", dsattributes.eDSStartsWith)
        ), "(!(" + dsattributes.kDSNAttrNickName + "=*))"),
        (expression(
            expression.AND, (
               expression(
                    expression.NOT, match(dsattributes.kDSNAttrNickName, "Billy", dsattributes.eDSContains)
               ),
               expression(
                    expression.NOT, match(dsattributes.kDSNAttrEMailAddress, "Billy", dsattributes.eDSContains)
               ),
            ),
        ), "(&(!(" + dsattributes.kDSNAttrNickName + "=*Billy*))(!(" + dsattributes.kDSNAttrEMailAddress + "=*Billy*)))"),
        (expression(
            expression.NOT, expression(
                    expression.OR, (
                        match(dsattributes.kDSNAttrNickName, "", dsattributes.eDSStartsWith),
                        match(dsattributes.kDSNAttrEMailAddress, "", dsattributes.eDSStartsWith),
                    ),
            ),
        ), "(!(|(" + dsattributes.kDSNAttrNickName + "=*)(" + dsattributes.kDSNAttrEMailAddress + "=*)))"),
    )

    for expr, result in exprs:
        gen = expr.generate()
        if gen != result:
            print("Generate expression %s != %s" % (gen, result,))
    print("Done.")
