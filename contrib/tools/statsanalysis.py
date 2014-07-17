#!/usr/bin/env python
##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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
from __future__ import print_function

import getopt
import matplotlib.pyplot as plt
import os
import sys

dataset = {}

def analyze(fpath, title):
    """
    Analyze a readStats data file.

    @param fpath: path of file to analyze
    @type fpath: L{str}
    @param title: title to use for data set
    @type title: L{str}
    """

    print("Analyzing data for %s" % (title,))
    dataset[title] = {}
    with open(fpath) as f:
        for line in f:
            if line.startswith("- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -"):
                analyzeRecord(f, title)

    print("Read %d data points\n" % (len(dataset[title]),))


def analyzeRecord(liter, title):
    """
    Analyze one entry from the readStats data file.

    @param liter: iterator over lines in the file
    @type liter: L{iter}
    @param title: title to use for data set
    @type title: L{str}
    """

    dt = liter.next()
    time = dt[11:]
    seconds = 60 * (60 * int(time[0:2]) + int(time[3:5])) + int(time[6:8])
    for line in liter:
        if line.startswith("| Overall:"):
            overall = parseOverall(line)
            dataset[title][seconds] = overall
        elif line.startswith("| Method"):
            methods = parseMethods(liter)
            dataset[title][seconds].update(methods)
            break


def parseOverall(line):
    """
    Parse the "Overall:" stats summary line.

    @param line: the line to parse
    @type line: L{str}
    """

    splits = line.split("|")
    overall = {}
    keys = (
        ("Requests", lambda x: int(x)),
        ("Av. Requests per second", lambda x: float(x)),
        ("Av. Response", lambda x: float(x)),
        ("Av. Response no write", lambda x: float(x)),
        ("Max. Response", lambda x: float(x)),
        ("Slot Average", lambda x: float(x)),
        ("CPU Average", lambda x: float(x[:-1])),
        ("CPU Current", lambda x: float(x[:-1])),
        ("Memory Current", lambda x: float(x[:-1])),
        ("500's", lambda x: int(x)),
    )
    for ctr, item in enumerate(keys):
        key, conv = item
        overall["Overall:{}".format(key)] = conv(splits[2 + ctr].strip())

    return overall


def parseMethods(liter):
    """
    Parse the "Method Count" table from a data file entry.

    @param liter: iterator over lines in the file
    @type liter: L{iter}
    """

    while liter.next()[1] != "-":
        pass

    methods = {}
    for line in liter:
        if line[0] == "+":
            break
        splits = line.split("|")
        keys = (
            ("Count", lambda x: int(x)),
            ("Count %", lambda x: float(x[:-1])),
            ("Av. Response", lambda x: float(x)),
            ("Av. Response %", lambda x: float(x[:-1])),
            ("Total Resp. %", lambda x: float(x[:-1])),
        )
        for ctr, item in enumerate(keys):
            key, conv = item
            methods["Method:{}:{}".format(splits[1].strip(), key)] = conv(splits[2 + ctr].strip())

    return methods


def plotSeries(key, ymin=None, ymax=None):
    """
    Plot the chosen dataset key for each scanned data file.

    @param key: data set key to use
    @type key: L{str}
    @param ymin: minimum value for y-axis or L{None} for default
    @type ymin: L{int} or L{float}
    @param ymax: maximum value for y-axis or L{None} for default
    @type ymax: L{int} or L{float}
    """

    titles = []
    for title, data in sorted(dataset.items(), key=lambda x: x[0]):
        titles.append(title)
        x, y = zip(*[(k / 3600.0, v[key]) for k, v in sorted(data.items(), key=lambda x: x[0]) if key in v])
    
        plt.plot(x, y)

    plt.xlabel("Hours")
    plt.ylabel(key)
    plt.xlim(0, 24)
    if ymin is not None:
        plt.ylim(ymin=ymin)
    if ymax is not None:
        plt.ylim(ymax=ymax)
    plt.xticks(
        (1, 4, 7, 10, 13, 16, 19, 22,),
        (18, 21, 0, 3, 6, 9, 12, 15,),
    )
    plt.legend(titles, 'upper left', shadow=True, fancybox=True)
    plt.show()


def usage(error_msg=None):
    if error_msg:
        print(error_msg)

    print("""Usage: statsanalysis [options]
Options:
    -h             Print this help and exit
    -s             Directory to scan for data [~/stats]

Arguments:

Description:
This utility will analyze the output of the readStats tool and
generate some pretty plots of data.
""")

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)

if __name__ == "__main__":

    scanDir = os.path.expanduser("~/stats")
    options, args = getopt.getopt(sys.argv[1:], "hs:", [])

    for option, value in options:
        if option == "-h":
            usage()
        elif option == "-s":
            scanDir = os.path.expanduser(value)
        else:
            usage("Unrecognized option: %s" % (option,))

    if scanDir and len(args) != 0:
        usage("No arguments allowed when scanning a directory")

    pwd = os.getcwd()

    # Scan data directory and read in data from each file found
    fnames = os.listdir(scanDir)
    count = 1
    for name in fnames:
        if name.startswith("stats_all.log"):
            print("Found file: %s" % (os.path.join(scanDir, name),))
            trailer = name[len("stats_all.log"):]
            if trailer.startswith("-"):
                trailer = trailer[1:]
            initialDate = None
            analyze(os.path.join(scanDir, name), trailer)
            count += 1

    # Build the set of data set keys that can be plotted and let the user
    # choose which one
    keys = set()
    for data in dataset.values():
        for items in data.values():
            keys.update([":".join(k.split(":")[:2]) for k in items.keys()])
    keys = sorted(list(keys))
    while True:
        print("Select a key:")
        print("\n".join(["{:2d}. {}".format(ctr + 1, key) for ctr, key in enumerate(keys)]))
        print(" Q. Quit\n")
        cmd = raw_input("Key: ")
        if cmd.lower() == 'q':
            print("\nQuitting")
            break
        try:
            position = int(cmd) - 1
        except ValueError:
            print("Invalid key. Try again.\n")
            continue

        if keys[position].startswith("Method:"):
            key = keys[position]
            methodkeys = ("Count", "Count %", "Av. Response", "Av. Response %", "Total Resp. %")
            while True:
                print("Select a sub-key:")
                print("\n".join(["{:2d}. {}".format(ctr + 1, subkey) for ctr, subkey in enumerate(methodkeys)]))
                print(" B. Back\n")
                cmd = raw_input("SubKey: ")
                if cmd.lower() == 'b':
                    key = None
                    break
                try:
                    position = int(cmd) - 1
                except ValueError:
                    print("Invalid subkey. Try again.\n")
                    continue
                break
            key = "{}:{}".format(key, methodkeys[position]) if key is not None else None
        else:
            key = keys[position]

        if key:
            plotSeries(key, ymin=0, ymax=None)
