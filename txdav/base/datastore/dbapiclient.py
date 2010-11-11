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
General utility client code for interfacing with DB-API 2.0 modules.
"""

class DiagnosticCursorWrapper(object):
    """
    Diagnostic wrapper around a DB-API 2.0 cursor for debugging connection
    status.
    """

    def __init__(self, realCursor, connectionWrapper):
        self.realCursor = realCursor
        self.connectionWrapper = connectionWrapper


    @property
    def rowcount(self):
        return self.realCursor.rowcount


    @property
    def description(self):
        return self.realCursor.description


    def execute(self, sql, args=()):
        self.connectionWrapper.state = 'executing %r' % (sql,)
# Use log.debug
#        sys.stdout.write(
#            "Really executing SQL %r in thread %r\n" %
#            ((sql % tuple(args)), thread.get_ident())
#        )
        self.realCursor.execute(sql, args)


    def close(self):
        self.realCursor.close()


    def fetchall(self):
        results = self.realCursor.fetchall()
# Use log.debug
#        sys.stdout.write(
#            "Really fetching results %r thread %r\n" %
#            (results, thread.get_ident())
#        )
        return results



class DiagnosticConnectionWrapper(object):
    """
    Diagnostic wrapper around a DB-API 2.0 connection for debugging connection
    status.
    """

    def __init__(self, realConnection, label):
        self.realConnection = realConnection
        self.label = label
        self.state = 'idle (start)'


    def cursor(self):
        return DiagnosticCursorWrapper(self.realConnection.cursor(), self)


    def close(self):
        self.realConnection.close()
        self.state = 'closed'


    def commit(self):
        self.realConnection.commit()
        self.state = 'idle (after commit)'


    def rollback(self):
        self.realConnection.rollback()
        self.state = 'idle (after rollback)'



class DBAPIConnector(object):
    """
    A simple wrapper for DB-API connectors.

    @ivar dbModule: the DB-API module to use.
    """

    def __init__(self, dbModule, preflight, *connectArgs, **connectKw):
        self.dbModule = dbModule
        self.connectArgs = connectArgs
        self.connectKw = connectKw
        self.preflight = preflight


    def connect(self, label="<unlabeled>"):
        connection = self.dbModule.connect(*self.connectArgs, **self.connectKw)
        w = DiagnosticConnectionWrapper(connection, label)
        self.preflight(w)
        return w



def postgresPreflight(connection):
    """
    Pre-flight function for PostgreSQL connections: enable standard conforming
    strings, and set a non-infinite statement timeout.
    """
    c = connection.cursor()

    # Turn on standard conforming strings.  This option is _required_ if
    # you want to get correct behavior out of parameter-passing with the
    # pgdb module.  If it is not set then the server is potentially
    # vulnerable to certain types of SQL injection.
    c.execute("set standard_conforming_strings=on")

    # Abort any second that takes more than 30 seconds (30000ms) to
    # execute. This is necessary as a temporary workaround since it's
    # hypothetically possible that different database operations could
    # block each other, while executing SQL in the same process (in the
    # same thread, since SQL executes in the main thread now).  It's
    # preferable to see some exceptions while we're in this state than to
    # have the entire worker process hang.
    c.execute("set statement_timeout=30000")

    # pgdb (as per DB-API 2.0) automatically puts the connection into a
    # 'executing a transaction' state when _any_ statement is executed on
    # it (even these not-touching-any-data statements); make sure to commit
    # first so that the application sees a fresh transaction, and the
    # connection can safely be pooled without executing anything on it.
    connection.commit()
    c.close()
