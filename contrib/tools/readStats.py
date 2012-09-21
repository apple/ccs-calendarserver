##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

from StringIO import StringIO
import datetime
import json
import socket
import tables
import time
import sys
import getopt

"""
This tool reads data from the server's statistics socket and prints a summary.
"""

def safeDivision(value, total, factor=1):
    return value * factor / total if total else 0

def readSock(sockname, useTCP):
    try:
        s = socket.socket(socket.AF_INET if useTCP else socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(sockname)
        data = ""
        while True:
            d = s.recv(1024)
            if d:
                data += d
            else:
                break
        s.close()
        data = json.loads(data)
    except socket.error:
        data = {"Failed": "Unable to read statistics from server: %s" % (sockname,)}
    data["Server"] = sockname
    return data

def printStats(stats):
    if len(stats) == 1 and False:
        if "Failed" in stats[0]:
            printFailedStats(stats[0]["Failed"]) 
        else:
            try:
                printStat(stats[0])
            except KeyError, e:
                printFailedStats("Unable to find key '%s' in statistics from server socket" % (e,))
                sys.exit(1)
            
    else:
        printMultipleStats(stats)
        
def printStat(stats):
    
    print "- " * 40
    print "Server: %s" % (stats["Server"],)
    print datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    print "Service Uptime: %s" % (datetime.timedelta(seconds=(int(time.time() - stats["System"]["start time"]))),)
    if stats["System"]["cpu count"] > 0:
        print "Current CPU: %.1f%% (%d CPUs)" % (
            stats["System"]["cpu use"],
            stats["System"]["cpu count"],
        )
        print "Current Memory Used: %d bytes (%.1f GB) (%.1f%% of total)" % (
            stats["System"]["memory used"],
            stats["System"]["memory used"] / (1024.0 * 1024 * 1024),
            stats["System"]["memory percent"],
        )
    else:
        print "Current CPU: Unavailable"
        print "Current Memory Used: Unavailable"
    print
    printRequestSummary(stats)
    printHistogramSummary(stats["5 Minutes"])

def printMultipleStats(stats):

    labels = serverLabels(stats)
 
    print "- " * 40
    print "Servers: %s" % (", ".join(labels),)

    print datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    times = []
    for stat in stats:
        try:
            t = str(datetime.timedelta(seconds=int(time.time() - stat["System"]["start time"])))
        except KeyError:
            t = "-"
        times.append(t)
    print "Service Uptime: %s" % (", ".join(times),)

    cpus = []
    memories = []
    for stat in stats:
        if stat["System"]["cpu count"] > 0:
            cpus.append("%.1f%%" % (stat["System"]["cpu use"],))
            memories.append("%.1f%%" % (stat["System"]["memory percent"],))
        else:
            cpus.append("-")
            memories("-")
    print "Current CPU: %s" % (", ".join(cpus),)
    print "Current Memory Used: %s" % (", ".join(memories),)
    print
    printMultiRequestSummary(stats, labels, ("5 Minutes", 5*60,))
    printMultiHistogramSummary(stats, "5 Minutes")

def serverLabels(stats):
    return [str(stat["Server"]) for stat in stats]

def printFailedStats(message):
    
    print "- " * 40
    print datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    print message
    print

def printRequestSummary(stats):
    table = tables.Table()
    table.addHeader(
        ("Period", "Requests", "Av. Requests", "Av. Response", "Av. Response", "Max. Response",    "Slot",     "CPU", "500's"),
    )
    table.addHeader(
        (      "",         "",   "per second",         "(ms)", "no write(ms)",          "(ms)", "Average", "Average",      ""),
    )
    table.setDefaultColumnFormats(
       (
            tables.Table.ColumnFormat("%s", tables.Table.ColumnFormat.LEFT_JUSTIFY), 
            tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.2f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f%%", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
        )
    )
    
    for key, seconds in (("Current", 60,), ("1 Minute", 60,), ("5 Minutes", 5*60,), ("1 Hour", 60*60,),):

        stat = stats[key]
        table.addRow((
            key,
            stat["requests"],
            safeDivision(float(stat["requests"]), seconds),
            safeDivision(stat["t"], stat["requests"]),
            safeDivision(stat["t"] - stat["t-resp-wr"], stat["requests"]),
            stat["T-MAX"],
            safeDivision(float(stat["slots"]), stat["requests"]),
            safeDivision(stat["cpu"], stat["requests"]),
            stat["500"],
        ))
        
    os = StringIO()
    table.printTable(os=os)
    print os.getvalue()

def printMultiRequestSummary(stats, labels, index):
    table = tables.Table()
    table.addHeader(
        ("Server", "Requests", "Av. Requests", "Av. Response", "Av. Response", "Max. Response",    "Slot",     "CPU", "500's"),
    )
    table.addHeader(
        (      "",         "",   "per second",         "(ms)", "no write(ms)",          "(ms)", "Average", "Average",      ""),
    )
    table.setDefaultColumnFormats(
       (
            tables.Table.ColumnFormat("%s", tables.Table.ColumnFormat.LEFT_JUSTIFY), 
            tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.2f", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f%%", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
        )
    )
    
    key, seconds = index
    totals = ["Overall:", 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0]
    for ctr, stat in enumerate(stats):

        stat = stat[key]
        
        col = []
        col.append(labels[ctr])
        col.append(stat["requests"])
        col.append(safeDivision(float(stat["requests"]), seconds))
        col.append(safeDivision(stat["t"], stat["requests"]))
        col.append(safeDivision(stat["t"] - stat["t-resp-wr"], stat["requests"]))
        col.append(stat["T-MAX"])
        col.append(safeDivision(float(stat["slots"]), stat["requests"]))
        col.append(safeDivision(stat["cpu"], stat["requests"]))
        col.append(stat["500"])
        table.addRow(col)
        for item in xrange(1, len(col)):
            totals[item] += col[item]
    
    for item in (2, 3, 4, 6, 7):
        totals[item] /= len(stats)
    
    table.addFooter(totals)

    os = StringIO()
    table.printTable(os=os)
    print os.getvalue()

def printHistogramSummary(stat):
    
    print "5 minute average response histogram"
    table = tables.Table()
    table.addHeader(
        ("", "<10ms", "10ms<->100ms", "100ms<->1s", "1s<->10s", "10s<->30s", "30s<->60s", ">60s",  "Over 1s", "Over 10s"),
    )
    table.setDefaultColumnFormats(
       (
            tables.Table.ColumnFormat("%s", tables.Table.ColumnFormat.CENTER_JUSTIFY), 
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f%%", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f%%", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
        )
    )
    for i in ("T", "T-RESP-WR",):
        table.addRow((
            "Overall Response" if i == "T" else "Response without Write",
            (stat[i]["<10ms"], safeDivision(stat[i]["<10ms"], stat["requests"], 100.0)),
            (stat[i]["10ms<->100ms"], safeDivision(stat[i]["10ms<->100ms"], stat["requests"], 100.0)),
            (stat[i]["100ms<->1s"], safeDivision(stat[i]["100ms<->1s"], stat["requests"], 100.0)),
            (stat[i]["1s<->10s"], safeDivision(stat[i]["1s<->10s"], stat["requests"], 100.0)),
            (stat[i]["10s<->30s"], safeDivision(stat[i]["10s<->30s"], stat["requests"], 100.0)),
            (stat[i]["30s<->60s"], safeDivision(stat[i]["30s<->60s"], stat["requests"], 100.0)),
            (stat[i][">60s"], safeDivision(stat[i][">60s"], stat["requests"], 100.0)),
            safeDivision(stat[i]["Over 1s"], stat["requests"], 100.0),
            safeDivision(stat[i]["Over 10s"], stat["requests"], 100.0),
        ))
    os = StringIO()
    table.printTable(os=os)
    print os.getvalue()
    
def printMultiHistogramSummary(stats, index):
    
    # Totals first
    keys = ("requests", "<10ms", "10ms<->100ms", "100ms<->1s", "1s<->10s", "10s<->30s", "30s<->60s", ">60s", "Over 1s", "Over 10s",)
    totals = {
        "T"        : dict([(k, 0) for k in keys]),
        "T-RESP-WR": dict([(k, 0) for k in keys]),
    }
    
    for stat in stats:
        for i in ("T", "T-RESP-WR",):
            totals[i][keys[0]] += stat[index][keys[0]]
            for k in keys[1:]:
                totals[i][k] += stat[index][i][k]

    print "5 minute average response histogram"
    table = tables.Table()
    table.addHeader(
        ("", "<10ms", "10ms<->100ms", "100ms<->1s", "1s<->10s", "10s<->30s", "30s<->60s", ">60s",  "Over 1s", "Over 10s"),
    )
    table.setDefaultColumnFormats(
       (
            tables.Table.ColumnFormat("%s", tables.Table.ColumnFormat.CENTER_JUSTIFY), 
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%d (%.1f%%)", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f%%", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            tables.Table.ColumnFormat("%.1f%%", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
        )
    )
    for i in ("T", "T-RESP-WR",):
        table.addRow((
            "Overall Response" if i == "T" else "Response without Write",
            (totals[i]["<10ms"], safeDivision(totals[i]["<10ms"], totals[i]["requests"], 100.0)),
            (totals[i]["10ms<->100ms"], safeDivision(totals[i]["10ms<->100ms"], totals[i]["requests"], 100.0)),
            (totals[i]["100ms<->1s"], safeDivision(totals[i]["100ms<->1s"], totals[i]["requests"], 100.0)),
            (totals[i]["1s<->10s"], safeDivision(totals[i]["1s<->10s"], totals[i]["requests"], 100.0)),
            (totals[i]["10s<->30s"], safeDivision(totals[i]["10s<->30s"], totals[i]["requests"], 100.0)),
            (totals[i]["30s<->60s"], safeDivision(totals[i]["30s<->60s"], totals[i]["requests"], 100.0)),
            (totals[i][">60s"], safeDivision(totals[i][">60s"], totals[i]["requests"], 100.0)),
            safeDivision(totals[i]["Over 1s"], totals[i]["requests"], 100.0),
            safeDivision(totals[i]["Over 10s"], totals[i]["requests"], 100.0),
        ))
    os = StringIO()
    table.printTable(os=os)
    print os.getvalue()
    
    
def usage(error_msg=None):
    if error_msg:
        print error_msg

    print """Usage: readStats [options]
Options:
    -h            Print this help and exit
    -s            Name of local socket to read from
    -t            Delay in seconds between each sample [10 seconds]
    --tcp host:port Use TCP connection with host:port

Description:
    This utility will print a summary of statistics read from a
    server continuously with the specified delay.

"""

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)

if __name__ == '__main__':
    
    delay = 10
    servers = ("data/Logs/state/caldavd-stats.sock",)
    useTCP = False

    options, args = getopt.getopt(sys.argv[1:], "hs:t:", ["tcp=",])

    for option, value in options:
        if option == "-h":
            usage()
        elif option == "-s":
            servers = value.split(",")
        elif option == "-t":
            delay = int(value)
        elif option == "--tcp":
            servers = [(host, int(port),) for host, port in [server.split(":") for server in value.split(",")]]
            useTCP = True

    while True:
        printStats([readSock(server, useTCP) for server in servers])
        time.sleep(delay)
