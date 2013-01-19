#!/usr/bin/env python

##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
This tool trawls through the server's data store, reading data.

This is useful for ensuring that any on-demand data format upgrades
are done.

This tool requires access to the calendar server's configuration and
data storage.
"""

import os
import sys
import sqlite3
from getopt import getopt, GetoptError
from os.path import dirname, abspath

from twistedcaldav.config import ConfigurationError
from twistedcaldav.resource import isPseudoCalendarCollectionResource,\
    CalendarHomeResource
from twistedcaldav.static import CalDAVFile
from twistedcaldav.directory.directory import DirectoryService

from calendarserver.tools.util import loadConfig, getDirectory, dummyDirectoryRecord

class UsageError (StandardError):
    pass

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options] [input_specifiers]" % (name,)
    print ""
    print "Warm up data store by reading everything once."
    print __doc__
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config: Specify caldavd.plist configuration path"
    print ""
    print "input specifiers:"
    print "  -a --all: add all calendar homes"
    print "  -H --home: add a calendar home (and all calendars within it)"
    print "  -r --record: add a directory record's calendar home (format: 'recordType:shortName')"
    print "  -u --user: add a user's calendar home (shorthand for '-r users:shortName')"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def main():
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hf:o:aH:r:u:", [
                "config=",
                "output=",
                "help",
                "all", "home=", "record=", "user=",
            ],
        )
    except GetoptError, e:
        usage(e)

    configFileName = None

    calendarHomes = set()
    records = set()
    allRecords = False

    def checkExists(resource):
        if not resource.exists():
            sys.stderr.write("No such file: %s\n" % (resource.fp.path,))
            sys.exit(1)

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("-a", "--all"):
            allRecords = True

        elif opt in ("-H", "--home"):
            path = abspath(arg)
            parent = CalDAVFile(dirname(abspath(path)))
            calendarHome = CalendarHomeResource(arg, parent, dummyDirectoryRecord)
            checkExists(calendarHome)
            calendarHomes.add(calendarHome)

        elif opt in ("-r", "--record"):
            try:
                recordType, shortName = arg.split(":", 1)
                if not recordType or not shortName:
                    raise ValueError()
            except ValueError:
                sys.stderr.write("Invalid record identifier: %r\n" % (arg,))
                sys.exit(1)

            records.add((recordType, shortName))

        elif opt in ("-u", "--user"):
            records.add((DirectoryService.recordType_users, arg))

    if args:
        usage("Too many arguments: %s" % (" ".join(args),))

    if records or allRecords:
        try:
            config = loadConfig(configFileName)
            config.directory = getDirectory()
        except ConfigurationError, e:
            sys.stdout.write("%s\n" % (e,))
            sys.exit(1)

        for record in records:
            recordType, shortName = record
            calendarHome = config.directory.calendarHomeForShortName(recordType, shortName)
            if not calendarHome:
                sys.stderr.write("No calendar home found for record: (%s)%s\n" % (recordType, shortName))
                sys.exit(1)
            calendarHomes.add(calendarHome)

        if allRecords:
            for record in config.directory.allRecords():
                calendarHome = config.directory.calendarHomeForRecord(record)
                if not calendarHome:
                    pass
                else:
                    calendarHomes.add(calendarHome)

    calendarCollections = set()

    for calendarHome in calendarHomes:
        #print calendarHome
        #sys.stdout.write("*")
        readProperties(calendarHome)

        for childName in calendarHome.listChildren():
            child = calendarHome.getChild(childName)
            if isPseudoCalendarCollectionResource(child):
                calendarCollections.add(child)

    for calendarCollection in calendarCollections:
        try:
            for name, uid, type in calendarCollection.index().indexedSearch(None):
                child = calendarCollection.getChild(name)

                #sys.stdout.write("+")
                child._text()

                readProperties(child)

        except sqlite3.OperationalError:
            # Outbox doesn't live on disk
            if calendarCollection.fp.basename() != "outbox":
                raise

def readProperties(resource):
    #sys.stdout.write("-")
    for qname in resource.deadProperties().list():
        resource.readDeadProperty(qname)
        #sys.stdout.write(".")

if __name__ == "__main__":
    main()
