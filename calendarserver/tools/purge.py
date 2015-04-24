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

from calendarserver.tools import tables
from calendarserver.tools.cmdline import utilityMain, WorkerService
from calendarserver.tools.util import removeProxy

from getopt import getopt, GetoptError

from pycalendar.datetime import PyCalendarDateTime

from twext.enterprise.dal.syntax import Select, Parameter, Max
from twext.python.log import Logger

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from twistedcaldav.config import config
from twistedcaldav.dateops import parseSQLDateToPyCalendar, pyCalendarTodatetime
from twistedcaldav.directory.directory import DirectoryRecord
from twistedcaldav.ical import Component, InvalidICalendarDataError
from twistedcaldav.query import calendarqueryfilter

from txdav.common.datastore.sql_tables import schema, _BIND_MODE_OWN
from txdav.xml import element as davxml

import collections
import os
import sys

log = Logger()

DEFAULT_BATCH_SIZE = 100
DEFAULT_RETAIN_DAYS = 365



class PurgeOldEventsService(WorkerService):

    uuid = None
    cutoff = None
    batchSize = None
    dryrun = False
    debug = False

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
        print("  -u --uuid <uuid>: Only process this user(s) [REQUIRED]")
        print("  -d --days <number>: specify how many days in the past to retain (default=%d)" % (DEFAULT_RETAIN_DAYS,))
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
                sys.argv[1:], "Dd:b:f:hnu:v", [
                    "days=",
                    "batch=",
                    "dry-run",
                    "config=",
                    "uuid=",
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

            elif opt in ("-u", "--uuid"):
                uuid = arg

            else:
                raise NotImplementedError(opt)

        if args:
            cls.usage("Too many arguments: %s" % (args,))

        if uuid is None:
            cls.usage("uuid must be specified")
        cls.uuid = uuid

        if dryrun:
            verbose = True

        cutoff = PyCalendarDateTime.getToday()
        cutoff.setDateOnly(False)
        cutoff.offsetDay(-days)
        cls.cutoff = cutoff
        cls.batchSize = batchSize
        cls.dryrun = dryrun
        cls.debug = debug

        utilityMain(
            configFileName,
            cls,
            verbose=verbose,
        )


    @classmethod
    @inlineCallbacks
    def purgeOldEvents(cls, store, uuid, cutoff, batchSize, debug=False, dryrun=False):

        service = cls(store)
        service.uuid = uuid
        service.cutoff = cutoff
        service.batchSize = batchSize
        service.dryrun = dryrun
        service.debug = debug
        result = (yield service.doWork())
        returnValue(result)


    @inlineCallbacks
    def getMatchingHomeUIDs(self):
        """
        Find all the calendar homes that match the uuid cli argument.
        """
        log.debug("Searching for calendar homes matching: '{}'".format(self.uuid))
        txn = self.store.newTransaction(label="Find matching homes")
        ch = schema.CALENDAR_HOME
        if self.uuid:
            kwds = {"uuid": self.uuid}
            rows = (yield Select(
                [ch.RESOURCE_ID, ch.OWNER_UID, ],
                From=ch,
                Where=(ch.OWNER_UID.StartsWith(Parameter("uuid"))),
            ).on(txn, **kwds))
        else:
            rows = (yield Select(
                [ch.RESOURCE_ID, ch.OWNER_UID, ],
                From=ch,
            ).on(txn))

        yield txn.commit()
        log.debug("  Found {} calendar homes".format(len(rows)))
        returnValue(sorted(rows, key=lambda x: x[1]))


    @inlineCallbacks
    def getMatchingCalendarIDs(self, home_id, owner_uid):
        """
        Find all the owned calendars for the specified calendar home.

        @param home_id: resource-id of calendar home to check
        @type home_id: L{int}
        @param owner_uid: owner UUID of home to check
        @type owner_uid: L{str}
        """
        log.debug("Checking calendar home: {} '{}'".format(home_id, owner_uid))
        txn = self.store.newTransaction(label="Find matching calendars")
        cb = schema.CALENDAR_BIND
        kwds = {"home_id": home_id}
        rows = (yield Select(
            [cb.CALENDAR_RESOURCE_ID, cb.CALENDAR_RESOURCE_NAME, ],
            From=cb,
            Where=(cb.CALENDAR_HOME_RESOURCE_ID == Parameter("home_id")).And(
                cb.BIND_MODE == _BIND_MODE_OWN
            ),
        ).on(txn, **kwds))
        yield txn.commit()
        log.debug("  Found {} calendars".format(len(rows)))
        returnValue(rows)


    PurgeEvent = collections.namedtuple("PurgeEvent", ("home", "calendar", "resource",))

    @inlineCallbacks
    def getResourceIDsToPurge(self, home_id, calendar_id, calendar_name):
        """
        For the given calendar find which calendar objects are older than the cut-off and return the
        resource-ids of those.

        @param home_id: resource-id of calendar home
        @type home_id: L{int}
        @param calendar_id: resource-id of the calendar to check
        @type calendar_id: L{int}
        @param calendar_name: name of the calendar to check
        @type calendar_name: L{str}
        """

        log.debug("  Checking calendar: {} '{}'".format(calendar_id, calendar_name))
        purge = set()
        txn = self.store.newTransaction(label="Find matching resources")
        co = schema.CALENDAR_OBJECT
        tr = schema.TIME_RANGE
        kwds = {"calendar_id": calendar_id}
        rows = (yield Select(
            [co.RESOURCE_ID, co.RECURRANCE_MAX, co.RECURRANCE_MIN, Max(tr.END_DATE)],
            From=co.join(tr, on=(co.RESOURCE_ID == tr.CALENDAR_OBJECT_RESOURCE_ID)),
            Where=(co.CALENDAR_RESOURCE_ID == Parameter("calendar_id")).And(
                co.ICALENDAR_TYPE == "VEVENT"
            ),
            GroupBy=(co.RESOURCE_ID, co.RECURRANCE_MAX, co.RECURRANCE_MIN,),
            Having=(
                (co.RECURRANCE_MAX == None).And(Max(tr.END_DATE) < pyCalendarTodatetime(self.cutoff))
            ).Or(
                (co.RECURRANCE_MAX != None).And(co.RECURRANCE_MAX < pyCalendarTodatetime(self.cutoff))
            ),
        ).on(txn, **kwds))

        log.debug("    Found {} resources to check".format(len(rows)))
        for resource_id, recurrence_max, recurrence_min, max_end_date in rows:

            recurrence_max = parseSQLDateToPyCalendar(recurrence_max) if recurrence_max else None
            recurrence_min = parseSQLDateToPyCalendar(recurrence_min) if recurrence_min else None
            max_end_date = parseSQLDateToPyCalendar(max_end_date) if max_end_date else None

            # Find events where we know the max(end_date) represents a valid,
            # untruncated expansion
            if recurrence_min is None or recurrence_min < self.cutoff:
                if recurrence_max is None:
                    # Here we know max_end_date is the fully expand final instance
                    if max_end_date < self.cutoff:
                        purge.add(self.PurgeEvent(home_id, calendar_id, resource_id,))
                    continue
                elif recurrence_max > self.cutoff:
                    # Here we know that there are instances newer than the cut-off
                    # but they have not yet been indexed out that far
                    continue

            # Manually detect the max_end_date from the actual calendar data
            calendar = yield self.getCalendar(txn, resource_id)
            if calendar is not None:
                if self.checkLastInstance(calendar):
                    purge.add(self.PurgeEvent(home_id, calendar_id, resource_id,))

        yield txn.commit()
        log.debug("    Found {} resources to purge".format(len(purge)))
        returnValue(purge)


    @inlineCallbacks
    def getCalendar(self, txn, resid):
        """
        Get the calendar data for a calendar object resource.

        @param resid: resource-id of the calendar object resource to load
        @type resid: L{int}
        """
        co = schema.CALENDAR_OBJECT
        kwds = {"ResourceID" : resid}
        rows = (yield Select(
            [co.ICALENDAR_TEXT],
            From=co,
            Where=(
                co.RESOURCE_ID == Parameter("ResourceID")
            ),
        ).on(txn, **kwds))
        try:
            caldata = Component.fromString(rows[0][0]) if rows else None
        except InvalidICalendarDataError:
            returnValue(None)

        returnValue(caldata)


    def checkLastInstance(self, calendar):
        """
        Determine the last instance of a calendar event. Try a "static" analysis of the data first,
        and only if needed, do an instance expansion.

        @param calendar: the calendar object to examine
        @type calendar: L{Component}
        """

        # Is it recurring
        master = calendar.masterComponent()
        if not calendar.isRecurring() or master is None:
            # Just check the end date
            for comp in calendar.subcomponents():
                if comp.name() == "VEVENT":
                    if comp.getEndDateUTC() > self.cutoff:
                        return False
            else:
                return True
        elif calendar.isRecurringUnbounded():
            return False
        else:
            # First test all sub-components
            # Just check the end date
            for comp in calendar.subcomponents():
                if comp.name() == "VEVENT":
                    if comp.getEndDateUTC() > self.cutoff:
                        return False

            # If we get here we need to test the RRULE - if there is an until use
            # that as the end point, if a count, we have to expand
            rrules = tuple(master.properties("RRULE"))
            if len(rrules):
                if rrules[0].value().getUseUntil():
                    return rrules[0].value().getUntil() < self.cutoff
                else:
                    return not calendar.hasInstancesAfter(self.cutoff)

        return True


    @inlineCallbacks
    def getResourcesToPurge(self, home_id, owner_uid):
        """
        Find all the resource-ids of calendar object resources that need to be purged in the specified home.

        @param home_id: resource-id of calendar home to check
        @type home_id: L{int}
        @param owner_uid: owner UUID of home to check
        @type owner_uid: L{str}
        """

        purge = set()
        calendars = yield self.getMatchingCalendarIDs(home_id, owner_uid)
        for calendar_id, calendar_name in calendars:
            purge.update((yield self.getResourceIDsToPurge(home_id, calendar_id, calendar_name)))

        returnValue(purge)


    @inlineCallbacks
    def purgeResources(self, events):
        """
        Remove up to batchSize events and return how
        many were removed.
        """

        txn = self.store.newTransaction(label="Remove old events")
        count = 0
        last_home = None
        last_calendar = None
        for event in events:
            if event.home != last_home:
                home = (yield txn.calendarHomeWithResourceID(event.home))
                last_home = event.home
            if event.calendar != last_calendar:
                calendar = (yield home.childWithID(event.calendar))
                last_calendar = event.calendar
            resource = (yield calendar.objectResourceWithID(event.resource))
            yield resource.remove(implicitly=False)
            log.debug("Removed resource {} '{}' from calendar {} '{}' of calendar home '{}'".format(
                resource.id(),
                resource.name(),
                resource.parentCollection().id(),
                resource.parentCollection().name(),
                resource.parentCollection().ownerHome().uid()
            ))
            count += 1
        yield txn.commit()
        returnValue(count)


    @inlineCallbacks
    def doWork(self):

        if self.debug:
            # Turn on debug logging for this module
            config.LogLevels[__name__] = "debug"
        else:
            config.LogLevels[__name__] = "info"
        config.update()

        homes = yield self.getMatchingHomeUIDs()
        if not homes:
            log.info("No homes to process")
            returnValue(0)

        if self.dryrun:
            log.info("Purge dry run only")

        log.info("Searching for old events...")

        purge = set()
        homes = yield self.getMatchingHomeUIDs()
        for home_id, owner_uid in homes:
            purge.update((yield self.getResourcesToPurge(home_id, owner_uid)))

        if self.dryrun:
            eventCount = len(purge)
            if eventCount == 0:
                log.info("No events are older than %s" % (self.cutoff,))
            elif eventCount == 1:
                log.info("1 event is older than %s" % (self.cutoff,))
            else:
                log.info("%d events are older than %s" % (eventCount, self.cutoff))
            returnValue(eventCount)

        purge = list(purge)
        purge.sort()
        totalEvents = len(purge)

        log.info("Removing {} events older than {}...".format(len(purge), self.cutoff,))

        numEventsRemoved = -1
        totalRemoved = 0
        while numEventsRemoved:
            numEventsRemoved = (yield self.purgeResources(purge[:self.batchSize]))
            if numEventsRemoved:
                totalRemoved += numEventsRemoved
                log.debug("  Removed {} of {} events...".format(totalRemoved, totalEvents))
                purge = purge[numEventsRemoved:]

        if totalRemoved == 0:
            log.info("No events were removed")
        elif totalRemoved == 1:
            log.info("1 event was removed in total")
        else:
            log.info("%d events were removed in total" % (totalRemoved,))

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
            cutoff = PyCalendarDateTime.getToday()
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
            cutoff = PyCalendarDateTime.getToday()
            cutoff.setDateOnly(False)
            cutoff.offsetDay(-days)
            service.cutoff = cutoff
        else:
            service.cutoff = None
        service.batchSize = limit
        service.dryrun = dryrun
        service.verbose = verbose
        result = (yield service.doWork())
        returnValue(result)


    @inlineCallbacks
    def doWork(self):

        if self.dryrun:
            orphans = (yield self._orphansDryRun())
            if self.cutoff is not None:
                dropbox = (yield self._dropboxDryRun())
                managed = (yield self._managedDryRun())
            else:
                dropbox = ()
                managed = ()

            returnValue(self._dryRunSummary(orphans, dropbox, managed))
        else:
            total = (yield self._orphansPurge())
            if self.cutoff is not None:
                total += (yield self._dropboxPurge())
                total += (yield self._managedPurge())
            returnValue(total)


    @inlineCallbacks
    def _orphansDryRun(self):

        if self.verbose:
            print("(Dry run) Searching for orphaned attachments...")
        txn = self.store.newTransaction(label="Find orphaned attachments")
        orphans = (yield txn.orphanedAttachments(self.uuid))
        returnValue(orphans)


    @inlineCallbacks
    def _dropboxDryRun(self):

        if self.verbose:
            print("(Dry run) Searching for old dropbox attachments...")
        txn = self.store.newTransaction(label="Find old dropbox attachments")
        cutoffs = (yield txn.oldDropboxAttachments(self.cutoff, self.uuid))
        yield txn.commit()

        returnValue(cutoffs)


    @inlineCallbacks
    def _managedDryRun(self):

        if self.verbose:
            print("(Dry run) Searching for old managed attachments...")
        txn = self.store.newTransaction(label="Find old managed attachments")
        cutoffs = (yield txn.oldManagedAttachments(self.cutoff, self.uuid))
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
            table.setDefaultColumnFormats((
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
            ))

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
            numOrphansRemoved = (yield txn.removeOrphanedAttachments(self.uuid, batchSize=self.batchSize))
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
            numOldRemoved = (yield txn.removeOldDropboxAttachments(self.cutoff, self.uuid, batchSize=self.batchSize))
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
            numOldRemoved = (yield txn.removeOldManagedAttachments(self.cutoff, self.uuid, batchSize=self.batchSize))
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
    def purgeUIDs(cls, store, directory, root, uids, verbose=False, dryrun=False,
                  completely=False, doimplicit=True, proxies=True, when=None):

        service = cls(store)
        service.root = root
        service.directory = directory
        service.uids = uids
        service.verbose = verbose
        service.dryrun = dryrun
        service.completely = completely
        service.doimplicit = doimplicit
        service.proxies = proxies
        service.when = when
        result = (yield service.doWork())
        returnValue(result)


    @inlineCallbacks
    def doWork(self):

        if self.root is None:
            self.root = self.rootResource()
        if self.directory is None:
            self.directory = self.root.getDirectory()

        total = 0

        allAssignments = {}

        for uid in self.uids:
            count, allAssignments[uid] = (yield self._purgeUID(uid))
            total += count

        if self.verbose:
            amount = "%d event%s" % (total, "s" if total > 1 else "")
            if self.dryrun:
                print("Would have modified or deleted %s" % (amount,))
            else:
                print("Modified or deleted %s" % (amount,))

        returnValue((total, allAssignments,))


    @inlineCallbacks
    def _purgeUID(self, uid):

        if self.when is None:
            self.when = PyCalendarDateTime.getNowUTC()

        # Does the record exist?
        record = self.directory.recordWithUID(uid)
        if record is None:
            # The user has already been removed from the directory service.  We
            # need to fashion a temporary, fake record

            # FIXME: probably want a more elegant way to accomplish this,
            # since it requires the aggregate directory to examine these first:
            record = DirectoryRecord(self.directory, "users", uid, shortNames=(uid,), enabledForCalendaring=True)
            self.directory._tmpRecords["shortNames"][uid] = record
            self.directory._tmpRecords["uids"][uid] = record

        # Override augments settings for this record
        record.enabled = True
        record.enabledForCalendaring = True
        record.enabledForAddressBooks = True

        cua = "urn:uuid:%s" % (uid,)

        principalCollection = self.directory.principalCollection
        principal = principalCollection.principalForRecord(record)

        # See if calendar home is provisioned
        txn = self.store.newTransaction()
        storeCalHome = (yield txn.calendarHomeWithUID(uid))
        calHomeProvisioned = storeCalHome is not None

        # If in "completely" mode, unshare collections, remove notifications
        if calHomeProvisioned and self.completely:
            yield self._cleanHome(txn, storeCalHome)

        yield txn.commit()

        count = 0
        assignments = []

        if calHomeProvisioned:
            count = (yield self._cancelEvents(txn, uid, cua))

        # Remove empty calendar collections (and calendar home if no more
        # calendars)
        yield self._removeCalendarHome(uid)

        # Remove VCards
        count += (yield self._removeAddressbookHome(uid))

        if self.proxies and not self.dryrun:
            if self.verbose:
                print("Deleting any proxy assignments")
            assignments = (yield self._purgeProxyAssignments(principal))

        returnValue((count, assignments))


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
                (yield child.unshare())

        if not self.dryrun:
            (yield storeCalHome.removeUnacceptedShares())
            notificationHome = (yield txn.notificationsWithUID(storeCalHome.uid()))
            if notificationHome is not None:
                (yield notificationHome.remove())


    @inlineCallbacks
    def _cancelEvents(self, txn, uid, cua):

        # Anything in the past is left alone
        whenString = self.when.getText()
        query_filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                caldavxml.ComponentFilter(
                    TimeRange(start=whenString,),
                    name=("VEVENT",),
                ),
                name="VCALENDAR",
            )
        )
        query_filter = calendarqueryfilter.Filter(query_filter)

        count = 0
        txn = self.store.newTransaction()
        storeCalHome = (yield txn.calendarHomeWithUID(uid))
        calendarNames = (yield storeCalHome.listCalendars())
        yield txn.commit()

        for calendarName in calendarNames:

            txn = self.store.newTransaction(authz_uid=uid)
            storeCalHome = (yield txn.calendarHomeWithUID(uid))
            calendar = (yield storeCalHome.calendarWithName(calendarName))
            childNames = []

            if self.completely:
                # all events
                for childName in (yield calendar.listCalendarObjects()):
                    childNames.append(childName)
            else:
                # events matching filter
                for childName, _ignore_childUid, _ignore_childType in (yield calendar._index.indexedSearch(query_filter)):
                    childNames.append(childName)
            yield txn.commit()

            for childName in childNames:

                txn = self.store.newTransaction(authz_uid=uid)
                storeCalHome = (yield txn.calendarHomeWithUID(uid))
                calendar = (yield storeCalHome.calendarWithName(calendarName))

                try:
                    childResource = (yield calendar.calendarObjectWithName(childName))

                    # Always delete inbox items
                    if self.completely or calendar.isInbox():
                        action = self.CANCELEVENT_SHOULD_DELETE
                    else:
                        event = (yield childResource.componentForUser())
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
            storeCalHome = (yield txn.calendarHomeWithUID(uid))
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
                        (yield storeCalHome.remove())

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
            storeAbHome = (yield txn.addressbookHomeWithUID(uid))
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
                            (yield card.remove())
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
                    (yield storeAbHome.remove())

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
    def _purgeProxyAssignments(self, principal):

        assignments = []

        for proxyType in ("read", "write"):

            proxyFor = (yield principal.proxyFor(proxyType == "write"))
            for other in proxyFor:
                assignments.append((principal.record.uid, proxyType, other.record.uid))
                (yield removeProxy(self.root, self.directory, self.store, other, principal))

            subPrincipal = principal.getChild("calendar-proxy-" + proxyType)
            proxies = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))
            for other in proxies.children:
                assignments.append((str(other).split("/")[3], proxyType, principal.record.uid))

            (yield subPrincipal.writeProperty(davxml.GroupMemberSet(), None))

        returnValue(assignments)
