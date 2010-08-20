
import sys, pickle

from matplotlib import pyplot
import numpy

from compare import select

def main():
    fig = pyplot.figure()
    ax = fig.add_subplot(111)

    data = []
    for fname in sys.argv[1:]:
        fname, bench, param, stat = fname.split(',')
        stats, samples = select(
            pickle.load(file(fname)), bench, param, stat)
        data.append(samples)
        if data:
            assert len(samples) == len(data[0])

    bars = []
    color = iter('rgbcmy').next
    w = 1.0 / len(data)
    xs = numpy.arange(len(data[0]))
    for i, s in enumerate(data):
        bars.append(ax.bar(xs + i * w, s, width=w, color=color())[0])

    ax.set_xlabel('sample #')
    ax.set_ylabel('seconds')
    ax.legend(bars, sys.argv[1:])
    pyplot.show()    
