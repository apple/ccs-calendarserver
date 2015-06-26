# -*- test-case-name: twext.enterprise.dal.test.test_record -*-
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

from twext.enterprise.dal.syntax import Max, Select, Parameter, Delete, Insert, \
    Update, ColumnSyntax, TableSyntax, Upper, utcNowSQL
from twext.python.clsprop import classproperty
from twext.python.log import Logger
from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from txdav.base.datastore.util import normalizeUUIDOrNot
from txdav.common.datastore.sql_tables import schema
from txdav.common.icommondatastore import SyncTokenValidException, \
    ENOTIFICATIONTYPE, ECALENDARTYPE, EADDRESSBOOKTYPE
import time
from uuid import UUID

log = Logger()


"""
Classes and methods for the SQL store.
"""

class _EmptyCacher(object):

    def set(self, key, value):
        return succeed(True)


    def get(self, key, withIdentifier=False):
        return succeed(None)


    def delete(self, key):
        return succeed(True)



class _SharedSyncLogic(object):
    """
    Logic for maintaining sync-token shared between notification collections and
    shared collections.
    """

    @classproperty
    def _childSyncTokenQuery(cls):
        """
        DAL query for retrieving the sync token of a L{CommonHomeChild} based on
        its resource ID.
        """
        rev = cls._revisionsSchema
        return Select([Max(rev.REVISION)], From=rev,
                      Where=rev.RESOURCE_ID == Parameter("resourceID"))


    @classmethod
    def _revisionsForResourceIDs(cls, resourceIDs):
        rev = cls._revisionsSchema
        return Select(
            [rev.RESOURCE_ID, Max(rev.REVISION)],
            From=rev,
            Where=rev.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))).And(
                (rev.RESOURCE_NAME != None).Or(rev.DELETED == False)),
            GroupBy=rev.RESOURCE_ID
        )


    def revisionFromToken(self, token):
        if token is None:
            return 0
        elif isinstance(token, str) or isinstance(token, unicode):
            _ignore_uuid, revision = token.split("_", 1)
            return int(revision)
        else:
            return token


    @inlineCallbacks
    def syncToken(self):
        if self._syncTokenRevision is None:
            self._syncTokenRevision = yield self.syncTokenRevision()
        returnValue(("%s_%s" % (self._resourceID, self._syncTokenRevision,)))


    @inlineCallbacks
    def syncTokenRevision(self):
        revision = (yield self._childSyncTokenQuery.on(self._txn, resourceID=self._resourceID))[0][0]
        if revision is None:
            revision = int((yield self._txn.calendarserverValue("MIN-VALID-REVISION")))
        returnValue(revision)


    @classmethod
    @inlineCallbacks
    def childSyncTokenRevisions(cls, home, childResourceIDs):
        rows = (yield cls._revisionsForResourceIDs(childResourceIDs).on(home._txn, resourceIDs=childResourceIDs))
        revisions = dict(rows)

        # Add in any that were missing - this assumes that childResourceIDs were all valid to begin with
        missingIDs = set(childResourceIDs) - set(revisions.keys())
        if missingIDs:
            min_revision = int((yield home._txn.calendarserverValue("MIN-VALID-REVISION")))
            for resourceID in missingIDs:
                revisions[resourceID] = min_revision
        returnValue(revisions)


    def objectResourcesSinceToken(self, token):
        raise NotImplementedError()


    @classmethod
    def _objectNamesSinceRevisionQuery(cls, deleted=True):
        """
        DAL query for (resource, deleted-flag)
        """
        rev = cls._revisionsSchema
        where = (rev.REVISION > Parameter("revision")).And(rev.RESOURCE_ID == Parameter("resourceID"))
        if not deleted:
            where = where.And(rev.DELETED == False)
        return Select(
            [rev.RESOURCE_NAME, rev.DELETED],
            From=rev,
            Where=where,
        )


    def resourceNamesSinceToken(self, token):
        """
        Return the changed and deleted resources since a particular sync-token. This simply extracts
        the revision from from the token then calls L{resourceNamesSinceRevision}.

        @param revision: the revision to determine changes since
        @type revision: C{int}
        """

        return self.resourceNamesSinceRevision(self.revisionFromToken(token))


    @inlineCallbacks
    def resourceNamesSinceRevision(self, revision):
        """
        Return the changed and deleted resources since a particular revision.

        @param revision: the revision to determine changes since
        @type revision: C{int}
        """
        changed = []
        deleted = []
        invalid = []
        if revision:
            minValidRevision = yield self._txn.calendarserverValue("MIN-VALID-REVISION")
            if revision < int(minValidRevision):
                raise SyncTokenValidException

            results = [
                (name if name else "", removed) for name, removed in (
                    yield self._objectNamesSinceRevisionQuery().on(
                        self._txn, revision=revision, resourceID=self._resourceID)
                )
            ]
            results.sort(key=lambda x: x[1])

            for name, wasdeleted in results:
                if name:
                    if wasdeleted:
                        deleted.append(name)
                    else:
                        changed.append(name)
        else:
            changed = yield self.listObjectResources()

        returnValue((changed, deleted, invalid))


    @classproperty
    def _removeDeletedRevision(cls):
        rev = cls._revisionsSchema
        return Delete(From=rev,
                      Where=(rev.HOME_RESOURCE_ID == Parameter("homeID")).And(
                          rev.COLLECTION_NAME == Parameter("collectionName")))


    @classproperty
    def _addNewRevision(cls):
        rev = cls._revisionsSchema
        return Insert(
            {
                rev.HOME_RESOURCE_ID: Parameter("homeID"),
                rev.RESOURCE_ID: Parameter("resourceID"),
                rev.COLLECTION_NAME: Parameter("collectionName"),
                rev.RESOURCE_NAME: None,
                # Always starts false; may be updated to be a tombstone
                # later.
                rev.DELETED: False
            },
            Return=[rev.REVISION]
        )


    @inlineCallbacks
    def _initSyncToken(self):
        yield self._removeDeletedRevision.on(
            self._txn, homeID=self._home._resourceID, collectionName=self._name
        )
        self._syncTokenRevision = (yield (
            self._addNewRevision.on(self._txn, homeID=self._home._resourceID,
                                    resourceID=self._resourceID,
                                    collectionName=self._name)))[0][0]
        self._txn.bumpRevisionForObject(self)


    @classproperty
    def _renameSyncTokenQuery(cls):
        """
        DAL query to change sync token for a rename (increment and adjust
        resource name).
        """
        rev = cls._revisionsSchema
        return Update(
            {
                rev.REVISION: schema.REVISION_SEQ,
                rev.COLLECTION_NAME: Parameter("name"),
                rev.MODIFIED: utcNowSQL,
            },
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And
                  (rev.RESOURCE_NAME == None),
            Return=rev.REVISION
        )


    @inlineCallbacks
    def _renameSyncToken(self):
        rows = yield self._renameSyncTokenQuery.on(
            self._txn, name=self._name, resourceID=self._resourceID)
        if rows:
            self._syncTokenRevision = rows[0][0]
            self._txn.bumpRevisionForObject(self)
        else:
            yield self._initSyncToken()


    @classproperty
    def _bumpSyncTokenQuery(cls):
        """
        DAL query to change collection sync token. Note this can impact multiple rows if the
        collection is shared.
        """
        rev = cls._revisionsSchema
        return Update(
            {
                rev.REVISION: schema.REVISION_SEQ,
                rev.MODIFIED: utcNowSQL,
            },
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And
                  (rev.RESOURCE_NAME == None)
        )


    @inlineCallbacks
    def _bumpSyncToken(self):

        if not self._txn.isRevisionBumpedAlready(self):
            self._txn.bumpRevisionForObject(self)
            yield self._bumpSyncTokenQuery.on(
                self._txn,
                resourceID=self._resourceID,
            )
            self._syncTokenRevision = None


    @classproperty
    def _deleteSyncTokenQuery(cls):
        """
        DAL query to remove all child revision information. The revision for the collection
        itself is not touched.
        """
        rev = cls._revisionsSchema
        return Delete(
            From=rev,
            Where=(rev.HOME_RESOURCE_ID == Parameter("homeID")).And
                  (rev.RESOURCE_ID == Parameter("resourceID")).And
                  (rev.COLLECTION_NAME == None)
        )


    @classproperty
    def _sharedRemovalQuery(cls):
        """
        DAL query to indicate a shared collection has been deleted.
        """
        rev = cls._revisionsSchema
        return Update(
            {
                rev.RESOURCE_ID: None,
                rev.REVISION: schema.REVISION_SEQ,
                rev.DELETED: True,
                rev.MODIFIED: utcNowSQL,
            },
            Where=(rev.HOME_RESOURCE_ID == Parameter("homeID")).And(
                rev.RESOURCE_ID == Parameter("resourceID")).And(
                rev.RESOURCE_NAME == None)
        )


    @classproperty
    def _unsharedRemovalQuery(cls):
        """
        DAL query to indicate an owned collection has been deleted.
        """
        rev = cls._revisionsSchema
        return Update(
            {
                rev.RESOURCE_ID: None,
                rev.REVISION: schema.REVISION_SEQ,
                rev.DELETED: True,
                rev.MODIFIED: utcNowSQL,
            },
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                rev.RESOURCE_NAME == None),
        )


    @inlineCallbacks
    def _deletedSyncToken(self, sharedRemoval=False):
        """
        When a collection is deleted we remove all the revision information for its child resources.
        We update the collection's sync token to indicate it has been deleted - that way a sync on
        the home collection can report the deletion of the collection.

        @param sharedRemoval: indicates whether the collection being removed is shared
        @type sharedRemoval: L{bool}
        """
        # Remove all child entries
        yield self._deleteSyncTokenQuery.on(self._txn,
                                            homeID=self._home._resourceID,
                                            resourceID=self._resourceID)

        # If this is a share being removed then we only mark this one specific
        # home/resource-id as being deleted.  On the other hand, if it is a
        # non-shared collection, then we need to mark all collections
        # with the resource-id as being deleted to account for direct shares.
        if sharedRemoval:
            yield self._sharedRemovalQuery.on(self._txn,
                                              homeID=self._home._resourceID,
                                              resourceID=self._resourceID)
        else:
            yield self._unsharedRemovalQuery.on(self._txn,
                                                resourceID=self._resourceID)
        self._syncTokenRevision = None


    def _insertRevision(self, name):
        return self._changeRevision("insert", name)


    def _updateRevision(self, name):
        return self._changeRevision("update", name)


    def _deleteRevision(self, name):
        return self._changeRevision("delete", name)


    @classproperty
    def _deleteBumpTokenQuery(cls):
        rev = cls._revisionsSchema
        return Update(
            {
                rev.REVISION: schema.REVISION_SEQ,
                rev.DELETED: True,
                rev.MODIFIED: utcNowSQL,
            },
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                rev.RESOURCE_NAME == Parameter("name")),
            Return=rev.REVISION
        )


    @classproperty
    def _updateBumpTokenQuery(cls):
        rev = cls._revisionsSchema
        return Update(
            {
                rev.REVISION: schema.REVISION_SEQ,
                rev.MODIFIED: utcNowSQL,
            },
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                rev.RESOURCE_NAME == Parameter("name")),
            Return=rev.REVISION
        )


    @classproperty
    def _insertFindPreviouslyNamedQuery(cls):
        rev = cls._revisionsSchema
        return Select(
            [rev.RESOURCE_ID],
            From=rev,
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                rev.RESOURCE_NAME == Parameter("name"))
        )


    @classproperty
    def _updatePreviouslyNamedQuery(cls):
        rev = cls._revisionsSchema
        return Update(
            {
                rev.REVISION: schema.REVISION_SEQ,
                rev.DELETED: False,
                rev.MODIFIED: utcNowSQL,
            },
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                rev.RESOURCE_NAME == Parameter("name")),
            Return=rev.REVISION
        )


    @classproperty
    def _completelyNewRevisionQuery(cls):
        rev = cls._revisionsSchema
        return Insert(
            {
                rev.HOME_RESOURCE_ID: Parameter("homeID"),
                rev.RESOURCE_ID: Parameter("resourceID"),
                rev.RESOURCE_NAME: Parameter("name"),
                rev.REVISION: schema.REVISION_SEQ,
                rev.DELETED: False
            },
            Return=rev.REVISION
        )


    @classproperty
    def _completelyNewDeletedRevisionQuery(cls):
        rev = cls._revisionsSchema
        return Insert(
            {
                rev.HOME_RESOURCE_ID: Parameter("homeID"),
                rev.RESOURCE_ID: Parameter("resourceID"),
                rev.RESOURCE_NAME: Parameter("name"),
                rev.REVISION: schema.REVISION_SEQ,
                rev.DELETED: True
            },
            Return=rev.REVISION
        )


    @inlineCallbacks
    def _changeRevision(self, action, name):

        # Need to handle the case where for some reason the revision entry is
        # actually missing. For a "delete" we don't care, for an "update" we
        # will turn it into an "insert".
        if action == "delete":
            rows = (
                yield self._deleteBumpTokenQuery.on(
                    self._txn, resourceID=self._resourceID, name=name))
            if rows:
                self._syncTokenRevision = rows[0][0]
            else:
                self._syncTokenRevision = (
                    yield self._completelyNewDeletedRevisionQuery.on(
                        self._txn, homeID=self.ownerHome()._resourceID,
                        resourceID=self._resourceID, name=name)
                )[0][0]

        elif action == "update":
            rows = (
                yield self._updateBumpTokenQuery.on(
                    self._txn, resourceID=self._resourceID, name=name))
            if rows:
                self._syncTokenRevision = rows[0][0]
            else:
                self._syncTokenRevision = (
                    yield self._completelyNewRevisionQuery.on(
                        self._txn, homeID=self.ownerHome()._resourceID,
                        resourceID=self._resourceID, name=name)
                )[0][0]

        elif action == "insert":
            # Note that an "insert" may happen for a resource that previously
            # existed and then was deleted. In that case an entry in the
            # REVISIONS table still exists so we have to detect that and do db
            # INSERT or UPDATE as appropriate

            found = bool((
                yield self._insertFindPreviouslyNamedQuery.on(
                    self._txn, resourceID=self._resourceID, name=name)))
            if found:
                self._syncTokenRevision = (
                    yield self._updatePreviouslyNamedQuery.on(
                        self._txn, resourceID=self._resourceID, name=name)
                )[0][0]
            else:
                self._syncTokenRevision = (
                    yield self._completelyNewRevisionQuery.on(
                        self._txn, homeID=self.ownerHome()._resourceID,
                        resourceID=self._resourceID, name=name)
                )[0][0]
        yield self._maybeNotify()
        returnValue(self._syncTokenRevision)


    def _maybeNotify(self):
        """
        Maybe notify changed.  (Overridden in NotificationCollection.)
        """
        return succeed(None)



def determineNewest(uid, homeType):
    """
    Construct a query to determine the modification time of the newest object
    in a given home.

    @param uid: the UID of the home to scan.
    @type uid: C{str}

    @param homeType: The type of home to scan; C{ECALENDARTYPE},
        C{ENOTIFICATIONTYPE}, or C{EADDRESSBOOKTYPE}.
    @type homeType: C{int}

    @return: A select query that will return a single row containing a single
        column which is the maximum value.
    @rtype: L{Select}
    """
    if homeType == ENOTIFICATIONTYPE:
        return Select(
            [Max(schema.NOTIFICATION.MODIFIED)],
            From=schema.NOTIFICATION_HOME.join(
                schema.NOTIFICATION,
                on=schema.NOTIFICATION_HOME.RESOURCE_ID ==
                schema.NOTIFICATION.NOTIFICATION_HOME_RESOURCE_ID),
            Where=schema.NOTIFICATION_HOME.OWNER_UID == uid
        )
    homeTypeName = {ECALENDARTYPE: "CALENDAR",
                    EADDRESSBOOKTYPE: "ADDRESSBOOK"}[homeType]
    home = getattr(schema, homeTypeName + "_HOME")
    bind = getattr(schema, homeTypeName + "_BIND")
    child = getattr(schema, homeTypeName)
    obj = getattr(schema, homeTypeName + "_OBJECT")
    return Select(
        [Max(obj.MODIFIED)],
        From=home.join(bind, on=bind.HOME_RESOURCE_ID == home.RESOURCE_ID).join(
            child, on=child.RESOURCE_ID == bind.RESOURCE_ID).join(
            obj, on=obj.PARENT_RESOURCE_ID == child.RESOURCE_ID),
        Where=(bind.BIND_MODE == 0).And(home.OWNER_UID == uid)
    )



@inlineCallbacks
def mergeHomes(sqlTxn, one, other, homeType):
    """
    Merge two homes together.  This determines which of C{one} or C{two} is
    newer - that is, has been modified more recently - and pulls all the data
    from the older into the newer home.  Then, it changes the UID of the old
    home to its UID, normalized and prefixed with "old.", and then re-names the
    new home to its name, normalized.

    Because the UIDs of both homes have changed, B{both one and two will be
    invalid to all other callers from the start of the invocation of this
    function}.

    @param sqlTxn: the transaction to use
    @type sqlTxn: A L{CommonTransaction}

    @param one: A calendar home.
    @type one: L{ICalendarHome}

    @param two: Another, different calendar home.
    @type two: L{ICalendarHome}

    @param homeType: The type of home to scan; L{ECALENDARTYPE} or
        L{EADDRESSBOOKTYPE}.
    @type homeType: C{int}

    @return: a L{Deferred} which fires with with the newer of C{one} or C{two},
        into which the data from the other home has been merged, when the merge
        is complete.
    """
    from txdav.caldav.datastore.util import migrateHome as migrateCalendarHome
    from txdav.carddav.datastore.util import migrateHome as migrateABHome
    migrateHome = {EADDRESSBOOKTYPE: migrateABHome,
                   ECALENDARTYPE: migrateCalendarHome,
                   ENOTIFICATIONTYPE: _dontBotherWithNotifications}[homeType]
    homeTable = {EADDRESSBOOKTYPE: schema.ADDRESSBOOK_HOME,
                 ECALENDARTYPE: schema.CALENDAR_HOME,
                 ENOTIFICATIONTYPE: schema.NOTIFICATION_HOME}[homeType]
    both = []
    both.append([one,
                 (yield determineNewest(one.uid(), homeType).on(sqlTxn))])
    both.append([other,
                 (yield determineNewest(other.uid(), homeType).on(sqlTxn))])
    both.sort(key=lambda x: x[1])

    older = both[0][0]
    newer = both[1][0]
    yield migrateHome(older, newer, merge=True)
    # Rename the old one to 'old.<correct-guid>'
    newNormalized = normalizeUUIDOrNot(newer.uid())
    oldNormalized = normalizeUUIDOrNot(older.uid())
    yield _renameHome(sqlTxn, homeTable, older.uid(), "old." + oldNormalized)
    # Rename the new one to '<correct-guid>'
    if newer.uid() != newNormalized:
        yield _renameHome(sqlTxn, homeTable, newer.uid(), newNormalized)
    yield returnValue(newer)



def _renameHome(txn, table, oldUID, newUID):
    """
    Rename a calendar, addressbook, or notification home.  Note that this
    function is only safe in transactions that have had caching disabled, and
    more specifically should only ever be used during upgrades.  Running this
    in a normal transaction will have unpredictable consequences, especially
    with respect to memcache.

    @param txn: an SQL transaction to use for this update
    @type txn: L{twext.enterprise.ienterprise.IAsyncTransaction}

    @param table: the storage table of the desired home type
    @type table: L{TableSyntax}

    @param oldUID: the old UID, the existing home's UID
    @type oldUID: L{str}

    @param newUID: the new UID, to change the UID to
    @type newUID: L{str}

    @return: a L{Deferred} which fires when the home is renamed.
    """
    return Update({table.OWNER_UID: newUID},
                  Where=table.OWNER_UID == oldUID).on(txn)



def _dontBotherWithNotifications(older, newer, merge):
    """
    Notifications are more transient and can be easily worked around; don't
    bother to migrate all of them when there is a UUID case mismatch.
    """
    pass



@inlineCallbacks
def _normalizeHomeUUIDsIn(t, homeType):
    """
    Normalize the UUIDs in the given L{txdav.common.datastore.CommonStore}.

    This changes the case of the UUIDs in the calendar home.

    @param t: the transaction to normalize all the UUIDs in.
    @type t: L{CommonStoreTransaction}

    @param homeType: The type of home to scan, L{ECALENDARTYPE},
        L{EADDRESSBOOKTYPE}, or L{ENOTIFICATIONTYPE}.
    @type homeType: C{int}

    @return: a L{Deferred} which fires with C{None} when the UUID normalization
        is complete.
    """
    from txdav.caldav.datastore.util import fixOneCalendarHome
    homeTable = {EADDRESSBOOKTYPE: schema.ADDRESSBOOK_HOME,
                 ECALENDARTYPE: schema.CALENDAR_HOME,
                 ENOTIFICATIONTYPE: schema.NOTIFICATION_HOME}[homeType]
    homeTypeName = homeTable.model.name.split("_")[0]

    allUIDs = yield Select([homeTable.OWNER_UID],
                           From=homeTable,
                           OrderBy=homeTable.OWNER_UID).on(t)
    total = len(allUIDs)
    allElapsed = []
    for n, [UID] in enumerate(allUIDs):
        start = time.time()
        if allElapsed:
            estimate = "%0.3d" % ((sum(allElapsed) / len(allElapsed)) *
                                  total - n)
        else:
            estimate = "unknown"
        log.info(
            "Scanning UID {uid} [{homeType}] "
            "({pct:0.2d}%, {estimate} seconds remaining)...",
            uid=UID, pct=(n / float(total)) * 100, estimate=estimate,
            homeType=homeTypeName
        )
        other = None
        this = yield _getHome(t, homeType, UID)
        if homeType == ECALENDARTYPE:
            fixedThisHome = yield fixOneCalendarHome(this)
        else:
            fixedThisHome = 0
        fixedOtherHome = 0
        if this is None:
            log.info(
                "{uid!r} appears to be missing, already processed", uid=UID
            )
        try:
            uuidobj = UUID(UID)
        except ValueError:
            pass
        else:
            newname = str(uuidobj).upper()
            if UID != newname:
                log.info(
                    "Detected case variance: {uid} {newuid}[{homeType}]",
                    uid=UID, newuid=newname, homeType=homeTypeName
                )
                other = yield _getHome(t, homeType, newname)
                if other is None:
                    # No duplicate: just fix the name.
                    yield _renameHome(t, homeTable, UID, newname)
                else:
                    if homeType == ECALENDARTYPE:
                        fixedOtherHome = yield fixOneCalendarHome(other)
                    this = yield mergeHomes(t, this, other, homeType)
                # NOTE: WE MUST NOT TOUCH EITHER HOME OBJECT AFTER THIS POINT.
                # THE UIDS HAVE CHANGED AND ALL OPERATIONS WILL FAIL.

        end = time.time()
        elapsed = end - start
        allElapsed.append(elapsed)
        log.info(
            "Scanned UID {uid}; {elapsed} seconds elapsed,"
            " {fixes} properties fixed ({duplicate} fixes in duplicate).",
            uid=UID, elapsed=elapsed, fixes=fixedThisHome,
            duplicate=fixedOtherHome
        )
    returnValue(None)



def _getHome(txn, homeType, uid):
    """
    Like L{CommonHome.homeWithUID} but also honoring ENOTIFICATIONTYPE which
    isn't I{really} a type of home.

    @param txn: the transaction to retrieve the home from
    @type txn: L{CommonStoreTransaction}

    @param homeType: L{ENOTIFICATIONTYPE}, L{ECALENDARTYPE}, or
        L{EADDRESSBOOKTYPE}.

    @param uid: the UID of the home to retrieve.
    @type uid: L{str}

    @return: a L{Deferred} that fires with the L{CommonHome} or
        L{NotificationHome} when it has been retrieved.
    """
    if homeType == ENOTIFICATIONTYPE:
        return txn.notificationsWithUID(uid)
    else:
        return txn.homeWithUID(homeType, uid)



@inlineCallbacks
def _normalizeColumnUUIDs(txn, column):
    """
    Upper-case the UUIDs in the given SQL DAL column.

    @param txn: The transaction.
    @type txn: L{CommonStoreTransaction}

    @param column: the column, which may contain UIDs, to normalize.
    @type column: L{ColumnSyntax}

    @return: A L{Deferred} that will fire when the UUID normalization of the
        given column has completed.
    """
    tableModel = column.model.table
    # Get a primary key made of column syntax objects for querying and
    # comparison later.
    pkey = [ColumnSyntax(columnModel)
            for columnModel in tableModel.primaryKey]
    for row in (yield Select([column] + pkey,
                             From=TableSyntax(tableModel)).on(txn)):
        before = row[0]
        pkeyparts = row[1:]
        after = normalizeUUIDOrNot(before)
        if after != before:
            where = _AndNothing
            # Build a where clause out of the primary key and the parts of the
            # primary key that were found.
            for pkeycol, pkeypart in zip(pkeyparts, pkey):
                where = where.And(pkeycol == pkeypart)
            yield Update({column: after}, Where=where).on(txn)



class _AndNothing(object):
    """
    Simple placeholder for iteratively generating a 'Where' clause; the 'And'
    just returns its argument, so it can be used at the start of the loop.
    """
    @staticmethod
    def And(self):
        """
        Return the argument.
        """
        return self



@inlineCallbacks
def _needsNormalizationUpgrade(txn):
    """
    Determine whether a given store requires a UUID normalization data upgrade.

    @param txn: the transaction to use
    @type txn: L{CommonStoreTransaction}

    @return: a L{Deferred} that fires with C{True} or C{False} depending on
        whether we need the normalization upgrade or not.
    """
    for x in [schema.CALENDAR_HOME, schema.ADDRESSBOOK_HOME,
              schema.NOTIFICATION_HOME]:
        slct = Select([x.OWNER_UID], From=x,
                      Where=x.OWNER_UID != Upper(x.OWNER_UID))
        rows = yield slct.on(txn)
        if rows:
            for [uid] in rows:
                if normalizeUUIDOrNot(uid) != uid:
                    returnValue(True)
    returnValue(False)



@inlineCallbacks
def fixUUIDNormalization(store):
    """
    Fix all UUIDs in the given SQL store to be in a canonical form;
    00000000-0000-0000-0000-000000000000 format and upper-case.
    """
    t = store.newTransaction(disableCache=True)

    # First, let's see if there are any calendar, addressbook, or notification
    # homes that have a de-normalized OWNER_UID.  If there are none, then we can
    # early-out and avoid the tedious and potentially expensive inspection of
    # oodles of calendar data.
    if not (yield _needsNormalizationUpgrade(t)):
        log.info("No potentially denormalized UUIDs detected, "
                 "skipping normalization upgrade.")
        yield t.abort()
        returnValue(None)
    try:
        yield _normalizeHomeUUIDsIn(t, ECALENDARTYPE)
        yield _normalizeHomeUUIDsIn(t, EADDRESSBOOKTYPE)
        yield _normalizeHomeUUIDsIn(t, ENOTIFICATIONTYPE)
        yield _normalizeColumnUUIDs(t, schema.RESOURCE_PROPERTY.VIEWER_UID)
        yield _normalizeColumnUUIDs(t, schema.APN_SUBSCRIPTIONS.SUBSCRIBER_GUID)
    except:
        log.failure("Unable to normalize UUIDs")
        yield t.abort()
        # There's a lot of possible problems here which are very hard to test
        # for individually; unexpected data that might cause constraint
        # violations under one of the manipulations done by
        # normalizeHomeUUIDsIn. Since this upgrade does not come along with a
        # schema version bump and may be re- attempted at any time, just raise
        # the exception and log it so that we can try again later, and the
        # service will survive for everyone _not_ affected by this somewhat
        # obscure bug.
    else:
        yield t.commit()
