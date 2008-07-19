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
    "XMLResponse",
]

import cPickle as pickle
import urllib
import cgi
import time

from twisted.internet.defer import succeed, deferredGenerator, waitForDeferred, DeferredList
from twisted.internet.defer import maybeDeferred
from twisted.web2 import responsecode
from twisted.web2.http import HTTPError, Response, RedirectResponse
from twisted.web2.http_headers import MimeType
from twisted.web2.stream import FileStream
from twisted.web2.static import MetaDataMixin
from twisted.web2.dav import davxml
from twisted.web2.dav.davxml import dav_namespace
from twisted.web2.dav.http import StatusResponse
from twisted.web2.dav.static import DAVFile as SuperDAVFile
from twisted.web2.dav.resource import DAVResource as SuperDAVResource
from twisted.web2.dav.resource import DAVPrincipalResource as SuperDAVPrincipalResource
from twisted.web2.dav.util import joinURL
from twisted.web2.dav.xattrprops import xattrPropertyStore

from twistedcaldav.log import Logger, LoggingMixIn
from twistedcaldav.util import submodule, Alternator, printTracebacks
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.directory import DirectoryService

log = Logger()

#
# Alter logger for some twisted stuff
#
import twisted
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
    submodule(twisted, m).log = Logger("twisted." + m)
del m

class SudoSACLMixin(object):
    """
    Mixin class to let DAVResource, and DAVFile subclasses below know
    about sudoer principals and how to find their AuthID
    """
    def authenticate(self, request):
        # Bypass normal authentication if its already been done (by SACL check)
        if (hasattr(request, "authnUser") and
            hasattr(request, "authzUser") and
            request.authnUser is not None and
            request.authzUser is not None):
            return (request.authnUser, request.authzUser)
        else:
            return super(SudoSACLMixin, self).authenticate(request)

    def findPrincipalForAuthID(self, authid):
        """
        Return an authentication and authorization principal identifiers for 
        the authentication identifier passed in.  Check for sudo users before
        regular users.
        """
        for collection in self.principalCollections():
            principal = collection.principalForShortName(
                SudoDirectoryService.recordType_sudoers, 
                authid)
            if principal is not None:
                return principal

        return super(SudoSACLMixin, self).findPrincipalForAuthID(authid)

    def authorizationPrincipal(self, request, authid, authnPrincipal):
        """
        Determine the authorization principal for the given request and authentication principal.
        This implementation looks for an X-Authorize-As header value to use as the authorization principal.
        
        @param request: the L{IRequest} for the request in progress.
        @param authid: a string containing the authentication/authorization identifier
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

        def isSudoPrincipal(authid):
            if getPrincipalForType(SudoDirectoryService.recordType_sudoers, 
                                   authid):
                return True
            return False

        if isSudoPrincipal(authid):
            if authz:
                if isSudoPrincipal(authz):
                    log.msg("Cannot proxy as another proxy: user '%s' as user '%s'" % (authid, authz))
                    raise HTTPError(responsecode.FORBIDDEN)
                else:
                    authzPrincipal = getPrincipalForType(
                        DirectoryService.recordType_groups, authz)

                    if not authzPrincipal:
                        authzPrincipal = self.findPrincipalForAuthID(authz)

                    if authzPrincipal is not None:
                        log.msg("Allow proxy: user '%s' as '%s'" % (authid, authz,))
                        yield authzPrincipal
                        return
                    else:
                        log.msg("Could not find authorization user id: '%s'" % 
                                (authz,))
                        raise HTTPError(responsecode.FORBIDDEN)
            else:
                log.msg("Cannot authenticate proxy user '%s' without X-Authorize-As header" % (authid, ))
                raise HTTPError(responsecode.BAD_REQUEST)
        elif authz:
            log.msg("Cannot proxy: user '%s' as '%s'" % (authid, authz,))
            raise HTTPError(responsecode.FORBIDDEN)
        else:
            # No proxy - do default behavior
            d = waitForDeferred(super(SudoSACLMixin, self).authorizationPrincipal(request, authid, authnPrincipal))
            yield d
            yield d.getResult()
            return

    authorizationPrincipal = deferredGenerator(authorizationPrincipal)


def updateCacheTokenOnCallback(f):
    def fun(self, *args, **kwargs):
        def _updateToken(response):
            return self.cacheNotifier.changed().addCallback(
                lambda _: response)

        d = maybeDeferred(f, self, *args, **kwargs)

        if hasattr(self, 'cacheNotifier'):
            d.addCallback(_updateToken)

        return d

    return fun


class DAVResource (SudoSACLMixin, SuperDAVResource, LoggingMixIn):
    """
    Extended L{twisted.web2.dav.resource.DAVResource} implementation.
    """

    @updateCacheTokenOnCallback
    def http_PROPPATCH(self, request):
        return super(DAVResource, self).http_PROPPATCH(request)


    @updateCacheTokenOnCallback
    def http_DELETE(self, request):
        return super(DAVResource, self).http_DELETE(request)


    @updateCacheTokenOnCallback
    def http_ACL(self, request):
        return super(DAVResource, self).http_ACL(request)


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
            yield None
            return

        # First find all depth 1 children
        #children = []
        #d = waitForDeferred(self.findChildren("1", request, lambda x, y: children.append((x, y)), privileges=None, inherited_aces=None))
        #yield d
        #d.getResult()

        children = []
        basepath = request.urlForResource(self)
        childnames = list(self.listChildren())
        for childname in childnames:
            if names and childname not in names:
                continue
            childpath = joinURL(basepath, childname)
            d = waitForDeferred(request.locateChildResource(self, childname))
            yield d
            child = d.getResult()
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
            acl = waitForDeferred(resource.accessControlList(request, inheritance=False, inherited_aces=inherited_aces))
            yield acl
            acl = acl.getResult()
            supportedPrivs = waitForDeferred(resource.supportedPrivileges(request))
            yield supportedPrivs
            supportedPrivs = supportedPrivs.getResult()
            aclmap.setdefault((pickle.dumps(acl), supportedPrivs), (acl, supportedPrivs, []))[2].append((resource, url))           

        # Now determine whether each ace satisfies privileges
        #print aclmap
        allowed_collections = []
        for items in aclmap.itervalues():
            checked = waitForDeferred(self.checkACLPrivilege(request, items[0], items[1], privileges, inherited_aces))
            yield checked
            checked = checked.getResult()
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
                collection_inherited_aces = waitForDeferred(collection.inheritedACEsforChildren(request))
                yield collection_inherited_aces
                collection_inherited_aces = collection_inherited_aces.getResult()
                d = waitForDeferred(collection.findChildrenFaster(depth, request, okcallback, badcallback, names, privileges, inherited_aces=collection_inherited_aces))
                yield d
                d.getResult()
                
        yield None
  
    findChildrenFaster = deferredGenerator(findChildrenFaster)

    def checkACLPrivilege(self, request, acl, privyset, privileges, inherited_aces):
        
        if acl is None:
            yield False
            return

        principal = self.currentPrincipal(request)

        # Other principal types don't make sense as actors.
        assert (
            principal.children[0].name in ("unauthenticated", "href"),
            "Principal is not an actor: %r" % (principal,)
        )

        acl = self.fullAccessControlList(acl, inherited_aces)

        pending = list(privileges)
        denied = []

        for ace in acl.children:
            for privilege in tuple(pending):
                if not self.matchPrivilege(davxml.Privilege(privilege), ace.privileges, privyset):
                    continue

                match = waitForDeferred(self.matchPrincipal(principal, ace.principal, request))
                yield match
                match = match.getResult()

                if match:
                    if ace.invert:
                        continue
                else:
                    if not ace.invert:
                        continue

                pending.remove(privilege)

                if not ace.allow:
                    denied.append(privilege)

        yield len(denied) + len(pending) == 0

    checkACLPrivilege = deferredGenerator(checkACLPrivilege)

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
    
    @deferredGenerator
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
            match = waitForDeferred(super(DAVResource, self).matchPrincipal(principal1, principal2, request))
            yield match
            match = match.getResult()
            request.matchPrincipalCache[cache_key] = match
            
        yield match

class DAVPrincipalResource (SuperDAVPrincipalResource, LoggingMixIn):
    """
    Extended L{twisted.web2.dav.static.DAVFile} implementation.
    """
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == (dav_namespace, "resourcetype"):
            return succeed(self.resourceType())

        return super(DAVPrincipalResource, self).readProperty(property, request)

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
    Extended L{twisted.web2.dav.static.DAVFile} implementation.
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
        # Allow live property to be overriden by dead property
        if self.deadProperties().contains((dav_namespace, "resourcetype")):
            return self.deadProperties().get((dav_namespace, "resourcetype"))
        if self.isCollection():
            return davxml.ResourceType.collection
        return davxml.ResourceType.empty

    def render(self, request):
        if not self.fp.exists():
            return responsecode.NOT_FOUND

        if self.fp.isdir():
            if request.uri[-1] != "/":
                # Redirect to include trailing '/' in URI
                return RedirectResponse(request.unparseURL(path=request.path+'/'))
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

            for qname in qnames:
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
                        """<tr class="%(even)s">"""
                        """<td valign="top">%(name)s</td>"""
                        """<td><pre>%(value)s</pre></td>"""
                        """</tr>"""
                        % {
                            "even": even.state() and "even" or "odd",
                            "name": name,
                            "value": value,
                        }
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

class XMLResponse (Response):
    """
    XML L{Response} object.
    Renders itself as an XML document.
    """
    def __init__(self, code, element):
        """
        @param xml_responses: an interable of davxml.Response objects.
        """
        Response.__init__(self, code, stream=element.toxml())
        self.headers.setHeader("content-type", MimeType("text", "xml"))

class PropertyNotFoundError (HTTPError):
    def __init__(self, qname):
        HTTPError.__init__(self,
            StatusResponse(
                responsecode.NOT_FOUND,
                "No such property: %s" % (qname,)
            )
        )

class CachingXattrPropertyStore(xattrPropertyStore, LoggingMixIn):
    """
    A Property Store that caches attributes from the xattrs.
    """
    def __init__(self, resource):
        super(CachingXattrPropertyStore, self).__init__(resource)

    def get(self, qname):
        self.log_debug("Get: %r, %r" % (self.resource.fp.path, qname))

        cache = self._cache()

        if qname in cache:
            property = cache.get(qname, None)
            if property is None:
                self.log_debug("Cache miss: %r, %r, %r" % (self, self.resource.fp.path, qname))
                try:
                    property = super(CachingXattrPropertyStore, self).get(qname)
                except HTTPError, e:
                    self.log_debug("Cache double miss: %r, %r, %r" % (self, self.resource.fp.path, qname))
                    del cache[qname]
                    raise PropertyNotFoundError(qname)
                cache[qname] = property
            else:
                self.log_debug("Cache hit: %r, %r, %r" % (self, self.resource.fp.path, qname))

            return property
        else:
            raise PropertyNotFoundError(qname)

    def set(self, property):
        self.log_debug("Set: %r, %r" % (self.resource.fp.path, property))

        cache = self._cache()

        cache[property.qname()] = None
        super(CachingXattrPropertyStore, self).set(property)
        cache[property.qname()] = property

    def contains(self, qname):
        self.log_debug("Contains: %r, %r" % (self.resource.fp.path, qname))

        try:
            cache = self._cache()
        except HTTPError, e:
            if e.response.code == responsecode.NOT_FOUND:
                return False
            else:
                raise

        if qname in cache:
            self.log_debug("Contains cache hit: %r, %r, %r" % (self, self.resource.fp.path, qname))
            return True
        else:
            return False

    def delete(self, qname):
        self.log_debug("Delete: %r, %r" % (self.resource.fp.path, qname))

        if self._data is not None and qname in self._data:
            del self._data[qname]

        super(CachingXattrPropertyStore, self).delete(qname)

    def list(self):
        self.log_debug("List: %r" % (self.resource.fp.path,))
        return self._cache().iterkeys()

    def _cache(self):
        if not hasattr(self, "_data"):
            self._data = dict(
                (name, None)
                for name in super(CachingXattrPropertyStore, self).list()
            )
        return self._data
