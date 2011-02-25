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

from twext.enterprise.dal.model import Schema, Table, Column, Sequence


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
        'pyformat': ('%s', lambda s: s.replace("%", "%%"))
    }

    def on(self, txn, raiseOnZeroRowCount=None, **kw):
        """
        Execute this statement on a given L{IAsyncTransaction} and return the
        resulting L{Deferred}.
        """
        placeholder, quote = self._paramstyles[txn.paramstyle]
        fragment = self.toSQL(placeholder, quote).bind(**kw)
        return txn.execSQL(fragment.text, fragment.parameters,
                           raiseOnZeroRowCount)



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
    def __init__(self, name, *args):
        self.name = name
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


    def subSQL(self, placeholder, quote, allTables):
        result = SQLFragment(self.name)
        result.append(_inParens(
            _commaJoined(_convert(arg).subSQL(placeholder, quote, allTables)
                         for arg in self.args)))
        return result



class Constant(ExpressionSyntax):
    def __init__(self, value):
        self.value = value


    def allColumns(self):
        return []


    def subSQL(self, placeholder, quote, allTables):
        return SQLFragment(placeholder, [self.value])



class NamedValue(ExpressionSyntax):
    """
    A constant within the database; something pre-defined, such as
    CURRENT_TIMESTAMP.
    """
    def __init__(self, name):
        self.name = name


    def subSQL(self, placeholder, quote, allTables):
        return SQLFragment(self.name)



class Function(object):
    """
    An L{Function} is a representation of an SQL Function function.
    """

    def __init__(self, name):
        self.name = name


    def __call__(self, *args):
        """
        Produce an L{FunctionInvocation}
        """
        return FunctionInvocation(self.name, *args)


Max = Function("max")
Len = Function("character_length")



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

    def subSQL(self, placeholder, quote, allTables):
        """
        Convert to an SQL fragment.
        """
        return SQLFragment("nextval('%s')" % (self.model.name,))



class TableSyntax(Syntax):
    """
    Syntactic convenience for L{Table}.
    """

    modelType = Table

    def join(self, otherTableSyntax, on=None, type=''):
        if on is None:
            type = 'cross'
        return Join(self, type, otherTableSyntax, on)


    def subSQL(self, placeholder, quote, allTables):
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


    def subSQL(self, placeholder, quote, allTables):
        stmt = SQLFragment()
        stmt.append(self.leftSide.subSQL(placeholder, quote, allTables))
        stmt.text += ' '
        if self.type:
            stmt.text += self.type
            stmt.text += ' '
        stmt.text += 'join '
        stmt.append(self.rightSide.subSQL(placeholder, quote, allTables))
        if self.type != 'cross':
            stmt.text += ' on '
            stmt.append(self.on.subSQL(placeholder, quote, allTables))
        return stmt


    def tables(self):
        return self.leftSide.tables() + self.rightSide.tables()


    def join(self, otherTable, on=None, type=None):
        if on is None:
            type = 'cross'
        return Join(self, type, otherTable, on)




class ColumnSyntax(ExpressionSyntax):
    """
    Syntactic convenience for L{Column}.
    """

    modelType = Column


    def allColumns(self):
        return [self]


    def subSQL(self, placeholder, quote, allTables):
        # XXX This, and 'model', could in principle conflict with column names.
        # Maybe do something about that.
        for tableSyntax in allTables:
            if self.model.table is not tableSyntax.model:
                if self.model.name in (c.name for c in
                                               tableSyntax.model.columns):
                    return SQLFragment((self.model.table.name + '.' +
                                         self.model.name))
        return SQLFragment(self.model.name)



class Comparison(ExpressionSyntax):

    def __init__(self, a, op, b):
        self.a = a
        self.op = op
        self.b = b


    def _subexpression(self, expr, placeholder, quote, allTables):
        result = expr.subSQL(placeholder, quote, allTables)
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


    def subSQL(self, placeholder, quote, allTables):
        sqls = SQLFragment()
        sqls.append(self.a.subSQL(placeholder, quote, allTables))
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


    def subSQL(self, placeholder, quote, allTables):
        stmt = SQLFragment()
        result = self._subexpression(self.a, placeholder, quote, allTables)
        if isinstance(self.a, CompoundComparison) and self.a.op == 'or' and self.op == 'and':
            result = _inParens(result)
        stmt.append(result)

        stmt.text += ' %s ' % (self.op,)

        result = self._subexpression(self.b, placeholder, quote, allTables)
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

    def subSQL(self, placeholder, quote, allTables):
        return SQLFragment(quote('*'))

ALL_COLUMNS = _AllColumns()



class _SomeColumns(object):

    def __init__(self, columns):
        self.columns = columns


    def subSQL(self, placeholder, quote, allTables):
        first = True
        cstatement = SQLFragment()
        for column in self.columns:
            if first:
                first = False
            else:
                cstatement.append(SQLFragment(", "))
            cstatement.append(column.subSQL(placeholder, quote, allTables))
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



class Select(_Statement):
    """
    'select' statement.
    """

    def __init__(self, columns=None, Where=None, From=None, OrderBy=None,
                 GroupBy=None, Limit=None, ForUpdate=False, Ascending=None,
                 Having=None):
        self.From = From
        self.Where = Where
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


    def toSQL(self, placeholder="?", quote=lambda x: x):
        """
        @return: a 'select' statement with placeholders and arguments

        @rtype: L{SQLFragment}
        """
        stmt = SQLFragment(quote("select "))
        allTables = self.From.tables()
        stmt.append(self.columns.subSQL(placeholder, quote, allTables))
        stmt.text += quote(" from ")
        stmt.append(self.From.subSQL(placeholder, quote, allTables))
        if self.Where is not None:
            wherestmt = self.Where.subSQL(placeholder, quote, allTables)
            stmt.text += quote(" where ")
            stmt.append(wherestmt)
        if self.GroupBy is not None:
            stmt.text += quote(" group by ")
            fst = True
            for subthing in self.GroupBy:
                if fst:
                    fst = False
                else:
                    stmt.text += ', '
                stmt.append(subthing.subSQL(placeholder, quote, allTables))
        if self.Having is not None:
            havingstmt = self.Having.subSQL(placeholder, quote, allTables)
            stmt.text += quote(" having ")
            stmt.append(havingstmt)
        if self.OrderBy is not None:
            stmt.text += quote(" order by ")
            fst = True
            for subthing in self.OrderBy:
                if fst:
                    fst = False
                else:
                    stmt.text += ', '
                stmt.append(subthing.subSQL(placeholder, quote, allTables))
            if self.Ascending is not None:
                if self.Ascending:
                    kw = " asc"
                else:
                    kw = " desc"
                stmt.append(SQLFragment(kw))
        if self.ForUpdate:
            stmt.text += quote(" for update")
        if self.Limit is not None:
            stmt.text += quote(" limit ")
            stmt.append(Constant(self.Limit).subSQL(placeholder, quote,
                                                    allTables))
        return stmt


    def subSQL(self, placeholder, quote, allTables):
        result = SQLFragment("(")
        result.append(self.toSQL(placeholder, quote))
        result.append(SQLFragment(")"))
        return result



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


    def subSQL(self, placeholder, quote, allTables):
        return _commaJoined(f.subSQL(placeholder, quote, allTables)
                            for f in self.subfragments)



class Insert(_Statement):
    """
    'insert' statement.
    """

    def __init__(self, columnMap, Return=None):
        self.columnMap = columnMap
        if isinstance(Return, (tuple, list)):
            Return = _CommaList(Return)
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


    def toSQL(self, placeholder="?", quote=lambda x: x):
        """
        @return: a 'insert' statement with placeholders and arguments

        @rtype: L{SQLFragment}
        """
        sortedColumns = sorted(self.columnMap.items(),
                               key=lambda (c, v): c.model.name)
        allTables = []
        stmt = SQLFragment('insert into ')
        stmt.append(
            TableSyntax(sortedColumns[0][0].model.table)
            .subSQL(placeholder, quote, allTables))
        stmt.append(SQLFragment(" "))
        stmt.append(_inParens(_commaJoined(
            [c.subSQL(placeholder, quote, allTables) for (c, v) in
             sortedColumns])))
        stmt.append(SQLFragment(" values "))
        stmt.append(_inParens(_commaJoined(
            [_convert(v).subSQL(placeholder, quote, allTables)
             for (c, v) in sortedColumns])))
        if self.Return is not None:
            stmt.text += ' returning '
            stmt.append(self.Return.subSQL(placeholder, quote, allTables))
        return stmt



def _convert(x):
    """
    Convert a value to an appropriate SQL AST node.  (Currently a simple
    isinstance, could be promoted to use adaptation if we want to get fancy.)
    """
    if isinstance(x, ExpressionSyntax):
        return x
    else:
        return Constant(x)



class Update(_Statement):
    """
    'update' statement
    """

    def __init__(self, columnMap, Where, Return=None):
        super(Update, self).__init__()
        _fromSameTable(_modelsFromMap(columnMap))
        self.columnMap = columnMap
        self.Where = Where
        if isinstance(Return, (tuple, list)):
            Return = _CommaList(Return)
        self.Return = Return


    def toSQL(self, placeholder="?", quote=lambda x: x):
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
                placeholder, quote, allTables)
        )
        result.text += ' set '
        result.append(
            _commaJoined(
                [c.subSQL(placeholder, quote, allTables).append(
                    SQLFragment(" = ").subSQL(placeholder, quote, allTables)
                ).append(_convert(v).subSQL(placeholder, quote, allTables))
                    for (c, v) in sortedColumns]
            )
        )
        result.append(SQLFragment( ' where '))
        result.append(self.Where.subSQL(placeholder, quote, allTables))
        if self.Return is not None:
            result.append(SQLFragment(' returning '))
            result.append(self.Return.subSQL(placeholder, quote, allTables))
        return result



class Delete(_Statement):
    """
    'delete' statement.
    """

    def __init__(self, From, Where, Return=None):
        self.From = From
        self.Where = Where
        self.Return = Return


    def toSQL(self, placeholder="?", quote=lambda x: x):
        result = SQLFragment()
        allTables = self.From.tables()
        result.text += quote('delete from ')
        result.append(self.From.subSQL(placeholder, quote, allTables))
        result.text += quote(' where ')
        result.append(self.Where.subSQL(placeholder, quote, allTables))
        if self.Return is not None:
            result.append(SQLFragment(' returning '))
            result.append(self.Return.subSQL(placeholder, quote, allTables))
        return result



class Lock(_Statement):
    """
    An SQL 'lock' statement.
    """

    def __init__(self, table, mode):
        self.table = table
        self.mode = mode


    @classmethod
    def exclusive(cls, table):
        return cls(table, 'exclusive')


    def toSQL(self, placeholder="?", quote=lambda x: x):
        return SQLFragment('lock table ').append(
            self.table.subSQL(placeholder, quote, [self.table])).append(
            SQLFragment(' in %s mode' % (self.mode,)))

class Savepoint(_Statement):
    """
    An SQL 'savepoint' statement.
    """

    def __init__(self, name):
        self.name = name


    def toSQL(self, placeholder="?", quote=lambda x: x):
        return SQLFragment('savepoint %s' % (self.name,))


class RollbackToSavepoint(_Statement):
    """
    An SQL 'rollback to savepoint' statement.
    """

    def __init__(self, name):
        self.name = name


    def toSQL(self, placeholder="?", quote=lambda x: x):
        return SQLFragment('rollback to savepoint %s' % (self.name,))


class ReleaseSavepoint(_Statement):
    """
    An SQL 'release savepoint' statement.
    """

    def __init__(self, name):
        self.name = name


    def toSQL(self, placeholder="?", quote=lambda x: x):
        return SQLFragment('release savepoint %s' % (self.name,))


class SavepointAction(object):
    
    def __init__(self, name):
        self._name = name
    
    def acquire(self, txn):
        return Savepoint(self._name).on(txn)

    def rollback(self, txn):
        return RollbackToSavepoint(self._name).on(txn)

    def release(self, txn):
        return ReleaseSavepoint(self._name).on(txn)

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


    def subSQL(self, placeholder, quote, allTables):
        return self



class Parameter(object):

    def __init__(self, name):
        self.name = name


    def __repr__(self):
        return 'Parameter(%r)' % (self.name,)


# Common helpers:

# current timestamp in UTC format.
utcNowSQL = Function('timezone')('UTC', NamedValue('CURRENT_TIMESTAMP'))

# You can't insert a column with no rows.  In SQL that just isn't valid syntax,
# and in this DAL you need at least one key or we can't tell what table you're
# talking about.  Luckily there's the 'default' keyword to the rescue, which, in
# the context of an INSERT statement means 'use the default value explicitly'.
# (Although this is a special keyword in a CREATE statement, in an INSERT it
# behaves like an expression to the best of my knowledge.)
default = NamedValue('default')

