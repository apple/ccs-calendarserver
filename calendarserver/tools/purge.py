#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_purge -*-
##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
from __future__ import print_function

import collections
from getopt import getopt, GetoptError
import os
import sys

from calendarserver.tools import tables
from calendarserver.tools.cmdline import utilityMain, WorkerService
from pycalendar.datetime import DateTime
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav import caldavxml
from txdav.caldav.datastore.query.filter import Filter
from twext.enterprise.dal.record import fromTable
from twext.enterprise.dal.syntax import Delete, Select
from twext.enterprise.jobqueue import WorkItem
from txdav.common.datastore.sql_tables import schema
import datetime

log = Logger()


DEFAULT_BATCH_SIZE = 100
DEFAULT_RETAIN_DAYS = 365



class PrincipalPurgePollingWork(
    WorkItem,
    fromTable(schema.PRINCIPAL_PURGE_POLLING_WORK)
):

    group = "principal_purge_polling"

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items
        yield Delete(From=self.table, Where=None).on(self.transaction)

        # Schedule next update, 7 days out
        notBefore = (
            datetime.datetime.utcnow() +
            datetime.timedelta(days=7)
        )
        log.info(
            "Scheduling next principal purge scan update: {when}", when=notBefore
        )
        yield self.transaction.enqueue(
            PrincipalPurgePollingWork,
            notBefore=notBefore
        )

        # Do the scan
        allUIDs = set()
        for home in (schema.CALENDAR_HOME, schema.ADDRESSBOOK_HOME):
            for [uid] in (
                yield Select(
                    [home.OWNER_UID],
                    From=home
                ).on(self.transaction)
            ):
                allUIDs.add(uid)

        # Spread out the per-uid checks 1 second apart
        seconds = 0
        for uid in allUIDs:
            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=seconds)
            )
            seconds += 1
            yield self.transaction.enqueue(
                PrincipalPurgeCheckWork,
                uid=uid,
                notBefore=notBefore
            )




class PrincipalPurgeCheckWork(
    WorkItem,
    fromTable(schema.PRINCIPAL_PURGE_CHECK_WORK)
):
    """
    Work item for checking for the existence of a UID in the directory
    """

    group = property(lambda self: self.uid)

    @inlineCallbacks
    def doWork(self):

        # Delete any other work items for this UID
        yield Delete(
            From=self.table,
            Where=self.table.UID == self.uid
        ).on(self.transaction)

        log.debug("Checking for existence of {uid} in directory", uid=self.uid)
        directory = self.transaction.store().directoryService()
        record = yield directory.recordWithUID(self.uid)

        if record is None:
            # Schedule purge of this UID a week from now
            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(minutes=1)
            )
            log.warn(
                "Principal {uid} is no longer in the directory; scheduling clean-up at {when}",
                uid=self.uid, when=notBefore
            )
            yield self.transaction.enqueue(
                PrincipalPurgeWork,
                uid=self.uid,
                notBefore=notBefore
            )
        else:
            log.debug("{uid} is still in the directory", uid=self.uid)



class PrincipalPurgeWork(
    WorkItem,
    fromTable(schema.PRINCIPAL_PURGE_WORK)
):
    """
    Work item for purging a UID's data
    """

    group = property(lambda self: self.uid)

    @inlineCallbacks
    def doWork(self):

        # Delete any other work items for this UID
        yield Delete(
            From=self.table,
            Where=self.table.UID == self.uid
        ).on(self.transaction)

        # Check for UID in directory again
        log.debug("One last existence check for {uid}", uid=self.uid)
        directory = self.transaction.store().directoryService()
        record = yield directory.recordWithUID(self.uid)

        if record is None:
            # Time to go
            service = PurgePrincipalService(self.transaction.store)
            log.warn(
                "Cleaning up future events for principal {uid} since they are no longer in directory",
                uid=self.uid
            )
            yield service.purgeUIDs(
                self.transaction.store,
                directory,
                [self.uid],
                completely=False,
                doimplicit=True,
                proxies=True,
                when=None
            )
        else:
            log.debug("{uid} has re-appeared in the directory", uid=self.uid)


@inlineCallbacks
def scheduleNextPrincipalPurgeUpdate(store, seconds):

    notBefore = (
        datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    )

    log.debug(
        "Scheduling next principal purge update: {when}", when=notBefore
    )

    def _enqueue(txn):
        return txn.enqueue(PrincipalPurgePollingWork, notBefore=notBefore)

    wp = yield store.inTransaction("scheduleNextPrincipalPurgeUpdate", _enqueue)

    returnValue(wp)



class PurgeOldEventsService(WorkerService):

    cutoff = None
    batchSize = None
    dryrun = False
    verbose = False

    @classmethod
    def usage(cls, e=None):

        name = os.path.basename(sys.argv[0])
        print("usage: %s [options]" % (name,))
        print("")
        print("  Remove old events from the calendar server")
        print("")
        print("options:")
        print("  -h --help: print this help and exit")
        print("  -f --config <path>: Specify caldavd.plist configuration path")
        print("  -d --days <number>: specify how many days in the past to retain (default=%d)" % (DEFAULT_RETAIN_DAYS,))
        #print("  -b --batch <number>: number of events to remove in each transaction (default=%d)" % (DEFAULT_BATCH_SIZE,))
        print("  -n --dry-run: calculate how many events to purge, but do not purge data")
        print("  -v --verbose: print progress information")
        print("  -D --debug: debug logging")
        print("")

        if e:
            sys.stderr.write("%s\n" % (e,))
            sys.exit(64)
        else:
            sys.exit(0)


    @classmethod
    def main(cls):

        try:
            (optargs, args) = getopt(
                sys.argv[1:], "Dd:b:f:hnv", [
                    "days=",
                    "batch=",
                    "dry-run",
                    "config=",
                    "help",
                    "verbose",
                    "debug",
                ],
            )
        except GetoptError, e:
            cls.usage(e)

        #
        # Get configuration
        #
        configFileName = None
        days = DEFAULT_RETAIN_DAYS
        batchSize = DEFAULT_BATCH_SIZE
        dryrun = False
        verbose = False
        debug = False

        for opt, arg in optargs:
            if opt in ("-h", "--help"):
                cls.usage()

            elif opt in ("-d", "--days"):
                try:
                    days = int(arg)
                except ValueError, e:
                    print("Invalid value for --days: %s" % (arg,))
                    cls.usage(e)

            elif opt in ("-b", "--batch"):
                try:
                    batchSize = int(arg)
                except ValueError, e:
                    print("Invalid value for --batch: %s" % (arg,))
                    cls.usage(e)

            elif opt in ("-v", "--verbose"):
                verbose = True

            elif opt in ("-D", "--debug"):
                debug = True

            elif opt in ("-n", "--dry-run"):
                dryrun = True

            elif opt in ("-f", "--config"):
                configFileName = arg

            else:
                raise NotImplementedError(opt)

        if args:
            cls.usage("Too many arguments: %s" % (args,))

        if dryrun:
            verbose = True

        cutoff = DateTime.getToday()
        cutoff.setDateOnly(False)
        cutoff.offsetDay(-days)
        cls.cutoff = cutoff
        cls.batchSize = batchSize
        cls.dryrun = dryrun
        cls.verbose = verbose

        utilityMain(
            configFileName,
            cls,
            verbose=debug,
        )


    @classmethod
    @inlineCallbacks
    def purgeOldEvents(cls, store, cutoff, batchSize, verbose=False, dryrun=False):

        service = cls(store)
        service.cutoff = cutoff
        service.batchSize = batchSize
        service.dryrun = dryrun
        service.verbose = verbose
        result = yield service.doWork()
        returnValue(result)


    @inlineCallbacks
    def doWork(self):

        if self.dryrun:
            if self.verbose:
                print("(Dry run) Searching for old events...")
            txn = self.store.newTransaction(label="Find old events")
            oldEvents = yield txn.eventsOlderThan(self.cutoff)
            eventCount = len(oldEvents)
            if self.verbose:
                if eventCount == 0:
                    print("No events are older than %s" % (self.cutoff,))
                elif eventCount == 1:
                    print("1 event is older than %s" % (self.cutoff,))
                else:
                    print("%d events are older than %s" % (eventCount, self.cutoff))
            returnValue(eventCount)

        if self.verbose:
            print("Removing events older than %s..." % (self.cutoff,))

        numEventsRemoved = -1
        totalRemoved = 0
        while numEventsRemoved:
            txn = self.store.newTransaction(label="Remove old events")
            numEventsRemoved = yield txn.removeOldEvents(self.cutoff, batchSize=self.batchSize)
            yield txn.commit()
            if numEventsRemoved:
                totalRemoved += numEventsRemoved
                if self.verbose:
                    print("%d," % (totalRemoved,),)

        if self.verbose:
            print("")
            if totalRemoved == 0:
                print("No events were removed")
            elif totalRemoved == 1:
                print("1 event was removed in total")
            else:
                print("%d events were removed in total" % (totalRemoved,))

        returnValue(totalRemoved)



class PurgeAttachmentsService(WorkerService):

    uuid = None
    cutoff = None
    batchSize = None
    dryrun = False
    verbose = False

    @classmethod
    def usage(cls, e=None):

        name = os.path.basename(sys.argv[0])
        print("usage: %s [options]" % (name,))
        print("")
        print("  Remove old or orphaned attachments from the calendar server")
        print("")
        print("options:")
        print("  -h --help: print this help and exit")
        print("  -f --config <path>: Specify caldavd.plist configuration path")
        print("  -u --uuid <owner uid>: target a specific user UID")
        #print("  -b --batch <number>: number of attachments to remove in each transaction (default=%d)" % (DEFAULT_BATCH_SIZE,))
        print("  -d --days <number>: specify how many days in the past to retain (default=%d) zero means no removal of old attachments" % (DEFAULT_RETAIN_DAYS,))
        print("  -n --dry-run: calculate how many attachments to purge, but do not purge data")
        print("  -v --verbose: print progress information")
        print("  -D --debug: debug logging")
        print("")

        if e:
            sys.stderr.write("%s\n" % (e,))
            sys.exit(64)
        else:
            sys.exit(0)


    @classmethod
    def main(cls):

        try:
            (optargs, args) = getopt(
                sys.argv[1:], "Dd:b:f:hnu:v", [
                    "uuid=",
                    "days=",
                    "batch=",
                    "dry-run",
                    "config=",
                    "help",
                    "verbose",
                    "debug",
                ],
            )
        except GetoptError, e:
            cls.usage(e)

        #
        # Get configuration
        #
        configFileName = None
        uuid = None
        days = DEFAULT_RETAIN_DAYS
        batchSize = DEFAULT_BATCH_SIZE
        dryrun = False
        verbose = False
        debug = False

        for opt, arg in optargs:
            if opt in ("-h", "--help"):
                cls.usage()

            elif opt in ("-u", "--uuid"):
                uuid = arg

            elif opt in ("-d", "--days"):
                try:
                    days = int(arg)
                except ValueError, e:
                    print("Invalid value for --days: %s" % (arg,))
                    cls.usage(e)

            elif opt in ("-b", "--batch"):
                try:
                    batchSize = int(arg)
                except ValueError, e:
                    print("Invalid value for --batch: %s" % (arg,))
                    cls.usage(e)

            elif opt in ("-v", "--verbose"):
                verbose = True

            elif opt in ("-D", "--debug"):
                debug = True

            elif opt in ("-n", "--dry-run"):
                dryrun = True

            elif opt in ("-f", "--config"):
                configFileName = arg

            else:
                raise NotImplementedError(opt)

        if args:
            cls.usage("Too many arguments: %s" % (args,))

        if dryrun:
            verbose = True

        cls.uuid = uuid
        if days > 0:
            cutoff = DateTime.getToday()
            cutoff.setDateOnly(False)
            cutoff.offsetDay(-days)
            cls.cutoff = cutoff
        else:
            cls.cutoff = None
        cls.batchSize = batchSize
        cls.dryrun = dryrun
        cls.verbose = verbose

        utilityMain(
            configFileName,
            cls,
            verbose=debug,
        )


    @classmethod
    @inlineCallbacks
    def purgeAttachments(cls, store, uuid, days, limit, dryrun, verbose):

        service = cls(store)
        service.uuid = uuid
        if days > 0:
            cutoff = DateTime.getToday()
            cutoff.setDateOnly(False)
            cutoff.offsetDay(-days)
            service.cutoff = cutoff
        else:
            service.cutoff = None
        service.batchSize = limit
        service.dryrun = dryrun
        service.verbose = verbose
        result = yield service.doWork()
        returnValue(result)


    @inlineCallbacks
    def doWork(self):

        if self.dryrun:
            orphans = yield self._orphansDryRun()
            if self.cutoff is not None:
                dropbox = yield self._dropboxDryRun()
                managed = yield self._managedDryRun()
            else:
                dropbox = ()
                managed = ()

            returnValue(self._dryRunSummary(orphans, dropbox, managed))
        else:
            total = yield self._orphansPurge()
            if self.cutoff is not None:
                total += yield self._dropboxPurge()
                total += yield self._managedPurge()
            returnValue(total)


    @inlineCallbacks
    def _orphansDryRun(self):

        if self.verbose:
            print("(Dry run) Searching for orphaned attachments...")
        txn = self.store.newTransaction(label="Find orphaned attachments")
        orphans = yield txn.orphanedAttachments(self.uuid)
        returnValue(orphans)


    @inlineCallbacks
    def _dropboxDryRun(self):

        if self.verbose:
            print("(Dry run) Searching for old dropbox attachments...")
        txn = self.store.newTransaction(label="Find old dropbox attachments")
        cutoffs = yield txn.oldDropboxAttachments(self.cutoff, self.uuid)
        yield txn.commit()

        returnValue(cutoffs)


    @inlineCallbacks
    def _managedDryRun(self):

        if self.verbose:
            print("(Dry run) Searching for old managed attachments...")
        txn = self.store.newTransaction(label="Find old managed attachments")
        cutoffs = yield txn.oldManagedAttachments(self.cutoff, self.uuid)
        yield txn.commit()

        returnValue(cutoffs)


    def _dryRunSummary(self, orphans, dropbox, managed):

        if self.verbose:
            byuser = {}
            ByUserData = collections.namedtuple(
                'ByUserData',
                ['quota', 'orphanSize', 'orphanCount', 'dropboxSize', 'dropboxCount', 'managedSize', 'managedCount']
            )
            for user, quota, size, count in orphans:
                byuser[user] = ByUserData(quota=quota, orphanSize=size, orphanCount=count, dropboxSize=0, dropboxCount=0, managedSize=0, managedCount=0)
            for user, quota, size, count in dropbox:
                if user in byuser:
                    byuser[user] = byuser[user]._replace(dropboxSize=size, dropboxCount=count)
                else:
                    byuser[user] = ByUserData(quota=quota, orphanSize=0, orphanCount=0, dropboxSize=size, dropboxCount=count, managedSize=0, managedCount=0)
            for user, quota, size, count in managed:
                if user in byuser:
                    byuser[user] = byuser[user]._replace(managedSize=size, managedCount=count)
                else:
                    byuser[user] = ByUserData(quota=quota, orphanSize=0, orphanCount=0, dropboxSize=0, dropboxCount=0, managedSize=size, managedCount=count)

            # Print table of results
            table = tables.Table()
            table.addHeader(("User", "Current Quota", "Orphan Size", "Orphan Count", "Dropbox Size", "Dropbox Count", "Managed Size", "Managed Count", "Total Size", "Total Count"))
            table.setDefaultColumnFormats(
               (
                    tables.Table.ColumnFormat("%s", tables.Table.ColumnFormat.LEFT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                    tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                )
            )

            totals = [0] * 8
            for user, data in sorted(byuser.items(), key=lambda x: x[0]):
                cols = (
                    data.orphanSize,
                    data.orphanCount,
                    data.dropboxSize,
                    data.dropboxCount,
                    data.managedSize,
                    data.managedCount,
                    data.orphanSize + data.dropboxSize + data.managedSize,
                    data.orphanCount + data.dropboxCount + data.managedCount,
                )
                table.addRow((user, data.quota,) + cols)
                for ctr, value in enumerate(cols):
                    totals[ctr] += value
            table.addFooter(("Total:", "",) + tuple(totals))
            total = totals[7]

            print("\n")
            print("Orphaned/Old Attachments by User:\n")
            table.printTable()
        else:
            total = sum([x[3] for x in orphans]) + sum([x[3] for x in dropbox]) + sum([x[3] for x in managed])

        return total


    @inlineCallbacks
    def _orphansPurge(self):

        if self.verbose:
            print("Removing orphaned attachments...",)

        numOrphansRemoved = -1
        totalRemoved = 0
        while numOrphansRemoved:
            txn = self.store.newTransaction(label="Remove orphaned attachments")
            numOrphansRemoved = yield txn.removeOrphanedAttachments(self.uuid, batchSize=self.batchSize)
            yield txn.commit()
            if numOrphansRemoved:
                totalRemoved += numOrphansRemoved
                if self.verbose:
                    print(" %d," % (totalRemoved,),)
            elif self.verbose:
                print("")

        if self.verbose:
            if totalRemoved == 0:
                print("No orphaned attachments were removed")
            elif totalRemoved == 1:
                print("1 orphaned attachment was removed in total")
            else:
                print("%d orphaned attachments were removed in total" % (totalRemoved,))
            print("")

        returnValue(totalRemoved)


    @inlineCallbacks
    def _dropboxPurge(self):

        if self.verbose:
            print("Removing old dropbox attachments...",)

        numOldRemoved = -1
        totalRemoved = 0
        while numOldRemoved:
            txn = self.store.newTransaction(label="Remove old dropbox attachments")
            numOldRemoved = yield txn.removeOldDropboxAttachments(self.cutoff, self.uuid, batchSize=self.batchSize)
            yield txn.commit()
            if numOldRemoved:
                totalRemoved += numOldRemoved
                if self.verbose:
                    print(" %d," % (totalRemoved,),)
            elif self.verbose:
                print("")

        if self.verbose:
            if totalRemoved == 0:
                print("No old dropbox attachments were removed")
            elif totalRemoved == 1:
                print("1 old dropbox attachment was removed in total")
            else:
                print("%d old dropbox attachments were removed in total" % (totalRemoved,))
            print("")

        returnValue(totalRemoved)


    @inlineCallbacks
    def _managedPurge(self):

        if self.verbose:
            print("Removing old managed attachments...",)

        numOldRemoved = -1
        totalRemoved = 0
        while numOldRemoved:
            txn = self.store.newTransaction(label="Remove old managed attachments")
            numOldRemoved = yield txn.removeOldManagedAttachments(self.cutoff, self.uuid, batchSize=self.batchSize)
            yield txn.commit()
            if numOldRemoved:
                totalRemoved += numOldRemoved
                if self.verbose:
                    print(" %d," % (totalRemoved,),)
            elif self.verbose:
                print("")

        if self.verbose:
            if totalRemoved == 0:
                print("No old managed attachments were removed")
            elif totalRemoved == 1:
                print("1 old managed attachment was removed in total")
            else:
                print("%d old managed attachments were removed in total" % (totalRemoved,))
            print("")

        returnValue(totalRemoved)



class PurgePrincipalService(WorkerService):

    root = None
    directory = None
    uids = None
    dryrun = False
    verbose = False
    completely = False
    doimplicit = True
    proxies = True
    when = None

    @classmethod
    def usage(cls, e=None):

        name = os.path.basename(sys.argv[0])
        print("usage: %s [options]" % (name,))
        print("")
        print("  Remove a principal's events and contacts from the calendar server")
        print("")
        print("options:")
        print("  -c --completely: By default, only future events are canceled; this option cancels all events")
        print("  -h --help: print this help and exit")
        print("  -f --config <path>: Specify caldavd.plist configuration path")
        print("  -n --dry-run: calculate how many events and contacts to purge, but do not purge data")
        print("  -v --verbose: print progress information")
        print("  -D --debug: debug logging")
        print("")

        if e:
            sys.stderr.write("%s\n" % (e,))
            sys.exit(64)
        else:
            sys.exit(0)


    @classmethod
    def main(cls):

        try:
            (optargs, args) = getopt(
                sys.argv[1:], "cDf:hnv", [
                    "completely",
                    "dry-run",
                    "config=",
                    "help",
                    "verbose",
                    "debug",
                    "noimplicit",
                ],
            )
        except GetoptError, e:
            cls.usage(e)

        #
        # Get configuration
        #
        configFileName = None
        dryrun = False
        verbose = False
        debug = False
        completely = False
        doimplicit = True

        for opt, arg in optargs:
            if opt in ("-h", "--help"):
                cls.usage()

            elif opt in ("-c", "--completely"):
                completely = True

            elif opt in ("-v", "--verbose"):
                verbose = True

            elif opt in ("-D", "--debug"):
                debug = True

            elif opt in ("-n", "--dry-run"):
                dryrun = True

            elif opt in ("-f", "--config"):
                configFileName = arg

            elif opt in ("--noimplicit"):
                doimplicit = False

            else:
                raise NotImplementedError(opt)

        # args is a list of uids
        cls.uids = args
        cls.completely = completely
        cls.dryrun = dryrun
        cls.verbose = verbose
        cls.doimplicit = doimplicit

        utilityMain(
            configFileName,
            cls,
            verbose=debug,
        )


    @classmethod
    @inlineCallbacks
    def purgeUIDs(cls, store, directory, uids, verbose=False, dryrun=False,
                  completely=False, doimplicit=True, proxies=True, when=None):

        service = cls(store)
        service.directory = directory
        service.uids = uids
        service.verbose = verbose
        service.dryrun = dryrun
        service.completely = completely
        service.doimplicit = doimplicit
        service.proxies = proxies
        service.when = when
        result = yield service.doWork()
        returnValue(result)


    @inlineCallbacks
    def doWork(self):

        if self.directory is None:
            self.directory = self.store.directoryService()

        total = 0

        for uid in self.uids:
            count = yield self._purgeUID(uid)
            total += count

        if self.verbose:
            amount = "%d event%s" % (total, "s" if total > 1 else "")
            if self.dryrun:
                print("Would have modified or deleted %s" % (amount,))
            else:
                print("Modified or deleted %s" % (amount,))

        returnValue(total)


    @inlineCallbacks
    def _purgeUID(self, uid):

        if self.when is None:
            self.when = DateTime.getNowUTC()

        # Does the record exist?
        record = yield self.directory.recordWithUID(uid)
        # MOVE2WHO
        # if record is None:
            # The user has already been removed from the directory service.  We
            # need to fashion a temporary, fake record

            # FIXME: probably want a more elegant way to accomplish this,
            # since it requires the aggregate directory to examine these first:
            # record = DirectoryRecord(self.directory, "users", uid, shortNames=(uid,), enabledForCalendaring=True)
            # self.directory._tmpRecords["shortNames"][uid] = record
            # self.directory._tmpRecords["uids"][uid] = record

        # Override augments settings for this record
        record.hasCalendars = True
        record.hasContacts = True

        cua = record.canonicalCalendarUserAddress()

        # See if calendar home is provisioned
        txn = self.store.newTransaction()
        storeCalHome = yield txn.calendarHomeWithUID(uid)
        calHomeProvisioned = storeCalHome is not None

        # If in "completely" mode, unshare collections, remove notifications
        if calHomeProvisioned and self.completely:
            yield self._cleanHome(txn, storeCalHome)

        yield txn.commit()

        count = 0

        if calHomeProvisioned:
            count = yield self._cancelEvents(txn, uid, cua)

        # Remove empty calendar collections (and calendar home if no more
        # calendars)
        yield self._removeCalendarHome(uid)

        # Remove VCards
        count += (yield self._removeAddressbookHome(uid))

        if self.proxies and not self.dryrun:
            if self.verbose:
                print("Deleting any proxy assignments")
            yield self._purgeProxyAssignments(self.store, record)

        returnValue(count)


    @inlineCallbacks
    def _cleanHome(self, txn, storeCalHome):

        # Process shared and shared-to-me calendars
        children = list((yield storeCalHome.children()))
        for child in children:
            if self.verbose:
                if self.dryrun:
                    print("Would unshare: %s" % (child.name(),))
                else:
                    print("Unsharing: %s" % (child.name(),))
            if not self.dryrun:
                yield child.unshare()

        if not self.dryrun:
            yield storeCalHome.removeUnacceptedShares()
            notificationHome = yield txn.notificationsWithUID(storeCalHome.uid())
            if notificationHome is not None:
                yield notificationHome.remove()


    @inlineCallbacks
    def _cancelEvents(self, txn, uid, cua):

        # Anything in the past is left alone
        whenString = self.when.getText()
        query_filter = caldavxml.Filter(
              caldavxml.ComponentFilter(
                  caldavxml.ComponentFilter(
                      caldavxml.TimeRange(start=whenString,),
                      name=("VEVENT",),
                  ),
                  name="VCALENDAR",
               )
          )
        query_filter = Filter(query_filter)

        count = 0
        txn = self.store.newTransaction()
        storeCalHome = yield txn.calendarHomeWithUID(uid)
        calendarNames = yield storeCalHome.listCalendars()
        yield txn.commit()

        for calendarName in calendarNames:

            txn = self.store.newTransaction(authz_uid=uid)
            storeCalHome = yield txn.calendarHomeWithUID(uid)
            calendar = yield storeCalHome.calendarWithName(calendarName)
            childNames = []

            if self.completely:
                # all events
                for childName in (yield calendar.listCalendarObjects()):
                    childNames.append(childName)
            else:
                # events matching filter
                for childName, _ignore_childUid, _ignore_childType in (yield calendar.search(query_filter)):
                    childNames.append(childName)
            yield txn.commit()

            for childName in childNames:

                txn = self.store.newTransaction(authz_uid=uid)
                storeCalHome = yield txn.calendarHomeWithUID(uid)
                calendar = yield storeCalHome.calendarWithName(calendarName)

                try:
                    childResource = yield calendar.calendarObjectWithName(childName)

                    # Always delete inbox items
                    if self.completely or calendar.isInbox():
                        action = self.CANCELEVENT_SHOULD_DELETE
                    else:
                        event = yield childResource.componentForUser()
                        action = self._cancelEvent(event, self.when, cua)

                    uri = "/calendars/__uids__/%s/%s/%s" % (storeCalHome.uid(), calendar.name(), childName)
                    if action == self.CANCELEVENT_MODIFIED:
                        if self.verbose:
                            if self.dryrun:
                                print("Would modify: %s" % (uri,))
                            else:
                                print("Modifying: %s" % (uri,))
                        if not self.dryrun:
                            yield childResource.setComponent(event)
                        count += 1

                    elif action == self.CANCELEVENT_SHOULD_DELETE:
                        incrementCount = self.dryrun
                        if self.verbose:
                            if self.dryrun:
                                print("Would delete: %s" % (uri,))
                            else:
                                print("Deleting: %s" % (uri,))
                        if not self.dryrun:
                            retry = False
                            try:
                                yield childResource.remove(implicitly=self.doimplicit)
                                incrementCount = True
                            except Exception, e:
                                print("Exception deleting %s: %s" % (uri, str(e)))
                                retry = True

                            if retry and self.doimplicit:
                                # Try again with implicit scheduling off
                                print("Retrying deletion of %s with implicit scheduling turned off" % (uri, childName))
                                try:
                                    yield childResource.remove(implicitly=False)
                                    incrementCount = True
                                except Exception, e:
                                    print("Still couldn't delete %s even with implicit scheduling turned off: %s" % (uri, str(e)))

                        if incrementCount:
                            count += 1

                    # Commit
                    yield txn.commit()

                except Exception, e:
                    # Abort
                    yield txn.abort()
                    raise e

        returnValue(count)


    @inlineCallbacks
    def _removeCalendarHome(self, uid):

        try:
            txn = self.store.newTransaction(authz_uid=uid)

            # Remove empty calendar collections (and calendar home if no more
            # calendars)
            storeCalHome = yield txn.calendarHomeWithUID(uid)
            if storeCalHome is not None:
                calendars = list((yield storeCalHome.calendars()))
                remainingCalendars = len(calendars)
                for calColl in calendars:
                    if len(list((yield calColl.calendarObjects()))) == 0:
                        remainingCalendars -= 1
                        calendarName = calColl.name()
                        if self.verbose:
                            if self.dryrun:
                                print("Would delete calendar: %s" % (calendarName,))
                            else:
                                print("Deleting calendar: %s" % (calendarName,))
                        if not self.dryrun:
                            if calColl.owned():
                                yield storeCalHome.removeChildWithName(calendarName)
                            else:
                                yield calColl.unshare()

                if not remainingCalendars:
                    if self.verbose:
                        if self.dryrun:
                            print("Would delete calendar home")
                        else:
                            print("Deleting calendar home")
                    if not self.dryrun:
                        yield storeCalHome.remove()

            # Commit
            yield txn.commit()

        except Exception, e:
            # Abort
            yield txn.abort()
            raise e


    @inlineCallbacks
    def _removeAddressbookHome(self, uid):

        count = 0
        txn = self.store.newTransaction(authz_uid=uid)

        try:
            # Remove VCards
            storeAbHome = yield txn.addressbookHomeWithUID(uid)
            if storeAbHome is not None:
                for abColl in list((yield storeAbHome.addressbooks())):
                    for card in list((yield abColl.addressbookObjects())):
                        cardName = card.name()
                        if self.verbose:
                            uri = "/addressbooks/__uids__/%s/%s/%s" % (uid, abColl.name(), cardName)
                            if self.dryrun:
                                print("Would delete: %s" % (uri,))
                            else:
                                print("Deleting: %s" % (uri,))
                        if not self.dryrun:
                            yield card.remove()
                        count += 1
                    abName = abColl.name()
                    if self.verbose:
                        if self.dryrun:
                            print("Would delete addressbook: %s" % (abName,))
                        else:
                            print("Deleting addressbook: %s" % (abName,))
                    if not self.dryrun:
                        # Also remove the addressbook collection itself
                        if abColl.owned():
                            yield storeAbHome.removeChildWithName(abName)
                        else:
                            yield abColl.unshare()

                if self.verbose:
                    if self.dryrun:
                        print("Would delete addressbook home")
                    else:
                        print("Deleting addressbook home")
                if not self.dryrun:
                    yield storeAbHome.remove()

            # Commit
            yield txn.commit()

        except Exception, e:
            # Abort
            yield txn.abort()
            raise e

        returnValue(count)

    CANCELEVENT_SKIPPED = 1
    CANCELEVENT_MODIFIED = 2
    CANCELEVENT_NOT_MODIFIED = 3
    CANCELEVENT_SHOULD_DELETE = 4

    @classmethod
    def _cancelEvent(cls, event, when, cua):
        """
        Modify a VEVENT such that all future occurrences are removed

        @param event: the event to modify
        @type event: L{twistedcaldav.ical.Component}

        @param when: the cutoff date (anything after which is removed)
        @type when: DateTime

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
            return cls.CANCELEVENT_SKIPPED

        main = event.mainComponent()

        # Anything completely in the future is deleted
        dtstart = main.getStartDateUTC()
        isDateTime = not dtstart.isDateOnly()
        if dtstart > when:
            return cls.CANCELEVENT_SHOULD_DELETE

        organizer = main.getOrganizer()

        # Non-meetings are deleted
        if organizer is None:
            return cls.CANCELEVENT_SHOULD_DELETE

        # Meetings which cua is merely an attendee are deleted (thus implicitly
        # declined)
        # FIXME: I think we want to decline anything after the cut-off, not delete
        # the whole event.
        if organizer != cua:
            return cls.CANCELEVENT_SHOULD_DELETE

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
            return cls.CANCELEVENT_MODIFIED
        else:
            return cls.CANCELEVENT_NOT_MODIFIED


    @inlineCallbacks
    def _purgeProxyAssignments(self, store, record):

        txn = store.newTransaction()
        for readWrite in (True, False):
            yield txn.removeDelegates(record.uid, readWrite)
            yield txn.removeDelegateGroupss(record.uid, readWrite)
        yield txn.commit()
