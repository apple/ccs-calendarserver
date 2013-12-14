# -*- test-case-name: txweb2.dav.test.test_delete -*-
##
# Copyright (c) 2005-2013 Apple Computer, Inc. All rights reserved.
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
WebDAV DELETE method
"""

__all__ = ["http_DELETE"]

from twisted.internet.defer import waitForDeferred, deferredGenerator

from twext.python.log import Logger
from txweb2 import responsecode
from txweb2.http import HTTPError
from txdav.xml import element as davxml
from txweb2.dav.method.delete_common import deleteResource
from txweb2.dav.util import parentForURL

log = Logger()


def http_DELETE(self, request):
    """
    Respond to a DELETE request. (RFC 2518, section 8.6)
    """
    if not self.exists():
        log.error("File not found: %s" % (self,))
        raise HTTPError(responsecode.NOT_FOUND)

    depth = request.headers.getHeader("depth", "infinity")

    #
    # Check authentication and access controls
    #
    parent = waitForDeferred(request.locateResource(parentForURL(request.uri)))
    yield parent
    parent = parent.getResult()

    x = waitForDeferred(parent.authorize(request, (davxml.Unbind(),)))
    yield x
    x.getResult()

    x = waitForDeferred(deleteResource(request, self, request.uri, depth))
    yield x
    yield x.getResult()

http_DELETE = deferredGenerator(http_DELETE)
