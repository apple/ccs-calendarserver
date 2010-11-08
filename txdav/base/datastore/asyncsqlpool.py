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
Asynchronous multi-process connection pool.
"""

import sys

from cStringIO import StringIO
from cPickle import dumps, loads
from itertools import count

from zope.interface import implements

from twisted.internet.defer import inlineCallbacks
from twisted.internet.defer import returnValue
from txdav.idav import IAsyncTransaction
from twisted.internet.defer import Deferred
from twisted.protocols.amp import Boolean
from twisted.python.failure import Failure
from twisted.protocols.amp import Argument, String, Command, AMP, Integer
from twisted.internet import reactor as _reactor
from twisted.application.service import Service
from txdav.base.datastore.threadutils import ThreadHolder
from txdav.idav import AlreadyFinishedError
from twisted.python import log
from twisted.internet.defer import maybeDeferred
from twisted.python.components import proxyForInterface


class BaseSqlTxn(object):
    """
    L{IAsyncTransaction} implementation based on a L{ThreadHolder} in the
    current process.
    """
    implements(IAsyncTransaction)

    def __init__(self, connectionFactory, reactor=_reactor):
        """
        @param connectionFactory: A 0-argument callable which returns a DB-API
            2.0 connection.
        """
        self._completed = False
        self._holder = ThreadHolder(reactor)
        self._holder.start()
        def initCursor():
            # support threadlevel=1; we can't necessarily cursor() in a
            # different thread than we do transactions in.

            # TODO: Re-try connect when it fails.  Specify a timeout.  That
            # should happen in this layer because we need to be able to stop
            # the reconnect attempt if it's hanging.
            self._connection = connectionFactory()
            self._cursor = self._connection.cursor()

        # Note: no locking necessary here; since this gets submitted first, all
        # subsequent submitted work-units will be in line behind it and the
        # cursor will already have been initialized.
        self._holder.submit(initCursor)


    def _reallyExecSQL(self, sql, args=None, raiseOnZeroRowCount=None):
        if args is None:
            args = []
        self._cursor.execute(sql, args)
        if raiseOnZeroRowCount is not None and self._cursor.rowcount == 0:
            raise raiseOnZeroRowCount()
        if self._cursor.description:
            return self._cursor.fetchall()
        else:
            return None


    noisy = False

    def execSQL(self, *args, **kw):
        result = self._holder.submit(
            lambda : self._reallyExecSQL(*args, **kw)
        )
        if self.noisy:
            def reportResult(results):
                sys.stdout.write("\n".join([
                    "",
                    "SQL: %r %r" % (args, kw),
                    "Results: %r" % (results,),
                    "",
                    ]))
                return results
            result.addBoth(reportResult)
        return result


    def commit(self):
        if not self._completed:
            self._completed = True
            def reallyCommit():
                self._connection.commit()
            result = self._holder.submit(reallyCommit)
            return result
        else:
            raise AlreadyFinishedError()


    def abort(self):
        if not self._completed:
            self._completed = True
            def reallyAbort():
                self._connection.rollback()
            result = self._holder.submit(reallyAbort)
            return result
        else:
            raise AlreadyFinishedError()


    def __del__(self):
        if not self._completed:
            print 'BaseSqlTxn.__del__: OK'
            self.abort()


    def reset(self):
        """
        Call this when placing this transaction back into the pool.

        @raise RuntimeError: if the transaction has not been committed or
            aborted.
        """
        if not self._completed:
            raise RuntimeError("Attempt to re-set active transaction.")
        self._completed = False


    def stop(self):
        """
        Release the thread and database connection associated with this
        transaction.
        """
        self._completed = True
        self._stopped = True
        holder = self._holder
        self._holder = None
        holder.submit(self._connection.close)
        return holder.stop()



class SpooledTxn(object):
    """
    A L{SpooledTxn} is an implementation of L{IAsyncTransaction} which cannot
    yet actually execute anything, so it spools SQL reqeusts for later
    execution.  When a L{BaseSqlTxn} becomes available later, it can be
    unspooled onto that.
    """

    implements(IAsyncTransaction)

    def __init__(self):
        self._spool = []


    def _enspool(self, cmd, a=(), kw={}):
        d = Deferred()
        self._spool.append((d, cmd, a, kw))
        return d


    def _iterDestruct(self):
        """
        Iterate the spool list destructively, while popping items from the
        beginning.  This allows code which executes more SQL in the callback of
        a Deferred to not interfere with the originally submitted order of
        commands.
        """
        while self._spool:
            yield self._spool.pop(0)


    def _unspool(self, other):
        """
        Unspool this transaction onto another transaction.

        @param other: another provider of L{IAsyncTransaction} which will
            actually execute the SQL statements we have been buffering.
        """
        for (d, cmd, a, kw) in self._iterDestruct():
            self._relayCommand(other, d, cmd, a, kw)


    def _relayCommand(self, other, d, cmd, a, kw):
        """
        Relay a single command to another transaction.
        """
        maybeDeferred(getattr(other, cmd), *a, **kw).chainDeferred(d)


    def execSQL(self, *a, **kw):
        return self._enspool('execSQL', a, kw)


    def commit(self):
        return self._enspool('commit')


    def abort(self):
        return self._enspool('abort')



class PooledSqlTxn(proxyForInterface(iface=IAsyncTransaction,
                                     originalAttribute='_baseTxn')):
    """
    This is a temporary throw-away wrapper for the longer-lived BaseSqlTxn, so
    that if a badly-behaved API client accidentally hangs on to one of these
    and, for example C{.abort()}s it multiple times once another client is
    using that connection, it will get some harmless tracebacks.
    """

    def __init__(self, pool, baseTxn):
        self._pool     = pool
        self._baseTxn  = baseTxn
        self._complete = False


    def execSQL(self, *a, **kw):
        self._checkComplete()
        return super(PooledSqlTxn, self).execSQL(*a, **kw)


    def commit(self):
        self._markComplete()
        return self._repoolAfter(super(PooledSqlTxn, self).commit())


    def abort(self):
        self._markComplete()
        return self._repoolAfter(super(PooledSqlTxn, self).abort())


    def _checkComplete(self):
        """
        If the transaction is complete, raise L{AlreadyFinishedError}
        """
        if self._complete:
            raise AlreadyFinishedError()


    def _markComplete(self):
        """
        Mark the transaction as complete, raising AlreadyFinishedError.
        """
        self._checkComplete()
        self._complete = True


    def _repoolAfter(self, d):
        def repool(result):
            self._pool.reclaim(self)
            return result
        return d.addCallback(repool)



class ConnectionPool(Service, object):
    """
    This is a central service that has a threadpool and executes SQL statements
    asynchronously, in a pool.

    @ivar connectionFactory: a 0-or-1-argument callable that returns a DB-API
        connection.  The optional argument can be used as a label for
        diagnostic purposes.

    @ivar maxConnections: The connection pool will not attempt to make more
        than this many concurrent connections to the database.

    @type maxConnections: C{int}
    """

    reactor = _reactor

    def __init__(self, connectionFactory, maxConnections=10):
        super(ConnectionPool, self).__init__()
        self.free = []
        self.busy = []
        self.waiting = []
        self.connectionFactory = connectionFactory
        self.maxConnections = maxConnections


    def startService(self):
        """
        No startup necessary.
        """


    @inlineCallbacks
    def stopService(self):
        """
        Forcibly abort any outstanding transactions.
        """
        for busy in self.busy[:]:
            try:
                yield busy.abort()
            except:
                log.err()
        # all transactions should now be in the free list, since 'abort()' will
        # have put them there.
        for free in self.free:
            yield free.stop()


    def connection(self, label="<unlabeled>"):
        """
        Find a transaction; either retrieve a free one from the list or
        allocate a new one if no free ones are available.

        @return: an L{IAsyncTransaction}
        """

        overload = False
        if self.free:
            basetxn = self.free.pop(0)
        elif len(self.busy) < self.maxConnections:
            basetxn = BaseSqlTxn(
                connectionFactory=self.connectionFactory,
                reactor=self.reactor
            )
        else:
            basetxn = SpooledTxn()
            overload = True
        txn = PooledSqlTxn(self, basetxn)
        if overload:
            self.waiting.append(txn)
        else:
            self.busy.append(txn)
        return txn


    def reclaim(self, txn):
        """
        Shuck the L{PooledSqlTxn} wrapper off, and recycle the underlying
        BaseSqlTxn into the free list.
        """
        baseTxn = txn._baseTxn
        baseTxn.reset()
        self.busy.remove(txn)
        if self.waiting:
            waiting = self.waiting.pop(0)
            waiting._baseTxn._unspool(baseTxn)
            # Note: although commit() may already have been called, we don't
            # have to handle it specially here.  It only unspools after the
            # deferred returned by commit() has actually been called, and since
            # that occurs in a callFromThread, that won't happen until the next
            # iteration of the mainloop, when the _baseTxn is safely correct.
            waiting._baseTxn = baseTxn
            self.busy.append(waiting)
        else:
            self.free.append(baseTxn)



def txnarg():
    return [('transactionID', Integer())]


CHUNK_MAX = 0xffff

class BigArgument(Argument):
    """
    An argument whose payload can be larger than L{CHUNK_MAX}, by splitting
    across multiple AMP keys.
    """
    def fromBox(self, name, strings, objects, proto):
        value = StringIO()
        for counter in count():
            chunk = strings.get("%s.%d" % (name, counter))
            if chunk is None:
                break
            value.write(chunk)
        objects[name] = self.fromString(value.getvalue())


    def toBox(self, name, strings, objects, proto):
        value = StringIO(self.toString(objects[name]))
        for counter in count():
            nextChunk = value.read(CHUNK_MAX)
            if not nextChunk:
                break
            strings["%s.%d" % (name, counter)] = nextChunk



class Pickle(BigArgument):
    """
    A pickle sent over AMP.  This is to serialize the 'args' argument to
    C{execSQL}, which is the dynamically-typed 'args' list argument to a DB-API
    C{execute} function, as well as its dynamically-typed result ('rows').

    This should be cleaned up into a nicer structure, but this is not a network
    protocol, so we can be a little relaxed about security.

    This is a L{BigArgument} rather than a regular L{Argument} because
    individual arguments and query results need to contain entire vCard or
    iCalendar documents, which can easily be greater than 64k.
    """

    def toString(self, inObject):
        return dumps(inObject)

    def fromString(self, inString):
        return loads(inString)




class StartTxn(Command):
    """
    Start a transaction, identified with an ID generated by the client.
    """
    arguments = txnarg()



class ExecSQL(Command):
    """
    Execute an SQL statement.
    """
    arguments = [('sql', String()),
                 ('queryID', String()),
                 ('args', Pickle())] + txnarg()



class Row(Command):
    """
    A row has been returned.  Sent from server to client in response to
    L{ExecSQL}.
    """

    arguments = [('queryID', String()),
                 ('row', Pickle())]



class QueryComplete(Command):
    """
    A query issued with ExecSQL is complete.
    """

    arguments = [('queryID', String()),
                 ('norows', Boolean())]



class Commit(Command):
    arguments = txnarg()



class Abort(Command):
    arguments = txnarg()



class _NoRows(Exception):
    """
    Placeholder exception to report zero rows.
    """


class ConnectionPoolConnection(AMP):
    """
    A L{ConnectionPoolConnection} is a single connection to a
    L{ConnectionPool}.
    """

    def __init__(self, pool):
        """
        Initialize a mapping of transaction IDs to transaction objects.
        """
        super(ConnectionPoolConnection, self).__init__()
        self.pool = pool
        self._txns = {}


    @StartTxn.responder
    def start(self, transactionID):
        self._txns[transactionID] = self.pool.connection()
        return {}


    @ExecSQL.responder
    @inlineCallbacks
    def receivedSQL(self, transactionID, queryID, sql, args):
        try:
            rows = yield self._txns[transactionID].execSQL(sql, args, _NoRows)
        except _NoRows:
            norows = True
        else:
            norows = False
            if rows is not None:
                for row in rows:
                    # Either this should be yielded or it should be
                    # requiresAnswer=False
                    self.callRemote(Row, queryID=queryID, row=row)
        self.callRemote(QueryComplete, queryID=queryID, norows=norows)
        returnValue({})


    def _complete(self, transactionID, thunk):
        txn = self._txns.pop(transactionID)
        return thunk(txn).addCallback(lambda ignored: {})


    @Commit.responder
    def commit(self, transactionID):
        """
        Successfully complete the given transaction.
        """
        return self._complete(transactionID, lambda x: x.commit())


    @Abort.responder
    def abort(self, transactionID):
        """
        Roll back the given transaction.
        """
        return self._complete(transactionID, lambda x: x.abort())



class ConnectionPoolClient(AMP):
    """
    A client which can execute SQL.
    """
    def __init__(self):
        super(ConnectionPoolClient, self).__init__()
        self._nextID = count().next
        self._txns = {}
        self._queries = {}


    def newTransaction(self):
        txnid = str(self._nextID())
        self.callRemote(StartTxn, transactionID=txnid)
        txn = Transaction(client=self, transactionID=txnid)
        self._txns[txnid] = txn
        return txn


    @Row.responder
    def row(self, queryID, row):
        self._queries[queryID].row(row)
        return {}


    @QueryComplete.responder
    def complete(self, queryID, norows):
        self._queries.pop(queryID).done(norows)
        return {}



class _Query(object):
    def __init__(self, raiseOnZeroRowCount):
        self.results = []
        self.deferred = Deferred()
        self.raiseOnZeroRowCount = raiseOnZeroRowCount


    def row(self, row):
        """
        A row was received.
        """
        self.results.append(row)


    def done(self, norows):
        """
        The query is complete.

        @param norows: A boolean.  True if there were not any rows.
        """
        if norows and (self.raiseOnZeroRowCount is not None):
            exc = self.raiseOnZeroRowCount()
            self.deferred.errback(Failure(exc))
        else:
            self.deferred.callback(self.results)




class Transaction(object):
    """
    Async protocol-based transaction implementation.
    """

    implements(IAsyncTransaction)

    def __init__(self, client, transactionID):
        """
        Initialize a transaction with a L{ConnectionPoolClient} and a unique
        transaction identifier.
        """
        self._client = client
        self._transactionID = transactionID
        self._completed = False


    def execSQL(self, sql, args=None, raiseOnZeroRowCount=None):
        if args is None:
            args = []
        queryID = str(self._client._nextID())
        query = self._client._queries[queryID] = _Query(raiseOnZeroRowCount)
        self._client.callRemote(ExecSQL, queryID=queryID, sql=sql, args=args,
                                transactionID=self._transactionID)
        return query.deferred


    def _complete(self, command):
        if self._completed:
            raise AlreadyFinishedError()
        self._completed = True
        return self._client.callRemote(
            command, transactionID=self._transactionID
            ).addCallback(lambda x: None)


    def commit(self):
        return self._complete(Commit)


    def abort(self):
        return self._complete(Abort)


