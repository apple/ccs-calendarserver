#!/usr/bin/env python

##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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

from pwd import getpwnam
from twisted.python.util import switchUID
from twistedcaldav.directory.directory import DirectoryError
from grp import getgrnam
from calendarserver.tap.util import FakeRequest
from calendarserver.tap.util import getRootResource
from calendarserver.tools.util import loadConfig, setupMemcached, setupNotifications
from datetime import date, timedelta
from getopt import getopt, GetoptError
from twext.python.log import Logger
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, Deferred
from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.method.delete_common import DeleteResource
import os
import sys

log = Logger()

def usage(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "  Remove old events from the calendar server"
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -d --days <number>: specify how many days in the past to retain"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print "  -n --noprompt: don't prompt for confirmation"
    print "  -v --verbose: print progress information"
    print ""

    if e:
        sys.exit(64)
    else:
        sys.exit(0)


def main():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hd:f:nv", [
                "help",
                "days=",
                "config=",
                "noprompt",
                "verbose",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    configFileName = None
    days = 365
    verbose = False
    prompt = True

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-d", "--days"):
            try:
                days = int(arg)
            except ValueError, e:
                print "Invalid value for --days: %s" % (arg,)
                usage(e)

        elif opt in ("-v", "--verbose"):
            verbose = True

        elif opt in ("-n", "--noprompt"):
            prompt = False

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    try:
        loadConfig(configFileName)

        # Shed privileges
        if config.UserName and config.GroupName and os.getuid() == 0:
            uid = getpwnam(config.UserName).pw_uid
            gid = getgrnam(config.GroupName).gr_gid
            switchUID(uid, uid, gid)

        os.umask(config.umask)

        try:
            rootResource = getRootResource(config)
            directory = rootResource.getDirectory()
        except DirectoryError, e:
            print "Error: %s" % (e,)
            return
        setupMemcached(config)
        setupNotifications(config)
    except ConfigurationError, e:
        print "Error: %s" % (e,)
        return

    cutoff = (date.today() - timedelta(days=days)).strftime("%Y%m%dT000000Z")

    if prompt:
        response = raw_input("Are you sure you want to delete all events older than %d days? (yes/no) " % (days,))
        if response != "yes":
            print "Not deleting events"
            sys.exit(0)

    #
    # Start the reactor
    #
    reactor.callLater(0, purgeThenStop, directory, rootResource, cutoff,
        verbose=verbose)

    # In the case where there are no events to be purged, these two lines
    # seem to be necessary for reactor.run( ) to actually exit when we call
    # stop( ):
    d = Deferred()
    reactor.callLater(0, d.callback, True)

    reactor.run()

@inlineCallbacks
def purgeThenStop(directory, rootResource, cutoff, verbose=False):
    try:
        count = (yield purgeOldEvents(directory, rootResource, cutoff,
            verbose=verbose))
        print "Purged %d events" % (count,)
    finally:
        reactor.stop()



@inlineCallbacks
def purgeOldEvents(directory, root, date, verbose=False):

    calendars = root.getChild("calendars")
    uidsFPath = calendars.fp.child("__uids__")

    if verbose:
        print " Scanning calendar homes ...",

    records = []
    if uidsFPath.exists():
        for firstFPath in uidsFPath.children():
            if len(firstFPath.basename()) == 2:
                for secondFPath in firstFPath.children():
                    if len(secondFPath.basename()) == 2:
                        for homeFPath in secondFPath.children():
                            uid = homeFPath.basename()
                            record = directory.recordWithUID(uid)
                            if record is not None:
                                records.append(record)
    if verbose:
        print "%d calendar homes found" % (len(records),)

    log.info("Purging events from %d calendar homes" % (len(records),))

    filter =  caldavxml.Filter(
          caldavxml.ComponentFilter(
              caldavxml.ComponentFilter(
                  TimeRange(start=date,),
                  name=("VEVENT", "VFREEBUSY", "VAVAILABILITY"),
              ),
              name="VCALENDAR",
           )
      )

    eventCount = 0
    for record in records:
        # Get the calendar home
        principalCollection = directory.principalCollection
        principal = principalCollection.principalForRecord(record)
        calendarHome = principal.calendarHome()

        if verbose:
            print " %s ..." % (record.uid,),

        homeEventCount = 0
        # For each collection in calendar home...
        for collName in calendarHome.listChildren():
            collection = calendarHome.getChild(collName)
            if collection.isCalendarCollection():
                # ...use their indexes to figure out which events to purge.

                # First, get the list of all child resources...
                resources = set(collection.listChildren())

                # ...and ignore those that appear *after* the given cutoff
                for name, uid, type in collection.index().indexedSearch(filter):
                    if name in resources:
                        resources.remove(name)

                for name in resources:
                    resource = collection.getChild(name)
                    uri = "/calendars/__uids__/%s/%s/%s" % (
                        record.uid,
                        collName,
                        name
                    )
                    try:
                        (yield deleteResource(root, collection, resource, uri))
                        eventCount += 1
                        homeEventCount += 1
                    except Exception, e:
                        log.error("Failed to purge old event: %s (%s)" %
                            (uri, e))

        if verbose:
            print "%d events purged" % (homeEventCount,)

    returnValue(eventCount)


def deleteResource(root, collection, resource, uri):
    request = FakeRequest(root, "DELETE", uri)

    # TODO: this seems hacky, even for a stub request:
    request._rememberResource(resource, uri)

    deleter = DeleteResource(request, resource, uri,
        collection, "infinity", allowImplicitSchedule=False)
    return deleter.run()
