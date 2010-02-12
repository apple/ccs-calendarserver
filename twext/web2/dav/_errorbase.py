##
# Copyright (c) 2010 Apple Computer, Inc. All rights reserved.
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
##

"""
This module provides a point to avoid a circular dependency between the davxml
and http modules.
"""

from twext.web2.http_headers import MimeType
from twext.web2.http import Response

class ErrorResponse (Response):
    """
    A L{Response} object which contains a status code and a L{davxml.Error}
    element.
    Renders itself as a DAV:error XML document.
    """
    error = None

    def __init__(self, code, error, stream=None):
        """
        @param code: a response code.
        @param error: an L{davxml.WebDAVElement} identifying the error, or a
            tuple C{(namespace, name)} with which to create an empty element
            denoting the error.  (The latter is useful in the case of
            preconditions ans postconditions, not all of which have defined
            XML element classes.)
        """
        from twext.web2.dav import davxml

        if type(error) is tuple:
            xml_namespace, xml_name = error
            error = davxml.WebDAVUnknownElement()
            error.namespace = xml_namespace
            error.name = xml_name

        if stream is None:
            stream = davxml.Error(error).toxml()

        Response.__init__(self, code=code, stream=stream)

        self.headers.setHeader("content-type", MimeType("text", "xml"))

        self.error = error

    def __repr__(self):
        return "<%s %s %s>" % (self.__class__.__name__, self.code, self.error.sname())
