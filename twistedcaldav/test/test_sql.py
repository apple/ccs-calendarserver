##
# Copyright (c) 2007-2013 Apple Inc. All rights reserved.
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

from twistedcaldav.sql import AbstractSQLDatabase

import twistedcaldav.test.util

from threading import Thread
import time
import os

class SQL (twistedcaldav.test.util.TestCase):
    """
    Test abstract SQL DB class
    """

    class TestDB(AbstractSQLDatabase):

        def __init__(self, path, persistent=False, autocommit=False, version="1"):
            self.version = version
            super(SQL.TestDB, self).__init__(path, persistent, autocommit=autocommit)

        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return self.version

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


    class TestDBRecreateUpgrade(TestDB):

        class RecreateDBException(Exception):
            pass
        class UpgradeDBException(Exception):
            pass

        def __init__(self, path, persistent=False, autocommit=False):
            super(SQL.TestDBRecreateUpgrade, self).__init__(path, persistent, autocommit=autocommit, version="2")

        def _db_recreate(self, do_commit=True):
            raise self.RecreateDBException()


    class TestDBCreateIndexOnUpgrade(TestDB):

        def __init__(self, path, persistent=False, autocommit=False):
            super(SQL.TestDBCreateIndexOnUpgrade, self).__init__(path, persistent, autocommit=autocommit, version="2")

        def _db_upgrade_data_tables(self, q, old_version):
            q.execute(
                """
                create index TESTING on TESTTYPE (VALUE)
                """
            )


    class TestDBPauseInInit(TestDB):

        def _db_init(self, db_filename, q):

            time.sleep(1)
            super(SQL.TestDBPauseInInit, self)._db_init(db_filename, q)


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


    def test_duplicate_create(self):
        dbname = self.mktemp()

        class DBThread(Thread):

            def run(self):
                try:
                    db = SQL.TestDBPauseInInit(dbname)
                    db._db()
                    self.result = True
                except:
                    self.result = False

        t1 = DBThread()
        t2 = DBThread()
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertTrue(t1.result)
        self.assertTrue(t2.result)


    def test_version_upgrade_nonpersistent(self):
        """
        Connect to database and create table
        """
        db = SQL.TestDB(self.mktemp(), autocommit=True)
        self.assertTrue(db._db() is not None)
        db._db_execute("INSERT into TESTTYPE (KEY, VALUE) values (:1, :2)", "FOO", "BAR")
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [("FOO", "BAR")])
        db._db_close()
        db = None

        db = SQL.TestDBRecreateUpgrade(self.mktemp(), autocommit=True)
        self.assertRaises(SQL.TestDBRecreateUpgrade.RecreateDBException, db._db)
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [])


    def test_version_upgrade_persistent(self):
        """
        Connect to database and create table
        """
        db_file = self.mktemp()
        db = SQL.TestDB(db_file, persistent=True, autocommit=True)
        self.assertTrue(db._db() is not None)
        db._db_execute("INSERT into TESTTYPE (KEY, VALUE) values (:1, :2)", "FOO", "BAR")
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [("FOO", "BAR")])
        db._db_close()
        db = None

        db = SQL.TestDBRecreateUpgrade(db_file, persistent=True, autocommit=True)
        self.assertRaises(NotImplementedError, db._db)
        self.assertTrue(os.path.exists(db_file))
        db._db_close()
        db = None

        db = SQL.TestDB(db_file, persistent=True, autocommit=True)
        self.assertTrue(db._db() is not None)
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [("FOO", "BAR")])


    def test_version_upgrade_persistent_add_index(self):
        """
        Connect to database and create table
        """
        db_file = self.mktemp()
        db = SQL.TestDB(db_file, persistent=True, autocommit=True)
        self.assertTrue(db._db() is not None)
        db._db_execute("INSERT into TESTTYPE (KEY, VALUE) values (:1, :2)", "FOO", "BAR")
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [("FOO", "BAR")])
        db._db_close()
        db = None

        db = SQL.TestDBCreateIndexOnUpgrade(db_file, persistent=True, autocommit=True)
        self.assertTrue(db._db() is not None)
        items = db._db_execute("SELECT * from TESTTYPE")
        self.assertEqual(items, [("FOO", "BAR")])
