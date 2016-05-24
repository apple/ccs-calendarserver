# -*- test-case-name: txdav.common.datastore.work.test.test_revision_cleanup -*-
##
# Copyright (c) 2013-2016 Apple Inc. All rights reserved.
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
from twext.enterprise.jobs.workitem import WorkItem, RegeneratingWorkItem
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
            log.error(
                "Inbox cleanup work: Can't schedule per home cleanup because {} work items still queued.",
                queuedCleanupOneInboxWorkItems
            )
        else:
            # enumerate provisioned normal calendar homes
            ch = schema.CALENDAR_HOME
            homeRows = yield Select(
                [ch.RESOURCE_ID],
                From=ch,
                Where=ch.STATUS == _HOME_STATUS_NORMAL,
            ).on(self.transaction)

            # Add an initial delay to the start of the first work item, then add an offset between each item
            seconds = config.InboxCleanup.StartDelaySeconds
            for homeRow in homeRows:
                yield CleanupOneInboxWork.reschedule(self.transaction, seconds=seconds, homeID=homeRow[0])
                seconds += config.InboxCleanup.StaggerSeconds



class CleanupOneInboxWork(WorkItem, fromTable(schema.CLEANUP_ONE_INBOX_WORK)):

    group = property(lambda self: (self.table.HOME_ID == self.homeID))

    @inlineCallbacks
    def doWork(self):

        # No need to delete other work items.  They are unique

        # get old item names
        if float(config.InboxCleanup.ItemLifetimeDays) >= 0: # use -1 to disable; 0 is test case
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=float(config.InboxCleanup.ItemLifetimeDays))
            oldItemNames = set((
                yield self.transaction.listInboxItemsInHomeCreatedBefore(self.homeID, cutoff)
            ))
            if oldItemNames:
                home = yield self.transaction.calendarHomeWithResourceID(self.homeID)
                log.info(
                    "Inbox cleanup work in home: {homeUID}, deleting old items: {oldItemNames}",
                    homeUID=home.uid(), oldItemNames=oldItemNames,
                )

                # If the number to delete is below our threshold then delete right away,
                # otherwise queue up more work items to delete these
                if len(oldItemNames) < config.InboxCleanup.InboxRemoveWorkThreshold:
                    inbox = yield home.childWithName("inbox")
                    for item in (yield inbox.objectResourcesWithNames(oldItemNames)):
                        yield item.remove()
                else:
                    seconds = config.InboxCleanup.RemovalStaggerSeconds
                    for item in oldItemNames:
                        yield InboxRemoveWork.reschedule(self.transaction, seconds=seconds, homeID=self.homeID, resourceName=item)
                        seconds += config.InboxCleanup.RemovalStaggerSeconds



class InboxRemoveWork(WorkItem, fromTable(schema.INBOX_REMOVE_WORK)):

    group = property(lambda self: (self.table.HOME_ID == self.homeID).And(self.table.RESOURCE_NAME == self.resourceName))

    @inlineCallbacks
    def doWork(self):

        # Some of the resources may no longer exist by the time this work item runs
        # so simply ignore that and let the work complete without doing anything
        home = yield self.transaction.calendarHomeWithResourceID(self.homeID)
        if home is not None:
            inbox = yield home.childWithName("inbox")
            if inbox is not None:
                item = yield inbox.objectResourceWithName(self.resourceName)
                if item is not None:
                    yield item.remove()
