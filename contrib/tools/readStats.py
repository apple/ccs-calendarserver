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

def readSock(sockname):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sockname)
    data = ""
    while True:
        d = s.recv(1024)
        if d:
            data += d
        else:
            break
    s.close()
    return data

def printStats(data):
    
    stats = json.loads(data)
    print "- " * 40
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
    
    
def usage(error_msg=None):
    if error_msg:
        print error_msg

    print """Usage: readStats [options]
Options:
    -h            Print this help and exit
    -s            Name of local socket to read from
    -t            Delay in seconds between each sample [10 seconds]

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
    sockname = "data/Logs/state/caldavd-stats.sock"

    options, args = getopt.getopt(sys.argv[1:], "hs:t:", [])

    for option, value in options:
        if option == "-h":
            usage()
        elif option == "-s":
            sockname = value
        elif option == "-t":
            delay = int(value)

    while True:
        try:
            printStats(readSock(sockname))
        except socket.error:
            printFailedStats("Unable to read statistics from server socket: %s" % (sockname,))
        except KeyError, e:
            printFailedStats("Unable to find key '%s' in statistics from server socket" % (e,))
            sys.exit(1)

        time.sleep(delay)
