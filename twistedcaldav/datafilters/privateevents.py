##
# Copyright (c) 2009-2012 Apple Inc. All rights reserved.
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

from twext.web2 import responsecode
from twext.web2.http import HTTPError, StatusResponse
from twistedcaldav.caldavxml import Property, CalendarData, CalendarComponent,\
    AllProperties, AllComponents
from twistedcaldav.datafilters.calendardata import CalendarDataFilter
from twistedcaldav.datafilters.filter import CalendarFilter
from twistedcaldav.ical import Component

__all__ = [
    "PrivateEventFilter",
]

class PrivateEventFilter(CalendarFilter):
    """
    Filter a private event to match the rights of the non-owner user accessing the data
    """

    def __init__(self, accessRestriction, isowner):
        """
        
        @param accessRestriction: one of the access levels in L{Component}
        @type accessRestriction: C{str}
        @param isowner: whether the current user is the owner of the data
        @type isowner: C{bool}
        """
        
        self.accessRestriction = accessRestriction
        self.isowner = isowner
    
    def filter(self, ical):
        """
        Filter the supplied iCalendar object using the request information.

        @param ical: iCalendar object
        @type ical: L{Component} or C{str}
        
        @return: L{Component} for the filtered calendar data
        """
        
        if self.isowner or self.accessRestriction == Component.ACCESS_PUBLIC or not self.accessRestriction:
            # No need to filter for the owner or public event
            return ical
        
        elif self.accessRestriction == Component.ACCESS_PRIVATE:
            # We should never get here because ACCESS_PRIVATE is protected via an ACL
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Access Denied"))

        elif self.accessRestriction == Component.ACCESS_PUBLIC:
            return ical
        elif self.accessRestriction in (Component.ACCESS_CONFIDENTIAL, Component.ACCESS_RESTRICTED):
            # Create a CALDAV:calendar-data element with the appropriate iCalendar Component/Property
            # filter in place for the access restriction in use
            
            extra_access = ()
            if self.accessRestriction == Component.ACCESS_RESTRICTED:
                extra_access = (
                    Property(name="SUMMARY"),
                    Property(name="LOCATION"),
                )

            calendardata = CalendarData(
                CalendarComponent(
                    
                    # VCALENDAR properties
                    Property(name="PRODID"),
                    Property(name="VERSION"),
                    Property(name="CALSCALE"),
                    Property(name=Component.ACCESS_PROPERTY),

                    # VEVENT
                    CalendarComponent(
                        Property(name="UID"),
                        Property(name="RECURRENCE-ID"),
                        Property(name="SEQUENCE"),
                        Property(name="DTSTAMP"),
                        Property(name="STATUS"),
                        Property(name="TRANSP"),
                        Property(name="DTSTART"),
                        Property(name="DTEND"),
                        Property(name="DURATION"),
                        Property(name="RRULE"),
                        Property(name="RDATE"),
                        Property(name="EXRULE"),
                        Property(name="EXDATE"),
                        *extra_access,
                        **{"name":"VEVENT"}
                    ),
                    
                    # VTODO
                    CalendarComponent(
                        Property(name="UID"),
                        Property(name="RECURRENCE-ID"),
                        Property(name="SEQUENCE"),
                        Property(name="DTSTAMP"),
                        Property(name="STATUS"),
                        Property(name="DTSTART"),
                        Property(name="COMPLETED"),
                        Property(name="DUE"),
                        Property(name="DURATION"),
                        Property(name="RRULE"),
                        Property(name="RDATE"),
                        Property(name="EXRULE"),
                        Property(name="EXDATE"),
                        *extra_access,
                        **{"name":"VTODO"}
                    ),
                    
                    # VJOURNAL
                    CalendarComponent(
                        Property(name="UID"),
                        Property(name="RECURRENCE-ID"),
                        Property(name="SEQUENCE"),
                        Property(name="DTSTAMP"),
                        Property(name="STATUS"),
                        Property(name="TRANSP"),
                        Property(name="DTSTART"),
                        Property(name="RRULE"),
                        Property(name="RDATE"),
                        Property(name="EXRULE"),
                        Property(name="EXDATE"),
                        *extra_access,
                        **{"name":"VJOURNAL"}
                    ),
                    
                    # VFREEBUSY
                    CalendarComponent(
                        Property(name="UID"),
                        Property(name="DTSTAMP"),
                        Property(name="DTSTART"),
                        Property(name="DTEND"),
                        Property(name="DURATION"),
                        Property(name="FREEBUSY"),
                        *extra_access,
                        **{"name":"VFREEBUSY"}
                    ),
                    
                    # VTIMEZONE
                    CalendarComponent(
                        AllProperties(),
                        AllComponents(),
                        name="VTIMEZONE",
                    ),
                    name="VCALENDAR",
                ),
            )

            # Now "filter" the resource calendar data through the CALDAV:calendar-data element
            return CalendarDataFilter(calendardata).filter(ical)
        else:
            # Unknown access restriction
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Access Denied"))
    
    def merge(self, icalnew, icalold):
        """
        Private event merging does not happen
        """
        raise NotImplementedError
