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

from __future__ import print_function

from math import log, sqrt
from time import mktime
import random
import sqlparse

from pycalendar.datetime import DateTime
from pycalendar.duration import Duration as PyDuration
from pycalendar.icalendar.property import Property
from pycalendar.timezone import Timezone

from zope.interface import Interface, implements
from twisted.python.util import FancyEqMixin


NANO = 1000000000.0


def mean(samples):
    return sum(samples) / len(samples)



def median(samples):
    return sorted(samples)[len(samples) / 2]



def residuals(samples, from_):
    return [from_ - s for s in samples]



def stddev(samples):
    m = mean(samples)
    variance = sum([datum ** 2 for datum in residuals(samples, m)]) / len(samples)
    return variance ** 0.5



def mad(samples):
    """
    Return the median absolute deviation of the given data set.
    """
    med = median(samples)
    res = map(abs, residuals(samples, med))
    return median(res)



class _Statistic(object):
    commands = ['summarize']

    def __init__(self, name):
        self.name = name


    def __eq__(self, other):
        if isinstance(other, _Statistic):
            return self.name == other.name
        return NotImplemented


    def __hash__(self):
        return hash((self.__class__, self.name))


    def __repr__(self):
        return '<Stat %r>' % (self.name,)


    def squash(self, samples, mode=None):
        """
        Normalize the sample data into float values (one per sample)
        in seconds (I hope time is the only thing you measure).
        """
        return samples


    def summarize(self, data):
        return ''.join([
            self.name, ' mean ', str(mean(data)), '\n',
            self.name, ' median ', str(median(data)), '\n',
            self.name, ' stddev ', str(stddev(data)), '\n',
            self.name, ' median absolute deviation ', str(mad(data)), '\n',
            self.name, ' sum ', str(sum(data)), '\n'])


    def write(self, basename, data):
        fObj = file(basename % (self.name,), 'w')
        fObj.write('\n'.join(map(str, data)) + '\n')
        fObj.close()



class Duration(_Statistic):
    pass



class SQLDuration(_Statistic):
    commands = ['summarize', 'statements', 'transcript']

    def _is_literal(self, token):
        if token.ttype in sqlparse.tokens.Literal:
            return True
        if token.ttype == sqlparse.tokens.Keyword and token.value in (u'True', u'False'):
            return True
        return False


    def _substitute(self, expression, replacement):
        try:
            expression.tokens
        except AttributeError:
            return

        for i, token in enumerate(expression.tokens):
            if self._is_literal(token):
                expression.tokens[i] = replacement
            elif token.is_whitespace():
                expression.tokens[i] = sqlparse.sql.Token('Whitespace', ' ')
            else:
                self._substitute(token, replacement)


    def normalize(self, sql):
        (statement,) = sqlparse.parse(sql)
        # Replace any literal values with placeholders
        qmark = sqlparse.sql.Token('Operator', '?')
        self._substitute(statement, qmark)
        return sqlparse.format(statement.to_unicode().encode('ascii'))


    def squash(self, samples, mode="duration"):
        """
        Summarize the execution of a number of SQL statements.

        @param mode: C{"duration"} to squash the durations into the
            result.  C{"count"} to squash the count of statements
            executed into the result.
        """
        results = []
        for data in samples:
            if mode == "duration":
                value = sum([interval for (_ignore_sql, interval) in data]) / NANO
            else:
                value = len(data)
            results.append(value)
        return results


    def summarize(self, samples):
        times = []
        statements = {}
        for data in samples:
            total = 0
            for (sql, interval) in data:
                sql = self.normalize(sql)
                statements[sql] = statements.get(sql, 0) + 1
                total += interval
            times.append(total / NANO * 1000)
        return ''.join([
            '%d: %s\n' % (count, statement)
            for (statement, count)
            in statements.iteritems()]) + _Statistic.summarize(self, times)


    def statements(self, samples):
        statements = {}
        for data in samples:
            for (sql, interval) in data:
                sql = self.normalize(sql)
                statements.setdefault(sql, []).append(interval)

        byTime = []
        for statement, times in statements.iteritems():
            byTime.append((sum(times), len(times), statement))
        byTime.sort()
        byTime.reverse()

        if byTime:
            header = '%10s %10s %10s %s'
            row = '%10.5f %10.5f %10d %s'
            print(header % ('TOTAL MS', 'PERCALL MS', 'NCALLS', 'STATEMENT'))
            for (time, count, statement) in byTime:
                time = time / NANO * 1000
                print(row % (time, time / count, count, statement))


    def transcript(self, samples):
        statements = []
        data = samples[len(samples) / 2]
        for (sql, _ignore_interval) in data:
            statements.append(self.normalize(sql))
        return '\n'.join(statements) + '\n'



class Bytes(_Statistic):
    def squash(self, samples):
        return [sum(bytes) for bytes in samples]


    def summarize(self, samples):
        return _Statistic.summarize(self, self.squash(samples))



def quantize(data):
    """
    Given some continuous data, quantize it into appropriately sized
    discrete buckets (eg, as would be suitable for constructing a
    histogram of the values).
    """
    # buckets = {}
    return []



class IPopulation(Interface):
    def sample(): #@NoSelf
        pass



class UniformDiscreteDistribution(object, FancyEqMixin):
    """

    """
    implements(IPopulation)

    compareAttributes = ['_values']

    def __init__(self, values, randomize=True):
        self._values = values
        self._randomize = randomize
        self._refill()


    def _refill(self):
        self._remaining = self._values[:]
        if self._randomize:
            random.shuffle(self._remaining)


    def sample(self):
        if not self._remaining:
            self._refill()
        return self._remaining.pop()



class LogNormalDistribution(object, FancyEqMixin):
    """
    """
    implements(IPopulation)

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
            for _ignore in range(10):
                result = self._scale * random.lognormvariate(self._mu, self._sigma)
                if result <= self._maximum:
                    break
            else:
                raise ValueError("Unable to generate LogNormalDistribution sample within required range")
        return result



class FixedDistribution(object, FancyEqMixin):
    """
    """
    implements(IPopulation)

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
    mu = 1.5
    sigma = 1.22
    distribution = LogNormalDistribution(mu, sigma, 100)
    result = defaultdict(int)
    for i in range(100000):
        s = int(distribution.sample())
        if s > 300:
            continue
        result[s] += 1

    total = 0
    for k, v in sorted(result.items(), key=lambda x: x[0]):
        print("%d\t%.5f" % (k, float(v) / result[1]))
        total += k * v

    print("Average: %.2f" % (float(total) / sum(result.values()),))
