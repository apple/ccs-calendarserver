##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
Custom CalDAV XML Support.

This module provides custom XML utilities for use with CalDAV.

This API is considered private to static.py and is therefore subject to
change.
"""

from twisted.web2.dav.resource import twisted_dav_namespace
from twisted.web2.dav import davxml

from twistedcaldav.ical import Component as iComponent

calendarserver_namespace = "http://calendarserver.org/ns/"

calendarserver_proxy_compliance = (
    "calendar-proxy",
)

calendarserver_private_events_compliance = (
    "calendarserver-private-events",
)

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

class TwistedCalendarAccessProperty (davxml.WebDAVTextElement):
    """
    Contains the calendar access level (private events) for the resource.
    """
    namespace = twisted_dav_namespace
    name = "calendar-access"
    hidden = True

    def getValue(self):
        return str(self)

class CalendarProxyRead (davxml.WebDAVEmptyElement):
    """
    A read-only calendar user proxy principal resource.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "calendar-proxy-read"

class CalendarProxyWrite (davxml.WebDAVEmptyElement):
    """
    A read-write calendar user proxy principal resource.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "calendar-proxy-write"

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

class DropBoxHome (davxml.WebDAVEmptyElement):
    """
    Denotes a drop box home collection (a collection that will contain drop boxes).
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "dropbox-home"

class DropBox (davxml.WebDAVEmptyElement):
    """
    Denotes a drop box collection.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "dropbox"

class DropBoxHomeURL (davxml.WebDAVElement):
    """
    A principal property to indicate the location of the drop box home.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "dropbox-home-URL"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, 1) }

class GETCTag (davxml.WebDAVTextElement):
    """
    Contains the calendar collection entity tag.
    """
    namespace = calendarserver_namespace
    name = "getctag"
    protected = True

class CalendarAvailability (davxml.WebDAVTextElement):
    """
    Contains the calendar availability property.
    """
    namespace = calendarserver_namespace
    name = "calendar-availability"
    hidden = True


    def calendar(self):
        """
        Returns a calendar component derived from this element.
        """
        return iComponent.fromString(str(self))

    def valid(self):
        """
        Determine whether the content of this element is a valid single VAVAILABILITY component,
        with zero or more VTIEMZONE components.

        @return: True if valid, False if not.
        """
        
        try:
            calendar = self.calendar()
            if calendar is None:
                return False
        except ValueError:
            return False

        found = False
        for subcomponent in calendar.subcomponents():
            if subcomponent.name() == "VAVAILABILITY":
                if found:
                    return False
                else:
                    found = True
            elif subcomponent.name() == "VTIMEZONE":
                continue
            else:
                return False

        return found

class Timezones (davxml.WebDAVEmptyElement):
    """
    Denotes a timezone service resource.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "timezones"

class TZIDs (davxml.WebDAVElement):
    """
    Wraps a list of timezone ids.
    """
    namespace = calendarserver_namespace
    name = "tzids"
    allowed_children = { (calendarserver_namespace, "tzid" ): (0, None) }

class TZID (davxml.WebDAVTextElement):
    """
    A timezone id.
    """
    namespace = calendarserver_namespace
    name = "tzid"

class TZData (davxml.WebDAVElement):
    """
    Wraps a list of timezone observances.
    """
    namespace = calendarserver_namespace
    name = "tzdata"
    allowed_children = { (calendarserver_namespace, "observance" ): (0, None) }

class Observance (davxml.WebDAVElement):
    """
    A timezone observance.
    """
    namespace = calendarserver_namespace
    name = "observance"
    allowed_children = {
        (calendarserver_namespace, "onset" )     : (1, 1),
        (calendarserver_namespace, "utc-offset" ): (1, 1),
    }

class Onset (davxml.WebDAVTextElement):
    """
    The onset date-time for a DST transition.
    """
    namespace = calendarserver_namespace
    name = "onset"

class UTCOffset (davxml.WebDAVTextElement):
    """
    A UTC offset value for a timezone observance.
    """
    namespace = calendarserver_namespace
    name = "utc-offset"

class PubSubXMPPURIProperty (davxml.WebDAVTextElement):
    """
    A calendarhomefile property to indicate the pubsub XMPP URI to subscribe to
    for notifications.
    """
    namespace = calendarserver_namespace
    name = "xmpp-uri"
    protected = True

class IScheduleInbox (davxml.WebDAVEmptyElement):
    """
    Denotes the resourcetype of a iSchedule Inbox.
    (CalDAV-s2s-xx, section x.x.x)
    """
    namespace = calendarserver_namespace
    name = "ischedule-inbox"

class FreeBusyURL (davxml.WebDAVEmptyElement):
    """
    Denotes the resourcetype of a free-busy URL resource.
    (CalDAV-s2s-xx, section x.x.x)
    """
    namespace = calendarserver_namespace
    name = "free-busy-url"

##
# Extensions to davxml.ResourceType
##

davxml.ResourceType.dropboxhome = davxml.ResourceType(davxml.Collection(), DropBoxHome())
davxml.ResourceType.dropbox = davxml.ResourceType(davxml.Collection(), DropBox())
davxml.ResourceType.calendarproxyread = davxml.ResourceType(davxml.Principal(), davxml.Collection(), CalendarProxyRead())
davxml.ResourceType.calendarproxywrite = davxml.ResourceType(davxml.Principal(), davxml.Collection(), CalendarProxyWrite())
davxml.ResourceType.timezones = davxml.ResourceType(Timezones())
davxml.ResourceType.ischeduleinbox = davxml.ResourceType(IScheduleInbox())
davxml.ResourceType.freebusyurl = davxml.ResourceType(FreeBusyURL())
