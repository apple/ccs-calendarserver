##
# Copyright (c) 2007 Apple Inc. All rights reserved.
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

from twistedcaldav.sql import AbstractSQLDatabase

import twistedcaldav.test.util

class SQL (twistedcaldav.test.util.TestCase):
    """
    Test abstract SQL DB class
    """
    
    class TestDB(AbstractSQLDatabase):
        
        def __init__(self, path, autocommit=False):
            super(SQL.TestDB, self).__init__(path, autocommit=autocommit)

        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return 1
            
        def _db_type(self):
            """
            @return: the collection type assigned to this index.
            """
            return "TESTTYPE"
            
        def _db_init_data_tables(self, q):
            """
            Initialise the underlying database tables.
            @param q:           a database cursor to use.
            """
    
            #
            # TESTTYPE table
            #
            q.execute(
                """
                create table TESTTYPE (
                    KEY         text unique,
                    VALUE       text
                )
                """
            )

    def test_connect(self):
        """
        Connect to database and create table
        """
        db = SQL.TestDB(self.mktemp())
        self.assertFalse(hasattr(db, "_db_connection"))
        self.assertTrue(db._db() is not None)
        self.assertTrue(db._db_connection is not None)

    def test_connect_autocommit(self):
        """
        Connect to database and create table
        """
        db = SQL.TestDB(self.mktemp(), autocommit=True)
        self.assertFalse(hasattr(db, "_db_connection"))
        self.assertTrue(db._db() is not None)
        self.assertTrue(db._db_connection is not None)

    def test_readwrite(self):
        """
        Add a record, search for it
        """
        db = SQL.TestDB(self.mktemp())
        db._db().execute("INSERT into TESTTYPE (KEY, VALUE) values (:1, :2)", ("FOO", "BAR",))
        db._db_commit()
        q = db._db().execute("SELECT * from TESTTYPE")
        items = [i for i in q.fetchall()]
        self.assertEqual(items, [("FOO", "BAR")])

    def test_readwrite_autocommit(self):
        """
        Add a record, search for it
        """
        db = SQL.TestDB(self.mktemp(), autocommit=True)
        db._db().execute("INSERT into TESTTYPE (KEY, VALUE) values (:1, :2)", ("FOO", "BAR",))
        q = db._db().execute("SELECT * from TESTTYPE")
        items = [i for i in q.fetchall()]
        self.assertEqual(items, [("FOO", "BAR")])

    def test_readwrite_cursor(self):
        """
        Add a record, search for it
        """
        db = SQL.TestDB(self.mktemp())
        db._db_execute("INSERT into TESTTYPE (KEY, VALUE) values (:1, :2)", "FOO", "BAR")
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [("FOO", "BAR")])

    def test_readwrite_cursor_autocommit(self):
        """
        Add a record, search for it
        """
        db = SQL.TestDB(self.mktemp(), autocommit=True)
        db._db_execute("INSERT into TESTTYPE (KEY, VALUE) values (:1, :2)", "FOO", "BAR")
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [("FOO", "BAR")])

    def test_readwrite_rollback(self):
        """
        Add a record, search for it
        """
        db = SQL.TestDB(self.mktemp())
        db._db_execute("INSERT into TESTTYPE (KEY, VALUE) values (:1, :2)", "FOO", "BAR")
        db._db_rollback()
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [])

    def test_close(self):
        """
        Close database
        """
        db = SQL.TestDB(self.mktemp())
        self.assertFalse(hasattr(db, "_db_connection"))
        self.assertTrue(db._db() is not None)
        db._db_close()
        self.assertFalse(hasattr(db, "_db_connection"))
        db._db_close()
