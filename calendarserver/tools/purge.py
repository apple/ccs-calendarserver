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

from calendarserver.tap.util import FakeRequest
from calendarserver.tap.util import getRootResource
from calendarserver.tools.principals import removeProxy
from calendarserver.tools.util import loadConfig, setupMemcached
from datetime import date, timedelta, datetime
from getopt import getopt, GetoptError
from grp import getgrnam
from pwd import getpwnam
from twext.python.log import Logger
from twext.web2.dav import davxml
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.util import switchUID
from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.directory.directory import DirectoryError, DirectoryRecord
from twistedcaldav.method.delete_common import DeleteResource
from twistedcaldav.query import calendarqueryfilter
import os
import sys

log = Logger()

def usage_purge_events(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "  Remove old events from the calendar server"
    print ""
    print "options:"
    print "  -d --days <number>: specify how many days in the past to retain (default=365)"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print "  -h --help: print this help and exit"
    print "  -n --dry-run: only calculate how many events to purge"
    print "  -v --verbose: print progress information"
    print ""

    if e:
        sys.stderr.write("%s\n" % (e,))
        sys.exit(64)
    else:
        sys.exit(0)

def usage_purge_principal(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "  Remove a principal's events from the calendar server"
    print ""
    print "options:"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print "  -h --help: print this help and exit"
    print "  -n --dry-run: only calculate how many events to purge"
    print "  -v --verbose: print progress information"
    print ""

    if e:
        sys.stderr.write("%s\n" % (e,))
        sys.exit(64)
    else:
        sys.exit(0)



def shared_main(configFileName, method, *args, **kwds):

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
    except ConfigurationError, e:
        print "Error: %s" % (e,)
        return


    #
    # Start the reactor
    #
    reactor.callLater(0.1, callThenStop, method, directory,
        rootResource, *args, **kwds)

    reactor.run()

def main_purge_events():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "d:f:hnv", [
                "days=",
                "dry-run",
                "config=",
                "help",
                "verbose",
            ],
        )
    except GetoptError, e:
        usage_purge_events(e)

    #
    # Get configuration
    #
    configFileName = None
    days = 365
    dryrun = False
    verbose = False

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage_purge_events()

        elif opt in ("-d", "--days"):
            try:
                days = int(arg)
            except ValueError, e:
                print "Invalid value for --days: %s" % (arg,)
                usage_purge_events(e)

        elif opt in ("-v", "--verbose"):
            verbose = True

        elif opt in ("-n", "--dry-run"):
            dryrun = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    if args:
        usage_purge_events("Too many arguments: %s" % (args,))

    cutoff = (date.today()-timedelta(days=days)).strftime("%Y%m%dT000000Z")

    shared_main(
        configFileName,
        purgeOldEvents,
        cutoff,
        verbose=verbose,
        dryrun=dryrun,
    )


def main_purge_principals():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "f:hnv", [
                "dry-run",
                "config=",
                "help",
                "verbose",
            ],
        )
    except GetoptError, e:
        usage_purge_principal(e)

    #
    # Get configuration
    #
    configFileName = None
    dryrun = False
    verbose = False

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage_purge_principal()

        elif opt in ("-v", "--verbose"):
            verbose = True

        elif opt in ("-n", "--dry-run"):
            dryrun = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    # args is a list of guids

    shared_main(
        configFileName,
        purgeGUIDs,
        args,
        verbose=verbose,
        dryrun=dryrun,
    )


@inlineCallbacks
def callThenStop(method, *args, **kwds):
    try:
        count = (yield method(*args, **kwds))
        if kwds.get("dryrun", False):
            print "Would have purged %d events" % (count,)
        else:
            print "Purged %d events" % (count,)
    except Exception, e:
        print "Error: %s" % (e,)
    finally:
        reactor.stop()


@inlineCallbacks
def purgeOldEvents(directory, root, date, verbose=False, dryrun=False):

    calendars = root.getChild("calendars")
    uidsFPath = calendars.fp.child("__uids__")

    if dryrun:
        print "Dry run"

    if verbose:
        print "Scanning calendar homes ...",

    records = []
    calendars = root.getChild("calendars")
    uidsFPath = calendars.fp.child("__uids__")

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
    filter = calendarqueryfilter.Filter(filter)

    eventCount = 0
    for record in records:
        # Get the calendar home
        principalCollection = directory.principalCollection
        principal = principalCollection.principalForRecord(record)
        calendarHome = yield principal.calendarHome()

        if verbose:
            print "%s %-15s :" % (record.uid, record.shortNames[0]),

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
                    if isinstance(name, unicode):
                        name = name.encode("utf-8")
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
                        if not dryrun:
                            (yield deleteResource(root, collection, resource,
                                uri, record.guid))
                        eventCount += 1
                        homeEventCount += 1
                    except Exception, e:
                        log.error("Failed to purge old event: %s (%s)" %
                            (uri, e))

        if verbose:
            print "%d events" % (homeEventCount,)

    returnValue(eventCount)


def deleteResource(root, collection, resource, uri, guid, implicit=False):
    request = FakeRequest(root, "DELETE", uri)
    request.authnUser = request.authzUser = davxml.Principal(
        davxml.HRef.fromString("/principals/__uids__/%s/" % (guid,))
    )

    # TODO: this seems hacky, even for a stub request:
    request._rememberResource(resource, uri)

    deleter = DeleteResource(request, resource, uri,
        collection, "infinity", allowImplicitSchedule=implicit)
    return deleter.run()


@inlineCallbacks
def purgeGUIDs(directory, root, guids, verbose=False, dryrun=False):
    total = 0

    allAssignments = { }

    for guid in guids:
        count, allAssignments[guid] = (yield purgeGUID(guid, directory, root,
            verbose=verbose, dryrun=dryrun))
        total += count


    # TODO: figure out what to do with the purged proxy assignments...
    # ...print to stdout?
    # ...save in a file?

    returnValue(total)


@inlineCallbacks
def purgeGUID(guid, directory, root, verbose=False, dryrun=False):

    # Does the record exist?
    record = directory.recordWithGUID(guid)
    if record is None:
        # The user has already been removed from the directory service.  We
        # need to fashion a temporary, fake record

        # FIXME: probaby want a more elegant way to accomplish this,
        # since it requires the aggregate directory to examine these first:
        record = DirectoryRecord(directory, "users", guid, shortNames=(guid,),
            enabledForCalendaring=True)
        record.enabled = True
        directory._tmpRecords["shortNames"][guid] = record
        directory._tmpRecords["guids"][guid] = record

    principalCollection = directory.principalCollection
    principal = principalCollection.principalForRecord(record)
    calendarHome = yield principal.calendarHome()

    # Anything in the past is left alone
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filter =  caldavxml.Filter(
          caldavxml.ComponentFilter(
              caldavxml.ComponentFilter(
                  TimeRange(start=now,),
                  name=("VEVENT", "VFREEBUSY", "VAVAILABILITY"),
              ),
              name="VCALENDAR",
           )
      )
    filter = calendarqueryfilter.Filter(filter)

    count = 0

    for collName in calendarHome.listChildren():
        collection = calendarHome.getChild(collName)
        if collection.isCalendarCollection():

            for name, uid, type in collection.index().indexedSearch(filter):
                if isinstance(name, unicode):
                    name = name.encode("utf-8")
                resource = collection.getChild(name)
                uri = "/calendars/__uids__/%s/%s/%s" % (
                    record.uid,
                    collName,
                    name
                )
                if not dryrun:
                    (yield deleteResource(root, collection, resource,
                        uri, guid, implicit=True))
                count += 1

    if not dryrun:
        assignments = (yield purgeProxyAssignments(principal))

    returnValue((count, assignments))


@inlineCallbacks
def purgeProxyAssignments(principal):

    assignments = []

    for proxyType in ("read", "write"):

        proxyFor = (yield principal.proxyFor(proxyType == "write"))
        for other in proxyFor:
            assignments.append((principal.record.guid, proxyType, other.record.guid))
            (yield removeProxy(other, principal))

        subPrincipal = principal.getChild("calendar-proxy-" + proxyType)
        proxies = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))
        for other in proxies.children:
            assignments.append((str(other).split("/")[3], proxyType, principal.record.guid))

        (yield subPrincipal.writeProperty(davxml.GroupMemberSet(), None))

    returnValue(assignments)


