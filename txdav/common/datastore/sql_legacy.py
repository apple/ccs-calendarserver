# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
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

import datetime
import StringIO

from twistedcaldav.sharing import SharedCollectionRecord

from twisted.python import hashlib
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twext.python.log import Logger, LoggingMixIn

from twistedcaldav import carddavxml
from twistedcaldav.config import config
from twistedcaldav.dateops import normalizeForIndex
from twistedcaldav.memcachepool import CachePoolUserMixIn
from twistedcaldav.notifications import NotificationRecord
from twistedcaldav.query import calendarqueryfilter, calendarquery, \
    addressbookquery
from twistedcaldav.query.sqlgenerator import sqlgenerator
from twistedcaldav.sharing import Invite

from txdav.common.icommondatastore import IndexedSearchException, \
    ReservationError
from txdav.common.datastore.sql_tables import \
    _BIND_MODE_OWN, _BIND_MODE_READ, _BIND_MODE_WRITE, _BIND_MODE_DIRECT, \
    _BIND_STATUS_INVITED, _BIND_STATUS_ACCEPTED, _BIND_STATUS_DECLINED, _BIND_STATUS_INVALID, \
    CALENDAR_BIND_TABLE, CALENDAR_HOME_TABLE, ADDRESSBOOK_HOME_TABLE, \
    ADDRESSBOOK_BIND_TABLE

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
                    (yield notificationObject._fieldQuery("XML_TYPE"))
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


    @inlineCallbacks
    def allRecords(self):
        values = []
        for row in (yield self._txn.execSQL(
            """
            select
                INVITE.INVITE_UID,
                INVITE.NAME,
                INVITE.RECIPIENT_ADDRESS,
                %(HOME:name)s.%(HOME:column_OWNER_UID)s,
                %(BIND:name)s.%(BIND:column_BIND_MODE)s,
                %(BIND:name)s.%(BIND:column_BIND_STATUS)s,
                %(BIND:name)s.%(BIND:column_MESSAGE)s
            from
                INVITE, %(HOME:name)s, %(BIND:name)s
            where
                INVITE.RESOURCE_ID = %%s
                and INVITE.HOME_RESOURCE_ID = %(HOME:name)s.%(HOME:column_RESOURCE_ID)s
                and %(BIND:name)s.%(BIND:column_RESOURCE_ID)s = INVITE.RESOURCE_ID
                and %(BIND:name)s.%(BIND:column_HOME_RESOURCE_ID)s = INVITE.HOME_RESOURCE_ID
            order by
                INVITE.NAME asc
            """ % self._combinedTable,
            [self._collection._resourceID]
        )):
            values.append(self._makeInvite(row))
        returnValue(values)


    @inlineCallbacks
    def recordForUserID(self, userid):
        rows = yield self._txn.execSQL(
            """
            select
                INVITE.INVITE_UID,
                INVITE.NAME,
                INVITE.RECIPIENT_ADDRESS,
                %(HOME:name)s.%(HOME:column_OWNER_UID)s,
                %(BIND:name)s.%(BIND:column_BIND_MODE)s,
                %(BIND:name)s.%(BIND:column_BIND_STATUS)s,
                %(BIND:name)s.%(BIND:column_MESSAGE)s
            from
                INVITE, %(HOME:name)s, %(BIND:name)s
            where INVITE.RECIPIENT_ADDRESS = %%s
             and INVITE.HOME_RESOURCE_ID = %(HOME:name)s.%(HOME:column_RESOURCE_ID)s
             and %(BIND:name)s.%(BIND:column_RESOURCE_ID)s = INVITE.RESOURCE_ID
             and %(BIND:name)s.%(BIND:column_HOME_RESOURCE_ID)s = INVITE.HOME_RESOURCE_ID
            """ % self._combinedTable,
            [userid]
        )
        returnValue(self._makeInvite(rows[0]) if rows else None)


    @inlineCallbacks
    def recordForPrincipalURL(self, principalURL):
        for record in (yield self.allRecords()):
            if record.principalURL == principalURL:
                returnValue(record)


    @inlineCallbacks
    def recordForInviteUID(self, inviteUID):
        rows = yield self._txn.execSQL(
            """
            select
                INVITE.INVITE_UID,
                INVITE.NAME,
                INVITE.RECIPIENT_ADDRESS,
                %(HOME:name)s.%(HOME:column_OWNER_UID)s,
                %(BIND:name)s.%(BIND:column_BIND_MODE)s,
                %(BIND:name)s.%(BIND:column_BIND_STATUS)s,
                %(BIND:name)s.%(BIND:column_MESSAGE)s
            from
                INVITE, %(HOME:name)s, %(BIND:name)s
            where INVITE.INVITE_UID = %%s
             and INVITE.HOME_RESOURCE_ID = %(HOME:name)s.%(HOME:column_RESOURCE_ID)s
             and %(BIND:name)s.%(BIND:column_RESOURCE_ID)s = INVITE.RESOURCE_ID
             and %(BIND:name)s.%(BIND:column_HOME_RESOURCE_ID)s = INVITE.HOME_RESOURCE_ID
            """ % self._combinedTable,
            [inviteUID]
        )
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
        principalURL = "/principals/__uids__/%s/" % (ownerUID,)
        return Invite(
            inviteuid, userid, principalURL, common_name,
            access, state, summary
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
        # principalURL is derived from a directory record's principalURL() so
        # it will always contain the UID.  The form is '/principals/__uids__/x'
        # (and may contain a trailing slash).
        principalUID = record.principalURL.split("/")[3]
        shareeHome = yield self._getHomeWithUID(principalUID)
        rows = yield self._txn.execSQL(
            "select RESOURCE_ID, HOME_RESOURCE_ID from INVITE where RECIPIENT_ADDRESS = %s",
            [record.userid]
        )
        if rows:
            [[resourceID, homeResourceID]] = rows
            # Invite(inviteuid, userid, principalURL, common_name, access, state, summary)
            yield self._txn.execSQL(
                """
                update %(BIND:name)s
                set %(BIND:column_BIND_MODE)s = %%s,
                    %(BIND:column_BIND_STATUS)s = %%s,
                    %(BIND:column_MESSAGE)s = %%s
                where %(BIND:column_RESOURCE_ID)s = %%s
                 and %(BIND:column_HOME_RESOURCE_ID)s = %%s
                """ % self._combinedTable,
                [bindMode, bindStatus, record.summary, resourceID, homeResourceID]
            )
            yield self._txn.execSQL("""
                update INVITE
                set NAME = %s, INVITE_UID = %s
                where RECIPIENT_ADDRESS = %s
                """,
                [record.name, record.inviteuid, record.userid]
            )
        else:
            yield self._txn.execSQL(
                """
                insert into INVITE
                (
                    INVITE_UID, NAME,
                    HOME_RESOURCE_ID, RESOURCE_ID,
                    RECIPIENT_ADDRESS
                )
                values (%s, %s, %s, %s, %s)
                """,
                [
                    record.inviteuid, record.name,
                    shareeHome._resourceID, self._collection._resourceID,
                    record.userid
                ])
            yield self._txn.execSQL(
                """
                insert into %(BIND:name)s
                (
                    %(BIND:column_HOME_RESOURCE_ID)s,
                    %(BIND:column_RESOURCE_ID)s, 
                    %(BIND:column_RESOURCE_NAME)s,
                    %(BIND:column_BIND_MODE)s,
                    %(BIND:column_BIND_STATUS)s,
                    %(BIND:column_SEEN_BY_OWNER)s,
                    %(BIND:column_SEEN_BY_SHAREE)s,
                    %(BIND:column_MESSAGE)s
                )
                values (%%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s)
                """ % self._combinedTable,
                [
                    shareeHome._resourceID,
                    self._collection._resourceID,
                    None, # this is NULL because it is not bound yet, let's be
                          # explicit about that.
                    bindMode,
                    bindStatus,
                    False,
                    False,
                    record.summary
                ]
            )


    @inlineCallbacks
    def removeRecordForUserID(self, userid):
        yield self._txn.execSQL(
            """
            delete from %(BIND:name)s using INVITE
            where INVITE.RECIPIENT_ADDRESS = %%s
             and %(BIND:name)s.%(BIND:column_HOME_RESOURCE_ID)s = INVITE.HOME_RESOURCE_ID
             and %(BIND:name)s.%(BIND:column_RESOURCE_ID)s = INVITE.RESOURCE_ID
            """ % self._combinedTable,
            [userid]
        )
        yield self._txn.execSQL(
            "delete from INVITE where RECIPIENT_ADDRESS = %s",
            [userid]
        )


    @inlineCallbacks
    def removeRecordForInviteUID(self, inviteUID):
        yield self._txn.execSQL(
            """
            delete from %(BIND:name)s using INVITE
            where INVITE.INVITE_UID = %s
             and %(BIND:name)s.%(BIND:column_HOME_RESOURCE_ID)s = INVITE.HOME_RESOURCE_ID
             and %(BIND:name)s.%(BIND:column_RESOURCE_ID)s = INVITE.RESOURCE_ID
            """ % self._combinedTable,
            [inviteUID]
        )
        yield self._txn.execSQL(
            "delete from INVITE where INVITE_UID = %s",
            [inviteUID]
        )



class SQLLegacyCalendarInvites(SQLLegacyInvites):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    def __init__(self, calendar):
        self._homeTable = CALENDAR_HOME_TABLE
        self._bindTable = CALENDAR_BIND_TABLE
        super(SQLLegacyCalendarInvites, self).__init__(calendar)


    def _getHomeWithUID(self, uid):
        return self._txn.calendarHomeWithUID(uid, create=True)



class SQLLegacyAddressBookInvites(SQLLegacyInvites):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    def __init__(self, addressbook):
        self._homeTable = ADDRESSBOOK_HOME_TABLE
        self._bindTable = ADDRESSBOOK_BIND_TABLE
        super(SQLLegacyAddressBookInvites, self).__init__(addressbook)


    def _getHomeWithUID(self, uid):
        return self._txn.addressbookHomeWithUID(uid, create=True)



class SQLLegacyShares(object):

    _homeTable = None
    _bindTable = None
    _urlTopSegment = None

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


    @inlineCallbacks
    def allRecords(self):
        # This should have been a smart join that got all these columns at
        # once, but let's not bother to fix it, since the actual query we
        # _want_ to do (just look for binds in a particular homes) is
        # much simpler anyway; we should just do that.
        all = []
        shareRows = yield self._txn.execSQL(
            """
            select %(column_RESOURCE_ID)s, %(column_RESOURCE_NAME)s, %(column_BIND_MODE)s, %(column_MESSAGE)s
            from %(name)s
            where %(column_HOME_RESOURCE_ID)s = %%s
             and %(column_BIND_MODE)s != %%s
             and %(column_RESOURCE_NAME)s is not null
            """ % self._bindTable,
            [self._home._resourceID, _BIND_MODE_OWN]
        )
        for resourceID, resourceName, bindMode, summary in shareRows:
            if bindMode != _BIND_MODE_DIRECT:
                [[shareuid]] = yield self._txn.execSQL(
                    """
                    select INVITE_UID
                    from INVITE
                    where RESOURCE_ID = %s and HOME_RESOURCE_ID = %s
                    """,
                    [resourceID, self._home._resourceID]
                )
                sharetype = 'I'
                [[ownerHomeID, ownerResourceName]] = yield self._txn.execSQL(
                    """
                    select %(column_HOME_RESOURCE_ID)s, %(column_RESOURCE_NAME)s
                    from %(name)s
                    where %(column_RESOURCE_ID)s = %%s
                     and %(column_BIND_MODE)s = %%s
                    """ % self._bindTable,
                    [resourceID, _BIND_MODE_OWN]
                )
                [[ownerUID]] = yield self._txn.execSQL(
                    """
                    select %(column_OWNER_UID)s from %(name)s
                    where %(column_RESOURCE_ID)s = %%s
                    """ % self._homeTable,
                    [ownerHomeID]
                )
                hosturl = '/%s/__uids__/%s/%s' % (
                    self._urlTopSegment, ownerUID, ownerResourceName
                )
                localname = resourceName
                record = SharedCollectionRecord(
                    shareuid, sharetype, hosturl, localname, summary
                )
                all.append(record)
            else:
                sharetype = 'D'
                [[ownerHomeID, ownerResourceName]] = yield self._txn.execSQL(
                    """
                    select %(column_HOME_RESOURCE_ID)s, %(column_RESOURCE_NAME)s
                    from %(name)s
                    where %(column_RESOURCE_ID)s = %%s
                     and %(column_BIND_MODE)s = %%s
                    """ % self._bindTable,
                    [resourceID, _BIND_MODE_OWN]
                )
                [[ownerUID]] = yield self._txn.execSQL(
                    """
                    select %(column_OWNER_UID)s from %(name)s
                    where %(column_RESOURCE_ID)s = %%s
                    """ % self._homeTable,
                    [ownerHomeID]
                )
                hosturl = '/%s/__uids__/%s/%s' % (
                    self._urlTopSegment, ownerUID, ownerResourceName
                )
                localname = resourceName
                synthesisedUID = "Direct-%s-%s" % (self._home._resourceID, resourceID,)
                record = SharedCollectionRecord(
                    synthesisedUID, sharetype, hosturl, localname, summary
                )
                all.append(record)
        returnValue(all)


    @inlineCallbacks
    def _search(self, **kw):
        [[key, value]] = kw.items()
        for record in (yield self.allRecords()):
            if getattr(record, key) == value:
                returnValue((record))


    def recordForShareUID(self, shareUID):
        return self._search(shareuid=shareUID)


    @inlineCallbacks
    def addOrUpdateRecord(self, record):
        # record.hosturl -> /.../__uids__/<uid>/<name>
        splithost = record.hosturl.split('/')
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

            yield self._txn.execSQL(
                """
                update %(name)s
                set %(column_RESOURCE_NAME)s = %%s
                where %(column_HOME_RESOURCE_ID)s = %%s
                 and %(column_RESOURCE_ID)s = %%s
                """ % self._bindTable,
                [record.localname, self._home._resourceID, collectionResourceID]
            )
        elif record.sharetype == 'D':
            # There is no bind entry already so add one.

            yield self._txn.execSQL(
                """
                insert into %(name)s
                (
                    %(column_HOME_RESOURCE_ID)s,
                    %(column_RESOURCE_ID)s, 
                    %(column_RESOURCE_NAME)s,
                    %(column_BIND_MODE)s,
                    %(column_BIND_STATUS)s,
                    %(column_SEEN_BY_OWNER)s,
                    %(column_SEEN_BY_SHAREE)s,
                    %(column_MESSAGE)s
                )
                values (%%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s)
                """ % self._bindTable,
                [
                    self._home._resourceID,
                    collectionResourceID,
                    record.localname,
                    _BIND_MODE_DIRECT,
                    _BIND_STATUS_ACCEPTED,
                    True,
                    True,
                    record.summary,
                ])

        shareeCollection = yield self._home.sharedChildWithName(record.localname)
        shareeCollection._initSyncToken()


    @inlineCallbacks
    def removeRecordForLocalName(self, localname):
        record = yield self.recordForLocalName(localname)
        shareeCollection = yield self._home.sharedChildWithName(record.localname)
        yield shareeCollection._deletedSyncToken()

        returnValue((yield self._txn.execSQL(
            """
            update %(name)s
            set %(column_RESOURCE_NAME)s = NULL
            where %(column_RESOURCE_NAME)s = %%s
             and %(column_HOME_RESOURCE_ID)s = %%s
            """ % self._bindTable,
            [localname, self._home._resourceID]
        )))


    @inlineCallbacks
    def removeRecordForShareUID(self, shareUID):

        record = yield self.recordForShareUID(shareUID)
        shareeCollection = yield self._home.sharedChildWithName(record.localname)
        yield shareeCollection._deletedSyncToken()

        if not shareUID.startswith("Direct"):
            yield self._txn.execSQL(
                """
                update %(name)s
                set %(column_RESOURCE_NAME)s = NULL
                from INVITE
                where INVITE.INVITE_UID = %%s
                 and %(name)s.%(column_HOME_RESOURCE_ID)s = INVITE.HOME_RESOURCE_ID
                 and %(name)s.%(column_RESOURCE_ID)s = INVITE.RESOURCE_ID
                """ % self._bindTable,
                [shareUID, ]
            )
        else:
            # Extract pieces from synthesised UID
            homeID, resourceID = shareUID[len("Direct-"):].split("-")

            # Now remove the binding for the direct share
            yield self._txn.execSQL(
                """
                delete from %(name)s
                where %(column_HOME_RESOURCE_ID)s = %%s
                 and %(column_RESOURCE_ID)s = %%s
                """ % self._bindTable,
                [homeID, resourceID, ]
            )



class SQLLegacyCalendarShares(SQLLegacyShares):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    def __init__(self, home):
        self._homeTable = CALENDAR_HOME_TABLE
        self._bindTable = CALENDAR_BIND_TABLE
        self._urlTopSegment = "calendars"

        super(SQLLegacyCalendarShares, self).__init__(home)


    def _getHomeWithUID(self, uid):
        return self._txn.calendarHomeWithUID(uid, create=True)



class SQLLegacyAddressBookShares(SQLLegacyShares):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """

    def __init__(self, home):
        self._homeTable = ADDRESSBOOK_HOME_TABLE
        self._bindTable = ADDRESSBOOK_BIND_TABLE
        self._urlTopSegment = "addressbooks"

        super(SQLLegacyAddressBookShares, self).__init__(home)

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

class postgresqlgenerator(sqlgenerator):
    """
    Query generator for postgreSQL indexed searches.  (Currently unused: work
    in progress.)
    """

    ISOP = " = "
    CONTAINSOP = " LIKE "
    NOTCONTAINSOP = " NOT LIKE "
    FIELDS = {
        "TYPE": "CALENDAR_OBJECT.ICALENDAR_TYPE",
        "UID":  "CALENDAR_OBJECT.ICALENDAR_UID",
    }

    def __init__(self, expr, calendarid, userid):
        self.RESOURCEDB = "CALENDAR_OBJECT"
        self.TIMESPANDB = "TIME_RANGE"
        self.TIMESPANTEST = "((TIME_RANGE.FLOATING = FALSE AND TIME_RANGE.START_DATE < %s AND TIME_RANGE.END_DATE > %s) OR (TIME_RANGE.FLOATING = TRUE AND TIME_RANGE.START_DATE < %s AND TIME_RANGE.END_DATE > %s))"
        self.TIMESPANTEST_NOEND = "((TIME_RANGE.FLOATING = FALSE AND TIME_RANGE.END_DATE > %s) OR (TIME_RANGE.FLOATING = TRUE AND TIME_RANGE.END_DATE > %s))"
        self.TIMESPANTEST_NOSTART = "((TIME_RANGE.FLOATING = FALSE AND TIME_RANGE.START_DATE < %s) OR (TIME_RANGE.FLOATING = TRUE AND TIME_RANGE.START_DATE < %s))"
        self.TIMESPANTEST_TAIL_PIECE = " AND TIME_RANGE.CALENDAR_OBJECT_RESOURCE_ID = CALENDAR_OBJECT.RESOURCE_ID AND CALENDAR_OBJECT.CALENDAR_RESOURCE_ID = %s"
        self.TIMESPANTEST_JOIN_ON_PIECE = "TIME_RANGE.INSTANCE_ID = TRANSPARENCY.TIME_RANGE_INSTANCE_ID AND TRANSPARENCY.USER_ID = %s"

        super(postgresqlgenerator, self).__init__(expr, calendarid, userid)


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

        # Generate ' where ...' partial statement
        self.sout.write(self.WHERE)
        self.generateExpression(self.expression)

        # Prefix with ' from ...' partial statement
        select = self.FROM + self.RESOURCEDB
        if self.usedtimespan:
            self.frontArgument(self.userid)
            select += ", %s LEFT OUTER JOIN %s ON (%s)" % (
                self.TIMESPANDB,
                self.TRANSPARENCYDB,
                self.TIMESPANTEST_JOIN_ON_PIECE
            )
        select += self.sout.getvalue()

        select = select % tuple(self.substitutions)

        return select, self.arguments


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

    def containsArgument(self, arg):
        return "%%%s%%" % (arg,)


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
        obj = yield self.calendar.calendarObjectWithName(name)
        if obj is None:
            returnValue(None)
        returnValue(obj.uid())


    @inlineCallbacks
    def resourceNameForUID(self, uid):
        obj = yield self.calendar.calendarObjectWithUID(uid)
        if obj is None:
            returnValue(None)
        returnValue(obj.name())


    @inlineCallbacks
    def notExpandedBeyond(self, minDate):
        """
        Gives all resources which have not been expanded beyond a given date
        in the database.  (Unused; see above L{postgresqlgenerator}.
        """
        returnValue([row[0] for row in (yield self._txn.execSQL(
            "select RESOURCE_NAME from CALENDAR_OBJECT "
            "where RECURRANCE_MAX < %s and CALENDAR_RESOURCE_ID = %s",
            [normalizeForIndex(minDate), self.calendar._resourceID]
        ))])


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
            self.log_info("Search falls outside range of index for %s %s" % (name, minDate))
            yield self.reExpandResource(name, minDate)


    @inlineCallbacks
    def indexedSearch(self, filter, useruid='', fbtype=False):
        """
        Finds resources matching the given qualifiers.
        @param filter: the L{Filter} for the calendar-query to execute.

        @return: a L{Deferred} which fires with an iterable of tuples for each
            resource matching the given C{qualifiers}. The tuples are C{(name,
            uid, type)}, where C{name} is the resource name, C{uid} is the
            resource UID, and C{type} is the resource iCalendar component
            type.
        """
        # Make sure we have a proper Filter element and get the partial SQL
        # statement to use.
        if isinstance(filter, calendarqueryfilter.Filter):
            qualifiers = calendarquery.sqlcalendarquery(
                filter, self.calendar._resourceID, useruid,
                generator=postgresqlgenerator
            )
            if qualifiers is not None:
                # Determine how far we need to extend the current expansion of
                # events. If we have an open-ended time-range we will expand
                # one year past the start. That should catch bounded
                # recurrences - unbounded will have been indexed with an
                # "infinite" value always included.
                maxDate, isStartDate = filter.getmaxtimerange()
                if maxDate:
                    maxDate = maxDate.date()
                    if isStartDate:
                        maxDate += datetime.timedelta(days=365)
                    yield self.testAndUpdateIndex(maxDate)
            else:
                # We cannot handler this filter in an indexed search
                raise IndexedSearchException()
        else:
            qualifiers = None

        # Perform the search
        if qualifiers is None:
            rowiter = yield self._txn.execSQL(
                """
                select RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE
                from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = %s
                """,
                [self.calendar._resourceID],
            )
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
                row[8] = 'T' if row[9] else 'F'
                del row[9]
            results.append(row)
        returnValue(results)


    def bruteForceSearch(self):
        return self._txn.execSQL(
            "select RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE from "
            "CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = %s",
            [self.calendar._resourceID]
        )


    @inlineCallbacks
    def resourcesExist(self, names):
        returnValue(list(set(names).intersection(
            set((yield self.calendar.listCalendarObjects())))))


    @inlineCallbacks
    def resourceExists(self, name):
        returnValue((bool(
            (yield self._txn.execSQL(
                "select RESOURCE_NAME from CALENDAR_OBJECT where "
                "RESOURCE_NAME = %s and CALENDAR_RESOURCE_ID = %s",
                [name, self.calendar._resourceID]
            ))
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

class postgresqladbkgenerator(sqlgenerator):
    """
    Query generator for postgreSQL indexed searches.  (Currently unused: work
    in progress.)
    """

    ISOP = " = "
    CONTAINSOP = " LIKE "
    NOTCONTAINSOP = " NOT LIKE "
    FIELDS = {
        "UID":  "ADDRESSBOOK_OBJECT.VCARD_UID",
    }

    def __init__(self, expr, addressbookid):
        self.RESOURCEDB = "ADDRESSBOOK_OBJECT"

        super(postgresqladbkgenerator, self).__init__(expr, addressbookid)


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

        # Generate ' where ...' partial statement
        self.sout.write(self.WHERE)
        self.generateExpression(self.expression)

        # Prefix with ' from ...' partial statement
        select = self.FROM + self.RESOURCEDB
        select += self.sout.getvalue()

        select = select % tuple(self.substitutions)

        return select, self.arguments


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

    def containsArgument(self, arg):
        return "%%%s%%" % (arg,)


class PostgresLegacyABIndexEmulator(LegacyIndexHelper):
    """
    Emulator for L{twistedcaldv.index.Index} and
    L{twistedcaldv.index.IndexSchedule}.
    """

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
        if isinstance(filter, carddavxml.Filter):
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

        # Make sure we have a proper Filter element and get the partial SQL statement to use.
        if isinstance(filter, carddavxml.Filter):
            qualifiers = addressbookquery.sqladdressbookquery(filter, self.addressbook._resourceID, generator=postgresqladbkgenerator)
        else:
            qualifiers = None
        if qualifiers is not None:
            rowiter = yield self._txn.execSQL(
                "select DISTINCT ADDRESSBOOK_OBJECT.RESOURCE_NAME, ADDRESSBOOK_OBJECT.VCARD_UID" +
                qualifiers[0],
                qualifiers[1]
            )
        else:
            rowiter = yield self._txn.execSQL(
                "select RESOURCE_NAME, VCARD_UID from ADDRESSBOOK_OBJECT where ADDRESSBOOK_RESOURCE_ID = %s",
                [self.addressbook._resourceID, ],
            )

        returnValue(list(rowiter))


    def indexedSearch(self, filter, useruid='', fbtype=False):
        """
        Always raise L{IndexedSearchException}, since these indexes are not
        fully implemented yet.
        """
        raise IndexedSearchException()


    def bruteForceSearch(self):
        return self._txn.execSQL(
            "select RESOURCE_NAME, VCARD_UID from "
            "ADDRESSBOOK_OBJECT where ADDRESSBOOK_RESOURCE_ID = %s",
            [self.addressbook._resourceID]
        )


    @inlineCallbacks
    def resourcesExist(self, names):
        returnValue(list(set(names).intersection(
            set((yield self.addressbook.listAddressbookObjects())))))


    @inlineCallbacks
    def resourceExists(self, name):
        returnValue(bool(
            (yield self._txn.execSQL(
                "select RESOURCE_NAME from ADDRESSBOOK_OBJECT where "
                "RESOURCE_NAME = %s and ADDRESSBOOK_RESOURCE_ID = %s",
                [name, self.addressbook._resourceID]
            ))
        ))
