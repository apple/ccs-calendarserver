# -*- coding: utf-8 -*-
##
# Copyright (c) 2009-2015 Apple Inc. All rights reserved.
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
##

from twext.python.filepath import CachingFilePath as FilePath
from txweb2.http_headers import MimeType
from txweb2.static import MetaDataMixin

from twisted.internet.defer import inlineCallbacks, Deferred, succeed
from twisted.web.microdom import parseString

from twistedcaldav.extensions import DAVFile, DAVResourceWithChildrenMixin, extractCalendarServerPrincipalSearchData, validateTokens
from twistedcaldav.test.util import TestCase

from txdav.xml.element import WebDAVElement, ResourceType
from txdav.xml.parser import WebDAVDocument

from xml.etree.cElementTree import XML

class UnicodeProperty(WebDAVElement):
    """
    An element with a unicode name.
    """

    name = u'unicode'

    allowed_children = {}



class StrProperty(WebDAVElement):
    """
    An element with a unicode name.
    """

    name = 'str'

    allowed_children = {}



class SimpleFakeRequest(object):
    """
    Emulate a very small portion of the web2 'Request' API, just enough to
    render a L{DAVFile}.

    @ivar path: the path portion of the URL being rendered.
    """

    def __init__(self, path):
        self.path = path


    def urlForResource(self, resource):
        """
        @return: this L{SimpleFakeRequest}'s 'path' attribute, since this
            request can render only one thing.
        """
        return self.path



def browserHTML2ETree(htmlString):
    """
    Loosely interpret an HTML string as XML and return an ElementTree object for it.

    We're not promising strict XML (in fact, we're specifically saying HTML) in
    the content-type of certain responses, but it's much easier to work with
    the ElementTree data structures present in Python 2.5+ for testing; so
    we'll use Twisted's built-in facilities to sanitize the inputs before
    making any structured assertions about them.

    A more precise implementation would use
    U{HTML5Lib<http://code.google.com/p/html5lib/wiki/UserDocumentation>}'s
    etree bindings to do the parsing, as that is more directly 'what a browser
    would do', but Twisted's built-in stuff is a good approximation and doesn't
    drag in another dependency.

    @param htmlString: a L{str}, encoded in UTF-8, representing a pile of
        browser-friendly HTML tag soup.

    @return: an object implementing the standard library ElementTree interface.
    """
    return XML(parseString(htmlString, beExtremelyLenient=True).toxml())



nonASCIIFilename = u"アニメ.txt"


class DirectoryListingTest(TestCase):
    """
    Test cases for HTML directory listing.
    """

    @inlineCallbacks
    def doDirectoryTest(self, addedNames, modify=lambda x: None,
                        expectedNames=None):
        """
        Do a test of a L{DAVFile} pointed at a directory, verifying that files
        existing with the given names will be faithfully 'played back' via HTML
        rendering.
        """
        if expectedNames is None:
            expectedNames = addedNames
        fp = FilePath(self.mktemp())
        fp.createDirectory()
        for sampleName in expectedNames:
            fp.child(sampleName).touch()
        df = DAVFile(fp)
        modify(df)
        responseText = (yield df.render(SimpleFakeRequest('/'))).stream.read()
        responseXML = browserHTML2ETree(responseText)
        names = set([element.text.encode("utf-8")
                     for element in responseXML.findall(".//a")])
        self.assertEquals(set(expectedNames), names)


    def test_simpleList(self):
        """
        Rendering a L{DAVFile} that is backed by a directory will produce an
        HTML document including links to its contents.
        """
        return self.doDirectoryTest([u'gamma.txt', u'beta.html', u'alpha.xml'])


    def test_emptyList(self):
        """
        Listing a directory with no files in it will produce an index with no
        links.
        """
        return self.doDirectoryTest([])


    def test_nonASCIIList(self):
        """
        Listing a directory with a file in it that includes characters that
        fall outside of the 'Basic Latin' and 'Latin-1 Supplement' unicode
        blocks should result in those characters being rendered as links in the
        index.
        """
        return self.doDirectoryTest([nonASCIIFilename.encode("utf-8")])


    @inlineCallbacks
    def test_nonASCIIListMixedChildren(self):
        """
        Listing a directory that contains unicode content-type metadata and
        non-ASCII characters in a filename should result in a listing that
        contains the names of both entities.
        """
        unicodeChildName = "test"
        def addUnicodeChild(davFile):
            m = MetaDataMixin()
            m.contentType = lambda: MimeType.fromString('text/plain')
            m.resourceType = lambda: ResourceType()
            m.isCollection = lambda: False
            davFile.putChild(unicodeChildName, m)
        yield self.doDirectoryTest([nonASCIIFilename], addUnicodeChild,
                                   [nonASCIIFilename.encode("utf-8"), unicodeChildName])


    @inlineCallbacks
    def test_nonASCIIListMixedProperties(self):
        """
        Listing a directory that contains unicode DAV properties and non-ASCII
        characters in a filename should result in a listing that contains the
        names of both entities.
        """
        def addUnicodeChild(davFile):
            davFile.writeProperty(UnicodeProperty(), None)
            davFile.writeProperty(StrProperty(), None)
        yield self.doDirectoryTest([nonASCIIFilename], addUnicodeChild,
                                   [nonASCIIFilename.encode("utf-8")])


    def test_quotedCharacters(self):
        """
        Filenames might contain < or > characters, which need to be quoted in
        HTML.
        """
        return self.doDirectoryTest([u'<a>.txt', u'<script>.html',
                                     u'<style>.xml'])



class ChildTraversalTests(TestCase):
    def test_makeChildDeferred(self):
        """
        If L{DAVResourceWithChildrenMixin.makeChild} returns a L{Deferred},
        L{DAVResourceWithChildrenMixin.locateChild} will return a L{Deferred}.
        """
        class FakeChild(object):
            def __init__(self, name):
                self.name = name
        class SmellsLikeDAVResource(object):
            def __init__(self, **kw):
                pass
        class ResourceWithCheese(DAVResourceWithChildrenMixin,
                                 SmellsLikeDAVResource):
            def makeChild(self, name):
                return succeed(FakeChild(name))
        d = ResourceWithCheese().locateChild(None, ['cheese', 'burger'])
        self.assertIsInstance(d, Deferred)
        x = []
        d.addCallback(x.append)
        self.assertEquals(len(x), 1)
        [result] = x
        self.assertEquals(len(result), 2)
        self.assertEquals(result[0].name, 'cheese')
        self.assertEquals(result[1], ['burger'])



class CalendarServerPrincipalSearchTests(TestCase):
    def test_extractCalendarServerPrincipalSearchData(self):
        """
        Exercise the parser for calendarserver-principal-search documents
        """

        data = """<B:calendarserver-principal-search xmlns:A="DAV:" xmlns:B="http://calendarserver.org/ns/" context="attendee">
  <B:search-token>morgen</B:search-token>
  <A:prop>
    <A:principal-URL/>
    <A:displayname/>
  </A:prop>
</B:calendarserver-principal-search>
"""
        doc = WebDAVDocument.fromString(data)
        tokens, context, applyTo, clientLimit, _ignore_propElement = extractCalendarServerPrincipalSearchData(doc.root_element)
        self.assertEquals(tokens, ["morgen"])
        self.assertEquals(context, "attendee")
        self.assertFalse(applyTo)
        self.assertEquals(clientLimit, None)

        data = """<B:calendarserver-principal-search xmlns:A="DAV:" xmlns:B="http://calendarserver.org/ns/">
  <B:search-token>morgen</B:search-token>
  <B:search-token>sagen</B:search-token>
  <B:limit>
      <B:nresults>42</B:nresults>
  </B:limit>
  <A:prop>
    <A:principal-URL/>
    <A:displayname/>
  </A:prop>
  <A:apply-to-principal-collection-set/>
</B:calendarserver-principal-search>
"""
        doc = WebDAVDocument.fromString(data)
        tokens, context, applyTo, clientLimit, _ignore_propElement = extractCalendarServerPrincipalSearchData(doc.root_element)
        self.assertEquals(tokens, ["morgen", "sagen"])
        self.assertEquals(context, None)
        self.assertTrue(applyTo)
        self.assertEquals(clientLimit, 42)


    def test_validateTokens(self):
        """
        Ensure validateTokens only returns True if there is at least one token
        longer than one character
        """
        self.assertTrue(validateTokens(["abc"]))
        self.assertTrue(validateTokens(["ab", "c"]))
        self.assertTrue(validateTokens(["ab"]))
        self.assertFalse(validateTokens(["a"]))
        self.assertFalse(validateTokens(["a", "b", "c"]))
        self.assertFalse(validateTokens([""]))
        self.assertFalse(validateTokens([]))
