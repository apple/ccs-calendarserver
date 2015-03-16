# -*- test-case-name: txdav.common.datastore.test.test_sql_tables -*-
##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
from twext.enterprise.dal.model import Schema, Table, Column, Sequence, Function, \
    SQLType, ProcedureCall, Constraint, Index
from twext.enterprise.dal.parseschema import addSQLToSchema
from twext.enterprise.ienterprise import POSTGRES_DIALECT, ORACLE_DIALECT
import collections

"""
Dump a postgres DB into an L{Schema} model object.
"""

DTYPE_MAP_POSTGRES = {
    "character": "char",
    "character varying": "varchar",
    "timestamp without time zone": "timestamp",
}

DTYPE_MAP_ORACLE = {
    "number": "integer",
    "timestamp(6)": "timestamp",
}

DEFAULTVALUE_MAP_POSTGRES = {
    "timezone('UTC'::text, now())": ProcedureCall("timezone", ["UTC", "CURRENT_TIMESTAMP"]),
    "NULL::character varying": None,
    "false": False,
    "true": True,
}

DEFAULTVALUE_MAP_ORACLE = {
    "CURRENT_TIMESTAMP at time zone 'UTC'": ProcedureCall("timezone", ["UTC", "CURRENT_TIMESTAMP"]),
    "null": None,
}

def dumpSchema(txn, title, schemaname="public"):
    """
    Generate the L{Schema}.
    """

    if txn.dialect == POSTGRES_DIALECT:
        return dumpSchema_postgres(txn, title, schemaname)
    elif txn.dialect == ORACLE_DIALECT:
        return dumpSchema_oracle(txn, title, schemaname)



@inlineCallbacks
def dumpSchema_postgres(txn, title, schemaname="public"):
    """
    Generate the L{Schema}.
    """

    schemaname = schemaname.lower()

    schema = Schema(title)

    # Sequences
    seqs = {}
    rows = yield txn.execSQL("select sequence_name from information_schema.sequences where sequence_schema = '%s';" % (schemaname,))
    for row in rows:
        name = row[0]
        seqs[name.upper()] = Sequence(schema, name.upper())

    # Tables
    tables = {}
    rows = yield txn.execSQL("select table_name from information_schema.tables where table_schema = '%s';" % (schemaname,))
    for row in rows:
        name = row[0]
        table = Table(schema, name.upper())
        tables[name.upper()] = table

        # Columns
        rows = yield txn.execSQL("select column_name, data_type, is_nullable, character_maximum_length, column_default from information_schema.columns where table_schema = '%s' and table_name = '%s';" % (schemaname, name,))
        for name, datatype, is_nullable, charlen, default in rows:
            # TODO: figure out the type
            column = Column(table, name.upper(), SQLType(DTYPE_MAP_POSTGRES.get(datatype, datatype), charlen))
            table.columns.append(column)
            if default:
                if default.startswith("nextval("):
                    dname = default.split("'")[1].split(".")[-1]
                    column.default = seqs[dname.upper()]
                elif default in DEFAULTVALUE_MAP_POSTGRES:
                    column.default = DEFAULTVALUE_MAP_POSTGRES[default]
                else:
                    try:
                        column.default = int(default)
                    except ValueError:
                        column.default = default
            if is_nullable == "NO":
                table.tableConstraint(Constraint.NOT_NULL, [column.name, ])

    # Key columns
    keys = {}
    rows = yield txn.execSQL("select constraint_name, table_name, column_name from information_schema.key_column_usage where constraint_schema = '%s';" % (schemaname,))
    for conname, tname, cname in rows:
        keys[conname] = (tname, cname)

    # Constraints
    constraints = {}
    rows = yield txn.execSQL("select constraint_name, table_name, column_name from information_schema.constraint_column_usage where constraint_schema = '%s';" % (schemaname,))
    for conname, tname, cname in rows:
        constraints[conname] = (tname, cname)

    # References - referential_constraints
    rows = yield txn.execSQL("select constraint_name, unique_constraint_name, delete_rule from information_schema.referential_constraints where constraint_schema = '%s';" % (schemaname,))
    for conname, uconname, delete in rows:
        table = tables[keys[conname][0].upper()]
        column = table.columnNamed(keys[conname][1].upper())
        column.doesReferenceName(constraints[uconname][0].upper())
        if delete != "NO ACTION":
            column.deleteAction = delete.lower()

    # Indexes
    # TODO: handle implicit indexes created via primary key() and unique() statements within CREATE TABLE
    rows = yield txn.execSQL("select indexdef from pg_indexes where schemaname = '%s';" % (schemaname,))
    for indexdef in rows:
        addSQLToSchema(schema, indexdef[0].replace("%s." % (schemaname,), "").upper())

    # Functions
    rows = yield txn.execSQL("select routine_name from information_schema.routines where routine_schema = '%s';" % (schemaname,))
    for row in rows:
        name = row[0]
        Function(schema, name)

    returnValue(schema)



@inlineCallbacks
def dumpSchema_oracle(txn, title, schemaname="public"):
    """
    Generate the L{Schema}.
    """

    schemaname = schemaname.lower()

    schema = Schema(title)

    # Sequences
    seqs = {}
    rows = yield txn.execSQL("select sequence_name from all_sequences where sequence_owner = '%s'" % (schemaname.upper(),))
    for row in rows:
        name = row[0]
        seqs[name.upper()] = Sequence(schema, name.upper())

    # Tables
    tables = {}
    rows = yield txn.execSQL("select table_name from all_tables where owner = '%s'" % (schemaname.upper(),))
    for row in rows:
        name = row[0]
        table = Table(schema, name.upper())
        tables[name.upper()] = table

        # Columns
        rows = yield txn.execSQL("select column_name, data_type, nullable, char_length, data_default from all_tab_columns where owner = '%s' and table_name = '%s'" % (schemaname.upper(), name,))
        for name, datatype, is_nullable, charlen, default in rows:
            # TODO: figure out the type
            column = Column(table, name.upper(), SQLType(DTYPE_MAP_ORACLE.get(datatype.lower(), datatype.lower()), charlen))
            table.columns.append(column)
            if default:
                default = default.strip()
                if default.startswith("nextval("):
                    dname = default.split("'")[1].split(".")[-1]
                    column.default = seqs[dname.upper()]
                elif default in DEFAULTVALUE_MAP_ORACLE:
                    column.default = DEFAULTVALUE_MAP_ORACLE[default]
                else:
                    try:
                        column.default = int(default)
                    except ValueError:
                        column.default = default
            if is_nullable == "N":
                table.tableConstraint(Constraint.NOT_NULL, [column.name, ])

    # Constraints
    constraints = collections.defaultdict(list)
    rows = yield txn.execSQL("select constraint_name, table_name, column_name, position from all_cons_columns where owner = '%s'" % (schemaname.upper(),))
    for conname, tname, cname, position in rows:
        constraints[conname].append((tname, cname, position,))
    rows = yield txn.execSQL("select constraint_name, constraint_type, table_name, r_constraint_name, delete_rule from all_constraints where owner = '%s'" % (schemaname.upper(),))
    for conname, conntype, tname, r_constraint_name, delete_rule in rows:
        if constraints[conname][0][0].upper() in tables:
            constraint = constraints[conname]
            constraint = sorted(constraint, key=lambda x: x[2])
            table = tables[constraint[0][0].upper()]
            column_names = [item[1].upper() for item in constraint]
            columns = [table.columnNamed(column_name) for column_name in column_names]
            if conntype == "P":
                table.primaryKey = columns
            elif conntype == "U":
                table.tableConstraint(Constraint.UNIQUE, column_names)
            elif conntype == "R":
                columns[0].doesReferenceName(constraints[r_constraint_name][0][0].upper())
                if delete_rule.lower() != "no action":
                    columns[0].deleteAction = delete_rule.lower()

    # Indexed columns
    idx = collections.defaultdict(list)
    rows = yield txn.execSQL("select index_name, column_name, column_position from all_ind_columns where index_owner = '%s'" % (schemaname.upper(),))
    for index_name, column_name, column_position in rows:
        idx[index_name].append((column_name, column_position))

    # Indexes
    rows = yield txn.execSQL("select index_name, table_name, uniqueness from all_indexes where owner = '%s'" % (schemaname.upper(),))
    for index_name, table_name, uniqueness in rows:
        if table_name in tables:
            table = tables[table_name]
            column_names = [item[0].upper() for item in sorted(idx[index_name], key=lambda x: x[1])]
            columns = [table.columnNamed(column_name) for column_name in column_names]
            index = Index(schema, index_name.upper(), table, uniqueness == "UNIQUE")
            for column in columns:
                index.addColumn(column)

    returnValue(schema)
