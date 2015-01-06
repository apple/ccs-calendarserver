##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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

from txdav.common.datastore.sql_dump import dumpSchema
from twext.enterprise.dal.parseschema import schemaFromString

"""
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""

from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from txdav.common.datastore.test.util import theStoreBuilder, \
    StubNotifierFactory

class SQLDump(TestCase):
    """
    Tests for L{sql_dump}.
    """

    @inlineCallbacks
    def setUp(self):
        TestCase.setUp(self)

        self.store = yield theStoreBuilder.buildStore(
            self, {"push": StubNotifierFactory()}, enableJobProcessing=False
        )


    @inlineCallbacks
    def cleanUp(self):
        startTxn = self.store.newTransaction("test_sql_dump")
        yield startTxn.execSQL("set search_path to public;")
        yield startTxn.execSQL("drop schema test_sql_dump cascade;")
        yield startTxn.commit()


    @inlineCallbacks
    def _loadSchema(self, schema):
        """
        Use the postgres schema mechanism to do tests under a separate "namespace"
        in postgres that we can quickly wipe clean afterwards.
        """
        startTxn = self.store.newTransaction("test_sql_dump")
        yield startTxn.execSQL("create schema test_sql_dump;")
        yield startTxn.execSQL("set search_path to test_sql_dump;")
        yield startTxn.execSQL(schema)
        yield startTxn.commit()

        self.addCleanup(self.cleanUp)


    @inlineCallbacks
    def _schemaCheck(self, schema, schema_bad):

        # Load old schema and populate with data
        yield self._loadSchema(schema)

        txn = self.store.newTransaction("loadData")
        dumped = yield dumpSchema(txn, "test", schemaname="test_sql_dump")
        yield txn.commit()

        parsed = schemaFromString(schema)
        self.assertEqual(parsed.compare(dumped), [])

        parsed_bad = schemaFromString(schema_bad)
        self.assertNotEqual(parsed_bad.compare(dumped), [])


    @inlineCallbacks
    def test_pkey_column(self):

        schema = """
CREATE TABLE FOO (
    ID1 integer primary key,
    ID2 integer not null
);
"""

        schema_bad = """
CREATE TABLE FOO (
    ID1 integer primary key,
    ID2 integer
);
"""

        yield self._schemaCheck(schema, schema_bad)


    @inlineCallbacks
    def test_pkey_table(self):

        schema = """
CREATE TABLE FOO (
    ID1 integer not null,
    ID2 integer not null,

    primary key (ID1)
);
"""

        schema_bad = """
CREATE TABLE FOO (
    ID1 integer,
    ID2 integer,

    primary key (ID1)
);
"""

        yield self._schemaCheck(schema, schema_bad)


    @inlineCallbacks
    def test_multiple_pkey_table(self):

        schema = """
CREATE TABLE FOO (
    ID1 integer not null,
    ID2 integer not null,
    ID3 integer not null,

    primary key (ID1, ID2)
);
"""

        schema_bad = """
CREATE TABLE FOO (
    ID1 integer,
    ID2 integer,
    ID3 integer,

    primary key (ID1, ID2)
);
"""

        yield self._schemaCheck(schema, schema_bad)


    @inlineCallbacks
    def test_unique_column(self):

        schema = """
CREATE TABLE FOO (
    ID1 integer unique,
    ID2 integer not null
);
"""

        schema_bad = """
CREATE TABLE FOO (
    ID1 integer unique,
    ID2 integer
);
"""

        yield self._schemaCheck(schema, schema_bad)


    @inlineCallbacks
    def test_unique_table(self):

        schema = """
CREATE TABLE FOO (
    ID1 integer,
    ID2 integer not null,

    unique (ID1)
);
"""

        schema_bad = """
CREATE TABLE FOO (
    ID1 integer,
    ID2 integer,

    unique (ID1)
);
"""

        yield self._schemaCheck(schema, schema_bad)


    @inlineCallbacks
    def test_multiple_unique_table(self):

        schema = """
CREATE TABLE FOO (
    ID1 integer,
    ID2 integer,
    ID3 integer not null,

    unique (ID1, ID2)
);
"""

        schema_bad = """
CREATE TABLE FOO (
    ID1 integer,
    ID2 integer,
    ID3 integer,

    unique (ID1, ID2)
);
"""

        yield self._schemaCheck(schema, schema_bad)
