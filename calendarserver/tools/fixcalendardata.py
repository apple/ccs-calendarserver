#!/usr/bin/env python
#
##
# Copyright (c) 2009-2013 Apple Inc. All rights reserved.
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

import re
import datetime
import getopt
import hashlib
import os
import sys
import time
import xattr

from plistlib import readPlist

PLIST_FILE = "/Library/Server/Calendar and Contacts/Config/caldavd.plist"
SCAN_FILE = "problems.txt"

totalProblems = 0
totalErrors = 0
totalScanned = 0

verbose = False

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "Fix double-quote/escape bugs in iCalendar data."
    print "Fix incorrect use of TZID in iCalendar data."
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config: Specify caldavd.plist configuration path"
    print "  -o <path>: path to file for scan results [problems.txt]"
    print "  -v: print each calendar home scanned"
    print "  --scan: Scan for problems"
    print "  --fix: Apply fixes"
    print ""
    print "One of --scan or --fix must be specified. Both may be specified"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def updateEtag(path, caldata):

    x = xattr.xattr(path)
    x["WebDAV:{http:%2F%2Ftwistedmatrix.com%2Fxml_namespace%2Fdav%2F}getcontentmd5"] = """<?xml version='1.0' encoding='UTF-8'?>
<getcontentmd5 xmlns='http://twistedmatrix.com/xml_namespace/dav/'>%s</getcontentmd5>
""" % (hashlib.md5(caldata).hexdigest(),)

def updateCtag(path):

    x = xattr.xattr(path)
    x["WebDAV:{http:%2F%2Fcalendarserver.org%2Fns%2F}getctag"] = """<?xml version='1.0' encoding='UTF-8'?>
<getctag xmlns='http://calendarserver.org/ns/'>%s</getctag>
""" % (str(datetime.datetime.now()),)

def parsePlist(plistPath):

    plist = readPlist(plistPath)

    try:
        return plist["DocumentRoot"]
    except KeyError:
        raise ValueError("Unable to read DocumentRoot key from plist: %s" % (plistPath,))

def scanData(basePath, scanFile, doFix):
    
    uidsPath = os.path.join(basePath, "calendars", "__uids__")
    for item1 in os.listdir(uidsPath):
        if len(item1) == 2:
            level1Path = os.path.join(uidsPath, item1)
            for item2 in os.listdir(level1Path):
                if len(item2) == 2:
                    level2Path = os.path.join(level1Path, item2)
                    for item in os.listdir(level2Path):
                        calendarHome = os.path.join(level2Path, item)
                        if os.path.isdir(calendarHome):
                            scanCalendarHome(basePath, calendarHome, scanFile, doFix)

def scanCalendarHome(basePath, calendarHome, scanFile, doFix):
    if verbose:
        print "Scanning: %s" % (calendarHome,)
    
    for item in os.listdir(calendarHome):
        calendarPath = os.path.join(calendarHome, item)
        x = xattr.xattr(calendarPath)
        if x.has_key("WebDAV:{http:%2F%2Fcalendarserver.org%2Fns%2F}getctag"):
            scanCalendar(basePath, calendarPath, scanFile, doFix)

def scanCalendar(basePath, calendarPath, scanFile, doFix):

    global totalProblems
    global totalErrors
    global totalScanned

    if not os.path.exists(calendarPath):
        print "Calendar path does not exist: %s" % (calendarPath,)
        totalErrors += 1
        return

    # Look at each .ics in the calendar collection
    didFix = False
    basePathLength = len(basePath)
    for item in os.listdir(calendarPath):
        if not item.endswith(".ics"):
            continue
        totalScanned += 1
        icsPath = os.path.join(calendarPath, item)
        
        try:
            f = None
            f = open(icsPath)
            icsData = f.read()
        except Exception, e:
            print "Failed to read file %s due to %s" % (icsPath, str(e),)
            totalErrors += 1
            continue
        finally:
            if f:
                f.close()

        # See what needs fixing.
        problems = []
        fixQuotes = fixTZIDs = fixMultiVALARMs = False
        if testICSData_DoubleQuotes(icsData):
            problems.append("double quotes")
            fixQuotes = True
        if testICSData_TZIDs(icsData):
            problems.append("tzids")
            fixTZIDs = True
        valarms = testICSData_MultipleVALARMS(icsData)
        if valarms != 0:
            problems.append("multi-valarms-%d" % valarms)
            fixMultiVALARMs = True
        if problems:
            if doFix:
                if fixPath(icsPath, icsData, fixQuotes, fixTZIDs, fixMultiVALARMs):
                    didFix = True
                    print "Problems %s fixed in: <BasePath>%s" % (",".join(problems), icsPath[basePathLength:],)
            else:
                print "Problem %s found in: <BasePath>%s" % (",".join(problems), icsPath[basePathLength:],)
                scanFile.write(icsPath + "\n")
            totalProblems += 1
     
    # Change CTag on calendar collection if any resource was written
    if didFix:
        updateCtag(calendarPath)

def testICSData_DoubleQuotes(icsData):

    # See whether there is a \" that needs fixing.
    # NB Have to handle the case of a folded line... 
    return icsData.find('\\"') != -1 or icsData.find('\\\r\n "') != -1 or icsData.find('\r\n \r\n "') != -1

tzidRESearch = re.compile("(.*)TZID=[^;:]+;(VALUE=DATE.*)")
tzidREReplace = re.compile("(.*)TZID=[^;:]+;(VALUE=DATE.*)", flags=re.S)

def testICSData_TZIDs(icsData):
    
    return tzidRESearch.search(icsData) != None

def testICSData_MultipleVALARMS(icsData):
    
    if icsData.count("END:VALARM\r\nBEGIN:VALARM") > 0:
        
        # More detailed scan
        lines = icsData.split("\r\n")
        badcount = 0
        inevent = False
        for line in lines:
            line = line.upper()
            if line == "BEGIN:VEVENT":
                duplicate_count = 0
                alarm_ids = set()
                inevent = True
            elif line == "END:VEVENT":
                if duplicate_count > badcount:
                    badcount = duplicate_count
                inevent = False
            elif inevent and line.startswith("X-WR-ALARMUID"):
                new_id = line
                if new_id in alarm_ids:
                    duplicate_count += 1
                else:
                    alarm_ids.add(new_id)
        return badcount
    else:
        return 0

def fixData(basePath, scanPath):
    
    global totalProblems
    global totalErrors
    global totalScanned

    try:
        f = None
        f = open(scanPath)
        lines = [line[:-1] for line in f]
    except Exception, e:
        print "Failed to read file %s due to %s" % (scanPath, str(e),)
        totalErrors += 1
        return
    finally:
        if f:
            f.close()

    lines.sort()
    calendarPaths = {}
    for line in lines:
        calendarPath, icsName = line.rsplit("/", 1)
        calendarPaths.setdefault(calendarPath, []).append(icsName)
        totalScanned += 1
        
    basePathLength = len(basePath)
    for calendarPath, icsNames in sorted(calendarPaths.items(), key=lambda x:x[0]):
        didFix = False
        for icsName in icsNames:
            icsPath = os.path.join(calendarPath, icsName)
            if fixPath(icsPath):
                didFix = True
                print "Problem fixed in: <BasePath>%s" % (icsPath[basePathLength:],)
                totalProblems += 1
         
        # Change CTag on calendar collection if any resource was written
        if didFix:
            updateCtag(calendarPath)
        
def fixPath(icsPath, icsData=None, doQuotes=True, doTZIDs=True, doMultiVALARMs=True):

    global totalProblems
    global totalErrors
    global totalScanned

    if icsData is None:
        try:
            f = None
            f = open(icsPath)
            icsData = f.read()
        except Exception, e:
            print "Failed to read file %s due to %s" % (icsPath, str(e),)
            totalErrors += 1
            return False
        finally:
            if f:
                f.close()
        
    # Fix by continuously replacing \" with " until no more replacements occur
    if doQuotes:
        while True:
            newIcsData = icsData.replace('\\"', '"').replace('\\\r\n "', '\r\n "').replace('\r\n \r\n "', '\r\n "')
            if newIcsData == icsData:
                break
            else:
                icsData = newIcsData
    
    # Fix the TZID problem
    if doTZIDs:
        while True:
            icsMatch = tzidREReplace.search(icsData)
            if icsMatch is not None:
                icsData = icsMatch.expand("\\1\\2")
            else:
                break

    if doMultiVALARMs:
        lines = icsData.split("BEGIN:")
        newlines = []
        lastalarm = False
        for line in lines:
            isalarm = line.startswith("VALARM")
            if lastalarm and isalarm:
                newlines.pop()
            newlines.append(line)
            lastalarm = isalarm     
        icsData = "BEGIN:".join(newlines)

    try:
        f = None
        f = open(icsPath, "w")
        f.write(icsData)
    except Exception, e:
        print "Failed to write file %s due to %s" % (icsPath, str(e),)
        totalErrors += 1
        return False
    finally:
        if f:
            f.close()

    # Change ETag on written resource
    updateEtag(icsPath, icsData)

    return True

def main():
    
    plistPath = PLIST_FILE
    scanPath = SCAN_FILE
    doScan = False
    doFix = False
    
    # Parse command line options
    opts, _ignore_args = getopt.getopt(sys.argv[1:], "f:ho:", ["config", "scan", "fix", "help",])
    for option, value in opts:
        if option in ("-h", "--help"):
            usage()
        elif option in ("-f", "--config"):
            plistPath = value
            if not os.path.exists(plistPath):
                usage("Path does not exist: %s" % (plistPath,))
        elif option == "-o":
            scanPath = value
        elif option == "--scan":
            doScan = True
        elif option == "--fix":
            doFix = True
        else:
            usage("Invalid option")

    if not doScan and not doFix:
        usage("Must specify one or both of --scan or --fix")

    if not doScan and doFix and not scanPath:
        usage("Need to specify a file listing each path to fix")
    
    basePath = parsePlist(plistPath)

    start = time.time()
    print "Base Path is: %s" % (basePath,)
    if doScan:
        if doFix:
            print "Scanning data store and fixing"
            scanFile = None
        else:
            print "Scanning data store and writing results to '%s'" % (scanPath,)
            try:
                scanFile = open(scanPath, "w")
            except Exception, e:
                print "Failed to open file for writing %s due to %s" % (scanPath, str(e),)
        scanData(basePath, scanFile, doFix)
    elif doFix:
        print "Fixing data using results from '%s'" % (scanPath,)
        fixData(basePath, scanPath)
    difftime = time.time() - start

    print ""
    print "---------------------"
    print "Total Problems %s: %d of %d" % ("Fixed" if doFix else "Found", totalProblems, totalScanned,)
    if totalErrors:
        print "Total Errors: %s" % (totalErrors,)
    print "Time taken (secs): %.1f" % (difftime,)

if __name__ == '__main__':
    
    main()
