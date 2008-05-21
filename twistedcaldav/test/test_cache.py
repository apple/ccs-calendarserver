##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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

from new import instancemethod

from twisted.trial.unittest import TestCase

from twisted.python.filepath import FilePath

from twisted.web2.dav import davxml
from twisted.web2.dav.util import allDataFromStream
from twisted.web2.stream import MemoryStream
from twisted.web2.http_headers import Headers

from twistedcaldav.cache import CacheChangeNotifier
from twistedcaldav.cache import CacheTokensProperty
from twistedcaldav.cache import ResponseCache

from twistedcaldav.test.util import InMemoryPropertyStore


def _newCacheToken(self):
    called = getattr(self, '_called', 0)

    token = 'token%d' % (called,)
    setattr(self, '_called', called + 1)
    return token



class StubRequest(object):
    def __init__(self, method, uri, authnUser, depth=1, body=None):
        self.method = method
        self.uri = uri
        self.authnUser = davxml.Principal(davxml.HRef.fromString(authnUser))
        self.headers = Headers({'depth': depth})

        if body is None:
            body = "foobar"

        self.body = body
        self.stream = MemoryStream(body)



class StubResponse(object):
    def __init__(self, code, headers, body):
        self.code = code
        self.headers = Headers(headers)
        self.body = body
        self.stream = MemoryStream(body)



class CacheChangeNotifierTests(TestCase):
    def setUp(self):
        self.props = InMemoryPropertyStore()
        self.ccn = CacheChangeNotifier(self.props)
        self.ccn._newCacheToken = instancemethod(_newCacheToken,
                                                 self.ccn,
                                                 CacheChangeNotifier)


    def test_cacheTokenPropertyIsProvisioned(self):
        self.ccn.changed()
        token = self.props._properties[CacheTokensProperty.qname()
                                        ].children[0].data
        self.assertEquals(token, 'token0')


    def test_changedChangesToken(self):
        self.ccn.changed()
        self.ccn.changed()
        token = self.props._properties[CacheTokensProperty.qname()
                                        ].children[0].data
        self.assertEquals(token, 'token1')



class ResponseCacheTests(TestCase):
    def setUp(self):
        self.tokens = {
                '/calendars/users/cdaboo/': 'uriToken0',
                '/principals/users/cdaboo/': 'principalToken0',
                '/principals/users/dreid/': 'principalTokenX'}

        self.rc = ResponseCache(None)
        self.rc._tokenForURI = self.tokens.get

        self.rc._time = (lambda:0)

        self.expected_response = (200, Headers({}), "Foo")

        expected_key = (
                'PROPFIND',
                '/calendars/users/cdaboo/',
                '/principals/users/cdaboo/',
                1,
                hash('foobar'),
                )

        self.rc._responses[expected_key] = (
            'principalToken0', 'uriToken0', 0, self.expected_response)

        self.rc._accessList = [expected_key]


    def assertResponse(self, response, expected):
        self.assertEquals(response.code, expected[0])
        self.assertEquals(response.headers, expected[1])

        d = allDataFromStream(response.stream)
        d.addCallback(self.assertEquals, expected[2])
        return d


    def test_getResponseForRequestNotInCache(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/users/dreid/',
                '/principals/users/dreid/'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForRequestInCache(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/users/cdaboo/',
                '/principals/users/cdaboo/'))

        d.addCallback(self.assertResponse, self.expected_response)
        return d


    def test_getResponseForRequestPrincipalTokenChanged(self):
        self.tokens['/principals/users/cdaboo/'] = 'principalToken1'

        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/users/cdaboo/',
                '/principals/users/cdaboo/'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForRequestUriTokenChanged(self):
        self.tokens['/calendars/users/cdaboo/'] = 'uriToken1'

        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/users/cdaboo/',
                '/principals/users/cdaboo/'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForDepthZero(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/users/cdaboo/',
                '/principals/users/cdaboo/',
                depth=0))

        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForBody(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/users/cdaboo/',
                '/principals/users/cdaboo',
                body='bazbax'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_cacheResponseForRequest(self):
        expected_response = StubResponse(200, {}, "Foobar")

        def _assertResponse(ign):
            d1 = self.rc.getResponseForRequest(StubRequest(
                    'PROPFIND',
                    '/principals/users/dreid/',
                    '/principals/users/dreid/'))


            d1.addCallback(self.assertResponse,
                           (expected_response.code,
                            expected_response.headers,
                            expected_response.body))
            return d1

        d = self.rc.cacheResponseForRequest(
            StubRequest('PROPFIND',
                        '/principals/users/dreid/',
                        '/principals/users/dreid/'),
            expected_response)

        d.addCallback(_assertResponse)
        return d


    def test__tokenForURI(self):
        docroot = FilePath(self.mktemp())
        principal = docroot.child('principals'
                          ).child('users'
                          ).child('ws'
                          ).child('an'
                          ).child('wsanchez')

        expected_token = "wsanchezToken0"

        props = InMemoryPropertyStore()
        props._properties[CacheTokensProperty.qname()
                          ] = CacheTokensProperty.fromString(expected_token)

        stores = {principal.path: props}

        rc = ResponseCache(docroot)

        rc.propertyStoreFactory = (lambda rsrc: stores[rsrc.fp.path])

        token = rc._tokenForURI('/principals/users/wsanchez')
        self.assertEquals(token, expected_token)


    def test_cacheSizeExceeded(self):
        self.rc.CACHE_SIZE = 1
        def _assertResponse(ign):
            d1 = self.rc.getResponseForRequest(StubRequest(
                    'PROPFIND',
                    '/calendars/users/cdaboo/',
                    '/principals/users/cdaboo/'))

            d1.addCallback(self.assertEquals, None)
            return d1

        d = self.rc.cacheResponseForRequest(
            StubRequest('PROPFIND',
                        '/principals/users/dreid/',
                        '/principals/users/dreid/'),
            StubResponse(200, {}, "Foobar"))

        d.addCallback(_assertResponse)
        return d


    def test_cacheExpirationBenchmark(self):
        self.rc.CACHE_SIZE = 70000
        import time

        self.rc._responses = {}
        self.rc._accessList = []

        for x in xrange(0, self.rc.CACHE_SIZE):
            req = StubRequest('PROPFIND',
                              '/principals/users/user%d' % (x,),
                              '/principals/users/user%d' % (x,))
            self.rc._responses[req] = (
                'pTokenUser%d' % (x,), 'rTokenUser%d' % (x,), 0,
                (200, {}, 'foobar'))

            self.rc._accessList.append(req)

        def assertTime(result, startTime):
            duration = time.time() - startTime

            self.failUnless(
                duration < 0.01,
                "Took to long to add to the cache: %r" % (duration,))

        startTime = time.time()

        d = self.rc.cacheResponseForRequest(
            StubRequest('PROPFIND',
                        '/principals/users/dreid/',
                        '/principals/users/dreid/'),
            StubResponse(200, {}, 'Foobar'))

        d.addCallback(assertTime, startTime)
        return d
