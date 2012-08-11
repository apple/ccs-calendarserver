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



class _RecordBase(object):
    @classmethod
    @inlineCallbacks
    def load(cls, txn, *primaryKey):
        tbl = cls.__tbl__
        pkey = Tuple([ColumnSyntax(c) for c in tbl.model.primaryKey])
        allColumns = list(tbl)
        slct = Select(allColumns, From=tbl, Where=pkey == Tuple(map(Constant, primaryKey)))
        rows = yield slct.on(txn)
        row = rows[0]
        self = cls()
        for (column, value) in zip(allColumns, row):
            attrname = column.model.name.lower()
            setattr(self, attrname, value)
        returnValue(self)



def fromTable(table):
    """
    Create a L{type} that maps the columns from a particular table.

    A L{type} created in this manner will have instances with attributes that
    are mapped according to a naming convention like 'FOO_BAR' => 'fooBar'.

    @param table: The table.
    @type table: L{twext.enterprise.dal.syntax.TableSyntax}
    """
    return type(table.model.name, tuple([_RecordBase]),
                dict(__tbl__=table))

