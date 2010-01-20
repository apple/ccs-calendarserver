##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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

__all__ = [
    "RootResource",
]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.cred.error import LoginFailed, UnauthorizedLogin

from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.http import HTTPError, StatusResponse
from twisted.web2.auth.wrapper import UnauthorizedResponse
from twisted.web.xmlrpc import Proxy

from twistedcaldav.extensions import DAVFile, CachingPropertyStore
from twistedcaldav.extensions import DirectoryPrincipalPropertySearchMixIn
from twistedcaldav.extensions import ReadOnlyResourceMixIn
from twistedcaldav.config import config
from twistedcaldav.log import Logger
from twistedcaldav.cache import _CachedResponseResource
from twistedcaldav.cache import MemcacheResponseCache, MemcacheChangeNotifier
from twistedcaldav.cache import DisabledCache
from twistedcaldav.static import CalendarHomeFile
from twistedcaldav.directory.principal import DirectoryPrincipalResource

log = Logger()


class RootResource (ReadOnlyResourceMixIn, DirectoryPrincipalPropertySearchMixIn, DAVFile):
    """
    A special root resource that contains support checking SACLs
    as well as adding responseFilters.
    """

    useSacls = False
    saclService = "calendar"

    def __init__(self, path, *args, **kwargs):
        super(RootResource, self).__init__(path, *args, **kwargs)

        if config.EnableSACLs:
            if RootResource.CheckSACL:
                self.useSacls = True
            else:
                log.warn("SACLs are enabled, but SACLs are not supported.")

        self.contentFilters = []

        if config.Memcached["ClientEnabled"]:
            self.responseCache = MemcacheResponseCache(self.fp)

            CalendarHomeFile.cacheNotifierFactory = MemcacheChangeNotifier
            DirectoryPrincipalResource.cacheNotifierFactory = MemcacheChangeNotifier
        else:
            self.responseCache = DisabledCache()

        if config.ResponseCompression:
            from twisted.web2.filter import gzip
            self.contentFilters.append((gzip.gzipfilter, True))

        if not config.EnableKeepAlive:
            def addConnectionClose(request, response):
                response.headers.setHeader("connection", ("close",))
                request.chanRequest.channel.setReadPersistent(False)
                return response
            self.contentFilters.append((addConnectionClose, True))

    def deadProperties(self):
        # FIXME: Same as in static.py's CalDAVFile
        if not hasattr(self, "_dead_properties"):
            # Get the property store from super
            deadProperties = super(RootResource, self).deadProperties()

            # Wrap the property store in a memory store
            deadProperties = CachingPropertyStore(deadProperties)

            self._dead_properties = deadProperties

        return self._dead_properties

    def defaultAccessControlList(self):
        return config.RootResourceACL

    @inlineCallbacks
    def checkSacl(self, request):
        """
        Check SACLs against the current request
        """

        try:
            authnUser, authzUser = yield self.authenticate(request)
        except Exception:
            response = (yield UnauthorizedResponse.makeResponse(
                request.credentialFactories,
                request.remoteAddr
            ))
            raise HTTPError(response)

        # SACLs are enabled in the plist, but there may not actually
        # be a SACL group assigned to this service.  Let's see if
        # unauthenticated users are allowed by calling CheckSACL
        # with an empty string.
        if authzUser == davxml.Principal(davxml.Unauthenticated()):
            if RootResource.CheckSACL("", self.saclService) != 0:
                log.info("Unauthenticated users not enabled with the %r SACL" % (self.saclService,))
                response = (yield UnauthorizedResponse.makeResponse(
                    request.credentialFactories,
                    request.remoteAddr
                ))
                raise HTTPError(response)
            else:
                returnValue(True)

        # Cache the authentication details
        request.authnUser = authnUser
        request.authzUser = authzUser

        # Figure out the "username" from the davxml.Principal object
        request.checkingSACL = True

        for collection in self.principalCollections():
            principal = collection._principalForURI(authzUser.children[0].children[0].data)
            if principal is None:
                response = (yield UnauthorizedResponse.makeResponse(
                    request.credentialFactories,
                    request.remoteAddr
                ))
                raise HTTPError(response)

        delattr(request, "checkingSACL")
        username = principal.record.shortNames[0]

        if RootResource.CheckSACL(username, self.saclService) != 0:
            log.info("User %r is not enabled with the %r SACL" % (username, self.saclService,))
            raise HTTPError(responsecode.FORBIDDEN)

        # Mark SACLs as having been checked so we can avoid doing it multiple times
        request.checkedSACL = True


        returnValue(True)

    @inlineCallbacks
    def locateChild(self, request, segments):

        for filter in self.contentFilters:
            request.addResponseFilter(filter[0], atEnd=filter[1])

        # Examine cookies for wiki auth token; if there, ask the paired wiki
        # server for the corresponding record name.  If that maps to a
        # principal, assign that to authnuser.

        wikiConfig = config.Authentication.Wiki
        cookies = request.headers.getHeader("cookie")
        if wikiConfig["Enabled"] and cookies is not None:
            for cookie in cookies:
                if cookie.name == wikiConfig["Cookie"]:
                    token = cookie.value
                    break
            else:
                token = None

            if token is not None and token != "unauthenticated":
                log.debug("Wiki sessionID cookie value: %s" % (token,))
                proxy = Proxy(wikiConfig["URL"])
                try:
                    username = (yield proxy.callRemote(wikiConfig["UserMethod"], token))
                except Exception, e:
                    log.error("Failed to look up wiki token (%s)" % (e,))
                    username = None

                if username is not None:
                    log.debug("Wiki lookup returned user: %s" % (username,))
                    principal = None
                    directory = request.site.resource.getDirectory()
                    record = directory.recordWithShortName("users", username)
                    log.debug("Wiki user record for user %s : %s" % (username, record))
                    if record:
                        # Note: record will be None if it's a /Local/Default user
                        for collection in self.principalCollections():
                            principal = collection.principalForRecord(record)
                            if principal is not None:
                                break

                    if principal:
                        log.debug("Found wiki principal and setting authnuser and authzuser")
                        request.authzUser = request.authnUser = davxml.Principal(
                            davxml.HRef.fromString("/principals/__uids__/%s/" % (record.guid,))
                        )

        # We don't want the /inbox resource to pay attention to SACLs because
        # we just want it to use the hard-coded ACL for the imip reply user.
        # The /timezones resource is used by the wiki web calendar, so open
        # up that resource.
        if segments[0] in ("inbox", "timezones"):
            request.checkedSACL = True

        elif (len(segments) > 2 and (segments[1] == "wikis" or
            (segments[1] == "__uids__" and segments[2].startswith("wiki-")))):

            # This is a wiki-related resource. SACLs are not checked.
            request.checkedSACL = True

            # The authzuser value is set to that of the wiki principal.
            wikiName = None
            if segments[1] == "wikis":
                wikiName = segments[2]
            else:
                wikiName = segments[2][5:]
            if wikiName:
                request.authzUser = davxml.Principal(
                    davxml.HRef.fromString("/principals/wikis/%s/" % (wikiName,))
                )

        elif self.useSacls and not hasattr(request, "checkedSACL") and not hasattr(request, "checkingSACL"):
            yield self.checkSacl(request)

        if config.RejectClients:
            #
            # Filter out unsupported clients
            #
            agent = request.headers.getHeader("user-agent")
            if agent is not None:
                for reject in config.RejectClients:
                    if reject.search(agent) is not None:
                        log.info("Rejecting user-agent: %s" % (agent,))
                        raise HTTPError(StatusResponse(
                            responsecode.FORBIDDEN,
                            "Your client software (%s) is not allowed to access this service." % (agent,)
                        ))

        if request.method == "PROPFIND" and not getattr(request, "notInCache", False) and len(segments) > 1:
            try:
                authnUser, authzUser = (yield self.authenticate(request))
                request.authnUser = authnUser
                request.authzUser = authzUser
            except (UnauthorizedLogin, LoginFailed):
                response = (yield UnauthorizedResponse.makeResponse(
                    request.credentialFactories,
                    request.remoteAddr
                ))
                raise HTTPError(response)

            try:
                if not getattr(request, "checkingCache", False):
                    request.checkingCache = True
                    response = (yield self.responseCache.getResponseForRequest(request))
                    if response is None:
                        request.notInCache = True
                        raise KeyError("Not found in cache.")
        
                    returnValue((_CachedResponseResource(response), []))
            except KeyError:
                pass

        child = (yield super(RootResource, self).locateChild(request, segments))
        returnValue(child)

    def http_COPY       (self, request): return responsecode.FORBIDDEN
    def http_MOVE       (self, request): return responsecode.FORBIDDEN
    def http_DELETE     (self, request): return responsecode.FORBIDDEN

# So CheckSACL will be parameterized
# We do this after RootResource is defined
try:
    from calendarserver.platform.darwin._sacl import CheckSACL
    RootResource.CheckSACL = CheckSACL
except ImportError:
    RootResource.CheckSACL = None
