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
Interfaces, mostly related to L{twext.enterprise.adbapi2}.
"""

__all__ = [
    "IAsyncTransaction",
]

from zope.interface import Interface, Attribute


class AlreadyFinishedError(Exception):
    """
    The transaction was already completed via an C{abort} or C{commit} and
    cannot be aborted or committed again.
    """



class ConnectionError(Exception):
    """
    An error occurred with the underlying database connection.
    """



POSTGRES_DIALECT = 'postgres-dialect'
ORACLE_DIALECT = 'oracle-dialect'
ORACLE_TABLE_NAME_MAX = 30



class IAsyncTransaction(Interface):
    """
    Asynchronous execution of SQL.

    Note that there is no {begin()} method; if an L{IAsyncTransaction} exists,
    it is assumed to have been started.
    """

    paramstyle = Attribute(
        """
        A copy of the 'paramstyle' attribute from a DB-API 2.0 module.
        """)


    dialect = Attribute(
        """
        A copy of the 'dialect' attribute from the connection pool.  One of the
        C{*_DIALECT} constants in this module, such as C{POSTGRES_DIALECT}.
        """)


    def execSQL(sql, args=(), raiseOnZeroRowCount=None):
        """
        Execute some SQL.

        @param sql: an SQL string.

        @type sql: C{str}

        @param args: C{list} of arguments to interpolate into C{sql}.

        @param raiseOnZeroRowCount: a 0-argument callable which returns an
            exception to raise if the executed SQL does not affect any rows.

        @return: L{Deferred} which fires C{list} of C{tuple}

        @raise: C{raiseOnZeroRowCount} if it was specified and no rows were
            affected.
        """


    def commit():
        """
        Commit changes caused by this transaction.

        @return: L{Deferred} which fires with C{None} upon successful
            completion of this transaction.
        """


    def abort():
        """
        Roll back changes caused by this transaction.

        @return: L{Deferred} which fires with C{None} upon successful
            rollback of this transaction.
        """



class IDerivedParameter(Interface):
    """
    A parameter which needs to be derived from the underlying DB-API cursor;
    implicitly, meaning that this must also interact with the actual thread
    manipulating said cursor.  If a provider of this interface is passed in the
    C{args} argument to L{IAsyncTransaction.execSQL}, it will have its
    C{prequery} and C{postquery} methods invoked on it before and after
    executing the SQL query in question, respectively.
    """

    def preQuery(cursor):
        """
        Before running a query, invoke this method with the cursor that the
        query will be run on.

        (This can be used, for example, to allocate a special database-specific
        variable based on the cursor, like an out parameter.)

        @param cursor: the DB-API cursor.

        @return: the concrete value which should be passed to the DB-API layer.
        """


    def postQuery(cursor):
        """
        After running a query, invoke this method in the DB-API thread.

        (This can be used, for example, to manipulate any state created in the
        preQuery method.)

        @param cursor: the DB-API cursor.

        @return: C{None}
        """
