import sys, pickle

from benchlib import select

def main():
    if len(sys.argv) < 5:
        print 'Usage: %s <datafile> <benchmark name> <parameter value> <metric> [command]' % (sys.argv[0],)
    else:
        stat, samples = select(pickle.load(file(sys.argv[1])), *sys.argv[2:5])
        if len(sys.argv) == 5:
            print 'Samples'
            print '\t' + '\n\t'.join(map(str, stat.squash(samples)))
            print 'Commands'
            print '\t' + '\n\t'.join(stat.commands)
        else:
            print getattr(stat, sys.argv[5])(samples, *sys.argv[6:])

