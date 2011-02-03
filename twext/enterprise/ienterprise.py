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

