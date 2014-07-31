# -*- test-case-name: calendarserver.provision.test.test_root -*-
##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

try:
    from calendarserver.platform.darwin.sacl import checkSACL
except ImportError:
    # OS X Server SACLs not supported on this system, make SACL check a no-op
    checkSACL = lambda *ignored: True

from twext.python.log import Logger
from twisted.cred.error import LoginFailed, UnauthorizedLogin
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python.reflect import namedClass
from twisted.web.error import Error as WebError
from twistedcaldav.cache import DisabledCache
from twistedcaldav.cache import MemcacheResponseCache, MemcacheChangeNotifier
from twistedcaldav.cache import _CachedResponseResource
from twistedcaldav.config import config
from twistedcaldav.directory.principal import DirectoryPrincipalResource
from twistedcaldav.extensions import DAVFile, CachingPropertyStore
from twistedcaldav.extensions import DirectoryPrincipalPropertySearchMixIn
from twistedcaldav.extensions import ReadOnlyResourceMixIn
from twistedcaldav.resource import CalDAVComplianceMixIn
from txdav.who.wiki import DirectoryService as WikiDirectoryService
from txdav.who.wiki import uidForAuthToken
from txweb2 import responsecode
from txweb2.auth.wrapper import UnauthorizedResponse
from txweb2.dav.xattrprops import xattrPropertyStore
from txweb2.http import HTTPError, StatusResponse, RedirectResponse

log = Logger()


class RootResource(
    ReadOnlyResourceMixIn, DirectoryPrincipalPropertySearchMixIn,
    CalDAVComplianceMixIn, DAVFile
):
    """
    A special root resource that contains support checking SACLs
    as well as adding responseFilters.
    """

    useSacls = False

    # Mapping of top-level resource paths to SACLs.  If a request path
    # starts with any of these, then the list of SACLs are checked.  If the
    # request path does not start with any of these, then no SACLs are checked.
    saclMap = {
        "addressbooks": ("addressbook",),
        "calendars": ("calendar",),
        "directory": ("addressbook",),
        "principals": ("addressbook", "calendar"),
        "webcal": ("calendar",),
    }

    # If a top-level resource path starts with any of these, an unauthenticated
    # request is redirected to the auth url (config.WebCalendarAuthPath)
    authServiceMap = {
        "webcal": True,
    }

    def __init__(self, path, *args, **kwargs):
        super(RootResource, self).__init__(path, *args, **kwargs)

        if config.EnableSACLs:
            self.useSacls = True

        self.contentFilters = []

        if (
            config.EnableResponseCache and
            config.Memcached.Pools.Default.ClientEnabled
        ):
            self.responseCache = MemcacheResponseCache(self.fp)

            # These class attributes need to be setup with our memcache\
            # notifier
            DirectoryPrincipalResource.cacheNotifierFactory = (
                MemcacheChangeNotifier
            )
        else:
            self.responseCache = DisabledCache()

        if config.ResponseCompression:
            from txweb2.filter import gzip
            self.contentFilters.append((gzip.gzipfilter, True))


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            # Get the property store from super
            deadProperties = (
                namedClass(config.RootResourcePropStoreClass)(self)
            )

            # Wrap the property store in a memory store
            if isinstance(deadProperties, xattrPropertyStore):
                deadProperties = CachingPropertyStore(deadProperties)

            self._dead_properties = deadProperties

        return self._dead_properties


    def defaultAccessControlList(self):
        return succeed(config.RootResourceACL)


    @inlineCallbacks
    def checkSACL(self, request):
        """
        Check SACLs against the current request
        """

        topLevel = request.path.strip("/").split("/")[0]
        saclServices = self.saclMap.get(topLevel, None)
        if not saclServices:
            returnValue(True)

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
        if authzUser is None:
            for saclService in saclServices:
                if checkSACL("", saclService):
                    # No group actually exists for this SACL, so allow
                    # unauthenticated access
                    returnValue(True)
            # There is a SACL group for at least one of the SACLs, so no
            # unauthenticated access
            response = (yield UnauthorizedResponse.makeResponse(
                request.credentialFactories,
                request.remoteAddr
            ))
            log.info("Unauthenticated user denied by SACLs")
            raise HTTPError(response)

        # Cache the authentication details
        request.authnUser = authnUser
        request.authzUser = authzUser

        # Figure out the "username" from the davxml.Principal object
        username = authzUser.record.shortNames[0]

        access = False
        for saclService in saclServices:
            if checkSACL(username, saclService):
                # Access is allowed
                access = True
                break

        # Mark SACLs as having been checked so we can avoid doing it
        # multiple times
        request.checkedSACL = True

        if access:
            returnValue(True)

        log.warn(
            "User {user!r} is not enabled with the {sacl!r} SACL(s)",
            user=username, sacl=saclServices
        )
        raise HTTPError(responsecode.FORBIDDEN)


    @inlineCallbacks
    def locateChild(self, request, segments):

        for filter in self.contentFilters:
            request.addResponseFilter(filter[0], atEnd=filter[1])

        # Examine cookies for wiki auth token; if there, ask the paired wiki
        # server for the corresponding record name.  If that maps to a
        # principal, assign that to authnuser.

        # Also, certain non-browser clients send along the wiki auth token
        # sometimes, so we now also look for the presence of x-requested-with
        # header that the webclient sends.  However, in the case of a GET on
        # /webcal that header won't be sent so therefore we allow wiki auth
        # for any path in the authServiceMap even if that header is missing.
        allowWikiAuth = False
        topLevel = request.path.strip("/").split("/")[0]
        if self.authServiceMap.get(topLevel, False):
            allowWikiAuth = True

        if not hasattr(request, "checkedWiki"):
            # Only do this once per request
            request.checkedWiki = True

            wikiConfig = config.Authentication.Wiki
            cookies = request.headers.getHeader("cookie")
            requestedWith = request.headers.hasHeader("x-requested-with")
            if (
                wikiConfig["Enabled"] and
                (requestedWith or allowWikiAuth) and
                cookies is not None
            ):
                for cookie in cookies:
                    if cookie.name == wikiConfig["Cookie"]:
                        token = cookie.value
                        break
                else:
                    token = None

                if token is not None and token != "unauthenticated":
                    log.debug(
                        "Wiki sessionID cookie value: {token}", token=token
                    )

                    record = None
                    try:
                        uid = yield uidForAuthToken(token)
                        if uid == "unauthenticated":
                            uid = None

                    except WebError as w:
                        uid = None
                        # FORBIDDEN status means it's an unknown token
                        if int(w.status) == responsecode.NOT_FOUND:
                            log.debug(
                                "Unknown wiki token: {token}", token=token
                            )
                        else:
                            log.error(
                                "Failed to look up wiki token {token}: "
                                "{message}",
                                token=token, message=w.message
                            )

                    except Exception as e:
                        log.error(
                            "Failed to look up wiki token: {error}",
                            error=e
                        )
                        uid = None

                    if uid is not None:
                        log.debug(
                            "Wiki lookup returned uid: {uid}", uid=uid
                        )
                        principal = yield self.principalForUID(request, uid)

                        if principal:
                            log.debug(
                                "Wiki-authenticated principal {record.uid} "
                                "being assigned to authnUser and authzUser",
                                record=record
                            )
                            request.authzUser = request.authnUser = principal

        if not hasattr(request, "authzUser") and config.WebCalendarAuthPath:
            topLevel = request.path.strip("/").split("/")[0]
            if self.authServiceMap.get(topLevel, False):
                # We've not been authenticated and the auth service is enabled
                # for this resource, so redirect.

                # Use config.ServerHostName if no x-forwarded-host header,
                # otherwise use the final hostname in x-forwarded-host.
                host = request.headers.getRawHeaders(
                    "x-forwarded-host",
                    [config.ServerHostName]
                )[-1].split(",")[-1].strip()
                port = 443 if config.EnableSSL else 80
                scheme = "https" if config.EnableSSL else "http"

                response = RedirectResponse(
                    request.unparseURL(
                        host=host,
                        port=port,
                        scheme=scheme,
                        path=config.WebCalendarAuthPath,
                        querystring="redirect={}://{}{}".format(
                            scheme,
                            host,
                            request.path
                        )
                    ),
                    temporary=True
                )
                raise HTTPError(response)

        # We don't want the /inbox resource to pay attention to SACLs because
        # we just want it to use the hard-coded ACL for the imip reply user.
        # The /timezones resource is used by the wiki web calendar, so open
        # up that resource.
        if segments[0] in ("inbox", "timezones"):
            request.checkedSACL = True

        elif (
            (
                len(segments) > 2 and
                segments[0] in ("calendars", "principals") and
                (
                    segments[1] == "wikis" or
                    (
                        segments[1] == "__uids__" and
                        segments[2].startswith(WikiDirectoryService.uidPrefix)
                    )
                )
            )
        ):
            # This is a wiki-related calendar resource. SACLs are not checked.
            request.checkedSACL = True

            # The authzuser value is set to that of the wiki principal if
            # not already set.
            if not hasattr(request, "authzUser") and segments[2]:
                wikiUid = None
                if segments[1] == "wikis":
                    wikiUid = "{}{}".format(WikiDirectoryService.uidPrefix, segments[2])
                else:
                    wikiUid = segments[2]
                if wikiUid:
                    log.debug(
                        "Wiki principal {name} being assigned to authzUser",
                        name=wikiUid
                    )
                    request.authzUser = yield self.principalForUID(request, wikiUid)

        elif (
            self.useSacls and
            not hasattr(request, "checkedSACL")
        ):
            yield self.checkSACL(request)

        if config.RejectClients:
            #
            # Filter out unsupported clients
            #
            agent = request.headers.getHeader("user-agent")
            if agent is not None:
                for reject in config.RejectClients:
                    if reject.search(agent) is not None:
                        log.info("Rejecting user-agent: {agent}", agent=agent)
                        raise HTTPError(StatusResponse(
                            responsecode.FORBIDDEN,
                            "Your client software ({}) is not allowed to "
                            "access this service."
                            .format(agent)
                        ))

        if not hasattr(request, "authnUser"):
            try:
                authnUser, authzUser = yield self.authenticate(request)
                request.authnUser = authnUser
                request.authzUser = authzUser
            except (UnauthorizedLogin, LoginFailed):
                response = yield UnauthorizedResponse.makeResponse(
                    request.credentialFactories,
                    request.remoteAddr
                )
                raise HTTPError(response)

        if (
            config.EnableResponseCache and
            request.method == "PROPFIND" and
            not getattr(request, "notInCache", False) and
            len(segments) > 1
        ):

            try:
                if not getattr(request, "checkingCache", False):
                    request.checkingCache = True
                    response = yield self.responseCache.getResponseForRequest(
                        request
                    )
                    if response is None:
                        request.notInCache = True
                        raise KeyError("Not found in cache.")

                    returnValue((_CachedResponseResource(response), []))
            except KeyError:
                pass

        child = yield super(RootResource, self).locateChild(
            request, segments
        )
        returnValue(child)


    @inlineCallbacks
    def principalForUID(self, request, uid):
        principal = None
        directory = request.site.resource.getDirectory()
        record = yield directory.recordWithUID(uid)
        if record is not None:
            username = record.shortNames[0]
            log.debug(
                "Wiki user record for user {user}: {record}",
                user=username, record=record
            )
            for collection in self.principalCollections():
                principal = yield collection.principalForRecord(record)
                if principal is not None:
                    break

        returnValue(principal)


    def http_COPY(self, request):
        return responsecode.FORBIDDEN


    def http_MOVE(self, request):
        return responsecode.FORBIDDEN


    def http_DELETE(self, request):
        return responsecode.FORBIDDEN
