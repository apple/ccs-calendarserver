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

from twext.enterprise.dal.record import fromTable

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
        def connectionFactory(label="test"):
            return sqlite3.connect(sqlitename)
        con = connectionFactory()
        con.execute(schemaString)
        con.commit()
        self.pool = ConnectionPool(connectionFactory, paramstyle='numeric')
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
        rec = yield TestRecord.create(txn, beta=3, gamma='epsilon')
        self.assertEquals(rec.beta, 3)
        self.assertEqual(rec.gamma, 'epsilon')
        rows = yield txn.execSQL("select BETA, GAMMA from ALPHA")
        self.assertEqual(rows, [[3, 'epsilon']])



class TestQuery(object):
    """
    Tests for loading row objects from the database.
    """
