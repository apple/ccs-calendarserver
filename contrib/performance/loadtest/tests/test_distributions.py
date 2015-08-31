from twisted.trial.unittest import TestCase

from contrib.performance.loadtest.distributions import (
    # Continuous distributions
    LogNormalDistribution, NormalDistribution,
    # Discrete distributions
    UniformDiscreteDistribution, UniformIntegerDistribution,
    BernoulliDistribution, BinomialDistribution, FixedDistribution,
    # Calendar-specific distributions
    WorkDistribution, RecurrenceDistribution,
)

from pycalendar.datetime import DateTime
from pycalendar.timezone import Timezone

from scipy import stats
from scipy.optimize import curve_fit
import itertools

"""
Disclaimer: These tests are nondeterministic, so be careful
"""

class DistributionTestBase(TestCase):
    def get_n_samples(self, dist, n):
        samples = []
        for _ignore_i in xrange(n):
            samples.append(dist.sample())
        return samples

class DiscreteDistributionTests(DistributionTestBase):
    def test_bernoulli(self):
        sample_count = 1000
        proportions = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]
        for prop in proportions:
            dist = BernoulliDistribution(proportion=prop)
            samples = self.get_n_samples(dist, sample_count)
            successes = samples.count(True)

            # This representes the likelihood that we would see as many successes
            # as we did given that the true proportion is prop
            p_value = stats.binom_test(successes, n=sample_count, p=prop)
            self.assertFalse(p_value <= 0.01, "%d/%d, expected %f" % (successes, sample_count, prop))

    def test_binomial(self):
        sample_counts = [100, 1000, 10000]
        proportions = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]
        for sample_count, prop in itertools.product(sample_counts, proportions):
            dist = BinomialDistribution(p=prop, n=sample_count)
            successes = dist.sample()

            # This representes the likelihood that we would see as many successes
            # as we did given that the true proportion is prop
            p_value = stats.binom_test(successes, n=sample_count, p=prop)
            self.assertFalse(p_value <= 0.01, "%d/%d, expected %f" % (successes, sample_count, prop))

    def test_fixed(self):
        dist = FixedDistribution(4) # https://xkcd.com/221/
        for _ignore_i in xrange(100):
            self.assertEqual(dist.sample(), 4)

    def test_uniformdiscrete(self):
        population = [82, 101, 100, 109, 111, 110, 100]
        counts = dict.fromkeys(population, 0)
        dist = UniformDiscreteDistribution(population)
        for _ignore_i in range(len(population) * 10):
            counts[dist.sample()] += 1
        self.assertEqual(dict.fromkeys(population, 10), counts)
        # Do some chi squared stuff

    def test_uniform(self):
        dist = UniformIntegerDistribution(-5, 10)
        for _ignore_i in range(100):
            value = dist.sample()
            self.assertTrue(-5 <= value < 10)
            self.assertIsInstance(value, int)

class ContinuousDistributionTests(TestCase):
    def is_fit(self, pdf, xdata, ydata, pexp):
        """
        expected parameters
        """
        popt, pcov = curve_fit(pdf, xdata, ydata)
        print popt

    def test_normal(self):
        dist = NormalDistribution()

    def test_lognormal(self):
        dist = LogNormalDistribution(mu=1, sigma=1)
        for _ignore_i in range(100):
            value = dist.sample()
            self.assertIsInstance(value, float)
            self.assertTrue(value >= 0.0, "negative value %r" % (value,))
            self.assertTrue(value <= 1000, "implausibly high value %r" % (value,))

        dist = LogNormalDistribution(mode=1, median=2)
        for _ignore_i in range(100):
            value = dist.sample()
            self.assertIsInstance(value, float)
            self.assertTrue(value >= 0.0, "negative value %r" % (value,))
            self.assertTrue(value <= 1000, "implausibly high value %r" % (value,))

        dist = LogNormalDistribution(mode=1, mean=2)
        for _ignore_i in range(100):
            value = dist.sample()
            self.assertIsInstance(value, float)
            self.assertTrue(value >= 0.0, "negative value %r" % (value,))
            self.assertTrue(value <= 1000, "implausibly high value %r" % (value,))

        self.assertRaises(ValueError, LogNormalDistribution, mu=1)
        self.assertRaises(ValueError, LogNormalDistribution, sigma=1)
        self.assertRaises(ValueError, LogNormalDistribution, mode=1)
        self.assertRaises(ValueError, LogNormalDistribution, mean=1)
        self.assertRaises(ValueError, LogNormalDistribution, median=1)

class CalendarDistributionTests(TestCase):

    def test_workdistribution(self):
        tzname = "US/Eastern"
        dist = WorkDistribution(["mon", "wed", "thu", "sat"], 10, 20, tzname)
        dist._helperDistribution = UniformDiscreteDistribution([35 * 60 * 60 + 30 * 60])
        dist.now = lambda tzname = None: DateTime(2011, 5, 29, 18, 5, 36, tzid=tzname)
        value = dist.sample()
        self.assertEqual(
            # Move past three workdays - monday, wednesday, thursday - using 30
            # of the hours, and then five and a half hours into the fourth
            # workday, saturday.  Workday starts at 10am, so the sample value
            # is 3:30pm, ie 1530 hours.
            DateTime(2011, 6, 4, 15, 30, 0, tzid=Timezone(tzid=tzname)),
            value
        )

        dist = WorkDistribution(["mon", "tue", "wed", "thu", "fri"], 10, 20, tzname)
        dist._helperDistribution = UniformDiscreteDistribution([35 * 60 * 60 + 30 * 60])
        value = dist.sample()
        self.assertTrue(isinstance(value, DateTime))

    # twisted.trial.unittest.FailTest: not equal:
    # a = datetime.datetime(2011, 6, 4, 15, 30, tzinfo=<DstTzInfo 'US/Eastern' EST-1 day, 19:00:00 STD>)
    # b = datetime.datetime(2011, 6, 4, 19, 30, tzinfo=<DstTzInfo 'US/Eastern' EDT-1 day, 20:00:00 DST>)
    # test_workdistribution.todo = "Somehow timezones mess this up"


    def test_recurrencedistribution(self):
        dist = RecurrenceDistribution(False)
        for _ignore in range(100):
            value = dist.sample()
            self.assertTrue(value is None)

        dist = RecurrenceDistribution(True, {"daily": 1, "none": 2, "weekly": 1})
        dist._helperDistribution = UniformDiscreteDistribution([0, 3, 2, 1, 0])
        value = dist.sample()
        self.assertTrue(value is not None)
        value = dist.sample()
        self.assertTrue(value is None)
        value = dist.sample()
        self.assertTrue(value is None)
        value = dist.sample()
        self.assertTrue(value is not None)
        value = dist.sample()
        self.assertTrue(value is not None)
