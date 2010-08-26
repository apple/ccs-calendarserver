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
from twisted.internet.defer import succeed

from twext.python.log import Logger, LoggingMixIn

from twistedcaldav import carddavxml
from twistedcaldav.config import config
from twistedcaldav.dateops import normalizeForIndex
from twistedcaldav.index import IndexedSearchException, ReservationError,\
    SyncTokenValidException
from twistedcaldav.memcachepool import CachePoolUserMixIn
from twistedcaldav.notifications import NotificationRecord
from twistedcaldav.query import calendarqueryfilter, calendarquery, \
    addressbookquery
from twistedcaldav.query.sqlgenerator import sqlgenerator
from twistedcaldav.sharing import Invite

from txdav.common.datastore.sql_tables import \
    _BIND_MODE_OWN, _BIND_MODE_READ, _BIND_MODE_WRITE, _BIND_STATUS_INVITED,\
    _BIND_STATUS_ACCEPTED, _BIND_STATUS_DECLINED, _BIND_STATUS_INVALID

log = Logger()

indexfbtype_to_icalfbtype = {
    0: '?',
    1: 'F',
    2: 'B',
    3: 'U',
    4: 'T',
}

class PostgresLegacyInvitesEmulator(object):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """


    def __init__(self, calendar):
        self._calendar = calendar


    @property
    def _txn(self):
        return self._calendar._txn


    def create(self):
        "No-op, because the index implicitly always exists in the database."


    def remove(self):
        "No-op, because the index implicitly always exists in the database."


    def allRecords(self):
        for row in self._txn.execSQL(
                """
                select
                    INVITE.INVITE_UID, INVITE.NAME, INVITE.RECIPIENT_ADDRESS,
                    CALENDAR_HOME.OWNER_UID, CALENDAR_BIND.BIND_MODE,
                    CALENDAR_BIND.BIND_STATUS, CALENDAR_BIND.MESSAGE
                from
                    INVITE, CALENDAR_HOME, CALENDAR_BIND
                where
                    INVITE.RESOURCE_ID = %s and
                    INVITE.HOME_RESOURCE_ID = 
                        CALENDAR_HOME.RESOURCE_ID and
                    CALENDAR_BIND.CALENDAR_RESOURCE_ID =
                        INVITE.RESOURCE_ID and
                    CALENDAR_BIND.CALENDAR_HOME_RESOURCE_ID =
                        INVITE.HOME_RESOURCE_ID
                order by
                    INVITE.NAME asc
                """, [self._calendar._resourceID]):
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
                _BIND_MODE_READ: "read-only",
                _BIND_MODE_WRITE: "read-write"
            }[bindMode]
            principalURL = "/principals/__uids__/%s/" % (ownerUID,)
            yield Invite(
                inviteuid, userid, principalURL, common_name,
                access, state, summary
            )


    def recordForUserID(self, userid):
        for record in self.allRecords():
            if record.userid == userid:
                return record


    def recordForPrincipalURL(self, principalURL):
        for record in self.allRecords():
            if record.principalURL == principalURL:
                return record


    def recordForInviteUID(self, inviteUID):
        for record in self.allRecords():
            if record.inviteuid == inviteUID:
                return record


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
        shareeHome = self._txn.calendarHomeWithUID(principalUID, create=True)
        rows = self._txn.execSQL(
            "select RESOURCE_ID, HOME_RESOURCE_ID from INVITE where RECIPIENT_ADDRESS = %s",
            [record.userid]
        )
        if rows:
            [[resourceID, homeResourceID]] = rows
            # Invite(inviteuid, userid, principalURL, common_name, access, state, summary)
            self._txn.execSQL("""
                update CALENDAR_BIND set BIND_MODE = %s,
                BIND_STATUS = %s, MESSAGE = %s
                where
                    CALENDAR_RESOURCE_ID = %s and
                    CALENDAR_HOME_RESOURCE_ID = %s
            """, [bindMode, bindStatus, record.summary,
                resourceID, homeResourceID])
            self._txn.execSQL("""
                update INVITE set NAME = %s, INVITE_UID = %s
                where RECIPIENT_ADDRESS = %s
                """,
                [record.name, record.inviteuid, record.userid]
            )
        else:
            self._txn.execSQL(
                """
                insert into INVITE (
                    INVITE_UID, NAME,
                    HOME_RESOURCE_ID, RESOURCE_ID,
                    RECIPIENT_ADDRESS
                )
                values (%s, %s, %s, %s, %s)
                """,
                [
                    record.inviteuid, record.name,
                    shareeHome._resourceID, self._calendar._resourceID,
                    record.userid
                ])
            self._txn.execSQL(
                """
                insert into CALENDAR_BIND
                (
                    CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID, 
                    CALENDAR_RESOURCE_NAME, BIND_MODE, BIND_STATUS,
                    SEEN_BY_OWNER, SEEN_BY_SHAREE, MESSAGE
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    shareeHome._resourceID,
                    self._calendar._resourceID,
                    None, # this is NULL because it is not bound yet, let's be
                          # explicit about that.
                    bindMode,
                    bindStatus,
                    False,
                    False,
                    record.summary
                ])


    def removeRecordForUserID(self, userid):
        rec = self.recordForUserID(userid)
        self.removeRecordForInviteUID(rec.inviteuid)


    def removeRecordForPrincipalURL(self, principalURL):
        raise NotImplementedError("removeRecordForPrincipalURL")


    def removeRecordForInviteUID(self, inviteUID):
        rows = self._txn.execSQL("""
                select HOME_RESOURCE_ID, RESOURCE_ID from INVITE where
                INVITE_UID = %s
            """, [inviteUID])
        if rows:
            [[homeID, resourceID]] = rows
            self._txn.execSQL(
                "delete from CALENDAR_BIND where "
                "CALENDAR_HOME_RESOURCE_ID = %s and CALENDAR_RESOURCE_ID = %s",
                [homeID, resourceID])
            self._txn.execSQL("delete from INVITE where INVITE_UID = %s",
                [inviteUID])



class PostgresLegacySharesEmulator(object):

    def __init__(self, home):
        self._home = home


    @property
    def _txn(self):
        return self._home._txn


    def create(self):
        pass


    def remove(self):
        pass


    def allRecords(self):
        # This should have been a smart join that got all these columns at
        # once, but let's not bother to fix it, since the actual query we
        # _want_ to do (just look for calendar binds in a particular homes) is
        # much simpler anyway; we should just do that.
        shareRows = self._txn.execSQL(
            """
            select CALENDAR_RESOURCE_ID, CALENDAR_RESOURCE_NAME, MESSAGE
            from CALENDAR_BIND
                where CALENDAR_HOME_RESOURCE_ID = %s and
                BIND_MODE != %s and
                CALENDAR_RESOURCE_NAME is not null
            """, [self._home._resourceID, _BIND_MODE_OWN])
        for resourceID, resourceName, summary in shareRows:
            [[shareuid]] = self._txn.execSQL(
                """
                select INVITE_UID
                from INVITE
                where RESOURCE_ID = %s and HOME_RESOURCE_ID = %s
                """, [resourceID, self._home._resourceID])
            sharetype = 'I'
            [[ownerHomeID, ownerResourceName]] = self._txn.execSQL(
                """
                select CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_NAME
                from CALENDAR_BIND
                where CALENDAR_RESOURCE_ID = %s and
                    BIND_MODE = %s
                """, [resourceID, _BIND_MODE_OWN]
                )
            [[ownerUID]] = self._txn.execSQL(
                "select OWNER_UID from CALENDAR_HOME where RESOURCE_ID = %s",
                [ownerHomeID])
            hosturl = '/calendars/__uids__/%s/%s' % (
                ownerUID, ownerResourceName
            )
            localname = resourceName
            record = SharedCollectionRecord(
                shareuid, sharetype, hosturl, localname, summary
            )
            yield record


    def _search(self, **kw):
        [[key, value]] = kw.items()
        for record in self.allRecords():
            if getattr(record, key) == value:
                return record

    def recordForLocalName(self, localname):
        return self._search(localname=localname)

    def recordForShareUID(self, shareUID):
        return self._search(shareuid=shareUID)


    def addOrUpdateRecord(self, record):
#        print '*** SHARING***: Adding or updating this record:'
#        import pprint
#        pprint.pprint(record.__dict__)
        # record.hosturl -> /calendars/__uids__/<uid>/<calendarname>
        splithost = record.hosturl.split('/')
        ownerUID = splithost[3]
        ownerCalendarName = splithost[4]
        ownerHome = self._txn.calendarHomeWithUID(ownerUID)
        ownerCalendar = ownerHome.calendarWithName(ownerCalendarName)
        calendarResourceID = ownerCalendar._resourceID

        # There needs to be a bind already, one that corresponds to the
        # invitation.  The invitation's UID is the same as the share UID.  I
        # just need to update its 'localname', i.e.
        # CALENDAR_BIND.CALENDAR_RESOURCE_NAME.

        self._txn.execSQL(
            """
            update CALENDAR_BIND set CALENDAR_RESOURCE_NAME = %s
            where CALENDAR_HOME_RESOURCE_ID = %s and CALENDAR_RESOURCE_ID = %s
            """,
            [record.localname, self._home._resourceID, calendarResourceID]
        )


    def removeRecordForLocalName(self, localname):
        self._txn.execSQL(
            "delete from CALENDAR_BIND where CALENDAR_RESOURCE_NAME = %s "
            "and CALENDAR_HOME_RESOURCE_ID = %s",
            [localname, self._home._resourceID]
        )


    def removeRecordForShareUID(self, shareUID):
        pass
#        c = self._home._cursor()
#        c.execute(
#            "delete from CALENDAR_BIND where CALENDAR_RESOURCE_NAME = %s "
#            "and CALENDAR_HOME_RESOURCE_ID = %s",
#            [self._home._resourceID]
#        )



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

class PostgresLegacyIndexEmulator(LoggingMixIn):
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


    def reserveUID(self, uid):
        if self.calendar._name == "inbox":
            return succeed(None)
        else:
            return self.reserver.reserveUID(uid)


    def unreserveUID(self, uid):
        if self.calendar._name == "inbox":
            return succeed(None)
        else:
            return self.reserver.unreserveUID(uid)


    def isReservedUID(self, uid):
        if self.calendar._name == "inbox":
            return succeed(False)
        else:
            return self.reserver.isReservedUID(uid)


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
        if self.calendar._name == "inbox":
            return True
        else:
            rname = self.resourceNameForUID(uid)
            return (rname is None or rname in names)

    def resourceUIDForName(self, name):
        obj = self.calendar.calendarObjectWithName(name)
        if obj is None:
            return None
        return obj.uid()


    def resourceNameForUID(self, uid):
        obj = self.calendar.calendarObjectWithUID(uid)
        if obj is None:
            return None
        return obj.name()


    def notExpandedBeyond(self, minDate):
        """
        Gives all resources which have not been expanded beyond a given date
        in the database.  (Unused; see above L{postgresqlgenerator}.
        """
        return [row[0] for row in self._txn.execSQL(
            "select RESOURCE_NAME from CALENDAR_OBJECT "
            "where RECURRANCE_MAX < %s and CALENDAR_RESOURCE_ID = %s",
            [normalizeForIndex(minDate), self.calendar._resourceID]
        )]


    def reExpandResource(self, name, expand_until):
        """
        Given a resource name, remove it from the database and re-add it
        with a longer expansion.
        """
        obj = self.calendar.calendarObjectWithName(name)
        obj.updateDatabase(obj.component(), expand_until=expand_until, reCreate=True)

    def testAndUpdateIndex(self, minDate):
        # Find out if the index is expanded far enough
        names = self.notExpandedBeyond(minDate)

        # Actually expand recurrence max
        for name in names:
            self.log_info("Search falls outside range of index for %s %s" % (name, minDate))
            self.reExpandResource(name, minDate)

    def whatchanged(self, revision):

        results = [
            (name.encode("utf-8"), deleted)
            for name, deleted in
            self._txn.execSQL(
                """select RESOURCE_NAME, DELETED from CALENDAR_OBJECT_REVISIONS
                   where REVISION > %s and CALENDAR_RESOURCE_ID = %s""",
                [revision, self.calendar._resourceID],
            )
        ]
        results.sort(key=lambda x:x[1])
        
        changed = []
        deleted = []
        for name, wasdeleted in results:
            if name:
                if wasdeleted:
                    if revision:
                        deleted.append(name)
                else:
                    changed.append(name)
            else:
                raise SyncTokenValidException
        
        return changed, deleted,

    def indexedSearch(self, filter, useruid='', fbtype=False):
        """
        Finds resources matching the given qualifiers.
        @param filter: the L{Filter} for the calendar-query to execute.
        @return: an iterable of tuples for each resource matching the
            given C{qualifiers}. The tuples are C{(name, uid, type)}, where
            C{name} is the resource name, C{uid} is the resource UID, and
            C{type} is the resource iCalendar component type.x
        """

        # Make sure we have a proper Filter element and get the partial SQL
        # statement to use.
        if isinstance(filter, calendarqueryfilter.Filter):
            qualifiers = calendarquery.sqlcalendarquery(filter, self.calendar._resourceID, useruid, generator=postgresqlgenerator)
            if qualifiers is not None:
                # Determine how far we need to extend the current expansion of
                # events. If we have an open-ended time-range we will expand one
                # year past the start. That should catch bounded recurrences - unbounded
                # will have been indexed with an "infinite" value always included.
                maxDate, isStartDate = filter.getmaxtimerange()
                if maxDate:
                    maxDate = maxDate.date()
                    if isStartDate:
                        maxDate += datetime.timedelta(days=365)
                    self.testAndUpdateIndex(maxDate)
            else:
                # We cannot handler this filter in an indexed search
                raise IndexedSearchException()

        else:
            qualifiers = None

        # Perform the search
        if qualifiers is None:
            rowiter = self._txn.execSQL(
                "select RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = %s",
                [self.calendar._resourceID, ],
            )
        else:
            if fbtype:
                # For a free-busy time-range query we return all instances
                rowiter = self._txn.execSQL(
                    """select DISTINCT
                        CALENDAR_OBJECT.RESOURCE_NAME, CALENDAR_OBJECT.ICALENDAR_UID, CALENDAR_OBJECT.ICALENDAR_TYPE, CALENDAR_OBJECT.ORGANIZER,
                        TIME_RANGE.FLOATING, TIME_RANGE.START_DATE, TIME_RANGE.END_DATE, TIME_RANGE.FBTYPE, TIME_RANGE.TRANSPARENT, TRANSPARENCY.TRANSPARENT""" +
                    qualifiers[0],
                    qualifiers[1]
                )
            else:
                rowiter = self._txn.execSQL(
                    "select DISTINCT CALENDAR_OBJECT.RESOURCE_NAME, CALENDAR_OBJECT.ICALENDAR_UID, CALENDAR_OBJECT.ICALENDAR_TYPE" +
                    qualifiers[0],
                    qualifiers[1]
                )

        # Check result for missing resources

        for row in rowiter:
            if fbtype:
                row = list(row)
                row[4] = 'Y' if row[4] else 'N'
                row[7] = indexfbtype_to_icalfbtype[row[7]]
                row[8] = 'T' if row[9] else 'F'
                del row[9]
            yield row


    def bruteForceSearch(self):
        return self._txn.execSQL(
            "select RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE from "
            "CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = %s",
            [self.calendar._resourceID]
        )


    def resourcesExist(self, names):
        return list(set(names).intersection(
            set(self.calendar.listCalendarObjects())))


    def resourceExists(self, name):
        return bool(
            self._txn.execSQL(
                "select RESOURCE_NAME from CALENDAR_OBJECT where "
                "RESOURCE_NAME = %s and CALENDAR_RESOURCE_ID = %s",
                [name, self.calendar._resourceID]
            )
        )




class PostgresLegacyNotificationsEmulator(object):
    def __init__(self, notificationsCollection):
        self._collection = notificationsCollection


    def _recordForObject(self, notificationObject):
        return NotificationRecord(
            notificationObject.uid(),
            notificationObject.name(),
            notificationObject._fieldQuery("XML_TYPE"))


    def recordForName(self, name):
        return self._recordForObject(
            self._collection.notificationObjectWithName(name)
        )


    def recordForUID(self, uid):
        return self._recordForObject(
            self._collection.notificationObjectWithUID(uid)
        )


    def removeRecordForUID(self, uid):
        self._collection.removeNotificationObjectWithUID(uid)


    def removeRecordForName(self, name):
        self._collection.removeNotificationObjectWithName(name)




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


class PostgresLegacyABIndexEmulator(object):
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


    def reserveUID(self, uid):
        return self.reserver.reserveUID(uid)


    def unreserveUID(self, uid):
        return self.reserver.unreserveUID(uid)


    def isReservedUID(self, uid):
        return self.reserver.isReservedUID(uid)


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
        rname = self.resourceNameForUID(uid)
        return (rname is None or rname in names)


    def resourceUIDForName(self, name):
        obj = self.addressbook.addressbookObjectWithName(name)
        if obj is None:
            return None
        return obj.uid()


    def resourceNameForUID(self, uid):
        obj = self.addressbook.addressbookObjectWithUID(uid)
        if obj is None:
            return None
        return obj.name()


    def whatchanged(self, revision):

        results = [
            (name.encode("utf-8"), deleted)
            for name, deleted in
            self._txn.execSQL(
                """select RESOURCE_NAME, DELETED from ADDRESSBOOK_OBJECT_REVISIONS
                   where REVISION > %s and ADDRESSBOOK_RESOURCE_ID = %s""",
                [revision, self.addressbook._resourceID],
            )
        ]
        results.sort(key=lambda x:x[1])
        
        changed = []
        deleted = []
        for name, wasdeleted in results:
            if name:
                if wasdeleted:
                    if revision:
                        deleted.append(name)
                else:
                    changed.append(name)
            else:
                raise SyncTokenValidException
        
        return changed, deleted,

    def searchValid(self, filter):
        if isinstance(filter, carddavxml.Filter):
            qualifiers = addressbookquery.sqladdressbookquery(filter)
        else:
            qualifiers = None

        return qualifiers is not None

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
            rowiter = self._txn.execSQL(
                "select DISTINCT ADDRESSBOOK_OBJECT.RESOURCE_NAME, ADDRESSBOOK_OBJECT.VCARD_UID" +
                qualifiers[0],
                qualifiers[1]
            )
        else:
            rowiter = self._txn.execSQL(
                "select RESOURCE_NAME, VCARD_UID from ADDRESSBOOK_OBJECT where ADDRESSBOOK_RESOURCE_ID = %s",
                [self.addressbook._resourceID, ],
            )

        for row in rowiter:
            yield row

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


    def resourcesExist(self, names):
        return list(set(names).intersection(
            set(self.addressbook.listAddressbookObjects())))


    def resourceExists(self, name):
        return bool(
            self._txn.execSQL(
                "select RESOURCE_NAME from ADDRESSBOOK_OBJECT where "
                "RESOURCE_NAME = %s and ADDRESSBOOK_RESOURCE_ID = %s",
                [name, self.addressbook._resourceID]
            )
        )


class PostgresLegacyABInvitesEmulator(object):
    """
    Emulator for the implicit interface specified by
    L{twistedcaldav.sharing.InvitesDatabase}.
    """


    def __init__(self, addressbook):
        self._addressbook = addressbook


    @property
    def _txn(self):
        return self._addressbook._txn


    def create(self):
        "No-op, because the index implicitly always exists in the database."


    def remove(self):
        "No-op, because the index implicitly always exists in the database."


    def allRecords(self):
        for row in self._txn.execSQL(
                """
                select
                    INVITE.INVITE_UID, INVITE.NAME, INVITE.RECIPIENT_ADDRESS,
                    ADDRESSBOOK_HOME.OWNER_UID, ADDRESSBOOK_BIND.BIND_MODE,
                    ADDRESSBOOK_BIND.BIND_STATUS, ADDRESSBOOK_BIND.MESSAGE
                from
                    INVITE, ADDRESSBOOK_HOME, ADDRESSBOOK_BIND
                where
                    INVITE.RESOURCE_ID = %s and
                    INVITE.HOME_RESOURCE_ID = 
                        ADDRESSBOOK_HOME.RESOURCE_ID and
                    ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID =
                        INVITE.RESOURCE_ID and
                    ADDRESSBOOK_BIND.ADDRESSBOOK_HOME_RESOURCE_ID =
                        INVITE.HOME_RESOURCE_ID
                order by
                    INVITE.NAME asc
                """, [self._addressbook._resourceID]):
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
                _BIND_MODE_READ: "read-only",
                _BIND_MODE_WRITE: "read-write"
            }[bindMode]
            principalURL = "/principals/__uids__/%s/" % (ownerUID,)
            yield Invite(
                inviteuid, userid, principalURL, common_name,
                access, state, summary
            )


    def recordForUserID(self, userid):
        for record in self.allRecords():
            if record.userid == userid:
                return record


    def recordForPrincipalURL(self, principalURL):
        for record in self.allRecords():
            if record.principalURL == principalURL:
                return record


    def recordForInviteUID(self, inviteUID):
        for record in self.allRecords():
            if record.inviteuid == inviteUID:
                return record


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
        shareeHome = self._txn.addressbookHomeWithUID(principalUID, create=True)
        rows = self._txn.execSQL(
            "select RESOURCE_ID, HOME_RESOURCE_ID from INVITE where RECIPIENT_ADDRESS = %s",
            [record.userid]
        )
        if rows:
            [[resourceID, homeResourceID]] = rows
            # Invite(inviteuid, userid, principalURL, common_name, access, state, summary)
            self._txn.execSQL("""
                update ADDRESSBOOK_BIND set BIND_MODE = %s,
                BIND_STATUS = %s, MESSAGE = %s
                where
                    ADDRESSBOOK_RESOURCE_ID = %s and
                    ADDRESSBOOK_HOME_RESOURCE_ID = %s
            """, [bindMode, bindStatus, record.summary,
                resourceID, homeResourceID])
            self._txn.execSQL("""
                update INVITE set NAME = %s, INVITE_UID = %s
                where RECIPIENT_ADDRESS = %s
                """,
                [record.name, record.inviteuid, record.userid]
            )
        else:
            self._txn.execSQL(
                """
                insert into INVITE (
                    INVITE_UID, NAME,
                    HOME_RESOURCE_ID, RESOURCE_ID,
                    RECIPIENT_ADDRESS
                )
                values (%s, %s, %s, %s, %s)
                """,
                [
                    record.inviteuid, record.name,
                    shareeHome._resourceID, self._addressbook._resourceID,
                    record.userid
                ])
            self._txn.execSQL(
                """
                insert into ADDRESSBOOK_BIND
                (
                    ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_ID, 
                    ADDRESSBOOK_RESOURCE_NAME, BIND_MODE, BIND_STATUS,
                    SEEN_BY_OWNER, SEEN_BY_SHAREE, MESSAGE
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    shareeHome._resourceID,
                    self._addressbook._resourceID,
                    None, # this is NULL because it is not bound yet, let's be
                          # explicit about that.
                    bindMode,
                    bindStatus,
                    False,
                    False,
                    record.summary
                ])


    def removeRecordForUserID(self, userid):
        rec = self.recordForUserID(userid)
        self.removeRecordForInviteUID(rec.inviteuid)


    def removeRecordForPrincipalURL(self, principalURL):
        raise NotImplementedError("removeRecordForPrincipalURL")


    def removeRecordForInviteUID(self, inviteUID):
        rows = self._txn.execSQL("""
                select HOME_RESOURCE_ID, RESOURCE_ID from INVITE where
                INVITE_UID = %s
            """, [inviteUID])
        if rows:
            [[homeID, resourceID]] = rows
            self._txn.execSQL(
                "delete from ADDRESSBOOK_BIND where "
                "ADDRESSBOOK_HOME_RESOURCE_ID = %s and ADDRESSBOOK_RESOURCE_ID = %s",
                [homeID, resourceID])
            self._txn.execSQL("delete from INVITE where INVITE_UID = %s",
                [inviteUID])



class PostgresLegacyABSharesEmulator(object):

    def __init__(self, home):
        self._home = home


    @property
    def _txn(self):
        return self._home._txn


    def create(self):
        pass


    def remove(self):
        pass


    def allRecords(self):
        # This should have been a smart join that got all these columns at
        # once, but let's not bother to fix it, since the actual query we
        # _want_ to do (just look for addressbook binds in a particular homes) is
        # much simpler anyway; we should just do that.
        shareRows = self._txn.execSQL(
            """
            select ADDRESSBOOK_RESOURCE_ID, ADDRESSBOOK_RESOURCE_NAME, MESSAGE
            from ADDRESSBOOK_BIND
                where ADDRESSBOOK_HOME_RESOURCE_ID = %s and
                BIND_MODE != %s and
                ADDRESSBOOK_RESOURCE_NAME is not null
            """, [self._home._resourceID, _BIND_MODE_OWN])
        for resourceID, resourceName, summary in shareRows:
            [[shareuid]] = self._txn.execSQL(
                """
                select INVITE_UID
                from INVITE
                where RESOURCE_ID = %s and HOME_RESOURCE_ID = %s
                """, [resourceID, self._home._resourceID])
            sharetype = 'I'
            [[ownerHomeID, ownerResourceName]] = self._txn.execSQL(
                """
                select ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_NAME
                from ADDRESSBOOK_BIND
                where ADDRESSBOOK_RESOURCE_ID = %s and
                    BIND_MODE = %s
                """, [resourceID, _BIND_MODE_OWN]
                )
            [[ownerUID]] = self._txn.execSQL(
                "select OWNER_UID from ADDRESSBOOK_HOME where RESOURCE_ID = %s",
                [ownerHomeID])
            hosturl = '/addressbooks/__uids__/%s/%s' % (
                ownerUID, ownerResourceName
            )
            localname = resourceName
            record = SharedCollectionRecord(
                shareuid, sharetype, hosturl, localname, summary
            )
            yield record


    def _search(self, **kw):
        [[key, value]] = kw.items()
        for record in self.allRecords():
            if getattr(record, key) == value:
                return record

    def recordForLocalName(self, localname):
        return self._search(localname=localname)

    def recordForShareUID(self, shareUID):
        return self._search(shareuid=shareUID)


    def addOrUpdateRecord(self, record):
#        print '*** SHARING***: Adding or updating this record:'
#        import pprint
#        pprint.pprint(record.__dict__)
        # record.hosturl -> /addressbooks/__uids__/<uid>/<addressbookname>
        splithost = record.hosturl.split('/')
        ownerUID = splithost[3]
        ownerAddressBookName = splithost[4]
        ownerHome = self._txn.addressbookHomeWithUID(ownerUID)
        ownerAddressBook = ownerHome.addressbookWithName(ownerAddressBookName)
        addressbookResourceID = ownerAddressBook._resourceID

        # There needs to be a bind already, one that corresponds to the
        # invitation.  The invitation's UID is the same as the share UID.  I
        # just need to update its 'localname', i.e.
        # ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME.

        self._txn.execSQL(
            """
            update ADDRESSBOOK_BIND set ADDRESSBOOK_RESOURCE_NAME = %s
            where ADDRESSBOOK_HOME_RESOURCE_ID = %s and ADDRESSBOOK_RESOURCE_ID = %s
            """,
            [record.localname, self._home._resourceID, addressbookResourceID]
        )


    def removeRecordForLocalName(self, localname):
        self._txn.execSQL(
            "delete from ADDRESSBOOK_BIND where ADDRESSBOOK_RESOURCE_NAME = %s "
            "and ADDRESSBOOK_HOME_RESOURCE_ID = %s",
            [localname, self._home._resourceID]
        )


    def removeRecordForShareUID(self, shareUID):
        pass
#        c = self._home._cursor()
#        c.execute(
#            "delete from ADDRESSBOOK_BIND where ADDRESSBOOK_RESOURCE_NAME = %s "
#            "and ADDRESSBOOK_HOME_RESOURCE_ID = %s",
#            [self._home._resourceID]
#        )
