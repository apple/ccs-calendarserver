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
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.scheduling.itip import iTipGenerator

from vobject.icalendar import dateTimeToString
from difflib import unified_diff

"""
Class that handles diff'ing two calendar objects.
"""

__all__ = [
    "iCalDiff",
]

log = Logger()

class iCalDiff(object):
    
    def __init__(self, calendar1, calendar2, smart_merge):
        """
        
        @param calendar1:
        @type calendar1:
        @param calendar2:
        @type calendar2:
        """
        
        self.calendar1 = calendar1
        self.calendar2 = calendar2
        self.smart_merge = smart_merge
    
    def organizerDiff(self):
        """
        Diff the two calendars looking for changes that should trigger implicit scheduling if
        changed by an organizer. Basically any change except for anything related to a VALARM.
        """
        
        # If smart merge is needed we have to do this before trying the diff
        if self.smart_merge:
            log.debug("organizerDiff: doing smart Organizer diff/merge")
            self._organizerMerge()

        def duplicateAndNormalize(calendar):
            calendar = calendar.duplicate()
            calendar.removeAlarms()
            calendar.filterProperties(remove=("X-CALENDARSERVER-ACCESS",), do_subcomponents=False)
            calendar.filterProperties(remove=(
                "CREATED",
                "DTSTAMP",
                "LAST-MODIFIED",
            ))
            calendar.removeXProperties()
            calendar.removePropertyParameters("ATTENDEE", ("RSVP", "SCHEDULE-AGENT", "SCHEDULE-STATUS",))
            calendar.normalizeAll()
            return calendar
        
        # Normalize components for comparison
        self.calendar1 = duplicateAndNormalize(self.calendar1)
        self.calendar2 = duplicateAndNormalize(self.calendar2)

        result = self.calendar1 == self.calendar2
        if not result:
            self._logDiffError("organizerDiff: Mismatched calendar objects")
        return result

    def _organizerMerge(self):
        """
        Merge changes to ATTENDEE properties in calendar1 into calendar2.
        """
        organizer = normalizeCUAddr(self.calendar2.masterComponent().propertyValue("ORGANIZER"))
        self._doSmartMerge(organizer, True)

    def _doSmartMerge(self, ignore_attendee, is_organizer):
        """
        Merge changes to ATTENDEE properties in calendar1 into calendar2.
        """
        
        old_master = self.calendar1.masterComponent()
        new_master = self.calendar2.masterComponent()
        
        # Do master merge first
        self._tryComponentMerge(old_master, new_master, ignore_attendee, is_organizer)

        # New check the matching components
        for old_component in self.calendar1.subcomponents():
            
            # Make sure we have an appropriate component
            if old_component.name() == "VTIMEZONE":
                continue
            rid = old_component.getRecurrenceIDUTC()
            if rid is None:
                continue

            # Find matching component in new calendar
            new_component = self.calendar2.overriddenComponent(rid)
            if new_component is None:
                # Determine whether the instance is still valid in the new calendar
                if True:
                    # Derive a new instance from the new calendar and transfer attendee status
                    new_component = self.calendar2.deriveInstance(rid)
                    self.calendar2.addComponent(new_component)
                    self._tryComponentMerge(old_component, new_component, ignore_attendee, is_organizer)
                else:
                    # Ignore the old instance as it no longer exists
                    pass
            else:
                self._tryComponentMerge(old_component, new_component, ignore_attendee, is_organizer)

        # Check the new instances not in the old calendar
        for new_component in self.calendar2.subcomponents():
            
            # Make sure we have an appropriate component
            if new_component.name() == "VTIMEZONE":
                continue
            rid = new_component.getRecurrenceIDUTC()
            if rid is None:
                continue

            # Find matching component in old calendar
            old_component = self.calendar1.overriddenComponent(rid)
            if old_component is None:
                # Try to derive a new instance in the client and transfer attendee status
                old_component = self.calendar1.deriveInstance(rid)
                if old_component:
                    self.calendar1.addComponent(old_component)
                    self._tryComponentMerge(old_component, new_component, ignore_attendee, is_organizer)
                else:
                    # Ignore as we have no state for the new instance
                    pass
    
    def _tryComponentMerge(self, old_comp, new_comp, ignore_attendee_value, is_organizer):
        if not is_organizer or not self._organizerChangePreventsMerge(old_comp, new_comp):
            self._transferAttendees(old_comp, new_comp, ignore_attendee_value)

    def _organizerChangePreventsMerge(self, old_comp, new_comp):
        """
        Check whether a change from an Organizer needs a re-schedule which means that any
        Attendee state changes on the server are no longer relevant.

        @param old_comp: existing server calendar component
        @type old_comp: L{Component}
        @param new_comp: new calendar component
        @type new_comp: L{Component}
        @return: C{True} if changes in new component are such that old attendee state is not
            relevant, C{False} otherwise
        """

        props_to_test = ("DTSTART", "DTEND", "DURATION", "RRULE", "RDATE", "EXDATE", "RECURRENCE-ID",)
        
        for prop in props_to_test:
            # Change => no merge
            if old_comp.getProperty(prop) != new_comp.getProperty(prop):
                # Always overwrite as we have a big change going on
                return True

        return False
    
    def _transferAttendees(self, old_comp, new_comp, ignore_attendee_value):
        """
        Transfer Attendee PARTSTAT from old component to new component.

        @param old_comp: existing server calendar component
        @type old_comp: L{Component}
        @param new_comp: new calendar component
        @type new_comp: L{Component}
        @param ignore_attendee_value: Attendee to ignore
        @type ignore_attendee_value: C{str}
        """

        # Create map of ATTENDEEs in old component
        old_attendees = {}
        for attendee in old_comp.properties("ATTENDEE"):
            value = normalizeCUAddr(attendee.value())
            if value == ignore_attendee_value:
                continue
            old_attendees[value] = attendee

        for new_attendee in new_comp.properties("ATTENDEE"):
            value = normalizeCUAddr(new_attendee.value())
            old_attendee = old_attendees.get(value)
            if old_attendee:
                self._transferParameter(old_attendee, new_attendee, "PARTSTAT")
                self._transferParameter(old_attendee, new_attendee, "SCHEDULE-STATUS")
    
    def _transferParameter(self, old_property, new_property, parameter):
        paramvalue = old_property.params().get(parameter)
        if paramvalue is None:
            try:
                del new_property.params()[parameter]
            except KeyError:
                pass
        else:
            new_property.params()[parameter] = paramvalue

    def attendeeDiff(self, attendee):
        """
        Merge the ATTENDEE specific changes with the organizer's view of the attendee's event.
        This will remove any attempt by the attendee to change things like the time or location.
       
        @param attendee: the value of the ATTENDEE property corresponding to the attendee making the change
        @type attendee: C{str}
        """
        
        self.attendee = normalizeCUAddr(attendee)

        # If smart merge is needed we have to do this before trying the diff
        if self.smart_merge:
            log.debug("attendeeDiff: doing smart Attendee diff/merge")
            self._attendeeMerge()

        def duplicateAndNormalize(calendar):
            calendar = calendar.duplicate()
            calendar.normalizePropertyValueLists("EXDATE")
            calendar.removePropertyParameters("ORGANIZER", ("SCHEDULE-STATUS",))
            calendar.normalizeAll()
            iTipGenerator.prepareSchedulingMessage(calendar, reply=True)
            return calendar

        # Do straight comparison without alarms
        self.calendar1 = duplicateAndNormalize(self.calendar1)
        self.calendar2 = duplicateAndNormalize(self.calendar2)

        if self.calendar1 == self.calendar2:
            return True, True

        # Need to look at each component and do special comparisons
        
        # Make sure the same VCALENDAR properties match
        if not self._checkVCALENDARProperties():
            self._logDiffError("attendeeDiff: VCALENDAR properties do not match")
            return False, False
        
        # Make sure the same VTIMEZONE components appear
        if not self._compareVTIMEZONEs():
            self._logDiffError("attendeeDiff: VTIMEZONEs do not match")
            return False, False
        
        # Compare each component instance from the new calendar with each derived
        # component instance from the old one
        result = self._compareComponents()
        if not result[0]:
            self._logDiffError("attendeeDiff: Mismatched calendar objects")
        return result
    
    def _attendeeMerge(self):
        """
        Merge changes to ATTENDEE properties in calendar1 into calendar2.
        
        NB At this point we are going to assume that the changes in calendar1 are only
        other ATTENDEE PARTSTAT changes as this method should only get called when
        If-Schedule-Tag-Match is present and does not generate an error for an Attendee.
        """
        self._doSmartMerge(self.attendee, False)

    def whatIsDifferent(self):
        """
        Compare the two calendar objects in their entirety and return a list of properties
        and PARTSTAT parameters that are different.
        """

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
        
        props_changed = set()
        rids = set()

        map1 = mapComponents(self.calendar1)
        set1 = set(map1.keys())
        map2 = mapComponents(self.calendar2)
        set2 = set(map2.keys())

        # Now verify that each component in set1 matches what is in set2
        for key in (set1 & set2):
            component1 = map1[key]
            component2 = map2[key]
            self._diffComponents(component1, component2, props_changed, rids)
        
        # Now verify that each additional component in set1 matches a derived component in set2
        for key in set1 - set2:
            component1 = map1[key]
            component2 = self.calendar2.deriveInstance(key[2])
            if component2 is None:
                continue
            self._diffComponents(component1, component2, props_changed, rids)
        
        # Now verify that each additional component in set1 matches a derived component in set2
        for key in set2 - set1:
            component1 = self.calendar1.deriveInstance(key[2])
            if component1 is None:
                continue
            component2 = map2[key]
            self._diffComponents(component1, component2, props_changed, rids)
        
        if not self.calendar1.isRecurring() and not self.calendar2.isRecurring() or not props_changed:
            rids = None
        return props_changed, rids

    def _checkVCALENDARProperties(self):

        # Get property differences in the VCALENDAR objects
        propdiff = set(self.calendar1.properties()) ^ set(self.calendar2.properties())
        
        # Ignore certain properties
        ignored = ("PRODID", "CALSCALE",)
        propdiff = set([prop for prop in propdiff if prop.name() not in ignored])
        
        result = len(propdiff) == 0
        if not result:
            log.debug("VCALENDAR properties differ: %s" % (propdiff,))
        return result

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
        result = tzids1 == tzids2
        if not result:
            log.debug("Different VTIMEZONES: %s %s" % (tzids1, tzids2))
        return result

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
        result = set1 - set2
        if result:
            log.debug("Missing components from first calendar: %s" % (result,))
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
                log.debug("_compareComponents: Could not derive instance: %s" % (key[2],))
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
            log.debug("Component names are different: '%s' and '%s'" % (comp1.name(), comp2.name()))
            return False, False
        
        # Only accept a change to this attendee's own ATTENDEE property
        comp1.transformAllFromNative()
        comp2.transformAllFromNative()
        propdiff = set(comp1.properties()) ^ set(comp2.properties())
        comp1.transformAllToNative()
        comp2.transformAllToNative()
        for prop in tuple(propdiff):
            # These ones are OK to change
            if prop.name() in (
                "TRANSP",
                "DTSTAMP",
                "CREATED",
                "LAST-MODIFIED",
                "SEQUENCE",
            ):
                propdiff.remove(prop)
                continue
            
            # These ones can change and trigger a reschedule
            if ((prop.name() == "ATTENDEE" and prop.value() == self.attendee) or
                prop.name() == "X-CALENDARSERVER-PRIVATE-COMMENT"):
                continue

            # Change that is not allowed
            log.debug("Component properties are different: %s" % (propdiff,))
            return False, False

        # Compare subcomponents.
        # NB at this point we assume VALARMS have been removed.
        result = set(comp1.subcomponents()) ^ set(comp2.subcomponents())
        if result:
            log.debug("Sub-components are different: %s" % (result,))
            return False, False
        
        return True, len(propdiff) == 0

    def _diffComponents(self, comp1, comp2, changed, rids):
        
        assert isinstance(comp1, Component) and isinstance(comp2, Component)
        
        if comp1.name() != comp2.name():
            log.debug("Component names are different: '%s' and '%s'" % (comp1.name(), comp2.name()))
            return
        
        # Diff all the properties
        comp1.transformAllFromNative()
        comp2.transformAllFromNative()
        propdiff = set(comp1.properties()) ^ set(comp2.properties())
        comp1.transformAllToNative()
        comp2.transformAllToNative()
        
        regular_changes = [prop.name() for prop in propdiff if prop.name() != "ATTENDEE"]
        changed.update(regular_changes)
        
        attendees = set([prop for prop in propdiff if prop.name() == "ATTENDEE"])
        done_attendee = False
        done_partstat = False
        for ctr, attendee in enumerate(attendees):
            for check_ctr, check_attendee in enumerate(attendees):
                if (ctr != check_ctr) and check_attendee.value() == attendee.value():
                    if check_attendee.params().get("PARTSTAT", ("NEEDS-ACTION",)) != attendee.params().get("PARTSTAT", ("NEEDS-ACTION",)):
                        changed.add("PARTSTAT")
                        done_partstat = True
                    break
            else:
                changed.add("ATTENDEE")
                done_attendee = True
            if done_attendee and done_partstat:
                break

        if regular_changes or done_attendee or done_partstat:
            rid = comp1.getRecurrenceIDUTC()
            rids.add(dateTimeToString(rid) if rid is not None else "")

    def _logDiffError(self, title):

        diff = "\n".join(unified_diff(
            str(self.calendar1).split("\n"),
            str(self.calendar2).split("\n"),
            fromfile='Existing Calendar Object',
            tofile='New Calendar Object',
        ))
        log.debug("%s:\n%s" % (title, diff,))
