# -*- test-case-name: calendarserver.webadmin.test.test_principals -*-
##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

from __future__ import print_function

"""
Calendar Server principal management web UI.
"""

__all__ = [
    "WorkMonitorResource",
]

# from twisted.internet.defer import inlineCallbacks, returnValue
# from twisted.web.template import tags as html, renderer

from .resource import PageElement, TemplateResource



class WorkMonitorPageElement(PageElement):
    """
    Principal management page element.
    """

    def __init__(self, store):
        PageElement.__init__(self, u"work")

        self._store = store


    def pageSlots(self):
        return {
            u"title": u"Workload Monitor",
        }



class WorkMonitorResource(TemplateResource):
    """
    Principal management page resource.
    """

    addSlash = True


    def __init__(self, store):
        TemplateResource.__init__(
            self, lambda: WorkMonitorPageElement(store)
        )
