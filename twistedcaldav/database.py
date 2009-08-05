##
# Copyright (c) 2009 Apple Inc. All rights reserved.
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

from twistedcaldav.log import Logger

from twisted.enterprise.adbapi import ConnectionPool
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.threadpool import ThreadPool

import thread

"""
Generic ADAPI database access object.
"""

__all__ = [
    "AbstractADBAPIDatabase",
]

log = Logger()

class ConnectionClosingThreadPool(ThreadPool):
    """
    A ThreadPool that closes connections for each worker thread
    """
    
    def _worker(self):
        log.debug("Starting ADBAPI thread: %s" % (thread.get_ident(),))
        ThreadPool._worker(self)
        self._closeConnection()

    def _closeConnection(self):
        
        tid = thread.get_ident()
        log.debug("Closing ADBAPI thread: %s" % (tid,))

        conn = self.pool.connections.get(tid)
        self.pool._close(conn)
        del self.pool.connections[tid]

class AbstractADBAPIDatabase(object):
    """
    A generic SQL database.
    """

    def __init__(self, dbID, dbapiName, dbapiArgs, persistent, **kwargs):
        """
        
        @param pool: the ADAPI ConnectionPool to use.
        @type dbpath: L{ConnectionPool}
        @param persistent: C{True} if the data in the DB must be perserved during upgrades,
            C{False} if the DB data can be re-created from an external source.
        @type persistent: bool
        """
        self.dbID = dbID
        self.dbapiName = dbapiName
        self.dbapiArgs = dbapiArgs
        self.dbapikwargs = kwargs

        self.persistent = persistent
        
        self.initialized = False

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.pool)

    @inlineCallbacks
    def open(self):
        """
        Access the underlying database.
        @return: a db2 connection object for this index's underlying data store.
        """
        if not self.initialized:

            self.pool = ConnectionPool(self.dbapiName, *self.dbapiArgs, **self.dbapikwargs)
            
            # sqlite3 is not thread safe which means we have to close the sqlite3 connections in the same thread that
            # opened them. We need a special thread pool class that has a thread worker function that does a close
            # when a thread is closed.
            if self.dbapiName == "sqlite3":
                self.pool.threadpool.stop()
                self.pool.threadpool = ConnectionClosingThreadPool(1, 1)
                self.pool.threadpool.start()
                self.pool.threadpool.pool = self.pool

            #
            # Set up the schema
            #
            # Create CALDAV table if needed

            test = (yield self._test_schema_table())
            if test:
                version = (yield self._db_value_for_sql("select VALUE from CALDAV where KEY = 'SCHEMA_VERSION'"))
                dbtype = (yield self._db_value_for_sql("select VALUE from CALDAV where KEY = 'TYPE'"))

                if (version != self._db_version()) or (dbtype != self._db_type()):

                    if dbtype != self._db_type():
                        log.err("Database %s has different type (%s vs. %s)"
                                % (self.dbID, dbtype, self._db_type()))

                        # Delete this index and start over
                        yield self._db_remove()
                        yield self._db_init()

                    elif version != self._db_version():
                        log.err("Database %s has different schema (v.%s vs. v.%s)"
                                % (self.dbID, version, self._db_version()))
                        
                        # Upgrade the DB
                        yield self._db_upgrade(version)

            else:
                yield self._db_init()
            self.initialized = True

    def close(self):
        
        if self.initialized:
            self.pool.close()
            self.pool = None
            self.initialized = False

    @inlineCallbacks
    def execute(self, sql, *query_params):
        
        if not self.initialized:
            yield self.open()

        result = (yield self._db_execute(sql, *query_params))
        returnValue(result)

    def _db_version(self):
        """
        @return: the schema version assigned to this DB.
        """
        raise NotImplementedError
        
    def _db_type(self):
        """
        @return: the collection type assigned to this DB.
        """
        raise NotImplementedError
        
    @inlineCallbacks
    def _test_schema_table(self):
        result = (yield self._db_value_for_sql("""
        select (1) from SQLITE_MASTER
         where TYPE = 'table' and NAME = 'CALDAV'
        """))
        returnValue(result)

    @inlineCallbacks
    def _db_init(self):
        """
        Initialise the underlying database tables.
        """
        log.msg("Initializing database %s" % (self.dbID,))

        # TODO we need an exclusive lock of some kind here to prevent a race condition
        # in which multiple processes try to create the tables.
        

        yield self._db_init_schema_table()
        yield self._db_init_data_tables()
        yield self._db_recreate()

    @inlineCallbacks
    def _db_init_schema_table(self):
        """
        Initialise the underlying database tables.
        @param db_filename: the file name of the index database.
        @param q:           a database cursor to use.
        """

        #
        # CALDAV table keeps track of our schema version and type
        #
        yield self._db_execute(
            """
            create table CALDAV (
                KEY text unique,
                VALUE text unique
            )
            """
        )
        yield self._db_execute(
            """
            insert into CALDAV (KEY, VALUE)
            values ('SCHEMA_VERSION', :1)
            """, (self._db_version(),)
        )
        yield self._db_execute(
            """
            insert into CALDAV (KEY, VALUE)
            values ('TYPE', :1)
            """, (self._db_type(),)
        )

    def _db_init_data_tables(self):
        """
        Initialise the underlying database tables.
        """
        raise NotImplementedError

    def _db_recreate(self):
        """
        Recreate the database tables.
        """

        # Implementations can override this to re-create data
        pass

    @inlineCallbacks
    def _db_upgrade(self, old_version):
        """
        Upgrade the database tables.
        """
        
        if self.persistent:
            yield self._db_upgrade_data_tables(old_version)
            yield self._db_upgrade_schema()
        else:
            # Non-persistent DB's by default can be removed and re-created. However, for simple
            # DB upgrades they SHOULD override this method and handle those for better performance.
            yield self._db_remove()
            yield self._db_init()
    
    def _db_upgrade_data_tables(self, old_version):
        """
        Upgrade the data from an older version of the DB.
        """
        # Persistent DB's MUST override this method and do a proper upgrade. Their data
        # cannot be thrown away.
        raise NotImplementedError("Persistent databases MUST support an upgrade method.")

    @inlineCallbacks
    def _db_upgrade_schema(self):
        """
        Upgrade the stored schema version to the current one.
        """
        yield self._db_execute("insert or replace into CALDAV (KEY, VALUE) values ('SCHEMA_VERSION', :1)", (self._db_version(),))

    @inlineCallbacks
    def _db_remove(self):
        """
        Remove all database information (all the tables)
        """
        yield self._db_remove_data_tables()
        yield self._db_remove_schema()

    def _db_remove_data_tables(self):
        """
        Remove all the data from an older version of the DB.
        """
        raise NotImplementedError("Each database must remove its own tables.")

    @inlineCallbacks
    def _db_remove_schema(self):
        """
        Remove the stored schema version table.
        """
        yield self._db_execute("drop table CALDAV")

    @inlineCallbacks
    def _db_values_for_sql(self, sql, *query_params):
        """
        Execute an SQL query and obtain the resulting values.
        @param sql: the SQL query to execute.
        @param query_params: parameters to C{sql}.
        @return: an interable of values in the first column of each row
            resulting from executing C{sql} with C{query_params}.
        @raise AssertionError: if the query yields multiple columns.
        """
        
        results = (yield self.pool.runQuery(sql, *query_params))
        returnValue(tuple([row[0] for row in results]))

    @inlineCallbacks
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
        for row in (yield self._db_values_for_sql(sql, *query_params)):
            assert value is None, "Multiple values in DB for %s %s" % (sql, query_params)
            value = row
        returnValue(value)

    @inlineCallbacks
    def _db_execute(self, sql, *query_params):
        """
        Execute an SQL query and obtain the resulting values.
        @param sql: the SQL query to execute.
        @param query_params: parameters to C{sql}.
        @return: an iterable of tuples for each row resulting from executing
            C{sql} with C{query_params}.
        """
        
        results = (yield self.pool.runQuery(sql, *query_params))
        returnValue(results)
