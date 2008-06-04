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

import uuid
import time
import hashlib
import cPickle

from zope.interface import implements

from twisted.python.failure import Failure
from twisted.internet.defer import succeed, fail
from twisted.internet.protocol import ClientCreator

from twisted.web2.iweb import IResource
from twisted.web2.dav import davxml
from twisted.web2.dav.util import allDataFromStream
from twisted.web2.http import HTTPError, Response
from twisted.web2.stream import MemoryStream

from twisted.web2.dav.xattrprops import xattrPropertyStore

from twisted.internet.threads import deferToThread

from twistedcaldav.log import LoggingMixIn
from twistedcaldav.memcachepool import CachePoolUserMixIn
from twistedcaldav.config import config


class DisabledCacheNotifier(object):
    def __init__(self, *args, **kwargs):
        pass


    def changed(self):
        return succeed(None)



class DisabledCache(object):
    def getResponseForRequest(self, request):
        return None

    def cacheResponseForRequest(self, request, response):
        return response


class URINotFoundException(Exception):
    def __init__(self, uri):
        self.uri = uri


    def __repr__(self):
        return "%s: Could not find URI %r" % (
            self.__class__.__name__,
            self.uri)


class MemcacheChangeNotifier(LoggingMixIn, CachePoolUserMixIn):
    def __init__(self, resource, cachePool=None):
        self._resource = resource
        self._cachePool = cachePool


    def _newCacheToken(self):
        return str(uuid.uuid4())


    def changed(self):
        """
        Change the cache token for a resource

        return: A L{Deferred} that fires when the token has been changed.
        """
        self.log_debug("Changing Cache Token for %r" % (self._resource.url(),))
        return self.getCachePool().set(
            'cacheToken:%s' % (self._resource.url(),),
            self._newCacheToken())



class BaseResponseCache(LoggingMixIn):
    """
    A base class which provides some common operations
    """
    propertyStoreFactory = xattrPropertyStore

    def _principalURI(self, principal):
        return str(principal.children[0])


    def _canonicalizeURIForRequest(self, uri, request):
        def _uriNotFound(f):
            f.trap(AttributeError)
            return Failure(URINotFoundException(uri))

        try:
            return request.locateResource(uri).addCallback(
                lambda resrc: resrc.url()).addErrback(_uriNotFound)
        except AssertionError:
            return fail(Failure(URINotFoundException(uri)))


    def _getURIs(self, request):
        def _getSecondURI(rURI):
            return self._canonicalizeURIForRequest(
                self._principalURI(request.authnUser),
                request).addCallback(lambda pURI: (pURI, rURI))

        d = self._canonicalizeURIForRequest(request.uri, request)
        d.addCallback(_getSecondURI)

        return d


    def _requestKey(self, request):
        def _getBody(uris):
            return allDataFromStream(request.stream).addCallback(
                lambda body: (body, uris))

        def _getKey((requestBody, (pURI, rURI))):
            if requestBody is not None:
                request.stream = MemoryStream(requestBody)
                request.stream.doStartReading = None

            request.cacheKey = (request.method,
                                pURI,
                                rURI,
                                request.headers.getHeader('depth'),
                                hash(requestBody))

            return request.cacheKey

        d = self._getURIs(request)
        d.addCallback(_getBody)
        d.addCallback(_getKey)
        return d


    def _getResponseBody(self, key, response):
        d1 = allDataFromStream(response.stream)
        d1.addCallback(lambda responseBody: (key, responseBody))
        return d1



class MemcacheResponseCache(BaseResponseCache, CachePoolUserMixIn):
    def __init__(self, docroot, cachePool=None):
        self._docroot = docroot
        self._cachePool = cachePool


    def _tokenForURI(self, uri):
        """
        Get a property store for the given C{uri}.

        @param uri: The URI we'd like the token for.
        @return: A C{str} representing the token for the URI.
        """

        return self.getCachePool().get('cacheToken:%s' % (uri,))


    def _getTokens(self, request):
        def _tokensForURIs((pURI, rURI)):
            tokens = []
            d1 = self._tokenForURI(pURI)
            d1.addCallback(lambda pToken: tokens.append(pToken))
            d1.addCallback(lambda _ign: self._tokenForURI(rURI))
            d1.addCallback(lambda uToken: tokens.append(uToken))
            d1.addCallback(lambda _ign: tokens)
            return d1

        d = self._getURIs(request)
        d.addCallback(_tokensForURIs)
        return d


    def _hashedRequestKey(self, request):
        def _hashKey(key):
            oldkey = key
            request.cacheKey = key = hashlib.md5(
                ':'.join([str(t) for t in key])).hexdigest()
            self.log_debug("hashing key for get: %r to %r" % (oldkey, key))
            return request.cacheKey

        d = self._requestKey(request)
        d.addCallback(_hashKey)
        return d


    def getResponseForRequest(self, request):
        def _checkTokens(curTokens, expectedTokens, (code, headers, body)):
            if curTokens[0] != expectedTokens[0]:
                self.log_debug(
                    "Principal token doesn't match for %r: %r != %r" % (
                        request.cacheKey,
                        curTokens[0],
                        expectedTokens[0]))
                return None

            if curTokens[1] != expectedTokens[1]:
                self.log_debug(
                    "URI token doesn't match for %r: %r != %r" % (
                        request.cacheKey,
                        curTokens[1],
                        expectedTokens[1]))
                return None

            r = Response(code,
                         stream=MemoryStream(body))

            for key, value in headers.iteritems():
                r.headers.setRawHeaders(key, value)

            return r

        def _unpickleResponse((flags, value), key):
            if value is None:
                self.log_debug("Not in cache: %r" % (key,))
                return None

            self.log_debug("Found in cache: %r = %r" % (key, value))

            (principalToken, uriToken,
             resp) = cPickle.loads(value)
            d2 = self._getTokens(request)

            d2.addCallback(_checkTokens, (principalToken, uriToken), resp)

            return d2

        def _getCached(key):
            self.log_debug("Checking cache for: %r" % (key,))
            d1 = self.getCachePool().get(key)
            return d1.addCallback(_unpickleResponse, key)

        def _handleExceptions(f):
            f.trap(URINotFoundException)
            self.log_warn("Could not locate URI: %r" % f.value)
            return None

        d = self._hashedRequestKey(request)
        d.addCallback(_getCached)
        d.addErrback(_handleExceptions)
        return d


    def cacheResponseForRequest(self, request, response):
        def _makeCacheEntry((pToken, uToken), (key, responseBody)):
            cacheEntry = cPickle.dumps(
                (pToken,
                 uToken,
                 (response.code,
                  dict(list(response.headers.getAllRawHeaders())),
                  responseBody)))

            self.log_debug("Adding to cache: %r = %r" % (key, cacheEntry))
            return self.getCachePool().set(key, cacheEntry).addCallback(
                lambda _: response)

        def _cacheResponse((key, responseBody)):
            principalURI = self._principalURI(request.authnUser)

            response.headers.removeHeader('date')
            response.stream = MemoryStream(responseBody)

            d1 = self._getTokens(request)
            d1.addCallback(_makeCacheEntry, (key, responseBody))
            return d1

        if hasattr(request, 'cacheKey'):
            d = succeed(request.cacheKey)
        else:
            d = self._hashedRequestKey(request)

        d.addCallback(self._getResponseBody, response)
        d.addCallback(_cacheResponse)
        return d



class _CachedResponseResource(object):
    implements(IResource)

    def __init__(self, response):
        self._response = response

    def renderHTTP(self, request):
        return self._response

    def locateChild(self, request, segments):
        return self, []



class PropfindCacheMixin(object):
    def http_PROPFIND(self, request):
        def _cacheResponse(responseCache, response):
            return responseCache.cacheResponseForRequest(request, response)

        def _getResponseCache(response):
            d1 = request.locateResource("/")
            d1.addCallback(lambda resource: resource.responseCache)
            d1.addCallback(_cacheResponse, response)
            return d1

        d = super(PropfindCacheMixin, self).http_PROPFIND(request)
        d.addCallback(_getResponseCache)
        return d
