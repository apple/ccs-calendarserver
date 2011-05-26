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

import sqlparse

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
                value = sum([interval for (sql, interval) in data]) / NANO
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
            print header % ('TOTAL MS', 'PERCALL MS', 'NCALLS', 'STATEMENT')
            for (time, count, statement) in byTime:
                time = time / NANO * 1000
                print row % (time, time / count, count, statement)


    def transcript(self, samples):
        statements = []
        data = samples[len(samples) / 2]
        for (sql, interval) in data:
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
    buckets = {}
    return []
