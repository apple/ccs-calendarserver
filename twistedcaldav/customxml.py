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

from twisted.web2.dav.resource import twisted_dav_namespace
from twisted.web2.dav import davxml

apple_namespace = "http://apple.com/ns/calendarserver/"

class TwistedGUIDProperty (davxml.WebDAVTextElement):
    """
    Contains the GUID value for a directory record corresponding to a principal.
    """
    namespace = twisted_dav_namespace
    name = "guid"
    hidden = True

    def getValue(self):
        return str(self)

class TwistedLastModifiedProperty (davxml.WebDAVTextElement):
    """
    Contains the Last-Modified value for a directory record corresponding to a principal.
    """
    namespace = twisted_dav_namespace
    name = "last-modified"
    hidden = True

    def getValue(self):
        return str(self)

class TwistedCalendarPrincipalURI(davxml.WebDAVTextElement):
    """
    Contains the calendarPrincipalURI value for a directory record corresponding to a principal.
    """
    namespace = twisted_dav_namespace
    name = "calendar-principal-uri"
    hidden = True

    def getValue(self):
        return str(self)

class TwistedGroupMemberGUIDs(davxml.WebDAVElement):
    """
    Contains a list of GUIDs (TwistedGUIDProperty) for members of a group. Only used on group principals.
    """
    namespace = twisted_dav_namespace
    name = "group-member-guids"
    hidden = True

    allowed_children = { (twisted_dav_namespace, "guid"): (0, None) }

class TwistedScheduleAutoRespond(davxml.WebDAVEmptyElement):
    """
    When set on an Inbox, scheduling requests are automatically handled.
    """
    namespace = twisted_dav_namespace
    name = "schedule-auto-respond"
    hidden = True

class DropBoxHome (davxml.WebDAVEmptyElement):
    """
    Denotes a drop box home collection (a collection that will contain drop boxes).
    (Apple Extension to CalDAV)
    """
    namespace = apple_namespace
    name = "dropbox-home"

class DropBox (davxml.WebDAVEmptyElement):
    """
    Denotes a drop box collection.
    (Apple Extension to CalDAV)
    """
    namespace = apple_namespace
    name = "dropbox"

class Notifications (davxml.WebDAVEmptyElement):
    """
    Denotes a notifications collection.
    (Apple Extension to CalDAV)
    """
    namespace = apple_namespace
    name = "notifications"

class DropBoxHomeURL (davxml.WebDAVElement):
    """
    A principal property to indicate the location of the drop box home.
    (Apple Extension to CalDAV)
    """
    namespace = apple_namespace
    name = "dropbox-home-URL"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, 1) }

class NotificationsURL (davxml.WebDAVElement):
    """
    A principal property to indicate the location of the notification collection.
    (Apple Extension to CalDAV)
    """
    namespace = apple_namespace
    name = "notifications-URL"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, 1) }

class Notification(davxml.WebDAVElement):
    """
    Root element for XML data in a notification resource.
    """
    namespace = apple_namespace
    name = "notification"

    allowed_children = {
        (apple_namespace, "time-stamp" ): (1, 1),
        (apple_namespace, "changed"    ): (1, 1),
    }

class TimeStamp (davxml.WebDAVTextElement):
    """
    A property to indicate the timestamp of a notification resource.
    (Apple Extension to CalDAV)
    """
    namespace = apple_namespace
    name = "time-stamp"
    hidden = True
    protected = True

class Changed (davxml.WebDAVElement):
    """
    A property to indicate the URI of the drop box that generated
    notification resource.
    (Apple Extension to CalDAV)
    """
    namespace = apple_namespace
    name = "changed"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, 1) }

class Subscribed (davxml.WebDAVElement):
    """
    A property to indicate which principals will receive notifications.
    (Apple Extension to CalDAV)
    """
    namespace = apple_namespace
    name = "subscribed"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "principal"): (0, None) }

##
# Extensions to davxml.ResourceType
##

davxml.ResourceType.dropboxhome = davxml.ResourceType(davxml.Collection(), DropBoxHome())
davxml.ResourceType.dropbox = davxml.ResourceType(davxml.Collection(), DropBox())
davxml.ResourceType.notifications = davxml.ResourceType(davxml.Collection(), Notifications())
