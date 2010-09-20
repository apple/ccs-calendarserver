
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


    def squash(self, samples):
        """
        Normalize the sample data into float values (one per sample)
        in seconds (I hope time is the only thing you measure).
        """
        return samples


    def summarize(self, data):
        print self.name, 'mean', mean(data)
        print self.name, 'median', median(data)
        print self.name, 'stddev', stddev(data)
        print self.name, 'median absolute deviation', mad(data)
        print self.name, 'sum', sum(data)


    def write(self, basename, data):
        fObj = file(basename % (self.name,), 'w')
        fObj.write('\n'.join(map(str, data)) + '\n')
        fObj.close()



class Duration(_Statistic):
    pass



class SQLDuration(_Statistic):
    commands = ['summarize', 'statements']

    def _is_literal(self, token):
        if sqlparse.tokens.is_token_subtype(token.ttype, sqlparse.tokens.Literal):
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


    def squash(self, samples):
        times = []
        for data in samples:
            times.append(
                sum([interval for (sql, interval) in data]) / NANO)
        return times


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
        for statement, count in statements.iteritems():
            print count, ':', statement
        return _Statistic.summarize(self, times)


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


class Bytes(_Statistic):
    def squash(self, samples):
        return [sum(bytes) for bytes in samples]


    def summarize(self, samples):
        return _Statistic.summarize(self, self.squash(samples))
