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

from functools import wraps

from twext.python.log import Logger
from twisted.internet.defer import returnValue, inlineCallbacks
from twisted.python.failure import Failure
from txdav.caldav.icalendarstore import ComponentUpdateState
from txdav.common.datastore.podding.migration.sync_metadata import CalendarMigrationRecord, \
    CalendarObjectMigrationRecord, AttachmentMigrationRecord
from txdav.caldav.datastore.sql import ManagedAttachment, CalendarBindRecord
from txdav.common.datastore.sql_external import NotificationCollectionExternal
from txdav.common.datastore.sql_notification import NotificationCollection
from txdav.common.datastore.sql_tables import _HOME_STATUS_EXTERNAL, \
    _HOME_STATUS_MIGRATING
from txdav.common.idirectoryservice import DirectoryRecordNotFoundError

from uuid import uuid4

log = Logger()


def inTransactionWrapper(operation):
    """
    This wrapper converts an instance method that takes a transaction as its
    first parameter into one where the transaction parameter is an optional
    keyword argument. If the keyword argument is present and not None, then
    the instance method is called with that keyword as the first positional
    argument (i.e., almost a NoOp). If the keyword argument is not present,
    then a new transaction is created and the instance method called with
    it as the first positional argument, plus the call is wrapped with
    try/except/else to ensure proper commit and abort of the internally
    created transaction is done.

    So this wrapper allows for a method that requires a transaction to be run
    with either an existing transaction or one created just for the purpose
    of running it.

    @param operation: a callable that takes an L{IAsyncTransaction} as its first
        argument, and returns a value.
    """

    @wraps(operation)
    @inlineCallbacks
    def _inTxn(self, *args, **kwargs):
        label = self.label(operation.__name__)
        if "txn" in kwargs:
            txn = kwargs["txn"]
            del kwargs["txn"]
            result = yield operation(self, txn, *args, **kwargs)
            returnValue(result)
        else:
            txn = self.store.newTransaction(label=label)
            try:
                result = yield operation(self, txn, *args, **kwargs)
            except Exception as ex:
                f = Failure()
                yield txn.abort()
                log.error("{label} failed: {e}".format(label=label, e=str(ex)))
                returnValue(f)
            else:
                yield txn.commit()
                returnValue(result)

    return _inTxn



# Cross-pod synchronization of an entire calendar home
class CrossPodHomeSync(object):

    BATCH_SIZE = 50

    def __init__(self, store, diruid):
        """
        @param store: the data store
        @type store: L{CommonDataStore}
        @param diruid: directory uid of the user whose home is to be sync'd
        @type diruid: L{str}
        """

        self.store = store
        self.diruid = diruid


    def label(self, detail):
        return "Cross-pod Migration Sync for {}: {}".format(self.diruid, detail)


    @inlineCallbacks
    def migrateHere(self):
        """
        This is a full, serialized version of a data migration (minus any directory
        update) that can be triggered via a command line tool. It is designed to
        minimize down time for the migrating user.
        """

        # Step 1 - initial full sync
        yield self.sync()

        # Step 2 - increment sync (since the initial sync may take a long time
        # to run we should do one incremental sync before bringing down the
        # account being migrated)
        yield self.sync()

        # Step 3 - disable remote home
        # NB Any failure from this point on will need to be caught and
        # handled by re-enabling the old home (and fixing any sharing state
        # that may have been changed)
        yield self.disableRemoteHome()

        # Step 4 - final incremental sync
        yield self.sync()

        # Step 5 - final overall sync of meta-data (including sharing re-linking)
        yield self.finalSync()

        # Step 6 - enable new home
        yield self.enableLocalHome()

        # Step 7 - remote remote home
        yield self.removeRemoteHome()

        # Step 8 - say phew! TODO: Actually alert everyone else
        pass


    @inlineCallbacks
    def sync(self):
        """
        Initiate a sync of the home. This is a simple data sync that does not
        reconcile sharing state etc. The L{finalSync} method will do a full
        sharing reconcile as well as disable the migration source home.
        """

        yield self.loadRecord()
        yield self.prepareCalendarHome()

        # Calendar list and calendar data
        yield self.syncCalendarList()

        # Sync home metadata such as alarms, default calendars, etc
        yield self.syncCalendarHomeMetaData()

        # Sync attachments
        yield self.syncAttachments()


    @inlineCallbacks
    def finalSync(self):
        """
        Do the final sync up of any additional data, re-link sharing bind
        rows, recalculate quota etc.
        """

        # Link attachments to resources: ATTACHMENT_CALENDAR_OBJECT table
        yield self.linkAttachments()

        # TODO: Re-write attachment URIs - not sure if we need this as reverse proxy may take care of it
        pass

        # Group attendee reconcile
        yield self.groupAttendeeReconcile()

        # Delegates reconcile
        yield self.delegateReconcile()

        # TODO: shared collections reconcile
        yield self.sharedByCollectionsReconcile()
        yield self.sharedToCollectionsReconcile()

        # TODO: group sharee reconcile
        pass

        # Notifications
        yield self.notificationsReconcile()

        # TODO: work items
        pass


    @inlineCallbacks
    def disableRemoteHome(self):
        """
        Mark the remote home as disabled.
        """

        # TODO: implement API on CommonHome to rename the ownerUID column and
        # change the status column.
        pass


    @inlineCallbacks
    def enableLocalHome(self):
        """
        Mark the local home as enabled.
        """

        # TODO: implement API on CommonHome to rename the ownerUID column and
        # change the status column. Also adjust NotificationCollection.
        pass


    @inlineCallbacks
    def removeRemoteHome(self):
        """
        Remove all the old data on the remote pod.
        """

        # TODO: implement API on CommonHome to purge the old data without
        # any side-effects (scheduling, sharing etc).
        pass


    @inlineCallbacks
    def loadRecord(self):
        """
        Initiate a sync of the home.
        """

        self.record = yield self.store.directoryService().recordWithUID(self.diruid)
        if self.record is None:
            raise DirectoryRecordNotFoundError("Cross-pod Migration Sync missing directory record for {}".format(self.diruid))
        if self.record.thisServer():
            raise ValueError("Cross-pod Migration Sync cannot sync with user already on this server: {}".format(self.diruid))


    @inTransactionWrapper
    @inlineCallbacks
    def prepareCalendarHome(self, txn):
        """
        Make sure the inactive home to migrate into is present on this pod.
        """

        home = yield self._localHome(txn)
        if home is None:
            home = yield txn.calendarHomeWithUID(self.diruid, status=_HOME_STATUS_MIGRATING, create=True)
        self.homeId = home.id()


    @inTransactionWrapper
    @inlineCallbacks
    def syncCalendarHomeMetaData(self, txn):
        """
        Make sure the home meta-data (alarms, default calendars) is properly sync'd
        """

        remote_home = yield self._remoteHome(txn=txn)
        yield remote_home.readMetaData()

        calendars = yield CalendarMigrationRecord.querysimple(txn, calendarHomeResourceID=self.homeId)
        calendarIDMap = dict((item.remoteResourceID, item.localResourceID) for item in calendars)

        local_home = yield self._localHome(txn)
        yield local_home.copyMetadata(remote_home, calendarIDMap)


    @inlineCallbacks
    def _remoteHome(self, txn):
        """
        Create a synthetic external home object that maps to the actual remote home.
        """

        from txdav.caldav.datastore.sql_external import CalendarHomeExternal
        resourceID = yield txn.store().conduit.send_home_resource_id(txn, self.record)
        home = CalendarHomeExternal.makeSyntheticExternalHome(txn, self.record.uid, resourceID) if resourceID is not None else None
        returnValue(home)


    def _localHome(self, txn):
        """
        Get the home on this pod that will have data migrated to it.
        """

        return txn.calendarHomeWithUID(self.diruid, status=_HOME_STATUS_MIGRATING)


    @inlineCallbacks
    def syncCalendarList(self):
        """
        Synchronize each owned calendar.
        """

        # Remote sync details
        remote_sync_state = yield self.getCalendarSyncList()

        # Get local sync details from local DB
        local_sync_state = yield self.getSyncState()

        # Remove local calendars no longer on the remote side
        yield self.purgeLocal(local_sync_state, remote_sync_state)

        # Sync each calendar that matches on both sides
        for remoteID in remote_sync_state.keys():
            yield self.syncCalendar(remoteID, local_sync_state, remote_sync_state)


    @inTransactionWrapper
    @inlineCallbacks
    def getCalendarSyncList(self, txn):
        """
        Get the names and sync-tokens for each remote owned calendar.
        """

        # List of calendars from the remote side
        home = yield self._remoteHome(txn)
        if home is None:
            returnValue(None)
        calendars = yield home.loadChildren()
        results = {}
        for calendar in calendars:
            if calendar.owned():
                sync_token = yield calendar.syncToken()
                results[calendar.id()] = CalendarMigrationRecord.make(
                    calendarHomeResourceID=home.id(),
                    remoteResourceID=calendar.id(),
                    localResourceID=0,
                    lastSyncToken=sync_token,
                )

        returnValue(results)


    @inTransactionWrapper
    @inlineCallbacks
    def getSyncState(self, txn):
        """
        Get local synchronization state for the home being migrated.
        """
        records = yield CalendarMigrationRecord.querysimple(
            txn, calendarHomeResourceID=self.homeId
        )
        returnValue(dict([(record.remoteResourceID, record) for record in records]))


    @inTransactionWrapper
    @inlineCallbacks
    def updateSyncState(self, txn, stateRecord, newSyncToken):
        """
        Update or insert an L{CalendarMigrationRecord} with the new specified sync token.
        """
        if stateRecord.isnew():
            stateRecord.lastSyncToken = newSyncToken
            yield stateRecord.insert(txn)
        else:
            # The existing stateRecord has a stale txn, but valid column values. We have
            # to duplicate it before we can give it a different txn.
            stateRecord = stateRecord.duplicate()
            stateRecord.transaction = txn
            yield stateRecord.update(lastSyncToken=newSyncToken)


    @inTransactionWrapper
    @inlineCallbacks
    def purgeLocal(self, txn, local_sync_state, remote_sync_state):
        """
        Remove (silently - i.e., no scheduling) local calendars that are no longer on the remote side.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param local_sync_state: local sync state
        @type local_sync_state: L{dict}
        @param remote_sync_state: remote sync state
        @type remote_sync_state: L{dict}
        """
        home = yield self._localHome(txn)
        for remoteID in set(local_sync_state.keys()) - set(remote_sync_state.keys()):
            calendar = yield home.childWithID(local_sync_state[remoteID].localResourceID)
            if calendar is not None:
                yield calendar.purge()
            del local_sync_state[remoteID]


    @inlineCallbacks
    def syncCalendar(self, remoteID, local_sync_state, remote_sync_state):
        """
        Sync the contents of a calendar from the remote side. The local calendar may need to be created
        on initial sync. Make use of sync tokens to avoid unnecessary work.

        @param remoteID: id of the remote calendar to sync
        @type remoteID: L{int}
        @param local_sync_state: local sync state
        @type local_sync_state: L{dict}
        @param remote_sync_state: remote sync state
        @type remote_sync_state: L{dict}
        """

        # See if we need to create the local one first
        if remoteID not in local_sync_state:
            localID = yield self.newCalendar()
            local_sync_state[remoteID] = CalendarMigrationRecord.make(
                calendarHomeResourceID=self.homeId,
                remoteResourceID=remoteID,
                localResourceID=localID,
                lastSyncToken=None,
            )
        local_record = local_sync_state.get(remoteID)

        remote_token = remote_sync_state[remoteID].lastSyncToken
        if local_record.lastSyncToken != remote_token:
            # Sync meta-data such as name, alarms, supported-components, transp, etc
            yield self.syncCalendarMetaData(local_record)

            # Sync object resources
            changed, deleted = yield self.findObjectsToSync(local_record)
            yield self.purgeDeletedObjectsInBatches(local_record, deleted)
            yield self.updateChangedObjectsInBatches(local_record, changed)

        yield self.updateSyncState(local_record, remote_token)


    @inTransactionWrapper
    @inlineCallbacks
    def newCalendar(self, txn):
        """
        Create a new local calendar to sync remote data to. We don't care about the name
        of the calendar right now - it will be sync'd later.
        """

        home = yield self._localHome(txn)
        calendar = yield home.createChildWithName(str(uuid4()))
        returnValue(calendar.id())


    @inTransactionWrapper
    @inlineCallbacks
    def syncCalendarMetaData(self, txn, migrationRecord):
        """
        Sync the metadata of a calendar from the remote side.

        @param migrationRecord: current migration record
        @type localID: L{CalendarMigrationRecord}
        """
        # Remote changes
        remote_home = yield self._remoteHome(txn)
        remote_calendar = yield remote_home.childWithID(migrationRecord.remoteResourceID)
        if remote_calendar is None:
            returnValue(None)

        # Check whether the deleted set items
        local_home = yield self._localHome(txn)
        local_calendar = yield local_home.childWithID(migrationRecord.localResourceID)
        yield local_calendar.copyMetadata(remote_calendar)


    @inTransactionWrapper
    @inlineCallbacks
    def findObjectsToSync(self, txn, migrationRecord):
        """
        Find the set of object resources that need to be sync'd from the remote
        side and the set that need to be removed locally. Take into account the
        possibility that this is a partial sync and removals or additions might
        be false positives.

        @param migrationRecord: current migration record
        @type localID: L{CalendarMigrationRecord}
        """

        # Remote changes
        remote_home = yield self._remoteHome(txn)
        remote_calendar = yield remote_home.childWithID(migrationRecord.remoteResourceID)
        if remote_calendar is None:
            returnValue(None)
        changed, deleted, _ignore_invalid = yield remote_calendar.resourceNamesSinceToken(migrationRecord.lastSyncToken)

        # Check whether the deleted set items
        local_home = yield self._localHome(txn)
        local_calendar = yield local_home.childWithID(migrationRecord.localResourceID)

        # Check the md5's on each changed remote with the local one to filter out ones
        # we don't actually need to sync
        remote_changes = yield remote_calendar.objectResourcesWithNames(changed)
        remote_changes = dict([(calendar.name(), calendar) for calendar in remote_changes])

        local_changes = yield local_calendar.objectResourcesWithNames(changed)
        local_changes = dict([(calendar.name(), calendar) for calendar in local_changes])

        actual_changes = []
        for name, calendar in remote_changes.items():
            if name not in local_changes or remote_changes[name].md5() != local_changes[name].md5():
                actual_changes.append(name)

        returnValue((actual_changes, deleted,))


    @inlineCallbacks
    def purgeDeletedObjectsInBatches(self, migrationRecord, deleted):
        """
        Purge (silently remove) the specified object resources. This needs to
        succeed in the case where some or all resources have already been deleted.
        Do this in batches to keep transaction times small.

        @param migrationRecord: local calendar migration record
        @type migrationRecord: L{CalendarMigrationRecord}
        @param deleted: list of names to purge
        @type deleted: L{list} of L{str}
        """

        remaining = list(deleted)
        while remaining:
            yield self.purgeBatch(migrationRecord.localResourceID, remaining[:self.BATCH_SIZE])
            del remaining[:self.BATCH_SIZE]


    @inTransactionWrapper
    @inlineCallbacks
    def purgeBatch(self, txn, localID, purge_names):
        """
        Purge a bunch of object resources from the specified calendar.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param localID: id of the local calendar to sync
        @type localID: L{int}
        @param purge_names: object resource names to purge
        @type purge_names: L{list} of L{str}
        """

        # Check whether the deleted set items
        local_home = yield self._localHome(txn)
        local_calendar = yield local_home.childWithID(localID)
        local_objects = yield local_calendar.objectResourcesWithNames(purge_names)

        for local_object in local_objects:
            yield local_object.purge()


    @inlineCallbacks
    def updateChangedObjectsInBatches(self, migrationRecord, changed):
        """
        Update the specified object resources. This needs to succeed in the
        case where some or all resources have already been deleted.
        Do this in batches to keep transaction times small.

        @param migrationRecord: local calendar migration record
        @type migrationRecord: L{CalendarMigrationRecord}
        @param changed: list of names to update
        @type changed: L{list} of L{str}
        """

        remaining = list(changed)
        while remaining:
            yield self.updateBatch(
                migrationRecord.localResourceID,
                migrationRecord.remoteResourceID,
                remaining[:self.BATCH_SIZE],
            )
            del remaining[:self.BATCH_SIZE]


    @inTransactionWrapper
    @inlineCallbacks
    def updateBatch(self, txn, localID, remoteID, remaining):
        """
        Update a bunch of object resources from the specified remote calendar.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param localID: id of the local calendar to sync
        @type localID: L{int}
        @param remoteID: id of the remote calendar to sync with
        @type remoteID: L{int}
        @param purge_names: object resource names to update
        @type purge_names: L{list} of L{str}
        """

        # Get remote objects
        remote_home = yield self._remoteHome(txn)
        remote_calendar = yield remote_home.childWithID(remoteID)
        if remote_calendar is None:
            returnValue(None)
        remote_objects = yield remote_calendar.objectResourcesWithNames(remaining)
        remote_objects = dict([(obj.name(), obj) for obj in remote_objects])

        # Get local objects
        local_home = yield self._localHome(txn)
        local_calendar = yield local_home.childWithID(localID)
        local_objects = yield local_calendar.objectResourcesWithNames(remaining)
        local_objects = dict([(obj.name(), obj) for obj in local_objects])

        # Sync ones that still exist - use txn._migrating together with stuffing the remote md5
        # value onto the component being stored to ensure that the md5 value stored locally
        # matches the remote one (which should help reduce the need for a client to resync
        # the data when moved from one pod to the other).
        txn._migrating = True
        for obj_name in remote_objects.keys():
            remote_object = remote_objects[obj_name]
            remote_data = yield remote_object.component()
            remote_data.md5 = remote_object.md5()
            if obj_name in local_objects:
                local_object = yield local_objects[obj_name]
                yield local_object._setComponentInternal(remote_data, internal_state=ComponentUpdateState.RAW)
                del local_objects[obj_name]
            else:
                local_object = yield local_calendar._createCalendarObjectWithNameInternal(obj_name, remote_data, internal_state=ComponentUpdateState.RAW)

                # Maintain the mapping from the remote to local id. Note that this mapping never changes as the ids on both
                # sides are immutable - though it may get deleted if the local object is removed during sync (via a cascade).
                yield CalendarObjectMigrationRecord.create(
                    txn,
                    calendarHomeResourceID=self.homeId,
                    remoteResourceID=remote_object.id(),
                    localResourceID=local_object.id()
                )

            # Sync meta-data such as schedule object, schedule tags, access mode etc
            yield local_object.copyMetadata(remote_object)

        # Purge the ones that remain
        for local_object in local_objects.values():
            yield local_object.purge()


    @inlineCallbacks
    def syncAttachments(self):
        """
        Sync attachments (both metadata and actual attachment data) for the home being migrated.
        """

        # Two steps - sync the table first in one txn, then sync each attachment's data
        changed_ids, removed_ids = yield self.syncAttachmentTable()

        for local_id in changed_ids:
            yield self.syncAttachmentData(local_id)

        returnValue((changed_ids, removed_ids,))


    @inTransactionWrapper
    @inlineCallbacks
    def syncAttachmentTable(self, txn):
        """
        Sync the ATTACHMENT table data for the home being migrated. Return the list of local attachment ids that
        now need there attachment data sync'd from the server.
        """

        remote_home = yield self._remoteHome(txn)
        rattachments = yield remote_home.getAllAttachments()
        rmap = dict([(attachment.id(), attachment) for attachment in rattachments])

        local_home = yield self._localHome(txn)
        lattachments = yield local_home.getAllAttachments()
        lmap = dict([(attachment.id(), attachment) for attachment in lattachments])

        # Figure out the differences
        records = yield AttachmentMigrationRecord.querysimple(
            txn, calendarHomeResourceID=self.homeId
        )
        mapping = dict([(record.remoteResourceID, record) for record in records])

        # Removed - remove attachment and migration state
        removed = set(mapping.keys()) - set(rmap.keys())
        for remove_id in removed:
            record = mapping[remove_id]
            att = yield ManagedAttachment.load(txn, None, None, attachmentID=record.localResourceID)
            if att:
                yield att.remove(adjustQuota=False)
            else:
                yield record.delete()

        # Track which ones need attachment data sync'd over
        data_ids = set()

        # Added - add new attachment and migration state
        added = set(rmap.keys()) - set(mapping.keys())
        for added_id in added:
            attachment = yield ManagedAttachment._create(txn, None, self.homeId)
            yield AttachmentMigrationRecord.create(
                txn,
                calendarHomeResourceID=self.homeId,
                remoteResourceID=added_id,
                localResourceID=attachment.id(),
            )
            data_ids.add(attachment.id())

        # Possible updates - check for md5 change and sync
        updates = set(mapping.keys()) & set(rmap.keys())
        for updated_id in updates:
            local_id = mapping[updated_id].localResourceID
            if rmap[updated_id].md5() != lmap[local_id].md5():
                yield lmap[local_id].copyRemote(rmap[updated_id])
                data_ids.add(local_id)

        returnValue((data_ids, removed,))


    @inTransactionWrapper
    @inlineCallbacks
    def syncAttachmentData(self, txn, local_id):
        """
        Sync the attachment data for the home being migrated.
        """

        remote_home = yield self._remoteHome(txn)
        local_home = yield self._localHome(txn)
        attachment = yield local_home.getAttachmentByID(local_id)
        if attachment is None:
            returnValue(None)

        records = yield AttachmentMigrationRecord.querysimple(
            txn, calendarHomeResourceID=self.homeId, localResourceID=local_id
        )
        if records:
            # Read the data from the conduit
            yield remote_home.readAttachmentData(records[0].remoteResourceID, attachment)


    @inlineCallbacks
    def linkAttachments(self):
        """
        Link attachments to the calendar objects they belong to.
        """

        # Get the map of links for the remote home
        links = yield self.getAttachmentLinks()

        # Get remote->local ID mappings
        attachmentIDMap, objectIDMap = yield self.getAttachmentMappings()

        # Batch setting links for the local home
        len_links = len(links)
        while links:
            yield self.makeAttachmentLinks(links[:50], attachmentIDMap, objectIDMap)
            links = links[50:]

        returnValue(len_links)


    @inTransactionWrapper
    @inlineCallbacks
    def getAttachmentLinks(self, txn):
        """
        Get the remote link information.
        """

        # Get the map of links for the remote home
        remote_home = yield self._remoteHome(txn)
        links = yield remote_home.getAttachmentLinks()
        returnValue(links)


    @inTransactionWrapper
    @inlineCallbacks
    def getAttachmentMappings(self, txn):
        """
        Get the remote link information.
        """

        # Get migration mappings
        records = yield AttachmentMigrationRecord.querysimple(
            txn, calendarHomeResourceID=self.homeId
        )
        attachmentIDMap = dict([(record.remoteResourceID, record) for record in records])

        records = yield CalendarObjectMigrationRecord.querysimple(
            txn, calendarHomeResourceID=self.homeId
        )
        objectIDMap = dict([(record.remoteResourceID, record) for record in records])

        returnValue((attachmentIDMap, objectIDMap,))


    @inTransactionWrapper
    @inlineCallbacks
    def makeAttachmentLinks(self, txn, links, attachmentIDMap, objectIDMap):
        """
        Map remote links to local links.
        """

        for link in links:
            # Remote link has an invalid txn at this point so replace that first
            link._txn = txn

            # Now re-map the attachment ID and calendar_object_id to the local ones
            link._attachmentID = attachmentIDMap[link._attachmentID].localResourceID
            link._calendarObjectID = objectIDMap[link._calendarObjectID].localResourceID

            yield link.insert()


    @inlineCallbacks
    def delegateReconcile(self):
        """
        Sync the delegate assignments from the remote home to the local home. We won't use
        a fake directory UID locally.
        """

        yield self.individualDelegateReconcile()
        yield self.groupDelegateReconcile()
        yield self.externalDelegateReconcile()


    @inTransactionWrapper
    @inlineCallbacks
    def individualDelegateReconcile(self, txn):
        """
        Sync the delegate assignments from the remote home to the local home. We won't use
        a fake directory UID locally.
        """
        remote_records = yield txn.dumpIndividualDelegatesExternal(self.record)
        for record in remote_records:
            yield record.insert(txn)


    @inTransactionWrapper
    @inlineCallbacks
    def groupDelegateReconcile(self, txn):
        """
        Sync the delegate assignments from the remote home to the local home. We won't use
        a fake directory UID locally.
        """
        remote_records = yield txn.dumpGroupDelegatesExternal(self.record)
        for delegator, group in remote_records:
            # We need to make sure the group exists locally first and map the groupID to the local one
            local_group = yield txn.groupByUID(group.groupUID)
            delegator.groupID = local_group.groupID
            yield delegator.insert(txn)


    @inTransactionWrapper
    @inlineCallbacks
    def externalDelegateReconcile(self, txn):
        """
        Sync the external delegate assignments from the remote home to the local home. We won't use
        a fake directory UID locally.
        """
        remote_records = yield txn.dumpExternalDelegatesExternal(self.record)
        for record in remote_records:
            yield record.insert(txn)


    @inlineCallbacks
    def groupAttendeeReconcile(self):
        """
        Sync the remote group attendee links to the local store.
        """

        # Get remote data and local mapping information
        remote_group_attendees, objectIDMap = yield self.groupAttendeeData()

        # Map each result to a local resource (in batches)
        number_of_links = len(remote_group_attendees)
        while remote_group_attendees:
            yield self.groupAttendeeProcess(remote_group_attendees[:50], objectIDMap)
            remote_group_attendees = remote_group_attendees[50:]

        returnValue(number_of_links)


    @inTransactionWrapper
    @inlineCallbacks
    def groupAttendeeData(self, txn):
        """
        Sync the remote group attendee links to the local store.
        """
        remote_home = yield self._remoteHome(txn)
        remote_group_attendees = yield remote_home.getAllGroupAttendees()

        # Get all remote->local object maps
        records = yield CalendarObjectMigrationRecord.querysimple(
            txn, calendarHomeResourceID=self.homeId
        )
        objectIDMap = dict([(record.remoteResourceID, record.localResourceID) for record in records])

        returnValue((remote_group_attendees, objectIDMap,))


    @inTransactionWrapper
    @inlineCallbacks
    def groupAttendeeProcess(self, txn, results, objectIDMap):
        """
        Sync the remote group attendee links to the local store.
        """
        # Map each result to a local resource
        for groupAttendee, group in results:
            local_group = yield txn.groupByUID(group.groupUID)
            groupAttendee.groupID = local_group.groupID
            try:
                groupAttendee.resourceID = objectIDMap[groupAttendee.resourceID]
            except KeyError:
                continue
            yield groupAttendee.insert(txn)


    @inlineCallbacks
    def notificationsReconcile(self):
        """
        Sync all the existing L{NotificationObject} resources from the remote store.
        """

        records = yield self.notificationRecords()

        # Batch setting resources for the local home
        len_records = len(records)
        while records:
            yield self.makeNotifications(records[:50])
            records = records[50:]

        returnValue(len_records)


    @inTransactionWrapper
    @inlineCallbacks
    def notificationRecords(self, txn):
        """
        Get all the existing L{NotificationObjectRecord}'s from the remote store.
        """

        notifications = yield NotificationCollectionExternal.notificationsWithUID(txn, self.diruid, True)
        records = yield notifications.notificationObjectRecords()
        for record in records:
            # This needs to be reset when added to the local store
            del record.resourceID

            # Map the remote id to the local one.
            record.notificationHomeResourceID = notifications.id()

        returnValue(records)


    @inTransactionWrapper
    @inlineCallbacks
    def makeNotifications(self, txn, records):
        """
        Create L{NotificationObjectRecord} records in the local store.
        """

        notifications = yield NotificationCollection.notificationsWithUID(txn, self.diruid, True, _HOME_STATUS_EXTERNAL)
        for record in records:
            # Do this via the "write" API so that sync revisions are updated properly, rather than just
            # inserting the records directly.
            yield notifications.writeNotificationObject(record.notificationUID, record.notificationType, record.notificationData)


    @inlineCallbacks
    def sharedByCollectionsReconcile(self):
        """
        Sync all the collections shared by the migrating user from the remote store. We will do this one calendar at a time since
        there could be a large number of sharees per calendar.

        Here is the logic we need: first assume we have three pods: A, B, C, and we are migrating a user from A->B. We start
        with a set of shares (X -> Y - where X is the sharer and Y the sharee) on pod A. We migrate the sharer to pod B. We
        then need to have a set of bind records on pod B, and adjust the set on pod A. Note that no changes are required on pod C.

        Original      |  Changes                     | Changes
        Shares        |  on B                        | on A
        --------------|------------------------------|---------------------
        A -> A        |  B -> A (new)                | B -> A (modify existing)
        A -> B        |  B -> B (modify existing)    | (removed)
        A -> C        |  B -> C (new)                | (removed)
        """

        calendars = yield self.getSyncState()

        len_records = 0
        for calendar in calendars.values():
            records, bindUID = yield self.sharedByCollectionRecords(calendar.remoteResourceID, calendar.localResourceID)
            records = records.items()

            # Batch setting resources for the local home
            len_records += len(records)
            while records:
                yield self.makeSharedByCollections(records[:50], calendar.localResourceID)
                records = records[50:]

            # Update the remote pod to switch over the shares
            yield self.updatedRemoteSharedByCollections(calendar.remoteResourceID, bindUID)

        returnValue(len_records)


    @inTransactionWrapper
    @inlineCallbacks
    def sharedByCollectionRecords(self, txn, remote_id, local_id):
        """
        Get all the existing L{CalendarBindRecord}'s from the remote store. Also make sure a
        bindUID exists for the local calendar.
        """

        remote_home = yield self._remoteHome(txn)
        remote_calendar = yield remote_home.childWithID(remote_id)
        records = yield remote_calendar.sharingBindRecords()

        # Check bindUID
        local_records = yield CalendarBindRecord.querysimple(
            txn,
            calendarHomeResourceID=self.homeId,
            calendarResourceID=local_id,
        )
        if not local_records[0].bindUID:
            yield local_records[0].update(bindUID=str(uuid4()))

        returnValue((records, local_records[0].bindUID,))


    @inTransactionWrapper
    @inlineCallbacks
    def makeSharedByCollections(self, txn, records, calendar_id):
        """
        Create L{CalendarBindRecord} records in the local store.
        """

        for shareeUID, record in records:
            shareeHome = yield txn.calendarHomeWithUID(shareeUID, create=True)

            # First look for an existing record that could be present if the migrating user had
            # previously shared with this sharee as a cross-pod share
            oldrecord = yield CalendarBindRecord.querysimple(
                txn,
                calendarHomeResourceID=shareeHome.id(),
                calendarResourceName=record.calendarResourceName,
            )

            # FIXME: need to figure out sync-token and bind revision changes

            if oldrecord:
                # Point old record to the new local calendar being shared
                yield oldrecord[0].update(
                    calendarResourceID=calendar_id,
                    bindRevision=0,
                )
            else:
                # Map the record resource ids and insert a new record
                record.calendarHomeResourceID = shareeHome.id()
                record.calendarResourceID = calendar_id
                record.bindRevision = 0
                yield record.insert(txn)


    @inTransactionWrapper
    @inlineCallbacks
    def updatedRemoteSharedByCollections(self, txn, remote_id, bindUID):
        """
        Get all the existing L{CalendarBindRecord}'s from the remote store.
        """

        remote_home = yield self._remoteHome(txn)
        remote_calendar = yield remote_home.childWithID(remote_id)
        records = yield remote_calendar.migrateBindRecords(bindUID)
        returnValue(records)


    @inlineCallbacks
    def sharedToCollectionsReconcile(self):
        """
        Sync all the collections shared to the migrating user from the remote store.

        Here is the logic we need: first assume we have three pods: A, B, C, and we are migrating a user from A->B. We start
        with a set of shares (X -> Y - where X is the sharer and Y the sharee) with sharee on pod A. We migrate the sharee to pod B. We
        then need to have a set of bind records on pod B, and adjust the set on pod A. Note that no changes are required on pod C.

        Original      |  Changes                     | Changes
        Shares        |  on B                        | on A
        --------------|------------------------------|---------------------
        A -> A        |  A -> B (new)                | A -> B (modify existing)
        B -> A        |  B -> B (modify existing)    | (removed)
        C -> A        |  C -> B (new)                | (removed)
        """
        records = yield self.sharedToCollectionRecords()
        records = records.items()
        len_records = len(records)

        while records:
            yield self.makeSharedToCollections(records[:50])
            records = records[50:]

        returnValue(len_records)


    @inTransactionWrapper
    @inlineCallbacks
    def sharedToCollectionRecords(self, txn):
        """
        Get the names and sharer UIDs for remote shared calendars.
        """

        # List of calendars from the remote side
        home = yield self._remoteHome(txn)
        if home is None:
            returnValue(None)
        results = yield home.sharedToBindRecords()
        returnValue(results)


    @inTransactionWrapper
    @inlineCallbacks
    def makeSharedToCollections(self, txn, records):
        """
        Create L{CalendarBindRecord} records in the local store.
        """

        for sharerUID, (shareeRecord, ownerRecord, metadataRecord) in records:
            sharerHome = yield txn.calendarHomeWithUID(sharerUID, create=True)

            # We need to figure out the right thing to do based on whether the sharer is local to this pod
            # (the one where the migrated user will be hosted) vs located on another pod

            if sharerHome.normal():
                # First look for an existing record that must be present if the migrating user had
                # previously been shared with by this sharee
                oldrecord = yield CalendarBindRecord.querysimple(
                    txn,
                    calendarResourceName=shareeRecord.calendarResourceName,
                )
                if len(oldrecord) == 1:
                    # Point old record to the new local calendar home
                    yield oldrecord[0].update(
                        calendarHomeResourceID=self.homeId,
                    )
                else:
                    raise AssertionError("An existing share must be present")
            else:
                # We have an external user. That sharer may have already shared the calendar with some other user
                # on this pod, in which case there is already a CALENDAR table entry for it, and we need the
                # resource ID from that to use in the new CALENDAR_BIND record we create. If a pre-existing share
                # is not present, then we have to create the CALENDAR table entry and associated pieces

                remote_id = shareeRecord.calendarResourceID

                # Look for pre-existing share with the same external ID
                oldrecord = yield CalendarBindRecord.querysimple(
                    txn,
                    calendarHomeResourceID=sharerHome.id(),
                    bindUID=ownerRecord.bindUID,
                )
                if oldrecord:
                    # Map the record resource ids and insert a new record
                    calendar_id = oldrecord.calendarResourceID
                else:
                    sharerView = yield sharerHome.createCollectionForExternalShare(
                        ownerRecord.calendarResourceName,
                        ownerRecord.bindUID,
                        metadataRecord.supportedComponents,
                    )
                    calendar_id = sharerView.id()

                shareeRecord.calendarHomeResourceID = self.homeId
                shareeRecord.calendarResourceID = calendar_id
                shareeRecord.bindRevision = 0
                yield shareeRecord.insert(txn)

                yield self.updatedRemoteSharedToCollection(remote_id, txn=txn)


    @inTransactionWrapper
    @inlineCallbacks
    def updatedRemoteSharedToCollection(self, txn, remote_id):
        """
        Get all the existing L{CalendarBindRecord}'s from the remote store.
        """

        remote_home = yield self._remoteHome(txn)
        remote_calendar = yield remote_home.childWithID(remote_id)
        records = yield remote_calendar.migrateBindRecords(None)
        returnValue(records)
