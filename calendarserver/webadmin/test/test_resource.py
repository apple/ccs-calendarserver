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

from twisted.web.microdom import parseString
from calendarserver.tap.util import FakeRequest
from twisted.internet.defer import inlineCallbacks
from twisted.internet.defer import returnValue
from calendarserver.webadmin.resource import WebAdminResource



class RenderingTests(TestCase):
    """
    Tests for HTML rendering L{WebAdminResource}.
    """

    def recordsMatchingFields(self, fields):
        """
        Pretend to be a directory object for the purposes of testing.
        """
        # 'fields' will be a list of 4-tuples of (fieldName, searchStr, True,
        # "contains"; implement this for tests which will want to call
        # 'search()')


    def setUp(self):
        self.resource = WebAdminResource(self.mktemp(), None, self)


    @inlineCallbacks
    def renderPage(self):
        """
        Render a page, returning a Deferred that fires with the HTML as a
        result..
        """
        req = FakeRequest(method='GET', path='/webadmin',
                          rootResource=self.resource)
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



class NewRenderingTests(RenderingTests):
    """
    Tests for new L{WebAdminPage} renderer.
    """

    @inlineCallbacks
    def renderPage(self):
        self.resource.render = self.resource.renderNew
        returnValue((yield super(NewRenderingTests, self).renderPage()))


