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

"""
Mac OS X Server Service Access Control Lists
"""

__all__ = [
    "SudoSACLMixin",
]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twisted.web2.auth.wrapper import UnauthorizedResponse
from twisted.web2.http import HTTPError
from twisted.web2.dav import davxml
from twisted.web2.dav.auth import PrincipalCredentials
from twisted.web2.dav.idav import IDAVPrincipalResource

from twistedcaldav.log import Logger
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.directory import DirectoryService

log = Logger()

class SudoSACLMixin(object):
    """
    Mixin class to let DAVResource, and DAVFile subclasses below know
    about sudoer principals and how to find their AuthID
    """

    @inlineCallbacks
    def authenticate(self, request):
        # Bypass normal authentication if its already been done (by SACL check)
        if (hasattr(request, "authnUser") and
            hasattr(request, "authzUser") and
            request.authnUser is not None and
            request.authzUser is not None):
            returnValue((request.authnUser, request.authzUser))

        # Copy of SuperDAVResource.authenticate except we pass the creds on as well
        # as we will need to take different actions based on what the auth method was
        if not (
            hasattr(request, 'portal') and 
            hasattr(request, 'credentialFactories') and
            hasattr(request, 'loginInterfaces')
        ):
            request.authnUser = davxml.Principal(davxml.Unauthenticated())
            request.authzUser = davxml.Principal(davxml.Unauthenticated())
            returnValue((request.authnUser, request.authzUser,))

        authHeader = request.headers.getHeader('authorization')

        if authHeader is not None:
            if authHeader[0] not in request.credentialFactories:
                log.error("Client authentication scheme %s is not provided by server %s"
                               % (authHeader[0], request.credentialFactories.keys()))

                response = (yield UnauthorizedResponse.makeResponse(
                    request.credentialFactories,
                    request.remoteAddr
                ))
                raise HTTPError(response)
            else:
                factory = request.credentialFactories[authHeader[0]]

                creds = (yield factory.decode(authHeader[1], request))

                # Try to match principals in each principal collection on the resource
                authnPrincipal, authzPrincipal = (yield self.principalsForAuthID(request, creds))
                authnPrincipal = IDAVPrincipalResource(authnPrincipal)
                authzPrincipal = IDAVPrincipalResource(authzPrincipal)

                pcreds = PrincipalCredentials(authnPrincipal, authzPrincipal, creds)

                result = (yield request.portal.login(pcreds, None, *request.loginInterfaces))
                request.authnUser = result[1]
                request.authzUser = result[2]
                returnValue((request.authnUser, request.authzUser,))
        else:
            request.authnUser = davxml.Principal(davxml.Unauthenticated())
            request.authzUser = davxml.Principal(davxml.Unauthenticated())
            returnValue((request.authnUser, request.authzUser,))


    def principalsForAuthID(self, request, creds):
        """
        Return authentication and authorization prinicipal identifiers for the
        authentication identifer passed in. In this implementation authn and authz
        principals are the same.

        @param request: the L{IRequest} for the request in progress.
        @param creds: L{Credentials} or the principal to lookup.
        @return: a deferred tuple of two tuples. Each tuple is
            C{(principal, principalURI)} where: C{principal} is the L{Principal}
            that is found; {principalURI} is the C{str} URI of the principal.
            The first tuple corresponds to authentication identifiers,
            the second to authorization identifiers.
            It will errback with an HTTPError(responsecode.FORBIDDEN) if
            the principal isn't found.
        """
        authnPrincipal = self.findPrincipalForAuthID(creds)

        if authnPrincipal is None:
            log.info("Could not find the principal resource for user id: %s" % (creds.username,))
            raise HTTPError(responsecode.FORBIDDEN)

        d = self.authorizationPrincipal(request, creds.username, authnPrincipal)
        d.addCallback(lambda authzPrincipal: (authnPrincipal, authzPrincipal))
        return d

    def findPrincipalForAuthID(self, creds):
        """
        Return an authentication and authorization principal identifiers for 
        the authentication identifier passed in.  Check for sudo users before
        regular users.
        """
        
        if type(creds) is str:
            return super(SudoSACLMixin, self).findPrincipalForAuthID(creds)

        for collection in self.principalCollections():
            principal = collection.principalForShortName(
                SudoDirectoryService.recordType_sudoers, 
                creds.username)
            if principal is not None:
                return principal

        for collection in self.principalCollections():
            principal = collection.principalForAuthID(creds)
            if principal is not None:
                return principal
        return None

    @inlineCallbacks
    def authorizationPrincipal(self, request, authID, authnPrincipal):
        """
        Determine the authorization principal for the given request and authentication principal.
        This implementation looks for an X-Authorize-As header value to use as the authorization principal.
        
        @param request: the L{IRequest} for the request in progress.
        @param authID: a string containing the authentication/authorization identifier
            for the principal to lookup.
        @param authnPrincipal: the L{IDAVPrincipal} for the authenticated principal
        @return: a deferred result C{tuple} of (L{IDAVPrincipal}, C{str}) containing the authorization principal
            resource and URI respectively.
        """
        # FIXME: Unroll defgen

        # Look for X-Authorize-As Header
        authz = request.headers.getRawHeaders("x-authorize-as")

        if authz is not None and (len(authz) == 1):
            # Substitute the authz value for principal look up
            authz = authz[0]

        def getPrincipalForType(type, name):
            for collection in self.principalCollections():
                principal = collection.principalForShortName(type, name)
                if principal:
                    return principal

        def isSudoUser(authzID):
            if getPrincipalForType(SudoDirectoryService.recordType_sudoers, authzID):
                return True
            return False

        if hasattr(authnPrincipal, "record") and authnPrincipal.record.recordType == SudoDirectoryService.recordType_sudoers:
            if authz:
                if isSudoUser(authz):
                    log.info("Cannot proxy as another proxy: user '%s' as user '%s'" % (authID, authz))
                    raise HTTPError(responsecode.FORBIDDEN)
                else:
                    authzPrincipal = getPrincipalForType(
                        DirectoryService.recordType_users, authz)

                    if not authzPrincipal:
                        authzPrincipal = self.findPrincipalForAuthID(authz)

                    if authzPrincipal is not None:
                        log.info("Allow proxy: user '%s' as '%s'" % (authID, authz,))
                        returnValue(authzPrincipal)
                    else:
                        log.info("Could not find authorization user id: '%s'" % 
                                (authz,))
                        raise HTTPError(responsecode.FORBIDDEN)
            else:
                log.info("Cannot authenticate proxy user '%s' without X-Authorize-As header" % (authID, ))
                raise HTTPError(responsecode.BAD_REQUEST)
        elif authz:
            log.info("Cannot proxy: user '%s' as '%s'" % (authID, authz,))
            raise HTTPError(responsecode.FORBIDDEN)
        else:
            # No proxy - do default behavior
            result = (yield super(SudoSACLMixin, self).authorizationPrincipal(request, authID, authnPrincipal))
            returnValue(result)
