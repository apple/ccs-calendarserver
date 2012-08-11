##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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
Test cases for L{twext.enterprise.dal.record}.
"""

import sqlite3

from twisted.internet.defer import inlineCallbacks

from twisted.trial.unittest import TestCase

from twext.enterprise.dal.record import fromTable, ReadOnly
from twext.enterprise.dal.syntax import SQLITE_DIALECT

from twext.enterprise.dal.test.test_parseschema import SchemaTestHelper
from twext.enterprise.adbapi2 import ConnectionPool
from twext.enterprise.dal.syntax import SchemaSyntax

# from twext.enterprise.dal.syntax import


sth = SchemaTestHelper()
sth.id = lambda : __name__
schemaString = """
create table ALPHA (BETA integer primary key, GAMMA text);
"""
testSchema = SchemaSyntax(sth.schemaFromString(schemaString))



class TestRecord(fromTable(testSchema.ALPHA)):
    """
    A sample test record.
    """



class TestCRUD(TestCase):
    """
    Tests for creation, mutation, and deletion operations.
    """

    def setUp(self):
        sqlitename = self.mktemp()
        def connectionFactory(label=self.id()):
            return sqlite3.connect(sqlitename)
        con = connectionFactory()
        con.execute(schemaString)
        con.commit()
        self.pool = ConnectionPool(connectionFactory, paramstyle='numeric',
                                   dialect=SQLITE_DIALECT)
        self.pool.startService()
        self.addCleanup(self.pool.stopService)


    @inlineCallbacks
    def test_simpleLoad(self):
        """
        Loading an existing row from the database by its primary key will
        populate its attributes from columns of the corresponding row in the
        database.
        """
        txn = self.pool.connection()
        yield txn.execSQL("insert into ALPHA values (:1, :2)", [234, "one"])
        yield txn.execSQL("insert into ALPHA values (:1, :2)", [456, "two"])
        rec = yield TestRecord.load(txn, 456)
        self.assertIsInstance(rec, TestRecord)
        self.assertEquals(rec.beta, 456)
        self.assertEquals(rec.gamma, "two")
        rec2 = yield TestRecord.load(txn, 234)
        self.assertIsInstance(rec2, TestRecord)
        self.assertEqual(rec2.beta, 234)
        self.assertEqual(rec2.gamma, "one")


    @inlineCallbacks
    def test_simpleCreate(self):
        """
        When a record object is created, a row with matching column values will
        be created in the database.
        """
        txn = self.pool.connection()
        rec = yield TestRecord.create(txn, beta=3, gamma=u'epsilon')
        self.assertEquals(rec.beta, 3)
        self.assertEqual(rec.gamma, u'epsilon')
        rows = yield txn.execSQL("select BETA, GAMMA from ALPHA")
        self.assertEqual(rows, [tuple([3, u'epsilon'])])


    @inlineCallbacks
    def test_attributesArentMutableYet(self):
        """
        Changing attributes on a database object is not supported yet, because
        it's not entirely clear when to flush the SQL to the database.
        Instead, for the time being, use C{.update}.  When you attempt to set
        an attribute, an error will be raised informing you of this fact, so
        that the error is clear.
        """
        txn = self.pool.connection()
        rec = yield TestRecord.create(txn, beta=7, gamma=u'what')
        def setit():
            rec.beta = 12
        ro = self.assertRaises(ReadOnly, setit)
        self.assertEqual(rec.beta, 7)
        self.assertIn("SQL-backed attribute 'TestRecord.beta' is read-only. "
                      "Use '.update(...)' to modify attributes.", str(ro))


    @inlineCallbacks
    def test_simpleUpdate(self):
        """
        L{Record.update} will change the values on the record and in te
        database.
        """
        txn = self.pool.connection()
        rec = yield TestRecord.create(txn, beta=3, gamma=u'epsilon')
        yield rec.update(gamma=u'otherwise')
        self.assertEqual(rec.gamma, u'otherwise')
        yield txn.commit()
        # Make sure that it persists.
        txn = self.pool.connection()
        rec = yield TestRecord.load(txn, 3)
        self.assertEqual(rec.gamma, u'otherwise')



