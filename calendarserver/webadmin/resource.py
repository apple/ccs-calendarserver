# -*- test-case-name: calendarserver.webadmin.test.test_resource -*-
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

"""
Calendar Server Web Admin UI.
"""

__all__ = [
    "PageElement",
    "TemplateResource",
]

from twistedcaldav.simpleresource import SimpleResource

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.modules import getModule
from twisted.web.template import (
    Element, renderer, XMLFile, flattenString, tags
)

from txweb2.stream import MemoryStream
from txweb2.http import Response
from txweb2.http_headers import MimeType



class PageElement(Element):
    """
    Page element.
    """

    def __init__(self, templateName):
        super(PageElement, self).__init__()

        self.loader = XMLFile(
            getModule(__name__).filePath.sibling(
                u"{name}.xhtml".format(name=templateName)
            )
        )


    def pageSlots(self):
        return {}


    @renderer
    def main(self, request, tag):
        """
        Main renderer, which fills page-global slots like 'title'.
        """
        tag.fillSlots(**self.pageSlots())
        return tag


    @renderer
    def stylesheet(self, request, tag):
        return tags.link(
            rel=u"stylesheet",
            media=u"screen",
            href=u"/style.css",
            type=u"text/css",
        )



class TemplateResource(SimpleResource):
    """
    Resource that renders a template.
    """

    # @staticmethod
    # def queryValue(request, argument):
    #     for value in request.args.get(argument, []):
    #         return value

    #     return u""

    # @staticmethod
    # def queryValues(request, arguments):
    #     return request.args.get(arguments, [])

    def __init__(self, elementClass, pc, isdir):
        super(TemplateResource, self).__init__(pc, isdir=isdir)

        self.elementClass = elementClass


    # def handleQueryArguments(self, request):
    #     return succeed(None)


    @inlineCallbacks
    def render(self, request):
        # yield self.handleQueryArguments(request)

        htmlContent = yield flattenString(request, self.elementClass())

        response = Response()
        response.stream = MemoryStream(htmlContent)
        response.headers.setHeader(
            b"content-type", MimeType.fromString(b"text/html; charset=utf-8")
        )

        returnValue(response)
