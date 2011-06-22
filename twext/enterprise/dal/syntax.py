# -*- test-case-name: twext.enterprise.dal.test.test_sqlsyntax -*-
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
Syntax wrappers and generators for SQL.
"""

from itertools import count, repeat

from zope.interface import implements

from twisted.internet.defer import succeed

from twext.enterprise.ienterprise import POSTGRES_DIALECT, ORACLE_DIALECT
from twext.enterprise.ienterprise import IDerivedParameter

from twext.enterprise.util import mapOracleOutputType
from twext.enterprise.dal.model import Schema, Table, Column, Sequence

try:
    import cx_Oracle
    cx_Oracle
except ImportError:
    cx_Oracle = None

class ConnectionMetadata(object):
    """
    Representation of the metadata about the database connection required to
    generate some SQL, for a single statement.  Contains information necessary
    to generate placeholder strings and determine the database dialect.
    """

    def __init__(self, dialect):
        self.dialect = dialect


    def placeholder(self):
        raise NotImplementedError("See subclasses.")



class FixedPlaceholder(ConnectionMetadata):
    """
    Metadata about a connection which uses a fixed string as its placeholder.
    """

    def __init__(self, dialect, placeholder):
        super(FixedPlaceholder, self).__init__(dialect)
        self._placeholder = placeholder


    def placeholder(self):
        return self._placeholder



class NumericPlaceholder(ConnectionMetadata):

    def __init__(self, dialect):
        super(NumericPlaceholder, self).__init__(dialect)
        self._next = count(1).next


    def placeholder(self):
        return ':' + str(self._next())



def defaultMetadata():
    """
    Generate a default L{ConnectionMetadata}
    """
    return FixedPlaceholder(POSTGRES_DIALECT, '?')



class TableMismatch(Exception):
    """
    A table in a statement did not match with a column.
    """



class NotEnoughValues(ValueError):
    """
    Not enough values were supplied for an L{Insert}.
    """



class _Statement(object):
    """
    An SQL statement that may be executed.  (An abstract base class, must
    implement several methods.)
    """

    _paramstyles = {
        'pyformat': lambda dialect: FixedPlaceholder(dialect, "%s"),
        'numeric': NumericPlaceholder
    }


    def toSQL(self, metadata=None):
        if metadata is None:
            metadata = defaultMetadata()
        return self._toSQL(metadata)


    def _extraVars(self, txn, metadata):
        """
        A hook for subclasses to provide additional keyword arguments to the
        C{bind} call when L{_Statement.on} is executed.  Currently this is used
        only for 'out' parameters to capture results when executing statements
        that do not normally have a result (L{Insert}, L{Delete}, L{Update}).
        """
        return {}


    def _extraResult(self, result, outvars, metadata):
        """
        A hook for subclasses to manipulate the results of 'on', after they've
        been retrieved by the database but before they've been given to
        application code.

        @param result: a L{Deferred} that will fire with the rows as returned by
            the database.
        @type result: C{list} of rows, which are C{list}s or C{tuple}s.

        @param outvars: a dictionary of extra variables returned by
            C{self._extraVars}.

        @param metadata: information about the connection where the statement
            was executed.

        @type metadata: L{ConnectionMetadata} (a subclass thereof)

        @return: the result to be returned from L{_Statement.on}.

        @rtype: L{Deferred} firing result rows
        """
        return result


    def on(self, txn, raiseOnZeroRowCount=None, **kw):
        """
        Execute this statement on a given L{IAsyncTransaction} and return the
        resulting L{Deferred}.

        @param txn: the L{IAsyncTransaction} to execute this on.

        @param raiseOnZeroRowCount: the exception to raise if no data was
            affected or returned by this query.

        @param kw: keyword arguments, mapping names of L{Parameter} objects
            located somewhere in C{self}

        @return: results from the database.

        @rtype: a L{Deferred} firing a C{list} of records (C{tuple}s or
            C{list}s)
        """
        metadata = self._paramstyles[txn.paramstyle](txn.dialect)
        outvars = self._extraVars(txn, metadata)
        kw.update(outvars)
        fragment = self.toSQL(metadata).bind(**kw)
        result = txn.execSQL(fragment.text, fragment.parameters,
                             raiseOnZeroRowCount)
        result = self._extraResult(result, outvars, metadata)
        if metadata.dialect == ORACLE_DIALECT and result:
            result.addCallback(self._fixOracleNulls)
        return result


    def _resultColumns(self):
        """
        Subclasses must implement this to return a description of the columns
        expected to be returned.  This is a list of L{ColumnSyntax} objects, and
        possibly other expression syntaxes which will be converted to C{None}.
        """
        raise NotImplementedError(
            "Each statement subclass must describe its result"
        )


    def _resultShape(self):
        """
        Process the result of the subclass's C{_resultColumns}, as described in
        the docstring above.
        """
        for expectation in self._resultColumns():
            if isinstance(expectation, ColumnSyntax):
                yield expectation.model
            else:
                yield None


    def _fixOracleNulls(self, rows):
        """
        Oracle treats empty strings as C{NULL}.  Fix this by looking at the
        columns we expect to have returned, and replacing any C{None}s with
        empty strings in the appropriate position.
        """
        if rows is None:
            return None
        newRows = []
        for row in rows:
            newRow = []
            for column, description in zip(row, self._resultShape()):
                if ((description is not None and
                     # FIXME: "is the python type str" is what I mean; this list
                     # should be more centrally maintained
                     description.type.name in ('varchar', 'text', 'char') and
                     column is None
                    )):
                    column = ''
                newRow.append(column)
            newRows.append(newRow)
        return newRows



class Syntax(object):
    """
    Base class for syntactic convenience.

    This class will define dynamic attribute access to represent its underlying
    model as a Python namespace.

    You can access the underlying model as '.model'.
    """

    modelType = None
    model = None

    def __init__(self, model):
        if not isinstance(model, self.modelType):
            # make sure we don't get a misleading repr()
            raise ValueError("type mismatch: %r %r", type(self), model)
        self.model = model


    def __repr__(self):
        if self.model is not None:
            return '<Syntax for: %r>' % (self.model,)
        return super(Syntax, self).__repr__()



def comparison(comparator):
    def __(self, other):
        if other is None:
            return NullComparison(self, comparator)
        if isinstance(other, Select):
            return NotImplemented
        if isinstance(other, ColumnSyntax):
            return ColumnComparison(self, comparator, other)
        else:
            return CompoundComparison(self, comparator, Constant(other))
    return __



class ExpressionSyntax(Syntax):
    __eq__ = comparison('=')
    __ne__ = comparison('!=')
    __gt__ = comparison('>')
    __ge__ = comparison('>=')
    __lt__ = comparison('<')
    __le__ = comparison('<=')
    __add__ = comparison("+")
    __sub__ = comparison("-")
    __div__= comparison("/")
    __mul__= comparison("*")


    def __nonzero__(self):
        raise ValueError(
            "SQL expressions should not be tested for truth value in Python.")


    def In(self, subselect):
        # Can't be Select.__contains__ because __contains__ gets __nonzero__
        # called on its result by the 'in' syntax.
        return CompoundComparison(self, 'in', subselect)



class FunctionInvocation(ExpressionSyntax):
    def __init__(self, function, *args):
        self.function = function
        self.args = args


    def allColumns(self):
        """
        All of the columns in all of the arguments' columns.
        """
        def ac():
            for arg in self.args:
                for column in arg.allColumns():
                    yield column
        return list(ac())


    def subSQL(self, metadata, allTables):
        result = SQLFragment(self.function.nameFor(metadata))
        result.append(_inParens(
            _commaJoined(_convert(arg).subSQL(metadata, allTables)
                         for arg in self.args)))
        return result



class Constant(ExpressionSyntax):
    def __init__(self, value):
        self.value = value


    def allColumns(self):
        return []


    def subSQL(self, metadata, allTables):
        return SQLFragment(metadata.placeholder(), [self.value])



class NamedValue(ExpressionSyntax):
    """
    A constant within the database; something pre-defined, such as
    CURRENT_TIMESTAMP.
    """
    def __init__(self, name):
        self.name = name


    def subSQL(self, metadata, allTables):
        return SQLFragment(self.name)



class Function(object):
    """
    An L{Function} is a representation of an SQL Function function.
    """

    def __init__(self, name, oracleName=None):
        self.name = name
        self.oracleName = oracleName


    def nameFor(self, metadata):
        if metadata.dialect == ORACLE_DIALECT and self.oracleName is not None:
            return self.oracleName
        return self.name


    def __call__(self, *args):
        """
        Produce an L{FunctionInvocation}
        """
        return FunctionInvocation(self, *args)



Count = Function("count")
Max = Function("max")
Len = Function("character_length", "length")



class SchemaSyntax(Syntax):
    """
    Syntactic convenience for L{Schema}.
    """

    modelType = Schema

    def __getattr__(self, attr):
        try:
            tableModel = self.model.tableNamed(attr)
        except KeyError:
            try:
                seqModel = self.model.sequenceNamed(attr)
            except KeyError:
                raise AttributeError("schema has no table or sequence %r" % (attr,))
            else:
                return SequenceSyntax(seqModel)
        else:
            syntax = TableSyntax(tableModel)
            # Needs to be preserved here so that aliasing will work.
            setattr(self, attr, syntax)
            return syntax


    def __iter__(self):
        for table in self.model.tables:
            yield TableSyntax(table)



class SequenceSyntax(ExpressionSyntax):
    """
    Syntactic convenience for L{Sequence}.
    """

    modelType = Sequence

    def subSQL(self, metadata, allTables):
        """
        Convert to an SQL fragment.
        """
        if metadata.dialect == ORACLE_DIALECT:
            fmt = "%s.nextval"
        else:
            fmt = "nextval('%s')"
        return SQLFragment(fmt % (self.model.name,))



class TableSyntax(Syntax):
    """
    Syntactic convenience for L{Table}.
    """

    modelType = Table

    def join(self, otherTableSyntax, on=None, type=''):
        if on is None:
            type = 'cross'
        return Join(self, type, otherTableSyntax, on)


    def subSQL(self, metadata, allTables):
        """
        For use in a 'from' clause.
        """
        # XXX maybe there should be a specific method which is only invoked
        # from the FROM clause, that only tables and joins would implement?
        return SQLFragment(self.model.name)


    def __getattr__(self, attr):
        return ColumnSyntax(self.model.columnNamed(attr))


    def __iter__(self):
        for column in self.model.columns:
            yield ColumnSyntax(column)


    def tables(self):
        return [self]


    def aliases(self):
        result = {}
        for k, v in self.__dict__.items():
            if isinstance(v, ColumnSyntax):
                result[k] = v
        return result


    def __contains__(self, columnSyntax):
        if isinstance(columnSyntax, FunctionInvocation):
            columnSyntax = columnSyntax.arg
        return (columnSyntax.model in self.model.columns)



class Join(object):
    """
    A DAL object representing an SQL 'join' statement.

    @ivar leftSide: a L{Join} or L{TableSyntax} representing the left side of
        this join.

    @ivar rightSide: a L{TableSyntax} representing the right side of this join.

    @ivar type: the type of join this is.  For example, for a left outer join,
        this would be C{'left outer'}.
    @type type: C{str}

    @ivar on: the 'on' clause of this table.

    @type on: L{ExpressionSyntax}
    """

    def __init__(self, leftSide, type, rightSide, on):
        self.leftSide = leftSide
        self.type = type
        self.rightSide = rightSide
        self.on = on


    def subSQL(self, metadata, allTables):
        stmt = SQLFragment()
        stmt.append(self.leftSide.subSQL(metadata, allTables))
        stmt.text += ' '
        if self.type:
            stmt.text += self.type
            stmt.text += ' '
        stmt.text += 'join '
        stmt.append(self.rightSide.subSQL(metadata, allTables))
        if self.type != 'cross':
            stmt.text += ' on '
            stmt.append(self.on.subSQL(metadata, allTables))
        return stmt


    def tables(self):
        return self.leftSide.tables() + self.rightSide.tables()


    def join(self, otherTable, on=None, type=None):
        if on is None:
            type = 'cross'
        return Join(self, type, otherTable, on)


_KEYWORDS = ["access",
             # SQL keyword, but we have a column with this name
             "path",
             # Not actually a standard keyword, but a function in oracle, and we
             # have a column with this name.
             "size",
             # not actually sure what this is; only experimentally determined
             # that not quoting it causes an issue.
            ]


class ColumnSyntax(ExpressionSyntax):
    """
    Syntactic convenience for L{Column}.
    """

    modelType = Column


    def allColumns(self):
        return [self]


    def subSQL(self, metadata, allTables):
        # XXX This, and 'model', could in principle conflict with column names.
        # Maybe do something about that.
        name = self.model.name
        if metadata.dialect == ORACLE_DIALECT and name.lower() in _KEYWORDS:
            name = '"%s"' % (name,)

        for tableSyntax in allTables:
            if self.model.table is not tableSyntax.model:
                if self.model.name in (c.name for c in
                                               tableSyntax.model.columns):
                    return SQLFragment((self.model.table.name + '.' + name))
        return SQLFragment(name)



class Comparison(ExpressionSyntax):

    def __init__(self, a, op, b):
        self.a = a
        self.op = op
        self.b = b


    def _subexpression(self, expr, metadata, allTables):
        result = expr.subSQL(metadata, allTables)
        if self.op not in ('and', 'or') and isinstance(expr, Comparison):
            result = _inParens(result)
        return result


    def booleanOp(self, operand, other):
        return CompoundComparison(self, operand, other)


    def And(self, other):
        return self.booleanOp('and', other)


    def Or(self, other):
        return self.booleanOp('or', other)



class NullComparison(Comparison):
    """
    A L{NullComparison} is a comparison of a column or expression with None.
    """
    def __init__(self, a, op):
        # 'b' is always None for this comparison type
        super(NullComparison, self).__init__(a, op, None)


    def subSQL(self, metadata, allTables):
        sqls = SQLFragment()
        sqls.append(self.a.subSQL(metadata, allTables))
        sqls.text += " is "
        if self.op != "=":
            sqls.text += "not "
        sqls.text += "null"
        return sqls



class CompoundComparison(Comparison):
    """
    A compound comparison; two or more constraints, joined by an operation
    (currently only AND or OR).
    """

    def allColumns(self):
        return self.a.allColumns() + self.b.allColumns()


    def subSQL(self, metadata, allTables):
        stmt = SQLFragment()
        result = self._subexpression(self.a, metadata, allTables)
        if isinstance(self.a, CompoundComparison) and self.a.op == 'or' and self.op == 'and':
            result = _inParens(result)
        stmt.append(result)

        stmt.text += ' %s ' % (self.op,)

        result = self._subexpression(self.b, metadata, allTables)
        if isinstance(self.b, CompoundComparison) and self.b.op == 'or' and self.op == 'and':
            result = _inParens(result)
        stmt.append(result)
        return stmt



class ColumnComparison(CompoundComparison):
    """
    Comparing two columns is the same as comparing any other two expressions,
    (for now).
    """



class _AllColumns(object):

    def subSQL(self, metadata, allTables):
        return SQLFragment('*')

ALL_COLUMNS = _AllColumns()



class _SomeColumns(object):

    def __init__(self, columns):
        self.columns = columns


    def subSQL(self, metadata, allTables):
        first = True
        cstatement = SQLFragment()
        for column in self.columns:
            if first:
                first = False
            else:
                cstatement.append(SQLFragment(", "))
            cstatement.append(column.subSQL(metadata, allTables))
        return cstatement



def _columnsMatchTables(columns, tables):
    for expression in columns:
        for column in expression.allColumns():
            for table in tables:
                if column in table:
                    break
            else:
                return False
    return True


class Tuple(object):

    def __init__(self, columns):
        self.columns = columns


    def subSQL(self, metadata, allTables):
        return _inParens(_commaJoined(c.subSQL(metadata, allTables)
                                      for c in self.columns))


    def allColumns(self):
        return self.columns



class Select(_Statement):
    """
    'select' statement.
    """

    def __init__(self, columns=None, Where=None, From=None, OrderBy=None,
                 GroupBy=None, Limit=None, ForUpdate=False, Ascending=None,
                 Having=None, Distinct=False):
        self.From = From
        self.Where = Where
        self.Distinct = Distinct
        if not isinstance(OrderBy, (list, tuple, type(None))):
            OrderBy = [OrderBy]
        self.OrderBy = OrderBy
        if not isinstance(GroupBy, (list, tuple, type(None))):
            GroupBy = [GroupBy]
        self.GroupBy = GroupBy
        self.Limit = Limit
        self.Having = Having
        if columns is None:
            columns = ALL_COLUMNS
        else:
            if not _columnsMatchTables(columns, From.tables()):
                raise TableMismatch()

            columns = _SomeColumns(columns)
        self.columns = columns
        self.ForUpdate = ForUpdate
        self.Ascending = Ascending


    def __eq__(self, other):
        """
        Create a comparison.
        """
        if isinstance(other, (list, tuple)):
            other = Tuple(other)
        return CompoundComparison(other, '=', self)


    def _toSQL(self, metadata):
        """
        @return: a 'select' statement with placeholders and arguments

        @rtype: L{SQLFragment}
        """
        stmt = SQLFragment("select ")
        if self.Distinct:
            stmt.text += "distinct "
        allTables = self.From.tables()
        stmt.append(self.columns.subSQL(metadata, allTables))
        stmt.text += " from "
        stmt.append(self.From.subSQL(metadata, allTables))
        if self.Where is not None:
            wherestmt = self.Where.subSQL(metadata, allTables)
            stmt.text += " where "
            stmt.append(wherestmt)
        if self.GroupBy is not None:
            stmt.text += " group by "
            fst = True
            for subthing in self.GroupBy:
                if fst:
                    fst = False
                else:
                    stmt.text += ', '
                stmt.append(subthing.subSQL(metadata, allTables))
        if self.Having is not None:
            havingstmt = self.Having.subSQL(metadata, allTables)
            stmt.text += " having "
            stmt.append(havingstmt)
        if self.OrderBy is not None:
            stmt.text += " order by "
            fst = True
            for subthing in self.OrderBy:
                if fst:
                    fst = False
                else:
                    stmt.text += ', '
                stmt.append(subthing.subSQL(metadata, allTables))
            if self.Ascending is not None:
                if self.Ascending:
                    kw = " asc"
                else:
                    kw = " desc"
                stmt.append(SQLFragment(kw))
        if self.ForUpdate:
            stmt.text += " for update"
        if self.Limit is not None:
            stmt.text += " limit "
            stmt.append(Constant(self.Limit).subSQL(metadata, allTables))
        return stmt


    def subSQL(self, metadata, allTables):
        result = SQLFragment("(")
        result.append(self.toSQL(metadata))
        result.append(SQLFragment(")"))
        return result


    def _resultColumns(self):
        """
        Determine the list of L{ColumnSyntax} objects that will represent the
        result.  Normally just the list of selected columns; if wildcard syntax
        is used though, determine the ordering from the database.
        """
        if self.columns is ALL_COLUMNS:
            # TODO: Possibly this rewriting should always be done, before even
            # executing the query, so that if we develop a schema mismatch with
            # the database (additional columns), the application will still see
            # the right rows.
            for table in self.From.tables():
                for column in table:
                    yield column
        else:
            for column in self.columns.columns:
                yield column


def _commaJoined(stmts):
    first = True
    cstatement = SQLFragment()
    for stmt in stmts:
        if first:
            first = False
        else:
            cstatement.append(SQLFragment(", "))
        cstatement.append(stmt)
    return cstatement



def _inParens(stmt):
    result = SQLFragment("(")
    result.append(stmt)
    result.append(SQLFragment(")"))
    return result



def _fromSameTable(columns):
    """
    Extract the common table used by a list of L{Column} objects, raising
    L{TableMismatch}.
    """
    table = columns[0].table
    for column in columns:
        if table is not column.table:
            raise TableMismatch("Columns must all be from the same table.")
    return table



def _modelsFromMap(columnMap):
    """
    Get the L{Column} objects from a mapping of L{ColumnSyntax} to values.
    """
    return [c.model for c in columnMap.keys()]



class _CommaList(object):
    def __init__(self, subfragments):
        self.subfragments = subfragments


    def subSQL(self, metadata, allTables):
        return _commaJoined(f.subSQL(metadata, allTables)
                            for f in self.subfragments)



class _DMLStatement(_Statement):
    """
    Common functionality of Insert/Update/Delete statements.
    """

    def _returningClause(self, metadata, stmt, allTables):
        """
        Add a dialect-appropriate 'returning' clause to the end of the given SQL
        statement.

        @param metadata: describes the database we are generating the statement
            for.

        @type metadata: L{ConnectionMetadata}

        @param stmt: the SQL fragment generated without the 'returning' clause
        @type stmt: L{SQLFragment}

        @param allTables: all tables involved in the query; see any C{subSQL}
            method.

        @return: the C{stmt} parameter.
        """
        retclause = self.Return
        if isinstance(retclause, (tuple, list)):
            retclause = _CommaList(retclause)
        if retclause is not None:
            stmt.text += ' returning '
            stmt.append(retclause.subSQL(metadata, allTables))
            if metadata.dialect == ORACLE_DIALECT:
                stmt.text += ' into '
                params = []
                retvals = self._returnAsList()
                for n, v in enumerate(retvals):
                    params.append(
                        Constant(Parameter("oracle_out_" + str(n)))
                        .subSQL(metadata, allTables)
                    )
                stmt.append(_commaJoined(params))
        return stmt


    def _returnAsList(self):
        if not isinstance(self.Return, (tuple, list)):
            return [self.Return]
        else:
            return self.Return


    def _extraVars(self, txn, metadata):
        result = []
        rvars = self._returnAsList()
        if metadata.dialect == ORACLE_DIALECT:
            for n, v in enumerate(rvars):
                result.append(("oracle_out_" + str(n), _OracleOutParam(v)))
        return result


    def _extraResult(self, result, outvars, metadata):
        if metadata.dialect == ORACLE_DIALECT and self.Return is not None:
            def processIt(shouldBeNone):
                result = [[v.value for k, v in outvars]]
                return result
            return result.addCallback(processIt)
        else:
            return result


    def _resultColumns(self):
        return self._returnAsList()



class _OracleOutParam(object):
    """
    A parameter that will be populated using the cx_Oracle API for host
    variables.
    """
    implements(IDerivedParameter)

    def __init__(self, columnSyntax):
        self.columnSyntax = columnSyntax


    def preQuery(self, cursor):
        typeMap = {'integer': cx_Oracle.NUMBER,
                   'text': cx_Oracle.NCLOB,
                   'varchar': cx_Oracle.STRING,
                   'timestamp': cx_Oracle.TIMESTAMP}
        typeID = self.columnSyntax.model.type.name.lower()
        self.var = cursor.var(typeMap[typeID])
        return self.var


    def postQuery(self, cursor):
        self.value = mapOracleOutputType(self.var.getvalue())



class Insert(_DMLStatement):
    """
    'insert' statement.
    """

    def __init__(self, columnMap, Return=None):
        self.columnMap = columnMap
        self.Return = Return
        columns = _modelsFromMap(columnMap)
        table = _fromSameTable(columns)
        required = [column for column in table.columns if column.needsValue()]
        unspecified = [column for column in required
                       if column not in columns]
        if unspecified:
            raise NotEnoughValues(
                'Columns [%s] required.' %
                    (', '.join([c.name for c in unspecified])))


    def _toSQL(self, metadata):
        """
        @return: a 'insert' statement with placeholders and arguments

        @rtype: L{SQLFragment}
        """
        columnsAndValues = self.columnMap.items()
        tableModel = columnsAndValues[0][0].model.table
        specifiedColumnModels = [x.model for x in self.columnMap.keys()]
        if metadata.dialect == ORACLE_DIALECT:
            # See test_nextSequenceDefaultImplicitExplicitOracle.
            for column in tableModel.columns:
                if isinstance(column.default, Sequence):
                    columnSyntax = ColumnSyntax(column)
                    if column not in specifiedColumnModels:
                        columnsAndValues.append(
                            (columnSyntax, SequenceSyntax(column.default))
                        )
        sortedColumns = sorted(columnsAndValues,
                               key=lambda (c, v): c.model.name)
        allTables = []
        stmt = SQLFragment('insert into ')
        stmt.append(TableSyntax(tableModel).subSQL(metadata, allTables))
        stmt.append(SQLFragment(" "))
        stmt.append(_inParens(_commaJoined(
            [c.subSQL(metadata, allTables) for (c, v) in
             sortedColumns])))
        stmt.append(SQLFragment(" values "))
        stmt.append(_inParens(_commaJoined(
            [_convert(v).subSQL(metadata, allTables)
             for (c, v) in sortedColumns])))
        return self._returningClause(metadata, stmt, allTables)



def _convert(x):
    """
    Convert a value to an appropriate SQL AST node.  (Currently a simple
    isinstance, could be promoted to use adaptation if we want to get fancy.)
    """
    if isinstance(x, ExpressionSyntax):
        return x
    else:
        return Constant(x)



class Update(_DMLStatement):
    """
    'update' statement
    """

    def __init__(self, columnMap, Where, Return=None):
        super(Update, self).__init__()
        _fromSameTable(_modelsFromMap(columnMap))
        self.columnMap = columnMap
        self.Where = Where
        self.Return = Return


    def _toSQL(self, metadata):
        """
        @return: a 'insert' statement with placeholders and arguments

        @rtype: L{SQLFragment}
        """
        sortedColumns = sorted(self.columnMap.items(),
                               key=lambda (c, v): c.model.name)
        allTables = []
        result = SQLFragment('update ')
        result.append(
            TableSyntax(sortedColumns[0][0].model.table).subSQL(
                metadata, allTables)
        )
        result.text += ' set '
        result.append(
            _commaJoined(
                [c.subSQL(metadata, allTables).append(
                    SQLFragment(" = ").subSQL(metadata, allTables)
                ).append(_convert(v).subSQL(metadata, allTables))
                    for (c, v) in sortedColumns]
            )
        )
        result.append(SQLFragment( ' where '))
        result.append(self.Where.subSQL(metadata, allTables))
        return self._returningClause(metadata, result, allTables)



class Delete(_DMLStatement):
    """
    'delete' statement.
    """

    def __init__(self, From, Where, Return=None):
        """
        If Where is None then all rows will be deleted.
        """
        self.From = From
        self.Where = Where
        self.Return = Return


    def _toSQL(self, metadata):
        result = SQLFragment()
        allTables = self.From.tables()
        result.text += 'delete from '
        result.append(self.From.subSQL(metadata, allTables))
        if self.Where is not None:
            result.text += ' where '
            result.append(self.Where.subSQL(metadata, allTables))
        return self._returningClause(metadata, result, allTables)



class _LockingStatement(_Statement):
    """
    A statement related to lock management, which implicitly has no results.
    """
    def _resultColumns(self):
        """
        No columns should be expected, so return an infinite iterator of None.
        """
        return repeat(None)



class Lock(_LockingStatement):
    """
    An SQL 'lock' statement.
    """

    def __init__(self, table, mode):
        self.table = table
        self.mode = mode


    @classmethod
    def exclusive(cls, table):
        return cls(table, 'exclusive')


    def _toSQL(self, metadata):
        return SQLFragment('lock table ').append(
            self.table.subSQL(metadata, [self.table])).append(
            SQLFragment(' in %s mode' % (self.mode,)))



class Savepoint(_LockingStatement):
    """
    An SQL 'savepoint' statement.
    """

    def __init__(self, name):
        self.name = name


    def _toSQL(self, metadata):
        return SQLFragment('savepoint %s' % (self.name,))


class RollbackToSavepoint(_LockingStatement):
    """
    An SQL 'rollback to savepoint' statement.
    """

    def __init__(self, name):
        self.name = name


    def _toSQL(self, metadata):
        return SQLFragment('rollback to savepoint %s' % (self.name,))


class ReleaseSavepoint(_LockingStatement):
    """
    An SQL 'release savepoint' statement.
    """

    def __init__(self, name):
        self.name = name


    def _toSQL(self, metadata):
        return SQLFragment('release savepoint %s' % (self.name,))



class SavepointAction(object):

    def __init__(self, name):
        self._name = name


    def acquire(self, txn):
        return Savepoint(self._name).on(txn)


    def rollback(self, txn):
        return RollbackToSavepoint(self._name).on(txn)


    def release(self, txn):
        if txn.dialect == ORACLE_DIALECT:
            # There is no 'release savepoint' statement in oracle, but then, we
            # don't need it because there's no resource to manage.  Just don't
            # do anything.
            return NoOp()
        else:
            return ReleaseSavepoint(self._name).on(txn)



class NoOp(object):
    def on(self, *a, **kw):
        return succeed(None)



class SQLFragment(object):
    """
    Combination of SQL text and arguments; a statement which may be executed
    against a database.
    """

    def __init__(self, text="", parameters=None):
        self.text = text
        if parameters is None:
            parameters = []
        self.parameters = parameters


    def bind(self, **kw):
        params = []
        for parameter in self.parameters:
            if isinstance(parameter, Parameter):
                params.append(kw[parameter.name])
            else:
                params.append(parameter)
        return SQLFragment(self.text, params)


    def append(self, anotherStatement):
        self.text += anotherStatement.text
        self.parameters += anotherStatement.parameters
        return self


    def __eq__(self, stmt):
        if not isinstance(stmt, SQLFragment):
            return NotImplemented
        return (self.text, self.parameters) == (stmt.text, stmt.parameters)


    def __ne__(self, stmt):
        if not isinstance(stmt, SQLFragment):
            return NotImplemented
        return not self.__eq__(stmt)


    def __repr__(self):
        return self.__class__.__name__ + repr((self.text, self.parameters))


    def subSQL(self, metadata, allTables):
        return self



class Parameter(object):

    def __init__(self, name):
        self.name = name


    def __eq__(self, param):
        if not isinstance(param, Parameter):
            return NotImplemented
        return self.name == param.name


    def __ne__(self, param):
        if not isinstance(param, Parameter):
            return NotImplemented
        return not self.__eq__(param)


    def __repr__(self):
        return 'Parameter(%r)' % (self.name,)


# Common helpers:

# current timestamp in UTC format.  Hack to support standard syntax for this,
# rather than the compatibility procedure found in various databases.
utcNowSQL = NamedValue("CURRENT_TIMESTAMP at time zone 'UTC'")

# You can't insert a column with no rows.  In SQL that just isn't valid syntax,
# and in this DAL you need at least one key or we can't tell what table you're
# talking about.  Luckily there's the 'default' keyword to the rescue, which, in
# the context of an INSERT statement means 'use the default value explicitly'.
# (Although this is a special keyword in a CREATE statement, in an INSERT it
# behaves like an expression to the best of my knowledge.)
default = NamedValue('default')

