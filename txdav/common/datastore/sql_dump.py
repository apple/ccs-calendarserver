# -*- test-case-name: txdav.common.datastore.test.test_sql_tables -*-
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

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.enterprise.dal.model import Schema, Table, Column, Sequence, Function
from twext.enterprise.dal.parseschema import addSQLToSchema

"""
Dump a postgres DB into an L{Schema} model object.
"""

@inlineCallbacks
def dumpSchema(txn, title, schemaname="public"):
    """
    Generate the L{Schema}.
    """

    schemaname = schemaname.lower()

    schema = Schema(title)
    tables = {}

    # Tables
    rows = yield txn.execSQL("select table_name from information_schema.tables where table_schema = '%s';" % (schemaname,))
    for row in rows:
        name = row[0]
        table = Table(schema, name)
        tables[name] = table

        # Columns
        rows = yield txn.execSQL("select column_name from information_schema.columns where table_schema = '%s' and table_name = '%s';" % (schemaname, name,))
        for row in rows:
            name = row[0]
            # TODO: figure out the type
            column = Column(table, name, None)
            table.columns.append(column)

    # Indexes
    # TODO: handle implicit indexes created via primary key() and unique() statements within CREATE TABLE
    rows = yield txn.execSQL("select indexdef from pg_indexes where schemaname = '%s';" % (schemaname,))
    for indexdef in rows:
        addSQLToSchema(schema, indexdef[0].replace("%s." % (schemaname,), ""))

    # Sequences
    rows = yield txn.execSQL("select sequence_name from information_schema.sequences where sequence_schema = '%s';" % (schemaname,))
    for row in rows:
        name = row[0]
        Sequence(schema, name)

    # Functions
    rows = yield txn.execSQL("select routine_name from information_schema.routines where routine_schema = '%s';" % (schemaname,))
    for row in rows:
        name = row[0]
        Function(schema, name)

    returnValue(schema)
