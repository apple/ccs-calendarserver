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
            self._connection = connectionFactory()
            self._cursor = self._connection.cursor()

        # Note: no locking necessary here; since this gets submitted first, all
        # subsequent submitted work-units will be in line behind it and the
        # cursor will already have been initialized.
        self._holder.submit(initCursor)


    def _reallyExecSQL(self, sql, args=[], raiseOnZeroRowCount=None):
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
            def reallyAbort():
                self._connection.rollback()
            self._completed = True
            result = self._holder.submit(reallyAbort)
            return result
        else:
            raise AlreadyFinishedError()


    def __del__(self):
        if not self._completed:
            print 'CommonStoreTransaction.__del__: OK'
            self.abort()


    def reset(self):
        """
        Call this when placing this transaction back into the pool.

        @raise RuntimeError: if the transaction has not been committed or
            aborted.
        """
        if not self._completed:
            raise RuntimeError("Attempt to re-set active transaction.")


    def stop(self):
        """
        Release the thread and database connection associated with this
        transaction.
        """
        self._stopped = True
        self._holder.submit(self._connection.close)
        return self._holder.stop()



class PooledDBAPITransaction(BaseSqlTxn):

    def __init__(self, pool):
        self.pool = pool
        super(PooledDBAPITransaction, self).__init__(
            self.pool.connectionFactory,
            self.pool.reactor
        )


    def commit(self):
        return self.repoolAfter(super(PooledDBAPITransaction, self).commit())


    def abort(self):
        return self.repoolAfter(super(PooledDBAPITransaction, self).abort())


    def repoolAfter(self, d):
        def repool(result):
            self.pool.reclaim(self)
            return result
        return d.addCallback(repool)



class ConnectionPool(Service, object):
    """
    This is a central service that has a threadpool and executes SQL statements
    asynchronously, in a pool.
    """

    reactor = _reactor

    def __init__(self, connectionFactory):
        super(ConnectionPool, self).__init__()
        self.free = []
        self.busy = []
        self.connectionFactory = connectionFactory


    def startService(self):
        """
        No startup necessary.
        """


    @inlineCallbacks
    def stopService(self):
        """
        Forcibly abort any outstanding transactions.
        """
        for busy in self.busy:
            try:
                yield busy.abort()
            except:
                log.err()


    def connection(self):
        if self.free:
            txn = self.free.pop(0)
        else:
            txn = PooledDBAPITransaction(self)
        self.busy.append(txn)
        return self.txn


    def reclaim(self, txn):
        txn.reset()
        self.free.append(txn)
        self.busy.remove(txn)



def txnarg():
    return [('transactionID', Integer())]



class Pickle(Argument):
    """
    A pickle sent over AMP.  This is to serialize the 'args' argument to
    execSQL, which is the dynamically-typed 'args' list argument to a DB-API
    C{execute} function, as well as its dynamically-typed result ('rows').

    This should be cleaned up into a nicer structure, but this is not a network
    protocol, so we can be a little relaxed about security.
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


    @StartTxn.responder
    def start(self, transactionID):
        self._txns[transactionID] = self.pool.connection()
        return {}


    @ExecSQL.responder
    @inlineCallbacks
    def sendSQL(self, transactionID, queryID, sql, args):
        norows = True
        try:
            rows = yield self._txns[transactionID].execSQL(sql, args)
        except _NoRows:
            pass
        else:
            if rows is not None:
                for row in rows:
                    norows = False
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
        txn = Transaction(client=self, transactionID=txnid)
        self._txns[txnid] = txn
        self.callRemote(StartTxn, transactionID=txnid)
        return txn


    @Row.responder
    def row(self, queryID, row):
        self._queries[queryID].row(row)
        return {}


    @QueryComplete.responder
    def complete(self, queryID, norows):
        self.queries.pop(queryID).done(norows)
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

        @param norows: A boolean.  True if there were any rows.
        """
        if norows and self.raiseOnZeroRowCount is not None:
            exc = self.raiseOnZeroRowCount()
            self.deferred.errback(Failure(exc))
        else:
            self.deferred.callback(self.results)




class Transaction(object):
    """
    Async transaction implementation.
    """

    implements(IAsyncTransaction)

    def __init__(self, client, transactionID):
        """
        Initialize a transaction with a L{ConnectionPoolClient} and a unique
        transaction identifier.
        """
        self.client = client
        self.transactionID = transactionID


    def execSQL(self, sql, args, raiseOnZeroRowCount=None):
        queryID = self.client._nextID()
        d = Deferred()
        self.client._queries[queryID] = _Query(raiseOnZeroRowCount)
        self.client.callRemote(ExecSQL, queryID=queryID, sql=sql, args=args)
        return d


    def complete(self, command):
        return self.client.callRemote(
            command, transactionID=self.transactionID
            ).addCallback(lambda x: None)


    def commit(self):
        return self.complete(Commit)


    def abort(self):
        return self.complete(Abort)


