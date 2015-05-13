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

from twext.enterprise.dal.record import SerializableRecord, fromTable
from twext.enterprise.dal.syntax import Select, Parameter, Insert, \
    SavepointAction, Delete, Max, Len, Update
from twext.enterprise.util import parseSQLTimestamp
from twext.internet.decorate import memoizedKey
from twext.python.clsprop import classproperty
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.util import FancyEqMixin
from twistedcaldav.dateops import datetimeMktime
from txdav.base.propertystore.sql import PropertyStore
from txdav.common.datastore.sql_tables import schema, _HOME_STATUS_NORMAL, \
    _HOME_STATUS_EXTERNAL, _HOME_STATUS_DISABLED, _HOME_STATUS_MIGRATING
from txdav.common.datastore.sql_util import _SharedSyncLogic
from txdav.common.icommondatastore import RecordNotAllowedError
from txdav.common.idirectoryservice import DirectoryRecordNotFoundError
from txdav.common.inotifications import INotificationCollection, \
    INotificationObject
from txdav.idav import ChangeCategory
from txweb2.dav.noneprops import NonePropertyStore
from txweb2.http_headers import MimeType
from zope.interface.declarations import implements
import hashlib
import json

"""
Classes and methods that relate to the Notification collection in the SQL store.
"""
class NotificationCollection(FancyEqMixin, _SharedSyncLogic):
    log = Logger()

    implements(INotificationCollection)

    compareAttributes = (
        "_ownerUID",
        "_resourceID",
    )

    _revisionsSchema = schema.NOTIFICATION_OBJECT_REVISIONS
    _homeSchema = schema.NOTIFICATION_HOME

    _externalClass = None


    @classmethod
    def makeClass(cls, transaction, homeData):
        """
        Build the actual home class taking into account the possibility that we might need to
        switch in the external version of the class.

        @param transaction: transaction
        @type transaction: L{CommonStoreTransaction}
        @param homeData: home table column data
        @type homeData: C{list}
        """

        status = homeData[cls.homeColumns().index(cls._homeSchema.STATUS)]
        if status == _HOME_STATUS_EXTERNAL:
            home = cls._externalClass(transaction, homeData)
        else:
            home = cls(transaction, homeData)
        return home.initFromStore()


    @classmethod
    def homeColumns(cls):
        """
        Return a list of column names to retrieve when doing an ownerUID->home lookup.
        """

        # Common behavior is to have created and modified

        return (
            cls._homeSchema.RESOURCE_ID,
            cls._homeSchema.OWNER_UID,
            cls._homeSchema.STATUS,
        )


    @classmethod
    def homeAttributes(cls):
        """
        Return a list of attributes names to map L{homeColumns} to.
        """

        # Common behavior is to have created and modified

        return (
            "_resourceID",
            "_ownerUID",
            "_status",
        )


    def __init__(self, txn, homeData):

        self._txn = txn

        for attr, value in zip(self.homeAttributes(), homeData):
            setattr(self, attr, value)

        self._txn = txn
        self._dataVersion = None
        self._notifications = {}
        self._notificationNames = None
        self._syncTokenRevision = None

        # Make sure we have push notifications setup to push on this collection
        # as well as the home it is in
        self._notifiers = dict([(factory_name, factory.newNotifier(self),) for factory_name, factory in txn._notifierFactories.items()])


    @inlineCallbacks
    def initFromStore(self):
        """
        Initialize this object from the store.
        """

        yield self._loadPropertyStore()
        returnValue(self)


    @property
    def _home(self):
        """
        L{NotificationCollection} serves as its own C{_home} for the purposes of
        working with L{_SharedSyncLogic}.
        """
        return self


    @classmethod
    def notificationsWithUID(cls, txn, uid, status=None, create=False):
        return cls.notificationsWith(txn, None, uid, status=status, create=create)


    @classmethod
    def notificationsWithResourceID(cls, txn, rid):
        return cls.notificationsWith(txn, rid, None)


    @classmethod
    @inlineCallbacks
    def notificationsWith(cls, txn, rid, uid, status=None, create=False):
        """
        @param uid: I'm going to assume uid is utf-8 encoded bytes
        """
        if rid is not None:
            query = cls._homeSchema.RESOURCE_ID == rid
        elif uid is not None:
            query = cls._homeSchema.OWNER_UID == uid
            if status is not None:
                query = query.And(cls._homeSchema.STATUS == status)
            else:
                statusSet = (_HOME_STATUS_NORMAL, _HOME_STATUS_EXTERNAL,)
                if txn._allowDisabled:
                    statusSet += (_HOME_STATUS_DISABLED,)
                query = query.And(cls._homeSchema.STATUS.In(statusSet))
        else:
            raise AssertionError("One of rid or uid must be set")

        results = yield Select(
            cls.homeColumns(),
            From=cls._homeSchema,
            Where=query,
        ).on(txn)

        if len(results) > 1:
            # Pick the best one in order: normal, disabled and external
            byStatus = dict([(result[cls.homeColumns().index(cls._homeSchema.STATUS)], result) for result in results])
            result = byStatus.get(_HOME_STATUS_NORMAL)
            if result is None:
                result = byStatus.get(_HOME_STATUS_DISABLED)
            if result is None:
                result = byStatus.get(_HOME_STATUS_EXTERNAL)
        elif results:
            result = results[0]
        else:
            result = None

        if result:
            # Return object that already exists in the store
            homeObject = yield cls.makeClass(txn, result)
            returnValue(homeObject)
        else:
            # Can only create when uid is specified
            if not create or uid is None:
                returnValue(None)

            # Determine if the user is local or external
            record = yield txn.directoryService().recordWithUID(uid.decode("utf-8"))
            if record is None:
                raise DirectoryRecordNotFoundError("Cannot create home for UID since no directory record exists: {}".format(uid))

            if status is None:
                createStatus = _HOME_STATUS_NORMAL if record.thisServer() else _HOME_STATUS_EXTERNAL
            elif status == _HOME_STATUS_MIGRATING:
                if record.thisServer():
                    raise RecordNotAllowedError("Cannot migrate a user data for a user already hosted on this server")
                createStatus = status
            elif status in (_HOME_STATUS_NORMAL, _HOME_STATUS_EXTERNAL,):
                createStatus = status
            else:
                raise RecordNotAllowedError("Cannot create home with status {}: {}".format(status, uid))

            # Use savepoint so we can do a partial rollback if there is a race
            # condition where this row has already been inserted
            savepoint = SavepointAction("notificationsWithUID")
            yield savepoint.acquire(txn)

            try:
                resourceid = (yield Insert(
                    {
                        cls._homeSchema.OWNER_UID: uid,
                        cls._homeSchema.STATUS: createStatus,
                    },
                    Return=cls._homeSchema.RESOURCE_ID
                ).on(txn))[0][0]
            except Exception:
                # FIXME: Really want to trap the pg.DatabaseError but in a non-
                # DB specific manner
                yield savepoint.rollback(txn)

                # Retry the query - row may exist now, if not re-raise
                results = yield Select(
                    cls.homeColumns(),
                    From=cls._homeSchema,
                    Where=query,
                ).on(txn)
                if results:
                    homeObject = yield cls.makeClass(txn, results[0])
                    returnValue(homeObject)
                else:
                    raise
            else:
                yield savepoint.release(txn)

                # Note that we must not cache the owner_uid->resource_id
                # mapping in the query cacher when creating as we don't want that to appear
                # until AFTER the commit
                results = yield Select(
                    cls.homeColumns(),
                    From=cls._homeSchema,
                    Where=cls._homeSchema.RESOURCE_ID == resourceid,
                ).on(txn)
                homeObject = yield cls.makeClass(txn, results[0])
                if homeObject.normal():
                    yield homeObject._initSyncToken()
                    yield homeObject.notifyChanged()
                returnValue(homeObject)


    @inlineCallbacks
    def _loadPropertyStore(self):
        self._propertyStore = yield PropertyStore.load(
            self._ownerUID,
            self._ownerUID,
            None,
            self._txn,
            self._resourceID,
            notifyCallback=self.notifyChanged
        )


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)


    def id(self):
        """
        Retrieve the store identifier for this collection.

        @return: store identifier.
        @rtype: C{int}
        """
        return self._resourceID


    @classproperty
    def _dataVersionQuery(cls):
        nh = cls._homeSchema
        return Select(
            [nh.DATAVERSION], From=nh,
            Where=nh.RESOURCE_ID == Parameter("resourceID")
        )


    @inlineCallbacks
    def dataVersion(self):
        if self._dataVersion is None:
            self._dataVersion = (yield self._dataVersionQuery.on(
                self._txn, resourceID=self._resourceID))[0][0]
        returnValue(self._dataVersion)


    def name(self):
        return "notification"


    def uid(self):
        return self._ownerUID


    def status(self):
        return self._status


    @inlineCallbacks
    def setStatus(self, newStatus):
        """
        Mark this home as being purged.
        """
        # Only if different
        if self._status != newStatus:
            yield Update(
                {self._homeSchema.STATUS: newStatus},
                Where=(self._homeSchema.RESOURCE_ID == self._resourceID),
            ).on(self._txn)
            self._status = newStatus


    def normal(self):
        """
        Is this an normal (internal) home.

        @return: a L{bool}.
        """
        return self._status == _HOME_STATUS_NORMAL


    def external(self):
        """
        Is this an external home.

        @return: a L{bool}.
        """
        return self._status == _HOME_STATUS_EXTERNAL


    def owned(self):
        return True


    def ownerHome(self):
        return self._home


    def viewerHome(self):
        return self._home


    def notificationObjectRecords(self):
        return NotificationObjectRecord.querysimple(self._txn, notificationHomeResourceID=self.id())


    @inlineCallbacks
    def notificationObjects(self):
        results = (yield NotificationObject.loadAllObjects(self))
        for result in results:
            self._notifications[result.uid()] = result
        self._notificationNames = sorted([result.name() for result in results])
        returnValue(results)

    _notificationUIDsForHomeQuery = Select(
        [schema.NOTIFICATION.NOTIFICATION_UID], From=schema.NOTIFICATION,
        Where=schema.NOTIFICATION.NOTIFICATION_HOME_RESOURCE_ID ==
        Parameter("resourceID"))


    @inlineCallbacks
    def listNotificationObjects(self):
        if self._notificationNames is None:
            rows = yield self._notificationUIDsForHomeQuery.on(
                self._txn, resourceID=self._resourceID)
            self._notificationNames = sorted([row[0] for row in rows])
        returnValue(self._notificationNames)


    # used by _SharedSyncLogic.resourceNamesSinceRevision()
    def listObjectResources(self):
        return self.listNotificationObjects()


    def _nameToUID(self, name):
        """
        Based on the file-backed implementation, the 'name' is just uid +
        ".xml".
        """
        return name.rsplit(".", 1)[0]


    def notificationObjectWithName(self, name):
        return self.notificationObjectWithUID(self._nameToUID(name))


    @memoizedKey("uid", "_notifications")
    @inlineCallbacks
    def notificationObjectWithUID(self, uid):
        """
        Create an empty notification object first then have it initialize itself
        from the store.
        """
        no = NotificationObject(self, uid)
        no = (yield no.initFromStore())
        returnValue(no)


    @inlineCallbacks
    def writeNotificationObject(self, uid, notificationtype, notificationdata):

        inserting = False
        notificationObject = yield self.notificationObjectWithUID(uid)
        if notificationObject is None:
            notificationObject = NotificationObject(self, uid)
            inserting = True
        yield notificationObject.setData(uid, notificationtype, notificationdata, inserting=inserting)
        if inserting:
            yield self._insertRevision("%s.xml" % (uid,))
            if self._notificationNames is not None:
                self._notificationNames.append(notificationObject.uid())
        else:
            yield self._updateRevision("%s.xml" % (uid,))
        yield self.notifyChanged()
        returnValue(notificationObject)


    def removeNotificationObjectWithName(self, name):
        if self._notificationNames is not None:
            self._notificationNames.remove(self._nameToUID(name))
        return self.removeNotificationObjectWithUID(self._nameToUID(name))

    _removeByUIDQuery = Delete(
        From=schema.NOTIFICATION,
        Where=(schema.NOTIFICATION.NOTIFICATION_UID == Parameter("uid")).And(
            schema.NOTIFICATION.NOTIFICATION_HOME_RESOURCE_ID
            == Parameter("resourceID")))


    @inlineCallbacks
    def removeNotificationObjectWithUID(self, uid):
        yield self._removeByUIDQuery.on(
            self._txn, uid=uid, resourceID=self._resourceID)
        self._notifications.pop(uid, None)
        yield self._deleteRevision("%s.xml" % (uid,))
        yield self.notifyChanged()

    _initSyncTokenQuery = Insert(
        {
            _revisionsSchema.HOME_RESOURCE_ID : Parameter("resourceID"),
            _revisionsSchema.RESOURCE_NAME    : None,
            _revisionsSchema.REVISION         : schema.REVISION_SEQ,
            _revisionsSchema.DELETED          : False
        }, Return=_revisionsSchema.REVISION
    )


    @inlineCallbacks
    def _initSyncToken(self):
        self._syncTokenRevision = (yield self._initSyncTokenQuery.on(
            self._txn, resourceID=self._resourceID))[0][0]

    _syncTokenQuery = Select(
        [Max(_revisionsSchema.REVISION)], From=_revisionsSchema,
        Where=_revisionsSchema.HOME_RESOURCE_ID == Parameter("resourceID")
    )


    @inlineCallbacks
    def syncToken(self):
        if self._syncTokenRevision is None:
            self._syncTokenRevision = yield self.syncTokenRevision()
        returnValue("%s_%s" % (self._resourceID, self._syncTokenRevision))


    @inlineCallbacks
    def syncTokenRevision(self):
        revision = (yield self._syncTokenQuery.on(self._txn, resourceID=self._resourceID))[0][0]
        if revision is None:
            revision = int((yield self._txn.calendarserverValue("MIN-VALID-REVISION")))
        returnValue(revision)


    def properties(self):
        return self._propertyStore


    def addNotifier(self, factory_name, notifier):
        if self._notifiers is None:
            self._notifiers = {}
        self._notifiers[factory_name] = notifier


    def getNotifier(self, factory_name):
        return self._notifiers.get(factory_name)


    def notifierID(self):
        return (self._txn._homeClass[self._txn._primaryHomeType]._notifierPrefix, "%s/notification" % (self.ownerHome().uid(),),)


    def parentNotifierID(self):
        return (self._txn._homeClass[self._txn._primaryHomeType]._notifierPrefix, "%s" % (self.ownerHome().uid(),),)


    @inlineCallbacks
    def notifyChanged(self, category=ChangeCategory.default):
        """
        Send notifications, change sync token and bump last modified because
        the resource has changed.  We ensure we only do this once per object
        per transaction.
        """
        if self._txn.isNotifiedAlready(self):
            returnValue(None)
        self._txn.notificationAddedForObject(self)

        # Send notifications
        if self._notifiers:
            # cache notifiers run in post commit
            notifier = self._notifiers.get("cache", None)
            if notifier:
                self._txn.postCommit(notifier.notify)
            # push notifiers add their work items immediately
            notifier = self._notifiers.get("push", None)
            if notifier:
                yield notifier.notify(self._txn, priority=category.value)

        returnValue(None)


    @classproperty
    def _completelyNewRevisionQuery(cls):
        rev = cls._revisionsSchema
        return Insert({rev.HOME_RESOURCE_ID: Parameter("homeID"),
                       # rev.RESOURCE_ID: Parameter("resourceID"),
                       rev.RESOURCE_NAME: Parameter("name"),
                       rev.REVISION: schema.REVISION_SEQ,
                       rev.DELETED: False},
                      Return=rev.REVISION)


    def _maybeNotify(self):
        """
        Emit a push notification after C{_changeRevision}.
        """
        return self.notifyChanged()


    @inlineCallbacks
    def remove(self):
        """
        Remove DB rows corresponding to this notification home.
        """
        # Delete NOTIFICATION rows
        no = schema.NOTIFICATION
        kwds = {"ResourceID": self._resourceID}
        yield Delete(
            From=no,
            Where=(
                no.NOTIFICATION_HOME_RESOURCE_ID == Parameter("ResourceID")
            ),
        ).on(self._txn, **kwds)

        # Delete NOTIFICATION_HOME (will cascade to NOTIFICATION_OBJECT_REVISIONS)
        nh = schema.NOTIFICATION_HOME
        yield Delete(
            From=nh,
            Where=(
                nh.RESOURCE_ID == Parameter("ResourceID")
            ),
        ).on(self._txn, **kwds)

    purge = remove



class NotificationObjectRecord(SerializableRecord, fromTable(schema.NOTIFICATION)):
    """
    @DynamicAttrs
    L{Record} for L{schema.NOTIFICATION}.
    """
    pass



class NotificationObject(FancyEqMixin, object):
    """
    This used to store XML data and an XML element for the type. But we are now switching it
    to use JSON internally. The app layer will convert that to XML and fill in the "blanks" as
    needed for the app.
    """
    log = Logger()

    implements(INotificationObject)

    compareAttributes = (
        "_resourceID",
        "_home",
    )

    _objectSchema = schema.NOTIFICATION

    def __init__(self, home, uid):
        self._home = home
        self._resourceID = None
        self._uid = uid
        self._md5 = None
        self._size = None
        self._created = None
        self._modified = None
        self._notificationType = None
        self._notificationData = None


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)


    @classproperty
    def _allColumnsByHomeIDQuery(cls):
        """
        DAL query to load all columns by home ID.
        """
        obj = cls._objectSchema
        return Select(
            [obj.RESOURCE_ID, obj.NOTIFICATION_UID, obj.MD5,
             Len(obj.NOTIFICATION_DATA), obj.NOTIFICATION_TYPE, obj.CREATED, obj.MODIFIED],
            From=obj,
            Where=(obj.NOTIFICATION_HOME_RESOURCE_ID == Parameter("homeID"))
        )


    @classmethod
    @inlineCallbacks
    def loadAllObjects(cls, parent):
        """
        Load all child objects and return a list of them. This must create the
        child classes and initialize them using "batched" SQL operations to keep
        this constant wrt the number of children. This is an optimization for
        Depth:1 operations on the collection.
        """

        results = []

        # Load from the main table first
        dataRows = (
            yield cls._allColumnsByHomeIDQuery.on(parent._txn,
                                                  homeID=parent._resourceID))

        if dataRows:
            # Get property stores for all these child resources (if any found)
            propertyStores = (yield PropertyStore.forMultipleResources(
                parent.uid(),
                None,
                None,
                parent._txn,
                schema.NOTIFICATION.RESOURCE_ID,
                schema.NOTIFICATION.NOTIFICATION_HOME_RESOURCE_ID,
                parent._resourceID,
            ))

        # Create the actual objects merging in properties
        for row in dataRows:
            child = cls(parent, None)
            (child._resourceID,
             child._uid,
             child._md5,
             child._size,
             child._notificationType,
             child._created,
             child._modified,) = tuple(row)
            child._created = parseSQLTimestamp(child._created)
            child._modified = parseSQLTimestamp(child._modified)
            try:
                child._notificationType = json.loads(child._notificationType)
            except ValueError:
                pass
            if isinstance(child._notificationType, unicode):
                child._notificationType = child._notificationType.encode("utf-8")
            child._loadPropertyStore(
                props=propertyStores.get(child._resourceID, None)
            )
            results.append(child)

        returnValue(results)


    @classproperty
    def _oneNotificationQuery(cls):
        no = cls._objectSchema
        return Select(
            [
                no.RESOURCE_ID,
                no.MD5,
                Len(no.NOTIFICATION_DATA),
                no.NOTIFICATION_TYPE,
                no.CREATED,
                no.MODIFIED
            ],
            From=no,
            Where=(no.NOTIFICATION_UID ==
                   Parameter("uid")).And(no.NOTIFICATION_HOME_RESOURCE_ID ==
                                         Parameter("homeID")))


    @inlineCallbacks
    def initFromStore(self):
        """
        Initialise this object from the store, based on its UID and home
        resource ID. We read in and cache all the extra metadata from the DB to
        avoid having to do DB queries for those individually later.

        @return: L{self} if object exists in the DB, else C{None}
        """
        rows = (yield self._oneNotificationQuery.on(
            self._txn, uid=self._uid, homeID=self._home._resourceID))
        if rows:
            (self._resourceID,
             self._md5,
             self._size,
             self._notificationType,
             self._created,
             self._modified,) = tuple(rows[0])
            self._created = parseSQLTimestamp(self._created)
            self._modified = parseSQLTimestamp(self._modified)
            try:
                self._notificationType = json.loads(self._notificationType)
            except ValueError:
                pass
            if isinstance(self._notificationType, unicode):
                self._notificationType = self._notificationType.encode("utf-8")
            self._loadPropertyStore()
            returnValue(self)
        else:
            returnValue(None)


    def _loadPropertyStore(self, props=None, created=False):
        if props is None:
            props = NonePropertyStore(self._home.uid())
        self._propertyStore = props


    def properties(self):
        return self._propertyStore


    def id(self):
        """
        Retrieve the store identifier for this object.

        @return: store identifier.
        @rtype: C{int}
        """
        return self._resourceID


    @property
    def _txn(self):
        return self._home._txn


    def notificationCollection(self):
        return self._home


    def uid(self):
        return self._uid


    def name(self):
        return self.uid() + ".xml"


    @classproperty
    def _newNotificationQuery(cls):
        no = cls._objectSchema
        return Insert(
            {
                no.NOTIFICATION_HOME_RESOURCE_ID: Parameter("homeID"),
                no.NOTIFICATION_UID: Parameter("uid"),
                no.NOTIFICATION_TYPE: Parameter("notificationType"),
                no.NOTIFICATION_DATA: Parameter("notificationData"),
                no.MD5: Parameter("md5"),
            },
            Return=[no.RESOURCE_ID, no.CREATED, no.MODIFIED]
        )


    @classproperty
    def _updateNotificationQuery(cls):
        no = cls._objectSchema
        return Update(
            {
                no.NOTIFICATION_TYPE: Parameter("notificationType"),
                no.NOTIFICATION_DATA: Parameter("notificationData"),
                no.MD5: Parameter("md5"),
            },
            Where=(no.NOTIFICATION_HOME_RESOURCE_ID == Parameter("homeID")).And(
                no.NOTIFICATION_UID == Parameter("uid")),
            Return=no.MODIFIED
        )


    @inlineCallbacks
    def setData(self, uid, notificationtype, notificationdata, inserting=False):
        """
        Set the object resource data and update and cached metadata.
        """

        notificationtext = json.dumps(notificationdata)
        self._notificationType = notificationtype
        self._md5 = hashlib.md5(notificationtext).hexdigest()
        self._size = len(notificationtext)
        if inserting:
            rows = yield self._newNotificationQuery.on(
                self._txn, homeID=self._home._resourceID, uid=uid,
                notificationType=json.dumps(self._notificationType),
                notificationData=notificationtext, md5=self._md5
            )
            self._resourceID, self._created, self._modified = (
                rows[0][0],
                parseSQLTimestamp(rows[0][1]),
                parseSQLTimestamp(rows[0][2]),
            )
            self._loadPropertyStore()
        else:
            rows = yield self._updateNotificationQuery.on(
                self._txn, homeID=self._home._resourceID, uid=uid,
                notificationType=json.dumps(self._notificationType),
                notificationData=notificationtext, md5=self._md5
            )
            self._modified = parseSQLTimestamp(rows[0][0])
        self._notificationData = notificationdata

    _notificationDataFromID = Select(
        [_objectSchema.NOTIFICATION_DATA], From=_objectSchema,
        Where=_objectSchema.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def notificationData(self):
        if self._notificationData is None:
            self._notificationData = (yield self._notificationDataFromID.on(self._txn, resourceID=self._resourceID))[0][0]
            try:
                self._notificationData = json.loads(self._notificationData)
            except ValueError:
                pass
            if isinstance(self._notificationData, unicode):
                self._notificationData = self._notificationData.encode("utf-8")
        returnValue(self._notificationData)


    def contentType(self):
        """
        The content type of NotificationObjects is text/xml.
        """
        return MimeType.fromString("text/xml")


    def md5(self):
        return self._md5


    def size(self):
        return self._size


    def notificationType(self):
        return self._notificationType


    def created(self):
        return datetimeMktime(self._created)


    def modified(self):
        return datetimeMktime(self._modified)
