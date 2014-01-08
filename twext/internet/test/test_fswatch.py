##
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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
Tests for L{twext.internet.fswatch}.
"""

from twext.internet.fswatch import DirectoryChangeListener, patchReactor, \
    IDirectoryChangeListenee
from twisted.internet.kqreactor import KQueueReactor
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from zope.interface import implements


class KQueueReactorTestFixture(object):

    def __init__(self, testCase, action=None, timeout=10):
        """
        Creates a kqueue reactor for use in unit tests.  The reactor is patched
        with the vnode event handler.  Once the reactor is running, it will
        call a supplied method.  It's expected that the method will ultimately
        trigger the stop() of the reactor.  The reactor will time out after 10
        seconds.

        @param testCase: a test method which is needed for adding cleanup to
        @param action: a method which will get called after the reactor is
            running
        @param timeout: how many seconds to keep the reactor running before
            giving up and stopping it
        """
        self.testCase = testCase
        self.reactor = KQueueReactor()
        patchReactor(self.reactor)
        self.action = action
        self.timeout = timeout

        def maybeStop():
            if self.reactor.running:
                return self.reactor.stop()

        self.testCase.addCleanup(maybeStop)


    def runReactor(self):
        """
        Run the test reactor, adding cleanup code to stop if after a timeout,
        and calling the action method
        """
        def getReadyToStop():
            self.reactor.callLater(self.timeout, self.reactor.stop)
        self.reactor.callWhenRunning(getReadyToStop)
        if self.action is not None:
            self.reactor.callWhenRunning(self.action)
        self.reactor.run(installSignalHandlers=False)



class DataStoreMonitor(object):
    """
    Stub IDirectoryChangeListenee
    """
    implements(IDirectoryChangeListenee)


    def __init__(self, reactor, storageService):
        """
        @param storageService: the service making use of the DataStore
            directory; we send it a hardStop() to shut it down
        """
        self._reactor = reactor
        self._storageService = storageService
        self.methodCalled = ""


    def disconnected(self):
        self.methodCalled = "disconnected"
        self._storageService.hardStop()
        self._reactor.stop()


    def deleted(self):
        self.methodCalled = "deleted"
        self._storageService.hardStop()
        self._reactor.stop()


    def renamed(self):
        self.methodCalled = "renamed"
        self._storageService.hardStop()
        self._reactor.stop()


    def connectionLost(self, reason):
        pass



class StubStorageService(object):
    """
    Implements hardStop for testing
    """

    def __init__(self, ignored):
        self.stopCalled = False


    def hardStop(self):
        self.stopCalled = True



class DirectoryChangeListenerTestCase(TestCase):

    def test_delete(self):
        """
        Verify directory deletions can be monitored
        """

        self.tmpdir = FilePath(self.mktemp())
        self.tmpdir.makedirs()

        def deleteAction():
            self.tmpdir.remove()

        resource = KQueueReactorTestFixture(self, deleteAction)
        storageService = StubStorageService(resource.reactor)
        delegate = DataStoreMonitor(resource.reactor, storageService)
        dcl = DirectoryChangeListener(resource.reactor, self.tmpdir.path, delegate)
        dcl.startListening()
        resource.runReactor()
        self.assertTrue(storageService.stopCalled)
        self.assertEquals(delegate.methodCalled, "deleted")


    def test_rename(self):
        """
        Verify directory renames can be monitored
        """

        self.tmpdir = FilePath(self.mktemp())
        self.tmpdir.makedirs()

        def renameAction():
            self.tmpdir.moveTo(FilePath(self.mktemp()))

        resource = KQueueReactorTestFixture(self, renameAction)
        storageService = StubStorageService(resource.reactor)
        delegate = DataStoreMonitor(resource.reactor, storageService)
        dcl = DirectoryChangeListener(resource.reactor, self.tmpdir.path, delegate)
        dcl.startListening()
        resource.runReactor()
        self.assertTrue(storageService.stopCalled)
        self.assertEquals(delegate.methodCalled, "renamed")
