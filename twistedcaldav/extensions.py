# -*- test-case-name: twistedcaldav.test.test_extensions -*-
##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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
Extensions to web2.dav
"""

__all__ = [
    "SudoSACLMixin",
    "DAVResource",
    "DAVPrincipalResource",
    "DAVFile",
    "ReadOnlyWritePropertiesResourceMixIn",
    "ReadOnlyResourceMixIn",
    "CachingPropertyStore",
]

import cPickle as pickle
import urllib
import cgi
import time

from twisted.internet.defer import succeed, DeferredList, inlineCallbacks, returnValue
from twisted.internet.defer import maybeDeferred
from twisted.cred.error import LoginFailed, UnauthorizedLogin
from twext.web2 import responsecode
from twext.web2.auth.wrapper import UnauthorizedResponse
from twext.web2.http import HTTPError, Response, RedirectResponse
from twext.web2.http import StatusResponse
from twext.web2.http_headers import MimeType
from twext.web2.stream import FileStream
from twext.web2.static import MetaDataMixin
from twext.web2.dav import davxml
from twext.web2.dav.auth import PrincipalCredentials
from twext.web2.dav.davxml import dav_namespace
from twext.web2.dav.http import MultiStatusResponse
from twext.web2.dav.idav import IDAVPrincipalResource
from twext.web2.dav.static import DAVFile as SuperDAVFile
from twext.web2.dav.resource import DAVResource as SuperDAVResource
from twext.web2.dav.resource import DAVPrincipalResource as SuperDAVPrincipalResource
from twext.web2.dav.util import joinURL
from twext.web2.dav.method import prop_common
from twext.web2.dav.method.report import max_number_of_matches

from twext.python.log import Logger, LoggingMixIn

from twistedcaldav import customxml
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.util import submodule, Alternator, printTracebacks
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.method.report import http_REPORT

log = Logger()

#
# Alter logger for some twisted stuff
#
import twext
for m in (
    "web2.dav.fileop",
    "web2.dav.element.base",
    "web2.dav.fileop",
    "web2.dav.http",
    "web2.dav.method.acl",
    "web2.dav.method.copymove",
    "web2.dav.method.delete",
    "web2.dav.method.mkcol",
    "web2.dav.method.prop_common",
    "web2.dav.method.propfind",
    "web2.dav.method.proppatch",
    "web2.dav.method.put",
    "web2.dav.method.put_common",
    "web2.dav.method.report",
    "web2.dav.method.report_acl_principal_prop_set",
    "web2.dav.method.report_expand",
    "web2.dav.method.report_principal_match",
    "web2.dav.method.report_principal_property_search",
    "web2.dav.method.report_principal_search_property_set",
    "web2.dav.resource",
    "web2.dav.static",
    "web2.dav.util",
    "web2.dav.xattrprops",
):
    submodule(twext, m).log = Logger("twext." + m)
del m

class SudoSACLMixin (object):
    """
    Mixin class to let DAVResource, and DAVFile subclasses know about
    sudoer principals and how to find their AuthID.
    """

    @inlineCallbacks
    def authenticate(self, request):
        # Bypass normal authentication if its already been done (by SACL check)
        if (
            hasattr(request, "authnUser") and
            hasattr(request, "authzUser") and
            request.authnUser is not None and
            request.authzUser is not None
        ):
            returnValue((request.authnUser, request.authzUser))

        # Copy of SuperDAVResource.authenticate except we pass the
        # creds on as well as we will need to take different actions
        # based on what the auth method was
        if not (
            hasattr(request, "portal") and 
            hasattr(request, "credentialFactories") and
            hasattr(request, "loginInterfaces")
        ):
            request.authnUser = davxml.Principal(davxml.Unauthenticated())
            request.authzUser = davxml.Principal(davxml.Unauthenticated())
            returnValue((request.authnUser, request.authzUser,))

        authHeader = request.headers.getHeader("authorization")

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

                try:
                    creds = (yield factory.decode(authHeader[1], request))
                except (UnauthorizedLogin, LoginFailed,):
                    raise HTTPError((yield UnauthorizedResponse.makeResponse(
                                request.credentialFactories, request.remoteAddr)))

                # Try to match principals in each principal collection on the resource
                authnPrincipal, authzPrincipal = (yield self.principalsForAuthID(request, creds))
                authnPrincipal = IDAVPrincipalResource(authnPrincipal)
                authzPrincipal = IDAVPrincipalResource(authzPrincipal)

                pcreds = PrincipalCredentials(authnPrincipal, authzPrincipal, creds)

                try:
                    result = (yield request.portal.login(pcreds, None, *request.loginInterfaces))
                except UnauthorizedLogin:
                    raise HTTPError((yield UnauthorizedResponse.makeResponse(
                                request.credentialFactories, request.remoteAddr)))
                request.authnUser = result[1]
                request.authzUser = result[2]
                returnValue((request.authnUser, request.authzUser,))
        else:
            request.authnUser = davxml.Principal(davxml.Unauthenticated())
            request.authzUser = davxml.Principal(davxml.Unauthenticated())
            returnValue((request.authnUser, request.authzUser,))

    def principalsForAuthID(self, request, creds):
        """
        Return authentication and authorization prinicipal identifiers
        for the authentication identifer passed in. In this
        implementation authn and authz principals are the same.

        @param request: the L{IRequest} for the request in progress.
        @param creds: L{Credentials} or the principal to lookup.
        @return: a deferred tuple of two tuples. Each tuple is
            C{(principal, principalURI)} where: C{principal} is the
            L{Principal} that is found; {principalURI} is the C{str}
            URI of the principal.  The first tuple corresponds to
            authentication identifiers, the second to authorization
            identifiers.  It will errback with an
            HTTPError(responsecode.FORBIDDEN) if the principal isn't
            found.
        """
        authnPrincipal = self.findPrincipalForAuthID(creds)

        if authnPrincipal is None:
            log.info("Could not find the principal resource for user id: %s"
                     % (creds.username,))
            raise HTTPError(responsecode.FORBIDDEN)

        d = self.authorizationPrincipal(request, creds.username, authnPrincipal)
        d.addCallback(lambda authzPrincipal: (authnPrincipal, authzPrincipal))
        return d

    def findPrincipalForAuthID(self, creds):
        """
        Return an authentication and authorization principal
        identifiers for the authentication identifier passed in.
        Check for sudo users before regular users.
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
        Determine the authorization principal for the given request
        and authentication principal.  This implementation looks for
        an X-Authorize-As header value to use as the authorization
        principal.
        
        @param request: the L{IRequest} for the request in progress.
        @param authID: a string containing the
            authentication/authorization identifier for the principal
            to lookup.
        @param authnPrincipal: the L{IDAVPrincipal} for the
            authenticated principal
        @return: a deferred result C{tuple} of (L{IDAVPrincipal},
            C{str}) containing the authorization principal resource
            and URI respectively.
        """
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

        if (
            hasattr(authnPrincipal, "record") and
            authnPrincipal.record.recordType == SudoDirectoryService.recordType_sudoers
        ):
            if authz:
                if isSudoUser(authz):
                    log.info("Cannot proxy as another proxy: user %r as user %r"
                             % (authID, authz))
                    raise HTTPError(responsecode.FORBIDDEN)
                else:
                    authzPrincipal = getPrincipalForType(DirectoryService.recordType_users, authz)

                    if not authzPrincipal:
                        authzPrincipal = self.findPrincipalForAuthID(authz)

                    if authzPrincipal is not None:
                        log.info("Allow proxy: user %r as %r"
                                 % (authID, authz,))
                        returnValue(authzPrincipal)
                    else:
                        log.info("Could not find authorization user id: %r"
                                 % (authz,))
                        raise HTTPError(responsecode.FORBIDDEN)
            else:
                log.info("Cannot authenticate proxy user %r without X-Authorize-As header"
                         % (authID,))
                raise HTTPError(responsecode.BAD_REQUEST)
        elif authz:
            log.info("Cannot proxy: user %r as %r" % (authID, authz,))
            raise HTTPError(responsecode.FORBIDDEN)
        else:
            # No proxy - do default behavior
            result = (yield super(SudoSACLMixin, self).authorizationPrincipal(request, authID, authnPrincipal))
            returnValue(result)

def updateCacheTokenOnCallback(f):
    def wrapper(self, *args, **kwargs):
        if hasattr(self, "cacheNotifier"):
            def updateToken(response):
                d = self.cacheNotifier.changed()
                d.addCallback(lambda _: response)
                return d

            d = maybeDeferred(f, self, *args, **kwargs)

            if hasattr(self, "cacheNotifier"):
                d.addCallback(updateToken)

            return d
        else:
            return f(self, *args, **kwargs)

    return wrapper


class DirectoryPrincipalPropertySearchMixIn(object):

    @inlineCallbacks
    def report_DAV__principal_property_search(self, request,
        principal_property_search):
        """
        Generate a principal-property-search REPORT. (RFC 3744, section 9.4)
        Overrides twisted implementation, targeting only directory-enabled
        searching.
        """
        # Verify root element
        if not isinstance(principal_property_search, davxml.PrincipalPropertySearch):
            msg = "%s expected as root element, not %s." % (davxml.PrincipalPropertySearch.sname(), principal_property_search.sname())
            log.warn(msg)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

        # Should we AND (the default) or OR (if test="anyof")?
        testMode = principal_property_search.attributes.get("test", "allof")
        if testMode not in ("allof", "anyof"):
            msg = "Bad XML: unknown value for test attribute: %s" % (testMode,)
            log.warn(msg)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))
        operand = "and" if testMode == "allof" else "or"

        # Are we narrowing results down to a single CUTYPE?
        cuType = principal_property_search.attributes.get("type", None)
        if cuType not in ("INDIVIDUAL", "GROUP", "RESOURCE", "ROOM", None):
            msg = "Bad XML: unknown value for type attribute: %s" % (cuType,)
            log.warn(msg)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

        # Only handle Depth: 0
        depth = request.headers.getHeader("depth", "0")
        if depth != "0":
            log.err("Error in principal-property-search REPORT, Depth set to %s" % (depth,))
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Depth %s not allowed" % (depth,)))

        # Get any limit value from xml
        clientLimit = None

        # Get a single DAV:prop element from the REPORT request body
        propertiesForResource = None
        propElement = None
        propertySearches = []
        applyTo = False
        for child in principal_property_search.children:
            if child.qname() == (dav_namespace, "prop"):
                propertiesForResource = prop_common.propertyListForResource
                propElement = child

            elif child.qname() == (dav_namespace,
                "apply-to-principal-collection-set"):
                applyTo = True

            elif child.qname() == (dav_namespace, "property-search"):
                props = child.childOfType(davxml.PropertyContainer)
                props.removeWhitespaceNodes()

                match = child.childOfType(davxml.Match)
                caseless = match.attributes.get("caseless", "yes")
                if caseless not in ("yes", "no"):
                    msg = "Bad XML: unknown value for caseless attribute: %s" % (caseless,)
                    log.warn(msg)
                    raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))
                caseless = (caseless == "yes")
                matchType = match.attributes.get("match-type", "contains")
                if matchType not in ("starts-with", "contains", "equals"):
                    msg = "Bad XML: unknown value for match-type attribute: %s" % (matchType,)
                    log.warn(msg)
                    raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

                propertySearches.append((props.children, str(match), caseless, matchType))

            elif child.qname() == (calendarserver_namespace, "limit"):
                try:
                    nresults = child.childOfType(customxml.NResults)
                    clientLimit = int(str(nresults))
                except (TypeError, ValueError,):
                    msg = "Bad XML: unknown value for <limit> element"
                    log.warn(msg)
                    raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

        # Run report
        resultsWereLimited = None
        resources = []
        if applyTo or not hasattr(self, "directory"):
            for principalCollection in self.principalCollections():
                uri = principalCollection.principalCollectionURL()
                resource = (yield request.locateResource(uri))
                if resource:
                    resources.append((resource, uri))
        else:
            resources.append((self, request.uri))

        # We need to access a directory service
        principalCollection = resources[0][0]
        if not hasattr(principalCollection, "directory"):
            # Use Twisted's implementation instead in this case
            result = (yield super(DirectoryPrincipalPropertySearchMixIn, self).report_DAV__principal_property_search(request, principal_property_search))
            returnValue(result)

        dir = principalCollection.directory

        # See if we can take advantage of the directory
        fields = []
        nonDirectorySearches = []
        for props, match, caseless, matchType in propertySearches:
            nonDirectoryProps = []
            for prop in props:
                try:
                    fieldName, match = principalCollection.propertyToField(
                        prop, match)
                except ValueError, e:
                    raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))
                if fieldName:
                    fields.append((fieldName, match, caseless, matchType))
                else:
                    nonDirectoryProps.append(prop)
            if nonDirectoryProps:
                nonDirectorySearches.append((nonDirectoryProps, match,
                    caseless, matchType))

        matchingResources = []
        matchcount = 0

        # nonDirectorySearches are ignored
        if fields:

            records = (yield dir.recordsMatchingFieldsWithCUType(fields,
                operand=operand, cuType=cuType))

            for record in records:
                resource = principalCollection.principalForRecord(record)
                if resource:
                    matchingResources.append(resource)
    
                    # We've determined this is a matching resource
                    matchcount += 1
                    if clientLimit is not None and matchcount >= clientLimit:
                        resultsWereLimited = ("client", matchcount)
                        break
                    if matchcount >= max_number_of_matches:
                        resultsWereLimited = ("server", matchcount)
                        break

        # Generate the response
        responses = []
        for resource in matchingResources:
            url = resource.url()
            yield prop_common.responseForHref(
                request,
                responses,
                davxml.HRef.fromString(url),
                resource,
                propertiesForResource,
                propElement
            )

        if resultsWereLimited is not None:
            if resultsWereLimited[0] == "server":
                log.err("Too many matching resources in principal-property-search report")
            responses.append(davxml.StatusResponse(
                davxml.HRef.fromString(request.uri),
                davxml.Status.fromResponseCode(responsecode.INSUFFICIENT_STORAGE_SPACE),
                davxml.Error(davxml.NumberOfMatchesWithinLimits()),
                davxml.ResponseDescription("Results limited by %s at %d" % resultsWereLimited),
            ))
        returnValue(MultiStatusResponse(responses))


class DAVResource (DirectoryPrincipalPropertySearchMixIn, SudoSACLMixin, SuperDAVResource, LoggingMixIn):
    """
    Extended L{twext.web2.dav.resource.DAVResource} implementation.
    """
    def renderHTTP(self, request):
        log.info("%s %s %s" % (request.method, urllib.unquote(request.uri), "HTTP/%s.%s" % request.clientproto))
        return super(DAVResource, self).renderHTTP(request)

    @updateCacheTokenOnCallback
    def http_PROPPATCH(self, request):
        return super(DAVResource, self).http_PROPPATCH(request)


    @updateCacheTokenOnCallback
    def http_DELETE(self, request):
        return super(DAVResource, self).http_DELETE(request)


    @updateCacheTokenOnCallback
    def http_ACL(self, request):
        return super(DAVResource, self).http_ACL(request)

    
    http_REPORT = http_REPORT


    @inlineCallbacks
    def findChildrenFaster(self, depth, request, okcallback, badcallback, names, privileges, inherited_aces):
        """
        See L{IDAVResource.findChildren}.

        This implementation works for C{depth} values of C{"0"}, C{"1"}, 
        and C{"infinity"}.  As long as C{self.listChildren} is implemented
        
        @param depth: a C{str} for the depth: "0", "1" and "infinity" only allowed.
        @param request: the L{Request} for the current request in progress
        @param okcallback: a callback function used on all resources that pass the privilege check,
            or C{None}
        @param badcallback: a callback function used on all resources that fail the privilege check,
            or C{None}
        @param names: a C{list} of C{str}'s containing the names of the child resources to lookup. If
            empty or C{None} all children will be examined, otherwise only the ones in the list.
        @param privileges: a list of privileges to check.
        @param inherited_aces: the list of parent ACEs that are inherited by all children.
        """
        assert depth in ("0", "1", "infinity"), "Invalid depth: %s" % (depth,)

        if depth == "0" or not self.isCollection():
            returnValue(None)

        # First find all depth 1 children
        #children = []
        #yield self.findChildren("1", request, lambda x, y: children.append((x, y)), privileges=None, inherited_aces=None)

        children = []
        basepath = request.urlForResource(self)
        childnames = list(self.listChildren())
        for childname in childnames:
            if names and childname not in names:
                continue
            childpath = joinURL(basepath, childname)
            child = (yield request.locateChildResource(self, childname))
            if child is None:
                children.append((None, childpath + "/"))
            else:
                if child.isCollection():
                    children.append((child, childpath + "/"))
                else:
                    children.append((child, childpath))

        # Generate (acl,supported_privs) map
        aclmap = {}
        for resource, url in children:
            acl = (yield resource.accessControlList(request, inheritance=False, inherited_aces=inherited_aces))
            supportedPrivs = (yield resource.supportedPrivileges(request))
            aclmap.setdefault((pickle.dumps(acl), supportedPrivs), (acl, supportedPrivs, []))[2].append((resource, url))           

        # Now determine whether each ace satisfies privileges
        #print aclmap
        allowed_collections = []
        for items in aclmap.itervalues():
            checked = (yield self.checkACLPrivilege(request, items[0], items[1], privileges, inherited_aces))
            if checked:
                for resource, url in items[2]:
                    if okcallback:
                        okcallback(resource, url)
                    if resource.isCollection():
                        allowed_collections.append((resource, url))
            else:
                if badcallback:
                    for resource, url in items[2]:
                        badcallback(resource, url)

        # TODO: Depth: infinity support
        if depth == "infinity":
            for collection, url in allowed_collections:
                collection_inherited_aces = (yield collection.inheritedACEsforChildren(request))
                yield collection.findChildrenFaster(depth, request, okcallback, badcallback, names, privileges, inherited_aces=collection_inherited_aces)
                
        returnValue(None)

    @inlineCallbacks
    def checkACLPrivilege(self, request, acl, privyset, privileges, inherited_aces):
        
        if acl is None:
            returnValue(False)

        principal = self.currentPrincipal(request)

        # Other principal types don't make sense as actors.
        assert principal.children[0].name in ("unauthenticated", "href"), \
            "Principal is not an actor: %r" % (principal,)

        acl = self.fullAccessControlList(acl, inherited_aces)

        pending = list(privileges)
        denied = []

        for ace in acl.children:
            for privilege in tuple(pending):
                if not self.matchPrivilege(davxml.Privilege(privilege), ace.privileges, privyset):
                    continue

                match = (yield self.matchPrincipal(principal, ace.principal, request))

                if match:
                    if ace.invert:
                        continue
                else:
                    if not ace.invert:
                        continue

                pending.remove(privilege)

                if not ace.allow:
                    denied.append(privilege)

        returnValue(len(denied) + len(pending) == 0)

    def fullAccessControlList(self, acl, inherited_aces):
        """
        See L{IDAVResource.accessControlList}.

        This implementation looks up the ACL in the private property
        C{(L{twisted_private_namespace}, "acl")}.
        If no ACL has been stored for this resource, it returns the value
        returned by C{defaultAccessControlList}.
        If access is disabled it will return C{None}.
        """
        #
        # Inheritance is problematic. Here is what we do:
        #
        # 1. A private element <Twisted:inheritable> is defined for use inside
        #    of a <DAV:ace>. This private element is removed when the ACE is
        #    exposed via WebDAV.
        #
        # 2. When checking ACLs with inheritance resolution, the server must
        #    examine all parent resources of the current one looking for any
        #    <Twisted:inheritable> elements.
        #
        # If those are defined, the relevant ace is applied to the ACL on the
        # current resource.
        #

        # Dynamically update privileges for those ace's that are inherited.
        if acl:
            aces = list(acl.children)
        else:
            aces = []

        aces.extend(inherited_aces)

        acl = davxml.ACL(*aces)

        return acl
    
    @inlineCallbacks
    def matchPrincipal(self, principal1, principal2, request):
        """
        Implementation of DAVResource.matchPrincipal that caches the principal match
        for the duration of a request. This avoids having to do repeated group membership
        tests when privileges on multiple resources are determined.
        """
        
        if not hasattr(request, "matchPrincipalCache"):
            request.matchPrincipalCache = {}

        # The interesting part of a principal is it's one child
        principals = (principal1, principal2)
        cache_key = tuple([str(p.children[0]) for p in principals])

        match = request.matchPrincipalCache.get(cache_key, None)
        if match is None:
            match = (yield super(DAVResource, self).matchPrincipal(principal1, principal2, request))
            request.matchPrincipalCache[cache_key] = match
            
        returnValue(match)


class DAVPrincipalResource (DirectoryPrincipalPropertySearchMixIn, SuperDAVPrincipalResource, LoggingMixIn):
    """
    Extended L{twext.web2.dav.static.DAVFile} implementation.
    """

    liveProperties = tuple(SuperDAVPrincipalResource.liveProperties) + (
        (calendarserver_namespace, "expanded-group-member-set"),
        (calendarserver_namespace, "expanded-group-membership"),
        (calendarserver_namespace, "record-type"),
    )

    def renderHTTP(self, request):
        log.info("%s %s %s" % (request.method, urllib.unquote(request.uri), "HTTP/%s.%s" % request.clientproto))
        return super(DAVPrincipalResource, self).renderHTTP(request)

    http_REPORT = http_REPORT

    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname

        if namespace == dav_namespace:
            if name == "resourcetype":
                returnValue(self.resourceType())

        elif namespace == calendarserver_namespace:
            if name == "expanded-group-member-set":
                principals = (yield self.expandedGroupMembers())
                returnValue(customxml.ExpandedGroupMemberSet(
                    *[davxml.HRef(p.principalURL()) for p in principals]
                ))

            elif name == "expanded-group-membership":
                principals = (yield self.expandedGroupMemberships())
                returnValue(customxml.ExpandedGroupMembership(
                    *[davxml.HRef(p.principalURL()) for p in principals]
                ))

            elif name == "record-type":
                if hasattr(self, "record"):
                    returnValue(customxml.RecordType(self.record.recordType))
                else:
                    raise HTTPError(StatusResponse(
                        responsecode.NOT_FOUND,
                        "Property %s does not exist." % (qname,)
                    ))



        result = (yield super(DAVPrincipalResource, self).readProperty(property, request))
        returnValue(result)

    def groupMembers(self):
        return succeed(())

    def expandedGroupMembers(self):
        return succeed(())

    def groupMemberships(self):
        return succeed(())

    def expandedGroupMemberships(self):
        return succeed(())

    def resourceType(self):
        # Allow live property to be overridden by dead property
        if self.deadProperties().contains((dav_namespace, "resourcetype")):
            return self.deadProperties().get((dav_namespace, "resourcetype"))
        if self.isCollection():
            return davxml.ResourceType(davxml.Collection(), davxml.Principal())
        else:
            return davxml.ResourceType(davxml.Principal())


class DAVFile (SudoSACLMixin, SuperDAVFile, LoggingMixIn):
    """
    Extended L{twext.web2.dav.static.DAVFile} implementation.
    """
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == (dav_namespace, "resourcetype"):
            return succeed(self.resourceType())

        return super(DAVFile, self).readProperty(property, request)

    def resourceType(self):
        # Allow live property to be overridden by dead property
        if self.deadProperties().contains((dav_namespace, "resourcetype")):
            return self.deadProperties().get((dav_namespace, "resourcetype"))
        if self.isCollection():
            return davxml.ResourceType.collection
        return davxml.ResourceType.empty

    def render(self, request):
        if not self.fp.exists():
            return responsecode.NOT_FOUND

        if self.fp.isdir():
            if request.path[-1] != "/":
                # Redirect to include trailing '/' in URI
                return RedirectResponse(request.unparseURL(path=urllib.quote(urllib.unquote(request.path), safe=':/')+'/'))
            else:
                ifp = self.fp.childSearchPreauth(*self.indexNames)
                if ifp:
                    # Render from the index file
                    return self.createSimilarFile(ifp.path).render(request)

                return self.renderDirectory(request)

        try:
            f = self.fp.open()
        except IOError, e:
            import errno
            if e[0] == errno.EACCES:
                return responsecode.FORBIDDEN
            elif e[0] == errno.ENOENT:
                return responsecode.NOT_FOUND
            else:
                raise

        response = Response()
        response.stream = FileStream(f, 0, self.fp.getsize())

        for (header, value) in (
            ("content-type", self.contentType()),
            ("content-encoding", self.contentEncoding()),
        ):
            if value is not None:
                response.headers.setHeader(header, value)

        return response

    def directoryStyleSheet(self):
        return (
            "th, .even td, .odd td { padding-right: 0.5em; font-family: monospace}"
            ".even-dir { background-color: #efe0ef }"
            ".even { background-color: #eee }"
            ".odd-dir {background-color: #f0d0ef }"
            ".odd { background-color: #dedede }"
            ".icon { text-align: center }"
            ".listing {"
              "margin-left: auto;"
              "margin-right: auto;"
              "width: 50%;"
              "padding: 0.1em;"
            "}"
            "body { border: 0; padding: 0; margin: 0; background-color: #efefef;}"
            "h1 {padding: 0.1em; background-color: #777; color: white; border-bottom: thin white dashed;}"
        )

    def renderDirectory(self, request):
        """
        Render a directory listing.
        """
        output = [
            """<html>"""
            """<head>"""
            """<title>Collection listing for %(path)s</title>"""
            """<style>%(style)s</style>"""
            """</head>"""
            """<body>"""
            % {
                "path": "%s" % cgi.escape(urllib.unquote(request.path)),
                "style": self.directoryStyleSheet(),
            }
        ]

        def gotBody(body, output=output):
            output.append(body)
            output.append("</body></html>")

            output = "".join(output)

            if isinstance(output, unicode):
                output = output.encode("utf-8")

            mime_params = {"charset": "utf-8"}

            response = Response(200, {}, output)
            response.headers.setHeader("content-type", MimeType("text", "html", mime_params))
            return response

        d = self.renderDirectoryBody(request)
        d.addCallback(gotBody)
        return d

    @printTracebacks
    def renderDirectoryBody(self, request):
        """
        Generate a directory listing table in HTML.
        """
        output = [
            """<div class="directory-listing">"""
            """<h1>Collection Listing</h1>"""
            """<table>"""
            """<tr><th>Name</th> <th>Size</th> <th>Last Modified</th> <th>MIME Type</th></tr>"""
        ]

        even = Alternator()
        for name in sorted(self.listChildren()):
            child = self.getChild(name)

            url, name, size, lastModified, contentType = self.getChildDirectoryEntry(child, name)

            # FIXME: gray out resources that are not readable
            output.append(
                """<tr class="%(even)s">"""
                """<td><a href="%(url)s">%(name)s</a></td>"""
                """<td align="right">%(size)s</td>"""
                """<td>%(lastModified)s</td>"""
                """<td>%(type)s</td>"""
                """</tr>"""
                % {
                    "even": even.state() and "even" or "odd",
                    "url": url,
                    "name": cgi.escape(name),
                    "size": size,
                    "lastModified": lastModified,
                    "type": contentType,
                }
            )

        output.append(
            """</table></div>"""
            """<div class="directory-listing">"""
            """<h1>Properties</h1>"""
            """<table>"""
            """<tr><th>Name</th> <th>Value</th></tr>"""
        )

        def gotProperties(qnames):
            ds = []

            noneValue         = object()
            accessDeniedValue = object()

            def gotProperty(property):
                if property is None:
                    name = "{%s}%s" % qname
                    value = noneValue
                else:
                    name = property.sname()
                    value = property.toxml()

                return (name, value)

            def gotError(f, qname):
                f.trap(HTTPError)

                name = "{%s}%s" % qname
                code = f.value.response.code

                if code == responsecode.NOT_FOUND:
                    log.err("Property {%s}%s was returned by listProperties() but does not exist for resource %s."
                            % (qname[0], qname[1], self))
                    return (name, None)

                if code == responsecode.UNAUTHORIZED:
                    return (name, accessDeniedValue)

                return f

            for qname in sorted(qnames):
                d = self.readProperty(qname, request)
                d.addCallback(gotProperty)
                d.addErrback(gotError, qname)
                ds.append(d)

            even = Alternator()

            def gotValues(items):
                for result, (name, value) in items:
                    if not result:
                        continue

                    if value is None:
                        # An AssertionError might be appropriate, but
                        # we may as well continue rendering.
                        log.err("Unexpected None value for property: %s" % (name,))
                        continue
                    elif value is noneValue:
                        value = "<i>(no value)</i>"
                    elif value is accessDeniedValue:
                        value = "<i>(access forbidden)</i>"
                    else:
                        value = cgi.escape(value)

                    output.append(
                        str("""<tr class="%(even)s">"""
                            """<td valign="top">%(name)s</td>"""
                            """<td><pre>%(value)s</pre></td>"""
                            """</tr>"""
                            % {
                                "even": even.state() and "even" or "odd",
                                "name": name,
                                "value": value,
                            }
                        )
                    )

                output.append("</div>")
                return "".join(output)

            d = DeferredList(ds)
            d.addCallback(gotValues)
            return d

        d = self.listProperties(request)
        d.addCallback(gotProperties)
        return d

    def getChildDirectoryEntry(self, child, name):
        def orNone(value, default="?", f=None):
            if value is None:
                return default
            elif f is not None:
                return f(value)
            else:
                return value
            
        url = urllib.quote(name, '/')
        if isinstance(child, SuperDAVFile) and child.isCollection():
            url += "/"
            name += "/"

        if isinstance(child, MetaDataMixin):
            size = child.contentLength()
            lastModified = child.lastModified()
            contentType = child.contentType()
        else:
            size = None
            lastModified = None
            contentType = None

        if self.fp.isdir():
            contentType = "(collection)"
        else:
            contentType = self._orNone(
                contentType,
                default="-",
                f=lambda m: "%s/%s %s" % (m.mediaType, m.mediaSubtype, m.params)
            )

        return (
            url,
            name,
            orNone(size),
            orNone(
                lastModified,
                default="",
                f=lambda t: time.strftime("%Y-%b-%d %H:%M", time.localtime(t))
             ),
             contentType,
         )




class ReadOnlyWritePropertiesResourceMixIn (object):
    """
    Read only that will allow writing of properties resource.
    """
    readOnlyResponse = StatusResponse(
        responsecode.FORBIDDEN,
        "Resource is read only."
    )

    def _forbidden(self, request):
        return self.readOnlyResponse

    http_DELETE = _forbidden
    http_MOVE   = _forbidden
    http_PUT    = _forbidden

class ReadOnlyResourceMixIn (ReadOnlyWritePropertiesResourceMixIn):
    """
    Read only resource.
    """
    http_PROPPATCH = ReadOnlyWritePropertiesResourceMixIn._forbidden

    def writeProperty(self, property, request):
        raise HTTPError(self.readOnlyResponse)

    def accessControlList(
        self, request, inheritance=True, expanding=False, inherited_aces=None
    ):
        # Permissions here are fixed, and are not subject to                    
        # inheritance rules, etc.                                               
        return succeed(self.defaultAccessControlList())

class PropertyNotFoundError (HTTPError):
    def __init__(self, qname):
        HTTPError.__init__(self,
            StatusResponse(
                responsecode.NOT_FOUND,
                "No such property: {%s}%s" % qname
            )
        )

class CachingPropertyStore (LoggingMixIn):
    """
    DAV property store using a dict in memory on top of another
    property store implementation.
    """
    def __init__(self, propertyStore):
        self.propertyStore = propertyStore
        self.resource = propertyStore.resource

    def get(self, qname):
        #self.log_debug("Get: %r, %r" % (self.resource.fp.path, qname))

        cache = self._cache()

        if qname in cache:
            property = cache.get(qname, None)
            if property is None:
                self.log_debug("Cache miss: %r, %r, %r" % (self, self.resource.fp.path, qname))
                try:
                    property = self.propertyStore.get(qname)
                except HTTPError:
                    del cache[qname]
                    raise PropertyNotFoundError(qname)
                cache[qname] = property

            return property
        else:
            raise PropertyNotFoundError(qname)

    def set(self, property):
        #self.log_debug("Set: %r, %r" % (self.resource.fp.path, property))

        cache = self._cache()

        cache[property.qname()] = None
        self.propertyStore.set(property)
        cache[property.qname()] = property

    def contains(self, qname):
        #self.log_debug("Contains: %r, %r" % (self.resource.fp.path, qname))

        try:
            cache = self._cache()
        except HTTPError, e:
            if e.response.code == responsecode.NOT_FOUND:
                return False
            else:
                raise

        if qname in cache:
            #self.log_debug("Contains cache hit: %r, %r, %r" % (self, self.resource.fp.path, qname))
            return True
        else:
            return False

    def delete(self, qname):
        #self.log_debug("Delete: %r, %r" % (self.resource.fp.path, qname))

        if self._data is not None and qname in self._data:
            del self._data[qname]

        self.propertyStore.delete(qname)

    def list(self):
        #self.log_debug("List: %r" % (self.resource.fp.path,))
        return self._cache().iterkeys()

    def _cache(self):
        if not hasattr(self, "_data"):
            #self.log_debug("Cache init: %r" % (self.resource.fp.path,))
            self._data = dict(
                (name, None)
                for name in self.propertyStore.list()
            )
        return self._data

