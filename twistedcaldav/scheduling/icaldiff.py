##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

from twistedcaldav.ical import Component
from twistedcaldav.log import Logger

"""
Class that handles diff'ing two calendar objects.
"""

__all__ = [
    "iCalDiff",
]

log = Logger()

class iCalDiff(object):
    
    def __init__(self, calendar1, calendar2):
        """
        
        @param calendar1:
        @type calendar1:
        @param calendar2:
        @type calendar2:
        """
        
        self.calendar1 = calendar1
        self.calendar2 = calendar2
    
    def organizerDiff(self):
        """
        Diff the two calendars looking for changes that should trigger implicit scheduling if
        changed by an organizer. Basically any change except for anything related to a VALARM.
        """
        
        # Do straight comparison without alarms
        self.calendar1 = self.calendar1.duplicate()
        self.calendar1.removeAlarms()
        self.calendar2 = self.calendar2.duplicate()
        self.calendar2.removeAlarms()

        return self.calendar1 == self.calendar2

    def attendeeDiff(self, attendee):
        """
        
        @param attendee: the value of the ATTENDEE property corresponding to the attendee making the change
        @type attendee: C{str}
        """
        """
        Diff the two calendars looking for changes that should trigger implicit scheduling if
        changed by an attendee. Also look for changes that are not allowed by an attendee.
        
        Assume that calendar1 is the organizer's copy. We need to filter that to give the attendee's
        view of the event for comparison.
        """
        
        self.attendee = attendee

        # Do straight comparison without alarms
        self.calendar1 = self.calendar1.duplicate()
        self.calendar1.removeAlarms()
        self.calendar1.attendeesView((attendee,))

        self.calendar2 = self.calendar2.duplicate()
        self.calendar2.removeAlarms()

        if self.calendar1 == self.calendar2:
            return True, True

        # Need to look at each component and do special comparisons
        
        # Make sure the same VCALENDAR properties match
        if not self._checkVCALENDARProperties():
            return False, False
        
        # Make sure the same VTIMEZONE components appear
        if not self._compareVTIMEZONEs():
            return False, False
        
        # Compare each component instance from the new calendar with each derived
        # component instance from the old one
        return self._compareComponents()
    
    def _checkVCALENDARProperties(self):

        # Get property differences in the VCALENDAR objects
        propdiff = set(self.calendar1.properties()) ^ set(self.calendar2.properties())
        
        # Ignore certain properties
        ignored = ("PRODID", "CALSCALE",)
        propdiff = set([prop for prop in propdiff if prop.name() not in ignored])
        
        return len(propdiff) == 0

    def _compareVTIMEZONEs(self):

        # FIXME: clients may re-write timezones so the best we can do is
        # compare TZIDs. That is not ideal as a client could have an old version
        # of a VTIMEZONE and thus could show events at different times than the
        # organizer.
        
        def extractTZIDs(calendar):

            tzids = set()
            for component in calendar.subcomponents():
                if component.name() == "VTIMEZONE":
                    tzids.add(component.propertyValue("TZID"))
            return tzids
        
        tzids1 = extractTZIDs(self.calendar1)
        tzids2 = extractTZIDs(self.calendar2)
        return tzids1 == tzids2

    def _compareComponents(self):
        
        # First get uid/rid map of components
        def mapComponents(calendar):
            map = {}
            for component in calendar.subcomponents():
                if component.name() == "VTIMEZONE":
                    continue
                name = component.name()
                uid = component.propertyValue("UID")
                rid = component.getRecurrenceIDUTC()
                map[(name, uid, rid,)] = component
            return map
        
        map1 = mapComponents(self.calendar1)
        set1 = set(map1.keys())
        map2 = mapComponents(self.calendar2)
        set2 = set(map2.keys())

        # All the components in calendar1 must be in calendar2
        if set1 - set2:
            return False, False

        # Now verify that each component in set1 matches what is in set2
        attendee_unchanged = True
        for key, value in map1.iteritems():
            component1 = value
            component2 = map2[key]
            
            nomismatch, no_attendee_change = self._testComponents(component1, component2)
            if not nomismatch:
                return False, False
            attendee_unchanged &= no_attendee_change
        
        # Now verify that each additional component in set2 matches a derived component in set1
        for key in set2 - set1:
            component1 = self.calendar1.deriveInstance(key[2])
            if component1 is None:
                return False, False
            component2 = map2[key]
            
            nomismatch, no_attendee_change = self._testComponents(component1, component2)
            if not nomismatch:
                return False, False
            attendee_unchanged &= no_attendee_change
            
        return True, attendee_unchanged

    def _testComponents(self, comp1, comp2):
        
        assert isinstance(comp1, Component) and isinstance(comp2, Component)
        
        if comp1.name() != comp2.name():
            return False, False
        
        # Only accept a change to this attendee's own ATTENDEE property
        propdiff = set(comp1.properties()) ^ set(comp2.properties())
        for prop in propdiff:
            if prop.name() != "ATTENDEE" or prop.value() != self.attendee:
                return False, False

        # Compare subcomponents.
        # NB at this point we assume VALARMS have been removed.
        if set(comp1.subcomponents()) ^ set(comp2.subcomponents()):
            return False, False
        
        return True, len(propdiff) == 0
