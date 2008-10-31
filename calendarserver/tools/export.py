#!/usr/bin/env python

##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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

import os
import sys
from getopt import getopt, GetoptError
from os.path import dirname, abspath

from twistedcaldav.ical import Component as iComponent, Property as iProperty,\
    iCalendarProductID
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.static import CalDAVFile, CalendarHomeFile
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord

class UsageError (StandardError):
    pass

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [-c collection_path] [-H calendar_home_path]" % (name,)
    print ""
    print "Generate an iCalendar file containing the merged content of each calendar"
    print "collection read."
    print ""
    print "options:"
    print "  -h --help: print this help"
    print "  -c --collection: add a calendar collection"
    print "  -H --home: add a calendar home (and all calendars within it)"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def main():
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hc:H:", [
                "help",
                "collection=", "home="
            ],
        )
    except GetoptError, e:
        usage(e)

    collections = set()
    calendarHomes = set()

    def checkExists(resource):
        if not resource.exists():
            sys.stderr.write("No such file: %s\n" % (resource.fp.path,))
            sys.exit(1)

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

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
            calendarHome = CalendarHomeFile(arg, parent, dummyDirectoryRecord())
            checkExists(calendarHome)
            calendarHomes.add(calendarHome)

    if args:
        usage("Too many arguments: %s" % (" ".join(args),))

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
            for name, uid, type in collection.index().search(None):
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

        print calendar

    except UsageError, e:
        usage(e)

def dummyDirectoryRecord():
    global _dummyDirectoryRecord
    if _dummyDirectoryRecord is None:
        class DummyDirectoryService (DirectoryService):
            realmName = ""
            baseGUID = "51856FD4-5023-4890-94FE-4356C4AAC3E4"
            def recordTypes(self): return ()
            def listRecords(self): return ()
            def recordWithShortName(self): return None

        _dummyDirectoryRecord = DirectoryRecord(
            service = DummyDirectoryService(),
            recordType = "dummy",
            guid = "8EF0892F-7CB6-4B8E-B294-7C5A5321136A",
            shortName = "dummy",
            fullName = "Dummy McDummerson",
            firstName = "Dummy",
            lastName = "McDummerson",
            emailAddresses = (),
            calendarUserAddresses = (),
            autoSchedule = False,
        )
    return _dummyDirectoryRecord
_dummyDirectoryRecord = None

if __name__ == "__main__":
    main()
