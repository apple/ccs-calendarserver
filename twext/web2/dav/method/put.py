# -*- test-case-name: twext.web2.dav.test.test_put -*-
##
# Copyright (c) 2005-2012 Apple Computer, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
WebDAV PUT method
"""

__all__ = ["preconditions_PUT", "http_PUT"]

from twisted.internet.defer import deferredGenerator, waitForDeferred

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.http import HTTPError, StatusResponse
from txdav.xml import element as davxml
from twext.web2.dav.method import put_common
from twext.web2.dav.util import parentForURL

log = Logger()


def preconditions_PUT(self, request):
    #
    # Check authentication and access controls
    #
    if self.exists():
        x = waitForDeferred(self.authorize(request, (davxml.WriteContent(),)))
        yield x
        x.getResult()
    else:
        parent = waitForDeferred(request.locateResource(parentForURL(request.uri)))
        yield parent
        parent = parent.getResult()

        if not parent.exists():
            raise HTTPError(
                StatusResponse(
                    responsecode.CONFLICT,
                    "cannot PUT to non-existent parent"))
        x = waitForDeferred(parent.authorize(request, (davxml.Bind(),)))
        yield x
        x.getResult()


    #
    # HTTP/1.1 (RFC 2068, section 9.6) requires that we respond with a Not
    # Implemented error if we get a Content-* header which we don't
    # recognize and handle properly.
    #
    for header, value in request.headers.getAllRawHeaders():
        if header.startswith("Content-") and header not in (
           #"Content-Base",     # Doesn't make sense in PUT?
           #"Content-Encoding", # Requires that we decode it?
            "Content-Language",
            "Content-Length",
           #"Content-Location", # Doesn't make sense in PUT?
            "Content-MD5",
           #"Content-Range",    # FIXME: Need to implement this
            "Content-Type",
        ):
            log.err("Client sent unrecognized content header in PUT request: %s"
                    % (header,))
            raise HTTPError(StatusResponse(
                responsecode.NOT_IMPLEMENTED,
                "Unrecognized content header %r in request." % (header,)
            ))

preconditions_PUT = deferredGenerator(preconditions_PUT)

def http_PUT(self, request):
    """
    Respond to a PUT request. (RFC 2518, section 8.7)
    """
    log.msg("Writing request stream to %s" % (self,))

    #
    # Don't pass in the request URI, since PUT isn't specified to be able
    # to return a MULTI_STATUS response, which is WebDAV-specific (and PUT is
    # not).
    #
    #return put(request.stream, self.fp)
    return put_common.storeResource(request, destination=self, destination_uri=request.uri)
