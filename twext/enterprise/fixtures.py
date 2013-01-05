# -*- test-case-name: twext.enterprise.test.test_fixtures -*-
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
Fixtures for testing code that uses ADBAPI2.
"""

import sqlite3

from twext.enterprise.adbapi2 import ConnectionPool
from twext.enterprise.ienterprise import SQLITE_DIALECT

def buildConnectionPool(testCase, schemaText="", dialect=SQLITE_DIALECT):
    """
    Build a L{ConnectionPool} for testing purposes, with the given C{testCase}.

    @param testCase: the test case to attach the resulting L{ConnectionPool}
        to.
    @type testCase: L{twisted.trial.unittest.TestCase}

    @param schemaText: The text of the schema with which to initialize the
        database.
    @type schemaText: L{str}

    @return: a L{ConnectionPool} service whose C{startService} method has
        already been invoked.
    @rtype: L{ConnectionPool}
    """
    sqlitename = testCase.mktemp()
    seqs = {}
    def connectionFactory(label=testCase.id()):
        conn = sqlite3.connect(sqlitename)
        def nextval(seq):
            result = seqs[seq] = seqs.get(seq, 0) + 1
            return result
        conn.create_function("nextval", 1, nextval)
        return conn
    con = connectionFactory()
    con.executescript(schemaText)
    con.commit()
    pool = ConnectionPool(connectionFactory, paramstyle='numeric',
                          dialect=SQLITE_DIALECT)
    pool.startService()
    testCase.addCleanup(pool.stopService)
    return pool
