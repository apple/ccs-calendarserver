##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

from twisted.internet import defer
from twisted.python.failure import Failure
from twisted.cred.error import LoginFailed, UnauthorizedLogin

from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.http import HTTPError
from twisted.web2.auth.wrapper import UnauthorizedResponse

from twistedcaldav.extensions import DAVFile, CachingXattrPropertyStore
from twistedcaldav.config import config
from twistedcaldav.cache import _CachedResponseResource
from twistedcaldav.cache import MemcacheResponseCache, MemcacheChangeNotifier
from twistedcaldav.cache import DisabledCache
from twistedcaldav.log import Logger
from twistedcaldav.static import CalendarHomeFile
from twistedcaldav.directory.principal import DirectoryPrincipalResource

log = Logger()

class RootResource(DAVFile):
    """
    A special root resource that contains support checking SACLs
    as well as adding responseFilters.
    """

    useSacls = False
    saclService = 'calendar'

    def __init__(self, path, *args, **kwargs):
        super(RootResource, self).__init__(path, *args, **kwargs)

        if config.EnableSACLs:
            if RootResource.CheckSACL:
                self.useSacls = True
            else:
                log.msg(("RootResource.CheckSACL is unset but "
                         "config.EnableSACLs is True, SACLs will not be "
                         "turned on."))

        self.contentFilters = []

        if config.Memcached['ClientEnabled']:
            self.responseCache = MemcacheResponseCache(
                self.fp,
                config.Memcached['BindAddress'],
                config.Memcached['Port'])

            CalendarHomeFile.cacheNotifierFactory = MemcacheChangeNotifier
            DirectoryPrincipalResource.cacheNotifierFactory = MemcacheChangeNotifier
        else:
            self.responseCache = DisabledCache()

        if config.ResponseCompression:
            from twisted.web2.filter import gzip
            self.contentFilters.append((gzip.gzipfilter, True))

    def deadProperties(self):
        if not hasattr(self, '_dead_properties'):
            self._dead_properties = CachingXattrPropertyStore(self)

        return self._dead_properties

    def checkSacl(self, request):
        """
        Check SACLs against the current request
        """

        def _authCb((authnUser, authzUser)):
            # Ensure that the user is not unauthenticated.
            # SACLs are authorization for the use of the service,
            # so unauthenticated access doesn't make any sense.
            if authzUser == davxml.Principal(davxml.Unauthenticated()):
                log.msg("Unauthenticated users not enabled with the '%s' SACL" % (self.saclService,))
                return Failure(HTTPError(UnauthorizedResponse(
                            request.credentialFactories,
                            request.remoteAddr)))

            return (authnUser, authzUser)

        def _authEb(failure):
            # Make sure we propogate UnauthorizedLogin errors.
            failure.trap(UnauthorizedLogin, LoginFailed)

            return Failure(HTTPError(UnauthorizedResponse(
                        request.credentialFactories,
                        request.remoteAddr)))

        def _checkSACLCb((authnUser, authzUser)):
            # Cache the authentication details
            request.authnUser = authnUser
            request.authzUser = authzUser

            # Figure out the "username" from the davxml.Principal object
            request.checkingSACL = True
            d = request.locateResource(authzUser.children[0].children[0].data)

            def _checkedSACLCb(principal):
                delattr(request, "checkingSACL")
                username = principal.record.shortName

                if RootResource.CheckSACL(username, self.saclService) != 0:
                    log.msg("User '%s' is not enabled with the '%s' SACL" % (username, self.saclService,))
                    return Failure(HTTPError(403))

                # Mark SACL's as having been checked so we can avoid doing it multiple times
                request.checkedSACL = True
                return True

            d.addCallback(_checkedSACLCb)
            return d

        d = defer.maybeDeferred(self.authenticate, request)
        d.addCallbacks(_authCb, _authEb)
        d.addCallback(_checkSACLCb)
        return d


    def locateChild(self, request, segments):
        def _authCb((authnUser, authzUser)):
            request.authnUser = authnUser
            request.authzUser = authzUser

        def _authEb(failure):
            # Make sure we propogate UnauthorizedLogin errors.
            failure.trap(UnauthorizedLogin, LoginFailed)

            return Failure(HTTPError(UnauthorizedResponse(
                        request.credentialFactories,
                        request.remoteAddr)))

        for filter in self.contentFilters:
            request.addResponseFilter(filter[0], atEnd=filter[1])

        if self.useSacls and not hasattr(request, "checkedSACL") and not hasattr(request, "checkingSACL"):
            d = self.checkSacl(request)
            d.addCallback(lambda _: super(RootResource, self
                                          ).locateChild(request, segments))

            return d

        def _getCachedResource(_ign, request):
            if not getattr(request, 'checkingCache', False):
                request.checkingCache = True
                d = self.responseCache.getResponseForRequest(request)
                d.addCallback(_serveResponse)
                return d

            return super(RootResource, self).locateChild(request, segments)

        def _serveResponse(response):
            if response is None:
                request.notInCache = True
                raise KeyError("Not found in cache.")

            return _CachedResponseResource(response), []

        def _resourceNotInCacheEb(failure):
            failure.trap(KeyError)
            return super(RootResource, self).locateChild(request,segments)

        if request.method == 'PROPFIND' and not getattr(
            request, 'notInCache', False):
            d = defer.maybeDeferred(self.authenticate, request)
            d.addCallbacks(_authCb, _authEb)
            d.addCallback(_getCachedResource, request)
            d.addErrback(_resourceNotInCacheEb)
            return d

        return super(RootResource, self).locateChild(request, segments)

    def http_COPY       (self, request): return responsecode.FORBIDDEN
    def http_MOVE       (self, request): return responsecode.FORBIDDEN
    def http_DELETE     (self, request): return responsecode.FORBIDDEN

# So CheckSACL will be parameterized
# We do this after RootResource is defined
try:
    from twistedcaldav._sacl import CheckSACL
    RootResource.CheckSACL = CheckSACL
except ImportError:
    RootResource.CheckSACL = None
