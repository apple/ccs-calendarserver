# -*- test-case-name: twext.who.test.test_groups -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
from twext.enterprise.dal.syntax import Delete, Select, Update, Max
from twext.enterprise.queue import WorkItem
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav.config import config
from txdav.common.datastore.sql import deleteRevisionsBefore
from txdav.common.datastore.sql_tables import schema
import datetime

log = Logger()


class FindMinValidRevisionWork(WorkItem,
    fromTable(schema.FIND_MIN_VALID_REVISION_WORK)):

    group = "find_min_revision"

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items
        yield Delete(From=self.table, Where=None).on(self.transaction)

        # Get the minimum valid revision
        cs = schema.CALENDARSERVER
        minValidRevision = int((yield Select(
            [cs.VALUE],
            From=cs,
            Where=(cs.NAME == "MIN-VALID-REVISION")
        ).on(self.transaction))[0][0])

        # get max revision on table rows before dateLimit
        dateLimit = (datetime.datetime.utcnow() -
            datetime.timedelta(days=float(config.SyncTokenLifetimeDays)))
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
            # save it
            cs = schema.CALENDARSERVER
            yield Update(
                {cs.VALUE: maxRevOlderThanDate},
                Where=cs.NAME == "MIN-VALID-REVISION",
            ).on(self.transaction)

            # Schedule revision cleanup
            log.debug("Scheduling revision cleanup now")
            yield self.transaction.enqueue(RevisionCleanupWork)

        else:
            # Schedule next update
            notBefore = (datetime.datetime.utcnow() +
                datetime.timedelta(days=float(config.RevisionCleanupPeriodDays)))
            log.debug("Rescheduling find minimum valid revision work: %s" % (notBefore,))
            yield self.transaction.enqueue(FindMinValidRevisionWork,
                notBefore=notBefore)



class RevisionCleanupWork(WorkItem,
    fromTable(schema.REVISION_CLEANUP_WORK)):

    group = "group_revsion_cleanup"

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items
        yield Delete(From=self.table, Where=None).on(self.transaction)

        # Get the minimum valid revision
        cs = schema.CALENDARSERVER
        minValidRevision = int((yield Select(
            [cs.VALUE],
            From=cs,
            Where=(cs.NAME == "MIN-VALID-REVISION")
        ).on(self.transaction))[0][0])

        # delete revisions
        yield deleteRevisionsBefore(self.transaction, minValidRevision)

        # Schedule next update
        notBefore = (datetime.datetime.utcnow() +
            datetime.timedelta(days=float(config.RevisionCleanupPeriodDays)))
        log.debug("Rescheduling find minimum valid revision work: %s" % (notBefore,))
        yield self.transaction.enqueue(FindMinValidRevisionWork,
            notBefore=notBefore)



@inlineCallbacks
def scheduleFirstFindMinRevision(store, seconds):
    txn = store.newTransaction()
    notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    log.debug("Scheduling first find minimum valid revision work: %s" % (notBefore,))
    wp = (yield txn.enqueue(FindMinValidRevisionWork, notBefore=notBefore))
    yield txn.commit()
    returnValue(wp)
