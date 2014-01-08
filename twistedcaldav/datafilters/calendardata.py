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

from twistedcaldav.caldavxml import LimitRecurrenceSet, Expand, AllComponents, \
    AllProperties
from twistedcaldav.datafilters.filter import CalendarFilter
from twistedcaldav.dateops import clipPeriod
from twistedcaldav.ical import Component
from pycalendar.period import PyCalendarPeriod

__all__ = [
    "CalendarDataFilter",
]

class CalendarDataFilter(CalendarFilter):
    """
    Filter using the CALDAV:calendar-data element specification
    """

    def __init__(self, calendardata, timezone=None):
        """

        @param calendardata: the XML element describing how to filter
        @type calendardata: L{CalendarData}
        @param timezone: the VTIMEZONE to use for floating/all-day
        @type timezone: L{Component}
        """

        self.calendardata = calendardata
        self.timezone = timezone


    def filter(self, ical):
        """
        Filter the supplied iCalendar object using the request information.

        @param ical: iCalendar object
        @type ical: L{Component} or C{str}

        @return: L{Component} for the filtered calendar data
        """

        # Empty element: get all data
        if not self.calendardata.children:
            return ical

        # Make sure input is valid
        ical = self.validCalendar(ical)

        # Process the calendar data based on expand and limit options
        if self.calendardata.freebusy_set:
            ical = self.limitFreeBusy(ical)

        if self.calendardata.recurrence_set:
            if isinstance(self.calendardata.recurrence_set, LimitRecurrenceSet):
                ical = self.limitRecurrence(ical)
            elif isinstance(self.calendardata.recurrence_set, Expand):
                ical = self.expandRecurrence(ical, self.timezone)

        # Filter data based on any provided CALDAV:comp element, or use all current data
        if self.calendardata.component is not None:
            ical = self.compFilter(self.calendardata.component, ical)

        return ical


    def compFilter(self, comp, component):
        """
        Returns a calendar component object containing the data in the given
        component which is specified by this CalendarComponent.
        """
        if comp.type != component.name():
            raise ValueError("%s of type %r can't get data from component of type %r"
                             % (comp.sname(), comp.type, component.name()))

        result = Component(comp.type)

        xml_components = comp.components
        xml_properties = comp.properties

        # Empty element means do all properties and components
        if xml_components is None and xml_properties is None:
            xml_components = AllComponents()
            xml_properties = AllProperties()

        if xml_components is not None:
            if xml_components == AllComponents():
                for ical_subcomponent in component.subcomponents():
                    result.addComponent(ical_subcomponent)
            else:
                for xml_subcomponent in xml_components:
                    for ical_subcomponent in component.subcomponents():
                        if ical_subcomponent.name() == xml_subcomponent.type:
                            result.addComponent(self.compFilter(xml_subcomponent, ical_subcomponent))

        if xml_properties is not None:
            if xml_properties == AllProperties():
                for ical_property in component.properties():
                    result.addProperty(ical_property)
            else:
                for xml_property in xml_properties:
                    name = xml_property.property_name
                    for ical_property in component.properties(name):
                        result.addProperty(ical_property)

        return result


    def expandRecurrence(self, calendar, timezone=None):
        """
        Expand the recurrence set into individual items.
        @param calendar: the L{Component} for the calendar to operate on.
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.
        @return: the L{Component} for the result.
        """
        return calendar.expand(self.calendardata.recurrence_set.start, self.calendardata.recurrence_set.end, timezone)


    def limitRecurrence(self, calendar):
        """
        Limit the set of overridden instances returned to only those
        that are needed to describe the range of instances covered
        by the specified time range.
        @param calendar: the L{Component} for the calendar to operate on.
        @return: the L{Component} for the result.
        """
        raise NotImplementedError()
        return calendar


    def limitFreeBusy(self, calendar):
        """
        Limit the range of any FREEBUSY properties in the calendar, returning
        a new calendar if limits were applied, or the same one if no limits were applied.
        @param calendar: the L{Component} for the calendar to operate on.
        @return: the L{Component} for the result.
        """

        # First check for any VFREEBUSYs - can ignore limit if there are none
        if calendar.mainType() != "VFREEBUSY":
            return calendar

        # Create duplicate calendar and filter FREEBUSY properties
        calendar = calendar.duplicate()
        for component in calendar.subcomponents():
            if component.name() != "VFREEBUSY":
                continue
            for property in component.properties("FREEBUSY"):
                newvalue = []
                for period in property.value():
                    clipped = clipPeriod(period.getValue(), PyCalendarPeriod(self.calendardata.freebusy_set.start, self.calendardata.freebusy_set.end))
                    if clipped:
                        newvalue.append(clipped)
                if len(newvalue):
                    property.setValue(newvalue)
                else:
                    component.removeProperty(property)
        return calendar


    def merge(self, icalnew, icalold):
        """
        Calendar-data merging does not happen
        """
        raise NotImplementedError
