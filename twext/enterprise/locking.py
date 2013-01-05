# -*- test-case-name: twext.enterprise.test.test_locking -*-
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
Utilities to restrict concurrency based on mutual exclusion.
"""

from twext.enterprise.dal.model import Table
from twext.enterprise.dal.model import SQLType
from twext.enterprise.dal.model import Constraint
from twext.enterprise.dal.syntax import SchemaSyntax
from twext.enterprise.dal.model import Schema
from twext.enterprise.dal.record import Record
from twext.enterprise.dal.record import fromTable


class AlreadyUnlocked(Exception):
    """
    The lock you were trying to unlock was already unlocked.
    """



def makeLockSchema(inSchema):
    """
    Create a self-contained schema just for L{Locker} use, in C{inSchema}.

    @param inSchema: a L{Schema} to add the locks table to.
    @type inSchema: L{Schema}

    @return: inSchema
    """
    LockTable = Table(inSchema, 'NAMED_LOCK')

    LockTable.addColumn("LOCK_NAME", SQLType("varchar", 255))
    LockTable.tableConstraint(Constraint.NOT_NULL, ["LOCK_NAME"])
    LockTable.tableConstraint(Constraint.UNIQUE, ["LOCK_NAME"])
    LockTable.primaryKey = [LockTable.columnNamed("LOCK_NAME")]

    return inSchema

LockSchema = SchemaSyntax(makeLockSchema(Schema(__file__)))




class NamedLock(Record, fromTable(LockSchema.NAMED_LOCK)):
    """
    An L{AcquiredLock} lock against a shared data store that the current
    process holds via the referenced transaction.
    """

    @classmethod
    def acquire(cls, txn, name, wait=False):
        """
        Acquire a lock with the given name.

        @param name: The name of the lock to acquire.  Against the same store,
            no two locks may be acquired.
        @type name: L{unicode}

        @param wait: Whether or not to wait for the lock.  If L{True}, the
            L{Deferred} returned by L{lock} make some time to fire; if
            L{False}, it should quickly fail instead.

        @return: a L{Deferred} that fires with an L{AcquiredLock} when the lock
            has fired, or fails when the lock has not been acquired.
        """
        return cls.create(txn, lockName=name)


    def release(self, ignoreAlreadyUnlocked=False):
        """
        Release this lock.

        @param ignoreAlreadyUnlocked: If you don't care about the current
            status of this lock, and just want to release it if it is still
            acquired, pass this parameter as L{True}.  Otherwise this method
            will raise an exception if it is invoked when the lock has already
            been released.

        @raise: L{AlreadyUnlocked}

        @return: A L{Deferred} that fires with L{None} when the lock has been
            unlocked.
        """
        raise NotImplementedError()



