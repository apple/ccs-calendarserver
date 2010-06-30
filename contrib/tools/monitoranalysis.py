#!/usr/bin/env python
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

import matplotlib.pyplot as plt
import getopt
import sys
import os

dataset = []

def analyze(fpath, startDate, endDate, title=None):
    
    print "Analyzing data for %s" % (fpath,)
    data = []
    with open(fpath) as f:
        for line in f:
            try:
                if line.startswith("2010/0"):
                    
                    date = line[:10]
                    if startDate and date < startDate or endDate and date > endDate:
                        continue

                    digits = line[11:13]
                    if digits in ("05", "06"):
                        for _ignore in range(3):
                            f.next()
                        continue
                    datetime = line[:19]
                    if "Listenq" in line:
                        lqnon = line[len("2010/05/12 22:27:24 Listenq (ssl+non): "):].split("+", 1)[1]
                    else:
                        lqnon = line[len("2010/01/05 19:47:23 Listen queue: "):]
                        
                    lqnon = int(lqnon.split(" ", 1)[0])
                    
                    line = f.next()
                    cpu = int(line[len("CPU idle %: "):].split(" ", 1)[0])
                    
                    line = f.next()
                    reqs = int(float(line.split(" ", 1)[0]))
    
                    line = f.next()
                    resp = line[len("Response time: average "):].split(" ", 1)[0]
                    resp = int(float(resp)/10.0) * 10
    
                    if reqs <= 80:
                        data.append((datetime, reqs, resp, lqnon, cpu))
                    #print "%s %d %d %d %d" % (datetime, reqs, resp, lqnon, cpu)
            except StopIteration:
                break
    
    if not title:
        if startDate and endDate:
            title = "Between %s and %s" % (startDate, endDate,)
        elif startDate:
            title = "Since %s" % (startDate,)
        elif endDate:
            title = "Up to %s" % (endDate,)
        else:
            title = None 

    dataset.append((title, data,))
    
    print "Stored %d data points" % (len(data),)

def plotListenQBands(data, first, last):

    x1 = []
    y1 = []
    x2 = []
    y2 = []
    x3 = []
    y3 = []
    for datetime, reqs, resp, lq, cpu in data:
        if lq == 0:
            x1.append(reqs)
            y1.append(resp)
        elif lq < 50:
            x2.append(reqs)
            y2.append(resp)
        else:
            x3.append(reqs)
            y3.append(resp)
    
    plt.plot(x1, y1, "b+", x2, y2, "g+", x3, y3, "y+")
    
    if first:
        plt.legend(('ListenQ at zero', 'ListenQ < 50', 'ListenQ >= 50'),
               'upper right', shadow=True, fancybox=True)
    if last:
        plt.xlabel("Requests/second")
    plt.ylabel("Av. Response Time (ms)")
    plt.xlim(0, 80)
    plt.ylim(0, 4000)

def plotCPUBands(data, first, last):

    x = [[], [], [], []]
    y = [[], [], [], []]
    for datetime, reqs, resp, lq, cpu in data:
        if cpu > 75:
            x[0].append(reqs)
            y[0].append(resp)
        elif cpu > 50:
            x[1].append(reqs)
            y[1].append(resp)
        elif cpu > 25:
            x[2].append(reqs)
            y[2].append(resp)
        else:
            x[3].append(reqs)
            y[3].append(resp)
    
    plt.plot(
        x[0], y[0], "b+",
        x[1], y[1], "g+",
        x[2], y[2], "y+",
        x[3], y[3], "m+",
    )
    
    if first:
        plt.legend(('CPU < 1/4', 'CPU < 1/2', 'CPU < 3/4', "CPU High"),
               'upper right', shadow=True, fancybox=True)
    if last:
        plt.xlabel("Requests/second")
    plt.ylabel("Av. Response Time (ms)")
    plt.xlim(0, 80)
    plt.ylim(0, 4000)

def plot():
    
    print "Plotting data"
    
    plt.figure(1)

    nplots = len(dataset)
    subplot = nplots*100 + 20
    
    for ctr, item in enumerate(dataset):
        
        title, data = item
        if not title:
            title = "#%d" % (ctr+1,)

        plt.subplot(subplot + 2*ctr + 1)
        plotListenQBands(data, first=(ctr == 0), last=(ctr+1 == len(dataset)))
        plt.title("ListenQ %s" % (title,))
        
        plt.subplot(subplot + 2*ctr + 2)
        plotCPUBands(data, first=(ctr == 0), last=(ctr+1 == len(dataset)))
        plt.title("CPU %s" % (title,))
        
    plt.show()

def argPath(path):
    fpath = os.path.expanduser(path)
    if not fpath.startswith("/"):
        fpath = os.path.join(pwd, fpath)
    return fpath

def expandDate(date):
    return "%s/%s/%s" % (date[0:4], date[4:6], date[6:8],)

def usage(error_msg=None):
    if error_msg:
        print error_msg

    print """Usage: monitoranalysis [options] FILE+
Options:
    -h          Print this help and exit

Arguments:
    FILE      File names for the requests.log to analyze. A date
              range can be specified by append a comma, then a
              dash seperated pair of YYYYMMDD dates, e.g.:
              ~/request.log,20100614-20100619. Multiple
              ranges can be specified for multiple plots.

Description:
This utility will analyze the output of the request monitor tool and
generate some pretty plots of data.
"""

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)

if __name__ == "__main__":

    options, args = getopt.getopt(sys.argv[1:], "h", [])

    for option, value in options:
        if option == "-h":
            usage()
        else:
            usage("Unrecognized option: %s" % (option,))

    # Process arguments
    if len(args) == 0:
        usage("Must have arguments")

    pwd = os.getcwd()

    for arg in args:
        if "," in arg:
            items = arg.split(",")
            arg = items[0]
            start = []
            end = []
            for daterange in items[1:]:
                splits = daterange.split("-")
                if len(splits) == 1:
                    start.append(expandDate(splits[0]))
                    end.append(None)
                elif len(splits) == 2:
                    start.append(expandDate(splits[0]))
                    end.append(expandDate(splits[1]))
                else:
                    start.append(None)
                    end.append(None)
        else:
            start = (None,)
            end = (None,)
        
        for i in range(len(start)):
            analyze(argPath(arg), start[i], end[i])

    plot()
