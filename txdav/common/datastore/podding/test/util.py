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

from twisted.internet.defer import inlineCallbacks, returnValue

from txdav.caldav.datastore.scheduling.ischedule.localservers import (
    Server, ServersDB
)
from txdav.common.datastore.podding.conduit import PoddingConduit
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE
from txdav.common.datastore.test.util import (
    CommonCommonTests, SQLStoreBuilder, buildTestDirectory
)

import txweb2.dav.test.util

from twext.enterprise.ienterprise import AlreadyFinishedError

import json


class FakeConduitRequest(object):
    """
    A conduit request that sends messages internally rather than using HTTP
    """

    storeMap = {}

    @classmethod
    def addServerStore(cls, server, store):
        """
        Add a store mapped to a server. These mappings are used to "deliver" conduit
        requests to the appropriate store.

        @param uri: the server
        @type uri: L{Server}
        @param store: the store
        @type store: L{ICommonDataStore}
        """

        cls.storeMap[server.details()] = store


    def __init__(self, server, data, stream=None, stream_type=None):

        self.server = server
        self.data = json.dumps(data)
        self.stream = stream
        self.streamType = stream_type


    @inlineCallbacks
    def doRequest(self, txn):

        # Generate an HTTP client request
        try:
            response = (yield self._processRequest())
            response = json.loads(response)
        except Exception as e:
            raise ValueError("Failed cross-pod request: {}".format(e))

        returnValue(response)


    @inlineCallbacks
    def _processRequest(self):
        """
        Process the request by sending it to the relevant server.

        @return: the HTTP response.
        @rtype: L{Response}
        """

        store = self.storeMap[self.server.details()]
        j = json.loads(self.data)
        if self.stream is not None:
            j["stream"] = self.stream
            j["streamType"] = self.streamType
        result = yield store.conduit.processRequest(j)
        result = json.dumps(result)
        returnValue(result)



class MultiStoreConduitTest(CommonCommonTests, txweb2.dav.test.util.TestCase):

    theStoreBuilder2 = SQLStoreBuilder(secondary=True)
    otherTransaction = None

    @inlineCallbacks
    def setUp(self):
        yield super(MultiStoreConduitTest, self).setUp()

        # Store 1
        serversDB1 = ServersDB()
        server1a = Server("A", "http://127.0.0.1:8008", "A", True)
        serversDB1.addServer(server1a)
        server1b = Server("B", "http://127.0.0.1:8108", "B", False)
        serversDB1.addServer(server1b)
        yield self.buildStoreAndDirectory(serversDB=serversDB1)
        self.store.queryCacher = None     # Cannot use query caching
        self.store.conduit = self.makeConduit(self.store)

        # Store 2
        serversDB2 = ServersDB()
        server2a = Server("A", "http://127.0.0.1:8008", "A", False)
        serversDB2.addServer(server2a)
        server2b = Server("B", "http://127.0.0.1:8108", "B", True)
        serversDB2.addServer(server2b)

        self.store2 = yield self.buildStore(self.theStoreBuilder2)
        directory2 = buildTestDirectory(
            self.store2, self.mktemp(), serversDB=serversDB2
        )

        self.store2.setDirectoryService(directory2)
        self.store2.queryCacher = None     # Cannot use query caching
        self.store2.conduit = self.makeConduit(self.store2)

        FakeConduitRequest.addServerStore(server1a, self.store)
        FakeConduitRequest.addServerStore(server2b, self.store2)


    def configure(self):
        super(MultiStoreConduitTest, self).configure()
        self.config.Servers.Enabled = True


    def otherStoreUnderTest(self):
        """
        Return a store for testing.
        """
        return self.store2


    def newOtherTransaction(self):
        assert self.otherTransaction is None
        store2 = self.otherStoreUnderTest()
        txn = store2.newTransaction()

        @inlineCallbacks
        def maybeCommitThis():
            try:
                yield txn.commit()
            except AlreadyFinishedError:
                pass
        self.addCleanup(maybeCommitThis)
        self.otherTransaction = txn
        return self.otherTransaction


    def otherTransactionUnderTest(self):
        if self.otherTransaction is None:
            self.newOtherTransaction()
        return self.otherTransaction


    @inlineCallbacks
    def otherCommit(self):
        assert self.otherTransaction is not None
        yield self.otherTransaction.commit()
        self.otherTransaction = None


    @inlineCallbacks
    def otherAbort(self):
        assert self.otherTransaction is not None
        yield self.otherTransaction.abort()
        self.otherTransaction = None


    def makeConduit(self, store):
        conduit = PoddingConduit(store)
        conduit.conduitRequestClass = FakeConduitRequest
        return conduit


    @inlineCallbacks
    def createShare(self, ownerGUID="user01", shareeGUID="puser02", name="calendar"):

        home = yield self.homeUnderTest(name=ownerGUID, create=True)
        calendar = yield home.calendarWithName(name)
        yield calendar.inviteUIDToShare(shareeGUID, _BIND_MODE_WRITE, "shared", shareName="shared-calendar")
        yield self.commit()

        # ACK: home2 is None
        home2 = yield self.homeUnderTest(txn=self.newOtherTransaction(), name=shareeGUID)
        yield home2.acceptShare("shared-calendar")
        yield self.otherCommit()

        returnValue("shared-calendar")


    @inlineCallbacks
    def removeShare(self, ownerGUID="user01", shareeGUID="puser02", name="calendar"):

        home = yield self.homeUnderTest(name=ownerGUID)
        calendar = yield home.calendarWithName(name)
        yield calendar.uninviteUIDFromShare(shareeGUID)
        yield self.commit()
