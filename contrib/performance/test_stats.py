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

from stats import SQLDuration, LogNormalDistribution, UniformDiscreteDistribution, quantize

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
        for i in range(100):
            value = dist.sample()
            self.assertIsInstance(value, float)
            self.assertTrue(value >= 0.0, "negative value %r" % (value,))
            self.assertTrue(value <= 1000, "implausibly high value %r" % (value,))


    def test_uniformdiscrete(self):
        population = [1, 5, 6, 9]
        counts = dict.fromkeys(population, 0)
        dist = UniformDiscreteDistribution(population)
        for i in range(len(population) * 10):
            counts[dist.sample()] += 1
        self.assertEqual(dict.fromkeys(population, 10), counts)



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
