# -*- test-case-name: txdav.common.datastore.work.test.test_revision_cleanup -*-
##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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
Remove orphaned and old inbox items, and inbox items references old events
"""

from twext.enterprise.dal.record import fromTable
from twext.enterprise.dal.syntax import Select, Count
from twext.enterprise.jobqueue import WorkItem, RegeneratingWorkItem
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, succeed
from twistedcaldav.config import config
from txdav.common.datastore.sql_tables import schema, _HOME_STATUS_NORMAL
import datetime

log = Logger()


class InboxCleanupWork(RegeneratingWorkItem, fromTable(schema.INBOX_CLEANUP_WORK)):

    group = "inbox_cleanup"

    @classmethod
    def initialSchedule(cls, store, seconds):
        def _enqueue(txn):
            return InboxCleanupWork.reschedule(txn, seconds)

        if config.InboxCleanup.Enabled:
            return store.inTransaction("InboxCleanupWork.initialSchedule", _enqueue)
        else:
            return succeed(None)


    def regenerateInterval(self):
        """
        Return the interval in seconds between regenerating instances.
        """
        return float(config.InboxCleanup.CleanupPeriodDays) * 24 * 60 * 60


    @inlineCallbacks
    def doWork(self):

        # exit if not done with last delete:
        coiw = schema.CLEANUP_ONE_INBOX_WORK
        queuedCleanupOneInboxWorkItems = (yield Select(
            [Count(coiw.HOME_ID)],
            From=coiw,
        ).on(self.transaction))[0][0]

        if queuedCleanupOneInboxWorkItems:
            log.error("Inbox cleanup work: Can't schedule per home cleanup because {} work items still queued.".format(
                queuedCleanupOneInboxWorkItems))
        else:
            # enumerate provisioned normal calendar homes
            ch = schema.CALENDAR_HOME
            homeRows = yield Select(
                [ch.RESOURCE_ID],
                From=ch,
                Where=ch.STATUS == _HOME_STATUS_NORMAL,
            ).on(self.transaction)

            for homeRow in homeRows:
                yield CleanupOneInboxWork.reschedule(self.transaction, seconds=0, homeID=homeRow[0])



class CleanupOneInboxWork(WorkItem, fromTable(schema.CLEANUP_ONE_INBOX_WORK)):

    group = property(lambda self: (self.table.HOME_ID == self.homeID))

    @inlineCallbacks
    def doWork(self):

        # No need to delete other work items.  They are unique

        # get orphan names
        orphanNames = set((
            yield self.transaction.orphanedInboxItemsInHomeID(self.homeID)
        ))
        if orphanNames:
            home = yield self.transaction.calendarHomeWithResourceID(self.homeID)
            log.info("Inbox cleanup work in home: {homeUID}, deleting orphaned items: {orphanNames}".format(
                homeUID=home.uid(), orphanNames=orphanNames))

        # get old item names
        if float(config.InboxCleanup.ItemLifetimeDays) >= 0: # use -1 to disable; 0 is test case
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=float(config.InboxCleanup.ItemLifetimeDays))
            oldItemNames = set((
                yield self.transaction.listInboxItemsInHomeCreatedBefore(self.homeID, cutoff)
            ))
            newDeleters = oldItemNames - orphanNames
            if newDeleters:
                home = yield self.transaction.calendarHomeWithResourceID(self.homeID)
                log.info("Inbox cleanup work in home: {homeUID}, deleting old items: {newDeleters}".format(
                    homeUID=home.uid(), newDeleters=newDeleters))
        else:
            oldItemNames = set()

        # get item name for old events
        if float(config.InboxCleanup.ItemLifeBeyondEventEndDays) >= 0: # use -1 to disable; 0 is test case
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=float(config.InboxCleanup.ItemLifeBeyondEventEndDays))
            itemNamesForOldEvents = set((
                yield self.transaction.listInboxItemsInHomeForEventsBefore(self.homeID, cutoff)
            ))
            newDeleters = itemNamesForOldEvents - oldItemNames - orphanNames
            if newDeleters:
                home = yield self.transaction.calendarHomeWithResourceID(self.homeID)
                log.info("Inbox cleanup work in home: {homeUID}, deleting items for old events: {newDeleters}".format(
                    homeUID=home.uid(), newDeleters=newDeleters))
        else:
            itemNamesForOldEvents = set()

        itemNamesToDelete = orphanNames | itemNamesForOldEvents | oldItemNames
        if itemNamesToDelete:
            inbox = yield home.childWithName("inbox")
            for item in (yield inbox.objectResourcesWithNames(itemNamesToDelete)):
                yield item.remove()
