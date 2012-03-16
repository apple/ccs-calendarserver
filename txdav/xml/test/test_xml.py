# Copyright (c) 2009 Twisted Matrix Laboratories.
# See LICENSE for details.

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
##

"""
Tests for L{twext.web2.dav.davxml}.
"""

from twisted.trial.unittest import TestCase
from twext.web2.dav.davxml import WebDAVDocument, WebDAVUnknownElement
from twext.web2.dav.davxml import Response, HRef, MultiStatus, Status
from twext.web2.dav.davxml import CurrentUserPrincipal


class WebDAVElementTestsMixin:
    """
    Mixin for L{TestCase}s which test a L{WebDAVElement} subclass.
    """
    def test_fromString(self):
        """
        The XML representation of L{WebDAVDocument} can be parsed into a
        L{WebDAVDocument} instance using L{WebDAVDocument.fromString}.
        """
        doc = WebDAVDocument.fromString(self.serialized)
        self.assertEquals(doc, WebDAVDocument(self.element))


    def test_toxml(self):
        """
        L{WebDAVDocument.toxml} returns a C{str} giving the XML representation
        of the L{WebDAVDocument} instance.
        """
        document = WebDAVDocument(self.element)
        self.assertEquals(
            document,
            WebDAVDocument.fromString(document.toxml()))


class WebDAVUnknownElementTests(WebDAVElementTestsMixin, TestCase):
    """
    Tests for L{WebDAVUnknownElement}.
    """
    serialized = (
        """<?xml version="1.0" encoding="utf-8" ?>"""
        """<T:foo xmlns:T="http://twistedmatrix.com/"/>"""
    )

    element = WebDAVUnknownElement.withName(
        "http://twistedmatrix.com/",
        "foo"
    )


class MultiStatusTests(WebDAVElementTestsMixin, TestCase):
    """
    Tests for L{MultiStatus}
    """
    serialized = (
        """<?xml version="1.0" encoding="utf-8" ?>"""
        """<D:multistatus xmlns:D="DAV:">"""
        """  <D:response>"""
        """    <D:href>http://webdav.sb.aol.com/webdav/secret</D:href>"""
        """    <D:status>HTTP/1.1 403 Forbidden</D:status>"""
        """  </D:response>"""
        """</D:multistatus>"""
    )

    element = MultiStatus(
        Response(
            HRef("http://webdav.sb.aol.com/webdav/secret"),
            Status("HTTP/1.1 403 Forbidden")),
        )


class CurrentUserPrincipalTests(WebDAVElementTestsMixin, TestCase):
    """
    Tests for L{CurrentUserPrincipal}.
    """
    serialized = (
        """<?xml version="1.0" encoding="utf-8" ?>"""
        """<D:current-user-principal xmlns:D="DAV:">"""
        """  <D:href>foo</D:href>"""
        """</D:current-user-principal>"""
    )

    element = CurrentUserPrincipal(HRef("foo"))
