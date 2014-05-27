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



class WebAdminLandingPageElement(PageElement):
    """
    Web administration langing page element.
    """

    def __init__(self):
        super(WebAdminLandingPageElement, self).__init__(u"landing")


    def pageSlots(self):
        return {
            u"title": u"Server Administration",
        }



class WebAdminLandingResource(TemplateResource):
    """
    Web administration landing page resource.
    """

    addSlash = True


    def __init__(self, path, root, directory, store, principalCollections=()):
        super(WebAdminLandingResource, self).__init__(WebAdminLandingPageElement, principalCollections, True)

        from twistedcaldav.config import config as configuration

        self.configuration = configuration
        self.directory = directory
        self.store = store
        # self._path = path
        # self._root = root
        # self._principalCollections = principalCollections

        #from .config import ConfigurationResource
        #self.putChild(u"config", ConfigurationResource(configuration, principalCollections))

        #from .principals import PrincipalsResource
        #self.putChild(u"principals", PrincipalsResource(directory, store, principalCollections))

        # from .logs import LogsResource
        # self.putChild(u"logs", LogsResource())

        # from .work import WorkMonitorResource
        # self.putChild(u"work", WorkMonitorResource(store))


    def getChild(self, name):
        bound = super(WebAdminLandingResource, self).getChild(name)

        if bound is not None:
            return bound

        #
        # Dynamically load and vend child resources not bound using putChild()
        # in __init__().  This is useful for development, since it allows one
        # to comment out the putChild() call above, and then code will be
        # re-loaded for each request.
        #

        from . import config, principals, logs, work

        if name == u"config":
            reload(config)
            return config.ConfigurationResource(self.configuration, self._principalCollections)

        elif name == u"principals":
            reload(principals)
            return principals.PrincipalsResource(self.directory, self.store, self._principalCollections)

        elif name == u"logs":
            reload(logs)
            return logs.LogsResource(self._principalCollections)

        elif name == u"work":
            reload(work)
            return work.WorkMonitorResource(self.store, self._principalCollections)

        return None
