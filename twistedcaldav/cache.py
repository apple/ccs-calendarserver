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

from twisted.internet.defer import succeed
from twisted.internet.protocol import ClientCreator

from twisted.web2.iweb import IResource
from twisted.web2.dav import davxml
from twisted.web2.dav.util import allDataFromStream
from twisted.web2.http import HTTPError, Response
from twisted.web2.stream import MemoryStream

from twisted.web2.dav.xattrprops import xattrPropertyStore

from twisted.internet.threads import deferToThread

from twistedcaldav.log import LoggingMixIn
from twistedcaldav.memcache import MemCacheProtocol
from twistedcaldav.config import config

class CacheTokensProperty(davxml.WebDAVTextElement):
    namespace = davxml.twisted_private_namespace
    name = "cacheTokens"



class XattrCacheChangeNotifier(LoggingMixIn):
    def __init__(self, propertyStore):
        self._propertyStore = propertyStore
        self._token = None


    def _newCacheToken(self):
        return str(uuid.uuid4())


    def changed(self):
        """
        Change the cache token for a resource.

        return: A L{Deferred} that fires when the token has been changed.
        """
        self.log_debug("Changing Cache Token for %r" % (
                self._propertyStore.resource.fp))
        property = CacheTokensProperty.fromString(self._newCacheToken())
        self._propertyStore.set(property)
        return succeed(True)



class MemcacheChangeNotifier(LoggingMixIn):
    _memcacheProtocol = None

    def __init__(self, propertyStore):
        self._path = propertyStore.resource.fp.path
        self._host = config.Memcached['BindAddress']
        self._port = config.Memcached['Port']

        from twisted.internet import reactor
        self._reactor = reactor


    def _newCacheToken(self):
        return str(uuid.uuid4())


    def _getMemcacheProtocol(self):
        if MemcacheChangeNotifier._memcacheProtocol is not None:
            return succeed(self._memcacheProtocol)

        d = ClientCreator(self._reactor, MemCacheProtocol).connectTCP(
            self._host,
            self._port)

        def _cacheProtocol(proto):
            MemcacheChangeNotifier._memcacheProtocol = proto
            return proto

        return d.addCallback(_cacheProtocol)


    def changed(self):
        """
        Change the cache token for a resource

        return: A L{Deferred} that fires when the token has been changed.
        """
        def _updateCacheToken(proto):
            return proto.set('cacheToken:%s' % (self._path,),
                             self._newCacheToken())

        self.log_debug("Changing Cache Token for %r" % (self._path,))
        d = self._getMemcacheProtocol()
        d.addCallback(_updateCacheToken)
        return d



class BaseResponseCache(LoggingMixIn):
    """
    A base class which provides some common operations
    """
    propertyStoreFactory = xattrPropertyStore

    def _principalURI(self, principal):
        return str(principal.children[0])


    def _requestKey(self, request):
        def _getKey(requestBody):
            if requestBody is not None:
                request.stream = MemoryStream(requestBody)
                request.stream.doStartReading = None

            request.cacheKey = (request.method,
                                self._principalURI(request.authnUser),
                                request.uri,
                                request.headers.getHeader('depth'),
                                hash(requestBody))

            return request.cacheKey

        d = allDataFromStream(request.stream)
        d.addCallback(_getKey)
        return d


    def _getTokensInThread(self, principalURI, requestURI):
        def _getTokens():
            pToken = self._tokenForURI(principalURI)
            uToken = self._tokenForURI(requestURI)

            return (pToken, uToken)

        return deferToThread(_getTokens)


    def _tokenForURI(self, uri):
        """
        Get a property store for the given C{uri}.

        @param uri: The URI we'd like the token for.
        @return: A C{str} representing the token for the URI.
        """

        class __FauxStaticResource(object):
            def __init__(self, fp):
                self.fp = fp


        fp = self._docroot
        segments = uri.split('/')
        for childPath in segments[:3]:
            fp = fp.child(childPath)

        fp = fp.child(segments[3][:2]
                      ).child(segments[3][2:4]
                              ).child(segments[3])

        props = self.propertyStoreFactory(__FauxStaticResource(fp))

        try:
            tokenElement = props.get(CacheTokensProperty.qname())
            return tokenElement.children[0].data

        except HTTPError, err:
            pass


    def _getResponseBody(self, key, response):
        d1 = allDataFromStream(response.stream)
        d1.addCallback(lambda responseBody: (key, responseBody))
        return d1



class ResponseCache(BaseResponseCache):
    """
    An object that caches responses to given requests.

    @ivar CACHE_TIMEOUT: The number of seconds that a cache entry is valid,
        (default 3600 seconds or 1 hour).

    @ivar _docroot: An L{FilePath} that points to the document root.
    @ivar _responses: A C{dict} with (request-method, request-uri,
         principal-uri) keys and (principal-token, uri-token, cache-time,
         response) values.
    """

    CACHE_SIZE = 1000

    def __init__(self, docroot, cacheSize=None):
        self._docroot = docroot
        self._responses = {}

        if cacheSize is not None:
            self.CACHE_SIZE = cacheSize


    def _time(self):
        """
        Return the current time in seconds since the epoch
        """
        return time.time()


    def getResponseForRequest(self, request):
        """
        Retrieve a cached response to the given C{request} otherwise return
        C{None}

        @param request: An L{IRequest} provider that will be used to locate
            a cached L{IResponse}.

        @return: An L{IResponse} or C{None} if the response has not been cached.
        """
        principalURI = self._principalURI(request.authnUser)

        def _checkTokens((newPrincipalToken, newURIToken), key):
            (principalToken,
             uriToken,
             accessTime,
             response) = self._responses[key]

            if newPrincipalToken != principalToken:
                self.log_debug("Principal token changed on %r from %r to %r" % (
                        key,
                        principalToken,
                        newPrincipalToken
                        ))
                return None

            elif newURIToken != uriToken:
                self.log_debug("URI token changed on %r from %r to %r" % (
                        key,
                        uriToken,
                        newURIToken
                        ))
                return None

            response[1].removeHeader('date')

            responseObj = Response(response[0],
                                   headers=response[1],
                                   stream=MemoryStream(response[2]))

            self._responses[key] = (principalToken,
                                    uriToken,
                                    self._time(),
                                    response)

            self.log_debug("Found in cache: %r = %r" % (key,
                                                        responseObj))

            return responseObj


        def _checkKeyInCache(key):
            self.log_debug("Checking cache for: %r" % (key,))

            if key not in self._responses:
                self.log_debug("Not in cache: %r" % (key,))
                return None

            d1 = self._getTokensInThread(principalURI, request.uri)
            d1.addCallback(_checkTokens, key)

            return d1

        d = self._requestKey(request)
        d.addCallback(_checkKeyInCache)
        return d


    def cacheResponseForRequest(self, request, response):
        """
        Cache the given C{response} for the given C{request}.

        @param request: An L{IRequest} provider that will be keyed to the
            given C{response}.

        @param response: An L{IResponse} provider that will be returned on
            subsequent checks for the given L{IRequest}

        @return: A deferred that fires when the response has been added
            to the cache.
        """
        def _cacheResponse((key, responseBody)):
            principalURI = self._principalURI(request.authnUser)

            self.log_debug("Adding to cache: %r = %r" % (key,
                                                         response))

            if len(self._responses) >= self.CACHE_SIZE:
                leastRecentlyUsedTime = None
                leastRecentlyUsedKey = None

                for cacheKey, cacheEntry in self._responses.iteritems():
                    if leastRecentlyUsedTime is None:
                        leastRecentlyUsedTime = cacheEntry[2]
                        leastRecentlyUsedKey = cacheKey
                        continue

                    if leastRecentlyUsedTime < cacheEntry[2]:
                        leastRecentlyUsedTime = cacheEntry[2]
                        leastRecentlyUsedKey = cacheKey

                self.log_warn("Expiring from cache: %r" % (
                        leastRecentlyUsedKey,))

                del self._responses[leastRecentlyUsedKey]


            self._responses[key] = (self._tokenForURI(principalURI),
                                    self._tokenForURI(request.uri),
                                    self._time(),
                                    (response.code,
                                     response.headers,
                                     responseBody))

            self.log_debug("Cache Stats: # keys = %r" % (len(self._responses),))

            response.stream = MemoryStream(responseBody)
            return response

        if hasattr(request, 'cacheKey'):
            request.cacheKey
            d = succeed(request.cacheKey)
        else:
            d = self._requestKey(request)

        d.addCallback(self._getResponseBody, response)
        d.addCallback(_cacheResponse)
        return d



class MemcacheResponseCache(BaseResponseCache):
    def __init__(self, docroot, host, port, reactor=None):
        self._docroot = docroot
        self._host = host
        self._port = port
        if reactor is None:
            from twisted.internet import reactor

        self._reactor = reactor

        self._memcacheProtocol = None


    def _tokenForURI(self, uri):
        """
        Get a property store for the given C{uri}.

        @param uri: The URI we'd like the token for.
        @return: A C{str} representing the token for the URI.
        """

        class __FauxStaticResource(object):
            def __init__(self, fp):
                self.fp = fp


        fp = self._docroot
        for childPath in uri.split('/')[:4]:
            fp = fp.child(childPath)

        return self._getMemcacheProtocol().addCallback(
            lambda p: p.get('cacheToken:%s' % (fp.path,)))


    def _getTokens(self, principalURI, requestURI):
        def _getSecondToken(pToken):
            d1 = self._tokenForURI(requestURI)
            d1.addCallback(lambda uToken: (pToken, uToken))
            return d1

        d = self._tokenForURI(principalURI)
        d.addCallback(_getSecondToken)
        return d


    def _getMemcacheProtocol(self):
        if self._memcacheProtocol is not None:
            return succeed(self._memcacheProtocol)

        d = ClientCreator(self._reactor, MemCacheProtocol).connectTCP(
            self._host,
            self._port)

        def _cacheProtocol(proto):
            self._memcacheProtocol = proto
            return proto

        return d.addCallback(_cacheProtocol)


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

            d2 = self._getTokens(self._principalURI(request.authnUser),
                                         request.uri)

            d2.addCallback(_checkTokens, (principalToken, uriToken), resp)

            return d2

        def _getCache(proto, key):
            self.log_debug("Checking cache for: %r" % (key,))
            d1 = proto.get(key)
            return d1.addCallback(_unpickleResponse, key)

        def _getProtocol(key):
            return self._getMemcacheProtocol().addCallback(_getCache, key)

        d = self._hashedRequestKey(request)
        d.addCallback(_getProtocol)
        return d


    def cacheResponseForRequest(self, request, response):
        def _setCacheEntry(proto, key, cacheEntry):
            self.log_debug("Adding to cache: %r = %r" % (key, cacheEntry))
            return proto.set(key, cacheEntry).addCallback(
                lambda _: response)

        def _makeCacheEntry((pToken, uToken), (key, responseBody)):
            cacheEntry = cPickle.dumps(
                (pToken,
                 uToken,
                 (response.code,
                  dict(list(response.headers.getAllRawHeaders())),
                  responseBody)))

            d2 = self._getMemcacheProtocol()
            d2.addCallback(_setCacheEntry, key, cacheEntry)
            return d2

        def _cacheResponse((key, responseBody)):
            principalURI = self._principalURI(request.authnUser)

            response.headers.removeHeader('date')
            response.stream = MemoryStream(responseBody)

            d1 = self._getTokens(principalURI, request.uri)
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
