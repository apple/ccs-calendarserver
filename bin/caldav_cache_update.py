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
This tool trawls through the server's data store, reading data.

This is useful for ensuring that any on-demand data format upgrades
are done.

This tool requires access to the calendar server's configuration and
data storage.
"""

import sys

#sys.path.insert(0, "/usr/share/caldavd/lib/python")

from getopt import getopt, GetoptError
from os.path import dirname, abspath
from twisted.internet import reactor
from twisted.internet.address import IPv4Address
from twisted.internet.defer import inlineCallbacks
from twisted.python import log
from twisted.python.reflect import namedClass
from twistedcaldav import memcachepool
from twistedcaldav.cache import MemcacheChangeNotifier
from twistedcaldav.config import config, defaultConfigFile
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.principal import DirectoryPrincipalResource
from twistedcaldav.notify import installNotificationClient
from twistedcaldav.resource import isPseudoCalendarCollectionResource
from twistedcaldav.static import CalDAVFile, CalendarHomeFile
import os

CALENDARS_DOCROOT = "_run/main/docs/calendars/"

def loadConfig(configFileName):
    if configFileName is None:
        configFileName = defaultConfigFile

    if not os.path.isfile(configFileName):
        sys.stderr.write("No config file: %s\n" % (configFileName,))
        sys.exit(1)

    config.loadConfig(configFileName)

    CalendarHomeFile.cacheNotifierFactory = MemcacheChangeNotifier
    DirectoryPrincipalResource.cacheNotifierFactory = MemcacheChangeNotifier

    memcachepool.installPool(
        IPv4Address(
            'TCP',
            config.Memcached["BindAddress"],
            config.Memcached["Port"]),
        config.Memcached["MaxClients"])

    installNotificationClient(
        config.Notifications["InternalNotificationHost"],
        config.Notifications["InternalNotificationPort"],
    )

    return config

def getDirectory():
    BaseDirectoryService = namedClass(config.DirectoryService["type"])

    class MyDirectoryService (BaseDirectoryService):
        def getPrincipalCollection(self):
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

        def setPrincipalCollection(self, coll):
            # See principal.py line 237:  self.directory.principalCollection = self
            pass

        principalCollection = property(getPrincipalCollection, setPrincipalCollection)

        def calendarHomeForRecord(self, record):
            principal = self.principalCollection.principalForRecord(record)
            if principal:
                try:
                    return principal._calendarHome()
                except AttributeError:
                    pass
            return None

        def calendarHomeForShortName(self, recordType, shortName):
            principal = self.principalCollection.principalForShortName(recordType, shortName)
            if principal:
                try:
                    return principal._calendarHome()
                except AttributeError:
                    pass
            return None

        def principalForCalendarUserAddress(self, cua):
            return self.principalCollection.principalForCalendarUserAddress(cua)


    return MyDirectoryService(**config.DirectoryService["params"])

class DummyDirectoryService (DirectoryService):
    realmName = ""
    baseGUID = "51856FD4-5023-4890-94FE-4356C4AAC3E4"
    def recordTypes(self): return ()
    def listRecords(self): return ()
    def recordWithShortName(self): return None

dummyDirectoryRecord = DirectoryRecord(
    service = DummyDirectoryService(),
    recordType = "dummy",
    guid = "8EF0892F-7CB6-4B8E-B294-7C5A5321136A",
    shortName = "dummy",
    fullName = "Dummy McDummerson",
    calendarUserAddresses = set(),
    autoSchedule = False,
)

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
    print "  --no-icalendar: Don't read iCalendar data"
    print "  --no-properties: Don't read DAV properties"
    print "  --no-index: Don't read indexes"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def main():
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "c:d:hf:", [
                "config=",
                "log=",
                "calverified=",
                "docroot=",
                "help",
            ],
        )
    except GetoptError, e:
        usage(e)

    configFileName = None
    logFileName = "/dev/stdout"
    calverifyLogFileName = None
    docroot = CALENDARS_DOCROOT

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("--log",):
            logFileName = arg

        elif opt in ("-c", "--calverified",):
            calverifyLogFileName = arg

        elif opt in ("-d", "--docroot",):
            docroot = arg

    if args:
        usage("Too many arguments: %s" % (" ".join(args),))

    observer = log.FileLogObserver(open(logFileName, "a"))
    log.addObserver(observer.emit)

    if not calverifyLogFileName:
        usage("CalVerify log file name must be specified")

    changedHomes, changedCalendars = calverifyScrape(calverifyLogFileName, docroot)
    for i in sorted(changedHomes):
        print i
    for i in sorted(changedCalendars):
        print i
    print "Total homes: %s" % (len(changedHomes),)
    print "Total calendars: %s" % (len(changedCalendars),)

    #
    # Start the reactor
    #
    reactor.callLater(0, run, configFileName, changedHomes, changedCalendars)
    reactor.run()

@inlineCallbacks
def run(configFileName, changedHomes, changedCalendars):

    def checkExists(resource):
        if not resource.exists():
            sys.stderr.write("No such file: %s\n" % (resource.fp.path,))
            sys.exit(1)

    if changedHomes or changedCalendars:
        loadConfig(configFileName)
        directory = getDirectory()
        
        #from twistedcaldav.log import setLogLevelForNamespace
        #setLogLevelForNamespace("twistedcaldav.memcacheprops", "debug")

        calendarHomes = set()

        for path in changedHomes:
            path = abspath(path)
            guid = os.path.basename(path)

            record = directory.recordWithGUID(guid)
            if record is None:
                record = DirectoryRecord(
                    service = DummyDirectoryService(),
                    recordType = "dummy",
                    guid = guid,
                    shortName = "dummy",
                    fullName = "",
                    calendarUserAddresses = set(),
                    autoSchedule = False,
                )

            parent = CalDAVFile(dirname(abspath(path)))
            calendarHome = CalendarHomeFile(path, parent, record)
            calendarHome.url = lambda:"/calendars/__uids__/%s/" % (guid,)
            checkExists(calendarHome)
            calendarHomes.add(calendarHome)

        calendars = set()

        for path in changedCalendars:
            guid = os.path.basename(path)

            record = directory.recordWithGUID(guid)
            if record is None:
                record = DirectoryRecord(
                    service = DummyDirectoryService(),
                    recordType = "dummy",
                    guid = guid,
                    shortName = "dummy",
                    fullName = "",
                    calendarUserAddresses = set(),
                    autoSchedule = False,
                )

            parent.url = lambda self:"/calendars/__uids__/"
            calendarHome = CalendarHomeFile(path, parent, record)
            calendarHome.url = lambda:"/calendars/__uids__/%s/" % (guid,)
            checkExists(calendarHome)
            calendar = calendarHome.getChild(os.path.basename(path.basename()))
            calendars.add(calendar)

    n = 0
    ok_n = 0
    fail_n = 0
    N = len(calendarHomes) + len(calendars)
    for calendarHome in calendarHomes:
        n += 1
        log.msg("%.2f%% (%d of %d)" % (100.0 * n/N, n, N))
        try:
            yield processCalendarHome(
                calendarHome,
                directory = directory,
            )
            ok_n += 1
        except Exception, e:
            log.msg("Exception for calendar home '%s': %s" % (calendarHome, e))
            fail_n += 1
    for calendar in calendars:
        n += 1
        log.msg("%.2f%% (%d of %d)" % (100.0 * n/N, n, N))
        try:
            yield processCalendar(
                calendar,
            )
            ok_n += 1
        except Exception, e:
            log.msg("Exception for calendar '%s': %s" % (calendar, e))
            fail_n += 1

    log.msg("")
    log.msg("Results:")
    log.msg("Total Processed: %d" % (n,))
    log.msg("Total OK: %d" % (ok_n,))
    log.msg("Total Bad: %d" % (fail_n,))

    reactor.stop()

def calverifyScrape(fileName, docroot):
    
    # Find affected paths
    homes = set()
    individuals = set()
    with open(fileName) as f:
        
        for line in f:
            if line.startswith("Fixed:"):
                fixedpath = line[7:-1]
                splits = fixedpath.split("/")[:4]
                homes.add(docroot + "/".join(splits))
            elif line.startswith("Fixed (removed):"):
                fixedpath = line[17:-1]
                splits = fixedpath.split("/")[:-1]
                individuals.add(docroot + "/".join(splits))

    # Remove individuals also in homes
    for item in tuple(individuals):
        splits = item.split("/")[:5]
        if "/".join(splits) in homes:
            individuals.remove(item)

    return homes, individuals

@inlineCallbacks
def processCalendarHome(
    calendarHome,
    directory = None,
):
    # Update ctags on each calendar collection 
    for childName in calendarHome.listChildren():
        if childName in ("outbox", "dropbox",):
            continue
        child = calendarHome.getChild(childName)
        if isPseudoCalendarCollectionResource(child):
            yield processCalendar(
                child,
            )

@inlineCallbacks
def processCalendar(
    calendarCollection,
):
    # Update the ctag on the calendar. This will update the memcache token
    # and send a push notification.
    yield calendarCollection.updateCTag()
    
    print calendarCollection

if __name__ == "__main__":
    main()
