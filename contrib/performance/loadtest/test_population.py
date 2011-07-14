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

from contrib.performance.loadtest.population import ReportStatistics

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


    def test_noFailures(self):
        """
        If fewer than 1% of requests fail, fewer than 1% of requests take 5
        seconds or more, and fewer than 5% of requests take 3 seconds or more,
        L{ReportStatistics.failures} returns an empty list.
        """
        logger = ReportStatistics()
        logger.observe(dict(
                type='response', method='GET', success=True,
                duration=2.5, user='user01'))
        self.assertEqual([], logger.failures())


    def test_requestFailures(self):
        """
        If more than 1% of requests fail, L{ReportStatistics.failures} returns a
        list containing a string describing this.
        """
        logger = ReportStatistics()
        for i in range(98):
            logger.observe(dict(
                    type='response', method='GET', success=True,
                    duration=2.5, user='user01'))
        logger.observe(dict(
                type='response', method='GET', success=False,
                duration=2.5, user='user01'))
        self.assertEqual(
            ["Greater than 1% GET failed"],
            logger.failures())


    def test_threeSecondFailure(self):
        """
        If more than 5% of requests take longer than 3 seconds,
        L{ReportStatistics.failures} returns a list containing a string
        describing that.
        """
        logger = ReportStatistics()
        for i in range(94):
            logger.observe(dict(
                    type='response', method='GET', success=True,
                    duration=2.5, user='user01'))
        for i in range(5):
            logger.observe(dict(
                    type='response', method='GET', success=True,
                    duration=3.5, user='user02'))
        self.assertEqual(
            ["Greater than 5% GET exceeded 3 second response time"],
            logger.failures())


    def test_fiveSecondFailure(self):
        """
        If more than 1% of requests take longer than 5 seconds,
        L{ReportStatistics.failures} returns a list containing a string
        describing that.
        """
        logger = ReportStatistics()
        for i in range(98):
            logger.observe(dict(
                    type='response', method='GET', success=True,
                    duration=2.5, user='user01'))
        logger.observe(dict(
                type='response', method='GET', success=True,
                duration=5.5, user='user01'))
        self.assertEqual(
            ["Greater than 1% GET exceeded 5 second response time"],
            logger.failures())


    def test_methodsCountedSeparately(self):
        """
        The counts for one method do not affect the results of another method.
        """
        logger = ReportStatistics()
        for i in range(99):
            logger.observe(dict(
                    type='response', method='GET', success=True,
                    duration=2.5, user='user01'))
            logger.observe(dict(
                    type='response', method='POST', success=True,
                    duration=2.5, user='user01'))

        logger.observe(dict(
                type='response', method='GET', success=False,
                duration=2.5, user='user01'))
        logger.observe(dict(
                type='response', method='POST', success=False,
                duration=2.5, user='user01'))

        self.assertEqual([], logger.failures())
