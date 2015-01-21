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
        try:
            result = yield store.conduit.processRequest(j)
        except Exception as e:
            # Send the exception over to the other side
            result = {
                "result": "exception",
                "class": ".".join((e.__class__.__module__, e.__class__.__name__,)),
                "request": str(e),
            }
        result = json.dumps(result)
        returnValue(result)



class MultiStoreConduitTest(CommonCommonTests, txweb2.dav.test.util.TestCase):

    numberOfStores = 2

    theStoreBuilders = []
    theStores = []
    activeTransactions = []

    def __init__(self, methodName='runTest'):
        txweb2.dav.test.util.TestCase.__init__(self, methodName)
        while len(self.theStoreBuilders) < self.numberOfStores:
            self.theStoreBuilders.append(SQLStoreBuilder(count=len(self.theStoreBuilders)))
        self.theStores = [None] * self.numberOfStores
        self.activeTransactions = [None] * self.numberOfStores


    @inlineCallbacks
    def setUp(self):
        yield super(MultiStoreConduitTest, self).setUp()

        # Stores
        for i in range(self.numberOfStores):
            serversDB = ServersDB()
            for j in range(self.numberOfStores):
                letter = chr(ord("A") + j)
                port = 8008 + 100 * j
                server = Server(letter, "http://127.0.0.1:{}".format(port), letter, j == i)
                serversDB.addServer(server)

            if i == 0:
                yield self.buildStoreAndDirectory(
                    serversDB=serversDB,
                    storeBuilder=self.theStoreBuilders[i]
                )
                self.theStores[i] = self.store
            else:
                self.theStores[i] = yield self.buildStore(self.theStoreBuilders[i])
                directory = buildTestDirectory(
                    self.theStores[i], self.mktemp(), serversDB=serversDB
                )
                self.theStores[i].setDirectoryService(directory)

            self.theStores[i].queryCacher = None     # Cannot use query caching
            self.theStores[i].conduit = self.makeConduit(self.theStores[i])

            FakeConduitRequest.addServerStore(serversDB.getServerById(chr(ord("A") + i)), self.theStores[i])


    def configure(self):
        super(MultiStoreConduitTest, self).configure()
        self.config.Servers.Enabled = True


    def theStoreUnderTest(self, count):
        """
        Return a store for testing.
        """
        return self.theStores[count]


    def makeNewTransaction(self, count):
        assert self.activeTransactions[count] is None
        store = self.theStoreUnderTest(count)
        txn = store.newTransaction()

        @inlineCallbacks
        def maybeCommitThis():
            try:
                yield txn.commit()
            except AlreadyFinishedError:
                pass
        self.addCleanup(maybeCommitThis)
        self.activeTransactions[count] = txn
        return self.activeTransactions[count]


    def theTransactionUnderTest(self, count):
        if self.activeTransactions[count] is None:
            self.makeNewTransaction(count)
        return self.activeTransactions[count]


    @inlineCallbacks
    def commitTransaction(self, count):
        assert self.activeTransactions[count] is not None
        yield self.activeTransactions[count].commit()
        self.activeTransactions[count] = None


    @inlineCallbacks
    def abortTransaction(self, count):
        assert self.activeTransactions[count] is not None
        yield self.activeTransactions[count].abort()
        self.activeTransactions[count] = None


    def makeConduit(self, store):
        conduit = PoddingConduit(store)
        conduit.conduitRequestClass = FakeConduitRequest
        return conduit


    @inlineCallbacks
    def createShare(self, ownerGUID="user01", shareeGUID="puser02", name="calendar"):

        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name=ownerGUID, create=True)
        calendar = yield home.calendarWithName(name)
        yield calendar.inviteUIDToShare(shareeGUID, _BIND_MODE_WRITE, "shared", shareName="shared-calendar")
        yield self.commitTransaction(0)

        # ACK: home2 is None
        home2 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name=shareeGUID)
        yield home2.acceptShare("shared-calendar")
        yield self.commitTransaction(1)

        returnValue("shared-calendar")


    @inlineCallbacks
    def removeShare(self, ownerGUID="user01", shareeGUID="puser02", name="calendar"):

        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name=ownerGUID)
        calendar = yield home.calendarWithName(name)
        yield calendar.uninviteUIDFromShare(shareeGUID)
        yield self.commitTransaction(0)
