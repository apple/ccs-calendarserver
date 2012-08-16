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
Tests for L{twext.enterprise.fixtures}.

Quis custodiet ipsos custodes?  This module, that's who.
"""

from twext.enterprise.fixtures import buildConnectionPool

from twisted.trial.unittest import TestCase
from twisted.trial.reporter import TestResult
from twext.enterprise.adbapi2 import ConnectionPool

class PoolTests(TestCase):
    """
    Tests for fixtures that create a connection pool.
    """

    def test_buildConnectionPool(self):
        """
        L{buildConnectionPool} returns a L{ConnectionPool} which will be
        running only for the duration of the test.
        """
        collect = []
        class SampleTest(TestCase):
            def setUp(self):
                self.pool = buildConnectionPool(self)
            def test_sample(self):
                collect.append(self.pool.running)
            def tearDown(self):
                collect.append(self.pool.running)
        r = TestResult()
        t = SampleTest("test_sample")
        t.run(r)
        self.assertIsInstance(t.pool, ConnectionPool)
        self.assertEqual([True, False], collect)
