##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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

from txdav.common.datastore.query import expression
from twisted.trial.unittest import TestCase

class Tests(TestCase):

    def test_andWith(self):

        tests = (
            (
                expression.isExpression("A", "1", True),
                expression.isExpression("B", "2", True),
                "(is(A, 1, True) AND is(B, 2, True))"
            ),
            (
                expression.isExpression("A", "1", True),
                expression.andExpression((
                    expression.isExpression("B", "2", True),
                )),
                "(is(A, 1, True) AND is(B, 2, True))"
            ),
            (
                expression.isExpression("A", "1", True),
                expression.andExpression((
                    expression.isExpression("B", "2", True),
                    expression.isExpression("C", "3", True),
                )),
                "(is(A, 1, True) AND is(B, 2, True) AND is(C, 3, True))"
            ),
            (
                expression.isExpression("A", "1", True),
                expression.orExpression((
                    expression.isExpression("B", "2", True),
                )),
                "(is(A, 1, True) AND is(B, 2, True))"
            ),
            (
                expression.isExpression("A", "1", True),
                expression.orExpression((
                    expression.isExpression("B", "2", True),
                    expression.isExpression("C", "3", True),
                )),
                "(is(A, 1, True) AND (is(B, 2, True) OR is(C, 3, True)))"
            ),
            (
                expression.andExpression((
                    expression.isExpression("A", "1", True),
                )),
                expression.isExpression("B", "2", True),
                "(is(A, 1, True) AND is(B, 2, True))"
            ),
            (
                expression.andExpression((
                    expression.isExpression("A", "1", True),
                    expression.isExpression("B", "2", True),
                )),
                expression.isExpression("C", "3", True),
                "(is(A, 1, True) AND is(B, 2, True) AND is(C, 3, True))"
            ),
            (
                expression.orExpression((
                    expression.isExpression("A", "1", True),
                )),
                expression.isExpression("B", "2", True),
                "(is(A, 1, True) AND is(B, 2, True))"
            ),
            (
                expression.orExpression((
                    expression.isExpression("A", "1", True),
                    expression.isExpression("B", "2", True),
                )),
                expression.isExpression("C", "3", True),
                "((is(A, 1, True) OR is(B, 2, True)) AND is(C, 3, True))"
            ),
        )

        for expr1, expr2, result in tests:
            self.assertEqual(str(expr1.andWith(expr2)), result, msg="Failed on %s" % (result,))


    def test_orWith(self):

        tests = (
            (
                expression.isExpression("A", "1", True),
                expression.isExpression("B", "2", True),
                "(is(A, 1, True) OR is(B, 2, True))"
            ),
            (
                expression.isExpression("A", "1", True),
                expression.andExpression((
                    expression.isExpression("B", "2", True),
                )),
                "(is(A, 1, True) OR is(B, 2, True))"
            ),
            (
                expression.isExpression("A", "1", True),
                expression.andExpression((
                    expression.isExpression("B", "2", True),
                    expression.isExpression("C", "3", True),
                )),
                "(is(A, 1, True) OR (is(B, 2, True) AND is(C, 3, True)))"
            ),
            (
                expression.isExpression("A", "1", True),
                expression.orExpression((
                    expression.isExpression("B", "2", True),
                )),
                "(is(A, 1, True) OR is(B, 2, True))"
            ),
            (
                expression.isExpression("A", "1", True),
                expression.orExpression((
                    expression.isExpression("B", "2", True),
                    expression.isExpression("C", "3", True),
                )),
                "(is(A, 1, True) OR is(B, 2, True) OR is(C, 3, True))"
            ),
            (
                expression.andExpression((
                    expression.isExpression("A", "1", True),
                )),
                expression.isExpression("B", "2", True),
                "(is(A, 1, True) OR is(B, 2, True))"
            ),
            (
                expression.andExpression((
                    expression.isExpression("A", "1", True),
                    expression.isExpression("B", "2", True),
                )),
                expression.isExpression("C", "3", True),
                "((is(A, 1, True) AND is(B, 2, True)) OR is(C, 3, True))"
            ),
            (
                expression.orExpression((
                    expression.isExpression("A", "1", True),
                )),
                expression.isExpression("B", "2", True),
                "(is(A, 1, True) OR is(B, 2, True))"
            ),
            (
                expression.orExpression((
                    expression.isExpression("A", "1", True),
                    expression.isExpression("B", "2", True),
                )),
                expression.isExpression("C", "3", True),
                "(is(A, 1, True) OR is(B, 2, True) OR is(C, 3, True))"
            ),
        )

        for expr1, expr2, result in tests:
            self.assertEqual(str(expr1.orWith(expr2)), result, msg="Failed on %s" % (result,))
