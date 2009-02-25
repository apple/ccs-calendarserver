##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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

from twistedcaldav.dateops import normalizeToUTC
from twistedcaldav.ical import Component, Property
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
                # If the old component was cancelled ignore when an attendee
                if not is_organizer and old_component.propertyValue("STATUS") == "CANCELLED":
                    continue
                
                # Determine whether the instance is still valid in the new calendar
                new_component = self.calendar2.deriveInstance(rid)
                if new_component:
                    # Derive a new instance from the new calendar and transfer attendee status
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
                # If the new component is cancelled ignore when an attendee
                if not is_organizer and new_component.propertyValue("STATUS") == "CANCELLED":
                    continue
                
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
            old_props = set(old_comp.properties(prop))
            new_props = set(new_comp.properties(prop))
            if old_props.difference(new_props):
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
                self._transferParameter(old_attendee, new_attendee, "RSVP")
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
            calendar.normalizeAttachments()
            iTipGenerator.prepareSchedulingMessage(calendar, reply=True)
            return calendar

        # Do straight comparison without alarms
        self.originalCalendar1 = self.calendar1
        self.originalCalendar2 = self.calendar2
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
        tzidRemapping = False
        if not self._compareVTIMEZONEs():
            # Not an error any more. Instead we need to merge back the original TZIDs
            # into the event being written.
            tzidRemapping = True
        
        # Compare each component instance from the new calendar with each derived
        # component instance from the old one
        result = self._compareComponents()
        if not result[0]:
            self._logDiffError("attendeeDiff: Mismatched calendar objects")
        else:
            # May need to do some rewriting
            if tzidRemapping:
                try:
                    self._remapTZIDs()
                    self._logDiffError("attendeeDiff: VTIMEZONEs re-mapped")
                except ValueError, e:
                    self._logDiffError("attendeeDiff: VTIMEZONE re-mapping failed: %s" % (str(e),))
                    return False, False

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

    @staticmethod
    def _extractTZIDs(calendar):

        tzids = set()
        for component in calendar.subcomponents():
            if component.name() == "VTIMEZONE":
                tzids.add(component.propertyValue("TZID"))
        return tzids

    def _compareVTIMEZONEs(self):

        # FIXME: clients may re-write timezones so the best we can do is
        # compare TZIDs. That is not ideal as a client could have an old version
        # of a VTIMEZONE and thus could show events at different times than the
        # organizer.
        
        tzids1 = self._extractTZIDs(self.calendar1)
        tzids2 = self._extractTZIDs(self.calendar2)
        result = tzids1 == tzids2
        if not result:
            log.debug("Different VTIMEZONES: %s %s" % (tzids1, tzids2))
        return result

    def _remapTZIDs(self):
        """
        Re-map TZIDs that changed between the existing calendar data and the new data
        being written for the attendee.
        """

        # Do master component re-map first
        old_master = self.originalCalendar1.masterComponent()
        new_master = self.originalCalendar2.masterComponent()
        self._remapTZIDsOnComponent(old_master, new_master)
        
        # Now do each corresponding overridden component
        for newComponent in self.originalCalendar2.subcomponents():
            
            # Make sure we have an appropriate component
            if newComponent.name() == "VTIMEZONE":
                continue
            rid = newComponent.getRecurrenceIDUTC()
            if rid is None:
                continue

            # Find matching component in new calendar
            oldComponent = self.originalCalendar1.overriddenComponent(rid)
            if oldComponent is None:
                # Derive a new instance from the new calendar and transfer attendee status
                oldComponent = self.originalCalendar2.deriveInstance(rid)

            if oldComponent:
                self._remapTZIDsOnComponent(oldComponent, newComponent)
        
        
        # Now manipulate the VTIMEZONE components in the calendar data
        for newComponent in tuple(self.originalCalendar2.subcomponents()):
            # Make sure we have an appropriate component
            if newComponent.name() == "VTIMEZONE":
                self.originalCalendar2.removeComponent(newComponent)
                
        # The following statement is required to force vobject to serialize the
        # calendar data and in the process add any missing VTIMEZONEs as needed.
        _ignore = str(self.originalCalendar2)
        log.debug(_ignore)
        
    def _remapTZIDsOnComponent(self, oldComponent, newComponent):
        """
        Re-map TZIDs that changed between the existing calendar data and the new data
        being written for the attendee.
        """

        # Look at each property that culd contain a TZID:
        # DTSTART, DTEND, RDATE, EXDATE, RECURRENCE-ID, DUE.
        # NB EXDATE/RDATE can occur multiple times - special case
        checkPropertiesOneOff = (
            "DTSTART",
            "DTEND",
            "RECURRENCE-ID",
            "DUE",
        )
        checkPropertiesMultiple = (
            "RDATE",
            "EXDATE",
        )
        
        for propName in checkPropertiesOneOff:
            oldProp = oldComponent.getProperty(propName)
            newProp = newComponent.getProperty(propName)
            
            # Special case behavior where DURATIOn is mapped to DTEND
            if propName == "DTEND" and oldProp is None and newProp is not None:
                oldProp = oldComponent.getProperty("DTSTART")

            # Transfer tzinfo from old property value to the new one
            if oldProp is not None and newProp is not None:
                if "X-VOBJ-ORIGINAL-TZID" in oldProp.params():
                    oldTZID = oldProp.paramValue("X-VOBJ-ORIGINAL-TZID")
                    if "X-VOBJ-ORIGINAL-TZID" in newProp.params():
                        newTZID = newProp.paramValue("X-VOBJ-ORIGINAL-TZID")
                        
                        if oldTZID != newTZID:
                            newProp.params()["X-VOBJ-ORIGINAL-TZID"][0] = oldTZID
                            newProp.setValue(newProp.value().replace(tzinfo=oldProp.value().tzinfo))
                    else:
                        raise ValueError("Cannot handle mismatched TZIDs on %s" % (propName,))
                        
        for propName in checkPropertiesMultiple:
            oldProps = oldComponent.properties(propName)
            newProps = newComponent.properties(propName)
            oldTZID = None
            oldTzinfo = None
            for prop in oldProps:
                if "X-VOBJ-ORIGINAL-TZID" in prop.params():
                    if oldTZID and oldTZID != prop.paramValue("X-VOBJ-ORIGINAL-TZID"):
                        raise ValueError("Cannot handle different TZIDs on multiple %s" % (propName,))
                    else:
                        oldTZID = prop.paramValue("X-VOBJ-ORIGINAL-TZID")
                        oldTzinfo = prop.value()[0].tzinfo
            for prop in newProps:
                if "X-VOBJ-ORIGINAL-TZID" in prop.params():
                    if oldTZID:
                        prop.params()["X-VOBJ-ORIGINAL-TZID"][0] = oldTZID
                        prop.setValue([item.replace(tzinfo=oldTzinfo) for item in prop.value()])
                    else:
                        raise ValueError("Cannot handle mismatched TZIDs on %s" % (propName,))
                elif oldTZID:
                    raise ValueError("Cannot handle mismatched TZIDs on %s" % (propName,))

    def _compareComponents(self):
        
        # First get uid/rid map of components
        def mapComponents(calendar):
            map = {}
            cancelledRids = set()
            master = None
            for component in calendar.subcomponents():
                if component.name() == "VTIMEZONE":
                    continue
                name = component.name()
                uid = component.propertyValue("UID")
                rid = component.getRecurrenceIDUTC()
                map[(name, uid, rid,)] = component
                if component.propertyValue("STATUS") == "CANCELLED" and rid is not None:
                    cancelledRids.add(rid)
                if rid is None:
                    master = component
            
            # Normalize each master by adding any STATUS:CANCELLED components as EXDATEs
            exdates = set()
            if master:
                for rid in sorted(cancelledRids):
                    master.addProperty(Property("EXDATE", [rid,]))
                
                # Get all EXDATEs in UTC
                for exdate in master.properties("EXDATE"):
                    exdates.update([normalizeToUTC(value) for value in exdate.value()])
               
            return exdates, map
        
        exdates1, map1 = mapComponents(self.calendar1)
        set1 = set(map1.keys())
        exdates2, map2 = mapComponents(self.calendar2)
        set2 = set(map2.keys())

        # All the components in calendar1 must be in calendar2 unless they are CANCELLED
        result = set1 - set2
        for key in result:
            component = map1[key]
            if component.propertyValue("STATUS") != "CANCELLED":
                log.debug("Missing uncancelled component from first calendar: %s" % (key,))
                return False, False
            else: 
                _ignore_name, _ignore_uid, rid = key
                if rid not in exdates2:
                    log.debug("Missing EXDATE for cancelled components from first calendar: %s" % (key,))
                    return False, False
                    

        # Now verify that each component in set1 matches what is in set2
        attendee_unchanged = True
        for key, value in map1.iteritems():
            component1 = value
            component2 = map2.get(key)
            if component2 is None:
                continue

            nomismatch, no_attendee_change = self._testComponents(component1, component2)
            if not nomismatch:
                return False, False
            attendee_unchanged &= no_attendee_change
        
        # Now verify that each additional component in set2 matches a derived component in set1
        for key in set2 - set1:
            
            # First check if the attendee's copy is cancelled and properly EXDATE'd
            # and skip it if so.
            component2 = map2[key]
            if component2.propertyValue("STATUS") == "CANCELLED":
                _ignore_name, _ignore_uid, rid = key
                if rid not in exdates1:
                    log.debug("Cancelled component not found in first calendar (or no EXDATE): %s" % (key,))
                    return False, False
                continue

            # Now derive the organizer's expected instance and compare
            component1 = self.calendar1.deriveInstance(key[2])
            if component1 is None:
                log.debug("_compareComponents: Could not derive instance: %s" % (key[2],))
                return False, False
            
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
            log.debug("Component properties are different (trigger is '%s'): %s" % (prop.name(), propdiff,))
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
