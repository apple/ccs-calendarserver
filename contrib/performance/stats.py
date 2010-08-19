
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

    def summarize(self, data):
        statements = {}
        intervals = []
        for (sql, interval) in data:
            intervals.append(interval)
            statements[sql] = statements.get(sql, 0) + 1
        for statement, count in statements.iteritems():
            print count, ':', statement.replace('\n', ' ')
        return _Statistic.summarize(self, intervals)


    def statements(self, data):
        statements = {}
        for (sql, interval) in data:
            statements.setdefault(sql, []).append(interval)
        
        byTime = []
        for statement, times in statements.iteritems():
            byTime.append((sum(times), statement))
        byTime.sort()
        byTime.reverse()

        for (time, statement) in byTime:
            print time / NANO * 1000, 'ms:', statement.replace('\n', ' ')

class Bytes(_Statistic):
    pass
