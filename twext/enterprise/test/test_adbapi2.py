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
Tests for L{twext.enterprise.adbapi2}.
"""

from itertools import count

from twisted.trial.unittest import TestCase

from twisted.internet.defer import inlineCallbacks

from twisted.internet.defer import execute
from twext.enterprise.adbapi2 import ConnectionPool


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
        self._resultQueue = []
        self.defaultConnect()


    @property
    def connections(self):
        "Alias to make tests more readable."
        return self.children


    def connect(self):
        """
        Implement the C{ConnectionFactory} callable expected by
        L{ConnectionPool}.
        """
        if self._resultQueue:
            thunk = self._resultQueue.pop(0)
        else:
            thunk = self._default
        return thunk()


    def willConnect(self):
        """
        Used by tests to queue a successful result for connect().
        """
        def thunk():
            return FakeConnection(self)
        self._resultQueue.append(thunk)


    def willFail(self):
        """
        Used by tests to queue a successful result for connect().
        """
        def thunk():
            raise FakeConnectionError()
        self._resultQueue.append(thunk)


    def defaultConnect(self):
        """
        By default, connection attempts will succeed.
        """
        self.willConnect()
        self._default = self._resultQueue.pop()


    def defaultFail(self):
        """
        By default, connection attempts will fail.
        """
        self.willFail()
        self._default = self._resultQueue.pop()



class FakeConnectionError(Exception):
    """
    Synthetic error that might occur during connection.
    """



class FakeThreadHolder(object):
    """
    Run things submitted to this ThreadHolder on the main thread, so that
    execution is easier to control.
    """

    def __init__(self):
        self.started = False
        self.stopped = False


    def start(self):
        """
        Mark this L{FakeThreadHolder} as not started.
        """
        self.started = True


    def stop(self):
        """
        Mark this L{FakeThreadHolder} as stopped.
        """
        self.stopped = True


    def submit(self, work):
        """
        Call the function.
        """
        return execute(work)



class ConnectionPoolTests(TestCase):
    """
    Tests for L{ConnectionPool}.
    """

    def setUp(self):
        """
        Create a L{ConnectionPool} attached to a C{ConnectionFactory}.  Start
        the L{ConnectionPool}.
        """
        self.holders = []
        self.factory = ConnectionFactory()
        self.pool = ConnectionPool(self.factory.connect, maxConnections=2)
        self.pool._createHolder = self.makeAHolder
        self.pool.startService()
        self.addCleanup(self.pool.stopService)


    def makeAHolder(self):
        """
        Make a ThreadHolder-alike.
        """
        fth = FakeThreadHolder()
        self.holders.append(fth)
        return fth


    @inlineCallbacks
    def test_tooManyConnections(self):
        """
        When the number of outstanding busy transactions exceeds the number of
        slots specified by L{ConnectionPool.maxConnections},
        L{ConnectionPool.connection} will return a L{PooledSqlTxn} that is not
        backed by any L{BaseSqlTxn}; this object will queue its SQL statements
        until an existing connection becomes available.
        """
        a = self.pool.connection()
        [[counter, echo]] = yield a.execSQL("alpha")
        b = self.pool.connection()
        [[bcounter, becho]] = yield b.execSQL("beta")

        # both 'a' and 'b' are holding open a connection now; let's try to open
        # a third one.  (The ordering will be deterministic even if this fails,
        # because those threads are already busy.)
        c = self.pool.connection()
        enqueue = c.execSQL("gamma")
        x = []
        def addtox(it):
            x.append(it)
            return it
        enqueue.addCallback(addtox)

        # Did 'c' open a connection?  Let's hope not...
        self.assertEquals(len(self.factory.connections), 2)

        self.failIf(bool(x), "SQL executed too soon!")
        yield b.commit()

        # Now that 'b' has committed, 'c' should be able to complete.
        [[ccounter, cecho]] = yield enqueue

        # The connection for 'a' ought to be busy, so let's make sure we're
        # using the one for 'c'.
        self.assertEquals(ccounter, bcounter)


    @inlineCallbacks
    def test_stopService(self):
        """
        L{ConnectionPool.stopService} stops all the associated L{ThreadHolder}s
        and thereby frees up the resources it is holding.
        """
        a = self.pool.connection()
        [[counter, echo]] = yield a.execSQL("alpha")
        self.assertEquals(len(self.holders), 1)
        [holder] = self.holders
        self.assertEquals(holder.started, True)
        self.assertEquals(holder.stopped, False)
        yield self.pool.stopService()
        self.assertEquals(len(self.holders), 1)
        self.assertEquals(holder.started, True)
        self.assertEquals(holder.stopped, True)


    def test_retryAfterConnectError(self):
        """
        When the C{connectionFactory} passed to L{ConnectionPool} raises an
        exception, the L{ConnectionPool} will log the exception and delay
        execution of a new connection's SQL methods until an attempt succeeds.
        """
        self.factory.defaultFail()
        c = self.pool.connection()
        errors = self.flushLoggedErrors(FakeConnectionError)
        self.assertEquals(len(errors), 1)
        d = c.execSQL("alpha")
        happened = []
        d.addBoth(happened.append)
        self.assertEquals(happened, [])


