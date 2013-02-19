##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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

from twistedcaldav.datafilters.filter import CalendarFilter
from twistedcaldav.ical import Component, ignoredComponents, Property

__all__ = [
    "HiddenInstanceFilter",
]

class HiddenInstanceFilter(CalendarFilter):
    """
    Filter overridden components in an event marked by a specific property to remove the component and add
    a matching EXDATE.
    """

    def filter(self, ical):
        """
        Filter the supplied iCalendar object using the request information.

        @param ical: iCalendar object
        @type ical: L{Component} or C{str}
        
        @return: L{Component} for the filtered calendar data
        """
        
        master = ical.masterComponent()
        if master is None:
            return ical
        for component in tuple(ical.subcomponents()):
            if component.name() in ignoredComponents:
                continue
            rid = component.getRecurrenceIDUTC()
            if rid is None:
                continue
            if component.hasProperty(Component.HIDDEN_INSTANCE_PROPERTY):
                rid = component.getRecurrenceIDUTC()
                ical.removeComponent(component)
                
                # Add EXDATE and try to preserve same timezone as DTSTART
                dtstart = master.getProperty("DTSTART")
                if dtstart is not None and not dtstart.value().isDateOnly() and dtstart.value().local():
                    rid.adjustTimezone(dtstart.value().getTimezone())
                master.addProperty(Property("EXDATE", [rid,]))
        
        return ical
   
    def merge(self, icalnew, icalold):
        """
        Private event merging does not happen
        """
        raise NotImplementedError
