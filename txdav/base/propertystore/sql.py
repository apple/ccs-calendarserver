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

from txdav.base.propertystore.base import AbstractPropertyStore, PropertyName,\
    validKey

from twext.web2.dav.davxml import WebDAVDocument

class PropertyStore(AbstractPropertyStore):

    def __init__(self, defaultuser, txn, resourceID):
        super(PropertyStore, self).__init__(defaultuser)
        self._txn = txn
        self._resourceID = resourceID


    def _getitem_uid(self, key, uid):
        validKey(key)
        rows = self._txn.execSQL(
            "select VALUE from RESOURCE_PROPERTY where "
            "RESOURCE_ID = %s and NAME = %s and VIEWER_UID = %s",
            [self._resourceID, key.toString(), uid]
        )
        if not rows:
            raise KeyError(key)
        return WebDAVDocument.fromString(rows[0][0]).root_element


    def _setitem_uid(self, key, value, uid):
        validKey(key)
        try:
            self._delitem_uid(key, uid)
        except KeyError:
            pass
        self._txn.execSQL(
            "insert into RESOURCE_PROPERTY "
            "(RESOURCE_ID, NAME, VALUE, VIEWER_UID) values (%s, %s, %s, %s)",
            [self._resourceID, key.toString(), value.toxml(), uid]
        )


    def _delitem_uid(self, key, uid):
        validKey(key)
        self._txn.execSQL(
            "delete from RESOURCE_PROPERTY where VIEWER_UID = %s"
            "and RESOURCE_ID = %s AND NAME = %s",
            [uid, self._resourceID, key.toString()],
            raiseOnZeroRowCount=lambda:KeyError(key)
        )
            

    def _keys_uid(self, uid):
        rows = self._txn.execSQL(
            "select NAME from RESOURCE_PROPERTY where "
            "VIEWER_UID = %s and RESOURCE_ID = %s",
            [uid, self._resourceID]
        )
        for row in rows:
            yield PropertyName.fromString(row[0])
