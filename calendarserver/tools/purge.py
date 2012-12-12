#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_purge -*-
##
# Copyright (c) 2006-2012 Apple Inc. All rights reserved.
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
from errno import ENOENT, EACCES
from getopt import getopt, GetoptError

from pycalendar.datetime import PyCalendarDateTime

from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.log import Logger
from txdav.xml import element as davxml
from twext.web2.responsecode import NO_CONTENT

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.datafilters.peruserdata import PerUserDataFilter
from twistedcaldav.directory.directory import DirectoryRecord
from twistedcaldav.method.put_common import StoreCalendarObjectResource
from twistedcaldav.query import calendarqueryfilter

from calendarserver.tap.util import FakeRequest
from calendarserver.tap.util import getRootResource

from calendarserver.tools.cmdline import utilityMain
from calendarserver.tools.principals import removeProxy
from calendarserver.tools import tables

import collections

log = Logger()

DEFAULT_BATCH_SIZE = 100
DEFAULT_RETAIN_DAYS = 365

def usage_purge_events(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "  Remove old events from the calendar server"
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print "  -d --days <number>: specify how many days in the past to retain (default=%d)" % (DEFAULT_RETAIN_DAYS,)
    #print "  -b --batch <number>: number of events to remove in each transaction (default=%d)" % (DEFAULT_BATCH_SIZE,)
    print "  -n --dry-run: calculate how many events to purge, but do not purge data"
    print "  -v --verbose: print progress information"
    print ""

    if e:
        sys.stderr.write("%s\n" % (e,))
        sys.exit(64)
    else:
        sys.exit(0)



def usage_purge_orphaned_attachments(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "  Remove orphaned attachments from the calendar server"
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    #print "  -b --batch <number>: number of attachments to remove in each transaction (default=%d)" % (DEFAULT_BATCH_SIZE,)
    print "  -n --dry-run: calculate how many attachments to purge, but do not purge data"
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
    print "  Remove a principal's events and contacts from the calendar server"
    print ""
    print "options:"
    print "  -c --completely: By default, only future events are canceled; this option cancels all events"
    print "  -h --help: print this help and exit"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print "  -n --dry-run: calculate how many events and contacts to purge, but do not purge data"
    print "  -v --verbose: print progress information"
    print ""

    if e:
        sys.stderr.write("%s\n" % (e,))
        sys.exit(64)
    else:
        sys.exit(0)



class WorkerService(Service):

    def __init__(self, store):
        self._store = store


    def rootResource(self):
        try:
            rootResource = getRootResource(config, self._store)
        except OSError, e:
            if e.errno == ENOENT:
                # Trying to re-write resources.xml but its parent directory does
                # not exist.  The server's never been started, so we're missing
                # state required to do any work.  (Plus, what would be the point
                # of purging stuff from a server that's completely empty?)
                raise ConfigurationError(
                    "It appears that the server has never been started.\n"
                    "Please start it at least once before purging anything.")
            elif e.errno == EACCES:
                # Trying to re-write resources.xml but it is not writable by the
                # current user.  This most likely means we're in a system
                # configuration and the user doesn't have sufficient privileges
                # to do the other things the tool might need to do either.
                raise ConfigurationError("You must run this tool as root.")
            else:
                raise
        return rootResource


    @inlineCallbacks
    def startService(self):
        try:
            yield self.doWork()
        except ConfigurationError, ce:
            sys.stderr.write("Error: %s\n" % (str(ce),))
        except Exception, e:
            sys.stderr.write("Error: %s\n" % (e,))
            raise
        finally:
            reactor.stop()



class PurgeOldEventsService(WorkerService):

    cutoff = None
    batchSize = None
    dryrun = False
    verbose = False

    def doWork(self):
        rootResource = self.rootResource()
        directory = rootResource.getDirectory()
        return purgeOldEvents(self._store, directory, rootResource,
            self.cutoff, self.batchSize, verbose=self.verbose,
            dryrun=self.dryrun)



class PurgeOrphanedAttachmentsService(WorkerService):

    batchSize = None
    dryrun = False
    verbose = False

    def doWork(self):
        return purgeOrphanedAttachments(
            self._store, self.batchSize,
            verbose=self.verbose, dryrun=self.dryrun)



class PurgePrincipalService(WorkerService):

    uids = None
    dryrun = False
    verbose = False
    completely = False

    @inlineCallbacks
    def doWork(self):
        rootResource = self.rootResource()
        directory = rootResource.getDirectory()
        total = (yield purgeUIDs(self._store, directory, rootResource, self.uids,
            verbose=self.verbose, dryrun=self.dryrun,
            completely=self.completely, doimplicit=self.doimplicit))
        if self.verbose:
            amount = "%d event%s" % (total, "s" if total > 1 else "")
            if self.dryrun:
                print "Would have modified or deleted %s" % (amount,)
            else:
                print "Modified or deleted %s" % (amount,)



def main_purge_events():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "d:b:f:hnv", [
                "days=",
                "batch=",
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
    days = DEFAULT_RETAIN_DAYS
    batchSize = DEFAULT_BATCH_SIZE
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

        elif opt in ("-b", "--batch"):
            try:
                batchSize = int(arg)
            except ValueError, e:
                print "Invalid value for --batch: %s" % (arg,)
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

    if dryrun:
        verbose = True

    cutoff = PyCalendarDateTime.getToday()
    cutoff.setDateOnly(False)
    cutoff.offsetDay(-days)
    PurgeOldEventsService.cutoff = cutoff
    PurgeOldEventsService.batchSize = batchSize
    PurgeOldEventsService.dryrun = dryrun
    PurgeOldEventsService.verbose = verbose

    utilityMain(
        configFileName,
        PurgeOldEventsService,
    )



def main_purge_orphaned_attachments():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "d:b:f:hnv", [
                "batch=",
                "dry-run",
                "config=",
                "help",
                "verbose",
            ],
        )
    except GetoptError, e:
        usage_purge_orphaned_attachments(e)

    #
    # Get configuration
    #
    configFileName = None
    batchSize = DEFAULT_BATCH_SIZE
    dryrun = False
    verbose = False

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage_purge_orphaned_attachments()

        elif opt in ("-b", "--batch"):
            try:
                batchSize = int(arg)
            except ValueError, e:
                print "Invalid value for --batch: %s" % (arg,)
                usage_purge_orphaned_attachments(e)

        elif opt in ("-v", "--verbose"):
            verbose = True

        elif opt in ("-n", "--dry-run"):
            dryrun = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    if args:
        usage_purge_orphaned_attachments("Too many arguments: %s" % (args,))

    if dryrun:
        verbose = True

    PurgeOrphanedAttachmentsService.batchSize = batchSize
    PurgeOrphanedAttachmentsService.dryrun = dryrun
    PurgeOrphanedAttachmentsService.verbose = verbose

    utilityMain(
        configFileName,
        PurgeOrphanedAttachmentsService,
    )



def main_purge_principals():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "cf:hnv", [
                "completely",
                "dry-run",
                "config=",
                "help",
                "verbose",
                "noimplicit",
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
    completely = False
    doimplicit = True

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage_purge_principal()

        elif opt in ("-c", "--completely"):
            completely = True

        elif opt in ("-v", "--verbose"):
            verbose = True

        elif opt in ("-n", "--dry-run"):
            dryrun = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("--noimplicit"):
            doimplicit = False

        else:
            raise NotImplementedError(opt)

    # args is a list of uids
    PurgePrincipalService.uids = args
    PurgePrincipalService.completely = completely
    PurgePrincipalService.dryrun = dryrun
    PurgePrincipalService.verbose = verbose
    PurgePrincipalService.doimplicit = doimplicit

    utilityMain(
        configFileName,
        PurgePrincipalService
    )



@inlineCallbacks
def purgeOldEvents(store, directory, root, date, batchSize, verbose=False,
    dryrun=False):

    if dryrun:
        if verbose:
            print "(Dry run) Searching for old events..."
        txn = store.newTransaction(label="Find old events")
        oldEvents = (yield txn.eventsOlderThan(date))
        eventCount = len(oldEvents)
        if verbose:
            if eventCount == 0:
                print "No events are older than %s" % (date,)
            elif eventCount == 1:
                print "1 event is older than %s" % (date,)
            else:
                print "%d events are older than %s" % (eventCount, date)
        returnValue(eventCount)

    if verbose:
        print "Removing events older than %s..." % (date,)

    numEventsRemoved = -1
    totalRemoved = 0
    while numEventsRemoved:
        txn = store.newTransaction(label="Remove old events")
        numEventsRemoved = (yield txn.removeOldEvents(date, batchSize=batchSize))
        (yield txn.commit())
        if numEventsRemoved:
            totalRemoved += numEventsRemoved
            if verbose:
                print "%d," % (totalRemoved,),

    if verbose:
        print
        if totalRemoved == 0:
            print "No events were removed"
        elif totalRemoved == 1:
            print "1 event was removed in total"
        else:
            print "%d events were removed in total" % (totalRemoved,)

    returnValue(totalRemoved)



@inlineCallbacks
def purgeOrphanedAttachments(store, batchSize, verbose=False, dryrun=False):

    if dryrun:
        if verbose:
            print "(Dry run) Searching for orphaned attachments..."
        txn = store.newTransaction(label="Find orphaned attachments")
        orphans = (yield txn.orphanedAttachments())
        if verbose:
            # Print aggregate details by user
            byuser = collections.defaultdict(int)
            for owner_uid, _ignore_dropbox_id, _ignore_path, size in orphans:
                byuser[owner_uid] += size

            # Print table of results
            table = tables.Table()
            table.addHeader(("User", "Current Quota", "Orphaned Size", "Orphaned Count"))
            table.setDefaultColumnFormats(
               (
                    tables.Table.ColumnFormat("%s", tables.Table.ColumnFormat.LEFT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                )
            )
            total = 0
            for user, quota, size, count in sorted(orphans):
                table.addRow((
                    user,
                    quota,
                    size,
                    count,
                ))
                total += count
            table.addFooter(("Total:", "", "", total))

            print "\n"
            print "Orphaned Attachments by User:\n"
            table.printTable()
        else:
            total = sum([x[3] for x in orphans])

        returnValue(total)

    if verbose:
        print "Removing orphaned attachments..."

    numOrphansRemoved = -1
    totalRemoved = 0
    while numOrphansRemoved:
        txn = store.newTransaction(label="Remove orphaned attachments")
        numOrphansRemoved = (yield txn.removeOrphanedAttachments(batchSize=batchSize))
        (yield txn.commit())
        if numOrphansRemoved:
            totalRemoved += numOrphansRemoved
            if verbose:
                print "%d," % (totalRemoved,),

    if verbose:
        print
        if totalRemoved == 0:
            print "No orphaned attachments were removed"
        elif totalRemoved == 1:
            print "1 orphaned attachment was removed in total"
        else:
            print "%d orphaned attachments were removed in total" % (totalRemoved,)

    returnValue(totalRemoved)



@inlineCallbacks
def purgeUIDs(store, directory, root, uids, verbose=False, dryrun=False,
    completely=False, doimplicit=True):
    total = 0

    allAssignments = {}

    for uid in uids:
        count, allAssignments[uid] = (yield purgeUID(store, uid, directory, root,
            verbose=verbose, dryrun=dryrun, completely=completely, doimplicit=doimplicit))
        total += count

    # TODO: figure out what to do with the purged proxy assignments...
    # ...print to stdout?
    # ...save in a file?

    returnValue(total)


CANCELEVENT_SKIPPED = 1
CANCELEVENT_MODIFIED = 2
CANCELEVENT_NOT_MODIFIED = 3
CANCELEVENT_SHOULD_DELETE = 4

def cancelEvent(event, when, cua):
    """
    Modify a VEVENT such that all future occurrences are removed

    @param event: the event to modify
    @type event: L{twistedcaldav.ical.Component}

    @param when: the cutoff date (anything after which is removed)
    @type when: PyCalendarDateTime

    @param cua: Calendar User Address of principal being purged, to compare
        to see if it's the organizer of the event or just an attendee
    @type cua: string

    Assumes that event does not occur entirely in the past.

    @return: one of the 4 constants above to indicate what action to take
    """

    whenDate = when.duplicate()
    whenDate.setDateOnly(True)

    # Only process VEVENT
    if event.mainType() != "VEVENT":
        return CANCELEVENT_SKIPPED

    main = event.masterComponent()
    if main is None:
        # No master component, so this is an attendee being invited to one or
        # more occurrences
        main = event.mainComponent(allow_multiple=True)

    # Anything completely in the future is deleted
    dtstart = main.getStartDateUTC()
    isDateTime = not dtstart.isDateOnly()
    if dtstart > when:
        return CANCELEVENT_SHOULD_DELETE

    organizer = main.getOrganizer()

    # Non-meetings are deleted
    if organizer is None:
        return CANCELEVENT_SHOULD_DELETE

    # Meetings which cua is merely an attendee are deleted (thus implicitly
    # declined)
    # FIXME: I think we want to decline anything after the cut-off, not delete
    # the whole event.
    if organizer != cua:
        return CANCELEVENT_SHOULD_DELETE

    dirty = False

    # Set the UNTIL on RRULE to cease at the cutoff
    if main.hasProperty("RRULE"):
        for rrule in main.properties("RRULE"):
            rrule = rrule.value()
            if rrule.getUseCount():
                rrule.setUseCount(False)

            rrule.setUseUntil(True)
            if isDateTime:
                rrule.setUntil(when)
            else:
                rrule.setUntil(whenDate)
            dirty = True

    # Remove any EXDATEs and RDATEs beyond the cutoff
    for dateType in ("EXDATE", "RDATE"):
        if main.hasProperty(dateType):
            for exdate_rdate in main.properties(dateType):
                newValues = []
                for value in exdate_rdate.value():
                    if value.getValue() < when:
                        newValues.append(value)
                    else:
                        exdate_rdate.value().remove(value)
                        dirty = True
                if not newValues:
                    main.removeProperty(exdate_rdate)
                    dirty = True

    # Remove any overridden components beyond the cutoff
    for component in tuple(event.subcomponents()):
        if component.name() == "VEVENT":
            dtstart = component.getStartDateUTC()
            remove = False
            if dtstart > when:
                remove = True
            if remove:
                event.removeComponent(component)
                dirty = True

    if dirty:
        return CANCELEVENT_MODIFIED
    else:
        return CANCELEVENT_NOT_MODIFIED



@inlineCallbacks
def purgeUID(store, uid, directory, root, verbose=False, dryrun=False, proxies=True,
    when=None, completely=False, doimplicit=True):

    if when is None:
        when = PyCalendarDateTime.getNowUTC()

    # Does the record exist?
    record = directory.recordWithUID(uid)
    if record is None:
        # The user has already been removed from the directory service.  We
        # need to fashion a temporary, fake record

        # FIXME: probaby want a more elegant way to accomplish this,
        # since it requires the aggregate directory to examine these first:
        record = DirectoryRecord(directory, "users", uid, shortNames=(uid,),
            enabledForCalendaring=True)
        record.enabled = True
        directory._tmpRecords["shortNames"][uid] = record
        directory._tmpRecords["uids"][uid] = record

    cua = "urn:uuid:%s" % (uid,)

    principalCollection = directory.principalCollection
    principal = principalCollection.principalForRecord(record)

    request = FakeRequest(root, None, None)
    request.checkedSACL = True
    request.authnUser = request.authzUser = davxml.Principal(
        davxml.HRef.fromString("/principals/__uids__/%s/" % (uid,))
    )

    # See if calendar home is provisioned
    txn = store.newTransaction()
    storeCalHome = (yield txn.calendarHomeWithUID(uid))
    calHomeProvisioned = storeCalHome is not None

    # If in "completely" mode, unshare collections, remove notifications
    if calHomeProvisioned and completely:

        # Process shared and shared-to-me calendars
        children = list((yield storeCalHome.children()))
        for child in children:
            if verbose:
                if dryrun:
                    print "Would unshare: %s" % (child.name(),)
                else:
                    print "Unsharing: %s" % (child.name(),)
            if not dryrun:
                (yield child.unshare())

        if not dryrun:
            (yield storeCalHome.removeUnacceptedShares())
            notificationHome = (yield txn.notificationsWithUID(uid))
            if notificationHome is not None:
                (yield notificationHome.remove())

    (yield txn.commit())

    # Anything in the past is left alone
    whenString = when.getText()
    filter = caldavxml.Filter(
          caldavxml.ComponentFilter(
              caldavxml.ComponentFilter(
                  TimeRange(start=whenString,),
                  name=("VEVENT",),
              ),
              name="VCALENDAR",
           )
      )
    filter = calendarqueryfilter.Filter(filter)

    count = 0
    assignments = []

    perUserFilter = PerUserDataFilter(uid)

    try:
        if calHomeProvisioned:
            calendarHome = yield principal.calendarHome(request)
            for collName in (yield calendarHome.listChildren()):
                collection = (yield calendarHome.getChild(collName))

                if collection.isCalendarCollection() or collName == "inbox":
                    childNames = []

                    if completely:
                        # all events
                        for childName in (yield collection.listChildren()):
                            childNames.append(childName)
                    else:
                        # events matching filter
                        for childName, _ignore_childUid, _ignore_childType in (yield collection.index().indexedSearch(filter)):
                            childNames.append(childName)

                    for childName in childNames:

                        childResource = (yield collection.getChild(childName))
                        if completely:
                            action = CANCELEVENT_SHOULD_DELETE
                        else:
                            event = (yield childResource.iCalendar())
                            event = perUserFilter.filter(event)
                            action = cancelEvent(event, when, cua)

                        uri = "/calendars/__uids__/%s/%s/%s" % (uid, collName, childName)
                        request.path = uri
                        if action == CANCELEVENT_MODIFIED:
                            count += 1
                            request._rememberResource(childResource, uri)
                            storer = StoreCalendarObjectResource(
                                request=request,
                                destination=childResource,
                                destination_uri=uri,
                                destinationcal=True,
                                destinationparent=collection,
                                calendar=str(event),
                            )
                            if verbose:
                                if dryrun:
                                    print "Would modify: %s" % (uri,)
                                else:
                                    print "Modifying: %s" % (uri,)
                            if not dryrun:
                                result = (yield storer.run())

                        elif action == CANCELEVENT_SHOULD_DELETE:
                            incrementCount = dryrun
                            request._rememberResource(childResource, uri)
                            if verbose:
                                if dryrun:
                                    print "Would delete: %s" % (uri,)
                                else:
                                    print "Deleting: %s" % (uri,)
                            if not dryrun:
                                retry = False
                                try:
                                    result = (yield childResource.storeRemove(request, doimplicit, uri))
                                    if result != NO_CONTENT:
                                        print "Error deleting %s/%s/%s: %s" % (uid,
                                            collName, childName, result)
                                        retry = True
                                    else:
                                        incrementCount = True

                                except Exception, e:
                                    print "Exception deleting %s/%s/%s: %s" % (uid,
                                        collName, childName, str(e))
                                    retry = True

                                if retry and doimplicit:
                                    # Try again with implicit scheduling off
                                    print "Retrying deletion of %s/%s/%s with implicit scheduling turned off" % (uid, collName, childName)
                                    try:
                                        result = (yield childResource.storeRemove(request, False, uri))
                                        if result != NO_CONTENT:
                                            print "Error deleting %s/%s/%s: %s" % (uid,
                                                collName, childName, result)
                                        else:
                                            incrementCount = True
                                    except Exception, e:
                                        print "Still couldn't delete %s/%s/%s even with implicit scheduling turned off: %s" % (uid, collName, childName, str(e))

                            if incrementCount:
                                count += 1

        txn = getattr(request, "_newStoreTransaction", None)
        # Commit
        if txn is not None:
            (yield txn.commit())

    except Exception, e:
        # Abort
        txn = getattr(request, "_newStoreTransaction", None)
        if txn is not None:
            (yield txn.abort())
        raise e

    try:
        txn = store.newTransaction()

        # Remove empty calendar collections (and calendar home if no more
        # calendars)
        storeCalHome = (yield txn.calendarHomeWithUID(uid))
        if storeCalHome is not None:
            calendars = list((yield storeCalHome.calendars()))
            remainingCalendars = len(calendars)
            for calColl in calendars:
                if len(list((yield calColl.calendarObjects()))) == 0:
                    remainingCalendars -= 1
                    calendarName = calColl.name()
                    if verbose:
                        if dryrun:
                            print "Would delete calendar: %s" % (calendarName,)
                        else:
                            print "Deleting calendar: %s" % (calendarName,)
                    if not dryrun:
                        (yield storeCalHome.removeChildWithName(calendarName))

            if not remainingCalendars:
                if verbose:
                    if dryrun:
                        print "Would delete calendar home"
                    else:
                        print "Deleting calendar home"
                if not dryrun:
                    (yield storeCalHome.remove())

        # Remove VCards
        storeAbHome = (yield txn.addressbookHomeWithUID(uid))
        if storeAbHome is not None:
            for abColl in list((yield storeAbHome.addressbooks())):
                for card in list((yield abColl.addressbookObjects())):
                    cardName = card.name()
                    if verbose:
                        uri = "/addressbooks/__uids__/%s/%s/%s" % (uid, abColl.name(), cardName)
                        if dryrun:
                            print "Would delete: %s" % (uri,)
                        else:
                            print "Deleting: %s" % (uri,)
                    if not dryrun:
                        (yield abColl.removeObjectResourceWithName(cardName))
                    count += 1
                if verbose:
                    abName = abColl.name()
                    if dryrun:
                        print "Would delete addressbook: %s" % (abName,)
                    else:
                        print "Deleting addressbook: %s" % (abName,)
                if not dryrun:
                    # Also remove the addressbook collection itself
                    (yield storeAbHome.removeChildWithName(abColl.name()))

            if verbose:
                if dryrun:
                    print "Would delete addressbook home"
                else:
                    print "Deleting addressbook home"
            if not dryrun:
                (yield storeAbHome.remove())

        # Commit
        (yield txn.commit())

    except Exception, e:
        # Abort
        (yield txn.abort())
        raise e

    if proxies and not dryrun:
        if verbose:
            print "Deleting any proxy assignments"
        assignments = (yield purgeProxyAssignments(principal))

    returnValue((count, assignments))



@inlineCallbacks
def purgeProxyAssignments(principal):

    assignments = []

    for proxyType in ("read", "write"):

        proxyFor = (yield principal.proxyFor(proxyType == "write"))
        for other in proxyFor:
            assignments.append((principal.record.uid, proxyType, other.record.uid))
            (yield removeProxy(other, principal))

        subPrincipal = principal.getChild("calendar-proxy-" + proxyType)
        proxies = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))
        for other in proxies.children:
            assignments.append((str(other).split("/")[3], proxyType, principal.record.uid))

        (yield subPrincipal.writeProperty(davxml.GroupMemberSet(), None))

    returnValue(assignments)
