##
# Copyright (c) 2010-2017 Apple Inc. All rights reserved.
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

from txweb2.client.http import ClientRequest
from txweb2.http import HTTPError
from txweb2.test.test_server import SimpleRequest
from twistedcaldav.client.pool import _clientPools
from twistedcaldav.client.reverseproxy import ReverseProxyResource
from twistedcaldav.config import config
import twistedcaldav.test.util
from twisted.internet.defer import succeed, inlineCallbacks


class ReverseProxyNoLoop (twistedcaldav.test.util.TestCase):
    """
    Prevent loops in reverse proxy
    """

    def setUp(self):

        class DummyPool(object):

            def submitRequest(self, request):
                return succeed(request)

        _clientPools["pool"] = DummyPool()

        super(ReverseProxyNoLoop, self).setUp()

    @inlineCallbacks
    def test_No_Header(self):
        proxy = ReverseProxyResource("pool")
        request = SimpleRequest(proxy, "GET", "/")
        response = yield proxy.renderHTTP(request)
        self.assertIsInstance(response, ClientRequest)

    @inlineCallbacks
    def test_Header_Other_Server(self):
        proxy = ReverseProxyResource("pool")
        request = SimpleRequest(proxy, "GET", "/")
        request.headers.addRawHeader("x-forwarded-server", "foobar.example.com")
        response = yield proxy.renderHTTP(request)
        self.assertIsInstance(response, ClientRequest)

    @inlineCallbacks
    def test_Header_Other_Servers(self):
        proxy = ReverseProxyResource("pool")
        request = SimpleRequest(proxy, "GET", "/")
        request.headers.setHeader("x-forwarded-server", ("foobar.example.com", "bar.example.com",))
        response = yield proxy.renderHTTP(request)
        self.assertIsInstance(response, ClientRequest)

    @inlineCallbacks
    def test_Header_Our_Server(self):
        proxy = ReverseProxyResource("pool")
        request = SimpleRequest(proxy, "GET", "/")
        request.headers.addRawHeader("x-forwarded-server", config.ServerHostName)
        yield self.assertFailure(proxy.renderHTTP(request), HTTPError)

    @inlineCallbacks
    def test_Header_Our_Server_Moxied(self):
        proxy = ReverseProxyResource("pool")
        request = SimpleRequest(proxy, "GET", "/")
        request.headers.setHeader("x-forwarded-server", ("foobar.example.com", "bar.example.com", config.ServerHostName,))
        yield self.assertFailure(proxy.renderHTTP(request), HTTPError)

    @inlineCallbacks
    def test_Header_Our_Server_Allowed(self):
        proxy = ReverseProxyResource("pool")
        proxy.allowMultiHop = True
        request = SimpleRequest(proxy, "GET", "/")
        request.headers.addRawHeader("x-forwarded-server", config.ServerHostName)
        response = yield proxy.renderHTTP(request)
        self.assertIsInstance(response, ClientRequest)
