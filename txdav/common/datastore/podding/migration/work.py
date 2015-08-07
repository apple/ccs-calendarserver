##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.record import fromTable
from twext.enterprise.jobs.workitem import WorkItem

from twisted.internet.defer import inlineCallbacks

from txdav.caldav.datastore.scheduling.imip.token import iMIPTokenRecord
from txdav.caldav.datastore.scheduling.work import allScheduleWork
from txdav.common.datastore.podding.migration.sync_metadata import CalendarMigrationRecord, \
    CalendarObjectMigrationRecord, AttachmentMigrationRecord
from txdav.common.datastore.sql_directory import DelegateRecord, \
    DelegateGroupsRecord, ExternalDelegateGroupsRecord
from txdav.common.datastore.sql_tables import schema, _HOME_STATUS_DISABLED


class HomeCleanupWork(WorkItem, fromTable(schema.HOME_CLEANUP_WORK)):
    """
    Work item to clean up any previously "external" homes on the pod to which data was migrated to. Those
    old homes will now be marked as disabled and need to be silently removed without any side effects
    (i.e., no implicit scheduling, no sharing cancels, etc).
    """

    group = "ownerUID"

    notBeforeDelay = 300    # 5 minutes

    @inlineCallbacks
    def doWork(self):
        """
        Delete all the corresponding homes.
        """

        oldhome = yield self.transaction.calendarHomeWithUID(self.ownerUID, status=_HOME_STATUS_DISABLED)
        if oldhome is not None:
            yield oldhome.purgeAll()

        oldnotifications = yield self.transaction.notificationsWithUID(self.ownerUID, status=_HOME_STATUS_DISABLED)
        if oldnotifications is not None:
            yield oldnotifications.purge()



class MigratedHomeCleanupWork(WorkItem, fromTable(schema.MIGRATED_HOME_CLEANUP_WORK)):
    """
    Work item to clean up the old home data left behind after migration, as well
    as other unwanted items like iMIP tokens, delegates etc. The old homes will
    now be marked as disabled and need to be silently removed without any side
    effects (i.e., no implicit scheduling, no sharing cancels, etc).
    """

    group = "ownerUID"

    notBeforeDelay = 300    # 5 minutes

    @inlineCallbacks
    def doWork(self):
        """
        Delete all the corresponding homes, then the ancillary data.
        """

        oldhome = yield self.transaction.calendarHomeWithUID(self.ownerUID, status=_HOME_STATUS_DISABLED)
        if oldhome is not None:
            # Work items - we need to clean these up before the home goes away because we have an "on delete cascade" on the WorkItem
            # table, and if that ran it would leave orphaned Job rows set to a pause state and those would remain for ever in the table.
            for workType in allScheduleWork:
                items = yield workType.query(self.transaction, workType.homeResourceID == oldhome.id())
                for item in items:
                    yield item.remove()

            yield oldhome.purgeAll()

        oldnotifications = yield self.transaction.notificationsWithUID(self.ownerUID, status=_HOME_STATUS_DISABLED)
        if oldnotifications is not None:
            yield oldnotifications.purge()

        # These are things that reference the home id or the user UID but don't get removed via a cascade

        # iMIP tokens
        cuaddr = "urn:x-uid:{}".format(self.ownerUID)
        yield iMIPTokenRecord.deletesome(
            self.transaction,
            iMIPTokenRecord.organizer == cuaddr,
        )

        # Delegators - individual and group
        yield DelegateRecord.deletesome(self.transaction, DelegateRecord.delegator == self.ownerUID)
        yield DelegateGroupsRecord.deletesome(self.transaction, DelegateGroupsRecord.delegator == self.ownerUID)
        yield ExternalDelegateGroupsRecord.deletesome(self.transaction, ExternalDelegateGroupsRecord.delegator == self.ownerUID)



class MigrationCleanupWork(WorkItem, fromTable(schema.MIGRATION_CLEANUP_WORK)):

    group = "homeResourceID"

    notBeforeDelay = 300    # 5 minutes

    @inlineCallbacks
    def doWork(self):
        """
        Delete all the corresponding migration records.
        """

        yield CalendarMigrationRecord.deletesome(
            self.transaction,
            CalendarMigrationRecord.calendarHomeResourceID == self.homeResourceID,
        )
        yield CalendarObjectMigrationRecord.deletesome(
            self.transaction,
            CalendarObjectMigrationRecord.calendarHomeResourceID == self.homeResourceID,
        )
        yield AttachmentMigrationRecord.deletesome(
            self.transaction,
            AttachmentMigrationRecord.calendarHomeResourceID == self.homeResourceID,
        )
