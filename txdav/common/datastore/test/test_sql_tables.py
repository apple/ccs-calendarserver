# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Tests for the SQL Table definitions in txdav.common.datastore.sql_tables: sample
a couple of tables to make sure the schema is adequately parsed.

These aren't unit tests, they're integration tests to verify the behavior tested
by L{txdav.base.datastore.test.test_parseschema}.
"""

from cStringIO import StringIO

from twisted.python.modules import getModule
from twisted.trial.unittest import TestCase

from twext.enterprise.dal.syntax import SchemaSyntax

from txdav.common.datastore.sql_tables import schema, _translateSchema
from txdav.common.datastore.sql_tables import SchemaBroken

from twext.enterprise.dal.test.test_parseschema import SchemaTestHelper

class SampleSomeColumns(TestCase, SchemaTestHelper):
    """
    Sample some columns from the tables defined by L{schema} and verify that
    they look correct.
    """

    def translated(self, *schema):
        """
        Translate the given schema (or the default schema if no schema given)
        and return the resulting SQL as a string.
        """
        io = StringIO()
        _translateSchema(io, *schema)
        return io.getvalue()


    def assertSortaEquals(self, a, b):
        """
        Assert that two strings are equals, modulo whitespace differences.
        """
        sortaA = " ".join(a.split())
        sortaB = " ".join(b.split())
        self.assertEquals(sortaA, sortaB)


    def test_addressbookObjectResourceID(self):
        ao = schema.ADDRESSBOOK_OBJECT
        self.assertEquals(ao.RESOURCE_ID.model.name,
                          "RESOURCE_ID")


    def test_schemaTranslation(self):
        """
        Basic integration test to make sure that the current, production schema
        can be translated without errors.
        """
        self.translated()


    def test_schemaTranslationIncludesVersion(self):
        """
        _translateSchema includes 'insert' rows too.
        """

        pathObj = (
            getModule(__name__).filePath
            .parent().sibling("sql_schema").child("current.sql")
        )
        schema = pathObj.getContent()
        pos = schema.find("('VERSION', '")
        version = int(schema[pos+13])
        self.assertIn("insert into CALENDARSERVER (NAME, VALUE) "
                      "values ('VERSION', '%s');" % version,
                      self.translated())


    def test_translateSingleUnique(self):
        """
        L{_translateSchema} translates single-column 'unique' statements inline.
        """
        self.assertSortaEquals(
            self.translated(
                SchemaSyntax(
                    self.schemaFromString(
                        "create table alpha (beta integer unique)"
                    )
                )
            ),
            'create table alpha ( "beta" integer unique );'
        )


    def test_translateSingleTableUnique(self):
        """
        L{_translateSchema} translates single-column 'unique' statements inline,
        even if they were originally at the table level.
        """
        stx = SchemaSyntax(
            self.schemaFromString(
                "create table alpha (beta integer, unique(beta))"
            )
        )
        self.assertSortaEquals(
            self.translated(stx),
            'create table alpha ( "beta" integer unique );'
        )


    def test_multiTableUnique(self):
        """
        L{_translateSchema} translates multi-column 'unique' statements.
        """

        stx = SchemaSyntax(
            self.schemaFromString(
                "create table alpha ("
                "beta integer, gamma text, unique(beta, gamma))"
            )
        )
        self.assertSortaEquals(
            self.translated(stx),
            'create table alpha ( "beta" integer, "gamma" nclob, '
            'unique("beta", "gamma") );'
        )


    def test_translateSinglePrimaryKey(self):
        """
        L{_translateSchema} translates single-column 'primary key' statements
        inline.
        """
        self.assertSortaEquals(
            self.translated(
                SchemaSyntax(
                    self.schemaFromString(
                        "create table alpha (beta integer primary key)"
                    )
                )
            ),
            'create table alpha ( "beta" integer primary key );'
        )


    def test_translateSingleTablePrimaryKey(self):
        """
        L{_translateSchema} translates single-column 'primary key' statements
        inline, even if they were originally at the table level.
        """
        stx = SchemaSyntax(
            self.schemaFromString(
                "create table alpha (beta integer, primary key(beta))"
            )
        )
        self.assertSortaEquals(
            self.translated(stx),
            'create table alpha ( "beta" integer primary key );'
        )


    def test_multiTablePrimaryKey(self):
        """
        L{_translateSchema} translates multi-column 'primary key' statements.
        """

        stx = SchemaSyntax(
            self.schemaFromString(
                "create table alpha ("
                "beta integer, gamma text, primary key(beta, gamma))"
            )
        )
        self.assertSortaEquals(
            self.translated(stx),
            'create table alpha ( "beta" integer, "gamma" nclob, '
            'primary key("beta", "gamma") );'
        )


    def test_primaryKeyUniqueOrdering(self):
        """
        If a table specifies both a PRIMARY KEY and a UNIQUE constraint, the
        PRIMARY KEY will always be emitted first.
        """
        stx = SchemaSyntax(
            self.schemaFromString(
                "create table alpha ("
                "beta integer, gamma text, delta integer, "
                "unique(beta, delta), primary key(beta, gamma))"
            )
        )
        self.assertSortaEquals(
            self.translated(stx),
            'create table alpha ( '
            '"beta" integer, "gamma" nclob, "delta" integer, '
            'primary key("beta", "gamma"), unique("beta", "delta") );'
        )


    def test_anonymousCheckConstraint(self):
        """
        Named 'check' constraints are propagated through translation without
        modification.
        """
        self.assertSortaEquals(
            self.translated(SchemaSyntax(self.schemaFromString(
                            "create table alpha ( "
                            'beta integer, check(beta > 3)'
                            " );"
                        ))),
            "create table alpha ( "
            '"beta" integer, check("beta" > 3)'
            " );"
        )


    def test_namedCheckConstraint(self):
        """
        Named 'check' constraints are propagated through translation without
        modification.
        """
        self.assertSortaEquals(
            self.translated(SchemaSyntax(self.schemaFromString(
                            "create table alpha ( "
                            'beta integer, constraint beta_lt_3 check(beta > 3)'
                            " );"
                        ))),
            "create table alpha ("
            '"beta" integer, constraint beta_lt_3 check("beta" > 3)'
            ");"
        )


    def test_youBrokeTheSchema(self):
        """
        Oracle table names have a 30-character limit.  Our schema translator
        simply truncates the names if necessary, but that means that you can't
        have tables whose first 30 characters differ.  L{_translateSchema}
        raises a SchemaBroken() exception if this happens.  (This test is to
        make sure L{test_schemaTranslation}, above, will actually fail if this
        happens.)
        """
        # TODO: same thing for sequences.
        schema = self.schemaFromString(
            """
            create table same_012345678012345678990123456789_1 (foo integer);
            create table same_012345678012345678990123456789_2 (bar text);
            """
        )
        self.assertRaises(
            SchemaBroken, self.translated, SchemaSyntax(schema)
        )



