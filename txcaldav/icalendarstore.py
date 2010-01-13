##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Calendar store interfaces
"""

__all__ = [
    "ICalendarHome",
    "ICalendar",
    "ICalendarObject",
]

from zope.interface import Interface #, Attribute

from txdav.idav import IPropertyStore

class ICalendarHome(Interface):
    """
    Calendar home
    """
    def calendars(self):
        """
        Retrieve calendars contained in this calendar home.
        @return: an iterable of L{ICalendar}s.
        """

    def calendarWithName(self, name):
        """
        Retrieve the calendar with the given C{name} contained in this
        calendar home.
        @return: an L{ICalendar}.
        """

    def createCalendarWithName(self, name):
        """
        Create a calendar with the given C{name} in this calendar
        home.
        """

    def properties(self):
        """
        Retrieve the property store for this calendar home.
        @return: an L{IPropertyStore}.
        """

class ICalendar(Interface):
    """
    Calendar
    """
    def ownerCalendarHome(self):
        """
        Retrieve the calendar home for the owner of this calendar.
        Calendars may be shared from one (the owner's) calendar home
        to other (the sharee's) calendar homes.
        @return: an L{ICalendarHome}.
        """

    def calendarObjects(self):
        """
        Retrieve the calendar objects contained in this calendar.
        @return: an iterable of L{ICalendarObject}s.
        """

    def calendarObjectWithName(self, name):
        """
        Retrieve the calendar object with the given C{name} contained
        in this calendar.
        @return: an L{ICalendarObject} or C{None} if no such calendar
        object exists.
        """

    def calendarObjectWithUID(self, uid):
        """
        Retrieve the calendar object with the given C{uid} contained
        in this calendar.
        @return: an L{ICalendarObject} or C{None} if no such calendar
        object exists.
        """

    def syncToken(self):
        """
        Retrieve the current sync token for this calendar.
        @return: a string containing a sync token.
        """

#    def calendarObjectsInTimeRange(self, start, end, timeZone):
#        """
#        Retrieve all calendar objects in this calendar which have
#        instances that occur within the time range that begins at
#        C{start} and ends at C{end}.
#        @return: an iterable of L{ICalendarObject}s.
#        """

    def calendarObjectsSinceToken(self, token):
        """
        Retrieve all calendar objects in this calendar that have
        changed since the given C{token} was last valid.
        @return: a 3-tuple containing an iterable of
        L{ICalendarObject}s that have changed, an iterable of uids
        that have been removed, and the current sync token.
        """

    def properties(self):
        """
        Retrieve the property store for this calendar.
        @return: an L{IPropertyStore}.
        """

class ICalendarObject(Interface):
    """
    Calendar object (event, to-do, etc.).
    """
    def iCalendarText(self):
        """
        Retrieve the iCalendar text data for this calendar object.
        @return: a string containing iCalendar data for a single
        calendar object.
        """

    def uid(self):
        """
        Retrieve the UID for this calendar object.
        @return: a string containing a UID.
        """

    def componentType(self):
        """
        Retrieve the iCalendar component type for the main component
        in this calendar object.
        @return: a string containing the component type.
        """

    def organizer(self):
        # FIXME: Ideally should return a URI object
        """
        Retrieve the organizer for this calendar object.
        @return: a calendar user address.
        """

    def properties(self):
        """
        Retrieve the property store for this calendar object.
        @return: an L{IPropertyStore}.
        """
