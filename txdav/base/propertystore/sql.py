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
from twisted.internet.defer import inlineCallbacks, returnValue

"""
PostgreSQL data store.
"""

__all__ = [
    "PropertyStore",
]

from txdav.base.propertystore.base import AbstractPropertyStore, PropertyName,\
    validKey

from twext.web2.dav.davxml import WebDAVDocument

class PropertyStore(AbstractPropertyStore):

    def __init__(self, *a, **kw):
        raise NotImplementedError(
            "do not construct directly, call PropertyStore.load()"
        )


    @classmethod
    @inlineCallbacks
    def load(cls, defaultuser, txn, resourceID):
        self = cls.__new__(cls)
        super(PropertyStore, self).__init__(defaultuser)
        self._txn = txn
        self._resourceID = resourceID
        self._cached = {}
        rows = yield self._txn.execSQL(
            """
            select NAME, VIEWER_UID, VALUE from RESOURCE_PROPERTY
            where RESOURCE_ID = %s
            """,
            [self._resourceID]
        )
        for name, uid, value in rows:
            self._cached[(name, uid)] = value
        returnValue(self)


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
            

    def _keys_uid(self, uid):

        for cachedKey, cachedUID in self._cached.keys():
            if cachedUID == uid:
                yield PropertyName.fromString(cachedKey)
