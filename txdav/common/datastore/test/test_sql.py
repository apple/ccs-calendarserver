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
Tests for L{txdav.common.datastore.sql}.
"""

from twext.enterprise.dal.syntax import Select
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase
from txdav.common.datastore.sql import log, CommonStoreTransactionMonitor
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.test.util import CommonCommonTests, buildStore
from txdav.common.icommondatastore import AllRetriesFailed


class SubTransactionTests(CommonCommonTests, TestCase):
    """
    Tests for L{UpgradeToDatabaseService}.
    """

    @inlineCallbacks
    def setUp(self):
        """
        Set up two stores to migrate between.
        """
        yield super(SubTransactionTests, self).setUp()
        self._sqlStore = yield buildStore(self, self.notifierFactory)


    def storeUnderTest(self):
        """
        Return a store for testing.
        """
        return self._sqlStore


    @inlineCallbacks
    def test_logging(self):
        """
        txn.execSQL works with all logging options on.
        """
        
        # Patch config to turn on logging then rebuild the store
        self.patch(self._sqlStore, "logLabels", True)
        self.patch(self._sqlStore, "logStats", True)
        self.patch(self._sqlStore, "logSQL", True)

        txn = self.transactionUnderTest()
        cs = schema.CALENDARSERVER
        version = (yield Select(
                [cs.VALUE,],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(txn))
        self.assertNotEqual(version, None)
        self.assertEqual(len(version), 1)
        self.assertEqual(len(version[0]), 1)

    def test_logWaits(self):
        """
        CommonStoreTransactionMonitor logs waiting transactions.
        """
        
        c = Clock()
        self.patch(CommonStoreTransactionMonitor, "callLater", c.callLater)

        # Patch config to turn on log waits then rebuild the store
        self.patch(self._sqlStore, "logTransactionWaits", 1)
        
        ctr = [0]
        def counter(_ignore):
            ctr[0] += 1
        self.patch(log, "error", counter)

        txn = self.transactionUnderTest()        
 
        c.advance(2)
        self.assertNotEqual(ctr[0], 0)
        txn.abort()


    def test_txnTimeout(self):
        """
        CommonStoreTransactionMonitor terminates long transactions.
        """
        
        c = Clock()
        self.patch(CommonStoreTransactionMonitor, "callLater", c.callLater)

        # Patch config to turn on transaction timeouts then rebuild the store
        self.patch(self._sqlStore, "timeoutTransactions", 1)
        
        ctr = [0]
        def counter(_ignore):
            ctr[0] += 1
        self.patch(log, "error", counter)

        txn = self.transactionUnderTest()

        c.advance(2)
        self.assertNotEqual(ctr[0], 0)
        self.assertTrue(txn._sqlTxn._completed)


    def test_logWaitsAndTxnTimeout(self):
        """
        CommonStoreTransactionMonitor logs waiting transactions and terminates long transactions.
        """
        
        c = Clock()
        self.patch(CommonStoreTransactionMonitor, "callLater", c.callLater)

        # Patch config to turn on log waits then rebuild the store
        self.patch(self._sqlStore, "logTransactionWaits", 1)
        self.patch(self._sqlStore, "timeoutTransactions", 2)
        
        ctr = [0, 0]
        def counter(logStr):
            if "wait" in logStr:
                ctr[0] += 1
            elif "abort" in logStr:
                ctr[1] += 1
        self.patch(log, "error", counter)

        txn = self.transactionUnderTest()
        
        c.advance(2)
        self.assertNotEqual(ctr[0], 0)
        self.assertNotEqual(ctr[1], 0)
        self.assertTrue(txn._sqlTxn._completed)

    @inlineCallbacks
    def test_subtransactionOK(self):
        """
        txn.subtransaction runs loop once.
        """
        
        txn = self.transactionUnderTest()
        ctr = [0]

        def _test(subtxn):
            ctr[0] += 1
            cs = schema.CALENDARSERVER
            return Select(
                [cs.VALUE,],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(subtxn)
            
        (yield txn.subtransaction(_test, retries=0))[0][0]
        self.assertEqual(ctr[0], 1)


    @inlineCallbacks
    def test_subtransactionOKAfterRetry(self):
        """
        txn.subtransaction runs loop twice when one failure.
        """
        
        txn = self.transactionUnderTest()
        ctr = [0]

        def _test(subtxn):
            ctr[0] += 1
            if ctr[0] == 1:
                raise ValueError
            cs = schema.CALENDARSERVER
            return Select(
                [cs.VALUE,],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(subtxn)
            
        (yield txn.subtransaction(_test, retries=1))[0][0]
        self.assertEqual(ctr[0], 2)


    @inlineCallbacks
    def test_subtransactionFailNoRetry(self):
        """
        txn.subtransaction runs loop once when one failure and no retries.
        """
        
        txn = self.transactionUnderTest()
        ctr = [0]

        def _test(subtxn):
            ctr[0] += 1
            raise ValueError
            cs = schema.CALENDARSERVER
            return Select(
                [cs.VALUE,],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(subtxn)
        
        try:
            (yield txn.subtransaction(_test, retries=0))[0][0]
        except AllRetriesFailed:
            pass
        else:
            self.fail("AllRetriesFailed not raised")
        self.assertEqual(ctr[0], 1)


    @inlineCallbacks
    def test_subtransactionFailSomeRetries(self):
        """
        txn.subtransaction runs loop three times when all fail and two retries requested.
        """
        
        txn = self.transactionUnderTest()
        ctr = [0]

        def _test(subtxn):
            ctr[0] += 1
            raise ValueError
            cs = schema.CALENDARSERVER
            return Select(
                [cs.VALUE,],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(subtxn)
        
        try:
            (yield txn.subtransaction(_test, retries=2))[0][0]
        except AllRetriesFailed:
            pass
        else:
            self.fail("AllRetriesFailed not raised")
        self.assertEqual(ctr[0], 3)
