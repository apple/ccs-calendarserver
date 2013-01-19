##
# Copyright (c) 2009-2013 Apple Computer, Inc. All rights reserved.
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
RFC 5995 (Using POST to Add Members to WebDAV Collections) XML
Elements

This module provides XML element definitions for use with using POST
to add members to WebDAV collections.

See RFC 5995: http://www.ietf.org/rfc/rfc5995.txt
"""

__all__ = []


from txdav.xml.base import WebDAVElement, dav_namespace
from txdav.xml.element import registerElement, registerElementClass


@registerElement
@registerElementClass
class AddMember (WebDAVElement):
    """
    A property on a collection to allow for "anonymous" creation of
    resources.
    """
    name = "add-member"
    hidden = True
    protected = True

    allowed_children = { (dav_namespace, "href"): (0, 1) }


@registerElement
@registerElementClass
class AllowClientDefinedURI (WebDAVElement):
    """
    Precondition indicating that the server allows clients to specify
    the last path segment for newly created resources.
    """
    name = "allow-client-defined-uri"
