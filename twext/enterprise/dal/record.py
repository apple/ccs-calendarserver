# -*- test-case-name: twext.enterprise.dal.test.test_record -*-
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
RECORD: Relational Entity Creation from Objects Representing Data.

This is an asynchronous object-relational mapper based on
L{twext.enterprise.dal.syntax}.
"""

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.enterprise.dal.syntax import Select, Tuple, Constant, ColumnSyntax
from twext.enterprise.dal.syntax import Insert
from twext.enterprise.dal.syntax import Update
from twext.enterprise.dal.syntax import Delete

class ReadOnly(AttributeError):
    """
    A caller attempted to set an attribute on a database-backed record, rather
    than updating it through L{_RecordBase.update}.
    """

    def __init__(self, className, attributeName):
        self.className = className
        self.attributeName = attributeName
        super(ReadOnly, self).__init__("SQL-backed attribute '{}.{}' is "
                                       "read-only. Use '.update(...)' to "
                                       "modify attributes."
                                       .format(className, attributeName))



class NoSuchRecord(Exception):
    """
    No matching record could be found.
    """



class _RecordBase(object):
    """
    Superclass for all database-backed record classes.  (i.e.  an object mapped
    from a database record).

    @cvar __tbl__: the table that represents this L{_RecordBase} in the
        database.
    @type __tbl__: L{TableSyntax}

    @cvar __colmap__: map of L{ColumnSyntax} objects to attribute names.
    @type __colmap__: L{dict}

    @cvar __attrmap__: map of attribute names to L{ColumnSyntax} objects.
    @type __attrmap__: L{dict}
    """

    __txn__ = None
    def __setattr__(self, name, value):
        """
        Once the transaction is initialized, this object is immutable.  If you
        want to change it, use L{_RecordBase.update}.
        """
        if self.__txn__ is not None:
            raise ReadOnly(self.__class__.__name__, name)
        return super(_RecordBase, self).__setattr__(name, value)


    @classmethod
    def _primaryKeyExpression(cls):
        return Tuple([ColumnSyntax(c) for c in cls.__tbl__.model.primaryKey])


    def _primaryKeyValue(self):
        val = []
        for col in self._primaryKeyExpression().columns:
            val.append(getattr(self, self.__class__.__colmap__[col]))
        return val


    @classmethod
    def _primaryKeyComparison(cls, primaryKey):
        return (cls._primaryKeyExpression() ==
                Tuple(map(Constant, primaryKey)))


    @classmethod
    @inlineCallbacks
    def load(cls, txn, *primaryKey):
        self = (yield cls.query(txn, cls._primaryKeyComparison(primaryKey)))[0]
        returnValue(self)


    @classmethod
    @inlineCallbacks
    def create(cls, txn, *a, **k):
        """
        Create a row.

        Used like this::

            MyRecord.create(column1=1, column2=u'two')
        """
        self = cls()
        colmap = {}
        attrtocol = cls.__attrmap__
        for attr in k:
            setattr(self, attr, k[attr])
            # FIXME: better error reporting
            colmap[attrtocol[attr]] = k[attr]
        yield Insert(colmap).on(txn)
        self.__txn__ = txn
        returnValue(self)


    def delete(self):
        """
        Delete this row from the database.

        @return: a L{Deferred} which fires when the underlying row has been
            deleted.
        """
        return Delete(From=self.__tbl__,
                      Where=self._primaryKeyComparison(self._primaryKeyValue())
                      ).on(self.__txn__)


    @inlineCallbacks
    def update(self, **kw):
        """
        Modify the given attributes in the database.

        @return: a L{Deferred} that fires when the updates have been sent to
            the database.
        """
        colmap = {}
        for k, v in kw.iteritems():
            colmap[self.__attrmap__[k]] = v
        yield (Update(colmap,
                      Where=self._primaryKeyComparison(self._primaryKeyValue()))
                .on(self.__txn__))
        self.__dict__.update(kw)


    @classmethod
    @inlineCallbacks
    def pop(cls, primaryKey):
        """
        Atomically retrieve and remove a row from this L{_RecordBase}'s table
        with a primary key value of C{primaryKey}.

        @return: a L{Deferred} that fires with an instance of C{cls}, or fails
            with L{NoSuchRecord} if there were no records in the database.
        @rtype: L{Deferred}
        """
        yield None


    @classmethod
    @inlineCallbacks
    def query(cls, txn, expr, order=None, ascending=True):
        """
        Query the table that corresponds to C{cls}, and return instances of
        C{cls} corresponding to the rows that are returned from that table.
        """
        tbl = cls.__tbl__
        allColumns = list(tbl)
        kw = {}
        if order is not None:
            kw.update(OrderBy=order, Ascending=ascending)
        slct = Select(allColumns, From=tbl, Where=expr, **kw)
        rows = yield slct.on(txn)
        selves = []
        for row in rows:
            self = cls()
            for (column, value) in zip(allColumns, row):
                name = cls.__colmap__[column]
                setattr(self, name, value)
            self.__txn__ = txn
            selves.append(self)
        returnValue(selves)



def fromTable(table):
    """
    Create a L{type} that maps the columns from a particular table.

    A L{type} created in this manner will have instances with attributes that
    are mapped according to a naming convention like 'FOO_BAR' => 'fooBar'.

    @param table: The table.
    @type table: L{twext.enterprise.dal.syntax.TableSyntax}
    """
    attrmap = {}
    colmap = {}
    allColumns = list(table)
    for column in allColumns:
        attrname = column.model.name.lower()
        attrmap[attrname] = column
        colmap[column] = attrname
    ns = dict(__tbl__=table, __attrmap__=attrmap, __colmap__=colmap)
    ns.update(attrmap)
    return type(table.model.name, tuple([_RecordBase]), ns)



__all__ = [
    "ReadOnly",
    "fromTable",
]