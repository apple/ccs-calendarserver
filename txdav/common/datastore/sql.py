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
SQL data store.
"""

__all__ = [
    "CommonDataStore",
    "CommonStoreTransaction",
    "CommonHome",
]

from twext.python.log import Logger, LoggingMixIn
from twext.web2.dav.element.rfc2518 import ResourceType
from twext.web2.http_headers import MimeType

from twisted.application.service import Service
from twisted.python import hashlib
from twisted.python.modules import getModule
from twisted.python.util import FancyEqMixin

from twistedcaldav.customxml import NotificationType

from txdav.common.datastore.sql_legacy import PostgresLegacyNotificationsEmulator
from txdav.caldav.icalendarstore import ICalendarTransaction

from txdav.carddav.iaddressbookstore import IAddressBookTransaction

from txdav.common.datastore.sql_tables import CALENDAR_HOME_TABLE,\
    ADDRESSBOOK_HOME_TABLE, NOTIFICATION_HOME_TABLE, _BIND_MODE_OWN,\
    _BIND_STATUS_ACCEPTED
from txdav.common.icommondatastore import HomeChildNameNotAllowedError,\
    HomeChildNameAlreadyExistsError, NoSuchHomeChildError,\
    ObjectResourceNameNotAllowedError, ObjectResourceNameAlreadyExistsError,\
    NoSuchObjectResourceError
from txdav.common.inotifications import INotificationCollection,\
    INotificationObject
from txdav.base.datastore.sql import memoized
from txdav.base.datastore.util import cached
from txdav.idav import IDataStore, AlreadyFinishedError
from txdav.base.propertystore.base import PropertyName
from txdav.base.propertystore.sql import PropertyStore

from zope.interface.declarations import implements, directlyProvides

v1_schema = getModule(__name__).filePath.sibling(
    "sql_schema_v1.sql").getContent()

log = Logger()

ECALENDARTYPE = 0
EADDRESSBOOKTYPE = 1

class CommonDataStore(Service, object):

    implements(IDataStore)

    def __init__(self, connectionFactory, notifierFactory, attachmentsPath,
                 enableCalendars=True, enableAddressBooks=True):
        assert enableCalendars or enableAddressBooks

        self.connectionFactory = connectionFactory
        self.notifierFactory = notifierFactory
        self.attachmentsPath = attachmentsPath
        self.enableCalendars = enableCalendars
        self.enableAddressBooks = enableAddressBooks


    def newTransaction(self, label="unlabeled"):
        return CommonStoreTransaction(
            self,
            self.connectionFactory(),
            self.enableCalendars,
            self.enableAddressBooks, 
            self.notifierFactory,
            label
        )

class CommonStoreTransaction(object):
    """
    Transaction implementation for SQL database.
    """

    _homeClass = {}

    def __init__(self, store, connection, enableCalendars, enableAddressBooks, notifierFactory, label):

        self._store = store
        self._connection = connection
        self._cursor = connection.cursor()
        self._completed = False
        self._calendarHomes = {}
        self._addressbookHomes = {}
        self._notificationHomes = {}
        self._postCommitOperations = []
        self._notifierFactory = notifierFactory
        self._label = label

        extraInterfaces = []
        if enableCalendars:
            extraInterfaces.append(ICalendarTransaction)
        if enableAddressBooks:
            extraInterfaces.append(IAddressBookTransaction)
        directlyProvides(self, *extraInterfaces)

        from txdav.caldav.datastore.sql import CalendarHome
        from txdav.carddav.datastore.sql import AddressBookHome
        CommonStoreTransaction._homeClass[ECALENDARTYPE] = CalendarHome
        CommonStoreTransaction._homeClass[EADDRESSBOOKTYPE] = AddressBookHome

    def store(self):
        return self._store


    def __repr__(self):
        return 'PG-TXN<%s>' % (self._label,)


    def execSQL(self, sql, args=[], raiseOnZeroRowCount=None):
        # print 'EXECUTE %s: %s' % (self._label, sql)
        self._cursor.execute(sql, args)
        if raiseOnZeroRowCount is not None and self._cursor.rowcount == 0:
            raise raiseOnZeroRowCount()
        if self._cursor.description:
            return self._cursor.fetchall()
        else:
            return None


    def __del__(self):
        if not self._completed:
            self._connection.rollback()
            self._connection.close()


    @memoized('uid', '_calendarHomes')
    def calendarHomeWithUID(self, uid, create=False):
        return self.homeWithUID(ECALENDARTYPE, uid, create=create)

    @memoized('uid', '_addressbookHomes')
    def addressbookHomeWithUID(self, uid, create=False):
        return self.homeWithUID(EADDRESSBOOKTYPE, uid, create=create)

    def homeWithUID(self, storeType, uid, create=False):
        
        if storeType == ECALENDARTYPE:
            homeTable = CALENDAR_HOME_TABLE
        elif storeType == EADDRESSBOOKTYPE:
            homeTable = ADDRESSBOOK_HOME_TABLE

        data = self.execSQL(
            "select %(column_RESOURCE_ID)s from %(name)s where %(column_OWNER_UID)s = %%s" % homeTable,
            [uid]
        )
        if not data:
            if not create:
                return None
            
            # Need to lock to prevent race condition
            # FIXME: this is an entire table lock - ideally we want a row lock
            # but the row does not exist yet. However, the "exclusive" mode does
            # allow concurrent reads so the only thing we block is other attempts
            # to provision a home, which is not too bad
            self.execSQL(
                "lock %(name)s in exclusive mode" % homeTable,
            )
            
            # Now test again
            data = self.execSQL(
                "select %(column_RESOURCE_ID)s from %(name)s where %(column_OWNER_UID)s = %%s" % homeTable,
                [uid]
            )

            if not data:
                self.execSQL(
                    "insert into %(name)s (%(column_OWNER_UID)s) values (%%s)" % homeTable,
                    [uid]
                )
                home = self.homeWithUID(storeType, uid)
                home.createdHome()
                return home
        resid = data[0][0]

        if self._notifierFactory:
            notifier = self._notifierFactory.newNotifier(id=uid)
        else:
            notifier = None

        return self._homeClass[storeType](self, uid, resid, notifier)


    @memoized('uid', '_notificationHomes')
    def notificationsWithUID(self, uid):
        """
        Implement notificationsWithUID.
        """
        rows = self.execSQL(
            """
            select %(column_RESOURCE_ID)s from %(name)s where
            %(column_OWNER_UID)s = %%s
            """ % NOTIFICATION_HOME_TABLE, [uid]
        )
        if rows:
            resourceID = rows[0][0]
        else:
            resourceID = str(self.execSQL(
                "insert into %(name)s (%(column_OWNER_UID)s) values (%%s) returning %(column_RESOURCE_ID)s" % NOTIFICATION_HOME_TABLE,
                [uid]
            )[0][0])
        return NotificationCollection(self, uid, resourceID)


    def abort(self):
        if not self._completed:
            # print 'ABORTING', self._label
            self._completed = True
            self._connection.rollback()
            self._connection.close()
        else:
            raise AlreadyFinishedError()


    def commit(self):
        if not self._completed:
            # print 'COMPLETING', self._label
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

class CommonHome(LoggingMixIn):

    _childClass = None
    _childTable = None
    _bindTable = None

    def __init__(self, transaction, ownerUID, resourceID, notifier):
        self._txn = transaction
        self._ownerUID = ownerUID
        self._resourceID = resourceID
        self._shares = None
        self._children = {}
        self._notifier = notifier


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)

    def uid(self):
        """
        Retrieve the unique identifier for this home.

        @return: a string.
        """
        return self._ownerUID


    def transaction(self):
        return self._txn


    def retrieveOldShares(self):
        return self._shares


    def name(self):
        """
        Implement L{IDataStoreResource.name} to return the uid.
        """
        return self.uid()


    def children(self):
        """
        Retrieve children contained in this home.
        """
        names = self.listChildren()
        for name in names:
            yield self.childWithName(name)


    def listChildren(self):
        """
        Retrieve the names of the children in this home.

        @return: an iterable of C{str}s.
        """
        # FIXME: not specified on the interface or exercised by the tests, but
        # required by clients of the implementation!
        rows = self._txn.execSQL(
            "select %(column_RESOURCE_NAME)s from %(name)s where "
            "%(column_HOME_RESOURCE_ID)s = %%s "
            "and %(column_BIND_MODE)s = %%s " % self._bindTable,
            # Right now, we only show owned calendars.
            [self._resourceID, _BIND_MODE_OWN]
        )
        names = [row[0] for row in rows]
        return names


    @memoized('name', '_children')
    def childWithName(self, name):
        """
        Retrieve the child with the given C{name} contained in this
        home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such child
            exists.
        """
        data = self._txn.execSQL(
            "select %(column_RESOURCE_ID)s from %(name)s where "
            "%(column_RESOURCE_NAME)s = %%s and %(column_HOME_RESOURCE_ID)s = %%s "
            "and %(column_BIND_MODE)s = %%s" % self._bindTable,
            [name, self._resourceID, _BIND_MODE_OWN]
        )
        if not data:
            return None
        resourceID = data[0][0]
        if self._notifier:
            childID = "%s/%s" % (self.uid(), name)
            notifier = self._notifier.clone(label="collection", id=childID)
        else:
            notifier = None
        return self._childClass(self, name, resourceID, notifier)


    def createChildWithName(self, name):
        if name.startswith("."):
            raise HomeChildNameNotAllowedError(name)

        rows = self._txn.execSQL(
            "select %(column_RESOURCE_NAME)s from %(name)s where "
            "%(column_RESOURCE_NAME)s = %%s AND "
            "%(column_HOME_RESOURCE_ID)s = %%s" % self._bindTable,
            [name, self._resourceID]
        )
        if rows:
            raise HomeChildNameAlreadyExistsError()

        rows = self._txn.execSQL("select nextval('RESOURCE_ID_SEQ')")
        resourceID = rows[0][0]
        self._txn.execSQL(
            "insert into %(name)s (%(column_RESOURCE_ID)s) values "
            "(%%s)" % self._childTable,
            [resourceID])

        self._txn.execSQL("""
            insert into %(name)s (
                %(column_HOME_RESOURCE_ID)s,
                %(column_RESOURCE_ID)s, %(column_RESOURCE_NAME)s, %(column_BIND_MODE)s,
                %(column_SEEN_BY_OWNER)s, %(column_SEEN_BY_SHAREE)s, %(column_BIND_STATUS)s) values (
            %%s, %%s, %%s, %%s, %%s, %%s, %%s)
            """ % self._bindTable,
            [self._resourceID, resourceID, name, _BIND_MODE_OWN, True, True,
             _BIND_STATUS_ACCEPTED]
        )

        newChild = self.childWithName(name)
        newChild.properties()[
            PropertyName.fromElement(ResourceType)] = newChild.resourceType()
        newChild._updateSyncToken()
        self.createdChild(newChild)

        if self._notifier:
            self._txn.postCommit(self._notifier.notify)


    def createdChild(self, child):
        pass


    def removeChildWithName(self, name):
        rows = self._txn.execSQL(
            """select %(column_RESOURCE_ID)s from %(name)s
               where %(column_RESOURCE_NAME)s = %%s and %(column_HOME_RESOURCE_ID)s = %%s""" % self._bindTable,
            [name, self._resourceID]
        )
        if not rows:
            raise NoSuchHomeChildError()
        resourceID = rows[0][0]

        self._txn.execSQL(
            "delete from %(name)s where %(column_RESOURCE_ID)s = %%s" % self._childTable,
            [resourceID]
        )
        self._children.pop(name, None)
        if self._txn._cursor.rowcount == 0:
            raise NoSuchHomeChildError()
        if self._notifier:
            self._txn.postCommit(self._notifier.notify)


    @cached
    def properties(self):
        return PropertyStore(
            self.uid(),
            self._txn,
            self._resourceID
        )


    # IDataStoreResource
    def contentType(self):
        """
        The content type of objects
        """
        return None


    def md5(self):
        return None


    def size(self):
        return 0


    def created(self):
        return None


    def modified(self):
        return None


    def notifierID(self, label="default"):
        if self._notifier:
            return self._notifier.getID(label)
        else:
            return None

class CommonHomeChild(LoggingMixIn, FancyEqMixin):
    """
    Common ancestor class of AddressBooks and Calendars.
    """

    compareAttributes = '_name _home _resourceID'.split()

    _objectResourceClass = None
    _bindTable = None
    _homeChildTable = None
    _revisionsTable = None
    _objectTable = None

    def __init__(self, home, name, resourceID, notifier):
        self._home = home
        self._name = name
        self._resourceID = resourceID
        self._objects = {}
        self._notifier = notifier

        self._index = None  # Derived classes need to set this
        self._invites = None # Derived classes need to set this


    @property
    def _txn(self):
        return self._home._txn


    def resourceType(self):
        return NotImplementedError


    def retrieveOldIndex(self):
        return self._index


    def retrieveOldInvites(self):
        return self._invites

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)

    def name(self):
        return self._name


    def rename(self, name):
        oldName = self._name
        self._txn.execSQL(
            "update %(name)s set %(column_RESOURCE_NAME)s = %%s "
            "where %(column_RESOURCE_ID)s = %%s AND "
            "%(column_HOME_RESOURCE_ID)s = %%s" % self._bindTable,
            [name, self._resourceID, self._home._resourceID]
        )
        self._name = name
        # update memos
        del self._home._children[oldName]
        self._home._children[name] = self
        self._updateSyncToken()

        if self._notifier:
            self._txn.postCommit(self._notifier.notify)


    def ownerHome(self):
        return self._home


    def setSharingUID(self, uid):
        self.properties()._setPerUserUID(uid)


    def objectResources(self):
        for name in self.listObjectResources():
            yield self.objectResourceWithName(name)


    def listObjectResources(self):
        rows = self._txn.execSQL(
            "select %(column_RESOURCE_NAME)s from %(name)s "
            "where %(column_PARENT_RESOURCE_ID)s = %%s" % self._objectTable,
            [self._resourceID])
        return sorted([row[0] for row in rows])


    @memoized('name', '_objects')
    def objectResourceWithName(self, name):
        rows = self._txn.execSQL(
            "select %(column_RESOURCE_ID)s from %(name)s "
            "where %(column_RESOURCE_NAME)s = %%s and %(column_PARENT_RESOURCE_ID)s = %%s" % self._objectTable,
            [name, self._resourceID]
        )
        if not rows:
            return None
        resid = rows[0][0]
        return self._objectResourceClass(name, self, resid)


    @memoized('uid', '_objects')
    def objectResourceWithUID(self, uid):
        rows = self._txn.execSQL(
            "select %(column_RESOURCE_ID)s, %(column_RESOURCE_NAME)s from %(name)s "
            "where %(column_UID)s = %%s and %(column_PARENT_RESOURCE_ID)s = %%s" % self._objectTable,
            [uid, self._resourceID]
        )
        if not rows:
            return None
        resid = rows[0][0]
        name = rows[0][1]
        return self._objectResourceClass(name, self, resid)


    def createObjectResourceWithName(self, name, component):
        if name.startswith("."):
            raise ObjectResourceNameNotAllowedError(name)

        rows = self._txn.execSQL(
            "select %(column_RESOURCE_ID)s from %(name)s "
            "where %(column_RESOURCE_NAME)s = %%s and %(column_PARENT_RESOURCE_ID)s = %%s" % self._objectTable,
            [name, self._resourceID]
        )
        if rows:
            raise ObjectResourceNameAlreadyExistsError()

        objectResource = self._objectResourceClass(name, self, None)
        objectResource.setComponent(component, inserting=True)

        # Note: setComponent triggers a notification, so we don't need to
        # call notify( ) here like we do for object removal.


    def removeObjectResourceWithName(self, name):
        rows = self._txn.execSQL(
            "delete from %(name)s "
            "where %(column_RESOURCE_NAME)s = %%s and %(column_PARENT_RESOURCE_ID)s = %%s "
            "returning %(column_UID)s" % self._objectTable,
            [name, self._resourceID],
            raiseOnZeroRowCount=lambda:NoSuchObjectResourceError()
        )
        uid = rows[0][0]
        self._objects.pop(name, None)
        self._objects.pop(uid, None)
        self._deleteRevision(name)

        if self._notifier:
            self._txn.postCommit(self._notifier.notify)


    def removeObjectResourceWithUID(self, uid):
        rows = self._txn.execSQL(
            "delete from %(name)s "
            "where %(column_UID)s = %%s and %(column_PARENT_RESOURCE_ID)s = %%s "
            "returning %(column_RESOURCE_NAME)s" % self._objectTable,
            [uid, self._resourceID],
            raiseOnZeroRowCount=lambda:NoSuchObjectResourceError()
        )
        name = rows[0][0]
        self._objects.pop(name, None)
        self._objects.pop(uid, None)
        self._deleteRevision(name)

        if self._notifier:
            self._txn.postCommit(self._notifier.notify)


    def syncToken(self):
        revision = self._txn.execSQL(
            "select %(column_REVISION)s from %(name)s where %(column_RESOURCE_ID)s = %%s" % self._homeChildTable,
            [self._resourceID])[0][0]
        return "%s#%s" % (self._resourceID, revision,)

    def objectResourcesSinceToken(self, token):
        raise NotImplementedError()


    def _updateSyncToken(self):
        
        self._txn.execSQL("""
            update %(name)s
            set (%(column_REVISION)s) = (nextval('%(sequence)s'))
            where %(column_RESOURCE_ID)s = %%s
            """ % self._homeChildTable,
            [self._resourceID]
        )

    def _insertRevision(self, name):
        self._changeRevision("insert", name)

    def _updateRevision(self, name):
        self._changeRevision("update", name)

    def _deleteRevision(self, name):
        self._changeRevision("delete", name)

    def _changeRevision(self, action, name):
        
        nextrevision = self._txn.execSQL("""
            select nextval('%(sequence)s')
            """ % self._homeChildTable
        )

        if action == "delete":
            self._txn.execSQL("""
                update %(name)s
                set (%(column_REVISION)s, %(column_DELETED)s) = (%%s, TRUE)
                where %(column_RESOURCE_ID)s = %%s and %(column_RESOURCE_NAME)s = %%s
                """ % self._revisionsTable,
                [nextrevision, self._resourceID, name]
            )
            self._txn.execSQL("""    
                update %(name)s
                set (%(column_REVISION)s) = (%%s)
                where %(column_RESOURCE_ID)s = %%s
                """ % self._homeChildTable,
                [nextrevision, self._resourceID]
            )
        elif action == "update":
            self._txn.execSQL("""
                update %(name)s
                set (%(column_REVISION)s) = (%%s)
                where %(column_RESOURCE_ID)s = %%s and %(column_RESOURCE_NAME)s = %%s
                """ % self._revisionsTable,
                [nextrevision, self._resourceID, name]
            )
            self._txn.execSQL("""    
                update %(name)s
                set (%(column_REVISION)s) = (%%s)
                where %(column_RESOURCE_ID)s = %%s
                """ % self._homeChildTable,
                [nextrevision, self._resourceID]
            )
        elif action == "insert":
            self._txn.execSQL("""
                delete from %(name)s
                where %(column_RESOURCE_ID)s = %%s and %(column_RESOURCE_NAME)s = %%s
                """ % self._revisionsTable,
                [self._resourceID, name,]
            )
            self._txn.execSQL("""
                insert into %(name)s
                (%(column_RESOURCE_ID)s, %(column_RESOURCE_NAME)s, %(column_REVISION)s, %(column_DELETED)s)
                values (%%s, %%s, %%s, FALSE)
                """ % self._revisionsTable,
                [self._resourceID, name, nextrevision]
            )
            self._txn.execSQL("""    
                update %(name)s
                set (%(column_REVISION)s) = (%%s)
                where %(column_RESOURCE_ID)s = %%s
                """ % self._homeChildTable,
                [nextrevision, self._resourceID]
            )
    @cached
    def properties(self):
        props = PropertyStore(
            self.ownerHome().uid(),
            self._txn,
            self._resourceID
        )
        self.initPropertyStore(props)
        return props

    def initPropertyStore(self, props):
        """
        A hook for subclasses to override in order to set up their property
        store after it's been created.

        @param props: the L{PropertyStore} from C{properties()}.
        """
        pass

    def _doValidate(self, component):
        raise NotImplementedError

    def notifierID(self, label="default"):
        if self._notifier:
            return self._notifier.getID(label)
        else:
            return None



    # IDataStoreResource
    def contentType(self):
        raise NotImplementedError()


    def md5(self):
        return None


    def size(self):
        return 0


    def created(self):
        created = self._txn.execSQL(
            "select extract(EPOCH from %(column_CREATED)s) from %(name)s "
            "where %(column_RESOURCE_ID)s = %%s" % self._homeChildTable,
            [self._resourceID]
        )[0][0]
        return int(created)

    def modified(self):
        modified = self._txn.execSQL(
            "select extract(EPOCH from %(column_MODIFIED)s) from %(name)s "
            "where %(column_RESOURCE_ID)s = %%s" % self._homeChildTable,
            [self._resourceID]
        )[0][0]
        return int(modified)

class CommonObjectResource(LoggingMixIn, FancyEqMixin):
    """
    @ivar _path: The path of the file on disk

    @type _path: L{FilePath}
    """

    compareAttributes = '_name _parentCollection'.split()
    
    _objectTable = None

    def __init__(self, name, parent, resid):
        self._name = name
        self._parentCollection = parent
        self._resourceID = resid
        self._objectText = None

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)

    @property
    def _txn(self):
        return self._parentCollection._txn

    def setComponent(self, component, inserting=False):
        raise NotImplementedError


    def component(self):
        raise NotImplementedError


    def text(self):
        raise NotImplementedError


    def uid(self):
        raise NotImplementedError

    @cached
    def properties(self):
        props = PropertyStore(
            self.uid(),
            self._txn,
            self._resourceID
        )
        self.initPropertyStore(props)
        return props

    def initPropertyStore(self, props):
        """
        A hook for subclasses to override in order to set up their property
        store after it's been created.

        @param props: the L{PropertyStore} from C{properties()}.
        """
        pass

    # IDataStoreResource
    def contentType(self):
        raise NotImplementedError()

    def md5(self):
        return None

    def size(self):
        size = self._txn.execSQL(
            "select character_length(%(column_TEXT)s) from %(name)s "
            "where %(column_RESOURCE_ID)s = %%s" % self._objectTable,
            [self._resourceID]
        )[0][0]
        return size


    def created(self):
        created = self._txn.execSQL(
            "select extract(EPOCH from %(column_CREATED)s) from %(name)s "
            "where %(column_RESOURCE_ID)s = %%s" % self._objectTable,
            [self._resourceID]
        )[0][0]
        return int(created)

    def modified(self):
        modified = self._txn.execSQL(
            "select extract(EPOCH from %(column_MODIFIED)s) from %(name)s "
            "where %(column_RESOURCE_ID)s = %%s" % self._objectTable,
            [self._resourceID]
        )[0][0]
        return int(modified)

class NotificationCollection(LoggingMixIn, FancyEqMixin):

    implements(INotificationCollection)

    compareAttributes = '_uid _resourceID'.split()

    _objectResourceClass = None
    _bindTable = None
    _homeChildTable = None
    _revisionsTable = None
    _objectTable = None

    def __init__(self, txn, uid, resourceID):

        self._txn = txn
        self._uid = uid
        self._resourceID = resourceID
        self._notifications = {}


    def resourceType(self):
        return ResourceType.notification #@UndefinedVariable

    def retrieveOldIndex(self):
        return PostgresLegacyNotificationsEmulator(self)

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)

    def name(self):
        return 'notification'

    def uid(self):
        return self._uid

    def notificationObjects(self):
        for name in self.listNotificationObjects():
            yield self.notificationObjectWithName(name)

    def listNotificationObjects(self):
        rows = self._txn.execSQL(
            "select (NOTIFICATION_UID) from NOTIFICATION "
            "where NOTIFICATION_HOME_RESOURCE_ID = %s",
            [self._resourceID])
        return sorted(["%s.xml" % row[0] for row in rows])

    def _nameToUID(self, name):
        """
        Based on the file-backed implementation, the 'name' is just uid +
        ".xml".
        """
        return name.rsplit(".", 1)[0]


    def notificationObjectWithName(self, name):
        return self.notificationObjectWithUID(self._nameToUID(name))

    @memoized('uid', '_notifications')
    def notificationObjectWithUID(self, uid):
        rows = self._txn.execSQL(
            "select RESOURCE_ID from NOTIFICATION "
            "where NOTIFICATION_UID = %s and NOTIFICATION_HOME_RESOURCE_ID = %s",
            [uid, self._resourceID])
        if rows:
            resourceID = rows[0][0]
            return NotificationObject(self, resourceID)
        else:
            return None


    def writeNotificationObject(self, uid, xmltype, xmldata):

        inserting = False
        notificationObject = self.notificationObjectWithUID(uid)
        if notificationObject is None:
            notificationObject = NotificationObject(self, None)
            inserting = True
        notificationObject.setData(uid, xmltype, xmldata, inserting=inserting)


    def removeNotificationObjectWithName(self, name):
        self.removeNotificationObjectWithUID(self._nameToUID(name))


    def removeNotificationObjectWithUID(self, uid):
        self._txn.execSQL(
            "delete from NOTIFICATION "
            "where NOTIFICATION_UID = %s and NOTIFICATION_HOME_RESOURCE_ID = %s",
            [uid, self._resourceID]
        )
        self._notifications.pop(uid, None)


    def syncToken(self):
        return 'dummy-sync-token'


    def notificationObjectsSinceToken(self, token):
        changed = []
        removed = []
        token = self.syncToken()
        return (changed, removed, token)


    @cached
    def properties(self):
        return PropertyStore(
            self._uid,
            self._txn,
            self._resourceID
        )

class NotificationObject(LoggingMixIn, FancyEqMixin):
    implements(INotificationObject)

    compareAttributes = '_resourceID _home'.split()

    def __init__(self, home, resourceID):
        self._home = home
        self._resourceID = resourceID


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)

    
    @property
    def _txn(self):
        return self._home._txn


    def notificationCollection(self):
        return self._home


    def name(self):
        return self.uid() + ".xml"


    def setData(self, uid, xmltype, xmldata, inserting=False):

        xmltypeString = xmltype.toxml()
        if inserting:
            rows = self._txn.execSQL(
                "insert into NOTIFICATION (NOTIFICATION_HOME_RESOURCE_ID, NOTIFICATION_UID, XML_TYPE, XML_DATA) "
                "values (%s, %s, %s, %s) returning RESOURCE_ID",
                [self._home._resourceID, uid, xmltypeString, xmldata]
            )
            self._resourceID = rows[0][0]
        else:
            self._txn.execSQL(
                "update NOTIFICATION set XML_TYPE = %s, XML_DATA = %s "
                "where NOTIFICATION_HOME_RESOURCE_ID = %s and NOTIFICATION_UID = %s",
                [xmltypeString, xmldata, self._home._resourceID, uid])

        self.properties()[PropertyName.fromElement(NotificationType)] = NotificationType(xmltype)


    def _fieldQuery(self, field):
        data = self._txn.execSQL(
            "select " + field + " from NOTIFICATION "
            "where RESOURCE_ID = %s",
            [self._resourceID]
        )
        return data[0][0]


    def xmldata(self):
        return self._fieldQuery("XML_DATA")


    def uid(self):
        return self._fieldQuery("NOTIFICATION_UID")


    @cached
    def properties(self):
        props = PropertyStore(
            self._home.uid(),
            self._txn,
            self._resourceID
        )
        self.initPropertyStore(props)
        return props

    def initPropertyStore(self, props):
        # Setup peruser special properties
        props.setSpecialProperties(
            (
            ),
            (
                PropertyName.fromElement(NotificationType),
            ),
        )

    def contentType(self):
        """
        The content type of NotificationObjects is text/xml.
        """
        return MimeType.fromString("text/xml")


    def md5(self):
        return hashlib.md5(self.xmldata()).hexdigest()


    def size(self):
        size = self._txn.execSQL(
            "select character_length(XML_DATA) from NOTIFICATION "
            "where RESOURCE_ID = %s",
            [self._resourceID]
        )[0][0]
        return size


    def created(self):
        modified = self._txn.execSQL(
            "select extract(EPOCH from CREATED) from NOTIFICATION "
            "where RESOURCE_ID = %s",
            [self._resourceID]
        )[0][0]
        return int(modified)

    def modified(self):
        modified = self._txn.execSQL(
            "select extract(EPOCH from MODIFIED) from NOTIFICATION "
            "where RESOURCE_ID = %s", [self._resourceID]
        )[0][0]
        return int(modified)
