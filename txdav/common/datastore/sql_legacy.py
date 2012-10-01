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


from twisted.python import hashlib
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twistedcaldav.config import config
from twistedcaldav.dateops import normalizeForIndex, pyCalendarTodatetime
from twistedcaldav.memcachepool import CachePoolUserMixIn
from twistedcaldav.query import \
    calendarqueryfilter, calendarquery, addressbookquery, expression, \
    addressbookqueryfilter
from twistedcaldav.query.sqlgenerator import sqlgenerator

from txdav.caldav.icalendarstore import TimeRangeLowerLimit, TimeRangeUpperLimit
from txdav.common.icommondatastore import IndexedSearchException, \
    ReservationError, NoSuchObjectResourceError

from txdav.common.datastore.sql_tables import schema
from twext.enterprise.dal.syntax import Parameter, Select 
from twext.python.clsprop import classproperty
from twext.python.log import Logger, LoggingMixIn

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.duration import PyCalendarDuration

log = Logger()

indexfbtype_to_icalfbtype = {
    0: '?',
    1: 'F',
    2: 'B',
    3: 'U',
    4: 'T',
}

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
    def _notExpandedWithinQuery(cls): #@NoSelf
        """
        DAL query to satisfy L{PostgresLegacyIndexEmulator.notExpandedBeyond}.
        """
        co = schema.CALENDAR_OBJECT
        return Select(
            [co.RESOURCE_NAME],
            From=co,
            Where=((co.RECURRANCE_MIN > Parameter("minDate"))
                .Or(co.RECURRANCE_MAX < Parameter("maxDate")))
                .And(co.CALENDAR_RESOURCE_ID == Parameter("resourceID"))
        )


    @inlineCallbacks
    def notExpandedWithin(self, minDate, maxDate):
        """
        Gives all resources which have not been expanded beyond a given date
        in the database.  (Unused; see above L{postgresqlgenerator}.
        """
        returnValue([row[0] for row in (
            yield self._notExpandedWithinQuery.on(
                self._txn,
                minDate=pyCalendarTodatetime(normalizeForIndex(minDate)) if minDate is not None else None,
                maxDate=pyCalendarTodatetime(normalizeForIndex(maxDate)),
                resourceID=self.calendar._resourceID))]
        )


    @inlineCallbacks
    def reExpandResource(self, name, expand_start, expand_end):
        """
        Given a resource name, remove it from the database and re-add it
        with a longer expansion.
        """
        obj = yield self.calendar.calendarObjectWithName(name)
        
        # Use a new transaction to do this update quickly without locking the row for too long. However, the original
        # transaction may have the row locked, so use wait=False and if that fails, fall back to using the original txn. 
        
        newTxn = obj.transaction().store().newTransaction()
        try:
            yield obj.lock(wait=False, txn=newTxn)
        except NoSuchObjectResourceError:
            yield newTxn.commit()
            returnValue(None)
        except:
            yield newTxn.abort()
            newTxn = None

        # Now do the re-expand using the appropriate transaction
        try:
            doExpand = False
            if newTxn is None:
                doExpand = True
            else:
                # We repeat this check because the resource may have been re-expanded by someone else
                rmin, rmax = (yield obj.recurrenceMinMax(txn=newTxn))
                
                # If the resource is not fully expanded, see if within the required range or not.
                # Note that expand_start could be None if no lower limit is applied, but expand_end will
                # never be None
                if rmax is not None and rmax < expand_end:
                    doExpand = True
                if rmin is not None and expand_start is not None and rmin > expand_start:
                    doExpand = True

            if doExpand:
                yield obj.updateDatabase(
                    (yield obj.component()),
                    expand_until=expand_end,
                    reCreate=True,
                    txn=newTxn,
                )
        finally:
            if newTxn is not None:
                yield newTxn.commit()


    @inlineCallbacks
    def testAndUpdateIndex(self, minDate, maxDate):
        # Find out if the index is expanded far enough
        names = yield self.notExpandedWithin(minDate, maxDate)

        # Actually expand recurrence max
        for name in names:
            self.log_info("Search falls outside range of index for %s %s to %s" %
                          (name, minDate, maxDate))
            yield self.reExpandResource(name, minDate, maxDate)


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

                today = PyCalendarDateTime.getToday()

                # Determine how far we need to extend the current expansion of
                # events. If we have an open-ended time-range we will expand
                # one year past the start. That should catch bounded
                # recurrences - unbounded will have been indexed with an
                # "infinite" value always included.
                maxDate, isStartDate = filter.getmaxtimerange()
                if maxDate:
                    maxDate = maxDate.duplicate()
                    maxDate.setDateOnly(True)
                    upperLimit = today + PyCalendarDuration(days=config.FreeBusyIndexExpandMaxDays)
                    if maxDate > upperLimit:
                        raise TimeRangeUpperLimit(upperLimit)
                    if isStartDate:
                        maxDate += PyCalendarDuration(days=365)

                # Determine if the start date is too early for the restricted range we 
                # are applying. If it is today or later we don't need to worry about truncation
                # in the past.
                minDate, _ignore_isEndDate = filter.getmintimerange()
                if minDate >= today:
                    minDate = None
                if minDate is not None and config.FreeBusyIndexLowerLimitDays:
                    truncateLowerLimit = today - PyCalendarDuration(days=config.FreeBusyIndexLowerLimitDays)
                    if minDate < truncateLowerLimit:
                        raise TimeRangeLowerLimit(truncateLowerLimit)

                        
                if maxDate is not None or minDate is not None:
                    yield self.testAndUpdateIndex(minDate, maxDate)

            else:
                # We cannot handle this filter in an indexed search
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

