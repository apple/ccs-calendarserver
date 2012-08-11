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

class ReadOnly(AttributeError):
    """
    A caller attempted to set an attribute on a database-backed record, rather
    than updating it through L{_RecordBase.update}.
    """

    def __init__(self, className, attributeName):
        self.className = className
        self.attributeName = attributeName
        super(ReadOnly, self).__init__()



class _RecordBase(object):
    """
    Superclass for all database-backed record classes.  (i.e.  an object mapped
    from a database record).

    @cvar __colmap__: map of L{ColumnSyntax} objects to attribute names.
    @type __colmap__: L{dict}

    @cvar __attrmap__: map of attribute names to L{ColumnSyntax} objects.
    @type __attrmap__: L{dict}
    """
    @classmethod
    @inlineCallbacks
    def load(cls, txn, *primaryKey):
        tbl = cls.__tbl__
        pkey = Tuple([ColumnSyntax(c) for c in tbl.model.primaryKey])
        allColumns = list(tbl)
        slct = Select(allColumns, From=tbl,
                      Where=pkey == Tuple(map(Constant, primaryKey)))
        rows = yield slct.on(txn)
        row = rows[0]
        self = cls()
        for (column, value) in zip(allColumns, row):
            setattr(self, cls.__colmap__[column], value)
        returnValue(self)


    @classmethod
    @inlineCallbacks
    def create(cls, txn, *a, **k):
        """
        Create a row.
        """
        self = cls()
        colmap = {}
        attrtocol = cls.__attrmap__
        for attr in k:
            setattr(self, attr, k[attr])
            # FIXME: better error reporting
            colmap[attrtocol[attr]] = k[attr]
        yield Insert(colmap).on(txn)
        returnValue(self)


    def update(self, **kw):
        """
        Update the given attributes in the database.

        @return: a L{Deferred} that fires when the updates have been completed.
        """



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
    return type(table.model.name, tuple([_RecordBase]),
                dict(__tbl__=table, __attrmap__=attrmap, __colmap__=colmap))


__all__ = [
    "ReadOnly",
    "fromTable",
]