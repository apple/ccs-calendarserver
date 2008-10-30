#!/usr/bin/env python
import dsquery

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

try:
    import opendirectory
    import dsattributes
except ImportError:
    sys.path.append("/usr/share/caldavd/lib/python")
    import opendirectory
    import dsattributes

try:
    from plistlib import readPlist
except ImportError:
    from twistedcaldav.py.plistlib import readPlist

class CalendarExporter(object):
    
    def __init__(self, plistpath, users, output_dir):
        
        self.plistpath = plistpath
        self.users = users
        self.output_dir = output_dir

        self.dsnode = None
        self.docroot = None

    def run(self):
        self._extractPlistPieces()
        self.od = opendirectory.odInit(self.dsnode)

        for user in self.users:
            print ""
            print "Dumping user: %s" % (user,)
            self._dumpUser(user)

    def _extractPlistPieces(self):
        
        plist = readPlist(self.plistpath)
    
        try:
            self.dsnode = plist["DirectoryService"]["params"]["node"]
        except KeyError:
            raise ValueError("Unable to read DirectoryService/params/node key from plist: %s" % (self.plistpath,))
        
        try:
            self.docroot = plist["DocumentRoot"]
        except KeyError:
            raise ValueError("Unable to read DocumentRoot key from plist: %s" % (self.plistpath,))
        
        print ""
        print "Parsed:               %s" % (self.plistpath,)
        print "Found DS Node:        %s" % (self.dsnode,)
        print "Found Server docroot: %s" % (self.docroot)
        print "Output directory:     %s" % (self.output_dir)
    
    def _getCalendarHome(self, user):
        
        guid = self._getUserGUID(user)
        return os.path.join(self.docroot, "calendars/__uids__", guid[0:2], guid[2:4], guid)
        
    def _getUserGUID(self, user):
    
        query = dsquery.match(dsattributes.kDSNAttrRecordName, user, dsattributes.eDSExact)

        results = opendirectory.queryRecordsWithAttribute_list(
            self.od,
            query.attribute,
            query.value,
            query.matchType,
            False,
            dsattributes.kDSStdRecordTypeUsers,
            [dsattributes.kDS1AttrGeneratedUID,]
        )
    
        for (_ignore, record) in results:
            guid = record.get(dsattributes.kDS1AttrGeneratedUID, None)
            if guid:
                return guid
        else:
            raise ValueError("No directory record for user: %s" % (user,))
            
    def _findCalendars(self, basepath):
    
        paths = []
        
        def _addDirectories(path):
            
            for child in os.listdir(path):
                childpath = os.path.join(path, child)
                resource = CalDAVFile(childpath)
                if resource.exists() and isCalendarCollectionResource(resource):
                    paths.append(childpath)
                    continue
                elif os.path.isdir(childpath):
                    _addDirectories(childpath)
    
        _addDirectories(basepath)
        return paths
    
    def _dumpUser(self, user):
        
        # Find the user's calendar home
        calendar_home = self._getCalendarHome(user)
        if not os.path.exists(calendar_home):
            print "Error: No calendar home for user: %s" % (user,)
            return
    
        # Create an output directory for the user
        user_dir = os.path.join(self.output_dir, user)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
    
        # List all possible calendars
        calendar_paths = self._findCalendars(calendar_home)
        
        for calendar_path in calendar_paths:
            resource = CalDAVFile(calendar_path)
    
            if not resource.exists() or not isCalendarCollectionResource(resource):
                continue
            
            calendar = iComponent("VCALENDAR")
            calendar.addProperty(iProperty("VERSION", "2.0"))
        
            tzids = set()
        
            for name, _ignore_uid, type in resource.index().search(None):
                child = resource.getChild(name)
                child_data = child.iCalendarText()
    
                try:
                    child_calendar = iComponent.fromString(child_data)
                except ValueError:
                    continue
                assert child_calendar.name() == "VCALENDAR"
    
                for component in child_calendar.subcomponents():
                    # Only insert VTIMEZONEs once
                    if component.name() == "VTIMEZONE":
                        tzid = component.propertyValue("TZID")
                        if tzid in tzids:
                            continue
                        else:
                            tzids.add(tzid)
    
                    calendar.addComponent(component)
    
            f = file(os.path.join(user_dir, os.path.basename(calendar_path)), "w")
            f.write(str(calendar))
            f.close()
            print "Dumped calendar for user '%s': %s" % (user, calendar_path,)
        
def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [-f plistfile] [-o outputdir] [-u user]" % (name,)
    print ""
    print "Generate an iCalendar file containing the merged content of each calendar"
    print "collection specified."
    print ""
    print "options:"
    print "  -h: print this help"
    print "  -f: plist file for server configuration (/etc/caldavd/caldavd.plist)"
    print "  -o: directory in which to write results (./exported)"
    print "  -u: user record name to lookup (can appear multiple times)"
    print "  -h: print this help"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def main():
    try:
        (optargs, args) = getopt.getopt(sys.argv[1:], "hf:o:u:", ["help",])
    except getopt.GetoptError, e:
        usage(e)

    plistpath = "/etc/caldavd/caldavd.plist"
    users = set()
    output_dir = os.path.join(os.getcwd(), "exported")

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()
        elif opt in ("-o",):
            output_dir = arg
        elif opt in ("-u",):
            users.add(arg)
        elif opt == "-f":
            plistpath = arg

    if args:
        usage("Too many arguments: %s" % (" ".join(args),))

    try:
        print "CalendarServer calendar user export tool"
        print "====================================="
    
        if not os.path.exists(plistpath):
            raise ValueError("caldavd.plist file does not exist: %s" % (plistpath,))
    
        CalendarExporter(plistpath, users, output_dir).run()

    except ValueError, e:
        print ""
        print "Failed: %s" % (str(e),)

if __name__ == "__main__":
    main()
