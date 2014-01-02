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

import txweb2.dav.test.util
from txweb2 import http_headers, responsecode
from txweb2.dav.util import allDataFromStream
from txweb2.test.test_server import SimpleRequest

from twisted.internet.defer import inlineCallbacks, succeed

from txdav.caldav.datastore.scheduling.ischedule.localservers import Servers, Server
from txdav.caldav.datastore.test.util import buildCalendarStore
from txdav.common.datastore.podding.resource import ConduitResource
from txdav.common.datastore.test.util import populateCalendarsFrom, CommonCommonTests
import json
from txdav.common.datastore.podding.conduit import PoddingConduit

class ConduitPOST (CommonCommonTests, txweb2.dav.test.util.TestCase):

    class FakeConduit(PoddingConduit):

        def recv_fake(self, txn, j):
            return succeed({
                "result": "ok",
                "back2u": j["echo"],
                "more": "bits",
            })


    @inlineCallbacks
    def setUp(self):
        yield super(ConduitPOST, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        self.directory = self._sqlCalendarStore.directoryService()

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


    @inlineCallbacks
    def test_receive_no_secret(self):
        """
        Cross-pod request fails when there is no shared secret header present.
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/conduit",
            headers=http_headers.Headers(rawHeaders={
                "Content-Type": ("text/plain",)
            }),
            content="""Hello, World!
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.FORBIDDEN)


    @inlineCallbacks
    def test_receive_wrong_mime(self):
        """
        Cross-pod request fails when Content-Type header is wrong.
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/conduit",
            headers=http_headers.Headers(rawHeaders={
                "Content-Type": ("text/plain",),
                self.thisServer.secretHeader()[0]: self.thisServer.secretHeader()[1],
            }),
            content="""Hello, World!
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.BAD_REQUEST)


    @inlineCallbacks
    def test_receive_invalid_json(self):
        """
        Cross-pod request fails when request data is not JSON.
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/conduit",
            headers=http_headers.Headers(rawHeaders={
                "Content-Type": ("application/json",),
                self.thisServer.secretHeader()[0]: self.thisServer.secretHeader()[1],
            }),
            content="""Hello, World!
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.BAD_REQUEST)


    @inlineCallbacks
    def test_receive_bad_json(self):
        """
        Cross-pod request fails when JSON data does not have an "action".
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/conduit",
            headers=http_headers.Headers(rawHeaders={
                "Content-Type": ("application/json",),
                self.thisServer.secretHeader()[0]: self.thisServer.secretHeader()[1],
            }),
            content="""
{
    "foo":"bar"
}
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.BAD_REQUEST)


    @inlineCallbacks
    def test_receive_ping(self):
        """
        Cross-pod request works with the "ping" action.
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/conduit",
            headers=http_headers.Headers(rawHeaders={
                "Content-Type": ("application/json",),
                self.thisServer.secretHeader()[0]: self.thisServer.secretHeader()[1],
            }),
            content="""
{
    "action":"ping"
}
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.OK)
        data = (yield allDataFromStream(response.stream))
        j = json.loads(data)
        self.assertTrue("result" in j)
        self.assertEqual(j["result"], "ok")


    @inlineCallbacks
    def test_receive_fake_conduit_no_action(self):
        """
        Cross-pod request fails when conduit does not support the action.
        """

        store = self.storeUnderTest()
        self.patch(store, "conduit", self.FakeConduit(store))

        request = SimpleRequest(
            self.site,
            "POST",
            "/conduit",
            headers=http_headers.Headers(rawHeaders={
                "Content-Type": ("application/json",),
                self.thisServer.secretHeader()[0]: self.thisServer.secretHeader()[1],
            }),
            content="""
{
    "action":"bogus",
    "echo":"bravo"
}
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.BAD_REQUEST)


    @inlineCallbacks
    def test_receive_fake_conduit(self):
        """
        Cross-pod request works when conduit does support the action.
        """

        store = self.storeUnderTest()
        self.patch(store, "conduit", self.FakeConduit(store))

        request = SimpleRequest(
            self.site,
            "POST",
            "/conduit",
            headers=http_headers.Headers(rawHeaders={
                "Content-Type": ("application/json",),
                self.thisServer.secretHeader()[0]: self.thisServer.secretHeader()[1],
            }),
            content="""
{
    "action":"fake",
    "echo":"bravo"
}
""".replace("\n", "\r\n")
        )

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.OK)
        data = (yield allDataFromStream(response.stream))
        j = json.loads(data)
        self.assertTrue("result" in j)
        self.assertEqual(j["result"], "ok")
        self.assertTrue("back2u" in j)
        self.assertEqual(j["back2u"], "bravo")
        self.assertTrue("more" in j)
        self.assertEqual(j["more"], "bits")
