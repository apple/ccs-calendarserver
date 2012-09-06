#!/usr/bin/env python
#
##
# Copyright (c) 2008-2012 Apple Inc. All rights reserved.
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

import datetime
import getopt
import hashlib
import os
import sys
import xattr

ICALSERVER_DOCROOT = "/Library/CalendarServer/Documents"
DEFAULT_URIS = "uris.txt"

totalProblems = 0
totalErrors = 0
totalScanned = 0

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "Fix double-quote/escape bugs in iCalendar data."
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -p <path>: path to calendar server document root [icalserver default]"
    print "  -u <path>: path to file containing uris to process [uris.txt]"
    print "  --fix: Apply fixes, otherwise only check for problems"
    print ""
    print "uris: list of uris to process"

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

def scanURI(uri, basePath, doFix):
    
    global totalProblems
    global totalErrors
    global totalScanned

    # Verify we have a valid path
    pathBits = uri.strip("/").rstrip("/").split("/")
    if len(pathBits) != 4 or pathBits[0] != "calendars" or pathBits[1] != "__uids__":
        print "Invalid uri (ignoring): %s" % (uri,)
        totalErrors += 1
        return

    # Absolute hashed directory path to calendar collection
    calendarPath = os.path.join(
        basePath,
        pathBits[0],
        pathBits[1],
        pathBits[2][0:2],
        pathBits[2][2:4],
        pathBits[2],
        pathBits[3],
    )
    
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
            f = open(icsPath)
            icsData = f.read()
        except Exception, e:
            print "Failed to read file %s due to %s" % (icsPath, str(e),)
            totalErrors += 1
            continue
        finally:
            f.close()

        # See whether there is a \" that needs fixing.
        # NB Have to handle the case of a folded line... 
        if icsData.find('\\"') != -1 or icsData.find('\\\r\n "') != -1:
            if doFix:
                # Fix by continuously replacing \" with " until no more replacements occur
                while True:
                    newIcsData = icsData.replace('\\"', '"').replace('\\\r\n "', '\r\n "')
                    if newIcsData == icsData:
                        break
                    else:
                        icsData = newIcsData
                
                try:
                    f = open(icsPath, "w")
                    f.write(icsData)
                except Exception, e:
                    print "Failed to write file %s due to %s" % (icsPath, str(e),)
                    totalErrors += 1
                    continue
                finally:
                    f.close()

                # Change ETag on written resource
                updateEtag(icsPath, icsData)
                didFix = True
                print "Problem fixed in: <BasePath>%s" % (icsPath[basePathLength:],)
            else:
                print "Problem found in: <BasePath>%s" % (icsPath[basePathLength:],)
            totalProblems += 1
     
    # Change CTag on calendar collection if any resource was written
    if didFix:
        updateCtag(calendarPath)

def main():
    
    basePath = ICALSERVER_DOCROOT
    urisFile = DEFAULT_URIS
    doFix = False
    
    # Parse command line options
    opts, _ignore_args = getopt.getopt(sys.argv[1:], "hp:u:", ["fix", "help",])
    for option, value in opts:
        if option in ("-h", "--help"):
            usage()
        elif option == "-p":
            basePath = value
            if not os.path.exists(basePath):
                usage("Path does not exist: %s" % (basePath,))
            elif not os.path.isdir(basePath):
                usage("Path is not a directory: %s" % (basePath,))
        elif option == "-u":
            urisFile = value
        elif option == "--fix":
            doFix = True
        else:
            usage("Invalid option")

    if not urisFile:
        usage("Need to specify a file listing each URI to process")
    
    # Get all the uris to process
    f = open(urisFile)
    uris = set()
    for line in f:
        pos = line.find("/calendars/")
        if pos == -1:
            print "Ignored log line: %s" % (line,)
            continue
        uris.add(line[pos:].split()[0])
    uris = list(uris)
    uris.sort()
    f.close()

    print "Base Path is: %s" % (basePath,)
    print "Number of unique URIs to fix: %d" % (len(uris),)
    print ""
    for uri in uris:
        scanURI(uri, basePath, doFix)

    print ""
    print "---------------------"
    print "Total Problems %s: %d of %d" % ("Fixed" if doFix else "Found", totalProblems, totalScanned,)
    if totalErrors:
        print "Total Errors: %s" % (totalErrors,)

if __name__ == '__main__':
    
    main()
