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

from collections import namedtuple
from functools import wraps

from twext.enterprise.dal.syntax import Select, Delete, Parameter, Insert, \
    Update
from twext.python.log import Logger
from twisted.internet.defer import returnValue, inlineCallbacks
from twisted.python.failure import Failure
from txdav.caldav.icalendarstore import ComponentUpdateState
from txdav.caldav.datastore.sql import ManagedAttachment
from txdav.common.datastore.sql_tables import schema
from txdav.common.idirectoryservice import DirectoryRecordNotFoundError

import uuid

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

    CalendarSyncState = namedtuple("CalendarSyncState", ("localID", "lastSyncToken",))

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


    def migratingUid(self):
        return "Migrating-{}".format(self.diruid)


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
        self.homeId = yield self.prepareCalendarHome()

        yield self.syncCalendarList()

        # sync home metadata such as alarms, default calendars, etc
        yield self.syncCalendarHomeMetaData()

        # TODO: sync attachments
        yield self.syncAttachments()


    @inlineCallbacks
    def finalSync(self):
        """
        Do the final sync up of any additional data, re-link sharing bind
        rows, recalculate quota etc.
        """

        # TODO: link attachments to resources: ATTACHMENT_CALENDAR_OBJECT table
        yield self.linkAttachments()

        # TODO: Re-write attachment URIs - not sure if we need this as reverse proxy may take care of it
        pass

        # TODO: shared collections reconcile
        pass

        # TODO: group attendee reconcile
        pass

        # TODO: group sharee reconcile
        pass

        # TODO: delegates reconcile
        pass

        # TODO: notifications
        pass

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
        # change the status column.
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

        home = yield txn.calendarHomeWithUID(self.migratingUid())
        if home is None:
            home = yield txn.calendarHomeWithUID(self.migratingUid(), create=True, migratingUID=self.diruid)
        returnValue(home.id())


    @inTransactionWrapper
    @inlineCallbacks
    def syncCalendarHomeMetaData(self, txn):
        """
        Make sure the home meta-data (alarms, default calendars) is properly sync'd
        """

        remote_home = yield self._remoteHome(txn=txn)
        local_home = yield txn.calendarHomeWithUID(self.migratingUid())
        yield local_home.copyMetadata(remote_home)


    @inlineCallbacks
    def _remoteHome(self, txn):
        """
        Create a synthetic external home object that maps to the actual remote home.

        @param ownerUID: directory uid of the user's home
        @type ownerUID: L{str}
        """

        from txdav.caldav.datastore.sql_external import CalendarHomeExternal
        resourceID = yield txn.store().conduit.send_home_resource_id(txn, self.record)
        home = CalendarHomeExternal(txn, self.record.uid, resourceID) if resourceID is not None else None
        if home:
            home._childClass = home._childClass._externalClass
        returnValue(home)


    @inlineCallbacks
    def syncCalendarList(self):
        """
        Synchronize each owned calendar.
        """

        # Remote sync details
        remote_sync_state = yield self.getCalendarSyncList()

        # TODO: get local sync details from local DB
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
                results[calendar.id()] = self.CalendarSyncState(0, sync_token)

        returnValue(results)


    @inTransactionWrapper
    @inlineCallbacks
    def getSyncState(self, txn):
        """
        Get local synchronization state for the home being migrated.
        """
        cm = schema.CALENDAR_MIGRATION
        rows = yield Select(
            columns=(cm.REMOTE_RESOURCE_ID, cm.CALENDAR_RESOURCE_ID, cm.LAST_SYNC_TOKEN,),
            From=cm,
            Where=(cm.CALENDAR_HOME_RESOURCE_ID == self.homeId)
        ).on(txn)
        returnValue(dict([(remote_id, self.CalendarSyncState(local_id, sync,)) for remote_id, local_id, sync in rows]))


    @inTransactionWrapper
    @inlineCallbacks
    def setSyncState(self, txn, details):
        """
        Get local synchronization state for the home being migrated.
        """
        cm = schema.CALENDAR_MIGRATION

        old_details = yield self.getSyncState(txn=txn)

        # Remove missing keys
        missing = set(old_details.keys()) - set(details.keys())
        if missing:
            yield Delete(
                From=cm,
                Where=(cm.CALENDAR_HOME_RESOURCE_ID == self.homeId).And(
                    cm.REMOTE_RESOURCE_ID.In(Parameter("missing", len(missing)))
                )
            ).on(txn, missing=missing)

        # Add new ones
        insert = set(details.keys()) - set(old_details.keys())
        for key in insert:
            yield Insert({
                cm.CALENDAR_HOME_RESOURCE_ID: self.homeId,
                cm.REMOTE_RESOURCE_ID: key,
                cm.CALENDAR_RESOURCE_ID: details[key].localID,
                cm.LAST_SYNC_TOKEN: details[key].lastSyncToken,
            }).on(txn)

        # Update existing ones
        updates = set(details.keys()) & set(old_details.keys())
        for key in updates:
            yield Update(
                {
                    cm.CALENDAR_RESOURCE_ID: details[key].localID,
                    cm.LAST_SYNC_TOKEN: details[key].lastSyncToken,
                },
                Where=(cm.CALENDAR_HOME_RESOURCE_ID == self.homeId).And(
                    cm.REMOTE_RESOURCE_ID == key
                )
            ).on(txn)


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
        home = yield txn.calendarHomeWithUID(self.migratingUid())
        for remoteID in set(local_sync_state.keys()) - set(remote_sync_state.keys()):
            calendar = yield home.childWithID(local_sync_state[remoteID].localID)
            if calendar is not None:
                yield calendar.purge()
            del local_sync_state[remoteID]

        # FIXME: does this need to be done since we have a cascade on the table?
        # yield self.setSyncState(local_sync_state, txn=txn)


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
        local_state = local_sync_state.get(remoteID)
        if local_state is None:
            localID = yield self.newCalendar()
            local_sync_state[remoteID] = self.CalendarSyncState(localID, None)

        localID = local_sync_state.get(remoteID).localID
        local_token = local_sync_state.get(remoteID).lastSyncToken

        remote_token = remote_sync_state[remoteID].lastSyncToken
        if local_token != remote_token:
            # Sync meta-data such as name, alarms, supported-components, transp, etc
            yield self.syncCalendarMetaData(localID, remoteID)

            # Sync object resources
            changed, deleted = yield self.findObjectsToSync(localID, remoteID, local_token)
            yield self.purgeDeletedObjectsInBatches(localID, deleted)
            yield self.updateChangedObjectsInBatches(localID, remoteID, changed)

        local_sync_state[remoteID] = self.CalendarSyncState(localID, remote_token)
        yield self.setSyncState(local_sync_state)


    @inTransactionWrapper
    @inlineCallbacks
    def newCalendar(self, txn):
        """
        Create a new local calendar to sync remote data to. We don't care about the name
        of the calendar right now - it will be sync'd later.
        """

        home = yield txn.calendarHomeWithUID(self.migratingUid())
        calendar = yield home.createChildWithName(str(uuid.uuid4()))
        returnValue(calendar.id())


    @inTransactionWrapper
    @inlineCallbacks
    def syncCalendarMetaData(self, txn, localID, remoteID):
        """
        Sync the metadata of a calendar from the remote side.

        @param localID: id of the local calendar to sync
        @type localID: L{int}
        @param remoteID: id of the remote calendar to sync with
        @type remoteID: L{int}
        """
        # Remote changes
        remote_home = yield self._remoteHome(txn)
        remote_calendar = yield remote_home.childWithID(remoteID)
        if remote_calendar is None:
            returnValue(None)

        # Check whether the deleted set items
        local_home = yield txn.calendarHomeWithUID(self.migratingUid())
        local_calendar = yield local_home.childWithID(localID)
        yield local_calendar.copyMetadata(remote_calendar)


    @inTransactionWrapper
    @inlineCallbacks
    def findObjectsToSync(self, txn, localID, remoteID, local_token):
        """
        Find the set of object resources that need to be sync'd from the remote
        side and the set that need to be removed locally. Take into account the
        possibility that this is a partial sync and removals or additions might
        be false positives.

        @param localID: id of the local calendar to sync
        @type localID: L{int}
        @param remoteID: id of the remote calendar to sync with
        @type remoteID: L{int}
        @param local_token: sync token last used to sync the calendar
        @type local_token: L{str}
        """

        # Remote changes
        remote_home = yield self._remoteHome(txn)
        remote_calendar = yield remote_home.childWithID(remoteID)
        if remote_calendar is None:
            returnValue(None)
        changed, deleted, _ignore_invalid = yield remote_calendar.resourceNamesSinceToken(local_token)

        # Check whether the deleted set items
        local_home = yield txn.calendarHomeWithUID(self.migratingUid())
        local_calendar = yield local_home.childWithID(localID)

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
    def purgeDeletedObjectsInBatches(self, localID, deleted):
        """
        Purge (silently remove) the specified object resources. This needs to
        succeed in the case where some or all resources have already been deleted.
        Do this in batches to keep transaction times small.

        @param localID: id of the local calendar to sync
        @type localID: L{int}
        @param deleted: list of names to purge
        @type deleted: L{list} of L{str}
        """

        remaining = list(deleted)
        while remaining:
            yield self.purgeBatch(localID, remaining[:self.BATCH_SIZE])
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
        local_home = yield txn.calendarHomeWithUID(self.migratingUid())
        local_calendar = yield local_home.childWithID(localID)
        local_objects = yield local_calendar.objectResourcesWithNames(purge_names)

        for local_object in local_objects:
            yield local_object.purge()


    @inlineCallbacks
    def updateChangedObjectsInBatches(self, localID, remoteID, changed):
        """
        Update the specified object resources. This needs to succeed in the
        case where some or all resources have already been deleted.
        Do this in batches to keep transaction times small.

        @param localID: id of the local calendar to sync
        @type localID: L{int}
        @param remoteID: id of the remote calendar to sync with
        @type remoteID: L{int}
        @param changed: list of names to update
        @type changed: L{list} of L{str}
        """

        remaining = list(changed)
        while remaining:
            yield self.updateBatch(localID, remoteID, remaining[:self.BATCH_SIZE])
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
        local_home = yield txn.calendarHomeWithUID(self.migratingUid())
        local_calendar = yield local_home.childWithID(localID)
        local_objects = yield local_calendar.objectResourcesWithNames(remaining)
        local_objects = dict([(obj.name(), obj) for obj in local_objects])

        # Sync ones that still exist - use txn._migrating together with stuffing the remote md5
        # value onto the component being stored to ensure that the md5 value stored locally
        # matches the remote one (which should help reduce the need for a client to resync
        # the data when moved from one pod to the other).
        txn._migrating = True
        com = schema.CALENDAR_OBJECT_MIGRATION
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
                yield Insert(
                    {
                        com.CALENDAR_HOME_RESOURCE_ID: self.homeId,
                        com.REMOTE_RESOURCE_ID: remote_object.id(),
                        com.LOCAL_RESOURCE_ID: local_object.id()
                    }
                ).on(txn)

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

        local_home = yield txn.calendarHomeWithUID(self.migratingUid())
        lattachments = yield local_home.getAllAttachments()
        lmap = dict([(attachment.id(), attachment) for attachment in lattachments])

        # Figure out the differences
        am = schema.ATTACHMENT_MIGRATION
        rows = yield Select(
            [am.REMOTE_RESOURCE_ID, am.LOCAL_RESOURCE_ID],
            From=am,
            Where=(am.CALENDAR_HOME_RESOURCE_ID == self.homeId),
        ).on(txn)
        mapping = dict(rows)

        # Removed - remove attachment and migration state
        removed = set(mapping.keys()) - set(rmap.keys())
        for remove_id in removed:
            local_id = mapping[remove_id]
            att = yield ManagedAttachment.load(txn, None, None, attachmentID=local_id)
            if att:
                yield att.remove(adjustQuota=False)
            yield Delete(
                From=am,
                Where=(am.LOCAL_RESOURCE_ID == local_id),
            ).on(txn)

        # Track which ones need attachment data sync'd over
        data_ids = set()

        # Added - add new attachment and migration state
        added = set(rmap.keys()) - set(mapping.keys())
        for added_id in added:
            attachment = yield ManagedAttachment._create(txn, None, self.homeId)
            yield Insert(
                {
                    am.CALENDAR_HOME_RESOURCE_ID: self.homeId,
                    am.REMOTE_RESOURCE_ID: added_id,
                    am.LOCAL_RESOURCE_ID: attachment.id(),
                }
            ).on(txn)
            data_ids.add(attachment.id())

        # Possible updates - check for md5 change and sync
        updates = set(mapping.keys()) & set(rmap.keys())
        for updated_id in updates:
            local_id = mapping[updated_id]
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
        local_home = yield txn.calendarHomeWithUID(self.migratingUid())
        attachment = yield local_home.getAttachmentByID(local_id)
        if attachment is None:
            returnValue(None)

        am = schema.ATTACHMENT_MIGRATION
        rows = yield Select(
            [am.LOCAL_RESOURCE_ID, am.REMOTE_RESOURCE_ID],
            From=am,
            Where=(am.CALENDAR_HOME_RESOURCE_ID == self.homeId),
        ).on(txn)
        mapping = dict(rows)
        remote_id = mapping.get(local_id)
        if remote_id is None:
            returnValue(None)

        # Read the data from the conduit
        yield remote_home.readAttachmentData(remote_id, attachment)


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
        while len(links):
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
        am = schema.ATTACHMENT_MIGRATION
        rows = yield Select(
            [am.REMOTE_RESOURCE_ID, am.LOCAL_RESOURCE_ID],
            From=am,
            Where=(am.CALENDAR_HOME_RESOURCE_ID == self.homeId),
        ).on(txn)
        attachmentIDMap = dict(rows)

        com = schema.CALENDAR_OBJECT_MIGRATION
        rows = yield Select(
            [com.REMOTE_RESOURCE_ID, com.LOCAL_RESOURCE_ID],
            From=com,
            Where=(com.CALENDAR_HOME_RESOURCE_ID == self.homeId),
        ).on(txn)
        objectIDMap = dict(rows)

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
            link._attachmentID = attachmentIDMap[link._attachmentID]
            link._calendarObjectID = objectIDMap[link._calendarObjectID]

            yield link.insert()
