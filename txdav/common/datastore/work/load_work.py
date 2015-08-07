# -*- test-case-name: txdav.common.datastore.work.test.test_revision_cleanup -*-
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

from twext.enterprise.dal.record import fromTable
from twext.enterprise.jobs.workitem import WorkItem
from twext.python.log import Logger
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred
from txdav.common.datastore.sql_tables import schema

log = Logger()


class TestWork(WorkItem, fromTable(schema.TEST_WORK)):
    """
    This work item is used solely for testing purposes to allow us to simulate different
    types of work with varying priority, weight and notBefore, and taking a variable amount of
    time to complete. This will allow us to load test the job queue.
    """

    @classmethod
    def schedule(cls, store, delay, priority, weight, runtime):
        """
        Create a new L{TestWork} item.

        @param store: the L{CommonStore} to use
        @type store: L{CommonStore}
        @param delay: seconds before work executes
        @type delay: L{int}
        @param priority: priority to use for this work
        @type priority: L{int}
        @param weight: weight to use for thus work
        @type weight: L{int}
        @param runtime: amount of time this work should take to execute in milliseconds
        @type runtime: L{int}
        """
        def _enqueue(txn):
            return TestWork.reschedule(
                txn,
                delay,
                priority=priority,
                weight=weight,
                delay=runtime
            )

        return store.inTransaction("TestWork.schedule", _enqueue)


    @inlineCallbacks
    def doWork(self):
        """
        All this work does is wait for the specified amount of time.
        """

        log.debug("TestWork started: {}".format(self.jobID))
        if self.delay != 0:
            wait = Deferred()
            def _timedDeferred():
                wait.callback(True)
            reactor.callLater(self.delay / 1000.0, _timedDeferred)
            yield wait
        log.debug("TestWork done: {}".format(self.jobID))
