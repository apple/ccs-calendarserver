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
Tests for L{twext.enterprise.dal.syntax}
"""

from twext.enterprise.dal.model import Schema
from twext.enterprise.dal.parseschema import addSQLToSchema
from twext.enterprise.dal.syntax import (
    SchemaSyntax, Select, Insert, Update, Delete, Lock, SQLFragment,
    TableMismatch, Parameter, Max, Len, NotEnoughValues
)

from twisted.trial.unittest import TestCase

class GenerationTests(TestCase):
    """
    Tests for syntactic helpers to generate SQL queries.
    """

    def setUp(self):
        s = Schema(self.id())
        addSQLToSchema(schema=s, schemaData="""
                       create table FOO (BAR integer, BAZ integer);
                       create table BOZ (QUX integer);
                       create table OTHER (BAR integer,
                                           FOO_BAR integer not null);
                       create table TEXTUAL (MYTEXT varchar(255));
                       """)
        self.schema = SchemaSyntax(s)


    def test_simplestSelect(self):
        """
        L{Select} generates a 'select' statement, by default, asking for all
        rows in a table.
        """
        self.assertEquals(Select(From=self.schema.FOO).toSQL(),
                          SQLFragment("select * from FOO", []))


    def test_simpleWhereClause(self):
        """
        L{Select} generates a 'select' statement with a 'where' clause
        containing an expression.
        """
        self.assertEquals(Select(From=self.schema.FOO,
                                 Where=self.schema.FOO.BAR == 1).toSQL(),
                          SQLFragment("select * from FOO where BAR = ?", [1]))


    def test_quotingAndPlaceholder(self):
        """
        L{Select} generates a 'select' statement with the specified placeholder
        syntax and quoting function.
        """
        self.assertEquals(Select(From=self.schema.FOO,
                                 Where=self.schema.FOO.BAR == 1).toSQL(
                                 placeholder="*",
                                 quote=lambda partial: partial.replace("*", "**")),
                          SQLFragment("select ** from FOO where BAR = *", [1]))


    def test_columnComparison(self):
        """
        L{Select} generates a 'select' statement which compares columns.
        """
        self.assertEquals(Select(From=self.schema.FOO,
                                 Where=self.schema.FOO.BAR ==
                                 self.schema.FOO.BAZ).toSQL(),
                          SQLFragment("select * from FOO where BAR = BAZ", []))


    def test_comparisonTestErrorPrevention(self):
        """
        The comparison object between columns raises an exception when compared
        for a truth value, so that code will not accidentally test for '==' and
        always get a true value.
        """
        def sampleComparison():
            if self.schema.FOO.BAR == self.schema.FOO.BAZ:
                return 'comparison should not succeed'
        self.assertRaises(ValueError, sampleComparison)


    def test_nullComparison(self):
        """
        Comparing a column with None results in the generation of an 'is null'
        or 'is not null' SQL statement.
        """
        self.assertEquals(Select(From=self.schema.FOO,
                                 Where=self.schema.FOO.BAR ==
                                 None).toSQL(),
                          SQLFragment(
                              "select * from FOO where BAR is null", []))
        self.assertEquals(Select(From=self.schema.FOO,
                                 Where=self.schema.FOO.BAR !=
                                 None).toSQL(),
                          SQLFragment(
                              "select * from FOO where BAR is not null", []))


    def test_compoundWhere(self):
        """
        L{Select.And} and L{Select.Or} will return compound columns.
        """
        self.assertEquals(
            Select(From=self.schema.FOO,
                   Where=(self.schema.FOO.BAR < 2).Or(
                          self.schema.FOO.BAR > 5)).toSQL(),
            SQLFragment("select * from FOO where BAR < ? or BAR > ?", [2, 5]))


    def test_orderBy(self):
        """
        L{Select}'s L{OrderBy} parameter generates an 'order by' clause for a
        'select' statement.
        """
        self.assertEquals(
            Select(From=self.schema.FOO,
                   OrderBy=self.schema.FOO.BAR).toSQL(),
            SQLFragment("select * from FOO order by BAR")
        )


    def test_groupBy(self):
        """
        L{Select}'s L{GroupBy} parameter generates a 'group by' clause for a
        'select' statement.
        """
        self.assertEquals(
            Select(From=self.schema.FOO,
                   GroupBy=self.schema.FOO.BAR).toSQL(),
            SQLFragment("select * from FOO group by BAR")
        )


    def test_joinClause(self):
        """
        A table's .join() method returns a join statement in a SELECT.
        """
        self.assertEquals(
            Select(From=self.schema.FOO.join(
                self.schema.BOZ, self.schema.FOO.BAR ==
                self.schema.BOZ.QUX)).toSQL(),
            SQLFragment("select * from FOO join BOZ on BAR = QUX", [])
        )


    def test_columnSelection(self):
        """
        If a column is specified by the argument to L{Select}, those will be
        output by the SQL statement rather than the all-columns wildcard.
        """
        self.assertEquals(
            Select([self.schema.FOO.BAR],
                   From=self.schema.FOO).toSQL(),
            SQLFragment("select BAR from FOO")
        )


    def test_columnAliases(self):
        """
        When attributes are set on a L{TableSyntax}, they will be remembered as
        column aliases, and their alias names may be retrieved via the
        L{TableSyntax.aliases} method.
        """
        self.assertEquals(self.schema.FOO.aliases(), {})
        self.schema.FOO.ALIAS = self.schema.FOO.BAR
        # you comparing ColumnSyntax object results in a ColumnComparison, which
        # you can't test for truth.
        fixedForEquality = dict([(k, v.model) for k, v in
                                 self.schema.FOO.aliases().items()])
        self.assertEquals(fixedForEquality,
                          {'ALIAS': self.schema.FOO.BAR.model})
        self.assertIdentical(self.schema.FOO.ALIAS.model,
                             self.schema.FOO.BAR.model)


    def test_multiColumnSelection(self):
        """
        If multiple columns are specified by the argument to L{Select}, those
        will be output by the SQL statement rather than the all-columns
        wildcard.
        """
        self.assertEquals(
            Select([self.schema.FOO.BAZ,
                    self.schema.FOO.BAR],
                   From=self.schema.FOO).toSQL(),
            SQLFragment("select BAZ, BAR from FOO")
        )


    def test_joinColumnSelection(self):
        """
        If multiple columns are specified by the argument to L{Select} that uses
        a L{TableSyntax.join}, those will be output by the SQL statement.
        """
        self.assertEquals(
            Select([self.schema.FOO.BAZ,
                    self.schema.BOZ.QUX],
                   From=self.schema.FOO.join(self.schema.BOZ,
                                             self.schema.FOO.BAR ==
                                             self.schema.BOZ.QUX)).toSQL(),
            SQLFragment("select BAZ, QUX from FOO join BOZ on BAR = QUX")
        )


    def test_tableMismatch(self):
        """
        When a column in the 'columns' argument does not match the table from
        the 'From' argument, L{Select} raises a L{TableMismatch}.
        """
        self.assertRaises(TableMismatch, Select, [self.schema.BOZ.QUX],
                          From=self.schema.FOO)


    def test_qualifyNames(self):
        """
        When two columns in the FROM clause requested from different tables have
        the same name, the emitted SQL should explicitly disambiguate them.
        """
        self.assertEquals(
            Select([self.schema.FOO.BAR,
                    self.schema.OTHER.BAR],
                   From=self.schema.FOO.join(self.schema.OTHER,
                                             self.schema.OTHER.FOO_BAR ==
                                             self.schema.FOO.BAR)).toSQL(),
            SQLFragment(
                "select FOO.BAR, OTHER.BAR from FOO "
                "join OTHER on FOO_BAR = FOO.BAR"))


    def test_bindParameters(self):
        """
        L{SQLFragment.bind} returns a copy of that L{SQLFragment} with the
        L{Parameter} objects in its parameter list replaced with the keyword
        arguments to C{bind}.
        """

        self.assertEquals(
            Select(From=self.schema.FOO,
                   Where=(self.schema.FOO.BAR > Parameter("testing")).And(
                   self.schema.FOO.BAZ < 7)).toSQL().bind(testing=173),
            SQLFragment("select * from FOO where BAR > ? and BAZ < ?",
                         [173, 7]))


    def test_inSubSelect(self):
        """
        L{ColumnSyntax.In} returns a sub-expression using the SQL 'in' syntax.
        """
        wherein = (self.schema.FOO.BAR.In(
                    Select([self.schema.BOZ.QUX], From=self.schema.BOZ)))
        self.assertEquals(
            Select(From=self.schema.FOO, Where=wherein).toSQL(),
            SQLFragment(
                "select * from FOO where BAR in (select QUX from BOZ)"))


    def test_max(self):
        """
        Test for the 'Max' function.
        """
        self.assertEquals(
            Select([Max(self.schema.BOZ.QUX)], From=self.schema.BOZ).toSQL(),
            SQLFragment(
                "select max(QUX) from BOZ"))


    def test_len(self):
        """
        Test for the 'Len' function for determining character length of a
        column.  (Note that this should be updated to use different techniques
        as necessary in different databases.)
        """
        self.assertEquals(
            Select([Len(self.schema.TEXTUAL.MYTEXT)],
                    From=self.schema.TEXTUAL).toSQL(),
            SQLFragment(
                "select character_length(MYTEXT) from TEXTUAL"))


    def test_insert(self):
        """
        L{Insert.toSQL} generates an 'insert' statement with all the relevant
        columns.
        """
        self.assertEquals(
            Insert({self.schema.FOO.BAR: 23,
                    self.schema.FOO.BAZ: 9}).toSQL(),
            SQLFragment("insert into FOO (BAR, BAZ) values (?, ?)", [23, 9]))


    def test_insertNotEnough(self):
        """
        L{Insert}'s constructor will raise L{NotEnoughValues} if columns have
        not been specified.
        """
        notEnough = self.assertRaises(
            NotEnoughValues, Insert, {self.schema.OTHER.BAR: 9}
        )
        self.assertEquals(str(notEnough), "Columns [FOO_BAR] required.")


    def test_insertReturning(self):
        """
        L{Insert}'s C{Return} argument will insert an SQL 'returning' clause.
        """
        self.assertEquals(
            Insert({self.schema.FOO.BAR: 23,
                    self.schema.FOO.BAZ: 9},
                   Return=self.schema.FOO.BAR).toSQL(),
            SQLFragment(
                "insert into FOO (BAR, BAZ) values (?, ?) returning BAR",
                [23, 9])
        )


    def test_insertMismatch(self):
        """
        L{Insert} raises L{TableMismatch} if the columns specified aren't all
        from the same table.
        """
        self.assertRaises(
            TableMismatch,
            Insert, {self.schema.FOO.BAR: 23,
                     self.schema.FOO.BAZ: 9,
                     self.schema.TEXTUAL.MYTEXT: 'hello'}
        )


    def test_updateReturning(self):
        """
        L{update}'s C{Return} argument will update an SQL 'returning' clause.
        """
        self.assertEquals(
            Update({self.schema.FOO.BAR: 23},
                   self.schema.FOO.BAZ == 43,
                   Return=self.schema.FOO.BAR).toSQL(),
            SQLFragment(
                "update FOO set BAR = ? where BAZ = ? returning BAR",
                [23, 43])
        )


    def test_updateMismatch(self):
        """
        L{Update} raises L{TableMismatch} if the columns specified aren't all
        from the same table.
        """
        self.assertRaises(
            TableMismatch,
            Update, {self.schema.FOO.BAR: 23,
                     self.schema.FOO.BAZ: 9,
                     self.schema.TEXTUAL.MYTEXT: 'hello'},
            Where=self.schema.FOO.BAZ == 9
        )


    def test_deleteReturning(self):
        """
        L{Delete}'s C{Return} argument will delete an SQL 'returning' clause.
        """
        self.assertEquals(
            Delete(self.schema.FOO,
                   Where=self.schema.FOO.BAR == 7,
                   Return=self.schema.FOO.BAZ).toSQL(),
            SQLFragment(
                "delete from FOO where BAR = ? returning BAZ", [7])
        )


    def test_update(self):
        """
        L{Update.toSQL} generates an 'update' statement.
        """
        self.assertEquals(
            Update({self.schema.FOO.BAR: 4321},
                    self.schema.FOO.BAZ == 1234).toSQL(),
            SQLFragment("update FOO set BAR = ? where BAZ = ?", [4321, 1234]))


    def test_delete(self):
        """
        L{Delete} generates an SQL 'delete' statement.
        """
        self.assertEquals(
            Delete(self.schema.FOO,
                   Where=self.schema.FOO.BAR == 12).toSQL(),
            SQLFragment(
                "delete from FOO where BAR = ?", [12])
        )


    def test_lock(self):
        """
        L{Lock.exclusive} generates a ('lock table') statement, locking the
        table in the specified mode.
        """
        self.assertEquals(Lock.exclusive(self.schema.FOO).toSQL(),
                          SQLFragment("lock table FOO in exclusive mode"))

