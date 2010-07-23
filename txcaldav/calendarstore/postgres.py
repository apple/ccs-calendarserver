# -*- test-case-name: txcaldav.calendarstore.test.test_postgres -*-
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
    "CalendarStore",
    "CalendarHome",
    "Calendar",
    "CalendarObject",
]

from twisted.python.modules import getModule
from twisted.application.service import Service
from txdav.idav import IDataStore
from zope.interface.declarations import implements
from txcaldav.icalendarstore import ICalendarTransaction, ICalendarHome, \
    ICalendar, ICalendarObject
from txdav.propertystore.base import AbstractPropertyStore, PropertyName
from twext.web2.dav.element.parser import WebDAVDocument
from txdav.common.icommondatastore import ObjectResourceNameAlreadyExistsError
from txdav.propertystore.none import PropertyStore

from twext.python.vcomponent import VComponent


v1_schema = getModule(__name__).filePath.sibling(
    "postgres_schema_v1.sql").getContent()


# these are in the schema, and should probably be discovered from there
# somehow.

_BIND_STATUS_ACCEPTED = 1
_BIND_STATUS_DECLINED = 2

_ATTACHMENTS_MODE_WRITE = 1

_BIND_MODE_OWN = 0


class PropertyStore(AbstractPropertyStore):
    """
    
    """

    def __init__(self, cursor, connection, resourceID):
        self._cursor = cursor
        self._connection = connection
        self._resourceID = resourceID

    def _getitem_uid(self, key, uid):
        self._cursor.execute(
            "select VALUE from RESOURCE_PROPERTY where "
            "NAME = %s and VIEWER_UID = %s",
            [key.toString(), uid])
        rows = self._cursor.fetchall()
        if not rows:
            raise KeyError(key)
        return WebDAVDocument.fromString(rows[0][0]).root_element


    def _setitem_uid(self, key, value, uid):
        self._delitem_uid(key, uid)
        self._cursor.execute(
            "insert into RESOURCE_PROPERTY "
            "(RESOURCE_ID, NAME, VALUE, VIEWER_UID) values (%s, %s, %s, %s)",
            [self._resourceID, key.toString(), value.toxml(), uid])


    def _delitem_uid(self, key, uid):
        self._cursor.execute(
            "delete from RESOURCE_PROPERTY where VIEWER_UID = %s"
            "and RESOURCE_ID = %s AND NAME = %s",
            [uid, self._resourceID, key.toString()])


    def _keys_uid(self, uid):
        self._cursor.execute(
            "select NAME from RESOURCE_PROPERTY where "
            "VIEWER_UID = %s and RESOURCE_ID = %s",
            [uid, self._resourceID]
        )
        for row in self._cursor.fetchall():
            yield PropertyName.fromString(row[0])



class PostgresCalendarObject(object):
    implements(ICalendarObject)

    def __init__(self, calendar, name, resid):
        self._calendar = calendar
        self._name = name
        self._resourceID = resid


    def uid(self):
        return self.component().resourceUID()
    
    
    def dropboxID(self):
        return self.uid() + ".dropbox"


    def name(self):
        return self._name


    def iCalendarText(self):
        c = self._calendar._cursor()
        c.execute("select ICALENDAR_TEXT from CALENDAR_OBJECT where "
                  "RESOURCE_ID = %s", [self._resourceID])
        return c.fetchall()[0][0]


    def component(self):
        return VComponent.fromString(self.iCalendarText())


    def componentType(self):
        return self.component().mainType()


    def properties(self):
        return PropertyStore(self._calendar._cursor(),
            self._calendar._home._txn._connection,
            self._resourceID)


    def setComponent(self, component):
        self._calendar._cursor().execute(
            "update CALENDAR_OBJECT set ICALENDAR_TEXT = %s "
            "where RESOURCE_ID = %s", [str(component), self._resourceID]
        )


    def createAttachmentWithName(self, name, contentType):
        pass


    def attachments(self):
        return []


    def attachmentWithName(self, name):
        return None


    def removeAttachmentWithName(self, name):
        pass



class PostgresCalendar(object):
    """
    
    """

    implements(ICalendar)


    def __init__(self, home, name, resourceID):
        self._home = home
        self._name = name
        self._resourceID = resourceID


    def _cursor(self):
        return self._home._txn._cursor


    def name(self):
        return self._name

    def rename(self, name):
        raise NotImplementedError()

    def ownerCalendarHome(self):
        return self._home


    def calendarObjects(self):
        c = self._cursor()
        c.execute(
            "select RESOURCE_NAME from "
            "CALENDAR_OBJECT where "
            "CALENDAR_RESOURCE_ID = %s",
            [self._resourceID])
        for row in c.fetchall():
            name = row[0]
            yield self.calendarObjectWithName(name)


    def calendarObjectWithName(self, name):
        c = self._cursor()
        c.execute("select RESOURCE_ID from CALENDAR_OBJECT where "
                  "RESOURCE_NAME = %s and CALENDAR_RESOURCE_ID = %s",
                  [name, self._resourceID])
        rows = c.fetchall()
        if not rows:
            return None
        resid = rows[0][0]
        return PostgresCalendarObject(self, name, resid)


    def calendarObjectWithUID(self, uid):
        c = self._cursor()
        c.execute("select RESOURCE_NAME from CALENDAR_OBJECT where "
                  "ICALENDAR_UID = %s",
                  [uid])
        rows = c.fetchall()
        if not rows:
            return None
        name = rows[0][0]
        return self.calendarObjectWithName(name)


    def createCalendarObjectWithName(self, name, component):
        str(component)
        c = self._cursor()
        c.execute(
"""
insert into CALENDAR_OBJECT
(CALENDAR_RESOURCE_ID, RESOURCE_NAME, ICALENDAR_TEXT, ICALENDAR_UID,
 ICALENDAR_TYPE, ATTACHMENTS_MODE)
 values
(%s, %s, %s, %s, %s, %s)
"""
,
# should really be filling out more fields: ORGANIZER, ORGANIZER_OBJECT,
# a correct ATTACHMENTS_MODE based on X-APPLE-DROPBOX
[self._resourceID, name, str(component), component.resourceUID(),
component.resourceType(), _ATTACHMENTS_MODE_WRITE])


    def removeCalendarObjectWithName(self, name):
        c = self._cursor()
        c.execute("delete from CALENDAR_OBJECT where RESOURCE_NAME = %s and ",
                  "CALENDAR_RESOURCE_ID = %s",
                  [name, self._resourceID])


    def removeCalendarObjectWithUID(self, uid):
        c = self._cursor()
        c.execute("delete from CALENDAR_OBJECT where ICALENDAR_UID = %s and ",
                  "CALENDAR_RESOURCE_ID = %s",
                  [uid, self._resourceID])


    def syncToken(self):
        c = self._cursor()
        c.execute("select SYNC_TOKEN from CALENDAR where RESOURCE_ID = %s",
                  [self._resourceID])
        return c.fetchall()[0][0]


    def calendarObjectsInTimeRange(self, start, end, timeZone):
        raise NotImplementedError()


    def calendarObjectsSinceToken(self, token):
        raise NotImplementedError()


    def properties(self):
        return PropertyStore(self._cursor(), self._home._txn._connection,
                             self._resourceID)



class PostgresCalendarHome(object):
    implements(ICalendarHome)
    def __init__(self, transaction, ownerUID, resourceID):
        self._txn = transaction
        self._ownerUID = ownerUID
        self._resourceID = resourceID


    def uid(self):
        """
        Retrieve the unique identifier for this calendar home.

        @return: a string.
        """
        return self._ownerUID


    def calendars(self):
        """
        Retrieve calendars contained in this calendar home.

        @return: an iterable of L{ICalendar}s.
        """
        c = self._txn._cursor
        c.execute(
            "select CALENDAR_RESOURCE_NAME from CALENDAR_BIND where "
            "CALENDAR_HOME_RESOURCE_ID = %s "
            "AND STATUS != %s",
            [self._resourceID,
            _BIND_STATUS_DECLINED, ]
        )
        names = c.fetchall()
        for name in names:
            yield self.calendarWithName(name)


    def calendarWithName(self, name):
        """
        Retrieve the calendar with the given C{name} contained in this
        calendar home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such calendar
            exists.
        """
        c = self._txn._cursor
        c.execute("select CALENDAR_RESOURCE_ID from CALENDAR_BIND where "
                  "CALENDAR_RESOURCE_NAME = %s",
                  [name])
        data = c.fetchall()
        if not data:
            return None
        resourceID = data[0][0]
        return PostgresCalendar(self, name, resourceID)


    def calendarObjectWithDropboxID(self, dropboxID):
        """
        Implement lookup with brute-force scanning.
        """
        for calendar in self.calendars():
            for calendarObject in calendar.calendarObjects():
                if dropboxID == calendarObject.dropboxID():
                    return calendarObject


    def createCalendarWithName(self, name):
        c = self._txn._cursor
        c.execute("select nextval('RESOURCE_ID_SEQ')")
        resourceID = c.fetchall()[0][0]
        c.execute("insert into CALENDAR (SYNC_TOKEN, RESOURCE_ID) values "
                  "(%s, %s)",
                  ['uninitialized', resourceID])

        c.execute("""
        insert into CALENDAR_BIND (
            CALENDAR_HOME_RESOURCE_ID,
            CALENDAR_RESOURCE_ID, CALENDAR_RESOURCE_NAME, CALENDAR_MODE,
            SEEN_BY_OWNER, SEEN_BY_SHAREE, STATUS) values (
        %s, %s, %s, %s, %s, %s, %s)
        """,
        [self._resourceID, resourceID, name, _BIND_MODE_OWN, True, True,
        _BIND_STATUS_ACCEPTED])


    def removeCalendarWithName(self, name):
        c = self._txn._cursor
        c.execute(
            "delete from CALENDAR_BIND where CALENDAR_RESOURCE_NAME = %s and "
            "CALENDAR_HOME_RESOURCE_ID = %s",
            [name, self._resourceID])
        # FIXME: the schema should probably cascade the delete when the last
        # bind is deleted.


    def properties(self):
        return PropertyStore(self._txn._cursor, self._txn._connection,
                             self._resourceID)



class PostgresCalendarTransaction(object):
    """
    Transaction implementation for postgres database.
    """
    implements(ICalendarTransaction)

    def __init__(self, connection):
        self._connection = connection
        self._cursor = connection.cursor()


    def calendarHomeWithUID(self, uid, create=False):
        self._cursor.execute(
            "select RESOURCE_ID from CALENDAR_HOME where OWNER_UID = %s",
            [uid]
        )
        data = self._cursor.fetchall()
        if not data:
            if not create:
                return None
            self._cursor.execute(
                "insert into CALENDAR_HOME (OWNER_UID) values (%s)",
                [uid]
            )
            return self.calendarHomeWithUID(uid)
        resid = data[0][0]
        return PostgresCalendarHome(self, uid, resid)


    def abort(self):
        self._connection.rollback()
        self._connection.close()


    def commit(self):
        self._connection.commit()
        self._connection.close()


class PostgresStore(Service, object):

    implements(IDataStore)

    def __init__(self, connectionFactory):
        self.connectionFactory = connectionFactory


    def newTransaction(self):
        return PostgresCalendarTransaction(self.connectionFactory())

