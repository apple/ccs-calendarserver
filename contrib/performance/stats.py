
import sqlparse

NANO = 1000000000.0


def mean(samples):
    return sum(samples) / len(samples)


def median(samples):
    return sorted(samples)[len(samples) / 2]


def stddev(samples):
    m = mean(samples)
    variance = sum([(datum - m) ** 2 for datum in samples]) / len(samples)
    return variance ** 0.5


class _Statistic(object):
    commands = ['summarize']

    def __init__(self, name):
        self.name = name


    def summarize(self, data):
        print self.name, 'mean', mean(data)
        print self.name, 'median', median(data)
        print self.name, 'stddev', stddev(data)
        print self.name, 'sum', sum(data)


    def write(self, basename, data):
        fObj = file(basename % (self.name,), 'w')
        fObj.write('\n'.join(map(str, data)) + '\n')
        fObj.close()



class Duration(_Statistic):
    pass



class SQLDuration(_Statistic):
    commands = ['summarize', 'statements']

    def _substitute(self, expression, replacement):
        try:
            expression.tokens
        except AttributeError:
            return

        for i, token in enumerate(expression.tokens):
            if sqlparse.tokens.is_token_subtype(token.ttype, sqlparse.tokens.Literal):
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


    def summarize(self, data):
        statements = {}
        intervals = []
        for (sql, interval) in data:
            sql = self.normalize(sql)
            intervals.append(interval)
            statements[sql] = statements.get(sql, 0) + 1
        for statement, count in statements.iteritems():
            print count, ':', statement
        return _Statistic.summarize(self, intervals)


    def statements(self, data):
        statements = {}
        for (sql, interval) in data:
            sql = self.normalize(sql)
            statements.setdefault(sql, []).append(interval)
        
        byTime = []
        for statement, times in statements.iteritems():
            byTime.append((sum(times), statement))
        byTime.sort()
        byTime.reverse()

        for (time, statement) in byTime:
            print time / NANO * 1000, 'ms:', statement

class Bytes(_Statistic):
    pass
