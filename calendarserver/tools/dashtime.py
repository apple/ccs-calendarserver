#!/usr/bin/env python
##
# Copyright (c) 2015-2016 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##
"""
Tool that extracts time series data from a dashcollect log.
"""

from bz2 import BZ2File
from collections import OrderedDict, defaultdict
from zlib import decompress
import argparse
import json
import matplotlib.pyplot as plt
import operator
import os


verbose = False
def _verbose(log):
    if verbose:
        print(log)



def safeDivision(value, total, factor=1):
    return value * factor / total if total else 0



class DataType(object):
    """
    Base class for object that can process the different types of data in a
    dashcollect log.
    """

    allTypes = OrderedDict()
    key = ""

    # This indicates whether the class of data is based on a 1 minute average -
    # which means the data represents a 60 second delay compared to the "real-
    # time" value. If it is the average then setting this flag will cause the
    # first 60 data items to be skipped.
    skip60 = False


    @staticmethod
    def getTitle(measurement):
        if "-" in measurement:
            measurement, item = measurement.split("-", 1)
        else:
            item = ""
        return DataType.allTypes[measurement].title(item)


    @staticmethod
    def getMaxY(measurement, numHosts):
        if "-" in measurement:
            measurement = measurement.split("-", 1)[0]
        return DataType.allTypes[measurement].maxY(numHosts)


    @staticmethod
    def skip(measurement):
        if "-" in measurement:
            measurement = measurement.split("-", 1)[0]
        return DataType.allTypes[measurement].skip60


    @staticmethod
    def process(measurement, stats, host):
        if "-" in measurement:
            measurement, item = measurement.split("-", 1)
        else:
            item = ""
        return DataType.allTypes[measurement].calculate(stats, item, host)


    @staticmethod
    def title(item):
        raise NotImplementedError


    @staticmethod
    def maxY(numHosts):
        raise NotImplementedError


    @staticmethod
    def calculate(stats, item, hosts):
        """
        If hosts is L{None} then data from all hosts will be aggregated.

        @param stats: per-Pod L{dict} of data from each host in the pod.
        @type stats: L{dict}
        @param item: additional L{dict} key for data of interest
        @type item: L{str}
        @param hosts: list of hosts to process
        @type hosts: L{list}
        """
        raise NotImplementedError



class CPUDataType(DataType):
    """
    CPU use.
    """

    key = "cpu"

    @staticmethod
    def title(item):
        return "CPU Use %"


    @staticmethod
    def maxY(numHosts):
        return 100 * numHosts


    @staticmethod
    def calculate(stats, item, hosts):
        return sum([stats[onehost]["stats_system"]["cpu use"] for onehost in hosts])



class RequestsDataType(DataType):
    """
    Number of requests.
    """

    key = "reqs"
    skip60 = True

    @staticmethod
    def title(item):
        return "Requests/sec"


    @staticmethod
    def maxY(numHosts):
        return None


    @staticmethod
    def calculate(stats, item, hosts):
        return sum([stats[onehost]["stats"]["1m"]["requests"] for onehost in hosts]) / 60.0



class ResponseDataType(DataType):
    """
    Average response time.
    """

    key = "respt"
    skip60 = True

    @staticmethod
    def title(item):
        return "Av. Response Time (ms)"


    @staticmethod
    def maxY(numHosts):
        return None


    @staticmethod
    def calculate(stats, item, hosts):
        tsum = sum([stats[onehost]["stats"]["1m"]["t"] for onehost in hosts])
        rsum = sum([stats[onehost]["stats"]["1m"]["requests"] for onehost in hosts])
        return safeDivision(tsum, rsum)



class JobsCompletedDataType(DataType):
    """
    Job completion count from job assignments.
    """

    key = "jcomp"

    lastCompleted = defaultdict(int)

    @staticmethod
    def title(item):
        return "Completed"


    @staticmethod
    def maxY(numHosts):
        return None


    @staticmethod
    def calculate(stats, item, hosts):
        result = 0
        for onehost in hosts:
            completed = sum(map(operator.itemgetter(2), stats[onehost]["job_assignments"]["workers"]))
            result += completed - JobsCompletedDataType.lastCompleted[onehost] if JobsCompletedDataType.lastCompleted[onehost] else 0
            JobsCompletedDataType.lastCompleted[onehost] = completed
        return result



class MethodCountDataType(DataType):
    """
    Count of specified methods. L{item} should be set to the full name of the
    "decorated" method seen in dashview.
    """

    key = "methodc"
    skip60 = True

    @staticmethod
    def title(item):
        return item


    @staticmethod
    def maxY(numHosts):
        return None


    @staticmethod
    def calculate(stats, item, hosts):
        return sum([stats[onehost]["stats"]["1m"]["method"].get(item, 0) for onehost in hosts])



class MethodResponseDataType(DataType):
    """
    Average response time of specified methods. L{item} should be set to the
    full name of the "decorated" method seen in dashview.
    """

    key = "methodr"
    skip60 = True

    @staticmethod
    def title(item):
        return item


    @staticmethod
    def maxY(numHosts):
        return None


    @staticmethod
    def calculate(stats, item, hosts):
        tsum = sum([stats[onehost]["stats"]["1m"]["method-t"].get(item, 0) for onehost in hosts])
        rsum = sum([stats[onehost]["stats"]["1m"]["method"].get(item, 0) for onehost in hosts])
        return safeDivision(tsum, rsum)



class JobQueueDataType(DataType):
    """
    Count of queued job items. L{item} should be set to the full name or prefix
    of job types to process. Or if set to L{None}, all jobs are counted.
    """

    key = "jqueue"

    @staticmethod
    def title(item):
        return ("JQ " + "_".join(map(operator.itemgetter(0), item.split("_")))) if item else "Jobs Queued"


    @staticmethod
    def maxY(numHosts):
        return None


    @staticmethod
    def calculate(stats, item, hosts):
        # Job queue stat only read for first host
        onehost = sorted(stats.keys())[0]

        if item:
            return sum(map(operator.itemgetter("queued"), {k: v for k, v in stats[onehost]["jobs"].items() if k.startswith(item)}.values()))
        else:
            return sum(map(operator.itemgetter("queued"), stats[onehost]["jobs"].values()))


# Register the known L{DataType}s
for dtype in DataType.__subclasses__():
    DataType.allTypes[dtype.key] = dtype



def main():
    parser = argparse.ArgumentParser(
        description="Dashboard time series processor.",
        epilog="cpu - CPU use\nreqs - requests per second\nrespt - average response time",
    )
    parser.add_argument("-l", help="Log file to process")
    parser.add_argument("-p", help="Name of pod to analyze")
    parser.add_argument("-s", help="Name of server to analyze")
    parser.add_argument("-v", action="store_true", help="Verbose")
    args = parser.parse_args()
    if args.v:
        global verbose
        verbose = True

    # Get the log file
    try:
        if args.l.endswith(".bz2"):
            logfile = BZ2File(os.path.expanduser(args.l))
        else:
            logfile = open(os.path.expanduser(args.l))
    except:
        print("Failed to open logfile {}".format(args.l))

    # Start/end lines in log file to process
    line_start = 0
    line_count = 10000

    # Plot arrays that will be generated
    x = []
    y = OrderedDict()
    titles = {}
    ymaxes = {}

    def singleHost(valuekeys):
        """
        Generate data for a single host only.

        @param valuekeys: L{DataType} keys to process
        @type valuekeys: L{list} or L{str}
        """
        _plotHosts(valuekeys, (args.s,))


    def combinedHosts(valuekeys):
        """
        Generate data for all hosts.

        @param valuekeys: L{DataType} keys to process
        @type valuekeys: L{list} or L{str}
        """
        _plotHosts(valuekeys, None)


    def _plotHosts(valuekeys, hosts):
        """
        Generate data for a the specified list of hosts.

        @param valuekeys: L{DataType} keys to process
        @type valuekeys: L{list} or L{str}
        @param hosts: lists of hosts to process
        @type hosts: L{list} or L{str}
        """

        # For each log file line, process the data for each required measurement
        with logfile:
            line = logfile.readline()
            ctr = 0
            while line:
                if ctr < line_start:
                    ctr += 1
                    line = logfile.readline()
                    continue

                if line[0] == "\x1e":
                    line = line[1:]
                if line[0] != "{":
                    line = decompress(line.decode("base64"))
                jline = json.loads(line)

                x.append(ctr)
                ctr += 1

                # Initialize the plot arrays when we know how many hosts there are
                if len(y) == 0:
                    if hosts is None:
                        hosts = sorted(jline["pods"][args.p].keys())
                    for measurement in valuekeys:
                        y[measurement] = []
                        titles[measurement] = DataType.getTitle(measurement)
                        ymaxes[measurement] = DataType.getMaxY(measurement, len(hosts))


                for measurement in valuekeys:
                    stats = jline["pods"][args.p]
                    y[measurement].append(DataType.process(measurement, stats, hosts))

                line = logfile.readline()
                if ctr > line_start + line_count:
                    break

        # Offset data that is averaged over the previous minute
        for measurement in valuekeys:
            if DataType.skip(measurement):
                y[measurement] = y[measurement][60:]
                y[measurement].extend([None] * 60)


    def perHost(perhostkeys, combinedkeys):
        """
        Generate a set of per-host plots, together we a set of plots for all-
        host data.

        @param perhostkeys: L{DataType} keys for per-host data to process
        @type perhostkeys: L{list} or L{str}
        @param combinedkeys: L{DataType} keys for all-host data to process
        @type combinedkeys: L{list} or L{str}
        """

        # For each log file line, process the data for each required measurement
        with logfile:
            line = logfile.readline()
            ctr = 0
            while line:
                if ctr < line_start:
                    ctr += 1
                    line = logfile.readline()
                    continue

                if line[0] == "\x1e":
                    line = line[1:]
                if line[0] != "{":
                    line = decompress(line.decode("base64"))
                jline = json.loads(line)

                x.append(ctr)
                ctr += 1

                # Initialize the plot arrays when we know how many hosts there are
                if len(y) == 0:
                    hosts = sorted(jline["pods"][args.p].keys())

                    for host in hosts:
                        for measurement in perhostkeys:
                            ykey = "{}={}".format(measurement, host)
                            y[ykey] = []
                            titles[ykey] = DataType.getTitle(measurement)
                            ymaxes[ykey] = DataType.getMaxY(measurement, 1)

                    for measurement in combinedkeys:
                        y[measurement] = []
                        titles[measurement] = DataType.getTitle(measurement)
                        ymaxes[measurement] = DataType.getMaxY(measurement, len(hosts))

                # Get actual measurement data
                for host in hosts:
                    for measurement in perhostkeys:
                        ykey = "{}={}".format(measurement, host)
                        stats = jline["pods"][args.p]
                        y[ykey].append(DataType.process(measurement, stats, (host,)))

                for measurement in combinedkeys:
                    stats = jline["pods"][args.p]
                    y[measurement].append(DataType.process(measurement, stats, hosts))

                line = logfile.readline()
                if ctr > line_start + line_count:
                    break

        # Offset data that is averaged over the previous minute. Also determine
        # the highest max value of all the per-host measurements and scale each
        # per-host plot to the same range.
        overall_ymax = defaultdict(int)
        for host in hosts:
            for measurement in perhostkeys:
                ykey = "{}={}".format(measurement, host)
                overall_ymax[measurement] = max(overall_ymax[measurement], max(y[ykey]))
                if DataType.skip(measurement):
                    y[ykey] = y[ykey][60:]
                    y[ykey].extend([None] * 60)
        for host in hosts:
            for measurement in perhostkeys:
                ykey = "{}={}".format(measurement, host)
                ymaxes[ykey] = overall_ymax[measurement]

        for measurement in combinedkeys:
            if DataType.skip(measurement):
                y[measurement] = y[measurement][60:]
                y[measurement].extend([None] * 60)


    # Data for a single host, with jobs queued detail for all hosts
#    singleHost((
#        CPUDataType.key,
#        RequestsDataType.key,
#        ResponseDataType.key,
#        JobsCompletedDataType.key,
#        JobQueueDataType.key + "-SCHEDULE",
#        JobQueueDataType.key + "-PUSH",
#        JobQueueDataType.key,
#    ))

    # Data aggregated for all hosts - job detail
#    combinedHosts((
#        CPUDataType.key,
#        RequestsDataType.key,
#        ResponseDataType.key,
#        JobsCompletedDataType.key,
#        JobQueueDataType.key + "-SCHEDULE",
#        JobQueueDataType.key + "-PUSH",
#        JobQueueDataType.key,
#    ))

    # Generic aggregated data for all hosts
    combinedHosts((
        CPUDataType.key,
        RequestsDataType.key,
        ResponseDataType.key,
        JobsCompletedDataType.key,
        JobQueueDataType.key,
    ))


    # Data aggregated for all hosts - method detail
#    combinedHosts((
#        CPUDataType.key,
#        RequestsDataType.key,
#        ResponseDataType.key,
#        MethodCountDataType.key + "-PUT ics",
#        MethodCountDataType.key + "-REPORT cal-home-sync",
#        MethodCountDataType.key + "-PROPFIND Calendar Home",
#        MethodCountDataType.key + "-REPORT cal-sync",
#        MethodCountDataType.key + "-PROPFIND Calendar",
#    ))

    # Per-host CPU, and total CPU
#    perHost((
#        RequestsDataType.key,
#    ), (
#        CPUDataType.key,
#    ))

    # Per-host job completion, and total CPU, total jobs queued
#    perHost((
#        JobsCompletedDataType.key,
#    ), (
#        CPUDataType.key,
#        JobQueueDataType.key,
#    ))

    # Generate a single stacked plot of the data
    plotmax = len(y.keys())
    for plotnum, measurement in enumerate(y.keys()):
        plt.subplot(len(y), 1, plotnum + 1)
        plotSeries(titles[measurement], x, y[measurement], 0, ymaxes[measurement], plotnum == plotmax - 1)
    plt.show()



def plotSeries(title, x, y, ymin=None, ymax=None, last_subplot=True):
    """
    Plot the chosen dataset key for each scanned data file.

    @param key: data set key to use
    @type key: L{str}
    @param ymin: minimum value for y-axis or L{None} for default
    @type ymin: L{int} or L{float}
    @param ymax: maximum value for y-axis or L{None} for default
    @type ymax: L{int} or L{float}
    """

    plt.plot(x, y)

    if last_subplot:
        plt.xlabel("Time")
    else:
        frame = plt.gca()
        frame.axes.xaxis.set_ticklabels([])
    plt.ylabel(title, fontsize="small", horizontalalignment="right", rotation="horizontal")
    if ymin is not None:
        plt.ylim(ymin=ymin)
    if ymax is not None:
        plt.ylim(ymax=ymax)
    plt.minorticks_on()
    plt.grid(True, "major", "x", alpha=0.5, linewidth=0.5)
    plt.grid(True, "minor", "x", alpha=0.5, linewidth=0.5)

if __name__ == "__main__":
    main()
