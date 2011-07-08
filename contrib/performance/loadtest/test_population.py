##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

"""
Tests for some things in L{loadtest.population}.
"""

from twisted.trial.unittest import TestCase

from loadtest.population import ReportStatistics

class ReportStatisticsTests(TestCase):
    """
    Tests for L{loadtest.population.ReportStatistics}.
    """
    def test_countUsers(self):
        """
        L{ReportStatistics.countUsers} returns the number of users observed to
        have acted in the simulation.
        """
        logger = ReportStatistics()
        users = ['user01', 'user02', 'user03']
        for user in users:
            logger.observe(dict(
                    type='response', method='GET', success=True,
                    duration=1.23, user=user))
        self.assertEqual(len(users), logger.countUsers())
