##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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
Tests for L{twext.python.parallel}.
"""

from twisted.internet.defer import Deferred

from twext.python.parallel import Parallelizer

from twisted.trial.unittest import TestCase

class ParallelizerTests(TestCase):
    """
    Tests for L{Parallelizer}.
    """

    def test_doAndDone(self):
        """
        Blanket catch-all test.  (TODO: split this up into more nice
        fine-grained tests.)
        """
        d1 = Deferred()
        d2 = Deferred()
        d3 = Deferred()
        d4 = Deferred()
        doing = []
        done = []
        allDone = []
        p = Parallelizer(['a', 'b', 'c'])
        p.do(lambda a: doing.append(a) or d1).addCallback(done.append)
        p.do(lambda b: doing.append(b) or d2).addCallback(done.append)
        p.do(lambda c: doing.append(c) or d3).addCallback(done.append)
        p.do(lambda b1: doing.append(b1) or d4).addCallback(done.append)
        p.done().addCallback(allDone.append)
        self.assertEqual(allDone, [])
        self.assertEqual(doing, ['a', 'b', 'c'])
        self.assertEqual(done, [None, None, None])
        d2.callback(1)
        self.assertEqual(doing, ['a', 'b', 'c', 'b'])
        self.assertEqual(done, [None, None, None, None])
        self.assertEqual(allDone, [])
        d3.callback(2)
        d4.callback(3)
        d1.callback(4)
        self.assertEqual(done, [None, None, None, None])
        self.assertEqual(allDone, [None])


