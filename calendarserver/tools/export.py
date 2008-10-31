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

from twisted.python.reflect import namedClass
from twistedcaldav.ical import Component as iComponent, Property as iProperty
from twistedcaldav.ical import iCalendarProductID
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
    print "usage: %s [options] [input_specifiers]" % (name,)
    print ""
    print "Generate an iCalendar file containing the merged content of each calendar"
    print "collection read."
    print ""
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
                "config=",
                "output=",
                "help",
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
            calendarHome = CalendarHomeFile(arg, parent, dummyDirectoryRecord())
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
        config = getConfig(configFileName)
        directory = getDirectory(config)

    for record in records:
        recordType, shortName = record
        calendarHome = directory.calendarHomeForShortName(recordType, shortName)
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

_dummyDirectoryRecord = None
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

_config = None
def getConfig(configFileName):
    global _config
    if _config is None:
        from twistedcaldav.config import config, defaultConfigFile

        if configFileName is None:
            configFileName = defaultConfigFile

        if not os.path.isfile(configFileName):
            sys.stderr.write("No config file: %s\n" % (configFileName,))
            sys.exit(1)

        config.loadConfig(configFileName)

        _config = config

    return _config

_directory = None
def getDirectory(config):
    global _directory
    if _directory is None:
        BaseDirectoryService = namedClass(config.DirectoryService["type"])

        class MyDirectoryService (BaseDirectoryService):
            def principalCollection(self):
                if not hasattr(self, "_principalCollection"):
                    #
                    # Instantiating a CalendarHomeProvisioningResource with a directory
                    # will register it with the directory (still smells like a hack).
                    #
                    # We need that in order to locate calendar homes via the directory.
                    #
                    from twistedcaldav.static import CalendarHomeProvisioningFile
                    CalendarHomeProvisioningFile(os.path.join(config.DocumentRoot, "calendars"), self, "/calendars/")

                    from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
                    self._principalCollection = DirectoryPrincipalProvisioningResource("/principals/", self)

                return self._principalCollection

            def calendarHomeForShortName(self, recordType, shortName):
                principal = self.principalCollection().principalForShortName(recordType, shortName)
                if principal:
                    return principal.calendarHome()
                return None

        _directory = MyDirectoryService(**config.DirectoryService["params"])

    return _directory

if __name__ == "__main__":
    main()
