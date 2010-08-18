import sys, pickle


def main():
    statistics = pickle.load(file(sys.argv[1]))

    if len(sys.argv) == 2:
        print 'Available benchmarks'
        print '\t' + '\n\t'.join(statistics.keys())
        return

    statistics = statistics[sys.argv[2]]

    if len(sys.argv) == 3:
        print 'Available parameters'
        print '\t' + '\n\t'.join(map(str, statistics.keys()))
        return

    statistics = statistics[int(sys.argv[3])]

    if len(sys.argv) == 4:
        print 'Available statistics'
        print '\t' + '\n\t'.join([s.name for s in statistics])
        return

    for stat in statistics:
        if stat.name == sys.argv[4]:
            samples = statistics[stat]
            break

    if len(sys.argv) == 5:
        print 'Samples'
        print '\t' + '\n\t'.join(map(str, samples))
        print 'Commands'
        print '\t' + '\n\t'.join(stat.commands)
        return

    getattr(stat, sys.argv[5])(samples)

