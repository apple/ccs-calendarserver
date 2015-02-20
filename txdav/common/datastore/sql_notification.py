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
    _HOME_STATUS_EXTERNAL
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
        "_uid",
        "_resourceID",
    )

    _revisionsSchema = schema.NOTIFICATION_OBJECT_REVISIONS
    _homeSchema = schema.NOTIFICATION_HOME


    def __init__(self, txn, uid, resourceID, status):

        self._txn = txn
        self._uid = uid
        self._resourceID = resourceID
        self._status = status
        self._dataVersion = None
        self._notifications = {}
        self._notificationNames = None
        self._syncTokenRevision = None

        # Make sure we have push notifications setup to push on this collection
        # as well as the home it is in
        self._notifiers = dict([(factory_name, factory.newNotifier(self),) for factory_name, factory in txn._notifierFactories.items()])

    _resourceIDFromUIDQuery = Select(
        [_homeSchema.RESOURCE_ID, _homeSchema.STATUS],
        From=_homeSchema,
        Where=_homeSchema.OWNER_UID == Parameter("uid")
    )

    _UIDFromResourceIDQuery = Select(
        [_homeSchema.OWNER_UID],
        From=_homeSchema,
        Where=_homeSchema.RESOURCE_ID == Parameter("rid")
    )

    _provisionNewNotificationsQuery = Insert(
        {
            _homeSchema.OWNER_UID: Parameter("uid"),
            _homeSchema.STATUS: Parameter("status"),
        },
        Return=_homeSchema.RESOURCE_ID
    )


    @property
    def _home(self):
        """
        L{NotificationCollection} serves as its own C{_home} for the purposes of
        working with L{_SharedSyncLogic}.
        """
        return self


    @classmethod
    @inlineCallbacks
    def notificationsWithUID(cls, txn, uid, create, expected_status=_HOME_STATUS_NORMAL):
        """
        @param uid: I'm going to assume uid is utf-8 encoded bytes
        """
        rows = yield cls._resourceIDFromUIDQuery.on(txn, uid=uid)

        if rows:
            resourceID = rows[0][0]
            status = rows[0][1]
            if status != expected_status:
                raise RecordNotAllowedError("Notifications status mismatch: {} != {}".format(status, expected_status))
            created = False
        elif create:
            # Determine if the user is local or external
            record = yield txn.directoryService().recordWithUID(uid.decode("utf-8"))
            if record is None:
                raise DirectoryRecordNotFoundError("Cannot create home for UID since no directory record exists: {}".format(uid))

            status = _HOME_STATUS_NORMAL if record.thisServer() else _HOME_STATUS_EXTERNAL
            if status != expected_status:
                raise RecordNotAllowedError("Notifications status mismatch: {} != {}".format(status, expected_status))

            # Use savepoint so we can do a partial rollback if there is a race
            # condition where this row has already been inserted
            savepoint = SavepointAction("notificationsWithUID")
            yield savepoint.acquire(txn)

            try:
                resourceID = str((
                    yield cls._provisionNewNotificationsQuery.on(txn, uid=uid, status=status)
                )[0][0])
            except Exception:
                # FIXME: Really want to trap the pg.DatabaseError but in a non-
                # DB specific manner
                yield savepoint.rollback(txn)

                # Retry the query - row may exist now, if not re-raise
                rows = yield cls._resourceIDFromUIDQuery.on(txn, uid=uid)
                if rows:
                    resourceID = rows[0][0]
                    status = rows[0][1]
                    if status != expected_status:
                        raise RecordNotAllowedError("Notifications status mismatch: {} != {}".format(status, expected_status))
                    created = False
                else:
                    raise
            else:
                created = True
                yield savepoint.release(txn)
        else:
            returnValue(None)
        collection = cls(txn, uid, resourceID, status)
        yield collection._loadPropertyStore()
        if created:
            yield collection._initSyncToken()
            yield collection.notifyChanged()
        returnValue(collection)


    @classmethod
    @inlineCallbacks
    def notificationsWithResourceID(cls, txn, rid):
        rows = yield cls._UIDFromResourceIDQuery.on(txn, rid=rid)

        if rows:
            uid = rows[0][0]
            result = (yield cls.notificationsWithUID(txn, uid, create=False))
            returnValue(result)
        else:
            returnValue(None)


    @inlineCallbacks
    def _loadPropertyStore(self):
        self._propertyStore = yield PropertyStore.load(
            self._uid,
            self._uid,
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
        return self._uid


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
            self._resourceID, self._created, self._modified = rows[0]
            self._loadPropertyStore()
        else:
            rows = yield self._updateNotificationQuery.on(
                self._txn, homeID=self._home._resourceID, uid=uid,
                notificationType=json.dumps(self._notificationType),
                notificationData=notificationtext, md5=self._md5
            )
            self._modified = rows[0][0]
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
        return datetimeMktime(parseSQLTimestamp(self._created))


    def modified(self):
        return datetimeMktime(parseSQLTimestamp(self._modified))
