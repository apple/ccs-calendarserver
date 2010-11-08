# -*- test-case-name: txdav.caldav.datastore -*-
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
Tests for L{txdav.base.datastore.asyncsqlpool}.
"""

from itertools import count
from twisted.trial.unittest import TestCase

from txdav.base.datastore.asyncsqlpool import ConnectionPool
from twisted.internet.defer import inlineCallbacks


class Child(object):
    def __init__(self, parent):
        self.parent = parent
        self.parent.children.append(self)

    def close(self):
        self.parent.children.remove(self)



class Parent(object):

    def __init__(self):
        self.children = []



class FakeConnection(Parent, Child):
    """
    Fake Stand-in for DB-API 2.0 connection.
    """

    def __init__(self, factory):
        """
        Initialize list of cursors
        """
        Parent.__init__(self)
        Child.__init__(self, factory)
        self.id = factory.idcounter.next()


    @property
    def cursors(self):
        "Alias to make tests more readable."
        return self.children


    def cursor(self):
        return FakeCursor(self)


    def commit(self):
        return


    def rollback(self):
        return



class FakeCursor(Child):
    """
    Fake stand-in for a DB-API 2.0 cursor.
    """
    def __init__(self, connection):
        Child.__init__(self, connection)
        self.rowcount = 0
        # not entirely correct, but all we care about is its truth value.
        self.description = False


    @property
    def connection(self):
        "Alias to make tests more readable."
        return self.parent


    def execute(self, sql, args=()):
        self.sql = sql
        self.description = True
        self.rowcount = 1
        return


    def fetchall(self):
        """
        Just echo the SQL that was executed in the last query.
        """
        return [[self.connection.id, self.sql]]



class ConnectionFactory(Parent):
    def __init__(self):
        Parent.__init__(self)
        self.idcounter = count(1)

    @property
    def connections(self):
        "Alias to make tests more readable."
        return self.children


    def connect(self):
        return FakeConnection(self)



class ConnectionPoolTests(TestCase):

    @inlineCallbacks
    def test_tooManyConnections(self):
        """
        When the number of outstanding busy transactions exceeds the number of
        slots specified by L{ConnectionPool.maxConnections},
        L{ConnectionPool.connection} will return a L{PooledSqlTxn} that is not
        backed by any L{BaseSqlTxn}; this object will queue its SQL statements
        until an existing connection becomes available.
        """
        cf = ConnectionFactory()
        cp = ConnectionPool(cf.connect, maxConnections=2)
        cp.startService()
        self.addCleanup(cp.stopService)
        a = cp.connection()
        [[counter, echo]] = yield a.execSQL("alpha")
        b = cp.connection()
        [[bcounter, becho]] = yield b.execSQL("beta")

        # both 'a' and 'b' are holding open a connection now; let's try to open
        # a third one.  (The ordering will be deterministic even if this fails,
        # because those threads are already busy.)
        c = cp.connection()
        enqueue = c.execSQL("gamma")
        x = []
        def addtox(it):
            x.append(it)
            return it
        enqueue.addCallback(addtox)

        # Did 'c' open a connection?  Let's hope not...
        self.assertEquals(len(cf.connections), 2)
        # This assertion is _not_ deterministic, unfortunately; it's unlikely
        # that the implementation could be adjusted such that this assertion
        # would fail and the others would succeed.  However, if it does fail,
        # that's really bad, so I am leaving it regardless.
        self.failIf(bool(x), "SQL executed too soon!")
        yield b.commit()

        # Now that 'b' has committed, 'c' should be able to complete.
        [[ccounter, cecho]] = yield enqueue

        # The connection for 'a' ought to be busy, so let's make sure we're
        # using the one for 'c'.
        self.assertEquals(ccounter, bcounter)


