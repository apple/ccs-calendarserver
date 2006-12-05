##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
]

import urllib
import time

from twisted.web2 import responsecode
from twisted.web2.http import HTTPError, Response
from twisted.web2.http_headers import MimeType
from twisted.web2.stream import FileStream
from twisted.web2.static import MetaDataMixin
from twisted.web2.dav.http import StatusResponse
from twisted.web2.dav.static import DAVFile as SuperDAVFile
from twisted.web2.dav.resource import DAVResource as SuperDAVResource

class DAVResource (SuperDAVResource):
    """
    Extended L{twisted.web2.dav.resource.DAVResource} implementation.
    """

class DAVFile (SuperDAVFile):
    """
    Extended L{twisted.web2.dav.static.DAVFile} implementation.
    """
    def render(self, req):
        """You know what you doing."""
        if not self.fp.exists():
            return responsecode.NOT_FOUND

        if self.fp.isdir():
            if req.uri[-1] != "/":
                # Redirect to include trailing '/' in URI
                return http.RedirectResponse(req.unparseURL(path=req.path+'/'))
            else:
                ifp = self.fp.childSearchPreauth(*self.indexNames)
                if ifp:
                    # Render from the index file
                    return self.createSimilarFile(ifp.path).render(req)

                return self.render_directory(req)

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

    def render_directory(self, request):
        """
        Render a directory listing.
        """
        title = "Directory listing for %s" % urllib.unquote(request.path)
    
        s = """<html>
<head>
<title>%(title)s</title>
<style>
th, .even td, .odd td { padding-right: 0.5em; font-family: monospace}
.even-dir { background-color: #efe0ef }
.even { background-color: #eee }
.odd-dir {background-color: #f0d0ef }
.odd { background-color: #dedede }
.icon { text-align: center }
.listing {
  margin-left: auto;
  margin-right: auto;
  width: 50%%;
  padding: 0.1em;
}
body { border: 0; padding: 0; margin: 0; background-color: #efefef;}
h1 {padding: 0.1em; background-color: #777; color: white; border-bottom: thin white dashed;}
</style>
</head>
<body>
<div class="directory-listing">
<h1>%(title)s</h1>
<table>

<tr><th>Filename</th> <th>Size</th> <th>Last Modified</th> <th>File Type</th></tr>
""" % { "title": urllib.unquote(request.uri) }

        even = False
        children = list(self.listChildren())
        children.sort()
        for name in children:
            child = self.getChild(name)

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

            def orNone(value, default="?", f=None):
                if value is None:
                    return default
                elif f is not None:
                    return f(value)
                else:
                    return value

            # FIXME: gray out resources that are not readable
            s += """<tr class="%(even)s"><td><a href="%(url)s">%(name)s</a></td> <td align="right">%(size)s</td> <td>%(lastModified)s</td><td>%(type)s</td></tr>\n""" % {
                "even": even and "even" or "odd",
                "url": url,
                "name": name,
                "size": orNone(size),
                "lastModified": orNone(lastModified, f=lambda t: time.strftime("%Y-%b-%d %H:%M", time.localtime(t))),
                "type": orNone(contentType, default="-", f=lambda m: "%s/%s %s" % (m.mediaType, m.mediaSubtype, m.params)),
            }
            even = not even
        s += """
</table>
</div>
</body>
</html>
"""

        response = Response(200, {}, s)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response

class ReadOnlyResourceMixIn (object):
    """
    Read only resource.
    """
    readOnlyResponse = StatusResponse(
        responsecode.FORBIDDEN,
        "Resource is read only."
    )

    def _forbidden(self, request):
        return self.readOnlyResponse

    http_DELETE    = _forbidden
    http_MOVE      = _forbidden
    http_PROPPATCH = _forbidden
    http_PUT       = _forbidden

    def writeProperty(self, property, request):
        raise HTTPError(self.readOnlyResponse)
