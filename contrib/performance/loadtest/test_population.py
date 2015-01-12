##
# Copyright (c) 2011-2015 Apple Inc. All rights reserved.
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
                duration=1.23, user=user, client_type="test", client_id="1234"
            ))
        self.assertEqual(len(users), logger.countUsers())


    def test_countClients(self):
        """
        L{ReportStatistics.countClients} returns the number of clients observed to
        have acted in the simulation.
        """
        logger = ReportStatistics()
        clients = ['c01', 'c02', 'c03']
        for client in clients:
            logger.observe(dict(
                type='response', method='GET', success=True,
                duration=1.23, user="user01", client_type="test", client_id=client
            ))
        self.assertEqual(len(clients), logger.countClients())


    def test_clientFailures(self):
        """
        L{ReportStatistics.countClientFailures} returns the number of clients observed to
        have failed in the simulation.
        """
        logger = ReportStatistics()
        clients = ['c01', 'c02', 'c03']
        for client in clients:
            logger.observe(dict(
                type='client-failure', reason="testing %s" % (client,)
            ))
        self.assertEqual(len(clients), logger.countClientFailures())


    def test_simFailures(self):
        """
        L{ReportStatistics.countSimFailures} returns the number of clients observed to
        have caused an error in the simulation.
        """
        logger = ReportStatistics()
        clients = ['c01', 'c02', 'c03']
        for client in clients:
            logger.observe(dict(
                type='sim-failure', reason="testing %s" % (client,)
            ))
        self.assertEqual(len(clients), logger.countSimFailures())


    def test_noFailures(self):
        """
        If fewer than 1% of requests fail, fewer than 1% of requests take 5
        seconds or more, and fewer than 5% of requests take 3 seconds or more,
        L{ReportStatistics.failures} returns an empty list.
        """
        logger = ReportStatistics()
        logger.observe(dict(
            type='response', method='GET', success=True,
            duration=2.5, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual([], logger.failures())


    def test_requestFailures(self):
        """
        If more than 1% of requests fail, L{ReportStatistics.failures} returns a
        list containing a string describing this.
        """
        logger = ReportStatistics()
        for _ignore in range(98):
            logger.observe(dict(
                type='response', method='GET', success=True,
                duration=2.5, user='user01', client_type="test", client_id="1234"
            ))
        logger.observe(dict(
            type='response', method='GET', success=False,
            duration=2.5, user='user01', client_type="test", client_id="1234"
        ))
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
        for _ignore in range(94):
            logger.observe(dict(
                type='response', method='GET', success=True,
                duration=2.5, user='user01', client_type="test", client_id="1234"
            ))
        for _ignore in range(5):
            logger.observe(dict(
                type='response', method='GET', success=True,
                duration=3.5, user='user02', client_type="test", client_id="1234"
            ))
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
        for _ignore in range(98):
            logger.observe(dict(
                type='response', method='GET', success=True,
                duration=2.5, user='user01', client_type="test", client_id="1234"
            ))
        logger.observe(dict(
            type='response', method='GET', success=True,
            duration=5.5, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual(
            ["Greater than 1% GET exceeded 5 second response time"],
            logger.failures())


    def test_methodsCountedSeparately(self):
        """
        The counts for one method do not affect the results of another method.
        """
        logger = ReportStatistics()
        for _ignore in range(99):
            logger.observe(dict(
                type='response', method='GET', success=True,
                duration=2.5, user='user01', client_type="test", client_id="1234"
            ))
            logger.observe(dict(
                type='response', method='POST', success=True,
                duration=2.5, user='user01', client_type="test", client_id="1234"
            ))

        logger.observe(dict(
            type='response', method='GET', success=False,
            duration=2.5, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='POST', success=False,
            duration=2.5, user='user01', client_type="test", client_id="1234"
        ))

        self.assertEqual([], logger.failures())


    def test_bucketRequest(self):
        """
        PUT(xxx-huge/large/medium/small} have different thresholds. Test that requests straddling
        each of those are correctly determined to be failures or not.
        """

        _thresholds = {
            "requests": {
                "limits": [0.1, 0.5, 1.0, 3.0, 5.0, 10.0, 30.0],
                "thresholds": {
                    "default": [100.0, 100.0, 100.0, 5.0, 1.0, 0.5, 0.0],
                    "PUT{organizer-small}": [100.0, 50.0, 25.0, 5.0, 1.0, 0.5, 0.0],
                    "PUT{organizer-medium}": [100.0, 100.0, 50.0, 25.0, 5.0, 1.0, 0.5],
                    "PUT{organizer-large}": [100.0, 100.0, 100.0, 50.0, 25.0, 5.0, 1.0],
                    "PUT{organizer-huge}": [100.0, 100.0, 100.0, 100.0, 100.0, 50.0, 25.0],
                }
            }
        }

        # -small below threshold
        logger = ReportStatistics(thresholds=_thresholds)
        logger.observe(dict(
            type='response', method='PUT{organizer-small}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-small}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-small}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-small}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual([], logger.failures())

        # -small above 0.5 threshold
        logger = ReportStatistics(thresholds=_thresholds)
        logger.observe(dict(
            type='response', method='PUT{organizer-small}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-small}', success=True,
            duration=0.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-small}', success=True,
            duration=0.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-small}', success=True,
            duration=0.6, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual(
            ["Greater than 50% PUT{organizer-small} exceeded 0.5 second response time"],
            logger.failures()
        )

        # -medium below 0.5 threshold
        logger = ReportStatistics(thresholds=_thresholds)
        logger.observe(dict(
            type='response', method='PUT{organizer-medium}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-medium}', success=True,
            duration=0.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-medium}', success=True,
            duration=0.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-medium}', success=True,
            duration=0.6, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual(
            [],
            logger.failures()
        )

        # -medium above 1.0 threshold
        logger = ReportStatistics(thresholds=_thresholds)
        logger.observe(dict(
            type='response', method='PUT{organizer-medium}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-medium}', success=True,
            duration=1.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-medium}', success=True,
            duration=1.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-medium}', success=True,
            duration=1.6, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual(
            ["Greater than 50% PUT{organizer-medium} exceeded 1 second response time"],
            logger.failures()
        )

        # -large below 1.0 threshold
        logger = ReportStatistics(thresholds=_thresholds)
        logger.observe(dict(
            type='response', method='PUT{organizer-large}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-large}', success=True,
            duration=1.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-large}', success=True,
            duration=1.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-large}', success=True,
            duration=1.6, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual(
            [],
            logger.failures()
        )

        # -large above 3.0 threshold
        logger = ReportStatistics(thresholds=_thresholds)
        logger.observe(dict(
            type='response', method='PUT{organizer-large}', success=True,
            duration=0.2, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-large}', success=True,
            duration=3.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-large}', success=True,
            duration=3.6, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-large}', success=True,
            duration=3.6, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual(
            ["Greater than 50% PUT{organizer-large} exceeded 3 second response time"],
            logger.failures()
        )

        # -huge below 10.0 threshold
        logger = ReportStatistics(thresholds=_thresholds)
        logger.observe(dict(
            type='response', method='PUT{organizer-huge}', success=True,
            duration=12.0, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-huge}', success=True,
            duration=8, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-huge}', success=True,
            duration=11.0, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-huge}', success=True,
            duration=9.0, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual(
            [],
            logger.failures()
        )

        # -huge above 10.0 threshold
        logger = ReportStatistics(thresholds=_thresholds)
        logger.observe(dict(
            type='response', method='PUT{organizer-huge}', success=True,
            duration=12.0, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-huge}', success=True,
            duration=9.0, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-huge}', success=True,
            duration=12.0, user='user01', client_type="test", client_id="1234"
        ))
        logger.observe(dict(
            type='response', method='PUT{organizer-huge}', success=True,
            duration=42.42, user='user01', client_type="test", client_id="1234"
        ))
        self.assertEqual(
            ["Greater than 50% PUT{organizer-huge} exceeded 10 second response time"],
            logger.failures()
        )
