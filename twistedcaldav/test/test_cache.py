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
import hashlib
import cPickle

from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed, fail
from twisted.python.failure import Failure

from twisted.python.filepath import FilePath

from twisted.web2.dav import davxml
from twisted.web2.dav.util import allDataFromStream
from twisted.web2.stream import MemoryStream
from twisted.web2.http_headers import Headers

from twistedcaldav.cache import MemcacheResponseCache
from twistedcaldav.cache import MemcacheChangeNotifier

from twistedcaldav.test.util import InMemoryPropertyStore


def _newCacheToken(self):
    called = getattr(self, '_called', 0)

    token = 'token%d' % (called,)
    setattr(self, '_called', called + 1)
    return token



class StubRequest(object):
    resources = {}

    def __init__(self, method, uri, authnUser, depth='1', body=None):
        self.method = method
        self.uri = uri
        self.authnUser = davxml.Principal(davxml.HRef.fromString(authnUser))
        self.headers = Headers({'depth': depth})

        if body is None:
            body = "foobar"

        self.body = body
        self.stream = MemoryStream(body)


    def locateResource(self, uri):
        return succeed(self.resources.get(uri))



class StubResponse(object):
    def __init__(self, code, headers, body):
        self.code = code
        self.headers = Headers(headers)
        self.body = body
        self.stream = MemoryStream(body)



class InMemoryMemcacheProtocol(object):
    def __init__(self):
        self._cache = {}


    def get(self, key):
        if key not in self._cache:
            return succeed((0, None))

        return succeed(self._cache[key])


    def set(self, key, value, flags=0, expireTime=0):
        try:
            self._cache[key] = (flags, value)
            return succeed(True)

        except Exception, err:
            return fail(Failure())



class StubURLResource(object):
    def __init__(self, url):
        self._url = url


    def url(self):
        return self._url



class MemCacheChangeNotifierTests(TestCase):
    def setUp(self):
        self.memcache = InMemoryMemcacheProtocol()
        self.ccn = MemcacheChangeNotifier(InMemoryPropertyStore())
        MemcacheChangeNotifier._memcacheProtocol = self.memcache
        self.ccn._newCacheToken = instancemethod(_newCacheToken,
                                                 self.ccn,
                                                 MemcacheChangeNotifier)


    def assertToken(self, expectedToken):
        token = self.memcache._cache['cacheToken::memory:'][1]
        self.assertEquals(token, expectedToken)


    def test_cacheTokenPropertyIsProvisioned(self):
        d = self.ccn.changed()
        d.addCallback(lambda _: self.assertToken('token0'))
        return d


    def test_changedChangesToken(self):
        d = self.ccn.changed()
        d.addCallback(lambda _: self.ccn.changed())
        d.addCallback(lambda _: self.assertToken('token1'))
        return d


    def tearDown(self):
        MemcacheChangeNotifier._memcacheProtocol = None



class BaseCacheTestMixin(object):
    def setUp(self):
        StubRequest.resources = {
            '/calendars/__uids__/cdaboo/': StubURLResource(
                '/calendars/__uids__/cdaboo/'),
            '/principals/__uids__/cdaboo/': StubURLResource(
                '/principals/__uids__/cdaboo/'),
            '/calendars/__uids__/dreid/': StubURLResource(
                '/calendars/__uids__/dreid/'),
            '/principals/__uids__/dreid/': StubURLResource(
                '/principals/__uids__/dreid/')}


    def tearDown(self):
        StubRequest.resources = {}


    def assertResponse(self, response, expected):
        self.assertEquals(response.code, expected[0])
        self.assertEquals(set(response.headers.getAllRawHeaders()),
                          set(expected[1].getAllRawHeaders()))

        d = allDataFromStream(response.stream)
        d.addCallback(self.assertEquals, expected[2])
        return d


    def test_getResponseForRequestMultiHomedRequestURI(self):
        request = StubRequest(
            'PROPFIND',
            '/calendars/users/cdaboo/',
            '/principals/__uids__/cdaboo/')

        request.resources['/calendars/users/cdaboo/'] = StubURLResource(
            '/calendars/__uids__/cdaboo/')

        d = self.rc.getResponseForRequest(request)

        d.addCallback(self.assertResponse, self.expected_response)
        return d


    def test_getResponseForRequestURINotFound(self):
        request = StubRequest(
            'PROPFIND',
            '/calendars/__uids__/wsanchez/',
            '/calendars/__uids__/dreid/')

        d = self.rc.getResponseForRequest(request)
        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForRequestMultiHomedPrincipalURI(self):
        request = StubRequest(
            'PROPFIND',
            '/calendars/__uids__/cdaboo/',
            '/principals/users/cdaboo/')

        request.resources['/principals/users/cdaboo/'] = StubURLResource(
            '/principals/__uids__/cdaboo/')

        d = self.rc.getResponseForRequest(request)

        d.addCallback(self.assertResponse, self.expected_response)
        return d


    def test_getResponseForRequestNotInCache(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/__uids__/dreid/',
                '/principals/__uids__/dreid/'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForRequestInCache(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/__uids__/cdaboo/',
                '/principals/__uids__/cdaboo/'))

        d.addCallback(self.assertResponse, self.expected_response)
        return d


    def test_getResponseForRequestPrincipalTokenChanged(self):
        self.tokens['/principals/__uids__/cdaboo/'] = 'principalToken1'

        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/__uids__/cdaboo/',
                '/principals/__uids__/cdaboo/'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForRequestUriTokenChanged(self):
        self.tokens['/calendars/__uids__/cdaboo/'] = 'uriToken1'

        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/__uids__/cdaboo/',
                '/principals/__uids__/cdaboo/'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForDepthZero(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/__uids__/cdaboo/',
                '/principals/__uids__/cdaboo/',
                depth='0'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_getResponseForBody(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/__uids__/cdaboo/',
                '/principals/__uids__/cdaboo/',
                body='bazbax'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_cacheResponseForRequest(self):
        expected_response = StubResponse(200, {}, "Foobar")

        def _assertResponse(ign):
            d1 = self.rc.getResponseForRequest(StubRequest(
                    'PROPFIND',
                    '/principals/__uids__/dreid/',
                    '/principals/__uids__/dreid/'))


            d1.addCallback(self.assertResponse,
                           (expected_response.code,
                            expected_response.headers,
                            expected_response.body))
            return d1


        StubRequest.resources[
            '/principals/__uids__/dreid/'] = StubURLResource(
            '/principals/__uids__/dreid/')

        d = self.rc.cacheResponseForRequest(
            StubRequest('PROPFIND',
                        '/principals/__uids__/dreid/',
                        '/principals/__uids__/dreid/'),
            expected_response)

        d.addCallback(_assertResponse)
        return d



class MemcacheResponseCacheTests(BaseCacheTestMixin, TestCase):
    def setUp(self):
        super(MemcacheResponseCacheTests, self).setUp()

        memcacheStub = InMemoryMemcacheProtocol()
        self.rc = MemcacheResponseCache(None, None, None, None)
        self.rc.logger.setLevel('debug')
        self.tokens = {}

        self.tokens['/calendars/__uids__/cdaboo/'] = 'uriToken0'
        self.tokens['/principals/__uids__/cdaboo/'] = 'principalToken0'
        self.tokens['/principals/__uids__/dreid/'] = 'principalTokenX'

        def _getToken(uri):
            return succeed(self.tokens.get(uri))

        self.rc._tokenForURI = _getToken

        self.expected_response = (200, Headers({}), "Foo")

        expected_key = hashlib.md5(':'.join([str(t) for t in (
                'PROPFIND',
                '/principals/__uids__/cdaboo/',
                '/calendars/__uids__/cdaboo/',
                '1',
                hash('foobar'),
                )])).hexdigest()

        memcacheStub._cache[expected_key] = (
            0, #flags
            cPickle.dumps((
            'principalToken0',
            'uriToken0',
            (self.expected_response[0],
             dict(list(self.expected_response[1].getAllRawHeaders())),
             self.expected_response[2]))))

        self.rc._memcacheProtocol = memcacheStub


