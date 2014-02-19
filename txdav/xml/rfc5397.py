##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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
##

"""
RFC 5397 (WebDAV Current Principal Extension) XML Elements

This module provides XML element definitions for use with the
DAV:current-user-principal property.

See RFC 5397: http://www.ietf.org/rfc/rfc5397.txt
"""

__all__ = []


from txdav.xml.base import WebDAVElement, dav_namespace
from txdav.xml.element import registerElement, registerElementClass


@registerElement
@registerElementClass
class CurrentUserPrincipal(WebDAVElement):
    """
    Current principal information
    """
    name = "current-user-principal"

    allowed_children = {
        (dav_namespace, "href")            : (0, 1),
        (dav_namespace, "unauthenticated") : (0, 1),
    }
