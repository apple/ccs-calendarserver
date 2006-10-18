##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
CalDAV Index.

This API is considered private to static.py and is therefore subject to
change.
"""

__all__ = [
    "AbstractIndex",
    "Index",
    "IndexSchedule",
]

import os
import datetime

from pysqlite2 import dbapi2 as sqlite

from twisted.python import log
from twisted.python.failure import Failure

from twistedcaldav.dateops import normalizeForIndex
from twistedcaldav.ical import Component
from twistedcaldav.query import calendarquery
from twistedcaldav import caldavxml

db_basename = ".db.sqlite"
schema_version = "4"
collection_types = {"Calendar": "Regular Calendar Collection", "iTIP": "iTIP Calendar Collection"}

#
# Duration into the future through which recurrances are expanded in the index
# by default.  This is a caching parameter which affects the size of the index;
# it does not affect search results beyond this period, but it may affect
# performance of such a search.
#
default_future_expansion_duration = datetime.timedelta(days=356*1)

#
# Maximum duration into the future through which recurrances are expanded in the
# index.  This is a caching parameter which affects the size of the index; it
# does not affect search results beyond this period, but it may affect
# performance of such a search.
#
# When a search is performed on a timespan that goes beyond that which is
# expanded in the index, we have to open each resource which may have data in
# that time period.  In order to avoid doing that multiple times, we want to
# cache those results.  However, we don't necessarily want to cache all
# occurances into some obscenely far-in-the-future date, so we cap the caching
# period.  Searches beyond this period will always be relatively expensive for
# resources with occurances beyond this period.
#
maximum_future_expansion_duration = datetime.timedelta(days=356*5)

class ReservationError(LookupError):
    """
    Attempt to reserve a UID which is already reserved or to unreverse a UID
    which is not reserved.
    """

class AbstractIndex(object):
    """
    Calendar collection index abstract base class that defines the apis for the index.
    This will be subclassed for the two types of index behaviour we need: one for
    regular calendar collections, one for schedule calendar collections.
    """

    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index. C{resource} must be a calendar collection (ie.
            C{resource.isPseudoCalendarCollection()} returns C{True}.)
        """
        self.resource = resource

    def reserveUID(self, uid):
        """
        Reserve a UID for this index's resource.
        @param uid: the UID to reserve
        @raise ReservationError: if C{uid} is already reserved
        """
        raise NotImplementedError

    def unreserveUID(self, uid):
        """
        Unreserve a UID for this index's resource.
        @param uid: the UID to reserve
        @raise ReservationError: if C{uid} is not reserved
        """
        raise NotImplementedError

    def isReservedUID(self, uid):
        """
        Check to see whether a UID is reserved.
        @param uid: the UID to check
        @return: True if C{uid} is reserved, False otherwise.
        """
        raise NotImplementedError

    def isAllowedUID(self, uid, *names):
        """
        Checks to see whether to allow an operation with adds the the specified
        UID is allowed to the index.  Specifically, the operation may not
        violate the constraint that UIDs must be unique, and the UID must not
        be reserved.
        @param uid: the UID to check
        @param names: the names of resources being replaced or deleted by the
            operation; UIDs associated with these resources are not checked.
        @return: True if the UID is not in the index and is not reserved,
            False otherwise.
        """
        raise NotImplementedError

    def resourceNamesForUID(self, uid):
        """
        Looks up the names of the resources with the given UID.
        @param uid: the UID of the resources to look up.
        @return: a list of resource names
        """
        names = self._db_values_for_sql("select NAME from RESOURCE where UID = :1", uid)

        #
        # Check that each name exists as a child of self.resource.  If not, the
        # resource record is stale.
        #
        resources = []
        for name in names:
            if name is not None and self.resource.getChild(name) is None:
                # Clean up
                log.err("Stale resource record found for child %s with UID %s in %s" % (name, uid, self.resource))
                self._delete_from_db(name, uid)
                self._db_commit()
            else:
                resources.append(name)

        return resources

    def resourceNameForUID(self, uid):
        """
        Looks up the name of the resource with the given UID.
        @param uid: the UID of the resource to look up.
        @return: If the resource is found, its name; C{None} otherwise.
        """
        result = None

        for name in self.resourceNamesForUID(uid):
            assert result is None, "More than one resource with UID %s in calendar collection %r" % (uid, self)
            result = name
            
        return result

    def resourceUIDForName(self, name):
        """
        Looks up the UID of the resource with the given name.
        @param name: the name of the resource to look up.
        @return: If the resource is found, the UID of the resource; C{None}
            otherwise.
        """
        uid = self._db_value_for_sql("select UID from RESOURCE where NAME = :1", name)

        return uid

    def addResource(self, name, calendar, fast=False):
        """
        Adding or updating an existing resource.
        To check for an update we attempt to get an existing UID
        for the resource name. If present, then the index entries for
        that UID are removed. After that the new index entries are added.
        @param name: the name of the resource to add.
        @param calendar: a L{Calendar} object representing the resource
            contents.
        @param fast: if C{True} do not do commit, otherwise do commit.
        """
        oldUID = self.resourceUIDForName(name)
        if oldUID is not None:
            self._delete_from_db(name, oldUID)
        self._add_to_db(name, calendar)
        if not fast:
            self._db_commit()

    def deleteResource(self, name):
        """
        Remove this resource from the index.
        @param name: the name of the resource to add.
        @param uid: the UID of the calendar component in the resource.
        """
        uid = self.resourceUIDForName(name)
        if uid is not None:
            self._delete_from_db(name, uid)
            self._db_commit()
    
    def resourceExists(self, name):
        """
        Determines whether the specified resource name exists in the index.
        @param name: the name of the resource to test
        @return: True if the resource exists, False if not
        """
        uid = self._db_value_for_sql("select UID from RESOURCE where NAME = :1", name)
        return uid is not None
    
    def search(self, filter):
        """
        Finds resources matching the given qualifiers.
        @param filter: the L{Filter} for the calendar-query to execute.
        @return: an interable iterable of tuples for each resource matching the
            given C{qualifiers}. The tuples are C{(name, uid, type)}, where
            C{name} is the resource name, C{uid} is the resource UID, and
            C{type} is the resource iCalendar component type.x
        """
        # FIXME: Don't forget to use maximum_future_expansion_duration when we
        # start caching...
        
        # Make sure we have a proper Filter element and get the partial SQL statement to use.
        if isinstance(filter, caldavxml.Filter):
            qualifiers = calendarquery.sqlcalendarquery(filter)
        else:
            qualifiers = None
        if qualifiers is not None:
            rowiter = self._db_execute("select RESOURCE.NAME, RESOURCE.UID, RESOURCE.TYPE" + qualifiers[0], *qualifiers[1])
        else:
            rowiter = self._db_execute("select NAME, UID, TYPE from RESOURCE")
            
        for row in rowiter:
            name = row[0]
            if self.resource.getChild(name):
                yield row
            else:
                log.err("Calendar resource %s is missing from %s. Removing from index."
                        % (name, self.resource))
                self.deleteResource(name)

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        raise NotImplementedError
        
    def _db(self):
        """
        Access the underlying database.
        @return: a db2 connection object for this index's underlying data store.
        """
        if not hasattr(self, "_db_connection"):
            db_filename = os.path.join(self.resource.fp.path, db_basename)
            self._db_connection = sqlite.connect(db_filename)

            #
            # Set up the schema
            #
            q = self._db_connection.cursor()
            try:
                # Create CALDAV table if needed
                q.execute(
                    """
                    select (1) from SQLITE_MASTER
                     where TYPE = 'table' and NAME = 'CALDAV'
                    """)
                caldav = q.fetchone()

                if caldav:
                    q.execute(
                        """
                        select VALUE from CALDAV
                         where KEY = 'SCHEMA_VERSION'
                        """)
                    version = q.fetchone()

                    if version is not None: version = version[0]

                    q.execute(
                        """
                        select VALUE from CALDAV
                         where KEY = 'TYPE'
                        """)
                    type = q.fetchone()

                    if type is not None: type = type[0]

                    if (version != schema_version) or (type != self._db_type()):
                        if version != schema_version:
                            log.err("Index %s has different schema (v.%s vs. v.%s)"
                                    % (db_filename, version, schema_version))
                        if type != self._db_type():
                            log.err("Index %s has different type (%s vs. %s)"
                                    % (db_filename, type, self._db_type()))

                        # Delete this index and start over
                        q.close()
                        q = None
                        self._db_connection.close()
                        del(self._db_connection)
                        os.remove(db_filename)
                        return self._db()

                else:
                    self._db_init(db_filename, q)

                self._db_connection.commit()
            finally:
                if q is not None: q.close()
        return self._db_connection

    def _db_init(self, db_filename, q):
        """
        Initialise the underlying database tables.
        @param db_filename: the file name of the index database.
        @param q:           a database cursor to use.
        """
        log.msg("Initializing index %s" % (db_filename,))

        self._db_init_schema_table(q)
        self._db_init_data_tables(q)

    def _db_init_schema_table(self, q):
        """
        Initialise the underlying database tables.
        @param db_filename: the file name of the index database.
        @param q:           a database cursor to use.
        """

        #
        # CALDAV table keeps track of our schema version and type
        #
        q.execute(
            """
            create table CALDAV (
                KEY text unique, VALUE text unique
            )
            """
        )
        q.execute(
            """
            insert into CALDAV (KEY, VALUE)
            values ('SCHEMA_VERSION', :1)
            """, [schema_version]
        )
        q.execute(
            """
            insert into CALDAV (KEY, VALUE)
            values ('TYPE', :1)
            """, [self._db_type()]
        )

    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param db_filename: the file name of the index database.
        @param q:           a database cursor to use.
        """
        raise NotImplementedError

    def _add_to_db(self, name, calendar, cursor = None):
        """
        Records the given calendar resource in the index with the given name.
        Resource names and UIDs must both be unique; only one resource name may
        be associated with any given UID and vice versa.
        NB This method does not commit the changes to the db - the caller
        MUST take care of that
        @param name: the name of the resource to add.
        @param calendar: a L{Calendar} object representing the resource
            contents.
        """
        raise NotImplementedError
    
    def _delete_from_db(self, name, uid):
        """
        Deletes the specified entry from all dbs.
        @param name: the name of the resource to delete.
        @param uid: the uid of the resource to delete.
        """
        raise NotImplementedError
    
    def _db_values_for_sql(self, sql, *query_params):
        """
        Execute an SQL query and obtain the resulting values.
        @param sql: the SQL query to execute.
        @param query_params: parameters to C{sql}.
        @return: an interable of values in the first column of each row
            resulting from executing C{sql} with C{query_params}.
        @raise AssertionError: if the query yields multiple columns.
        """
        return (row[0] for row in self._db_execute(sql, *query_params))

    def _db_value_for_sql(self, sql, *query_params):
        """
        Execute an SQL query and obtain a single value.
        @param sql: the SQL query to execute.
        @param query_params: parameters to C{sql}.
        @return: the value resulting from the executing C{sql} with
            C{query_params}.
        @raise AssertionError: if the query yields multiple rows or columns.
        """
        value = None
        for row in self._db_values_for_sql(sql, *query_params):
            assert value is None, "Multiple values in DB for %s %s" % (sql, query_params)
            value = row
        return value

    def _db_execute(self, sql, *query_params):
        """
        Execute an SQL query and obtain the resulting values.
        @param sql: the SQL query to execute.
        @param query_params: parameters to C{sql}.
        @return: an interable of tuples for each row resulting from executing
            C{sql} with C{query_params}.
        """
        q = self._db().cursor()
        try:
            try:
                q.execute(sql, query_params)
            except:
                log.err("Exception while executing SQL: %r %r" % (sql, query_params))
                raise
            return q.fetchall()
        finally:
            q.close()

    def _db_commit  (self): self._db_connection.commit()
    def _db_rollback(self): self._db_connection.rollback()

class CalendarIndex (AbstractIndex):
    """
    Calendar index - abstract class for indexer that indexes calendar objects in a collection.
    """
    
    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index.
        """
        super(CalendarIndex, self).__init__(resource)

    def _db_init_data_tables_base(self, q, uidunique):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """
        #
        # RESOURCE table is the primary index table
        #   NAME: Last URI component (eg. <uid>.ics, RESOURCE primary key)
        #   UID: iCalendar UID (may or may not be unique)
        #   TYPE: iCalendar component type
        #   RECURRANCE_MAX: Highest date of recurrance expansion
        #
        if uidunique:
            q.execute(
                """
                create table RESOURCE (
                    NAME           text unique,
                    UID            text unique,
                    TYPE           text,
                    RECURRANCE_MAX date
                )
                """
            )
        else:
            q.execute(
                """
                create table RESOURCE (
                    NAME           text unique,
                    UID            text,
                    TYPE           text,
                    RECURRANCE_MAX date
                )
                """
            )

        #
        # TIMESPAN table tracks (expanded) timespans for resources
        #   NAME: Related resource (RESOURCE foreign key)
        #   FLOAT: 'Y' if start/end are floating, 'N' otherwise
        #   START: Start date
        #   END: End date
        #
        q.execute(
            """
            create table TIMESPAN (
                NAME  text,
                FLOAT text(1),
                START date,
                END   date
            )
            """
        )

    def _add_to_db(self, name, calendar, cursor = None):
        """
        Records the given calendar resource in the index with the given name.
        Resource names and UIDs must both be unique; only one resource name may
        be associated with any given UID and vice versa.
        NB This method does not commit the changes to the db - the caller
        MUST take care of that
        @param name: the name of the resource to add.
        @param calendar: a L{Calendar} object representing the resource
            contents.
        """
        uid = calendar.resourceUID()

        expand_max = datetime.date.today() + default_future_expansion_duration

        instances = calendar.expandTimeRanges(expand_max)
        for key in instances:
            instance = instances[key]
            float = ('N', 'Y')[instance.start.tzinfo is None]
            self._db_execute(
                """
                insert into TIMESPAN (NAME, FLOAT, START, END)
                values (:1, :2, :3, :4)
                """, name, float, normalizeForIndex(instance.start), normalizeForIndex(instance.end)
            )

        self._db_execute(
            """
            insert into RESOURCE (NAME, UID, TYPE, RECURRANCE_MAX)
            values (:1, :2, :3, :4)
            """, name, uid, calendar.resourceType(), instances.limit
        )
    
    def _delete_from_db(self, name, uid):
        """
        Deletes the specified entry from all dbs.
        @param name: the name of the resource to delete.
        @param uid: the uid of the resource to delete.
        """
        self._db_execute("delete from TIMESPAN where NAME = :1", name)
        self._db_execute("delete from RESOURCE where NAME = :1", name)
    
class Index (CalendarIndex):
    """
    Calendar collection index - regular collection that enforces CalDAV UID uniqueness requirement.
    """
    
    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index. C{resource} must be a calendar collection (ie.
            C{resource.isPseudoCalendarCollection()} returns C{True}.)
        """
        assert resource.isCalendarCollection(), "non-calendar collection resource %s has no index." % (resource,)
        super(Index, self).__init__(resource)

    #
    # A dict of sets. The dict keys are calendar collection paths,
    # and the sets contains reserved UIDs for each path.
    #
    _reservations = {}
    
    def reserveUID(self, uid):
        """
        Reserve a UID for this index's resource.
        @param uid: the UID to reserve
        @raise ReservationError: if C{uid} is already reserved
        """
        fpath = self.resource.fp.path

        if fpath in self._reservations and uid in self._reservations[fpath]:
            raise ReservationError(
                "UID %s already reserved for calendar collection %s."
                % (uid, self.resource)
            )

        if fpath not in self._reservations:
            self._reservations[fpath] = set()

        self._reservations[fpath].add(uid)
    
    def unreserveUID(self, uid):
        """
        Unreserve a UID for this index's resource.
        @param uid: the UID to reserve
        @raise ReservationError: if C{uid} is not reserved
        """
        fpath = self.resource.fp.path

        if fpath not in self._reservations or uid not in self._reservations[fpath]:
            raise ReservationError(
                "UID %s is not reserved for calendar collection %s."
                % (uid, self.resource)
            )

        self._reservations[fpath].remove(uid)
    
    def isReservedUID(self, uid):
        """
        Check to see whether a UID is reserved.
        @param uid: the UID to check
        @return: True if C{uid} is reserved, False otherwise.
        """
        fpath = self.resource.fp.path

        return fpath in self._reservations and uid in self._reservations[fpath]
        
    def isAllowedUID(self, uid, *names):
        """
        Checks to see whether to allow an operation with adds the the specified
        UID is allowed to the index.  Specifically, the operation may not
        violate the constraint that UIDs must be unique, and the UID must not
        be reserved.
        @param uid: the UID to check
        @param names: the names of resources being replaced or deleted by the
            operation; UIDs associated with these resources are not checked.
        @return: True if the UID is not in the index and is not reserved,
            False otherwise.
        """
        rname = self.resourceNameForUID(uid)
        return not self.isReservedUID(uid) and (rname is None or rname in names)
 
    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return collection_types["Calendar"]
        
    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """
        
        # Create database where the RESOURCE table has unique UID column.
        self._db_init_data_tables_base(q, True)

        #
        # Populate the DB with data from already existing resources.
        # This allows for index recovery if the DB file gets
        # deleted.
        #
        fp = self.resource.fp
        for name in fp.listdir():
            if name == db_basename: continue
            stream = fp.child(name).open()
            try:
                # FIXME: This is blocking I/O
                try:
                    calendar = Component.fromStream(stream)
                    calendar.validateForCalDAV()
                except ValueError:
                    log.err("Non-calendar resource: %s" % (name,))
                else:
                    log.msg("Indexing resource: %s" % (name,))
                    self.addResource(name, calendar, True)
            finally:
                stream.close()
        
        # Do commit outside of the loop for better performance
        self._db_commit()

class IndexSchedule (CalendarIndex):
    """
    Schedule collection index - does not require UID uniqueness.
    """
    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index. C{resource} must be a calendar collection (ie.
            C{resource.isPseudoCalendarCollection()} returns C{True}.)
        """
        assert resource.isPseudoCalendarCollection() and not resource.isCalendarCollection(), "non-calendar collection resource %s has no index." % (resource,)
        super(IndexSchedule, self).__init__(resource)

    def reserveUID(self, uid): #@UnusedVariable
        """
        Reserve a UID for this index's resource.
        @param uid: the UID to reserve
        @raise ReservationError: if C{uid} is already reserved
        """
        
        # iTIP does not require unique UIDs
        pass
    
    def unreserveUID(self, uid): #@UnusedVariable
        """
        Unreserve a UID for this index's resource.
        @param uid: the UID to reserve
        @raise ReservationError: if C{uid} is not reserved
        """
        
        # iTIP does not require unique UIDs
        pass
    
    def isReservedUID(self, uid): #@UnusedVariable
        """
        Check to see whether a UID is reserved.
        @param uid: the UID to check
        @return: True if C{uid} is reserved, False otherwise.
        """
        
        # iTIP does not require unique UIDs
        return False
        
    def isAllowedUID(self, uid, *names): #@UnusedVariable
        """
        Checks to see whether to allow an operation with adds the the specified
        UID is allowed to the index.  Specifically, the operation may not
        violate the constraint that UIDs must be unique, and the UID must not
        be reserved.
        @param uid: the UID to check
        @param names: the names of resources being replaced or deleted by the
            operation; UIDs associated with these resources are not checked.
        @return: True if the UID is not in the index and is not reserved,
            False otherwise.
        """
        
        # iTIP does not require unique UIDs
        return True
 
    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return collection_types["iTIP"]
        
    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """
        
        # Create database where the RESOURCE table has a UID column that is not unique.
        self._db_init_data_tables_base(q, False)

        #
        # Populate the DB with data from already existing resources.
        # This allows for index recovery if the DB file gets
        # deleted.
        #
        fp = self.resource.fp
        for name in fp.listdir():
            if name == db_basename: continue
            stream = fp.child(name).open()
            try:
                # FIXME: This is blocking I/O
                try:
                    calendar = Component.fromStream(stream)
                    calendar.validCalendarForCalDAV()
                    calendar.validateComponentsForCalDAV(True)
                except ValueError:
                    log.err("Non-calendar resource: %s" % (name,))
                else:
                    log.msg("Indexing resource: %s" % (name,))
                    self.addResource(name, calendar)
            finally:
                stream.close()
