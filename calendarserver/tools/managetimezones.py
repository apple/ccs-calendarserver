#!/usr/bin/env python
##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

from twistedcaldav.timezonestdservice import PrimaryTimezoneDatabase,\
    SecondaryTimezoneDatabase
from sys import stdout, stderr
import getopt
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python.log import addObserver, removeObserver
import sys
import os

def _doPrimaryActions(action, tzpath, xmlfile, changed):

    tzdb = PrimaryTimezoneDatabase(tzpath, xmlfile)
    if action == "create":
        print "Creating new XML file at: %s" % (xmlfile, )
        tzdb.createNewDatabase()
        print "Current total: %d" % (len(tzdb.timezones), )

    elif action == "update":
        print "Updating XML file at: %s" % (xmlfile, )
        tzdb.readDatabase()
        tzdb.updateDatabase()
        print "Current total: %d" % (len(tzdb.timezones), )
        print "Total Changed: %d" % (tzdb.changeCount, )
        if tzdb.changeCount:
            print "Changed:"
            for k in sorted(tzdb.changed):
                print "  %s" % (k, )
    
    elif action == "list":
        print "Listing XML file at: %s" % (xmlfile, )
        tzdb.readDatabase()
        print "Current timestamp: %s" % (tzdb.dtstamp, )
        print "Timezones:"
        for k in sorted(tzdb.timezones.keys()):
            print "  %s" % (k, )
    
    elif action == "changed":
        print "Changes from XML file at: %s" % (xmlfile, )
        tzdb.readDatabase()
        print "Check timestamp: %s" % (changed, )
        print "Current timestamp: %s" % (tzdb.dtstamp, )
        results = [k for k, v in tzdb.timezones.items() if v.dtstamp > changed]
        print "Total Changed: %d" % (len(results), )
        if results:
            print "Changed:"
            for k in sorted(results):
                print "  %s" % (k, )
    else:
        usage("Invalid action: %s" % (action, ))

class StandardIOObserver (object):
    """
    Log observer that writes to standard I/O.
    """
    def emit(self, eventDict):
        text = None

        if eventDict["isError"]:
            output = stderr
            if "failure" in eventDict:
                text = eventDict["failure"].getTraceback()
        else:
            output = stdout

        if not text:
            text = " ".join([str(m) for m in eventDict["message"]]) + "\n"

        output.write(text)
        output.flush()

    def start(self):
        addObserver(self.emit)

    def stop(self):
        removeObserver(self.emit)

@inlineCallbacks
def _runInReactor(tzdb):
    
    try:
        new, changed = yield tzdb.syncWithServer()
        print "New:           %d" % (new, )
        print "Changed:       %d" % (changed, )
        print "Current total: %d" % (len(tzdb.timezones), )
    except Exception, e:
        print "Could not sync with server: %s" % (str(e),)
    finally:
        reactor.stop()

def _doSecondaryActions(action, tzpath, xmlfile, url):

    tzdb = SecondaryTimezoneDatabase(tzpath, xmlfile, url)
    try:
        tzdb.readDatabase()
    except:
        pass
    if action == "cache":
        print "Caching from secondary server: %s" % (url, )

        observer = StandardIOObserver()
        observer.start()
        reactor.callLater(0, _runInReactor, tzdb)
        reactor.run()
    else:
        usage("Invalid action: %s" % (action, ))

def usage(error_msg=None):
    if error_msg:
        print error_msg
        print

    print """Usage: timezonestdservice [options]
Options:
    -h            Print this help and exit
    -f            XML file path
    -z            zoneinfo file path

    # Primary service
    --create      create new XML file
    --update      update XML file
    --list        list timezones in XML file
    --changed     changed since timestamp
    
    # Secondary service
    --url         URL or domain of service
    --cache       Cache data from service

Description:
    This utility will create, update or list an XML timezone database
    summary file.

"""

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)

def main():
    primary = False
    secondary = False
    action = None
    tzpath = None
    xmlfile = None
    changed = None
    url = None
    
    # Get options
    options, _ignore_args = getopt.getopt(
        sys.argv[1:],
        "hf:z:",
        [
            "create",
            "update",
            "list",
            "changed=",
            "url=",
            "cache",
        ]
    )

    for option, value in options:
        if option == "-h":
            usage()
        elif option == "-f":
            xmlfile = value
        elif option == "-z":
            tzpath = value
        elif option == "--create":
            action = "create"
            primary = True
        elif option == "--update":
            action = "update"
            primary = True
        elif option == "--list":
            action = "list"
            primary = True
        elif option == "--changed":
            action = "changed"
            primary = True
            changed = value
        elif option == "--url":
            url = value
            secondary = True
        elif option == "--cache":
            action = "cache"
            secondary = True
        else:
            usage("Unrecognized option: %s" % (option,))
    
    if action is None:
        action = "list"
        primary = True
    if tzpath is None:
        try:
            import pkg_resources
        except ImportError:
            tzpath = os.path.join(os.path.dirname(__file__), "zoneinfo")
        else:
            tzpath = pkg_resources.resource_filename("twistedcaldav", "zoneinfo") #@UndefinedVariable
    if xmlfile is None:
        xmlfile = os.path.join(tzpath, "timezones.xml")

    if primary and not os.path.isdir(tzpath):
        usage("Invalid zoneinfo path: %s" % (tzpath,))
    if primary and not os.path.isfile(xmlfile) and action != "create":
        usage("Invalid XML file path: %s" % (xmlfile,))

    if primary and secondary:
        usage("Cannot use primary and secondary options together")

    if primary:
        _doPrimaryActions(action, tzpath, xmlfile, changed)
    else:
        _doSecondaryActions(action, tzpath, xmlfile, url)

if __name__ == '__main__':
    main()
