#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_calverify -*-
##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
import sys
import os


def analyze(fname):
    
    lines = open(os.path.expanduser(fname)).read().splitlines()
    total = len(lines)
    ctr = 0
    results = {
        "table1": [],
        "table2": [],
        "table3": [],
        "table4": [],
    }

    def _tableParser(ctr, tableName, parseFn):
        ctr += 4
        while ctr < total:
            line = lines[ctr]
            if line.startswith("+------"):
                break
            else:
                results[tableName].append(parseFn(line))
            ctr += 1
        return ctr

    while ctr < total:
        line = lines[ctr]
        if line.startswith("Events missing from Attendee's calendars"):
            ctr = _tableParser(ctr, "table1", parseTableMissing)
        elif line.startswith("Events mismatched between Organizer's and Attendee's calendars"):
            ctr = _tableParser(ctr, "table2", parseTableMismatch)
        elif line.startswith("Attendee events missing in Organizer's calendar"):
            ctr = _tableParser(ctr, "table3", parseTableMissing)
        elif line.startswith("Attendee events mismatched in Organizer's calendar"):
            ctr = _tableParser(ctr, "table4", parseTableMismatch)
        ctr += 1
    
    return results

def parseTableMissing(line):
    splits = line.split("|")
    organizer = splits[1].strip()
    attendee = splits[2].strip()
    uid = splits[3].strip()
    resid = splits[4].strip()
    return (organizer, attendee, uid, resid,)

def parseTableMismatch(line):
    splits = line.split("|")
    organizer = splits[1].strip()
    attendee = splits[2].strip()
    uid = splits[3].strip()
    organizer_resid = splits[4].strip()
    attendee_resid = splits[7].strip()
    return (organizer, attendee, uid, organizer_resid, attendee_resid,)

def diff(results1, results2):
    
    print("\n\nEvents missing from Attendee's calendars")
    diffSets(results1["table1"], results2["table1"])
    
    print("\n\nEvents mismatched between Organizer's and Attendee's calendars")
    diffSets(results1["table2"], results2["table2"])
    
    print("\n\nAttendee events missing in Organizer's calendar")
    diffSets(results1["table3"], results2["table3"])
    
    print("\n\nAttendee events mismatched in Organizer's calendar")
    diffSets(results1["table4"], results2["table4"])

def diffSets(results1, results2):
    
    s1 = set(results1)
    s2 = set(results2)
    
    d = s1 - s2
    print("\nIn first, not in second: (%d)" % (len(d),))
    for i in sorted(d):
        print(i)
    
    d = s2 - s1
    print("\nIn second, not in first: (%d)" % (len(d),))
    for i in sorted(d):
        print(i)

def usage(error_msg=None):
    if error_msg:
        print(error_msg)

    print("""Usage: calverify_diff [options] FILE1 FILE2
Options:
    -h          Print this help and exit

Arguments:
    FILE1     File containing calverify output to analyze
    FILE2     File containing calverify output to analyze

Description:
    This utility will analyze the output of two calverify runs
    and show what is different between the two.
""")

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)


if __name__ == '__main__':

    options, args = getopt.getopt(sys.argv[1:], "h", [])

    for option, value in options:
        if option == "-h":
            usage()
        else:
            usage("Unrecognized option: %s" % (option,))

    if len(args) != 2:
        usage("Must have two arguments")
    else:
        fname1 = args[0]
        fname2 = args[1]

    print("*** CalVerify diff from %s to %s" % (
        os.path.basename(fname1),
        os.path.basename(fname2),
    ))
    results1 = analyze(fname1)
    results2 = analyze(fname2)
    diff(results1, results2)
