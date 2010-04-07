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
Implements notification functionality.
"""

__all__ = [
    "NotificationResource",
    "NotificationCollectionResource",
]

from twext.python.log import Logger, LoggingMixIn
from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.dav.resource import DAVResource
from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twistedcaldav.sql import AbstractSQLDatabase, db_prefix
import os
import types

log = Logger()

class NotificationResource(DAVResource):
    """
    An xml resource in a Notification collection.
    """
    def __init__(self, parent):
        self._parent = parent
        DAVResource.__init__(self)

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

class NotificationCollectionResource(DAVResource):
    
    def notificationsDB(self):
        
        if not hasattr(self, "_notificationsDB"):
            self._notificationsDB = NotificationsDatabase(self)
        return self._notificationsDB

    def isCollection(self):
        return True

    def resourceType(self, request):
        return succeed(davxml.ResourceType.notification)

    @inlineCallbacks
    def addNotification(self, request, uid, xmltype, xmldata):
        
        # Write data to file
        rname = uid + ".xml"
        yield self._writeNotification(request, uid, rname, xmltype, xmldata)

        # Update database
        self.notificationsDB().addOrUpdateRecord(NotificationRecord(uid, rname, xmltype.name))

    def _writeNotification(self, request, uid, rname, xmltype, xmldata):
        raise NotImplementedError

    def getNotifictionMessages(self, request, componentType=None, returnLatestVersion=True):
        return succeed([])

    def getNotifictionMessageByUID(self, request, uid):
        return succeed(self.notificationsDB().recordForUID(uid))

    @inlineCallbacks
    def deleteNotifictionMessageByUID(self, request, uid):
        
        # See if it exists and delete the resource
        record = self.notificationsDB().recordForUID(uid)
        if record:
            yield self._deleteNotification(request, record.name)
            self.notificationsDB().removeRecordForUID(record.uid)

    def deleteNotifictionMessageByName(self, request, rname):

        # See if it exists and delete the resource
        record = self.notificationsDB().recordForName(rname)
        if record:
            self._deleteNotification(request, record.name)
            self.notificationsDB().removeRecordForUID(record.uid)
        
        return succeed(None)

    def removedNotifictionMessage(self, request, rname):
        self.notificationsDB().removeRecordForName(rname)
        return succeed(None)
        
class NotificationRecord(object):
    
    def __init__(self, uid, name, xmltype):
        self.uid = uid
        self.name = name
        self.xmltype = xmltype

class NotificationsDatabase(AbstractSQLDatabase, LoggingMixIn):
    
    db_basename = db_prefix + "notifications"
    schema_version = "1"
    db_type = "notifications"

    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource for
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
    
    def removeRecordForUID(self, uid):

        self._db_execute("delete from NOTIFICATIONS where UID = :1", uid)
    
    def removeRecordForName(self, rname):

        self._db_execute("delete from NOTIFICATIONS where NAME = :1", rname)
    
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

    def _db_upgrade_data_tables(self, q, old_version):
        """
        Upgrade the data from an older version of the DB.
        """

        # Nothing to do as we have not changed the schema
        pass

    def _makeRecord(self, row):
        
        return NotificationRecord(*[str(item) if type(item) == types.UnicodeType else item for item in row])

