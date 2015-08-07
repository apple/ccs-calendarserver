##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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



from twext.enterprise.jobs.jobitem import JobItem
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from txdav.common.datastore.test.util import CommonCommonTests
from txdav.common.datastore.work.load_work import TestWork



class LoadWorkTests(CommonCommonTests, TestCase):
    """
    Test L{TestWork}.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(LoadWorkTests, self).setUp()
        yield self.buildStoreAndDirectory()


    @inlineCallbacks
    def test_basicWork(self):
        """
        Verify that an L{TestWork} item can be enqueued and executed.
        """

        # do FindMinValidRevisionWork
        yield TestWork.schedule(self.storeUnderTest(), 0, 1, 2, 3)

        work = yield TestWork.all(self.transactionUnderTest())
        self.assertEqual(len(work), 1)
        self.assertEqual(work[0].delay, 3)
        job = yield JobItem.querysimple(self.transactionUnderTest(), jobID=work[0].jobID)
        self.assertEqual(len(job), 1)
        self.assertEqual(job[0].priority, 1)
        self.assertEqual(job[0].weight, 2)
        yield self.commit()

        yield JobItem.waitEmpty(self.storeUnderTest().newTransaction, reactor, 60)
