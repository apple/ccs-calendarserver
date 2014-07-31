# #
# Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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
# #

from twext.enterprise.dal.parseschema import schemaFromPath
from twisted.python.modules import getModule
from twisted.trial.unittest import TestCase
import re

"""
Tests for L{txdav.common.datastore.sql}.
"""

class SQLSchemaFiles(TestCase):
    """
    Tests for txdav.common.datastore.sql_schema having complete information. Note that upgrade files are checked elsewhere.
    """

    def versionFromSchema(self, filePath):
        current_schema = filePath.getContent()
        found = re.search("insert into CALENDARSERVER values \('VERSION', '(\d+)'\);", current_schema)
        if found is None:
            found = re.search("insert into CALENDARSERVER \(NAME, VALUE\) values \('VERSION', '(\d+)'\);", current_schema)
            if found is None:
                self.fail("Could not find version string in %s" % (filePath.path,))

        return int(found.group(1))


    def test_old_files(self):
        """
        Make sure txdav.common.datastore.sql_schema.old contains all the appropriate old versions
        """

        sqlSchema = getModule(__name__).filePath.parent().sibling("sql_schema")
        currentSchema = sqlSchema.child("current.sql")
        current_version = self.versionFromSchema(currentSchema)
        current_set = set([i for i in range(3, current_version)])

        oldDirectory = sqlSchema.child("old")

        for child in oldDirectory.children():
            if child.basename().startswith("."):
                continue
            old_set = set()
            for oldVersion in child.children():
                if oldVersion.basename().startswith("."):
                    continue
                found = re.search("v(\d+).sql", oldVersion.basename())
                if found is None:
                    self.fail("%s is not a valid old sql file" % (oldVersion))
                old_set.add(int(found.group(1)))
            self.assertEqual(current_set, old_set, msg="Missing old schema file for dialect: %s" % (child.basename(),))


    def test_old_files_consistent(self):
        """
        Make sure txdav.common.datastore.sql_schema.old contains all the appropriate old versions
        """

        sqlSchema = getModule(__name__).filePath.parent().sibling("sql_schema")
        oldDirectory = sqlSchema.child("old")

        for child in oldDirectory.children():
            if child.basename().startswith("."):
                continue
            for oldVersion in child.children():
                if oldVersion.basename().startswith("."):
                    continue
                found = re.search("v(\d+).sql", oldVersion.basename())
                if found is None:
                    self.fail("%s is not a valid old sql file" % (oldVersion))
                old_name_version = int(found.group(1))
                old_version = self.versionFromSchema(oldVersion)
                self.assertEqual(old_name_version, old_version, "Name of schema file does not match actual schema version: %s" % (oldVersion.path,))


    def test_current_oracle(self):
        """
        Make sure current-oracle-dialect.sql matches current.sql
        """

        sqlSchema = getModule(__name__).filePath.parent().sibling("sql_schema")

        currentSchema = sqlSchema.child("current.sql")
        current_version = self.versionFromSchema(currentSchema)

        currentOracleSchema = sqlSchema.child("current-oracle-dialect.sql")
        current_oracle_version = self.versionFromSchema(currentOracleSchema)

        self.assertEqual(current_version, current_oracle_version)

        mismatched = schemaFromPath(currentSchema).compare(schemaFromPath(currentOracleSchema))
        self.assertEqual(len(mismatched), 0, msg=", ".join(mismatched))


    def test_schema_compare(self):

        sqlSchema = getModule(__name__).filePath.parent().sibling("sql_schema")

        # Test with same schema
        currentSchema = schemaFromPath(sqlSchema.child("current.sql"))
        duplicateSchema = schemaFromPath(sqlSchema.child("current.sql"))
        mismatched = currentSchema.compare(duplicateSchema)
        self.assertEqual(len(mismatched), 0)

        # Test with same schema
        v6Schema = schemaFromPath(sqlSchema.child("old").child("postgres-dialect").child("v6.sql"))
        v5Schema = schemaFromPath(sqlSchema.child("old").child("postgres-dialect").child("v5.sql"))
        mismatched = v6Schema.compare(v5Schema)
        self.assertEqual(len(mismatched), 4, msg="\n".join(mismatched))


    def test_references_index(self):
        """
        Make sure current-oracle-dialect.sql matches current.sql
        """

        schema = schemaFromPath(getModule(__name__).filePath.parent().sibling("sql_schema").child("current.sql"))

        # Get index details
        indexed_columns = set()
        for index in schema.pseudoIndexes():
            indexed_columns.add("%s.%s" % (index.table.name, index.columns[0].name,))
        # print indexed_columns

        # Look at each table
        failures = []
        for table in schema.tables:
            for column in table.columns:
                if column.references is not None:
                    id = "%s.%s" % (table.name, column.name,)
                    if id not in indexed_columns:
                        failures.append(id)

        self.assertEqual(len(failures), 0, msg="Missing index for references columns: %s" % (", ".join(sorted(failures))))


    def test_primary_keys(self):
        """
        Make sure current-oracle-dialect.sql matches current.sql
        """

        schema = schemaFromPath(getModule(__name__).filePath.parent().sibling("sql_schema").child("current.sql"))

        # Set of tables for which missing primary key is allowed
        table_exceptions = (
            "ADDRESSBOOK_OBJECT_REVISIONS",
            "CALENDAR_OBJECT_REVISIONS",
            "NOTIFICATION_OBJECT_REVISIONS",
            "PERUSER",
        )
        # Look at each table
        failures = []
        for table in schema.tables:
            if table.primaryKey is None and table.name not in table_exceptions:
                failures.append(table.name)

        self.assertEqual(len(failures), 0, msg="Missing primary key for tables: %s" % (", ".join(sorted(failures))))
