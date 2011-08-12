##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

"""
Tests for L{calendarserver.webadmin.resource}.
"""

from twisted.trial.unittest import TestCase

from twisted.web.microdom import parseString, getElementsByTagName
from twisted.web.domhelpers import gatherTextNodes

from calendarserver.tap.util import FakeRequest
from twisted.internet.defer import inlineCallbacks
from twisted.internet.defer import returnValue
from calendarserver.webadmin.resource import WebAdminResource
from twistedcaldav.directory.directory import DirectoryRecord



class RenderingTests(TestCase):
    """
    Tests for HTML rendering L{WebAdminResource}.
    """

    def expectRecordSearch(self, searchString, result):
        """
        Expect that a search will be issued via with the given fields, and will
        yield the given result.
        """
        fields = []
        for field in 'fullName', 'firstName', 'lastName', 'emailAddresses':
            fields.append((field, searchString, True, "contains"))
        self.expectedSearches[tuple(fields)] = result


    def recordsMatchingFields(self, fields):
        """
        Pretend to be a directory object for the purposes of testing.
        """
        # 'fields' will be a list of 4-tuples of (fieldName, searchStr, True,
        # "contains"; implement this for tests which will want to call
        # 'search()')
        return self.expectedSearches.pop(tuple(fields))


    def setUp(self):
        self.expectedSearches = {}
        self.resource = WebAdminResource(self.mktemp(), None, self)


    @inlineCallbacks
    def renderPage(self, args={}):
        """
        Render a page, returning a Deferred that fires with the HTML as a
        result.
        """
        req = FakeRequest(method='GET', path='/admin',
                          rootResource=self.resource)
        req.args = args
        response = yield self.resource.render(req)
        self.assertEquals(response.code, 200)
        content = response.stream.mem
        document = parseString(content)
        returnValue(document)


    @inlineCallbacks
    def test_simplestRender(self):
        """
        Rendering a L{WebAdminResource} will result in something vaguely
        parseable as HTML.
        """
        document = yield self.renderPage()
        self.assertEquals(document.documentElement.tagName, 'html')


    @inlineCallbacks
    def test_resourceSearch(self):
        """
        Searching for resources should result in an HTML table resource search.
        """
        self.expectRecordSearch(
            "bob", [
                DirectoryRecord(
                    service=self, recordType='users', guid=None,
                    authIDs=authIds, emailAddresses=tuple(emails),
                    shortNames=tuple(shortNames), fullName=fullName
                )
                for (shortNames, fullName, authIds, emails)
                in [
                    (["bob"], "Bob Bobson", ["boblogin"], [
                        "bob@example.com",
                        "bob@other.example.com"]),
                    (["bobd"], "Bob Dobson", ["bobdlogin"], ["bobd@example.com"]),
                   ]
            ])
        document = yield self.renderPage(dict(resourceSearch=["bob"]))
        tables = getElementsByTagName(document, "table")
        # search results are the first table
        rows = getElementsByTagName(tables[0], 'tr')
        self.assertEquals(len(rows), 3)
        firstRowCells = getElementsByTagName(rows[1], 'td')
        self.assertEquals([gatherTextNodes(cell) for cell in firstRowCells[1:]],
                         ["Bob Bobson", "User", "bob", "boblogin",
                          "bob@example.com, bob@other.example.com"])


    realmName = 'Fake'
    guid = '28c57671-2bf8-4ebd-bc45-fda5ffcee1e8'


class NewRenderingTests(RenderingTests):
    """
    Tests for new L{WebAdminPage} renderer.
    """

    @inlineCallbacks
    def renderPage(self, args={}):
        self.resource.render = self.resource.renderNew
        returnValue((yield super(NewRenderingTests, self).renderPage(args)))


