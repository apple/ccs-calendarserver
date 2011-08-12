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

import cgi

from functools import partial

from twisted.trial.unittest import TestCase

from twisted.web.microdom import parseString, getElementsByTagName
from twisted.web.domhelpers import gatherTextNodes


from calendarserver.tap.util import FakeRequest
from twisted.internet.defer import inlineCallbacks
from twisted.internet.defer import returnValue
from calendarserver.webadmin.resource import WebAdminResource

from twext.web2.dav.element.rfc3744 import GroupMemberSet
from twext.web2.dav.element.rfc2518 import DisplayName

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
                    (["bob"], "Bob Bobson", ["boblogin"],
                     ["bob@example.com", "bob@other.example.com"]),
                    (["bobd"], "Bob Dobson", ["bobdlogin"],
                     ["bobd@example.com"]),
                   ]
            ])
        document = yield self.renderPage(dict(resourceSearch=["bob"]))

        # Form is filled out with existing input.
        self.assertEquals(
            document.getElementById("txt_resourceSearch").getAttribute("value"),
            "bob"
        )
        tables = getElementsByTagName(document, "table")
        # search results are the first table
        rows = getElementsByTagName(tables[0], 'tr')
        self.assertEquals(len(rows), 3)
        firstRowCells = getElementsByTagName(rows[1], 'td')
        self.assertEquals(
            [gatherTextNodes(cell) for cell in firstRowCells[1:]],
            ["Bob Bobson", "User", "bob", "boblogin",
             "bob@example.com, bob@other.example.com"]
        )
        [resourceLink] = getElementsByTagName(
            firstRowCells[0], 'a')
        self.assertEquals(
            resourceLink.getAttribute("href"),
            "/admin/?resourceId=users:bob"
        )
        self.assertEquals(gatherTextNodes(resourceLink), "select")
        self.assertNotIn(
            "No matches found for resource bob",
            gatherTextNodes(document)
        )


    @inlineCallbacks
    def test_noResourceFound(self):
        """
        Searching for resources which don't exist should result in an
        informative message.
        """
        self.expectRecordSearch("bob", [])
        document = yield self.renderPage(dict(resourceSearch=["bob"]))
        self.assertIn(
            "No matches found for resource bob",
            gatherTextNodes(document)
        )


    @inlineCallbacks
    def test_selectResourceById(self):
        """
        When a resource is selected by a 'resourceId' parameter, 
        """
        self.resource.getResourceById = partial(FakePrincipalResource, self)
        document = yield self.renderPage(dict(resourceId=["qux"]))
        [detailsTitle] = getElementsByTagName(document, 'h3')
        detailString = gatherTextNodes(detailsTitle)
        self.assertEquals(detailString,
                          "Resource Details: Hello Fake Resource")
        hiddenResourceId = document.getElementById(
            "hdn_resourceId").getAttribute("value")
        self.assertEquals(hiddenResourceId, "qux")


    @inlineCallbacks
    def test_davProperty(self):
        """
        When a resource is selected by a resourceId parameter, and a DAV
        property is selected by the 'davPropertyName' parameter, that property
        will displayed.
        """
        self.resource.getResourceById = partial(FakePrincipalResource, self)
        document = yield self.renderPage(
            dict(resourceId=["qux"],
                 davPropertyName=["DAV:#displayname"])
        )
        propertyName = document.getElementById('txt_davPropertyName')
        self.assertEquals(propertyName.getAttribute("value"),
                          "DAV:#displayname")
        propertyValue = DisplayName("The Name To Display").toxml()
        self.assertIn(cgi.escape(propertyValue),
                      gatherTextNodes(document))


    realmName = 'Fake'
    guid = '28c57671-2bf8-4ebd-bc45-fda5ffcee1e8'



class FakePrincipalResource(object):
    def __init__(self, test, req, resid):
        self.test = test
        test.assertEquals(resid, "qux")


    @property
    def record(self):
        authIds = ['fake auth id']
        emails = ['fake email']
        shortNames = ['fake short name']
        fullName = 'nobody'
        return DirectoryRecord(
            service=self.test, recordType='users', guid=None,
            authIDs=authIds, emailAddresses=tuple(emails),
            shortNames=tuple(shortNames), fullName=fullName
        )


    def __str__(self):
        return 'Hello Fake Resource'


    def getChild(self, name):
        return self


    def readProperty(self, name, request):
        if name == DisplayName.qname():
            return DisplayName("The Name To Display")
        return GroupMemberSet()



class NewRenderingTests(RenderingTests):
    """
    Tests for new L{WebAdminPage} renderer.
    """

    @inlineCallbacks
    def renderPage(self, args={}):
        self.resource.render = self.resource.renderNew
        returnValue((yield super(NewRenderingTests, self).renderPage(args)))


