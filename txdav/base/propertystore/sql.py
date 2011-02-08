# -*- test-case-name: txdav.base.propertystore.test.test_sql -*-
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

from txdav.base.propertystore.base import AbstractPropertyStore, PropertyName,\
    validKey

from twext.web2.dav.davxml import WebDAVDocument

from twisted.internet.defer import inlineCallbacks, returnValue

class PropertyStore(AbstractPropertyStore):

    cacher = Memcacher("propertystore.sql", pickle=True)

    def __init__(self, *a, **kw):
        raise NotImplementedError(
            "do not construct directly, call PropertyStore.load()"
        )


    @classmethod
    @inlineCallbacks
    def load(cls, defaultuser, txn, resourceID, created=False):
        self = cls.__new__(cls)
        super(PropertyStore, self).__init__(defaultuser)
        self._txn = txn
        self._resourceID = resourceID
        self._cached = {}
        if not created:
            
            # Cache existing properties in this object 

            # Look for memcache entry first
            rows = yield self.cacher.get(str(self._resourceID))
            
            if rows is None:
                rows = yield self._txn.execSQL(
                    """
                    select NAME, VIEWER_UID, VALUE from RESOURCE_PROPERTY
                    where RESOURCE_ID = %s
                    """,
                    [self._resourceID]
                )
                yield self.cacher.set(str(self._resourceID), rows if rows is not None else ())
            for name, uid, value in rows:
                self._cached[(name, uid)] = value


        returnValue(self)

    @classmethod
    @inlineCallbacks
    def loadAll(cls, defaultuser, txn, joinTable, joinColumn, parentIDColumn, parentID):
        """
        Return a list of property stores for all objects in a parent collection
        """
        rows = yield txn.execSQL(
            """
            select
              %s,
              RESOURCE_PROPERTY.RESOURCE_ID,
              RESOURCE_PROPERTY.NAME,
              RESOURCE_PROPERTY.VIEWER_UID,
              RESOURCE_PROPERTY.VALUE
            from RESOURCE_PROPERTY
            right join %s on (RESOURCE_PROPERTY.RESOURCE_ID = %s) 
            where %s = %%s
            """ % (joinColumn, joinTable, joinColumn, parentIDColumn),
            [parentID]
        )
        
        createdStores = {}
        for object_resource_id, resource_id, name, view_uid, value in rows:
            if resource_id:
                if resource_id not in createdStores:
                    store = cls.__new__(cls)
                    super(PropertyStore, store).__init__(defaultuser)
                    store._txn = txn
                    store._resourceID = resource_id
                    store._cached = {}
                    createdStores[resource_id] = store
                createdStores[resource_id]._cached[(name, view_uid)] = value
            else:
                store = cls.__new__(cls)
                super(PropertyStore, store).__init__(defaultuser)
                store._txn = txn
                store._resourceID = object_resource_id
                store._cached = {}
                createdStores[object_resource_id] = store
                
        returnValue(createdStores)


    def _getitem_uid(self, key, uid):
        validKey(key)

        try:
            value = self._cached[(key.toString(), uid)]
        except KeyError:
            raise KeyError(key)

        return WebDAVDocument.fromString(value).root_element


    def _setitem_uid(self, key, value, uid):
        validKey(key)

        key_str = key.toString()
        value_str = value.toxml()

        if (key_str, uid) in self._cached:
            self._txn.execSQL(
                """
                update RESOURCE_PROPERTY
                set VALUE = %s
                where RESOURCE_ID = %s and NAME = %s and VIEWER_UID = %s
                """,
                [value_str, self._resourceID, key_str, uid]
            )
        else:        
            self._txn.execSQL(
                """
                insert into RESOURCE_PROPERTY
                (RESOURCE_ID, NAME, VALUE, VIEWER_UID)
                values (%s, %s, %s, %s)
                """,
                [self._resourceID, key_str, value_str, uid]
            )
        self._cached[(key_str, uid)] = value_str
        self.cacher.delete(str(self._resourceID))

    def _delitem_uid(self, key, uid):
        validKey(key)

        key_str = key.toString()
        del self._cached[(key_str, uid)]
        self._txn.execSQL(
            """
            delete from RESOURCE_PROPERTY
            where RESOURCE_ID = %s and NAME = %s and VIEWER_UID = %s
            """,
            [self._resourceID, key_str, uid],
            raiseOnZeroRowCount=lambda:KeyError(key)
        )
        self.cacher.delete(str(self._resourceID))
            

    def _keys_uid(self, uid):

        for cachedKey, cachedUID in self._cached.keys():
            if cachedUID == uid:
                yield PropertyName.fromString(cachedKey)
