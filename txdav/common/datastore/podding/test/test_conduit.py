##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twext.python.clsprop import classproperty
import twext.web2.dav.test.util
from twisted.internet.defer import inlineCallbacks, succeed
from txdav.caldav.datastore.scheduling.ischedule.localservers import Servers, Server
from txdav.caldav.datastore.test.util import buildCalendarStore, \
    TestCalendarStoreDirectoryRecord
from txdav.common.datastore.podding.resource import ConduitResource
from txdav.common.datastore.test.util import populateCalendarsFrom, CommonCommonTests
from txdav.common.datastore.podding.conduit import PoddingConduit, \
    InvalidCrossPodRequestError
from txdav.common.idirectoryservice import DirectoryRecordNotFoundError

class Conduit (CommonCommonTests, twext.web2.dav.test.util.TestCase):

    class FakeConduit(object):

        def recv_fake(self, j):
            return succeed({
                "result": "ok",
                "back2u": j["echo"],
                "more": "bits",
            })


    @inlineCallbacks
    def setUp(self):
        yield super(Conduit, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        self.directory = self._sqlCalendarStore.directoryService()

        for ctr in range(1, 100):
            self.directory.addRecord(TestCalendarStoreDirectoryRecord(
                "puser{:02d}".format(ctr),
                ("puser{:02d}".format(ctr),),
                "Puser {:02d}".format(ctr),
                frozenset((
                    "urn:uuid:puser{:02d}".format(ctr),
                    "mailto:puser{:02d}@example.com".format(ctr),
                )),
                thisServer=False,
            ))

        self.site.resource.putChild("conduit", ConduitResource(self.site.resource, self.storeUnderTest()))

        self.thisServer = Server("A", "http://127.0.0.1", "A", True)
        Servers.addServer(self.thisServer)

        yield self.populate()


    def storeUnderTest(self):
        """
        Return a store for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user02": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user03": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
    }


    def test_validRequst(self):
        """
        Cross-pod request fails when there is no shared secret header present.
        """

        conduit = PoddingConduit(self.storeUnderTest())
        r1, r2 = conduit.validRequst("user01", "puser02")
        self.assertTrue(r1 is not None)
        self.assertTrue(r2 is not None)

        self.assertRaises(DirectoryRecordNotFoundError, conduit.validRequst, "bogus01", "user02")
        self.assertRaises(DirectoryRecordNotFoundError, conduit.validRequst, "user01", "bogus02")
        self.assertRaises(InvalidCrossPodRequestError, conduit.validRequst, "user01", "user02")
