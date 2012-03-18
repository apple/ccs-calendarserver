# -*- test-case-name: twext.web2.dav.test.test_lock -*-
##
# Copyright (c) 2005 Apple Computer, Inc. All rights reserved.
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
WebDAV GET and HEAD methods
"""

__all__ = ["http_OPTIONS", "http_HEAD", "http_GET"]

import twext

from txdav.xml import element as davxml
from twext.web2.dav.util import parentForURL

def http_OPTIONS(self, request):
    d = authorize(self, request)
    d.addCallback(lambda _: super(twext.web2.dav.resource.DAVResource, self).http_OPTIONS(request))
    return d

def http_HEAD(self, request):
    d = authorize(self, request)
    d.addCallback(lambda _: super(twext.web2.dav.resource.DAVResource, self).http_HEAD(request))
    return d

def http_GET(self, request):
    d = authorize(self, request)
    d.addCallback(lambda _: super(twext.web2.dav.resource.DAVResource, self).http_GET(request))
    return d

def authorize(self, request):
    if self.exists():
        d = self.authorize(request, (davxml.Read(),))
    else:
        d = request.locateResource(parentForURL(request.uri))
        d.addCallback(lambda parent: parent.authorize(request, (davxml.Bind(),)))
    return d
