# -*- test-case-name: calendarserver.webadmin.test.test_landing -*-
##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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
    "WebAdminLandingResource",
]

from twisted.python.modules import getModule
from twisted.web.template import Element, renderer, XMLFile, tags

from .resource import TemplateResource



class WebAdminLandingPageElement(Element):
    """
    Web administration langing page element.
    """

    loader = XMLFile(
        getModule(__name__).filePath.sibling("landing.xhtml")
    )

    pageSlots = {
        u"title": u"Calendar & Contacts Server Administration",
    }


    def __init__(self):
        Element.__init__(self)


    @renderer
    def main(self, request, tag):
        """
        Main renderer, which fills page-global slots like 'title'.
        """
        tag.fillSlots(**self.pageSlots)
        return tag


    @renderer
    def stylesheet(self, request, tag):
        return tags.link(
            rel="stylesheet",
            media="screen",
            href="style.css",
            type="text/css",
        )



class WebAdminLandingResource(TemplateResource):
    """
    Web administration landing page resource.
    """

    addSlash = True

    def __init__(self, path, root, directory, store, principalCollections=()):
        TemplateResource.__init__(self, WebAdminLandingPageElement())

        self._path = path
        self._root = root
        self.directory = directory
        self.store = store
        self._principalCollections = principalCollections
