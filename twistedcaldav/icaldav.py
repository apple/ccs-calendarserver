##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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
CalDAV interfaces.
"""

__all__ = [
    "ICalDAVResource",
    "ICalendarPrincipalResource",
]

from txweb2.dav.idav import IDAVResource

class ICalDAVResource(IDAVResource):
    """
    CalDAV resource.
    """
    def isCalendarCollection(): #@NoSelf
        """
        (CalDAV-access-10, Section 4.2)
        @return: True if this resource is a calendar collection, False
            otherwise.
        """

    def isSpecialCollection(collectiontype): #@NoSelf
        """
        (CalDAV-access-10, Section 4.2)
        @param collectiontype: L{WebDAVElement} for the collection type to test for.
        @return: True if this resource is a collection that also has the specified type,
            False otherwise.
        """

    def isPseudoCalendarCollection(): #@NoSelf
        """
        @return: True if this resource is a calendar collection like (e.g.
            a regular calendar collection or schedule inbox/outbox), False
            otherwise.
        """

    def findCalendarCollections(depth): #@NoSelf
        """
        Returns an iterable of child calendar collection resources for the given
        depth.
        Because resources do not know their request URIs, children are returned
        as tuples C{(resource, uri)}, where C{resource} is the child resource
        and C{uri} is a URL path relative to this resource.
        @param depth: the search depth (one of "0", "1", or "infinity")
        @return: an iterable of tuples C{(resource, uri)}.
        """

    def createCalendar(request): #@NoSelf
        """
        Create a calendar collection for this resource.
        """

    def iCalendar(): #@NoSelf
        """
        Instantiate an iCalendar component object representing this resource or
        its child with the given name.
        The behavior of this method is not specified if it is called on a
        resource that is not a calendar collection or a calendar resource within
        a calendar collection.

        @return: a L{twistedcaldav.ical.Component} of type C{"VCALENDAR"}.
        """



class ICalendarPrincipalResource(IDAVResource):
    """
    CalDAV principle resource.
    """
    def principalUID(): #@NoSelf
        """
        @return: the user id for this principal.
        """

    def calendarHomeURLs(): #@NoSelf
        """
        @return: a list of calendar home URLs for this principal's calendar user.
        """

    def calendarUserAddresses(): #@NoSelf
        """
        @return: a list of calendar user addresses for this principal's calendar
            user.
        """

    def calendarFreeBusyURIs(request): #@NoSelf
        """
        @param request: the request being processed.
        @return: a L{Deferred} list of URIs for calendars that contribute to
            free-busy for this principal's calendar user.
        """

    def scheduleInboxURL(): #@NoSelf
        """
        Get the schedule INBOX URL for this principal's calendar user.
        @return: a string containing the URL from the schedule-inbox-URL property.
        """

    def scheduleOutboxURL(): #@NoSelf
        """
        Get the schedule OUTBOX URL for this principal's calendar user.
        @return: a string containing the URL from the schedule-outbox-URL property.
        """
