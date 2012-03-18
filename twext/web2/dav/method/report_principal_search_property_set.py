# -*- test-case-name: twext.web2.dav.test.test_report_expand -*-
##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
WebDAV principal-search-property-set report
"""

__all__ = ["report_DAV__principal_search_property_set"]

from twisted.internet.defer import deferredGenerator

from twext.python.log import Logger
from twext.web2 import responsecode
from txdav.xml import element as davxml
from twext.web2.http import HTTPError, Response, StatusResponse
from twext.web2.stream import MemoryStream

log = Logger()


def report_DAV__principal_search_property_set(self, request, principal_search_property_set):
    """
    Generate a principal-search-property-set REPORT. (RFC 3744, section 9.5)
    """
    # Verify root element
    if not isinstance(principal_search_property_set, davxml.PrincipalSearchPropertySet):
        raise ValueError("%s expected as root element, not %s."
                         % (davxml.PrincipalSearchPropertySet.sname(), principal_search_property_set.sname()))

    # Only handle Depth: 0
    depth = request.headers.getHeader("depth", "0")
    if depth != "0":
        log.err("Error in principal-search-property-set REPORT, Depth set to %s" % (depth,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Depth %s not allowed" % (depth,)))
    
    # Get details from the resource
    result = self.principalSearchPropertySet()
    if result is None:
        log.err("Error in principal-search-property-set REPORT not supported on: %s" % (self,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Not allowed on this resource"))
        
    yield Response(code=responsecode.OK, stream=MemoryStream(result.toxml()))

report_DAV__principal_search_property_set = deferredGenerator(report_DAV__principal_search_property_set)
