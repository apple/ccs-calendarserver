##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
Implements notification functionality.
"""

__all__ = [
    "NotificationResource",
    "NotificationCollectionResource",
]

from twext.python.log import Logger
from twext.web2 import responsecode
from txdav.xml import element as davxml

from twisted.internet.defer import succeed, inlineCallbacks, returnValue,\
    maybeDeferred

from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn, CalDAVResource
from twistedcaldav.sql import AbstractSQLDatabase, db_prefix

from txdav.common.icommondatastore import SyncTokenValidException

import os
import types

log = Logger()

class NotificationResource(CalDAVResource):
    """
    An xml resource in a Notification collection.
    """
    def __init__(self, parent):
        self._parent = parent
        CalDAVResource.__init__(self)

    def principalCollections(self):
        return self._parent.principalCollections()

    def isCollection(self):
        return False

    def resourceName(self):
        raise NotImplementedError
        
    def http_PUT(self, request):
        return responsecode.FORBIDDEN

    @inlineCallbacks
    def http_DELETE(self, request):
        
        response = (yield super(NotificationResource, self).http_DELETE(request))
        if response == responsecode.NO_CONTENT:
            yield self._parent.removedNotifictionMessage(request, self.resourceName())
        returnValue(response)
    
class NotificationCollectionResource(ReadOnlyNoCopyResourceMixIn, CalDAVResource):

    def notificationsDB(self):
        
        if not hasattr(self, "_notificationsDB"):
            self._notificationsDB = NotificationsDatabase(self)
        return self._notificationsDB

    def isCollection(self):
        return True

    def resourceType(self):
        return davxml.ResourceType.notification

    @inlineCallbacks
    def addNotification(self, request, uid, xmltype, xmldata):
        
        # Write data to file
        rname = uid + ".xml"
        yield self._writeNotification(request, uid, rname, xmltype, xmldata)

        # Update database
        self.notificationsDB().addOrUpdateRecord(NotificationRecord(uid, rname, xmltype.name))


    def getNotifictionMessages(self, request, componentType=None, returnLatestVersion=True):
        return succeed([])


    def getNotifictionMessageByUID(self, request, uid):
        return maybeDeferred(self.notificationsDB().recordForUID, uid)


    @inlineCallbacks
    def deleteNotifictionMessageByUID(self, request, uid):
        
        # See if it exists and delete the resource
        record = yield self.notificationsDB().recordForUID(uid)
        if record:
            yield self.deleteNotification(request, record)


    @inlineCallbacks
    def deleteNotifictionMessageByName(self, request, rname):

        # See if it exists and delete the resource
        record = yield self.notificationsDB().recordForName(rname)
        if record:
            yield self.deleteNotification(request, record)
        
        returnValue(None)


    @inlineCallbacks
    def deleteNotification(self, request, record):
        yield self._deleteNotification(request, record.name)
        yield self.notificationsDB().removeRecordForUID(record.uid)


    def removedNotifictionMessage(self, request, rname):
        return maybeDeferred(self.notificationsDB().removeRecordForName, rname)


class NotificationRecord(object):
    
    def __init__(self, uid, name, xmltype):
        self.uid = uid
        self.name = name
        self.xmltype = xmltype

class NotificationsDatabase(AbstractSQLDatabase):
    log = Logger()

    db_basename = db_prefix + "notifications"
    schema_version = "1"
    db_type = "notifications"

    def __init__(self, resource):
        """
        @param resource: the L{CalDAVResource} resource for
            the notifications collection.)
        """
        self.resource = resource
        db_filename = os.path.join(self.resource.fp.path, NotificationsDatabase.db_basename)
        super(NotificationsDatabase, self).__init__(db_filename, True, autocommit=True)

    def allRecords(self):
        
        records = self._db_execute("select * from NOTIFICATIONS")
        return [self._makeRecord(row) for row in (records if records is not None else ())]
    
    def recordForUID(self, uid):
        
        row = self._db_execute("select * from NOTIFICATIONS where UID = :1", uid)
        return self._makeRecord(row[0]) if row else None
    
    def addOrUpdateRecord(self, record):

        self._db_execute("""insert or replace into NOTIFICATIONS (UID, NAME, TYPE)
            values (:1, :2, :3)
            """, record.uid, record.name, record.xmltype,
        )
            
        self._db_execute(
            """
            insert or replace into REVISIONS (NAME, REVISION, DELETED)
            values (:1, :2, :3)
            """, record.name, self.bumpRevision(fast=True), 'N',
        )
    
    def removeRecordForUID(self, uid):

        record = self.recordForUID(uid)
        self.removeRecordForName(record.name)
    
    def removeRecordForName(self, rname):

        self._db_execute("delete from NOTIFICATIONS where NAME = :1", rname)
        self._db_execute(
            """
            update REVISIONS SET REVISION = :1, DELETED = :2
            where NAME = :3
            """, self.bumpRevision(fast=True), 'Y', rname
        )
    
    def whatchanged(self, revision):

        results = [(name.encode("utf-8"), deleted) for name, deleted in self._db_execute("select NAME, DELETED from REVISIONS where REVISION > :1", revision)]
        results.sort(key=lambda x:x[1])
        
        changed = []
        deleted = []
        for name, wasdeleted in results:
            if name:
                if wasdeleted == 'Y':
                    if revision:
                        deleted.append(name)
                else:
                    changed.append(name)
            else:
                raise SyncTokenValidException
        
        return changed, deleted,

    def lastRevision(self):
        return self._db_value_for_sql(
            "select REVISION from REVISION_SEQUENCE"
        )

    def bumpRevision(self, fast=False):
        self._db_execute(
            """
            update REVISION_SEQUENCE set REVISION = REVISION + 1
            """,
        )
        self._db_commit()
        return self._db_value_for_sql(
            """
            select REVISION from REVISION_SEQUENCE
            """,
        )

    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return NotificationsDatabase.schema_version

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return NotificationsDatabase.db_type

    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """
        #
        # NOTIFICATIONS table is the primary table
        #   UID: UID for this notification
        #   NAME: child resource name
        #   TYPE: type of notification
        #
        q.execute(
            """
            create table NOTIFICATIONS (
                UID            text unique,
                NAME           text unique,
                TYPE           text
            )
            """
        )

        q.execute(
            """
            create index UID on NOTIFICATIONS (UID)
            """
        )

        #
        # REVISIONS table tracks changes
        #   NAME: Last URI component (eg. <uid>.ics, RESOURCE primary key)
        #   REVISION: revision number
        #   WASDELETED: Y if revision deleted, N if added or changed
        #
        q.execute(
            """
            create table REVISION_SEQUENCE (
                REVISION        integer
            )
            """
        )
        q.execute(
            """
            insert into REVISION_SEQUENCE (REVISION) values (0)
            """
        )
        q.execute(
            """
            create table REVISIONS (
                NAME            text unique,
                REVISION        integer,
                DELETED         text(1)
            )
            """
        )
        q.execute(
            """
            create index REVISION on REVISIONS (REVISION)
            """
        )

    def _db_upgrade_data_tables(self, q, old_version):
        """
        Upgrade the data from an older version of the DB.
        """

        # Nothing to do as we have not changed the schema
        pass

    def _makeRecord(self, row):
        
        return NotificationRecord(*[str(item) if type(item) == types.UnicodeType else item for item in row])

