##
# Copyright (c) 2010 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from twisted.trial.unittest import TestCase

from stats import (
    SQLDuration, LogNormalDistribution, UniformDiscreteDistribution,
    UniformIntegerDistribution, WorkDistribution, quantize)
from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone

class SQLDurationTests(TestCase):
    def setUp(self):
        self.stat = SQLDuration('foo')


    def test_normalize_integer(self):
        self.assertEquals(
            self.stat.normalize('SELECT foo FROM bar WHERE 1'),
            'SELECT foo FROM bar WHERE ?')
        self.assertEquals(
            self.stat.normalize('SELECT foo FROM bar WHERE x = 1'),
            'SELECT foo FROM bar WHERE x = ?')
        self.assertEquals(
            self.stat.normalize('SELECT foo + 1 FROM bar'),
            'SELECT foo + ? FROM bar')


    def test_normalize_boolean(self):
        self.assertEquals(
            self.stat.normalize('SELECT foo FROM bar WHERE True'),
            'SELECT foo FROM bar WHERE ?')



class DistributionTests(TestCase):
    def test_lognormal(self):
        dist = LogNormalDistribution(1, 1)
        for _ignore_i in range(100):
            value = dist.sample()
            self.assertIsInstance(value, float)
            self.assertTrue(value >= 0.0, "negative value %r" % (value,))
            self.assertTrue(value <= 1000, "implausibly high value %r" % (value,))


    def test_uniformdiscrete(self):
        population = [1, 5, 6, 9]
        counts = dict.fromkeys(population, 0)
        dist = UniformDiscreteDistribution(population)
        for _ignore_i in range(len(population) * 10):
            counts[dist.sample()] += 1
        self.assertEqual(dict.fromkeys(population, 10), counts)


    def test_workdistribution(self):
        tzname = "US/Eastern"
        dist = WorkDistribution(["mon", "wed", "thu", "sat"], 10, 20, tzname)
        dist._helperDistribution = UniformDiscreteDistribution([35 * 60 * 60 + 30 * 60])
        dist.now = lambda tzname=None: PyCalendarDateTime(2011, 5, 29, 18, 5, 36, tzid=tzname)
        value = dist.sample()
        self.assertEqual(
            # Move past three workdays - monday, wednesday, thursday - using 30
            # of the hours, and then five and a half hours into the fourth
            # workday, saturday.  Workday starts at 10am, so the sample value
            # is 3:30pm, ie 1530 hours.
            PyCalendarDateTime(2011, 6, 4, 15, 30, 0, tzid=PyCalendarTimezone(tzid=tzname)),
            value
        )

        dist = WorkDistribution(["mon", "tue", "wed", "thu", "fri"], 10, 20, tzname)
        dist._helperDistribution = UniformDiscreteDistribution([35 * 60 * 60 + 30 * 60])
        value = dist.sample()
        self.assertTrue(isinstance(value, PyCalendarDateTime))

    # twisted.trial.unittest.FailTest: not equal:
    # a = datetime.datetime(2011, 6, 4, 15, 30, tzinfo=<DstTzInfo 'US/Eastern' EST-1 day, 19:00:00 STD>)
    # b = datetime.datetime(2011, 6, 4, 19, 30, tzinfo=<DstTzInfo 'US/Eastern' EDT-1 day, 20:00:00 DST>)
    #test_workdistribution.todo = "Somehow timezones mess this up"


    def test_uniform(self):
        dist = UniformIntegerDistribution(-5, 10)
        for _ignore_i in range(100):
            value = dist.sample()
            self.assertTrue(-5 <= value < 10)
            self.assertIsInstance(value, int)



class QuantizationTests(TestCase):
    """
    Tests for L{quantize} which constructs discrete datasets of
    dynamic quantization from continuous datasets.
    """
    skip = "nothing implemented yet, maybe not necessary"

    def test_one(self):
        """
        A single data point is put into a bucket equal to its value and returned.
        """
        dataset = [5.0]
        expected = [(5.0, [5.0])]
        self.assertEqual(quantize(dataset), expected)


    def test_two(self):
        """
        Each of two values are put into buckets the size of the
        standard deviation of the sample.
        """
        dataset = [2.0, 5.0]
        expected = [(1.5, [2.0]), (4.5, [5.0])]
        self.assertEqual(quantize(dataset), expected)


    def xtest_three(self):
        """
        If two out of three values fall within one bucket defined by
        the standard deviation of the sample, that bucket is split in
        half so each bucket has one value.
        """


    def xtest_alpha(self):
        """
        This exercises one simple case of L{quantize} with a small amount of data.
        """
