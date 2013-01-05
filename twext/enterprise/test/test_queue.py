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

from twisted.trial.unittest import TestCase
from twisted.internet.defer import Deferred

from twext.enterprise.queue import inTransaction

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


