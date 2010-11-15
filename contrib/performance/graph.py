
import sys

from matplotlib import pyplot
import numpy

from benchlib import load_stats

def main():
    fig = pyplot.figure()
    ax = fig.add_subplot(111)

    data = [samples for (stat, samples) in load_stats(sys.argv[1:])]

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
