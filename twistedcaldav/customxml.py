##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Custom CalDAV XML Support.

This module provides custom XML utilities for use with CalDAV.

This API is considered private to static.py and is therefore subject to
change.
"""

from twisted.web2.dav.element import parser
from twisted.web2.dav.resource import twisted_dav_namespace
from twisted.web2.dav import davxml

class TwistedGUIDProperty (davxml.WebDAVTextElement):
    """
    Contains the GUID value for a directory record corresponding to a principal.
    """
    namespace = twisted_dav_namespace
    name = "guid"

    def getValue(self):
        return str(self)

parser.registerElement(TwistedGUIDProperty)

class TwistedLastModifiedProperty (davxml.WebDAVTextElement):
    """
    Contains the Last-Modified value for a directory record corresponding to a principal.
    """
    namespace = twisted_dav_namespace
    name = "last-modified"

    def getValue(self):
        return str(self)

parser.registerElement(TwistedLastModifiedProperty)

class TwistedCalendarPrincipalURI(davxml.WebDAVTextElement):
    """
    Contains the calendarPrincipalURI value for a directory record corresponding to a principal.
    """
    namespace = twisted_dav_namespace
    name = "calendar-principal-uri"

    def getValue(self):
        return str(self)

parser.registerElement(TwistedCalendarPrincipalURI)

class TwistedGroupMemberGUIDs(davxml.WebDAVElement):
    """
    Contains a list of GUIDs (TwistedGUIDProperty) for members of a group. Only used on group principals.
    """
    namespace = twisted_dav_namespace
    name = "group-member-guids"

    allowed_children = { (twisted_dav_namespace, "guid"): (0, None) }

parser.registerElement(TwistedGroupMemberGUIDs)

class TwistedScheduleAutoRespond(davxml.WebDAVEmptyElement):
    """
    When set on an Inbox, scheduling requests are automatically handled.
    """
    namespace = twisted_dav_namespace
    name = "schedule-auto-respond"

parser.registerElement(TwistedScheduleAutoRespond)

