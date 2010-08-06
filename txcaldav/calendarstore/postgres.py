# -*- test-case-name: txcaldav.calendarstore.test.test_postgres.SQLStorageTests -*-
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
from twisted.python import hashlib

"""
PostgreSQL data store.
"""

__all__ = [
    "PostgresCalendarStore",
    "PostgresCalendarHome",
    "PostgresCalendar",
    "PostgresCalendarObject",
]

from inspect import getargspec
from zope.interface.declarations import implements

from twisted.python.modules import getModule
from twisted.application.service import Service
from twisted.internet.interfaces import ITransport
from twisted.internet.error import ConnectionLost
from twisted.python.failure import Failure

from twext.web2.dav.element.rfc2518 import ResourceType

from txdav.idav import IDataStore, AlreadyFinishedError

from txdav.common.icommondatastore import (
    ObjectResourceNameAlreadyExistsError, HomeChildNameAlreadyExistsError,
    NoSuchHomeChildError, NoSuchObjectResourceError)
from txcaldav.calendarstore.util import (validateCalendarComponent,
    dropboxIDFromCalendarObject)


from txcaldav.icalendarstore import (ICalendarTransaction, ICalendarHome,
    ICalendar, ICalendarObject, IAttachment)
from txdav.propertystore.base import AbstractPropertyStore, PropertyName
from txdav.propertystore.none import PropertyStore

from twext.web2.http_headers import MimeType
from twext.web2.dav.element.parser import WebDAVDocument


from twext.python.vcomponent import VComponent


v1_schema = getModule(__name__).filePath.sibling(
    "postgres_schema_v1.sql").getContent()


# these are in the schema, and should probably be discovered from there
# somehow.

_BIND_STATUS_ACCEPTED = 1
_BIND_STATUS_DECLINED = 2

_ATTACHMENTS_MODE_WRITE = 1

_BIND_MODE_OWN = 0



def _getarg(argname, argspec, args, kw):
    """
    Get an argument from some arguments.

    @param argname: The name of the argument to retrieve.

    @param argspec: The result of L{inspect.getargspec}.

    @param args: positional arguments passed to the function specified by
        argspec.

    @param kw: keyword arguments passed to the function specified by
        argspec.

    @return: The value of the argument named by 'argname'.
    """
    argnames = argspec[0]
    try:
        argpos = argnames.index(argname)
    except ValueError:
        argpos = None
    if argpos is not None:
        if len(args) > argpos:
            return args[argpos]
    if argname in kw:
        return kw[argname]
    else:
        raise TypeError("could not find key argument %r in %r/%r (%r)" %
            (argname, args, kw, argpos)
        )



def memoized(keyArgument, memoAttribute):
    """
    Decorator which memoizes the result of a method on that method's instance.

    @param keyArgument: The name of the 'key' argument.

    @type keyArgument: C{str}

    @param memoAttribute: The name of the attribute on the instance which
        should be used for memoizing the result of this method; the attribute
        itself must be a dictionary.

    @type memoAttribute: C{str}
    """
    def decorate(thunk):
        spec = getargspec(thunk)
        def outer(*a, **kw):
            self = a[0]
            memo = getattr(self, memoAttribute)
            key = _getarg(keyArgument, spec, a, kw)
            if key in memo:
                return memo[key]
            result = thunk(*a, **kw)
            if result is not None:
                memo[key] = result
            return result
        return outer
    return decorate



class PropertyStore(AbstractPropertyStore):

    def __init__(self, peruser, defaultuser, cursor, connection, resourceID):
        super(PropertyStore, self).__init__(peruser, defaultuser)
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
        self._calendarText = None


    def uid(self):
        return self.component().resourceUID()


    def organizer(self):
        return self.component().getOrganizer()


    def dropboxID(self):
        return dropboxIDFromCalendarObject(self)


    def name(self):
        return self._name


    def iCalendarText(self):
        if self._calendarText is None:
            c = self._calendar._cursor()
            c.execute("select ICALENDAR_TEXT from CALENDAR_OBJECT where "
                      "RESOURCE_ID = %s", [self._resourceID])
            text = c.fetchall()[0][0]
            self._calendarText = text
            return text
        else:
            return self._calendarText


    def component(self):
        return VComponent.fromString(self.iCalendarText())


    def componentType(self):
        return self.component().mainType()


    def properties(self):
        return PropertyStore(
            self.uid(),
            self.uid(),
            self._calendar._cursor(),
            self._calendar._home._txn._connection,
            self._resourceID
        )


    def setComponent(self, component):
        validateCalendarComponent(self, self._calendar, component)
        calendarText = str(component)
        self._calendar._cursor().execute(
            "update CALENDAR_OBJECT set ICALENDAR_TEXT = %s "
            "where RESOURCE_ID = %s", [calendarText, self._resourceID]
        )
        self._calendarText = calendarText
        self._calendar._home._txn.postCommit(self._calendar._notifier.notify)


    def _attachmentPath(self, name):
        return self._calendar._home._txn._store.attachmentsPath.child(
            "%s-%s-%s-%s.attachment" % (
                self._calendar._home.uid(), self._calendar.name(),
                self.name(), name
            )
        )


    def createAttachmentWithName(self, name, contentType):
        path = self._attachmentPath(name)
        c = self._calendar._cursor()
        attachment = PostgresAttachment(self, path)
        c.execute("""
            insert into ATTACHMENT (CALENDAR_OBJECT_RESOURCE_ID, CONTENT_TYPE,
            SIZE, MD5, PATH)
            values (%s, %s, %s, %s, %s)
            """,
            [
                self._resourceID, str(contentType), 0, "",
                attachment._pathValue()
            ]
        )
        return attachment.store(contentType)


    def attachments(self):
        c = self._calendar._cursor()
        c.execute("""
        select PATH from ATTACHMENT where CALENDAR_OBJECT_RESOURCE_ID = %s 
        """, [self._resourceID])
        rows = c.fetchall()
        for row in rows:
            demangledName = _pathToName(row[0])
            yield self.attachmentWithName(demangledName)


    def attachmentWithName(self, name):
        attachment = PostgresAttachment(self, self._attachmentPath(name))
        if attachment._populate():
            return attachment
        else:
            return None


    def removeAttachmentWithName(self, name):
        attachment = PostgresAttachment(self, self._attachmentPath(name))
        self._calendar._home._txn.postCommit(attachment._path.remove)
        c = self._calendar._cursor()
        c.execute("""
        delete from ATTACHMENT where CALENDAR_OBJECT_RESOURCE_ID = %s AND
        PATH = %s
        """, [self._resourceID, attachment._pathValue()])


    # IDataStoreResource
    def contentType(self):
        """
        The content type of Calendar objects is text/calendar.
        """
        return MimeType.fromString("text/calendar")


    def md5(self):
        return None


    def size(self):
        return 0


    def created(self):
        return None


    def modified(self):
        return None


def _pathToName(path):
    return path.rsplit(".", 1)[0].split("-", 3)[-1]

class PostgresAttachment(object):

    implements(IAttachment)

    def __init__(self, calendarObject, path):
        self._calendarObject = calendarObject
        self._path = path


    def _populate(self):
        """
        Execute necessary SQL queries to retrieve attributes.

        @return: C{True} if this attachment exists, C{False} otherwise.
        """
        c = self._calendarObject._calendar._cursor()
        c.execute(
            """
            select CONTENT_TYPE, MD5 from ATTACHMENT where PATH = %s
            """, [self._pathValue()])
        rows = c.fetchall()
        if not rows:
            return False
        self._contentType = MimeType.fromString(rows[0][0])
        self._md5 = rows[0][1]
        return True


    def store(self, contentType):
        return PostgresAttachmentStorageTransport(self, contentType)


    def retrieve(self, protocol):
        protocol.dataReceived(self._path.getContent())
        protocol.connectionLost(Failure(ConnectionLost()))


    def properties(self):
        pass # stub


    # IDataStoreResource
    def contentType(self):
        return self._contentType


    def md5(self):
        return self._md5


    def size(self):
        return 0


    def created(self):
        return None


    def modified(self):
        return None


    def name(self):
        return _pathToName(self._pathValue())


    def _pathValue(self):
        """
        Compute the value which should go into the 'path' column for this
        attachment.
        """
        root = self._calendarObject._calendar._home._txn._store.attachmentsPath
        return '/'.join(self._path.segmentsFrom(root))



class PostgresAttachmentStorageTransport(object):

    implements(ITransport)

    def __init__(self, attachment, contentType):
        self.attachment = attachment
        self.contentType = contentType
        self.buf = ''
        self.hash = hashlib.md5()

    def write(self, data):
        self.buf += data
        self.hash.update(data)

    def loseConnection(self):
        self.attachment._path.setContent(self.buf)
        pathValue = self.attachment._pathValue()
        c = self.attachment._calendarObject._calendar._home._txn._cursor
        contentTypeString = '%s/%s' % (self.contentType.mediaType,
                                       self.contentType.mediaSubtype)
        c.execute("update ATTACHMENT set CONTENT_TYPE = %s, MD5 = %s "
                  "WHERE PATH = %s",
                  [contentTypeString, self.hash.hexdigest(), pathValue])



class PostgresCalendar(object):

    implements(ICalendar)

    def __init__(self, home, name, resourceID, notifier):
        self._home = home
        self._name = name
        self._resourceID = resourceID
        self._objects = {}
        self._notifier = notifier


    def _cursor(self):
        return self._home._txn._cursor


    def notifierID(self, label="default"):
        return None


    def name(self):
        return self._name


    def rename(self, name):
        oldName = self._name
        c = self._cursor()
        c.execute(
            "update CALENDAR_BIND set CALENDAR_RESOURCE_NAME = %s "
            "where CALENDAR_RESOURCE_ID = %s AND "
            "CALENDAR_HOME_RESOURCE_ID = %s",
            [name, self._resourceID, self._home._resourceID]
        )
        self._name = name
        # update memos
        del self._home._calendars[oldName]
        self._home._calendars[name] = self


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


    @memoized('name', '_objects')
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
        c = self._cursor()
        c.execute(
            "select RESOURCE_NAME from CALENDAR_OBJECT where "
            " RESOURCE_NAME = %s AND CALENDAR_RESOURCE_ID = %s",
            [name, self._resourceID]
        )
        rows = c.fetchall()
        if rows:
            raise ObjectResourceNameAlreadyExistsError()

        calendarObject = PostgresCalendarObject(self, name, None)
        calendarObject.component = lambda : component

        validateCalendarComponent(calendarObject, self, component)

        componentText = str(component)
        c.execute(
            """
            insert into CALENDAR_OBJECT
            (CALENDAR_RESOURCE_ID, RESOURCE_NAME, ICALENDAR_TEXT,
             ICALENDAR_UID, ICALENDAR_TYPE, ATTACHMENTS_MODE)
             values
            (%s, %s, %s, %s, %s, %s)
            """,
            # should really be filling out more fields: ORGANIZER,
            # ORGANIZER_OBJECT, a correct ATTACHMENTS_MODE based on X-APPLE-
            # DROPBOX
            [self._resourceID, name, componentText, component.resourceUID(),
            component.resourceType(), _ATTACHMENTS_MODE_WRITE]
        )
        self._home._txn.postCommit(self._notifier.notify)


    def removeCalendarObjectWithName(self, name):
        c = self._cursor()
        c.execute("delete from CALENDAR_OBJECT where RESOURCE_NAME = %s and "
                  "CALENDAR_RESOURCE_ID = %s",
                  [name, self._resourceID])
        if c.rowcount == 0:
            raise NoSuchObjectResourceError()
        self._objects.pop(name, None)
        self._home._txn.postCommit(self._notifier.notify)


    def removeCalendarObjectWithUID(self, uid):
        c = self._cursor()
        c.execute(
            "select RESOURCE_NAME from CALENDAR_OBJECT where "
            "ICALENDAR_UID = %s AND CALENDAR_RESOURCE_ID = %s",
            [uid, self._resourceID]
        )
        rows = c.fetchall()
        if not rows:
            raise NoSuchObjectResourceError()
        name = rows[0][0]
        c.execute("delete from CALENDAR_OBJECT where ICALENDAR_UID = %s and "
                  "CALENDAR_RESOURCE_ID = %s",
                  [uid, self._resourceID])
        self._objects.pop(name, None)
        self._home._txn.postCommit(self._notifier.notify)


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
        ownerUID = self.ownerCalendarHome().uid()
        return PropertyStore(
            ownerUID,
            ownerUID,
            self._cursor(), self._home._txn._connection,
            self._resourceID
        )


    # IDataStoreResource
    def contentType(self):
        """
        The content type of Calendar objects is text/calendar.
        """
        return MimeType.fromString("text/calendar")


    def md5(self):
        return None


    def size(self):
        return 0


    def created(self):
        return None


    def modified(self):
        return None



class PostgresCalendarHome(object):

    implements(ICalendarHome)

    def __init__(self, transaction, ownerUID, resourceID, notifier):
        self._txn = transaction
        self._ownerUID = ownerUID
        self._resourceID = resourceID
        self._calendars = {}
        self._notifier = notifier


    def uid(self):
        """
        Retrieve the unique identifier for this calendar home.

        @return: a string.
        """
        return self._ownerUID


    def name(self):
        """
        Implement L{IDataStoreResource.name} to return the uid.
        """
        return self.uid()


    def calendars(self):
        """
        Retrieve calendars contained in this calendar home.

        @return: an iterable of L{ICalendar}s.
        """
        c = self._txn._cursor
        c.execute(
            "select CALENDAR_RESOURCE_NAME from CALENDAR_BIND where "
            "CALENDAR_HOME_RESOURCE_ID = %s "
            "AND BIND_STATUS != %s",
            [self._resourceID,
            _BIND_STATUS_DECLINED, ]
        )
        names = [row[0] for row in c.fetchall()]
        for name in names:
            yield self.calendarWithName(name)


    @memoized('name', '_calendars')
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
        childID = "%s/%s" % (self.uid(), name)
        notifier = self._notifier.clone(label="collection", id=childID)
        return PostgresCalendar(self, name, resourceID, notifier)


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
        c.execute(
            "select CALENDAR_RESOURCE_NAME from CALENDAR_BIND where "
            "CALENDAR_RESOURCE_NAME = %s AND "
            "CALENDAR_HOME_RESOURCE_ID = %s",
            [name, self._resourceID]
        )
        rows = c.fetchall()
        if rows:
            raise HomeChildNameAlreadyExistsError()
        c.execute("select nextval('RESOURCE_ID_SEQ')")
        resourceID = c.fetchall()[0][0]
        c.execute("insert into CALENDAR (SYNC_TOKEN, RESOURCE_ID) values "
                  "(%s, %s)",
                  ['uninitialized', resourceID])

        c.execute("""
            insert into CALENDAR_BIND (
                CALENDAR_HOME_RESOURCE_ID,
                CALENDAR_RESOURCE_ID, CALENDAR_RESOURCE_NAME, BIND_MODE,
                SEEN_BY_OWNER, SEEN_BY_SHAREE, BIND_STATUS) values (
            %s, %s, %s, %s, %s, %s, %s)
            """,
            [self._resourceID, resourceID, name, _BIND_MODE_OWN, True, True,
             _BIND_STATUS_ACCEPTED])

        calendarType = ResourceType.calendar #@UndefinedVariable
        self.calendarWithName(name).properties()[
            PropertyName.fromElement(ResourceType)] = calendarType
        self._txn.postCommit(self._notifier.notify)


    def removeCalendarWithName(self, name):
        c = self._txn._cursor
        c.execute(
            "delete from CALENDAR_BIND where CALENDAR_RESOURCE_NAME = %s and "
            "CALENDAR_HOME_RESOURCE_ID = %s",
            [name, self._resourceID]
        )
        self._calendars.pop(name, None)
        if c.rowcount == 0:
            raise NoSuchHomeChildError()
        # FIXME: the schema should probably cascade the calendar delete when
        # the last bind is deleted.
        self._txn.postCommit(self._notifier.notify)


    def properties(self):
        return PropertyStore(
            self.uid(),
            self.uid(),
            self._txn._cursor,
            self._txn._connection,
            self._resourceID
        )


    # IDataStoreResource
    def contentType(self):
        """
        The content type of Calendar objects is text/calendar.
        """
        return MimeType.fromString("text/calendar")


    def md5(self):
        return None


    def size(self):
        return 0


    def created(self):
        return None


    def modified(self):
        return None


    def notifierID(self, label="default"):
        return None



class PostgresCalendarTransaction(object):
    """
    Transaction implementation for postgres database.
    """
    implements(ICalendarTransaction)

    def __init__(self, store, connection, notifierFactory):
        self._store = store
        self._connection = connection
        self._cursor = connection.cursor()
        self._completed = False
        self._homes = {}
        self._postCommitOperations = []
        self._notifierFactory = notifierFactory


    def __del__(self):
        if not self._completed:
            self._connection.rollback()
            self._connection.close()


    @memoized('uid', '_homes')
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
        notifier = self._notifierFactory.newNotifier(id=uid)
        return PostgresCalendarHome(self, uid, resid, notifier)


    def notificationsWithUID(self, uid):
        """
        Implement notificationsWithUID.
        """
        raise NotImplementedError("no notifications collection yet")


    def abort(self):
        if not self._completed:
            self._completed = True
            self._connection.rollback()
            self._connection.close()
        else:
            raise AlreadyFinishedError()


    def commit(self):
        if not self._completed:
            self._completed = True
            self._connection.commit()
            self._connection.close()
            for operation in self._postCommitOperations:
                operation()
        else:
            raise AlreadyFinishedError()


    def postCommit(self, operation):
        """
        Run things after 'commit.'
        """
        self._postCommitOperations.append(operation)
        # FIXME: implement.



class PostgresStore(Service, object):

    implements(IDataStore)

    def __init__(self, connectionFactory, notifierFactory, attachmentsPath):
        self.connectionFactory = connectionFactory
        self.notifierFactory = notifierFactory
        self.attachmentsPath = attachmentsPath


    def newTransaction(self):
        return PostgresCalendarTransaction(
            self,
            self.connectionFactory(),
            self.notifierFactory
        )

