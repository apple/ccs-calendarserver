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

from datetime import datetime, date, tzinfo
from twext.icalendar import Component
from txdav.idav import IPropertyStore

#
# Exceptions
#

class CalendarStoreError(RuntimeError):
    """
    Calendar store generic error.
    """

class AlreadyExistsError(CalendarStoreError):
    """
    Attempt to create an object that already exists.
    """

class CalendarAlreadyExistsError(AlreadyExistsError):
    """
    Calendar already exists.
    """

class CalendarObjectNameAlreadyExistsError(AlreadyExistsError):
    """
    A calendar object with the requested name already exists.
    """

class CalendarObjectUIDAlreadyExistsError(AlreadyExistsError):
    """
    A calendar object with the requested UID already exists.
    """

class NotFoundError(CalendarStoreError):
    """
    Requested data not found.
    """

class NoSuchCalendarError(NotFoundError):
    """
    The requested calendar does not exist.
    """

class NoSuchCalendarObjectError(NotFoundError):
    """
    The requested calendar object does not exist.
    """

class InvalidCalendarComponentError(CalendarStoreError):
    """
    Invalid calendar component.
    """

#
# Interfaces
#

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

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such calendar
            exists.
        """

    def createCalendarWithName(self, name):
        """
        Create a calendar with the given C{name} in this calendar
        home.

        @param name: a string.
        @raise CalendarAlreadyExistsError: if a calendar with the
            given C{name} already exists.
        """

    def removeCalendarWithName(self, name):
        """
        Remove the calendar with the given C{name} from this calendar
        home.  If this calendar home owns the calendar, also remove
        the calendar from all calendar homes.

        @param name: a string.
        @raise NoSuchCalendarObjectError: if no such calendar exists.
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

        @param name: a string.
        @return: an L{ICalendarObject} or C{None} if no such calendar
            object exists.
        """

    def calendarObjectWithUID(self, uid):
        """
        Retrieve the calendar object with the given C{uid} contained
        in this calendar.

        @param uid: a string.
        @return: an L{ICalendarObject} or C{None} if no such calendar
            object exists.
        """

    def createCalendarObjectWithName(self, name, component):
        """
        Create a calendar component with the given C{name} in this
        calendar from the given C{component}.

        @param name: a string.
        @param component: a C{VCALENDAR} L{Component}
        @raise CalendarObjectNameAlreadyExistsError: if a calendar
            object with the given C{name} already exists.
        @raise CalendarObjectUIDAlreadyExistsError: if a calendar
            object with the same UID as the given C{component} already
            exists.
        @raise InvalidCalendarComponentError: if the given
            C{component} is not a valid C{VCALENDAR} L{Component} for
            a calendar object.
        """

    def removeCalendarComponentWithName(self, name):
        """
        Remove the calendar component with the given C{name} from this
        calendar.

        @param name: a string.
        @raise NoSuchCalendarObjectError: if no such calendar object
            exists.
        """

    def removeCalendarComponentWithUID(self, uid):
        """
        Remove the calendar component with the given C{uid} from this
        calendar.

        @param uid: a string.
        @raise NoSuchCalendarObjectError: if the calendar object does
            not exist.
        """

    def syncToken(self):
        """
        Retrieve the current sync token for this calendar.

        @return: a string containing a sync token.
        """

    def calendarObjectsInTimeRange(self, start, end, timeZone):
        """
        Retrieve all calendar objects in this calendar which have
        instances that occur within the time range that begins at
        C{start} and ends at C{end}.

        @param start: a L{datetime} or L{date}.
        @param end: a L{datetime} or L{date}.
        @param timeZone: a L{tzinfo}.
        @return: an iterable of L{ICalendarObject}s.
        """

    def calendarObjectsSinceToken(self, token):
        """
        Retrieve all calendar objects in this calendar that have
        changed since the given C{token} was last valid.

        @param token: a sync token.
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
    def setComponent(self, component):
        """
        Rewrite this calendar object to match the given C{component}.
        C{component} must have the same UID and be of the same
        component type as this calendar object.

        @param component: a C{VCALENDAR} L{Component}.
        @raise InvalidCalendarComponentError: if the given
            C{component} is not a valid C{VCALENDAR} L{Component} for
            a calendar object.
        """

    def component(self):
        """
        Retrieve the calendar component for this calendar object.

        @return: a C{VCALENDAR} L{Component}.
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
        Retrieve the organizer's calendar user address for this
        calendar object.

        @return: a URI string.
        """

    def properties(self):
        """
        Retrieve the property store for this calendar object.

        @return: an L{IPropertyStore}.
        """
