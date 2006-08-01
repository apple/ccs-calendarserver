##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
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

__version__ = "0.0"

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

