# -*- test-case-name: calendarserver.webadmin.test.test_log -*-
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
    "LogsResource",
]

# from twisted.web.template import renderer

from .resource import PageElement, TemplateResource



class LogsPageElement(PageElement):
    """
    Logs page element.
    """

    def __init__(self):
        PageElement.__init__(self, "logs")


    def pageSlots(self):
        return {
            u"title": u"Calendar & Contacts Server Logs",
        }



class LogsResource(TemplateResource):
    """
    Web administration landing page resource.
    """

    addSlash = False

    def __init__(self):
        TemplateResource.__init__(self, LogsPageElement())
