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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Extensions to web2.dav
"""

__all__ = [
    "DAVResource",
    "DAVFile",
    "ReadOnlyResourceMixIn",
    "SudoAuthIDMixin",
]

import urllib
import cgi
import time

from twisted.python import log
from twisted.internet.defer import succeed, deferredGenerator, waitForDeferred
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
from twistedcaldav.directory.sudo import SudoDirectoryService


class SudoAuthIDMixin(object):
    """
    Mixin class to let DAVResource, and DAVFile subclasses below know
    about sudoer principals and how to find their AuthID
    """

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

        return super(SudoAuthIDMixin, self).findPrincipalForAuthID(authid)


class DAVResource (SudoAuthIDMixin, SuperDAVResource):
    """
    Extended L{twisted.web2.dav.resource.DAVResource} implementation.
    """


class DAVPrincipalResource (SuperDAVPrincipalResource):
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
        # Allow live property to be overriden by dead property
        if self.deadProperties().contains((dav_namespace, "resourcetype")):
            return self.deadProperties().get((dav_namespace, "resourcetype"))
        if self.isCollection():
            return davxml.ResourceType(davxml.Collection(), davxml.Principal())
        else:
            return davxml.ResourceType(davxml.Principal())


class DAVFile (SudoAuthIDMixin, SuperDAVFile):
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

    def render(self, req):
        if not self.fp.exists():
            return responsecode.NOT_FOUND

        if self.fp.isdir():
            if req.uri[-1] != "/":
                # Redirect to include trailing '/' in URI
                return RedirectResponse(req.unparseURL(path=req.path+'/'))
            else:
                ifp = self.fp.childSearchPreauth(*self.indexNames)
                if ifp:
                    # Render from the index file
                    return self.createSimilarFile(ifp.path).render(req)

                return self.renderDirectory(req)

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

        def gotTable(table):
            output.append(table)
            output.append("</body></html>")

            response = Response(200, {}, "".join(output))
            response.headers.setHeader("content-type", MimeType("text", "html"))
            return response

        d = self.getDirectoryTable(request)
        d.addCallback(gotTable)
        return d

    def getDirectoryTable(self, request):
        """
        Generate a directory listing table in HTML.
        """
        output = [
            """<div class="directory-listing">"""
            """<h1>Collection Listing</h1>"""
            """<table>"""
            """<tr><th>Name</th> <th>Size</th> <th>Last Modified</th> <th>MIME Type</th></tr>"""
        ]

        even = False
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
                    "even": even and "even" or "odd",
                    "url": url,
                    "name": cgi.escape(name),
                    "size": size,
                    "lastModified": lastModified,
                    "type": contentType,
                }
            )
            even = not even

        output.append(
            """</table></div>"""
            """<div class="directory-listing">"""
            """<h1>Properties</h1>"""
            """<table>"""
            """<tr><th>Name</th> <th>Value</th></tr>"""
        )

        @deferredGenerator
        def gotProperties(qnames):
            even = False
            for qname in qnames:
                property = waitForDeferred(self.readProperty(qname, request))
                yield property
                try:
                    property = property.getResult()
                    name = property.sname()
                    value = property.toxml()
                except HTTPError, e:
                    if e.response.code != responsecode.UNAUTHORIZED:
                        log.err("Unable to read property %s for dirlist: %s" % (qname, e))
                        raise

                    name = "{%s}%s" % qname
                    value = "(access forbidden)"

                output.append(
                    """<tr class="%(even)s">"""
                    """<td>%(name)s</td>"""
                    """<td><pre>%(value)s</pre></td>"""
                    """</tr>"""
                    % {
                        "even": even and "even" or "odd",
                        "name": name,
                        "value": cgi.escape(value),
                    }
                )
                even = not even

            output.append("</div>")

            yield "".join(output)

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
