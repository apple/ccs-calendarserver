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

# from twisted.web.template import renderer

from .resource import PageElement, TemplateResource
from .resource import WebAdminResource
from .logs import LogsResource
from .principals import PrincipalsResource



class WebAdminLandingPageElement(PageElement):
    """
    Web administration langing page element.
    """

    def __init__(self):
        PageElement.__init__(self, u"landing")


    def pageSlots(self):
        return {
            u"title": u"Calendar & Contacts Server Administration",
        }



class WebAdminLandingResource(TemplateResource):
    """
    Web administration landing page resource.
    """

    addSlash = True

    def __init__(self, path, root, directory, store, principalCollections=()):
        TemplateResource.__init__(self, WebAdminLandingPageElement)

        self._path = path
        self._root = root
        self.directory = directory
        self.store = store
        self._principalCollections = principalCollections

        self.putChild(u"logs", LogsResource())
        self.putChild(u"principals", PrincipalsResource(directory))

        self.putChild(
            u"old",
            WebAdminResource(
                path, root, directory, store, principalCollections
            )
        )
