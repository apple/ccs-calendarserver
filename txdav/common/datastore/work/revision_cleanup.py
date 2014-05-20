# -*- test-case-name: txdav.common.datastore.work.test.test_revision_cleanup -*-
##
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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
Remove old and unused REVISION rows
"""

from twext.enterprise.dal.record import fromTable
from twext.enterprise.dal.syntax import Select, Max
from twext.enterprise.jobqueue import SingletonWorkItem, RegeneratingWorkItem
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, succeed
from twistedcaldav.config import config
from txdav.common.datastore.sql_tables import schema
import datetime

log = Logger()


class FindMinValidRevisionWork(RegeneratingWorkItem, fromTable(schema.FIND_MIN_VALID_REVISION_WORK)):

    group = "find_min_revision"

    @classmethod
    def initialSchedule(cls, store, seconds):
        def _enqueue(txn):
            return FindMinValidRevisionWork.reschedule(txn, seconds)

        if config.RevisionCleanup.Enabled:
            return store.inTransaction("FindMinValidRevisionWork.initialSchedule", _enqueue)
        else:
            return succeed(None)


    def regenerateInterval(self):
        """
        Return the interval in seconds between regenerating instances.
        """
        return float(config.RevisionCleanup.CleanupPeriodDays) * 24 * 60 * 60


    @inlineCallbacks
    def doWork(self):

        # Get the minimum valid revision
        minValidRevision = int((yield self.transaction.calendarserverValue("MIN-VALID-REVISION")))

        # get max revision on table rows before dateLimit
        dateLimit = (datetime.datetime.utcnow() -
            datetime.timedelta(days=float(config.RevisionCleanup.SyncTokenLifetimeDays)))
        maxRevOlderThanDate = 0

        # TODO: Use one Select statement
        for table in (
            schema.CALENDAR_OBJECT_REVISIONS,
            schema.NOTIFICATION_OBJECT_REVISIONS,
            schema.ADDRESSBOOK_OBJECT_REVISIONS,
            schema.ABO_MEMBERS,
        ):
            revisionRows = yield Select(
                [Max(table.REVISION)],
                From=table,
                Where=(table.MODIFIED < dateLimit),
            ).on(self.transaction)

            if revisionRows:
                tableMaxRevision = revisionRows[0][0]
                if tableMaxRevision > maxRevOlderThanDate:
                    maxRevOlderThanDate = tableMaxRevision

        if maxRevOlderThanDate > minValidRevision:
            # save new min valid revision
            yield self.transaction.updateCalendarserverValue("MIN-VALID-REVISION", maxRevOlderThanDate)

            # Schedule revision cleanup
            yield RevisionCleanupWork.reschedule(self.transaction, seconds=0)



class RevisionCleanupWork(SingletonWorkItem, fromTable(schema.REVISION_CLEANUP_WORK)):

    group = "group_revsion_cleanup"

    @inlineCallbacks
    def doWork(self):

        # Get the minimum valid revision
        minValidRevision = int((yield self.transaction.calendarserverValue("MIN-VALID-REVISION")))

        # delete revisions
        yield self.transaction.deleteRevisionsBefore(minValidRevision)
