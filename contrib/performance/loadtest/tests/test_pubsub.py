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
Tests for loadtest.pubsub
"""
from collections import defaultdict

from twisted.trial.unittest import TestCase

from contrib.performance.loadtest.pubsub import Publisher


class PubSubTests(TestCase):
    """Tests for Publisher"""
    def setUp(self):
        self.publisher = Publisher()
        # Maps IDs of subscribers to values issued
        self.values = defaultdict(list)


    def recordValueWithID(self, id):
        """
        Return a one-argument callable for use as a subscriber
        that appends its argument to the list of values associated with id
        """
        def recordValue(value):
            self.values[id].append(value)
        return recordValue


    def test_noSubscribers(self):
        """When no subscriptions are present, no value is published"""
        value = 'foobar'
        self.publisher.issue(value)
        self.assertEqual(self.values['sub1'], [])


    def test_subscribe(self):
        """Published values propagate to their subscribers"""
        value = 'foobar'
        self.publisher.subscribe(self.recordValueWithID('sub1'))
        self.publisher.issue(value)
        self.assertEqual(self.values['sub1'], [value])


    def test_cancel(self):
        """Cancelled subscriptions do not receive new publications"""
        value = 'foobar'
        subscr = self.publisher.subscribe(self.recordValueWithID('sub1'))
        subscr.cancel()
        self.publisher.issue(value)
        self.assertEqual(self.values['sub1'], [])


    def test_multiple_subscriptions(self):
        """Publisher supports adding and removing multiple subscriptions"""
        value = 'foobar'
        subscr1 = self.publisher.subscribe(self.recordValueWithID('sub1'))
        subscr2 = self.publisher.subscribe(self.recordValueWithID('sub2'))
        self.publisher.issue(value)
        self.assertEqual(self.values['sub1'], [value])
        self.assertEqual(self.values['sub2'], [value])

        subscr2.cancel()
        self.publisher.issue(value)
        self.assertEqual(self.values['sub1'], [value, value])
        self.assertEqual(self.values['sub2'], [value])

        subscr1.cancel()
        self.publisher.issue(value)
        self.assertEqual(self.values['sub1'], [value, value])
        self.assertEqual(self.values['sub2'], [value])
