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
Tests for L{twext.enterprise.queue}.
"""

import datetime

# TODO: There should be a store-building utility within twext.enterprise.
from txdav.common.datastore.test.util import buildStore

from twext.enterprise.dal.syntax import SchemaSyntax
from twext.enterprise.dal.record import fromTable
from twext.enterprise.dal.test.test_parseschema import SchemaTestHelper

from twext.enterprise.queue import inTransaction, PeerConnectionPool, WorkItem

from twisted.trial.unittest import TestCase
from twisted.internet.defer import Deferred, inlineCallbacks, gatherResults, passthru

from twisted.application.service import Service, MultiService

from twext.enterprise.dal.syntax import Insert
from twext.enterprise.queue import ImmediatePerformer

from twext.enterprise.dal.syntax import Select
class UtilityTests(TestCase):
    """
    Tests for supporting utilities.
    """

    def test_inTransactionSuccess(self):
        """
        L{inTransaction} invokes its C{transactionCreator} argument, and then
        returns a L{Deferred} which fires with the result of its C{operation}
        argument when it succeeds.
        """
        class faketxn(object):
            def __init__(self):
                self.commits = []
                self.aborts = []
            def commit(self):
                self.commits.append(Deferred())
                return self.commits[-1]
            def abort(self):
                self.aborts.append(Deferred())
                return self.aborts[-1]

        createdTxns = []
        def createTxn():
            createdTxns.append(faketxn())
            return createdTxns[-1]
        dfrs = []
        def operation(t):
            self.assertIdentical(t, createdTxns[-1])
            dfrs.append(Deferred())
            return dfrs[-1]
        d = inTransaction(createTxn, operation)
        x = []
        d.addCallback(x.append)
        self.assertEquals(x, [])
        self.assertEquals(len(dfrs), 1)
        dfrs[0].callback(35)
        # Commit in progress, so still no result...
        self.assertEquals(x, [])
        createdTxns[0].commits[0].callback(42)
        # Committed, everything's done.
        self.assertEquals(x, [35])



class SimpleSchemaHelper(SchemaTestHelper):
    def id(self):
        return 'worker'

SQL = passthru

schemaText = SQL("""
    create table DUMMY_WORK_ITEM (WORK_ID integer primary key,
                                  NOT_BEFORE timestamp,
                                  A integer, B integer);
    create table DUMMY_WORK_DONE (WORK_ID integer, A_PLUS_B integer);
""")

schema = SchemaSyntax(SimpleSchemaHelper().schemaFromString(schemaText))

dropSQL = ["drop table {name}".format(name=table.model.name)
           for table in schema]



class DummyWorkItem(WorkItem, fromTable(schema.DUMMY_WORK_ITEM)):
    """
    Sample L{WorkItem} subclass that adds two integers together and stores them
    in another table.
    """
    group = None

    def doWork(self):
        # Perform the work.
        result = self.a + self.b
        # Store the result.
        return (Insert({schema.DUMMY_WORK_DONE.WORK_ID: self.workID,
                        schema.DUMMY_WORK_DONE.A_PLUS_B: result})
                .on(self.transaction))



class WorkerConnectionPoolTests(TestCase):
    """
    A L{WorkerConnectionPool} is responsible for managing, in a node's
    controller (master) process, the collection of worker (slave) processes
    that are capable of executing queue work.
    """


class PeerConnectionPoolUnitTests(TestCase):
    """
    L{PeerConnectionPool} has many internal components.
    """

    def test_choosingPerformerWhenNoPeersAndNoWorkers(self):
        """
        If L{PeerConnectionPool.choosePerformer} is invoked when no workers
        have spawned and no peers have established connections (either incoming
        or outgoing), then it chooses an implementation of C{performWork} that
        simply executes the work locally.
        """
        pcp = PeerConnectionPool(None, None, 4321, schema)
        self.assertIsInstance(pcp.choosePerformer(), ImmediatePerformer)



class PeerConnectionPoolIntegrationTests(TestCase):
    """
    L{PeerConnectionPool} is the service responsible for coordinating
    eventually-consistent task queuing within a cluster.
    """

    @inlineCallbacks
    def setUp(self):
        """
        L{PeerConnectionPool} requires access to a database and the reactor.
        """
        self.store = yield buildStore(self, None)
        def doit(txn):
            return txn.execSQL(schemaText)
        yield inTransaction(lambda: self.store.newTransaction("bonus schema"),
                            doit)
        def deschema():
            @inlineCallbacks
            def deletestuff(txn):
                for stmt in dropSQL:
                    yield txn.execSQL(stmt)
            return inTransaction(self.store.newTransaction, deletestuff)
        self.addCleanup(deschema)

        from twisted.internet import reactor
        self.node1 = PeerConnectionPool(
            reactor, self.store.newTransaction, 0, schema)
        self.node2 = PeerConnectionPool(
            reactor, self.store.newTransaction, 0, schema)

        class FireMeService(Service, object):
            def __init__(self, d):
                super(FireMeService, self).__init__()
                self.d = d
            def startService(self):
                self.d.callback(None)
        d1 = Deferred()
        d2 = Deferred()
        FireMeService(d1).setServiceParent(self.node1)
        FireMeService(d2).setServiceParent(self.node2)
        ms = MultiService()
        self.node1.setServiceParent(ms)
        self.node2.setServiceParent(ms)
        ms.startService()
        self.addCleanup(ms.stopService)
        yield gatherResults([d1, d2])
        self.store.queuer = self.node1


    def test_currentNodeInfo(self):
        """
        There will be two C{NODE_INFO} rows in the database, retrievable as two
        L{NodeInfo} objects, once both nodes have started up.
        """
        @inlineCallbacks
        def check(txn):
            self.assertEquals(len((yield self.node1.activeNodes(txn))), 2)
            self.assertEquals(len((yield self.node2.activeNodes(txn))), 2)
        return inTransaction(self.store.newTransaction, check)


    @inlineCallbacks
    def test_enqueueHappyPath(self):
        """
        When a L{WorkItem} is scheduled for execution via
        L{PeerConnectionPool.enqueueWork} its C{doWork} method will be invoked
        by the time the L{Deferred} returned from the resulting
        L{WorkProposal}'s C{whenExecuted} method has fired.
        """
        # TODO: this exact test should run against NullQueuer as well.
        def operation(txn):
            # TODO: how does 'enqueue' get associated with the transaction? This
            # is not the fact with a raw t.w.enterprise transaction.  Should
            # probably do something with components.
            return txn.enqueue(DummyWorkItem, a=3, b=4, workID=4321,
                               notBefore=datetime.datetime.now())
        result = yield inTransaction(self.store.newTransaction, operation)
        # Wait for it to be executed.  Hopefully this does not time out :-\.
        yield result.whenExecuted()
        def op2(txn):
            return Select([schema.DUMMY_WORK_DONE.WORK_ID,
                           schema.DUMMY_WORK_DONE.A_PLUS_B],
                           From=schema.DUMMY_WORK_DONE).on(txn)
        rows = yield inTransaction(self.store.newTransaction, op2)
        self.assertEquals(rows, [[4321, 7]])


