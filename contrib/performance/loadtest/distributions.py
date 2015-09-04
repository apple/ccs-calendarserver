##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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

"""
Implementation of a statistics library for Calendar performance analysis.
Exports:

IDistribution interface exposes:
  sample()

Sampling from this distribution must *not* change the underlying behavior of a distribution

Distributions (all of which implement IDistribution):
  # Discrete Distributions / Finite Support
  Bernoulli
  Binomial
  Rademacher
  Fixed
  UniformDiscrete
  UniformInteger

  # Discrete Distributions / Infinite Support (> 0)
  Poisson
  Geometric

  LogNormal

  Normal
  UniformReal
  Triangular
  Beta
  ChiSquared
  Exponential
  Gamma

  # CalendarServer Specific
  NearFuture
  Work
  Recurrence

# TODO
Implement simple ones through large ones
Squeeze / pinch
"""
from math import log, sqrt
from time import mktime
import random
import numpy.random as nprandom

from pycalendar.datetime import DateTime
from pycalendar.duration import Duration as PyDuration
from pycalendar.icalendar.property import Property
from pycalendar.timezone import Timezone

from zope.interface import Interface, implements
from twisted.python.util import FancyEqMixin


class IDistribution(Interface):
    """Interface for a class that provides a single function, `sample`, which returns a float"""
    def sample(): #@NoSelf
        pass


class UniformDiscreteDistribution(object, FancyEqMixin):
    """

    """
    implements(IDistribution)

    compareAttributes = ['_values']

    def __init__(self, values):
        self._values = values

    def sample(self):
        return random.choice(self._values)



class LogNormalDistribution(object, FancyEqMixin):
    """
    """
    implements(IDistribution)

    compareAttributes = ['_mu', '_sigma', '_maximum']

    def __init__(self, mu=None, sigma=None, mean=None, mode=None, median=None, maximum=None):

        if mu is not None and sigma is not None:
            scale = 1.0
        elif not (mu is None and sigma is None):
            raise ValueError("mu and sigma must both be defined or both not defined")
        elif mode is None:
            raise ValueError("When mu and sigma are not defined, mode must be defined")
        elif median is not None:
            scale = mode
            median /= mode
            mode = 1.0
            mu = log(median)
            sigma = sqrt(log(median) - log(mode))
        elif mean is not None:
            scale = mode
            mean /= mode
            mode = 1.0
            mu = log(mean) + log(mode) / 2.0
            sigma = sqrt(log(mean) - log(mode) / 2.0)
        else:
            raise ValueError("When using mode one of median or mean must be defined")

        self._mu = mu
        self._sigma = sigma
        self._scale = scale
        self._maximum = maximum


    def sample(self):
        result = self._scale * random.lognormvariate(self._mu, self._sigma)
        if self._maximum is not None and result > self._maximum:
            for _ignore_i in range(10):
                result = self._scale * random.lognormvariate(self._mu, self._sigma)
                if result <= self._maximum:
                    break
            else:
                raise ValueError("Unable to generate LogNormalDistribution sample within required range")
        return result



class FixedDistribution(object, FancyEqMixin):
    """
    """
    implements(IDistribution)

    compareAttributes = ['_value']

    def __init__(self, value):
        self._value = value


    def sample(self):
        return self._value



class NearFutureDistribution(object, FancyEqMixin):
    compareAttributes = ['_offset']

    def __init__(self):
        self._offset = LogNormalDistribution(7, 0.8)


    def sample(self):
        now = DateTime.getNowUTC()
        now.offsetSeconds(int(self._offset.sample()))
        return now



class NormalDistribution(object, FancyEqMixin):
    compareAttributes = ['_mu', '_sigma']

    def __init__(self, mu, sigma):
        self._mu = mu
        self._sigma = sigma


    def sample(self):
        # Only return positive values or zero
        v = random.normalvariate(self._mu, self._sigma)
        while v < 0:
            v = random.normalvariate(self._mu, self._sigma)
        return v



class UniformIntegerDistribution(object, FancyEqMixin):
    compareAttributes = ['_min', '_max']

    def __init__(self, min, max):
        self._min = min
        self._max = max


    def sample(self):
        return int(random.uniform(self._min, self._max))


class UniformRealDistribution(object, FancyEqMixin):
    compareAttributes = ['_min', '_max']

    def __init__(self, min, max):
        self._min = min
        self._max = max


    def sample(self):
        return random.uniform(self._min, self._max)


class BernoulliDistribution(object, FancyEqMixin):
    compareAttributes = ["_p"]

    def __init__(self, proportion=0.5):
        """Initializes a bernoulli distribution with success probability given by p
        Prereq: 0 <= p <= 1
        Returns 1 with probability p, 0 with probability q = 1-p
        """
        self._p = proportion

    def sample(self):
        return 1 if random.random() <= self._p else 0


class RademacherDistribution(object, FancyEqMixin):
    """
    Takes value 1 with probability 1/2 and value -1 with probability 1/2
    """
    def __init__(self):
        """
        """
        self._d = BernoulliDistribution(proportion=0.5)

    def sample(self):
        return [-1, 1][self._d.sample()]



class BinomialDistribution(object, FancyEqMixin):
    compareAttributes = ["_successProbability", "_numTrials"]

    def __init__(self, p=0.5, n=10):
        self._successProbability = p
        self._numTrials = n

    def sample(self):
        return nprandom.binomial(self._numTrials, self._successProbability)



class TriangularDistribution(object, FancyEqMixin):
    compareAttributes = ["_left", "_mode", "_right"]

    def __init__(self, left, mode, right):
        self._left = left
        self._mode = mode
        self._right = right

    def sample(self):
        return nprandom.triangular(self._left, self._mode, self._right)


class GeometricDistribution(object, FancyEqMixin):
    """
    Expected number of Bernoulli trials before the first success
    """
    compareAttributes = ["_p"]
    def __init__(self, proportion=0.5):
        self._p = proportion

    def sample(self):
        return nprandom.geometric(self._p)


class PoissonDistribution(object, FancyEqMixin):
    compareAttributes = ["_lambda"]
    def __init__(self, lam):
        self._lambda = lam

    def sample(self):
        return nprandom.possion(self._lambda)


class BetaDistribution(object, FancyEqMixin):
    compareAttributes = ["_alpha", "_beta"]
    def __init__(self, alpha, beta):
        self._alpha = alpha
        self._beta = beta

    def sample(self):
        return nprandom.beta(self._alpha, self._beta)


class ChiSquaredDistribution(object, FancyEqMixin):
    compareAttributes = ["_df"]
    def __init__(self, degreesOfFreedom):
        self._df = degreesOfFreedom

    def sample(self):
        return nprandom.chisquare(self._df)


class ExponentialDistribution(object, FancyEqMixin):
    compareAttributes = ["_scale"]
    def __init__(self, scale):
        self._scale = scale

    def sample(self):
        return nprandom.exponential(self._scale)



class GammaDistribution(object, FancyEqMixin):
    compareAttributes = ["_shape", "_scale"]
    def __init__(self, shape, scale=1.0):
        self._shape = shape
        self._scale = scale

    def sample(self):
        return nprandom.gamma(self._shape, self._scale)

NUM_WEEKDAYS = 7

class WorkDistribution(object, FancyEqMixin):
    compareAttributes = ["_daysOfWeek", "_beginHour", "_endHour"]

    _weekdayNames = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]

    def __init__(self, daysOfWeek=["mon", "tue", "wed", "thu", "fri"], beginHour=8, endHour=17, tzname="UTC"):
        self._daysOfWeek = [self._weekdayNames.index(day) for day in daysOfWeek]
        self._beginHour = beginHour
        self._endHour = endHour
        self._tzname = tzname
        self._helperDistribution = NormalDistribution(
            # Mean 6 workdays in the future
            60 * 60 * 8 * 6,
            # Standard deviation of 4 workdays
            60 * 60 * 8 * 4)
        self.now = DateTime.getNow


    def astimestamp(self, dt):
        return mktime(dt.timetuple())


    def _findWorkAfter(self, when):
        """
        Return a two-tuple of the start and end of work hours following
        C{when}.  If C{when} falls within work hours, then the start time will
        be equal to when.
        """
        # Find a workday that follows the timestamp
        weekday = when.getDayOfWeek()
        for i in range(NUM_WEEKDAYS):
            day = when + PyDuration(days=i)
            if (weekday + i) % NUM_WEEKDAYS in self._daysOfWeek:
                # Joy, a day on which work might occur.  Find the first hour on
                # this day when work may start.
                day.setHHMMSS(self._beginHour, 0, 0)
                begin = day
                end = begin.duplicate()
                end.setHHMMSS(self._endHour, 0, 0)
                if end > when:
                    return begin, end


    def sample(self):
        offset = PyDuration(seconds=int(self._helperDistribution.sample()))
        beginning = self.now(Timezone(tzid=self._tzname))
        while offset:
            start, end = self._findWorkAfter(beginning)
            if end - start > offset:
                result = start + offset
                result.setMinutes(result.getMinutes() // 15 * 15)
                result.setSeconds(0)
                return result
            offset.setDuration(offset.getTotalSeconds() - (end - start).getTotalSeconds())
            beginning = end



class RecurrenceDistribution(object, FancyEqMixin):
    compareAttributes = ["_allowRecurrence", "_weights"]

    _model_rrules = {
        "none": None,
        "daily": "RRULE:FREQ=DAILY",
        "weekly": "RRULE:FREQ=WEEKLY",
        "monthly": "RRULE:FREQ=MONTHLY",
        "yearly": "RRULE:FREQ=YEARLY",
        "dailylimit": "RRULE:FREQ=DAILY;COUNT=14",
        "weeklylimit": "RRULE:FREQ=WEEKLY;COUNT=4",
        "workdays": "RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"
    }

    def __init__(self, allowRecurrence, weights={}):
        self._allowRecurrence = allowRecurrence
        self._rrules = []
        if self._allowRecurrence:
            for rrule, count in sorted(weights.items(), key=lambda x: x[0]):
                for _ignore in range(count):
                    self._rrules.append(self._model_rrules[rrule])
        self._helperDistribution = UniformIntegerDistribution(0, len(self._rrules) - 1)


    def sample(self):

        if self._allowRecurrence:
            index = self._helperDistribution.sample()
            rrule = self._rrules[index]
            if rrule:
                prop = Property.parseText(rrule)
                return prop

        return None

if __name__ == '__main__':
    from collections import defaultdict
    mu = 15
    sigma = 12
    print("Testing LogNormalDistribution with mu={mu}, sigma={sigma}".format(
        mu=mu, sigma=sigma
    ))
    distribution = LogNormalDistribution(mu, sigma, 100)
    result = defaultdict(int)
    for _ignore_i in xrange(100000):
        s = int(distribution.sample())
        if s > 300:
            continue
        result[s] += 1

    total = 0
    for k, v in sorted(result.items(), key=lambda x: x[0]):
        print("%d\t%.5f" % (k, float(v) / result[1]))
        total += k * v

    print("Average: %.2f" % (float(total) / sum(result.values()),))
