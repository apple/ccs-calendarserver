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

from calendarserver.tap.caldav import CalDAVServiceMaker, CalDAVOptions
from twisted.application.service import Service
from calendarserver.tap.util import FakeRequest
from calendarserver.tap.util import getRootResource
from calendarserver.tools.principals import removeProxy
from calendarserver.tools.util import loadConfig
from datetime import date, timedelta, datetime
from getopt import getopt, GetoptError
from twext.python.log import Logger
from twext.web2.dav import davxml
from twext.web2.responsecode import NO_CONTENT
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.directory.directory import DirectoryRecord
from twistedcaldav.method.put_common import StoreCalendarObjectResource
from twistedcaldav.query import calendarqueryfilter
from twistedcaldav.datafilters.peruserdata import PerUserDataFilter
from vobject.icalendar import utc
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
    print "  -b --batch <number>: number of events to remove in each transaction (default=100)"
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

def usage_purge_orphaned_attachments(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "  Remove orphaned attachments from the calendar server"
    print ""
    print "options:"
    print "  -b --batch <number>: number of attachments to remove in each transaction (default=100)"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print "  -h --help: print this help and exit"
    print "  -n --dry-run: only calculate how many attachments to purge"
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
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print "  -h --help: print this help and exit"
    print "  -n --dry-run: only calculate how many events and contacts to purge"
    print "  -v --verbose: print progress information"
    print ""

    if e:
        sys.stderr.write("%s\n" % (e,))
        sys.exit(64)
    else:
        sys.exit(0)


class PurgeOldEventsService(Service):

    cutoff = None
    batchSize = None
    dryrun = False
    verbose = False

    def __init__(self, store):
        self._store = store

    @inlineCallbacks
    def startService(self):
        try:
            rootResource = getRootResource(config, self._store)
            directory = rootResource.getDirectory()
            (yield purgeOldEvents(self._store, directory, rootResource,
                self.cutoff, self.batchSize, verbose=self.verbose,
                dryrun=self.dryrun))
        except Exception, e:
            print "Error:", e
            raise

        finally:
            reactor.stop()


class PurgeOrphanedAttachmentsService(Service):

    batchSize = None
    dryrun = False
    verbose = False

    def __init__(self, store):
        self._store = store

    @inlineCallbacks
    def startService(self):
        try:
            (yield purgeOrphanedAttachments(self._store, self.batchSize,
                verbose=self.verbose, dryrun=self.dryrun))
        except Exception, e:
            print "Error:", e
            raise

        finally:
            reactor.stop()


class PurgePrincipalService(Service):

    guids = None
    dryrun = False
    verbose = False

    def __init__(self, store):
        self._store = store

    @inlineCallbacks
    def startService(self):
        try:
            rootResource = getRootResource(config, self._store)
            directory = rootResource.getDirectory()
            total = (yield purgeGUIDs(directory, rootResource, self.guids,
                verbose=self.verbose, dryrun=self.dryrun))
            if self.verbose:
                amount = "%d event%s" % (total, "s" if total > 1 else "")
                if self.dryrun:
                    print "Would have modified or deleted %s" % (amount,)
                else:
                    print "Modified or deleted %s" % (amount,)
        except Exception, e:
            print "Error:", e
            raise
        finally:
            reactor.stop()


def shared_main(configFileName, serviceClass):

    try:
        loadConfig(configFileName)

        config.ProcessType = "Utility"
        config.UtilityServiceClass = serviceClass

        maker = CalDAVServiceMaker()
        options = CalDAVOptions
        service = maker.makeService(options)

        reactor.addSystemEventTrigger("during", "startup", service.startService)
        reactor.addSystemEventTrigger("before", "shutdown", service.stopService)

    except ConfigurationError, e:
        print "Error: %s" % (e,)
        return

    reactor.run()

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
    days = 365
    batchSize = 100
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

    cutoff = (date.today()-timedelta(days=days)).strftime("%Y%m%dT000000Z")
    PurgeOldEventsService.cutoff = cutoff
    PurgeOldEventsService.batchSize = batchSize
    PurgeOldEventsService.dryrun = dryrun
    PurgeOldEventsService.verbose = verbose

    shared_main(
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
    batchSize = 100
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

    shared_main(
        configFileName,
        PurgeOrphanedAttachmentsService,
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
    PurgePrincipalService.guids = args
    PurgePrincipalService.dryrun = dryrun
    PurgePrincipalService.verbose = verbose


    shared_main(
        configFileName,
        PurgePrincipalService
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
        orphanCount = len(orphans)
        if verbose:
            if orphanCount == 0:
                print "No orphaned attachments"
            elif orphanCount == 1:
                print "1 orphaned attachment"
            else:
                print "%d orphaned attachments" % (eventCount,)
        returnValue(orphanCount)

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
    @type when: datetime with tzinfo

    @param cua: Calendar User Address of principal being purged, to compare
        to see if it's the organizer of the event or just an attendee
    @type cua: string

    Assumes that event does not occur entirely in the past.

    @return: one of the 4 constants above to indicate what action to take
    """

    whenDate = when.date()

    master = event.masterComponent()

    # Only process VEVENT
    if master.name() != "VEVENT":
        return CANCELEVENT_SKIPPED

    # Anything completely in the future is deleted
    dtstart = master.getStartDateUTC()
    if isinstance(dtstart, datetime):
        isDateTime = True
        if dtstart > when:
            return CANCELEVENT_SHOULD_DELETE
    else:
        isDateTime = False
        if dtstart > whenDate:
            return CANCELEVENT_SHOULD_DELETE

    organizer = master.getOrganizer()

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
    if master.hasProperty("RRULE"):
        for rrule in master.properties("RRULE"):
            tokens = {}
            tokens.update([valuePart.split("=") for valuePart in rrule.value().split(";")])
            if tokens.has_key("COUNT"):
                dirty = True
                del tokens["COUNT"]

            if isDateTime:
                tokens["UNTIL"] = when.strftime("%Y%m%dT%H%M%SZ")
            else:
                tokens["UNTIL"] = when.strftime("%Y%m%d")

            newValue = ";".join(["%s=%s" % (key, value,) for key, value in tokens.iteritems()])
            rrule.setValue(newValue)
            dirty = True

    # Remove any EXDATEs and RDATEs beyond the cutoff
    for dateType in ("EXDATE", "RDATE"):
        if master.hasProperty(dateType):
            for exdate_rdate in master.properties(dateType):
                newValues = []
                for value in exdate_rdate.value():
                    if isinstance(value, datetime):
                        if value < when:
                            newValues.append(value)
                    else:
                        if value < whenDate:
                            newValues.append(value)
                if not newValues:
                    master.removeProperty(exdate_rdate)
                    dirty = True
                else:
                    exdate_rdate.setValue(newValues)
                    dirty = True


    # Remove any overridden components beyond the cutoff
    for component in tuple(event.subcomponents()):
        if component.name() == "VEVENT":
            dtstart = component.getStartDateUTC()
            remove = False
            if isinstance(dtstart, datetime):
                if dtstart > when:
                    remove = True
            else:
                if dtstart > whenDate:
                    remove = True
            if remove:
                event.removeComponent(component)
                dirty = True

    if dirty:
        return CANCELEVENT_MODIFIED
    else:
        return CANCELEVENT_NOT_MODIFIED


@inlineCallbacks
def purgeGUID(guid, directory, root, verbose=False, dryrun=False, proxies=True,
    when=None):

    if when is None:
        when = datetime.now(tz=utc)
    # when = datetime(2010, 12, 6, 12, 0, 0, 0, utc)

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

    cua = "urn:uuid:%s" % (guid,)

    principalCollection = directory.principalCollection
    principal = principalCollection.principalForRecord(record)

    request = FakeRequest(root, None, None)
    request.checkedSACL = True
    request.authnUser = request.authzUser = davxml.Principal(
        davxml.HRef.fromString("/principals/__uids__/%s/" % (guid,))
    )

    calendarHome = yield principal.calendarHome(request)

    # Anything in the past is left alone
    whenString = when.strftime("%Y%m%dT%H%M%SZ")
    filter =  caldavxml.Filter(
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

    perUserFilter = PerUserDataFilter(guid)

    for collName in (yield calendarHome.listChildren()):
        collection = (yield calendarHome.getChild(collName))
        if collection.isCalendarCollection():

            for childName, childUid, childType in (yield collection.index().indexedSearch(filter)):
                childResource = (yield collection.getChild(childName))
                event = (yield childResource.iCalendar())
                event = perUserFilter.filter(event)
                action = cancelEvent(event, when, cua)

                uri = "/calendars/__uids__/%s/%s/%s" % (guid, collName, childName)
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
                    count += 1
                    request._rememberResource(childResource, uri)
                    if verbose:
                        if dryrun:
                            print "Would delete: %s" % (uri,)
                        else:
                            print "Deleting: %s" % (uri,)
                    if not dryrun:
                        result = (yield childResource.storeRemove(request, True, uri))
                        if result != NO_CONTENT:
                            print "Error deleting %s/%s/%s: %s" % (guid,
                                collName, childName, result)


    txn = request._newStoreTransaction

    # Remove VCards
    abHome = (yield txn.addressbookHomeWithUID(guid))
    if abHome is not None:
        for abColl in list( (yield abHome.addressbooks()) ):
            for card in list( (yield abColl.addressbookObjects()) ):
                cardName = card.name()
                if verbose:
                    uri = "/addressbooks/__uids__/%s/%s/%s" % (guid, abColl.name(), cardName)
                    if dryrun:
                        print "Would delete: %s" % (uri,)
                    else:
                        print "Deleting: %s" % (uri,)
                if not dryrun:
                    (yield abColl.removeObjectResourceWithName(cardName))
                count += 1
            if not dryrun:
                # Also remove the addressbook collection itself
                (yield abHome.removeChildWithName(abColl.name()))

    # Commit
    (yield txn.commit())

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
            assignments.append((principal.record.guid, proxyType, other.record.guid))
            (yield removeProxy(other, principal))

        subPrincipal = principal.getChild("calendar-proxy-" + proxyType)
        proxies = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))
        for other in proxies.children:
            assignments.append((str(other).split("/")[3], proxyType, principal.record.guid))

        (yield subPrincipal.writeProperty(davxml.GroupMemberSet(), None))

    returnValue(assignments)

