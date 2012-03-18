##
# Copyright (c) 2008-2010 Apple Inc. All rights reserved.
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

from twisted.internet.defer import succeed, maybeDeferred

from txdav.xml import element as davxml
from twext.web2.dav.util import allDataFromStream
from twext.web2.stream import MemoryStream
from twext.web2.http_headers import Headers

from twistedcaldav.cache import MemcacheResponseCache
from twistedcaldav.cache import MemcacheChangeNotifier
from twistedcaldav.cache import PropfindCacheMixin

from twistedcaldav.test.util import InMemoryMemcacheProtocol
from twistedcaldav.test.util import TestCase


def _newCacheToken(self):
    called = getattr(self, '_called', 0)

    token = 'token%d' % (called,)
    setattr(self, '_called', called + 1)
    return token

class StubDirectoryRecord(object):
    
    def __init__(self, uid):
        self.uid = uid

class StubDirectory(object):
    
    def recordWithShortName(self, recordType, recordName):
        return StubDirectoryRecord(recordName)

class StubSiteResource(object):

    def __init__(self):
        self.directory = StubDirectory()
    
    def getDirectory(self):
        return self.directory

class StubSite(object):
    
    def __init__(self):
        self.resource = StubSiteResource()

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
        
        self.site = StubSite()


    def locateResource(self, uri):
        assert uri[0] == '/', "URI path didn't begin with '/': %s" % (uri,)
        return succeed(self.resources.get(uri))



class StubResponse(object):
    def __init__(self, code, headers, body):
        self.code = code
        self.headers = Headers(headers)
        self.body = body
        self.stream = MemoryStream(body)



class StubURLResource(object):
    def __init__(self, url, record=None):
        self._url = url

        if record is not None:
            self.record = record

    def url(self):
        return self._url



class MemCacheChangeNotifierTests(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.memcache = InMemoryMemcacheProtocol()
        self.ccn = MemcacheChangeNotifier(
            StubURLResource(':memory:'),
            cachePool=self.memcache)

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
        for call in self.memcache._timeouts.itervalues():
            call.cancel()
        MemcacheChangeNotifier._memcacheProtocol = None



class BaseCacheTestMixin(object):
    def setUp(self):
        StubRequest.resources = {
            '/calendars/__uids__/cdaboo/': StubURLResource(
                '/calendars/__uids__/cdaboo/'),
            '/calendars/users/cdaboo/': StubURLResource(
                '/calendars/__uids__/cdaboo/'),
            '/principals/__uids__/cdaboo/': StubURLResource(
                '/principals/__uids__/cdaboo/', record='directoryToken0'),
            '/calendars/__uids__/dreid/': StubURLResource(
                '/calendars/__uids__/dreid/'),
            '/principals/__uids__/dreid/': StubURLResource(
                '/principals/__uids__/dreid/', record='directoryToken0')}


    def tearDown(self):
        StubRequest.resources = {}


    def assertResponse(self, response, expected):
        self.assertNotEquals(response, None, "Got None instead of a response.")
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

        d = self.rc.getResponseForRequest(request)

        d.addCallback(self.assertEquals, None)
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

        d = self.rc.getResponseForRequest(request)

        d.addCallback(self.assertEquals, None)
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


    def test_getResponseForRequestChildTokenChanged(self):
        self.tokens['/calendars/__uids__/cdaboo/calendars/'] = 'childToken1'

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


    def test_getResponseForUnauthenticatedRequest(self):
        d = self.rc.getResponseForRequest(StubRequest(
                'PROPFIND',
                '/calendars/__uids__/cdaboo/',
                '{DAV:}unauthenticated',
                body='bazbax'))

        d.addCallback(self.assertEquals, None)
        return d


    def test_cacheUnauthenticatedResponse(self):
        expected_response = StubResponse(401, {}, "foobar")

        d = self.rc.cacheResponseForRequest(
            StubRequest('PROPFIND',
                        '/calendars/__uids__/cdaboo/',
                        '{DAV:}unauthenticated'),
            expected_response)

        d.addCallback(self.assertResponse,
                      (expected_response.code,
                       expected_response.headers,
                       expected_response.body))

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


        d = self.rc.cacheResponseForRequest(
            StubRequest('PROPFIND',
                        '/principals/__uids__/dreid/',
                        '/principals/__uids__/dreid/'),
            expected_response)

        d.addCallback(_assertResponse)
        return d


    def test_recordHashChangeInvalidatesCache(self):
        StubRequest.resources[
            '/principals/__uids__/cdaboo/'].record = 'directoryToken1'

        d = self.rc.getResponseForRequest(
            StubRequest(
                'PROPFIND',
                '/calendars/__uids__/cdaboo/',
                '/principals/__uids__/cdaboo/'))

        d.addCallback(self.assertEquals, None)
        return d



class MemcacheResponseCacheTests(BaseCacheTestMixin, TestCase):
    def setUp(self):
        super(MemcacheResponseCacheTests, self).setUp()

        memcacheStub = InMemoryMemcacheProtocol()
        self.rc = MemcacheResponseCache(None, cachePool=memcacheStub)
        self.rc.logger.setLevel('debug')
        self.tokens = {}

        self.tokens['/calendars/__uids__/cdaboo/'] = 'uriToken0'
        self.tokens['/calendars/__uids__/cdaboo/calendars/'] = 'childToken0'
        self.tokens['/principals/__uids__/cdaboo/'] = 'principalToken0'
        self.tokens['/principals/__uids__/dreid/'] = 'principalTokenX'

        def _getToken(uri, cachePoolHandle=None):
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
            hash('directoryToken0'),
            'uriToken0',
            {'/calendars/__uids__/cdaboo/calendars/':'childToken0'},
            (self.expected_response[0],
             dict(list(self.expected_response[1].getAllRawHeaders())),
             self.expected_response[2]))))

        self.memcacheStub = memcacheStub

    def tearDown(self):
        for call in self.memcacheStub._timeouts.itervalues():
            call.cancel()

    def test_givenURIsForKeys(self):
        expected_response = (200, Headers({}), "Foobarbaz")

        _key = (
                'PROPFIND',
                '/principals/__uids__/cdaboo/',
                '/calendars/users/cdaboo/',
                '1',
                hash('foobar'),
                )

        expected_key = hashlib.md5(':'.join([str(t) for t in _key])).hexdigest()

        self.memcacheStub._cache[expected_key] = (
            0, #flags
            cPickle.dumps((
                    'principalToken0',
                    hash('directoryToken0'),
                    'uriToken0',
                    {'/calendars/__uids__/cdaboo/calendars/':'childToken0'},
                    (expected_response[0],
                     dict(list(expected_response[1].getAllRawHeaders())),
                     expected_response[2]))))

        d = self.rc.getResponseForRequest(
            StubRequest('PROPFIND',
                        '/calendars/users/cdaboo/',
                        '/principals/__uids__/cdaboo/'))

        d.addCallback(self.assertResponse, expected_response)
        return d



class StubResponseCacheResource(object):
    def __init__(self):
        self.cache = {}
        self.responseCache = self


    def getResponseForRequest(self, request):
        if request in self.cache:
            return self.cache[request]


    def cacheResponseForRequest(self, request, response):
        self.cache[request] = response
        return response



class TestRenderMixin(object):
    davHeaders = ('foo',)

    def renderHTTP(self, request):
        self.response.headers.setHeader('dav', self.davHeaders)

        return self.response



class TestCachingResource(PropfindCacheMixin, TestRenderMixin):
    def __init__(self, response):
        self.response = response



class PropfindCacheMixinTests(TestCase):
    """
    Test the PropfindCacheMixin
    """
    def setUp(self):
        TestCase.setUp(self)
        self.resource = TestCachingResource(StubResponse(200, {}, "foobar"))
        self.responseCache = StubResponseCacheResource()

    def test_DAVHeaderCached(self):
        """
        Test that the DAV header set in renderHTTP is cached.
        """
        def _checkCache(response):
            self.assertEquals(response.headers.getHeader('dav'),
                              ('foo',))
            self.assertEquals(
                self.responseCache.cache[request].headers.getHeader('dav'),
                ('foo',))

        request = StubRequest('PROPFIND', '/', '/')
        request.resources['/'] = self.responseCache

        d = maybeDeferred(self.resource.renderHTTP, request)
        d.addCallback(_checkCache)

        return d


    def test_onlyCachePropfind(self):
        """
        Test that we only cache the result of a propfind request.
        """
        def _checkCache(response):
            self.assertEquals(self.responseCache.getResponseForRequest(request),
                              None)

        request = StubRequest('GET', '/', '/')
        request.resources['/'] = self.responseCache

        d = maybeDeferred(self.resource.renderHTTP, request)
        d.addCallback(_checkCache)

        return d
