#!/usr/bin/env python

##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
This tool reads calendar data from a series of inputs and generates a
single iCalendar file which can be opened in many calendar
applications.

This can be used to quickly create an iCalendar file from a user's
calendars.

This tool requires access to the calendar server's configuration and
data storage; it does not operate by talking to the server via the
network.  It therefore does not apply any of the access restrictions
that the server would.  As such, one should be midful that data
exported via this tool may be sensitive.
"""

import os
import sys
from getopt import getopt, GetoptError
from os.path import dirname, abspath

from twistedcaldav.config import ConfigurationError
from twistedcaldav.ical import Component as iComponent, Property as iProperty
from twistedcaldav.ical import iCalendarProductID
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.static import CalDAVFile, CalendarHomeFile
from twistedcaldav.directory.directory import DirectoryService

from calendarserver.tools.util import UsageError
from calendarserver.tools.util import loadConfig, getDirectory, dummyDirectoryRecord

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options] [input_specifiers]" % (name,)
    print ""
    print "Generate an iCalendar file containing the merged content of each calendar"
    print "collection read."
    print __doc__
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config: Specify caldavd.plist configuration path"
    print "  -o --output: Specify output file path (default: '-', meaning stdout)"
    print ""
    print "input specifiers:"
    print "  -c --collection: add a calendar collection"
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
            sys.argv[1:], "hf:o:c:H:r:u:", [
                "help",
                "config=",
                "output=",
                "collection=", "home=", "record=", "user=",
            ],
        )
    except GetoptError, e:
        usage(e)

    configFileName = None
    outputFileName = None

    collections = set()
    calendarHomes = set()
    records = set()

    def checkExists(resource):
        if not resource.exists():
            sys.stderr.write("No such file: %s\n" % (resource.fp.path,))
            sys.exit(1)

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("-o", "--output"):
            if arg == "-":
                outputFileName = None
            else:
                outputFileName = arg

        elif opt in ("-c", "--collection"):
            path = abspath(arg)
            collection = CalDAVFile(path)
            checkExists(collection)
            if not isCalendarCollectionResource(collection):
                sys.stderr.write("Not a calendar collection: %s\n" % (path,))
                sys.exit(1)
            collections.add(collection)

        elif opt in ("-H", "--home"):
            path = abspath(arg)
            parent = CalDAVFile(dirname(abspath(path)))
            calendarHome = CalendarHomeFile(arg, parent, dummyDirectoryRecord)
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

    if records:
        try:
            config = loadConfig(configFileName)
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

    for calendarHome in calendarHomes:
        for childName in calendarHome.listChildren():
            child = calendarHome.getChild(childName)
            if isCalendarCollectionResource(child):
                collections.add(child)

    try:
        calendar = iComponent("VCALENDAR")
        calendar.addProperty(iProperty("VERSION", "2.0"))
        calendar.addProperty(iProperty("PRODID", iCalendarProductID))

        uids  = set()
        tzids = set()

        for collection in collections:
            for name, uid, type in collection.index().indexedSearch(None):
                child = collection.getChild(name)
                childData = child.iCalendarText()

                try:
                    childCalendar = iComponent.fromString(childData)
                except ValueError:
                    continue
                assert childCalendar.name() == "VCALENDAR"

                if uid in uids:
                    sys.stderr.write("Skipping duplicate event UID %r from %s\n" % (uid, collection.fp.path))
                    continue
                else:
                    uids.add(uid)

                for component in childCalendar.subcomponents():
                    # Only insert VTIMEZONEs once
                    if component.name() == "VTIMEZONE":
                        tzid = component.propertyValue("TZID")
                        if tzid in tzids:
                            continue
                        else:
                            tzids.add(tzid)

                    calendar.addComponent(component)

        calendarData = str(calendar)

        if outputFileName:
            try:
                output = open(outputFileName, "w")
            except IOError, e:
                sys.stderr.write("Unable to open output file for writing %s: %s\n" % (outputFileName, e))
                sys.exit(1)
        else:
            output = sys.stdout

        output.write(calendarData)

    except UsageError, e:
        usage(e)

if __name__ == "__main__":
    main()
