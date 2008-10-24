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
import getopt

from twistedcaldav.ical import Component as iComponent, Property as iProperty
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.static import CalDAVFile

class UsageError (StandardError):
    pass

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [-c collection]" % (name,)
    print ""
    print "Generate an iCalendar file containing the merged content of each calendar"
    print "collection specified."
    print ""
    print "options:"
    print "  -h: print this help"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def main():
    try:
        (optargs, args) = getopt.getopt(sys.argv[1:], "hc:", ["help", "collection="])
    except getopt.GetoptError, e:
        usage(e)

    collections = set()

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()
        if opt in ("-c", "--collection"):
            collections.add(arg)

    if args:
        usage("Too many arguments: %s" % (" ".join(args),))

    try:
        calendar = iComponent("VCALENDAR")
        calendar.addProperty(iProperty("VERSION", "2.0"))

        uids  = set()
        tzids = set()

        for collection in collections:
            resource = CalDAVFile(collection)

            if not resource.exists() or not isCalendarCollectionResource(resource):
                sys.stderr.write("Not a calendar collection: %s\n" % (collection,))
                sys.exit(1)
            
            for name, uid, type in resource.index().search(None):
                child = resource.getChild(name)
                child_data = child.iCalendarText()

                try:
                    child_calendar = iComponent.fromString(child_data)
                except ValueError:
                    continue
                assert child_calendar.name() == "VCALENDAR"

                if uid in uids:
                    sys.stderr.write("Skipping duplicate event UID: %s" % (uid,))
                    continue
                else:
                    uids.add(uid)

                for component in child_calendar.subcomponents():
                    # Only insert VTIMEZONEs once
                    if component.name() == "VTIMEZONE":
                        tzid = component.propertyValue("TZID")
                        if tzid in tzids:
                            continue
                        else:
                            tzids.add(tzid)

                    calendar.addComponent(component)

    except UsageError, e:
        usage(e)

if __name__ == "__main__":
    main()
