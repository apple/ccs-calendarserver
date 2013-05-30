# -*- test-case-name: txdav.base.propertystore.test.test_sql -*-
##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
PostgreSQL data store.
"""

__all__ = [
    "PropertyStore",
]


from twistedcaldav.memcacher import Memcacher

from twext.enterprise.dal.syntax import (
    Select, Parameter, Update, Insert, TableSyntax, Delete)

from txdav.xml.parser import WebDAVDocument
from txdav.common.icommondatastore import AllRetriesFailed
from txdav.common.datastore.sql_tables import schema
from txdav.base.propertystore.base import (AbstractPropertyStore,
                                           PropertyName, validKey)

from twisted.internet.defer import inlineCallbacks, returnValue


prop = schema.RESOURCE_PROPERTY

class PropertyStore(AbstractPropertyStore):

    _cacher = Memcacher("SQL.props", pickle=True, key_normalization=False)

    def __init__(self, *a, **kw):
        raise NotImplementedError(
            "do not construct directly, call PropertyStore.load()"
        )

    _allWithID = Select([prop.NAME, prop.VIEWER_UID, prop.VALUE],
                        From=prop,
                        Where=prop.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def _refresh(self, txn):
        """
        Load, or re-load, this object with the given transaction; first from
        memcache, then pulling from the database again.
        """
        # Cache existing properties in this object
        # Look for memcache entry first
        rows = yield self._cacher.get(str(self._resourceID))
        if rows is None:
            rows = yield self._allWithID.on(txn, resourceID=self._resourceID)
            yield self._cacher.set(str(self._resourceID),
                                   rows if rows is not None else ())
        for name, uid, value in rows:
            self._cached[(name, uid)] = value


    @classmethod
    @inlineCallbacks
    def load(cls, defaultuser, shareUser, txn, resourceID, created=False, notifyCallback=None):
        """
        @param notifyCallback: a callable used to trigger notifications when the
            property store changes.
        """
        self = cls.__new__(cls)
        super(PropertyStore, self).__init__(defaultuser, shareUser)
        self._txn = txn
        self._resourceID = resourceID
        self._cached = {}
        if not created:
            yield self._refresh(txn)
        self._notifyCallback = notifyCallback
        returnValue(self)


    @classmethod
    @inlineCallbacks
    def forMultipleResources(cls, defaultUser, txn,
                             childColumn, parentColumn, parentID):
        """
        Load all property stores for all objects in a collection.  This is used
        to optimize Depth:1 operations on that collection, by loading all
        relevant properties in a single query.

        @param defaultUser: the UID of the user who owns / is requesting the
            property stores; the ones whose per-user properties will be exposed.

        @type defaultUser: C{str}

        @param txn: the transaction within which to fetch the rows.

        @type txn: L{IAsyncTransaction}

        @param childColumn: The resource ID column for the child resources, i.e.
            the resources of the type for which this method will loading the
            property stores.

        @param parentColumn: The resource ID column for the parent resources.
            e.g. if childColumn is addressbook object's resource ID, then this
            should be addressbook's resource ID.

        @return: a L{Deferred} that fires with a C{dict} mapping resource ID (a
            value taken from C{childColumn}) to a L{PropertyStore} for that ID.
        """
        childTable = TableSyntax(childColumn.model.table)
        query = Select([
            childColumn,
            # XXX is that column necessary?  as per the 'on' clause it has to be
            # the same as prop.RESOURCE_ID anyway.
            prop.RESOURCE_ID, prop.NAME, prop.VIEWER_UID, prop.VALUE],
            From=prop.join(childTable, prop.RESOURCE_ID == childColumn,
                           'right'),
            Where=parentColumn == parentID
        )
        rows = yield query.on(txn)
        stores = cls._createMultipleStores(defaultUser, txn, rows)
        returnValue(stores)


    @classmethod
    @inlineCallbacks
    def forMultipleResourcesWithResourceIDs(cls, defaultUser, txn, resourceIDs):
        """
        Load all property stores for all specified resources.  This is used
        to optimize Depth:1 operations on that collection, by loading all
        relevant properties in a single query. Note that the caller of this
        method must make sure that the number of items being queried for is
        within a reasonable batch size. If the caller is itself batching
        related queries, that will take care of itself.

        @param defaultUser: the UID of the user who owns / is requesting the
            property stores; the ones whose per-user properties will be exposed.

        @type defaultUser: C{str}

        @param txn: the transaction within which to fetch the rows.

        @type txn: L{IAsyncTransaction}

        @param resourceIDs: The set of resource ID's to query.

        @return: a L{Deferred} that fires with a C{dict} mapping resource ID (a
            value taken from C{childColumn}) to a L{PropertyStore} for that ID.
        """
        query = Select([
            prop.RESOURCE_ID, prop.NAME, prop.VIEWER_UID, prop.VALUE],
            From=prop,
            Where=prop.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs)))
        )
        rows = yield query.on(txn, resourceIDs=resourceIDs)
        stores = cls._createMultipleStores(defaultUser, txn, rows)

        # Make sure we have a store for each resourceID even if no properties exist
        for resourceID in resourceIDs:
            if resourceID not in stores:
                store = cls.__new__(cls)
                super(PropertyStore, store).__init__(defaultUser)
                store._txn = txn
                store._resourceID = resourceID
                store._cached = {}
                stores[resourceID] = store

        returnValue(stores)


    @classmethod
    def _createMultipleStores(cls, defaultUser, txn, rows):
        """
        Create a set of stores for the set of rows passed in.
        """

        createdStores = {}
        for row in rows:
            if len(row) == 5:
                object_resource_id, resource_id, name, view_uid, value = row
            else:
                object_resource_id = None
                resource_id, name, view_uid, value = row
            if resource_id:
                if resource_id not in createdStores:
                    store = cls.__new__(cls)
                    super(PropertyStore, store).__init__(defaultUser)
                    store._txn = txn
                    store._resourceID = resource_id
                    store._cached = {}
                    createdStores[resource_id] = store
                createdStores[resource_id]._cached[(name, view_uid)] = value
            elif object_resource_id:
                store = cls.__new__(cls)
                super(PropertyStore, store).__init__(defaultUser)
                store._txn = txn
                store._resourceID = object_resource_id
                store._cached = {}
                createdStores[object_resource_id] = store

        return createdStores


    def _getitem_uid(self, key, uid):
        validKey(key)

        try:
            value = self._cached[(key.toString(), uid)]
        except KeyError:
            raise KeyError(key)

        return WebDAVDocument.fromString(value).root_element

    _updateQuery = Update({prop.VALUE: Parameter("value")},
                          Where=(
                              prop.RESOURCE_ID == Parameter("resourceID")).And(
                              prop.NAME == Parameter("name")).And(
                              prop.VIEWER_UID == Parameter("uid")))

    _insertQuery = Insert({prop.VALUE: Parameter("value"),
                           prop.RESOURCE_ID: Parameter("resourceID"),
                           prop.NAME: Parameter("name"),
                           prop.VIEWER_UID: Parameter("uid")})


    def _setitem_uid(self, key, value, uid):
        validKey(key)

        key_str = key.toString()
        value_str = value.toxml()

        tried = []

        wasCached = [(key_str, uid) in self._cached]
        self._cached[(key_str, uid)] = value_str
        @inlineCallbacks
        def trySetItem(txn):
            if tried:
                yield self._refresh(txn)
                wasCached[:] = [(key_str, uid) in self._cached]
            tried.append(True)
            if wasCached[0]:
                yield self._updateQuery.on(
                    txn, resourceID=self._resourceID, value=value_str,
                    name=key_str, uid=uid)
            else:
                yield self._insertQuery.on(
                    txn, resourceID=self._resourceID, value=value_str,
                    name=key_str, uid=uid)
            self._cacher.delete(str(self._resourceID))

        # Call the registered notification callback - we need to do this as a preCommit since it involves
        # a bunch of deferred operations, but this propstore api is not deferred. preCommit will execute
        # the deferreds properly, and it is fine to wait until everything else is done before sending the
        # notifications.
        if hasattr(self, "_notifyCallback") and self._notifyCallback is not None:
            self._txn.preCommit(self._notifyCallback)

        def justLogIt(f):
            f.trap(AllRetriesFailed)
            self.log.error("setting a property failed; probably nothing.")
        self._txn.subtransaction(trySetItem).addErrback(justLogIt)

    _deleteQuery = Delete(
        prop, Where=(prop.RESOURCE_ID == Parameter("resourceID")).And(
            prop.NAME == Parameter("name")).And(
                prop.VIEWER_UID == Parameter("uid"))
    )


    def _delitem_uid(self, key, uid):
        validKey(key)

        key_str = key.toString()
        del self._cached[(key_str, uid)]
        @inlineCallbacks
        def doIt(txn):
            yield self._deleteQuery.on(txn, lambda: KeyError(key),
                                 resourceID=self._resourceID,
                                 name=key_str, uid=uid
                                )
            self._cacher.delete(str(self._resourceID))

        # Call the registered notification callback - we need to do this as a preCommit since it involves
        # a bunch of deferred operations, but this propstore api is not deferred. preCommit will execute
        # the deferreds properly, and it is fine to wait until everything else is done before sending the
        # notifications.
        if hasattr(self, "_notifyCallback") and self._notifyCallback is not None:
            self._txn.preCommit(self._notifyCallback)

        def justLogIt(f):
            f.trap(AllRetriesFailed)
            self.log.error("setting a property failed; probably nothing.")
        self._txn.subtransaction(doIt).addErrback(justLogIt)


    def _keys_uid(self, uid):
        for cachedKey, cachedUID in self._cached.keys():
            if cachedUID == uid:
                yield PropertyName.fromString(cachedKey)

    _deleteResourceQuery = Delete(
        prop, Where=(prop.RESOURCE_ID == Parameter("resourceID"))
    )

    @inlineCallbacks
    def _removeResource(self):

        self._cached = {}
        yield self._deleteResourceQuery.on(self._txn, resourceID=self._resourceID)
        self._cacher.delete(str(self._resourceID))


    @inlineCallbacks
    def copyAllProperties(self, other):
        """
        Copy all the properties from another store into this one. This needs to be done
        independently of the UID.
        """

        rows = yield other._allWithID.on(other._txn, resourceID=other._resourceID)
        for key_str, uid, value_str in rows:
            wasCached = [(key_str, uid) in self._cached]
            if wasCached[0]:
                yield self._updateQuery.on(
                    self._txn, resourceID=self._resourceID, value=value_str,
                    name=key_str, uid=uid)
            else:
                yield self._insertQuery.on(
                    self._txn, resourceID=self._resourceID, value=value_str,
                    name=key_str, uid=uid)

        # Reload from the DB
        self._cached = {}
        self._cacher.delete(str(self._resourceID))
        yield self._refresh(self._txn)
