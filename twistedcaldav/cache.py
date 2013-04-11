##
# Copyright (c) 2008-2013 Apple Inc. All rights reserved.
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

from twisted.internet.defer import succeed, maybeDeferred, inlineCallbacks, \
    returnValue
from twext.web2.dav.util import allDataFromStream
from twext.web2.http import Response
from twext.web2.iweb import IResource
from twext.web2.stream import MemoryStream

from twext.python.log import LoggingMixIn

from twistedcaldav.memcachepool import CachePoolUserMixIn, defaultCachePool
from twistedcaldav.config import config

"""
The basic principals of the PROPFIND cache are this:

(1) In RootResource.locateChild we "intercept" request processing at a very early stage (before traversing the resource
hierarchy for the request URI). If the request is a PROPFIND we check to see whether a cache entry exists and if so immediately
return that. If no cache entry exists, normal PROPFIND processing occurs.

(2) The PropfindCacheMixin class is mixed into calendar/address book homes. That causes all valid PROPFIND responses to be
cached, and also provides a cache invalidation api to allow signaling of changes that need to invalidate the cache. The main
and child resources need to cause that api to be called when appropriate changes occur.

(3) The response cache entries consist of a key, derived from the request only, and a value. The value contains the set of tokens
in effect at the time the entry was cached, together with the response that was cached. The tokens are:

  - principalToken - a token for the authenticated user's principal
  - directoryToken - a hash of that principal's directory record
  - uriToken - a token for the request uri
  - childTokens - tokens for any child resources the request uri depends on (for depth:1)

  The current principalToken, uriToken and childTokens values are themselves stored in the cache using the key prefix 'cacheToken:'.
When the 'changeCache' api is called the cached value for the matching token is updated.

(4) When a request is being checked in the cache, the response cache entry key is first computed and any value extracted. The
tokens in the value are then checked against the current set of tokens in the cache. If there is any mismatch between tokens, the
cache entry is considered invalid and the cached response is not returned. If everything matches up, the cached response is returned
to the caller and ultimately sent directly back to the client.

(5) Because of shared calendars/address books that can affect the calendar/address book homes of several different users at once, we
need to keep track of the separate childTokens for each child resource. The tokens for shared resources are keyed of the sharer's uri,
so sharee's homes use that token. That way a single token for all shared instances is used and changed just once.

(6) Principals and directory records need to be included as tokens to take account of variations in access control based on who
is making the request (including proxy state changes etc).

"""

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

        # For shared resources we use the owner URL as the cache key
        if hasattr(self._resource, "owner_url"):
            url = self._resource.owner_url()
        else:
            url = self._resource.url()

        self.log_debug("Changing Cache Token for %r" % (url,))
        return self.getCachePool().set(
            'cacheToken:%s' % (url,),
            self._newCacheToken(), expireTime=config.ResponseCacheTimeout * 60)



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
        """
        Return the directory record for the specified principal uri.
        """
        def _getRecord(resrc):
            if hasattr(resrc, 'record'):
                return resrc.record

        try:
            return request.locateResource(uri).addCallback(
                _getRecord).addErrback(self._uriNotFound, uri)
        except AssertionError:
            raise URINotFoundException(uri)


    def _canonicalizeURIForRequest(self, uri, request):
        """
        Always use canonicalized forms of the URIs for caching (i.e. __uids__ paths).

        Do this without calling locateResource which may cause a query on the store.
        """

        uribits = uri.split("/")
        if len(uribits) > 1 and uribits[1] in ("principals", "calendars", "addressbooks"):
            if uribits[2] == "__uids__":
                return succeed(uri)
            else:
                recordType = uribits[2]
                recordName = uribits[3]
                directory = request.site.resource.getDirectory()
                record = directory.recordWithShortName(recordType, recordName)
                if record is not None:
                    uribits[2] = "__uids__"
                    uribits[3] = record.uid
                    return succeed("/".join(uribits))

        # Fall back to the locateResource approach
        try:
            return request.locateResource(uri).addCallback(
                lambda resrc: resrc.url()).addErrback(self._uriNotFound, uri)
        except AssertionError:
            raise URINotFoundException(uri)


    def _getURIs(self, request):
        """
        Get principal and resource URIs from the request.
        """
        def _getSecondURI(rURI):
            return self._canonicalizeURIForRequest(
                self._principalURI(request.authnUser),
                request).addCallback(lambda pURI: (pURI, rURI))

        d = self._canonicalizeURIForRequest(request.uri, request)
        d.addCallback(_getSecondURI)

        return d


    @inlineCallbacks
    def _requestKey(self, request):
        """
        Get a key for this request. This depends on the method, Depth: header, authn user principal,
        request uri and a hash of the request body (the body being normalized for property order).
        """
        requestBody = (yield allDataFromStream(request.stream))
        if requestBody is not None:
            # Give it back to the request so it can be read again
            request.stream = MemoryStream(requestBody)
            request.stream.doStartReading = None

            # Normalize the property order by doing a "dumb" sort on lines
            requestLines = requestBody.splitlines()
            requestLines.sort()
            requestBody = "\n".join(requestLines)

        request.cacheKey = (request.method,
                            self._principalURI(request.authnUser),
                            request.uri,
                            request.headers.getHeader('depth'),
                            hash(requestBody))

        returnValue(request.cacheKey)


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
        Get the current token for a particular URI.
        """

        if cachePoolHandle:
            return defaultCachePool(cachePoolHandle).get('cacheToken:%s' % (uri,))
        else:
            return self.getCachePool().get('cacheToken:%s' % (uri,))


    @inlineCallbacks
    def _tokenForRecord(self, uri, request):
        """
        Get the current token for a particular principal URI's directory record.
        """

        record = (yield self._getRecordForURI(uri, request))
        returnValue(record.cacheToken())


    @inlineCallbacks
    def _tokensForChildren(self, rURI, request):
        """
        Create a dict of child resource tokens for any "recorded" during this request in the childCacheURIs attribute.
        """

        if hasattr(request, "childCacheURIs"):
            tokens = dict([(uri, (yield self._tokenForURI(uri)),) for uri in request.childCacheURIs])
            returnValue(tokens)
        else:
            returnValue({})


    @inlineCallbacks
    def _getTokens(self, request):
        """
        Tokens are a principal token, directory record token, resource token and list
        of child resource tokens. A change to any one of those will cause cache invalidation.
        """
        tokens = []
        pURI, rURI = (yield self._getURIs(request))
        tokens.append((yield self._tokenForURI(pURI, "PrincipalToken")))
        tokens.append((yield self._tokenForRecord(pURI, request)))
        tokens.append((yield self._tokenForURI(rURI)))
        tokens.append((yield self._tokensForChildren(rURI, request)))
        returnValue(tokens)


    @inlineCallbacks
    def _hashedRequestKey(self, request):
        """
        Make a key for a response cache entry. This depends on various request parameters
        (see _requestKey for details).
        """
        oldkey = (yield self._requestKey(request))
        request.cacheKey = key = hashlib.md5(
            ':'.join([str(t) for t in oldkey])).hexdigest()
        self.log_debug("hashing key for get: %r to %r" % (oldkey, key))
        returnValue(request.cacheKey)


    @inlineCallbacks
    def getResponseForRequest(self, request):
        """
        Try to match a request and a response cache entry. We first get the request key and match that, then pull
        the cache entry and decompose it into tokens and response. We then compare the cached tokens with their current values.
        If all match, we can return the cached response data.
        """
        try:
            key = (yield self._hashedRequestKey(request))

            self.log_debug("Checking cache for: %r" % (key,))
            _ignore_flags, value = (yield self.getCachePool().get(key))

            if value is None:
                self.log_debug("Not in cache: %r" % (key,))
                returnValue(None)

            self.log_debug("Found in cache: %r = %r" % (key, value))

            (principalToken, directoryToken, uriToken, childTokens, (code, headers, body)) = cPickle.loads(value)
            currentTokens = (yield self._getTokens(request))

            if currentTokens[0] != principalToken:
                self.log_debug(
                    "Principal token doesn't match for %r: %r != %r" % (
                        request.cacheKey,
                        currentTokens[0],
                        principalToken))
                returnValue(None)

            if currentTokens[1] != directoryToken:
                self.log_debug(
                    "Directory Record Token doesn't match for %r: %r != %r" % (
                        request.cacheKey,
                        currentTokens[1],
                        directoryToken))
                returnValue(None)

            if currentTokens[2] != uriToken:
                self.log_debug(
                    "URI token doesn't match for %r: %r != %r" % (
                        request.cacheKey,
                        currentTokens[2],
                        uriToken))
                returnValue(None)

            for childuri, token in childTokens.items():
                currentToken = (yield self._tokenForURI(childuri))
                if currentToken != token:
                    self.log_debug(
                        "Child %s token doesn't match for %r: %r != %r" % (
                            childuri,
                            request.cacheKey,
                            currentToken,
                            token))
                    returnValue(None)

            r = Response(code,
                         stream=MemoryStream(body))

            for key, value in headers.iteritems():
                r.headers.setRawHeaders(key, value)

            returnValue(r)

        except URINotFoundException, e:
            self.log_debug("Could not locate URI: %r" % (e,))
            returnValue(None)


    @inlineCallbacks
    def cacheResponseForRequest(self, request, response):
        """
        Given a request and its response, make a response cache entry that encodes the response and various
        cache tokens. Later, when getResponseForRequest is called we retrieve this entry and compare the
        old cache tokens with the current ones. If any have changed the response cache entry is removed.
        """
        try:
            if hasattr(request, 'cacheKey'):
                key = request.cacheKey
            else:
                key = (yield self._hashedRequestKey(request))

            key, responseBody = (yield self._getResponseBody(key, response))

            response.headers.removeHeader('date')
            response.stream = MemoryStream(responseBody)
            pToken, dToken, uToken, cTokens = (yield self._getTokens(request))

            cacheEntry = cPickle.dumps((
                pToken,
                dToken,
                uToken,
                cTokens,
                (
                    response.code,
                    dict(list(response.headers.getAllRawHeaders())),
                    responseBody
                )
            ))
            self.log_debug("Adding to cache: %r = %r" % (key, cacheEntry))
            yield self.getCachePool().set(key, cacheEntry,
                expireTime=config.ResponseCacheTimeout * 60)

        except URINotFoundException, e:
            self.log_debug("Could not locate URI: %r" % (e,))

        returnValue(response)



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
    """
    A mixin that causes a resource's PROPFIND response to be cached. It also adds an api to change the
    resource's uriToken - this must be used whenever something changes to cause the cache to be invalidated.
    """
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


    def changeCache(self):
        if hasattr(self, 'cacheNotifier'):
            return self.cacheNotifier.changed()
        else:
            self.log_debug("%r does not have a cacheNotifier but was changed" % (self,))



class ResponseCacheMixin(object):
    """
    This is a mixin for a child resource that does not itself cache PROPFINDs, but needs to invalidate a parent
    resource's PROPFIND cache by virtue of a change to its own childToken.
    """

    def changeCache(self):
        if hasattr(self, 'cacheNotifier'):
            return self.cacheNotifier.changed()
        else:
            self.log_debug("%r does not have a cacheNotifier but was changed" % (self,))



class CacheStoreNotifier(object):

    def __init__(self, resource):
        self.resource = resource


    def notify(self, op="update"):
        self.resource.changeCache()


    def clone(self, label="default", id=None):
        return self


    def getID(self, label="default"):
        return None


    def nodeName(self, label="default"):
        return succeed(None)
