##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Abstract SQLite Index base class. This class will be sub-classed for the
different types of index we need in the server.
"""

__all__ = ["AbstractIndex"]

import os

try:
    import sqlite3 as sqlite
except ImportError:
    from pysqlite2 import dbapi2 as sqlite

from twisted.python import log

db_basename = ".db.sqlite"

class AbstractIndex(object):
    def __init__(self, resource, returnUTF8 = True):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index.)
        """
        self.resource = resource
        self.utf8 = returnUTF8

    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        raise NotImplementedError
        
    def _db_type(self):
        """
        @return: the type assigned to this index.
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
            if self.utf8:
                self._db_connection.text_factory = str

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

                    if (version != self._db_version()) or (type != self._db_type()):
                        if version != self._db_version():
                            log.err("Index %s has different schema (v.%s vs. v.%s)"
                                    % (db_filename, version, self._db_version()))
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
        self._db_recreate()

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
            """, [self._db_version()]
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

    def _db_recreate(self):
        """
        Recreate the database tables.
        """
        raise NotImplementedError

    def _add_to_db(self):
        """
        Add a record to the database.
        """
        raise NotImplementedError
    
    def _delete_from_db(self):
        """
        Delete a record from the database.
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

    def _db_commit  (self):
        self._db_connection.commit()

    def _db_rollback(self):
        self._db_connection.rollback()

