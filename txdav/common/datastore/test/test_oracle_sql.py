##
# Copyright (c) 2012-2015 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Select, Insert, Delete
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.test.util import CommonCommonTests


class OracleSpecificSQLStoreTests(CommonCommonTests, TestCase):
    """
    Tests for shared functionality in L{txdav.common.datastore.sql}.
    """

    @inlineCallbacks
    def setUp(self):
        """
        Set up two stores to migrate between.
        """
        yield super(OracleSpecificSQLStoreTests, self).setUp()
        yield self.buildStoreAndDirectory()


    @inlineCallbacks
    def test_logging(self):
        """
        txn.execSQL works with all logging options on.
        """

        # Patch config to turn on logging then rebuild the store
        self.patch(self.store, "logLabels", True)
        self.patch(self.store, "logStats", True)
        self.patch(self.store, "logSQL", True)

        txn = self.transactionUnderTest()
        cs = schema.CALENDARSERVER
        version = (yield Select(
            [cs.VALUE],
            From=cs,
            Where=cs.NAME == "VERSION",
        ).on(txn))
        self.assertNotEqual(version, None)
        self.assertEqual(len(version), 1)
        self.assertEqual(len(version[0]), 1)


    @inlineCallbacks
    def test_delete_returning(self):
        """
        txn.execSQL works with all logging options on.
        """

        txn = self.transactionUnderTest()
        cs = schema.CALENDARSERVER
        yield Insert(
            {cs.NAME: "TEST", cs.VALUE: "Value"},
        ).on(txn)
        yield self.commit()

        txn = self.transactionUnderTest()
        value = yield Delete(
            From=cs,
            Where=(cs.NAME == "TEST"),
            Return=cs.VALUE,
        ).on(txn)
        self.assertEqual(list(value), [["Value"]])

        txn = self.transactionUnderTest()
        value = yield Delete(
            From=cs,
            Where=(cs.NAME == "TEST"),
            Return=cs.VALUE,
        ).on(txn)
        self.assertEqual(list(value), [])
