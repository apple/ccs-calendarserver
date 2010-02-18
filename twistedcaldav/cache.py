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

import cPickle
import hashlib
import uuid

from zope.interface import implements

from twisted.internet.defer import succeed, maybeDeferred
from twext.web2.dav.util import allDataFromStream
from twext.web2.http import Response
from twext.web2.iweb import IResource
from twext.web2.stream import MemoryStream

from twext.log import LoggingMixIn

from twistedcaldav.memcachepool import CachePoolUserMixIn, defaultCachePool
from twistedcaldav.config import config


class DisabledCacheNotifier(object):
    def __init__(self, *args, **kwargs):
        pass

    def changed(self):
        return succeed(None)


class DisabledCache(object):
    def getResponseForRequest(self, request):
        return succeed(None)

    def cacheResponseForRequest(self, request, response):
        return succeed(response)


class URINotFoundException(Exception):
    def __init__(self, uri):
        self.uri = uri


    def __repr__(self):
        return "%s: Could not find URI %r" % (
            self.__class__.__name__,
            self.uri)


class MemcacheChangeNotifier(LoggingMixIn, CachePoolUserMixIn):

    def __init__(self, resource, cachePool=None, cacheHandle="Default"):
        self._resource = resource
        self._cachePool = cachePool
        self._cachePoolHandle = cacheHandle

    def _newCacheToken(self):
        return str(uuid.uuid4())

    def changed(self):
        """
        Change the cache token for a resource

        return: A L{Deferred} that fires when the token has been changed.
        """
        url = self._resource.url()

        self.log_debug("Changing Cache Token for %r" % (url,))
        return self.getCachePool().set(
            'cacheToken:%s' % (url,),
            self._newCacheToken(), expireTime=config.ResponseCacheTimeout*60)


class BaseResponseCache(LoggingMixIn):
    """
    A base class which provides some common operations
    """
    def _principalURI(self, principal):
        return str(principal.children[0])


    def _uriNotFound(self, f, uri):
        f.trap(AttributeError)
        raise URINotFoundException(uri)


    def _getRecordForURI(self, uri, request):
        def _getRecord(resrc):
            if hasattr(resrc, 'record'):
                return resrc.record

        try:
            return request.locateResource(uri).addCallback(
                _getRecord).addErrback(self._uriNotFound, uri)
        except AssertionError:
            raise URINotFoundException(uri)


    def _canonicalizeURIForRequest(self, uri, request):
        try:
            return request.locateResource(uri).addCallback(
                lambda resrc: resrc.url()).addErrback(self._uriNotFound, uri)
        except AssertionError:
            raise URINotFoundException(uri)


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

        d = _getBody((self._principalURI(request.authnUser), request.uri))
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


    def _tokenForURI(self, uri, cachePoolHandle=None):
        """
        Get a property store for the given C{uri}.

        @param uri: The URI we'd like the token for.
        @return: A C{str} representing the token for the URI.
        """

        if cachePoolHandle:
            return defaultCachePool(cachePoolHandle).get('cacheToken:%s' % (uri,))
        else:
            return self.getCachePool().get('cacheToken:%s' % (uri,))


    def _getTokens(self, request):
        def _tokensForURIs((pURI, rURI)):
            tokens = []
            d1 = self._tokenForURI(pURI, "PrincipalToken")
            d1.addCallback(tokens.append)
            d1.addCallback(lambda _ign: self._getRecordForURI(pURI, request))
            d1.addCallback(lambda dToken: tokens.append(hash(dToken)))
            d1.addCallback(lambda _ign: self._tokenForURI(rURI))
            d1.addCallback(tokens.append)
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
                    "Directory Record Token doesn't match for %r: %r != %r" % (
                        request.cacheKey,
                        curTokens[1],
                        expectedTokens[1]))
                return None

            if curTokens[2] != expectedTokens[2]:
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

            (principalToken, directoryToken, uriToken,
             resp) = cPickle.loads(value)
            d2 = self._getTokens(request)

            d2.addCallback(_checkTokens,
                           (principalToken,
                            directoryToken,
                            uriToken),
                           resp)

            return d2

        def _getCached(key):
            self.log_debug("Checking cache for: %r" % (key,))
            d1 = self.getCachePool().get(key)
            return d1.addCallback(_unpickleResponse, key)

        def _handleExceptions(f):
            f.trap(URINotFoundException)
            self.log_debug("Could not locate URI: %r" % (f.value,))
            return None

        d = self._hashedRequestKey(request)
        d.addCallback(_getCached)
        d.addErrback(_handleExceptions)
        return d


    def cacheResponseForRequest(self, request, response):
        def _makeCacheEntry((pToken, dToken, uToken), (key, responseBody)):
            cacheEntry = cPickle.dumps(
                (pToken,
                 dToken,
                 uToken,
                 (response.code,
                  dict(list(response.headers.getAllRawHeaders())),
                  responseBody)))

            self.log_debug("Adding to cache: %r = %r" % (key, cacheEntry))
            return self.getCachePool().set(key, cacheEntry,
                expireTime=config.ResponseCacheTimeout*60).addCallback(
                lambda _: response)

        def _cacheResponse((key, responseBody)):

            response.headers.removeHeader('date')
            response.stream = MemoryStream(responseBody)

            d1 = self._getTokens(request)
            d1.addCallback(_makeCacheEntry, (key, responseBody))
            return d1

        def _handleExceptions(f):
            f.trap(URINotFoundException)
            self.log_debug("Could not locate URI: %r" % (f.value,))
            return response

        if hasattr(request, 'cacheKey'):
            d = succeed(request.cacheKey)
        else:
            d = self._hashedRequestKey(request)

        d.addCallback(self._getResponseBody, response)
        d.addCallback(_cacheResponse)
        d.addErrback(_handleExceptions)
        return d


class _CachedResponseResource(object):
    implements(IResource)

    def __init__(self, response):
        self._response = response

    def renderHTTP(self, request):
        if not hasattr(request, "extendedLogItems"):
            request.extendedLogItems = {}
        request.extendedLogItems["cached"] = "1"
        return self._response

    def locateChild(self, request, segments):
        return self, []


class PropfindCacheMixin(object):
    def renderHTTP(self, request):
        def _cacheResponse(responseCache, response):
            return responseCache.cacheResponseForRequest(request, response)

        def _getResponseCache(response):
            d1 = request.locateResource("/")
            d1.addCallback(lambda resource: resource.responseCache)
            d1.addCallback(_cacheResponse, response)
            return d1

        d = maybeDeferred(super(PropfindCacheMixin, self).renderHTTP, request)

        if request.method == 'PROPFIND':
            d.addCallback(_getResponseCache)
        return d
