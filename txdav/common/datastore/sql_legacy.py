# -*- test-case-name: twistedcaldav.test.test_sharing,twistedcaldav.test.test_calendarquery -*-
##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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

import StringIO

from twistedcaldav.sharing import SharedCollectionRecord

from twisted.python import hashlib
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twext.python.clsprop import classproperty
from twext.python.log import Logger, LoggingMixIn

from twistedcaldav.config import config
from twistedcaldav.dateops import normalizeForIndex, pyCalendarTodatetime
from twistedcaldav.memcachepool import CachePoolUserMixIn
from twistedcaldav.notifications import NotificationRecord
from twistedcaldav.query import (
    calendarqueryfilter, calendarquery, addressbookquery, expression,
    addressbookqueryfilter)
from twistedcaldav.query.sqlgenerator import sqlgenerator
from twistedcaldav.sharing import Invite

from txdav.common.icommondatastore import (
    IndexedSearchException, ReservationError)

from twext.enterprise.dal.syntax import Update, SavepointAction
from twext.enterprise.dal.syntax import Insert
from twext.enterprise.dal.syntax import Select
from twext.enterprise.dal.syntax import Delete
from twext.enterprise.dal.syntax import Parameter
from txdav.common.datastore.sql_tables import (
    _BIND_MODE_OWN, _BIND_MODE_READ, _BIND_MODE_WRITE, _BIND_MODE_DIRECT,
    _BIND_STATUS_INVITED, _BIND_STATUS_ACCEPTED, _BIND_STATUS_DECLINED,
    _BIND_STATUS_INVALID, CALENDAR_BIND_TABLE, CALENDAR_HOME_TABLE,
    ADDRESSBOOK_HOME_TABLE, ADDRESSBOOK_BIND_TABLE, schema)


from pycalendar.duration import PyCalendarDuration

log = Logger()

indexfbtype_to_icalfbtype = {
    0: '?',
    1: 'F',
    2: 'B',
    3: 'U',
    4: 'T',
}

class PostgresLegacyNotificationsEmulator(object):
    def __init__(self, notificationsCollection):
        self._collection = notificationsCollection


    @inlineCallbacks
    def _recordForObject(self, notificationObject):
        if notificationObject:
            returnValue(
                NotificationRecord(
                    notificationObject.uid(),
                    notificationObject.name(),
                    (yield notificationObject.xmlType().toxml())
                )
            )
        else:
            returnValue(None)


    def recordForName(self, name):
        return self._recordForObject(
            self._collection.notificationObjectWithName(name)
        )


    @inlineCallbacks
    def recordForUID(self, uid):
        returnValue((yield self._recordForObject(
            (yield self._collection.notificationObjectWithUID(uid))
        )))


    def removeRecordForUID(self, uid):
        return self._collection.removeNotificationObjectWithUID(uid)


    def removeRecordForName(self, name):
        return self._collection.removeNotificationObjectWithName(name)



class SQLLegacyInvites(object):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    _homeTable = None
    _bindTable = None

    _homeSchema = None
    _bindSchema = None

    def __init__(self, collection):
        self._collection = collection

        # Since we do multi-table requests we need a dict that combines tables
        self._combinedTable = {}
        for key, value in self._homeTable.iteritems():
            self._combinedTable["HOME:%s" % (key,)] = value
        for key, value in self._bindTable.iteritems():
            self._combinedTable["BIND:%s" % (key,)] = value


    @property
    def _txn(self):
        return self._collection._txn


    def _getHomeWithUID(self, uid):
        raise NotImplementedError()


    def create(self):
        "No-op, because the index implicitly always exists in the database."


    def remove(self):
        "No-op, because the index implicitly always exists in the database."


    @classmethod
    def _allColumnsQuery(cls, condition):
        inv = schema.INVITE
        home = cls._homeSchema
        bind = cls._bindSchema
        return Select(
            [inv.INVITE_UID,
             inv.NAME,
             inv.RECIPIENT_ADDRESS,
             home.OWNER_UID,
             bind.BIND_MODE,
             bind.BIND_STATUS,
             bind.MESSAGE],
            From=inv.join(home).join(bind),
            Where=(
                condition
                .And(inv.RESOURCE_ID == bind.RESOURCE_ID)
                .And(inv.HOME_RESOURCE_ID == home.RESOURCE_ID)
                .And(inv.HOME_RESOURCE_ID == bind.HOME_RESOURCE_ID)),
            OrderBy=inv.NAME, Ascending=True
        )


    @classproperty
    def _allRecordsQuery(cls): #@NoSelf
        """
        DAL query for all invite records with a given resource ID.
        """
        inv = schema.INVITE
        return cls._allColumnsQuery(inv.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def allRecords(self):
        values = []
        rows = yield self._allRecordsQuery.on(
            self._txn, resourceID=self._collection._resourceID
        )
        for row in rows:
            values.append(self._makeInvite(row))
        returnValue(values)


    @classproperty
    def _inviteForRecipientQuery(cls): #@NoSelf
        """
        DAL query to retrieve an invite record for a given recipient address.
        """
        inv = schema.INVITE
        return cls._allColumnsQuery(
            (inv.RESOURCE_ID == Parameter("resourceID")).And(inv.RECIPIENT_ADDRESS == Parameter("recipient"))
        )


    @inlineCallbacks
    def recordForUserID(self, userid):
        rows = yield self._inviteForRecipientQuery.on(
            self._txn,
            resourceID=self._collection._resourceID,
            recipient=userid
        )
        returnValue(self._makeInvite(rows[0]) if rows else None)


    @classproperty
    def _inviteForPrincipalUIDQuery(cls): #@NoSelf
        """
        DAL query to retrieve an invite record for a given principal UID.
        """
        inv = schema.INVITE
        home = cls._homeSchema
        return cls._allColumnsQuery(
            (inv.RESOURCE_ID == Parameter("resourceID")).And(home.OWNER_UID == Parameter("principalUID"))
        )


    @inlineCallbacks
    def recordForPrincipalUID(self, principalUID):
        rows = yield self._inviteForPrincipalUIDQuery.on(
            self._txn,
            resourceID=self._collection._resourceID,
            principalUID=principalUID
        )
        returnValue(self._makeInvite(rows[0]) if rows else None)


    @classproperty
    def _inviteForUIDQuery(cls): #@NoSelf
        """
        DAL query to retrieve an invite record for a given recipient address.
        """
        inv = schema.INVITE
        return cls._allColumnsQuery(inv.INVITE_UID == Parameter("uid"))


    @inlineCallbacks
    def recordForInviteUID(self, inviteUID):
        rows = yield self._inviteForUIDQuery.on(self._txn, uid=inviteUID)
        returnValue(self._makeInvite(rows[0]) if rows else None)


    def _makeInvite(self, row):
        [inviteuid, common_name, userid, ownerUID,
            bindMode, bindStatus, summary] = row
        # FIXME: this is really the responsibility of the protocol layer.
        state = {
            _BIND_STATUS_INVITED: "NEEDS-ACTION",
            _BIND_STATUS_ACCEPTED: "ACCEPTED",
            _BIND_STATUS_DECLINED: "DECLINED",
            _BIND_STATUS_INVALID: "INVALID",
        }[bindStatus]
        access = {
            _BIND_MODE_OWN: "own",
            _BIND_MODE_READ: "read-only",
            _BIND_MODE_WRITE: "read-write"
        }[bindMode]
        return Invite(
            inviteuid, userid, ownerUID, common_name,
            access, state, summary
        )


    @classproperty
    def _updateBindQuery(cls): #@NoSelf
        bind = cls._bindSchema

        return Update({bind.BIND_MODE: Parameter("mode"),
                       bind.BIND_STATUS: Parameter("status"),
                       bind.MESSAGE: Parameter("message")},
                      Where=
                      (bind.RESOURCE_ID == Parameter("resourceID"))
                      .And(bind.HOME_RESOURCE_ID == Parameter("homeID")))


    @classproperty
    def _idsForInviteUID(cls): #@NoSelf
        inv = schema.INVITE
        return Select([inv.RESOURCE_ID, inv.HOME_RESOURCE_ID],
                      From=inv,
                      Where=inv.INVITE_UID == Parameter("inviteuid"))


    @classproperty
    def _updateInviteQuery(cls): #@NoSelf
        """
        DAL query to update an invitation for a given recipient.
        """
        inv = schema.INVITE
        return Update({inv.NAME: Parameter("name")},
                      Where=inv.INVITE_UID == Parameter("uid"))


    @classproperty
    def _insertBindQuery(cls): #@NoSelf
        bind = cls._bindSchema
        return Insert(
            {
                bind.HOME_RESOURCE_ID: Parameter("homeID"),
                bind.RESOURCE_ID: Parameter("resourceID"),
                bind.BIND_MODE: Parameter("mode"),
                bind.BIND_STATUS: Parameter("status"),
                bind.MESSAGE: Parameter("message"),

                # name is NULL because the resource is not bound yet, just
                # invited; let's be explicit about that.
                bind.RESOURCE_NAME: None,
                bind.SEEN_BY_OWNER: False,
                bind.SEEN_BY_SHAREE: False,
            }
        )


    @classproperty
    def _insertInviteQuery(cls): #@NoSelf
        inv = schema.INVITE
        return Insert(
            {
                inv.INVITE_UID: Parameter("uid"),
                inv.NAME: Parameter("name"),
                inv.HOME_RESOURCE_ID: Parameter("homeID"),
                inv.RESOURCE_ID: Parameter("resourceID"),
                inv.RECIPIENT_ADDRESS: Parameter("recipient")
            }
        )


    @inlineCallbacks
    def addOrUpdateRecord(self, record):
        bindMode = {'read-only': _BIND_MODE_READ,
                    'read-write': _BIND_MODE_WRITE}[record.access]
        bindStatus = {
            "NEEDS-ACTION": _BIND_STATUS_INVITED,
            "ACCEPTED": _BIND_STATUS_ACCEPTED,
            "DECLINED": _BIND_STATUS_DECLINED,
            "INVALID": _BIND_STATUS_INVALID,
        }[record.state]
        shareeHome = yield self._getHomeWithUID(record.principalUID)
        rows = yield self._idsForInviteUID.on(self._txn,
                                              inviteuid=record.inviteuid)
        if rows:
            [[resourceID, homeResourceID]] = rows
            yield self._updateBindQuery.on(
                self._txn,
                mode=bindMode, status=bindStatus, message=record.summary,
                resourceID=resourceID, homeID=homeResourceID
            )
            yield self._updateInviteQuery.on(
                self._txn, name=record.name, uid=record.inviteuid
            )
        else:
            yield self._insertInviteQuery.on(
                self._txn, uid=record.inviteuid, name=record.name,
                homeID=shareeHome._resourceID,
                resourceID=self._collection._resourceID,
                recipient=record.userid
            )
            yield self._insertBindQuery.on(
                self._txn,
                homeID=shareeHome._resourceID,
                resourceID=self._collection._resourceID,
                mode=bindMode,
                status=bindStatus,
                message=record.summary
            )
        
        # Must send notification to ensure cache invalidation occurs
        self._collection.notifyChanged()


    @classmethod
    def _deleteOneBindQuery(cls, constraint):
        inv = schema.INVITE
        bind = cls._bindSchema
        return Delete(
            From=bind, Where=(bind.HOME_RESOURCE_ID, bind.RESOURCE_ID) ==
            Select([inv.HOME_RESOURCE_ID, inv.RESOURCE_ID],
                   From=inv, Where=constraint))


    @classmethod
    def _deleteOneInviteQuery(cls, constraint):
        inv = schema.INVITE
        return Delete(From=inv, Where=constraint)


    @classproperty
    def _deleteBindByUID(cls): #@NoSelf
        inv = schema.INVITE
        return cls._deleteOneBindQuery(inv.INVITE_UID == Parameter("uid"))


    @classproperty
    def _deleteInviteByUID(cls): #@NoSelf
        inv = schema.INVITE
        return cls._deleteOneInviteQuery(inv.INVITE_UID == Parameter("uid"))


    @inlineCallbacks
    def removeRecordForInviteUID(self, inviteUID):
        yield self._deleteBindByUID.on(self._txn, uid=inviteUID)
        yield self._deleteInviteByUID.on(self._txn, uid=inviteUID)
        
        # Must send notification to ensure cache invalidation occurs
        self._collection.notifyChanged()



class SQLLegacyCalendarInvites(SQLLegacyInvites):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    _homeTable = CALENDAR_HOME_TABLE
    _bindTable = CALENDAR_BIND_TABLE

    _homeSchema = schema.CALENDAR_HOME
    _bindSchema = schema.CALENDAR_BIND

    def _getHomeWithUID(self, uid):
        return self._txn.calendarHomeWithUID(uid, create=True)



class SQLLegacyAddressBookInvites(SQLLegacyInvites):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    _homeTable = ADDRESSBOOK_HOME_TABLE
    _bindTable = ADDRESSBOOK_BIND_TABLE

    _homeSchema = schema.ADDRESSBOOK_HOME
    _bindSchema = schema.ADDRESSBOOK_BIND

    def _getHomeWithUID(self, uid):
        return self._txn.addressbookHomeWithUID(uid, create=True)



class SQLLegacyShares(object):

    _homeTable = None
    _bindTable = None
    _urlTopSegment = None

    _homeSchema = None
    _bindSchema = None

    def __init__(self, home):
        self._home = home


    @property
    def _txn(self):
        return self._home._txn


    def _getHomeWithUID(self, uid):
        raise NotImplementedError()


    def create(self):
        pass


    def remove(self):
        pass


    @classproperty
    def _allSharedToQuery(cls): #@NoSelf
        bind = cls._bindSchema
        return Select(
            [bind.RESOURCE_ID, bind.RESOURCE_NAME,
             bind.BIND_MODE, bind.MESSAGE],
            From=bind,
            Where=(bind.HOME_RESOURCE_ID == Parameter("homeID"))
            .And(bind.BIND_MODE != _BIND_MODE_OWN)
            .And(bind.RESOURCE_NAME != None)
        )


    @classproperty
    def _inviteUIDByResourceIDsQuery(cls): #@NoSelf
        inv = schema.INVITE
        return Select(
            [inv.INVITE_UID], From=inv, Where=
            (inv.RESOURCE_ID == Parameter("resourceID"))
            .And(inv.HOME_RESOURCE_ID == Parameter("homeID"))
        )


    @classproperty
    def _ownerHomeIDAndName(cls): #@NoSelf
        bind = cls._bindSchema
        return Select(
            [bind.HOME_RESOURCE_ID, bind.RESOURCE_NAME], From=bind, Where=
            (bind.RESOURCE_ID == Parameter("resourceID"))
            .And(bind.BIND_MODE == _BIND_MODE_OWN)
        )


    @classproperty
    def _ownerUIDFromHomeID(cls): #@NoSelf
        home = cls._homeSchema
        return Select(
            [home.OWNER_UID], From=home,
            Where=home.RESOURCE_ID == Parameter("homeID")
        )




    @inlineCallbacks
    def allRecords(self):
        # This should have been a smart join that got all these columns at
        # once, but let's not bother to fix it, since the actual query we
        # _want_ to do (just look for binds in a particular homes) is
        # much simpler anyway; we should just do that.
        all = []
        shareRows = yield self._allSharedToQuery.on(
            self._txn, homeID=self._home._resourceID)
        for resourceID, resourceName, bindMode, summary in shareRows:
            [[ownerHomeID, ownerResourceName]] = yield (
                self._ownerHomeIDAndName.on(self._txn,
                                            resourceID=resourceID))
            [[ownerUID]] = yield self._ownerUIDFromHomeID.on(
                self._txn, homeID=ownerHomeID)
            hosturl = '/%s/__uids__/%s/%s' % (
                self._urlTopSegment, ownerUID, ownerResourceName
            )
            localname = resourceName
            if bindMode != _BIND_MODE_DIRECT:
                sharetype = 'I'
                [[shareuid]] = yield self._inviteUIDByResourceIDsQuery.on(
                    self._txn, resourceID=resourceID,
                    homeID=self._home._resourceID
                )
            else:
                sharetype = 'D'
                shareuid = "Direct-%s-%s" % (self._home._resourceID, resourceID,)
            record = SharedCollectionRecord(
                shareuid, sharetype, hosturl, localname, summary
            )
            all.append(record)
        returnValue(all)

    def directShareID(self, shareeHome, sharerCollection):
        return "Direct-%s-%s" % (shareeHome._newStoreHome._resourceID, sharerCollection._newStoreObject._resourceID,)

    @inlineCallbacks
    def _search(self, **kw):
        [[key, value]] = kw.items()
        for record in (yield self.allRecords()):
            if getattr(record, key) == value:
                returnValue((record))


    def recordForShareUID(self, shareUID):
        return self._search(shareuid=shareUID)


    @classproperty
    def _updateBindName(cls): #@NoSelf
        bind = cls._bindSchema
        return Update({bind.RESOURCE_NAME: Parameter("localname")},
                      Where=(bind.HOME_RESOURCE_ID == Parameter("homeID"))
                      .And(bind.RESOURCE_ID == Parameter('resourceID')))


    @classproperty
    def _acceptDirectShareQuery(cls): #@NoSelf
        bind = cls._bindSchema
        return Insert({
            bind.HOME_RESOURCE_ID: Parameter("homeID"),
            bind.RESOURCE_ID: Parameter("resourceID"), 
            bind.RESOURCE_NAME: Parameter("name"),
            bind.MESSAGE: Parameter("message"),
            bind.BIND_MODE: _BIND_MODE_DIRECT,
            bind.BIND_STATUS: _BIND_STATUS_ACCEPTED,
            bind.SEEN_BY_OWNER: True,
            bind.SEEN_BY_SHAREE: True,
        })


    @inlineCallbacks
    def addOrUpdateRecord(self, record):
        # record.hosturl -> /.../__uids__/<uid>/<name>
        splithost = record.hosturl.split('/')

        # Double-check the path
        if splithost[2] != "__uids__":
            raise ValueError(
                "Sharing URL must be a __uids__ path: %s" % (record.hosturl,))

        ownerUID = splithost[3]
        ownerCollectionName = splithost[4]
        ownerHome = yield self._getHomeWithUID(ownerUID)
        ownerCollection = yield ownerHome.childWithName(ownerCollectionName)
        collectionResourceID = ownerCollection._resourceID

        if record.sharetype == 'I':
            # There needs to be a bind already, one that corresponds to the
            # invitation.  The invitation's UID is the same as the share UID.  I
            # just need to update its 'localname', i.e.
            # XXX_BIND.XXX_RESOURCE_NAME.

            yield self._updateBindName.on(
                self._txn, localname=record.localname,
                homeID=self._home._resourceID, resourceID=collectionResourceID
            )
        elif record.sharetype == 'D':
            # There is no bind entry already so add one - but be aware of possible race to create

            # Use savepoint so we can do a partial rollback if there is a race condition
            # where this row has already been inserted
            savepoint = SavepointAction("addOrUpdateRecord")
            yield savepoint.acquire(self._txn)

            try:
                yield self._acceptDirectShareQuery.on(
                    self._txn, homeID=self._home._resourceID,
                    resourceID=collectionResourceID, name=record.localname,
                    message=record.summary
                )
            except Exception: # FIXME: Really want to trap the pg.DatabaseError but in a non-DB specific manner
                yield savepoint.rollback(self._txn)

                # For now we will assume that the insert already done is the winner - so nothing more to do here
            else:
                yield savepoint.release(self._txn)

        shareeCollection = yield self._home.sharedChildWithName(record.localname)
        yield shareeCollection._initSyncToken()


    @classproperty
    def _unbindShareQuery(cls): #@NoSelf
        bind = cls._bindSchema
        return Update({
            bind.RESOURCE_NAME: None
        }, Where=(bind.RESOURCE_NAME == Parameter("name"))
        .And(bind.HOME_RESOURCE_ID == Parameter("homeID")))


    @inlineCallbacks
    def removeRecordForLocalName(self, localname):
        record = yield self.recordForLocalName(localname)
        shareeCollection = yield self._home.sharedChildWithName(record.localname)
        yield shareeCollection._deletedSyncToken(sharedRemoval=True)

        result = yield self._unbindShareQuery.on(self._txn, name=localname,
                                                 homeID=self._home._resourceID)
        returnValue(result)


    @classproperty
    def _removeInviteShareQuery(cls): #@NoSelf
        """
        DAL query to remove a non-direct share by invite UID.
        """
        bind = cls._bindSchema
        inv = schema.INVITE
        return Update(
            {bind.RESOURCE_NAME: None},
            Where=(bind.HOME_RESOURCE_ID, bind.RESOURCE_ID) ==
            Select([inv.HOME_RESOURCE_ID, inv.RESOURCE_ID],
                   From=inv, Where=inv.INVITE_UID == Parameter("uid")))


    @classproperty
    def _removeDirectShareQuery(cls): #@NoSelf
        """
        DAL query to remove a direct share by its homeID and resourceID.
        """
        bind = cls._bindSchema
        return Delete(From=bind,
                      Where=(bind.HOME_RESOURCE_ID == Parameter("homeID"))
                      .And(bind.RESOURCE_ID == Parameter("resourceID")))


    @inlineCallbacks
    def removeRecordForShareUID(self, shareUID):

        record = yield self.recordForShareUID(shareUID)
        shareeCollection = yield self._home.sharedChildWithName(record.localname)
        yield shareeCollection._deletedSyncToken(sharedRemoval=True)

        if not shareUID.startswith("Direct"):
            yield self._removeInviteShareQuery.on(self._txn, uid=shareUID)
        else:
            # Extract pieces from synthesised UID
            homeID, resourceID = shareUID[len("Direct-"):].split("-")
            # Now remove the binding for the direct share
            yield self._removeDirectShareQuery.on(
                self._txn, homeID=homeID, resourceID=resourceID)


class SQLLegacyCalendarShares(SQLLegacyShares):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    _homeTable = CALENDAR_HOME_TABLE
    _bindTable = CALENDAR_BIND_TABLE
    _homeSchema = schema.CALENDAR_HOME
    _bindSchema = schema.CALENDAR_BIND
    _urlTopSegment = "calendars"


    def _getHomeWithUID(self, uid):
        return self._txn.calendarHomeWithUID(uid, create=True)



class SQLLegacyAddressBookShares(SQLLegacyShares):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    _homeTable = ADDRESSBOOK_HOME_TABLE
    _bindTable = ADDRESSBOOK_BIND_TABLE
    _homeSchema = schema.ADDRESSBOOK_HOME
    _bindSchema = schema.ADDRESSBOOK_BIND
    _urlTopSegment = "addressbooks"


    def _getHomeWithUID(self, uid):
        return self._txn.addressbookHomeWithUID(uid, create=True)



class MemcachedUIDReserver(CachePoolUserMixIn, LoggingMixIn):
    def __init__(self, index, cachePool=None):
        self.index = index
        self._cachePool = cachePool

    def _key(self, uid):
        return 'reservation:%s' % (
            hashlib.md5('%s:%s' % (uid,
                                   self.index.resource._resourceID)).hexdigest())

    def reserveUID(self, uid):
        uid = uid.encode('utf-8')
        self.log_debug("Reserving UID %r @ %r" % (
                uid,
                self.index.resource))

        def _handleFalse(result):
            if result is False:
                raise ReservationError(
                    "UID %s already reserved for calendar collection %s."
                    % (uid, self.index.resource._name)
                    )

        d = self.getCachePool().add(self._key(uid),
                                    'reserved',
                                    expireTime=config.UIDReservationTimeOut)
        d.addCallback(_handleFalse)
        return d


    def unreserveUID(self, uid):
        uid = uid.encode('utf-8')
        self.log_debug("Unreserving UID %r @ %r" % (
                uid,
                self.index.resource))

        def _handleFalse(result):
            if result is False:
                raise ReservationError(
                    "UID %s is not reserved for calendar collection %s."
                    % (uid, self.index.resource._resourceID)
                    )

        d = self.getCachePool().delete(self._key(uid))
        d.addCallback(_handleFalse)
        return d


    def isReservedUID(self, uid):
        uid = uid.encode('utf-8')
        self.log_debug("Is reserved UID %r @ %r" % (
                uid,
                self.index.resource))

        def _checkValue((flags, value)):
            if value is None:
                return False
            else:
                return True

        d = self.getCachePool().get(self._key(uid))
        d.addCallback(_checkValue)
        return d

class DummyUIDReserver(LoggingMixIn):

    def __init__(self, index):
        self.index = index
        self.reservations = set()

    def _key(self, uid):
        return 'reservation:%s' % (
            hashlib.md5('%s:%s' % (uid,
                                   self.index.resource._resourceID)).hexdigest())

    def reserveUID(self, uid):
        uid = uid.encode('utf-8')
        self.log_debug("Reserving UID %r @ %r" % (
                uid,
                self.index.resource))

        key = self._key(uid)
        if key in self.reservations:
            raise ReservationError(
                "UID %s already reserved for calendar collection %s."
                % (uid, self.index.resource._name)
                )
        self.reservations.add(key)
        return succeed(None)


    def unreserveUID(self, uid):
        uid = uid.encode('utf-8')
        self.log_debug("Unreserving UID %r @ %r" % (
                uid,
                self.index.resource))

        key = self._key(uid)
        if key in self.reservations:
            self.reservations.remove(key)
        return succeed(None)


    def isReservedUID(self, uid):
        uid = uid.encode('utf-8')
        self.log_debug("Is reserved UID %r @ %r" % (
                uid,
                self.index.resource))
        key = self._key(uid)
        return succeed(key in self.reservations)



class RealSQLBehaviorMixin(object):
    """
    Class attributes for 'real' SQL behavior; avoid idiosyncracies of SQLite,
    use standard SQL constructions, and depend on the full schema in
    sql_schema/current.sql rather than the partial one in twistedcaldav which depends
    on the placement of the database in the filesystem for some information.
    """

    ISOP = " = "
    STARTSWITHOP = ENDSWITHOP = CONTAINSOP = " LIKE "
    NOTSTARTSWITHOP = NOTENDSWITHOP = NOTCONTAINSOP = " NOT LIKE "

    def containsArgument(self, arg):
        return "%%%s%%" % (arg,)

    def startswithArgument(self, arg):
        return "%s%%" % (arg,)

    def endswithArgument(self, arg):
        return "%%%s" % (arg,)

class CalDAVSQLBehaviorMixin(RealSQLBehaviorMixin):
    """
    Query generator for CalDAV indexed searches.
    """

    FIELDS = {
        "TYPE": "CALENDAR_OBJECT.ICALENDAR_TYPE",
        "UID":  "CALENDAR_OBJECT.ICALENDAR_UID",
    }
    RESOURCEDB = "CALENDAR_OBJECT"
    TIMESPANDB = "TIME_RANGE"

    TIMESPANTEST = "((TIME_RANGE.FLOATING = FALSE AND TIME_RANGE.START_DATE < %s AND TIME_RANGE.END_DATE > %s) OR (TIME_RANGE.FLOATING = TRUE AND TIME_RANGE.START_DATE < %s AND TIME_RANGE.END_DATE > %s))"
    TIMESPANTEST_NOEND = "((TIME_RANGE.FLOATING = FALSE AND TIME_RANGE.END_DATE > %s) OR (TIME_RANGE.FLOATING = TRUE AND TIME_RANGE.END_DATE > %s))"
    TIMESPANTEST_NOSTART = "((TIME_RANGE.FLOATING = FALSE AND TIME_RANGE.START_DATE < %s) OR (TIME_RANGE.FLOATING = TRUE AND TIME_RANGE.START_DATE < %s))"
    TIMESPANTEST_TAIL_PIECE = " AND TIME_RANGE.CALENDAR_OBJECT_RESOURCE_ID = CALENDAR_OBJECT.RESOURCE_ID AND TIME_RANGE.CALENDAR_RESOURCE_ID = %s"
    TIMESPANTEST_JOIN_ON_PIECE = "TIME_RANGE.INSTANCE_ID = TRANSPARENCY.TIME_RANGE_INSTANCE_ID AND TRANSPARENCY.USER_ID = %s"

    def generate(self):
        """
        Generate the actual SQL 'where ...' expression from the passed in
        expression tree.

        @return: a C{tuple} of (C{str}, C{list}), where the C{str} is the
            partial SQL statement, and the C{list} is the list of argument
            substitutions to use with the SQL API execute method.
        """

        # Init state
        self.sout = StringIO.StringIO()
        self.arguments = []
        self.substitutions = []
        self.usedtimespan = False

        # For SQL data DB we need to restrict the query to just the targeted calendar resource-id if provided
        if self.calendarid:
            
            test = expression.isExpression("CALENDAR_OBJECT.CALENDAR_RESOURCE_ID", str(self.calendarid), True)

            # Since timerange expression already have the calendar resource-id test in them, do not
            # add the additional term to those. When the additional term is added, add it as the first
            # component in the AND expression to hopefully get the DB to use its index first

            # Top-level timerange expression already has calendar resource-id restriction in it
            if isinstance(self.expression, expression.timerangeExpression):
                pass
            
            # Top-level OR - check each component
            elif isinstance(self.expression, expression.orExpression):
                
                def _hasTopLevelTimerange(testexpr):
                    if isinstance(testexpr, expression.timerangeExpression):
                        return True
                    elif isinstance(testexpr, expression.andExpression):
                        return any([isinstance(expr, expression.timerangeExpression) for expr in testexpr.expressions])
                    else:
                        return False
                        
                hasTimerange = any([_hasTopLevelTimerange(expr) for expr in self.expression.expressions])

                if hasTimerange:
                    # timerange expression forces a join on calendarid
                    pass
                else:
                    # AND the whole thing with calendarid
                    self.expression = test.andWith(self.expression)    

            
            # Top-level AND - only add additional expression if timerange not present
            elif isinstance(self.expression, expression.andExpression):
                hasTimerange = any([isinstance(expr, expression.timerangeExpression) for expr in self.expression.expressions])
                if not hasTimerange:
                    # AND the whole thing
                    self.expression = test.andWith(self.expression)    
            
            # Just AND the entire thing
            else:
                self.expression = test.andWith(self.expression)

        # Generate ' where ...' partial statement
        self.generateExpression(self.expression)

        # Prefix with ' from ...' partial statement
        select = self.FROM + self.RESOURCEDB
        if self.usedtimespan:

            # Free busy needs transparency join            
            if self.freebusy:
                self.frontArgument(self.userid)
                select += ", %s LEFT OUTER JOIN %s ON (%s)" % (
                    self.TIMESPANDB,
                    self.TRANSPARENCYDB,
                    self.TIMESPANTEST_JOIN_ON_PIECE
                )
            else:
                select += ", %s" % (
                    self.TIMESPANDB,
                )
        select += self.WHERE
        if self.usedtimespan:
            select += "("
        select += self.sout.getvalue()
        if self.usedtimespan:
            if self.calendarid:
                self.setArgument(self.calendarid)
            select += ")%s" % (self.TIMESPANTEST_TAIL_PIECE,)

        select = select % tuple(self.substitutions)

        return select, self.arguments


class FormatParamStyleMixin(object):
    """
    Mixin for overriding methods on sqlgenerator that generate arguments
    according to format/pyformat rules rather than the base class's 'numeric'
    rules.
    """

    def addArgument(self, arg):
        self.arguments.append(arg)
        self.substitutions.append("%s")
        self.sout.write("%s")


    def setArgument(self, arg):
        self.arguments.append(arg)
        self.substitutions.append("%s")


    def frontArgument(self, arg):
        self.arguments.insert(0, arg)
        self.substitutions.insert(0, "%s")



class postgresqlgenerator(FormatParamStyleMixin, CalDAVSQLBehaviorMixin,
                          sqlgenerator):
    """
    Query generator for PostgreSQL indexed searches.
    """


def fixbools(sqltext):
    return sqltext.replace("TRUE", "1").replace("FALSE", "0")



class oraclesqlgenerator(CalDAVSQLBehaviorMixin, sqlgenerator):
    """
    Query generator for Oracle indexed searches.
    """
    TIMESPANTEST = fixbools(CalDAVSQLBehaviorMixin.TIMESPANTEST)
    TIMESPANTEST_NOEND = fixbools(CalDAVSQLBehaviorMixin.TIMESPANTEST_NOEND)
    TIMESPANTEST_NOSTART = fixbools(CalDAVSQLBehaviorMixin.TIMESPANTEST_NOSTART)
    TIMESPANTEST_TAIL_PIECE = fixbools(
        CalDAVSQLBehaviorMixin.TIMESPANTEST_TAIL_PIECE)
    TIMESPANTEST_JOIN_ON_PIECE = fixbools(
        CalDAVSQLBehaviorMixin.TIMESPANTEST_JOIN_ON_PIECE)



class LegacyIndexHelper(LoggingMixIn, object):

    @inlineCallbacks
    def isAllowedUID(self, uid, *names):
        """
        Checks to see whether to allow an operation which would add the
        specified UID to the index.  Specifically, the operation may not
        violate the constraint that UIDs must be unique.
        @param uid: the UID to check
        @param names: the names of resources being replaced or deleted by the
            operation; UIDs associated with these resources are not checked.
        @return: True if the UID is not in the index and is not reserved,
            False otherwise.
        """
        rname = yield self.resourceNameForUID(uid)
        returnValue(rname is None or rname in names)


    def reserveUID(self, uid):
        return self.reserver.reserveUID(uid)


    def unreserveUID(self, uid):
        return self.reserver.unreserveUID(uid)


    def isReservedUID(self, uid):
        return self.reserver.isReservedUID(uid)



class PostgresLegacyIndexEmulator(LegacyIndexHelper):
    """
    Emulator for L{twistedcaldv.index.Index} and
    L{twistedcaldv.index.IndexSchedule}.
    """

    def __init__(self, calendar):
        self.resource = self.calendar = calendar
        if (
            hasattr(config, "Memcached") and
            config.Memcached.Pools.Default.ClientEnabled
        ):
            self.reserver = MemcachedUIDReserver(self)
        else:
            # This is only used with unit tests
            self.reserver = DummyUIDReserver(self)

    _objectSchema = schema.CALENDAR_OBJECT

    @property
    def _txn(self):
        return self.calendar._txn


    @inlineCallbacks
    def isAllowedUID(self, uid, *names):
        """
        Checks to see whether to allow an operation which would add the
        specified UID to the index.  Specifically, the operation may not
        violate the constraint that UIDs must be unique.
        @param uid: the UID to check
        @param names: the names of resources being replaced or deleted by the
            operation; UIDs associated with these resources are not checked.
        @return: True if the UID is not in the index and is not reserved,
            False otherwise.
        """
        rname = yield self.resourceNameForUID(uid)
        returnValue(rname is None or rname in names)


    @inlineCallbacks
    def resourceUIDForName(self, name):
        uid = yield self.calendar.resourceUIDForName(name)
        returnValue(uid)


    @inlineCallbacks
    def resourceNameForUID(self, uid):
        name = yield self.calendar.resourceNameForUID(uid)
        returnValue(name)


    @classproperty
    def _notExpandedBeyondQuery(cls): #@NoSelf
        """
        DAL query to satisfy L{PostgresLegacyIndexEmulator.notExpandedBeyond}.
        """
        co = schema.CALENDAR_OBJECT
        return Select([co.RESOURCE_NAME], From=co,
                      Where=(co.RECURRANCE_MAX < Parameter("minDate"))
                      .And(co.CALENDAR_RESOURCE_ID == Parameter("resourceID")))


    @inlineCallbacks
    def notExpandedBeyond(self, minDate):
        """
        Gives all resources which have not been expanded beyond a given date
        in the database.  (Unused; see above L{postgresqlgenerator}.
        """
        returnValue([row[0] for row in (
            yield self._notExpandedBeyondQuery.on(
                self._txn, minDate=pyCalendarTodatetime(normalizeForIndex(minDate)),
                resourceID=self.calendar._resourceID))]
        )


    @inlineCallbacks
    def reExpandResource(self, name, expand_until):
        """
        Given a resource name, remove it from the database and re-add it
        with a longer expansion.
        """
        obj = yield self.calendar.calendarObjectWithName(name)
        yield obj.updateDatabase(
            (yield obj.component()), expand_until=expand_until, reCreate=True
        )


    @inlineCallbacks
    def testAndUpdateIndex(self, minDate):
        # Find out if the index is expanded far enough
        names = yield self.notExpandedBeyond(minDate)

        # Actually expand recurrence max
        for name in names:
            self.log_info("Search falls outside range of index for %s %s" %
                          (name, minDate))
            yield self.reExpandResource(name, minDate)


    @inlineCallbacks
    def indexedSearch(self, filter, useruid='', fbtype=False):
        """
        Finds resources matching the given qualifiers.

        @param filter: the L{Filter} for the calendar-query to execute.

        @return: a L{Deferred} which fires with an iterable of tuples for each
            resource matching the given C{qualifiers}. The tuples are C{(name,
            uid, type)}, where C{name} is the resource name, C{uid} is the
            resource UID, and C{type} is the resource iCalendar component type.
        """
        # Detect which style of parameter-generation we're using.  Naming is a
        # little off here, because the reason we're using the numeric one is
        # that it happens to be used by the oracle binding that we're using,
        # whereas the postgres binding happens to use the 'pyformat' (e.g. %s)
        # parameter style.
        if self.calendar._txn.paramstyle == 'numeric':
            generator = oraclesqlgenerator
        else:
            generator = postgresqlgenerator
        # Make sure we have a proper Filter element and get the partial SQL
        # statement to use.
        if isinstance(filter, calendarqueryfilter.Filter):
            qualifiers = calendarquery.sqlcalendarquery(
                filter, self.calendar._resourceID, useruid, fbtype,
                generator=generator
            )
            if qualifiers is not None:
                # Determine how far we need to extend the current expansion of
                # events. If we have an open-ended time-range we will expand
                # one year past the start. That should catch bounded
                # recurrences - unbounded will have been indexed with an
                # "infinite" value always included.
                maxDate, isStartDate = filter.getmaxtimerange()
                if maxDate:
                    maxDate = maxDate.duplicate()
                    maxDate.setDateOnly(True)
                    if isStartDate:
                        maxDate += PyCalendarDuration(days=365)
                    yield self.testAndUpdateIndex(maxDate)
            else:
                # We cannot handler this filter in an indexed search
                raise IndexedSearchException()
        else:
            qualifiers = None

        # Perform the search
        if qualifiers is None:
            rowiter = yield self.bruteForceSearch()
        else:
            if fbtype:
                # For a free-busy time-range query we return all instances
                rowiter = yield self._txn.execSQL(
                    """
                    select DISTINCT
                        CALENDAR_OBJECT.RESOURCE_NAME,
                        CALENDAR_OBJECT.ICALENDAR_UID,
                        CALENDAR_OBJECT.ICALENDAR_TYPE,
                        CALENDAR_OBJECT.ORGANIZER,
                        TIME_RANGE.FLOATING, TIME_RANGE.START_DATE,
                        TIME_RANGE.END_DATE, TIME_RANGE.FBTYPE,
                        TIME_RANGE.TRANSPARENT, TRANSPARENCY.TRANSPARENT
                    """ +
                    qualifiers[0],
                    qualifiers[1]
                )
            else:
                rowiter = yield self._txn.execSQL(
                    """
                    select
                        DISTINCT CALENDAR_OBJECT.RESOURCE_NAME,
                        CALENDAR_OBJECT.ICALENDAR_UID,
                        CALENDAR_OBJECT.ICALENDAR_TYPE
                    """ +
                    qualifiers[0],
                    qualifiers[1]
                )

        # Check result for missing resources

        results = []
        for row in rowiter:
            if fbtype:
                row = list(row)
                row[4] = 'Y' if row[4] else 'N'
                row[7] = indexfbtype_to_icalfbtype[row[7]]
                if row[9] is not None:
                    row[8] = row[9]
                row[8] = 'T' if row[8] else 'F'
                del row[9]
            results.append(row)
        returnValue(results)


    @classproperty
    def _bruteForceQuery(cls): #@NoSelf
        """
        DAL query for all C{CALENDAR_OBJECT} rows in the calendar represented by
        this index.
        """
        obj = cls._objectSchema
        return Select(
            [obj.RESOURCE_NAME, obj.ICALENDAR_UID, obj.ICALENDAR_TYPE],
            From=obj, Where=obj.PARENT_RESOURCE_ID == Parameter("resourceID")
        )


    def bruteForceSearch(self):
        return self._bruteForceQuery.on(
            self._txn, resourceID=self.resource._resourceID)


    @inlineCallbacks
    def resourcesExist(self, names):
        returnValue(list(set(names).intersection(
            set((yield self.calendar.listCalendarObjects())))))


    @classproperty
    def _resourceExistsQuery(cls): #@NoSelf
        """
        DAL query to determine whether a calendar object exists in the
        collection represented by this index.
        """
        obj = cls._objectSchema
        return Select(
            [obj.RESOURCE_NAME], From=obj,
            Where=(obj.RESOURCE_NAME == Parameter("name"))
            .And(obj.PARENT_RESOURCE_ID == Parameter("resourceID"))
        )


    @inlineCallbacks
    def resourceExists(self, name):
        returnValue((bool(
            (yield self._resourceExistsQuery.on(
                self._txn, name=name, resourceID=self.resource._resourceID))
        )))



class PostgresLegacyInboxIndexEmulator(PostgresLegacyIndexEmulator):
    """
    UIDs need not be unique in the 'inbox' calendar, so override those
    behaviors intended to ensure that.
    """

    def isAllowedUID(self):
        return succeed(True)

    def reserveUID(self, uid):
        return succeed(None)

    def unreserveUID(self, uid):
        return succeed(None)

    def isReservedUID(self, uid):
        return succeed(False)



# CARDDAV

class CardDAVSQLBehaviorMixin(RealSQLBehaviorMixin):
    """
    Query generator for CardDAV indexed searches.
    """

    FIELDS = {
        "UID":  "ADDRESSBOOK_OBJECT.VCARD_UID",
    }
    RESOURCEDB = "ADDRESSBOOK_OBJECT"

    def generate(self):
        """
        Generate the actual SQL 'where ...' expression from the passed in
        expression tree.

        @return: a C{tuple} of (C{str}, C{list}), where the C{str} is the
            partial SQL statement, and the C{list} is the list of argument
            substitutions to use with the SQL API execute method.
        """

        # Init state
        self.sout = StringIO.StringIO()
        self.arguments = []
        self.substitutions = []

        # For SQL data DB we need to restrict the query to just the targeted calendar resource-id if provided
        if self.calendarid:
            
            # AND the whole thing
            test = expression.isExpression("ADDRESSBOOK_OBJECT.ADDRESSBOOK_RESOURCE_ID", str(self.calendarid), True)
            self.expression = test.andWith(self.expression)    

        # Generate ' where ...' partial statement
        self.sout.write(self.WHERE)
        self.generateExpression(self.expression)

        # Prefix with ' from ...' partial statement
        select = self.FROM + self.RESOURCEDB
        select += self.sout.getvalue()

        select = select % tuple(self.substitutions)

        return select, self.arguments



class postgresqladbkgenerator(FormatParamStyleMixin, CardDAVSQLBehaviorMixin, sqlgenerator):
    """
    Query generator for PostgreSQL indexed searches.
    """

class oraclesqladbkgenerator(CardDAVSQLBehaviorMixin, sqlgenerator):
    """
    Query generator for Oracle indexed searches.
    """



class PostgresLegacyABIndexEmulator(LegacyIndexHelper):
    """
    Emulator for L{twistedcaldv.index.Index} and
    L{twistedcaldv.index.IndexSchedule}.
    """

    _objectSchema = schema.ADDRESSBOOK_OBJECT

    def __init__(self, addressbook):
        self.resource = self.addressbook = addressbook
        if (
            hasattr(config, "Memcached") and
            config.Memcached.Pools.Default.ClientEnabled
        ):
            self.reserver = MemcachedUIDReserver(self)
        else:
            # This is only used with unit tests
            self.reserver = DummyUIDReserver(self)


    @property
    def _txn(self):
        return self.addressbook._txn


    @inlineCallbacks
    def resourceUIDForName(self, name):
        obj = yield self.addressbook.addressbookObjectWithName(name)
        if obj is None:
            returnValue(None)
        returnValue(obj.uid())


    @inlineCallbacks
    def resourceNameForUID(self, uid):
        obj = yield self.addressbook.addressbookObjectWithUID(uid)
        if obj is None:
            returnValue(None)
        returnValue(obj.name())


    def searchValid(self, filter):
        if isinstance(filter, addressbookqueryfilter.Filter):
            qualifiers = addressbookquery.sqladdressbookquery(filter)
        else:
            qualifiers = None

        return qualifiers is not None


    @inlineCallbacks
    def search(self, filter):
        """
        Finds resources matching the given qualifiers.
        @param filter: the L{Filter} for the addressbook-query to execute.
        @return: an iterable of tuples for each resource matching the
            given C{qualifiers}. The tuples are C{(name, uid, type)}, where
            C{name} is the resource name, C{uid} is the resource UID, and
            C{type} is the resource iCalendar component type.x
        """
        if self.addressbook._txn.paramstyle == 'numeric':
            generator = oraclesqladbkgenerator
        else:
            generator = postgresqladbkgenerator
        # Make sure we have a proper Filter element and get the partial SQL statement to use.
        if isinstance(filter, addressbookqueryfilter.Filter):
            qualifiers = addressbookquery.sqladdressbookquery(
                filter, self.addressbook._resourceID, generator=generator)
        else:
            qualifiers = None
        if qualifiers is not None:
            rowiter = yield self._txn.execSQL(
                "select DISTINCT ADDRESSBOOK_OBJECT.RESOURCE_NAME, ADDRESSBOOK_OBJECT.VCARD_UID" +
                qualifiers[0],
                qualifiers[1]
            )
        else:
            rowiter = yield Select(
                [self._objectSchema.RESOURCE_NAME,
                 self._objectSchema.VCARD_UID],
                From=self._objectSchema,
                Where=self._objectSchema.ADDRESSBOOK_RESOURCE_ID ==
                self.addressbook._resourceID
            ).on(self.addressbook._txn)

        returnValue(list(rowiter))


    def indexedSearch(self, filter, useruid='', fbtype=False):
        """
        Always raise L{IndexedSearchException}, since these indexes are not
        fully implemented yet.
        """
        raise IndexedSearchException()


    @inlineCallbacks
    def resourcesExist(self, names):
        returnValue(list(set(names).intersection(
            set((yield self.addressbook.listAddressbookObjects())))))

