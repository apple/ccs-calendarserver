##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
Tests for mutual exclusion locks.
"""

from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

from twext.enterprise.fixtures import buildConnectionPool
from twext.enterprise.locking import NamedLock, LockTimeout
from twext.enterprise.dal.syntax import Select
from twext.enterprise.locking import LockSchema

schemaText = """
create table NAMED_LOCK (LOCK_NAME varchar(255) unique primary key);
"""

class TestLocking(TestCase):
    """
    Test locking and unlocking a database row.
    """

    def setUp(self):
        """
        Build a connection pool for the tests to use.
        """
        self.pool = buildConnectionPool(self, schemaText)


    @inlineCallbacks
    def test_acquire(self):
        """
        Acquiring a lock adds a row in that transaction.
        """
        txn = self.pool.connection()
        yield NamedLock.acquire(txn, u"a test lock")
        rows = yield Select(From=LockSchema.NAMED_LOCK).on(txn)
        self.assertEquals(rows, [tuple([u"a test lock"])])


    @inlineCallbacks
    def test_release(self):
        """
        Releasing an acquired lock removes the row.
        """
        txn = self.pool.connection()
        lck = yield NamedLock.acquire(txn, u"a test lock")
        yield lck.release()
        rows = yield Select(From=LockSchema.NAMED_LOCK).on(txn)
        self.assertEquals(rows, [])


    @inlineCallbacks
    def test_autoRelease(self):
        """
        Committing a transaction automatically releases all of its locks.
        """
        txn = self.pool.connection()
        yield NamedLock.acquire(txn, u"something")
        yield txn.commit()
        txn2 = self.pool.connection()
        rows = yield Select(From=LockSchema.NAMED_LOCK).on(txn2)
        self.assertEquals(rows, [])


    @inlineCallbacks
    def test_timeout(self):
        """
        Trying to acquire second lock times out.
        """
        txn1 = self.pool.connection()
        yield NamedLock.acquire(txn1, u"a test lock")

        txn2 = self.pool.connection()
        yield self.assertFailure(NamedLock.acquire(txn2, u"a test lock"), LockTimeout)
        yield txn2.abort()
        self.flushLoggedErrors()
