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

from twistedcaldav.dateops import normalizeToUTC, toString,\
    normalizeStartEndDuration
from twistedcaldav.ical import Component, Property
from twistedcaldav.log import Logger
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.scheduling.itip import iTipGenerator

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

    def attendeeMerge(self, attendee):
        """
        Merge the ATTENDEE specific changes with the organizer's view of the attendee's event.
        This will remove any attempt by the attendee to change things like the time or location.
       
        @param attendee: the value of the ATTENDEE property corresponding to the attendee making the change
        @type attendee: C{str}
        
        @return: C{tuple} of:
            C{bool} - change is allowed
            C{bool} - iTIP reply needs to be sent
            C{list} - list of RECURRENCE-IDs changed
            L{Component} - new calendar object to store
        """
        
        self.attendee = normalizeCUAddr(attendee)

        self.newCalendar = self.calendar1.duplicate()
        self.newMaster = self.newCalendar.masterComponent()

        changeCausesReply = False
        changedRids = []
        
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
            _ignore_name, _ignore_uid, rid = key
            component = map1[key]
            if component.propertyValue("STATUS") != "CANCELLED":
                # Attendee may decline by EXDATE'ing an instance - we need to handle that
                if rid in exdates2:
                    # Mark Attendee as DECLINED in the server instance
                    if self._attendeeDecline(self.newCalendar.overriddenComponent(rid)):
                        changeCausesReply = True
                        changedRids.append(rid)
                else:
                    log.debug("attendeeMerge: Missing uncancelled component from first calendar: %s" % (key,))
                    return False, False, (), None
            else: 
                if rid not in exdates2:
                    log.debug("attendeeMerge: Missing EXDATE for cancelled components from first calendar: %s" % (key,))
                    return False, False, (), None
                else:
                    # Remove the CANCELLED component from the new calendar and add an EXDATE
                    overridden = self.newCalendar.overriddenComponent(rid)
                    self.newCalendar.removeComponent(overridden)
                    if self.newMaster:
                        self.newMaster.addProperty(Property("EXDATE", (rid,)))
        
        # Derive a new component in the new calendar for each new one in set2
        for key in set2 - set1:
            
            # First check if the attendee's copy is cancelled and properly EXDATE'd
            # and skip it if so.
            _ignore_name, _ignore_uid, rid = key
            component2 = map2[key]
            if component2.propertyValue("STATUS") == "CANCELLED":
                if rid not in exdates1:
                    log.debug("attendeeMerge: Cancelled component not found in first calendar (or no EXDATE): %s" % (key,))
                    return False, False, (), None
                else:
                    # Derive new component with STATUS:CANCELLED and remove EXDATE
                    newOverride = self.newCalendar.deriveInstance(rid, allowCancelled=True)
                    if newOverride is None:
                        log.debug("attendeeMerge: Could not derive instance for cancelled component: %s" % (key,))
                        return False, False, (), None
                    self.newCalendar.addComponent(newOverride)
            else:
                # Derive new component
                newOverride = self.newCalendar.deriveInstance(rid)
                if newOverride is None:
                    log.debug("attendeeMerge: Could not derive instance for uncancelled component: %s" % (key,))
                    return False, False, (), None
                self.newCalendar.addComponent(newOverride)

        # So now newCalendar has all the same components as set2. Check changes and do transfers.
        
        # Make sure the same VCALENDAR properties match
        if not self._checkVCALENDARProperties(self.newCalendar, self.calendar2):
            self._logDiffError("attendeeMerge: VCALENDAR properties do not match")
            return False, False, (), None

        # Now we transfer per-Attendee
        # data from calendar2 into newCalendar to sync up changes, whilst verifying that other
        # key properties are unchanged
        declines = []
        for key in set2:
            _ignore_name, _ignore_uid, rid = key
            serverData = self.newCalendar.overriddenComponent(rid)
            clientData = map2[key]
            
            allowed, reply = self._transferAttendeeData(serverData, clientData, declines)
            if not allowed:
                self._logDiffError("attendeeMerge: Mismatched calendar objects")
                return False, False, (), None
            changeCausesReply |= reply
            if reply:
                changedRids.append(rid)

        # We need to derive instances for any declined using an EXDATE
        for decline in sorted(declines):
            overridden = self.newCalendar.overriddenComponent(decline)
            if not overridden:
                overridden = self.newCalendar.deriveInstance(decline)
                if overridden:
                    self.newCalendar.addComponent(overridden)
                    if self._attendeeDecline(overridden):
                        changeCausesReply = True
                        changedRids.append(decline)
                else:
                    log.debug("Unable to override and instance to mark as DECLINED: %s" % (decline,))
                    return False, False, (), None

        return True, changeCausesReply, changedRids, self.newCalendar

    def _checkVCALENDARProperties(self, serverData, clientData):

        self._transferProperty("X-CALENDARSERVER-ACCESS", serverData, clientData)

        # Get property differences in the VCALENDAR objects
        propdiff = set(serverData.properties()) ^ set(clientData.properties())
        
        # Ignore certain properties
        ignored = ("PRODID", "CALSCALE",)
        propdiff = set([prop for prop in propdiff if prop.name() not in ignored])
        
        result = len(propdiff) == 0
        if not result:
            log.debug("VCALENDAR properties differ: %s" % (propdiff,))
        return result

    def _transferAttendeeData(self, serverComponent, clientComponent, declines):
        
        # First check validity of date-time related properties
        if not self._checkInvalidChanges(serverComponent, clientComponent, declines):
            return False, False
        
        # Now look for items to transfer from one to the other.
        # We care about the ATTENDEE's PARTSTAT, TRANSP, VALARMS, X-APPLE-NEEDS-REPLY,
        # DTSTAMP, LAST-MODIFIED, and ATTACH's referring to a dropbox
        
        replyNeeded = False

        # ATTENDEE/PARTSTAT/RSVP
        serverAttendee = serverComponent.getAttendeeProperty((self.attendee,))
        clientAttendee = clientComponent.getAttendeeProperty((self.attendee,))
        if serverAttendee.params().get("PARTSTAT", ("NEEDS-ACTION",))[0] != clientAttendee.params().get("PARTSTAT", ("NEEDS-ACTION",))[0]:
            serverAttendee.params()["PARTSTAT"] = clientAttendee.params().get("PARTSTAT", "NEEDS-ACTION")
            replyNeeded = True
        if serverAttendee.params().get("RSVP", ("FALSE",))[0] != clientAttendee.params().get("RSVP", ("FALSE",))[0]:
            if clientAttendee.params().get("RSVP", ("FALSE",))[0] == "FALSE":
                try:
                    del serverAttendee.params()["RSVP"]
                except KeyError:
                    pass
            else:
                serverAttendee.params()["RSVP"] = ["TRUE",]

        # Transfer these properties from the client data
        replyNeeded |= self._transferProperty("X-CALENDARSERVER-PRIVATE-COMMENT", serverComponent, clientComponent)
        self._transferProperty("TRANSP", serverComponent, clientComponent)
        self._transferProperty("DTSTAMP", serverComponent, clientComponent)
        self._transferProperty("LAST-MODIFIED", serverComponent, clientComponent)
        self._transferProperty("X-APPLE-NEEDS-REPLY", serverComponent, clientComponent)
        
        # Dropbox
        if not self._transferDropBoxData(serverComponent, clientComponent):
            return False, False

        # Handle VALARMs
        serverComponent.removeAlarms()
        for comp in clientComponent.subcomponents():
            if comp.name() == "VALARM":
                serverComponent.addComponent(comp)
        
        return True, replyNeeded
    
    def _transferDropBoxData(self, serverComponent, clientComponent):
        
        serverDropbox = serverComponent.propertyValue("X-APPLE-DROPBOX")
        clientDropbox = clientComponent.propertyValue("X-APPLE-DROPBOX")
        
        # Handle four cases
        if not clientDropbox:
            return True
        elif not serverDropbox:
            # Attendee not allowed to add a dropbox
            log.debug("Attendee not allowed to add dropbox: %s" % (clientDropbox,))
            return False
        else:
            # Values must be the same
            if serverDropbox != clientDropbox:
                log.debug("Attendee not allowed to change dropbox from: %s to: %s" % (serverDropbox, clientDropbox,))
                return False

            # Remove existing ATTACH's from server
            for attachment in tuple(serverComponent.properties("ATTACH")):
                valueType = attachment.paramValue("VALUE")
                if valueType in (None, "URI"):
                    dataValue = attachment.value()
                    if dataValue.find(serverDropbox) != -1:
                        serverComponent.removeProperty(attachment)
        
            # Copy new ATTACH's to server
            for attachment in tuple(clientComponent.properties("ATTACH")):
                valueType = attachment.paramValue("VALUE")
                if valueType in (None, "URI"):
                    dataValue = attachment.value()
                    if dataValue.find(serverDropbox) != -1:
                        serverComponent.addProperty(attachment)
                        
            return True
        
    def _checkInvalidChanges(self, serverComponent, clientComponent, declines):
        
        # Properties we care about: DTSTART, DTEND, DURATION, RRULE, RDATE, EXDATE
        
        serverProps = self._getNormalizedDateTimeProperties(serverComponent)
        clientProps = self._getNormalizedDateTimeProperties(clientComponent)
        
        # Need to special case EXDATEs as an Attendee can effectively DECLINE by adding an EXDATE
        if serverProps[:-1] != clientProps[:-1]:
            invalidChanges = []
            propNames = ("DTSTART", "DTEND", "RRULE", "RDATE", "EXDATE")
            invalidChanges = [propName for ctr, propName in enumerate(propNames) if serverProps[ctr] != clientProps[ctr]]
            log.debug("Critical properties do not match: %s" % (", ".join(invalidChanges),))
            return False
        elif serverProps[-1] != clientProps[-1]:
            # Bad if EXDATEs have been removed
            missing = serverProps[-1] - clientProps[-1]
            if missing:
                log.debug("EXDATEs missing: %s" % (", ".join([toString(exdate) for exdate in missing]),))
                return False
            declines.extend(clientProps[-1] - serverProps[-1])
            return True
        else:
            return True
        
    def _getNormalizedDateTimeProperties(self, component):
        
        # Basic time properties
        dtstart = component.getProperty("DTSTART")
        dtend = component.getProperty("DTEND")
        duration = component.getProperty("DURATION")
        
        newdtstart, newdtend = normalizeStartEndDuration(
            dtstart.value(),
            dtend.value() if dtend is not None else None,
            duration.value() if duration is not None else None,
        )
        
        # Recurrence rules - we need to normalize the order of the value parts
        newrrules = set()
        rrules = component.properties("RRULE")
        for rrule in rrules:
            indexedTokens = {}
            indexedTokens.update([valuePart.split("=") for valuePart in rrule.value().split(";")])
            sortedValue = ";".join(["%s=%s" % (key, value,) for key, value in sorted(indexedTokens.iteritems(), key=lambda x:x[0])])
            newrrules.add(sortedValue)
        
        # RDATEs
        newrdates = set()
        rdates = component.properties("RDATE")
        for rdate in rdates:
            newrdates.update([normalizeToUTC(value) for value in rdate.value()])
        
        # EXDATEs
        newexdates = set()
        exdates = component.properties("EXDATE")
        for exdate in exdates:
            newexdates.update([normalizeToUTC(value) for value in exdate.value()])

        return newdtstart, newdtend, newrrules, newrdates, newexdates

    def _transferProperty(self, propName, serverComponent, clientComponent):

        changed = False
        serverProp = serverComponent.getProperty(propName)
        clientProp = clientComponent.getProperty(propName)
        if serverProp != clientProp:
            if clientProp:
                serverComponent.replaceProperty(Property(propName, clientProp.value()))
            else:
                serverComponent.removeProperty(serverProp)
            changed = True
        return changed


    def _attendeeDecline(self, component):
        """
        Marke attendee as DECLINED in the component.

        @param component:
        @type component:
        
        @return: C{bool} indicating whether the PARTSTAT value was in fact changed
        """
        attendee = component.getAttendeeProperty((self.attendee,))
        partstatChanged = attendee.params().get("PARTSTAT", ("NEEDS-ACTION",))[0] != "DECLINED"
        attendee.params()["PARTSTAT"] = ["DECLINED",]
        try:
            del attendee.params()["RSVP"]
        except KeyError:
            pass
        prop = component.getProperty("X-APPLE-NEEDS-REPLY")
        if prop:
            component.removeProperty(prop)
        return partstatChanged

    def whatIsDifferent(self):
        """
        Compare the two calendar objects in their entirety and return a list of properties
        and PARTSTAT parameters that are different.
        """

        # Do straight comparison without alarms
        self.calendar1 = self._attendeeDuplicateAndNormalize(self.calendar1)
        self.calendar2 = self._attendeeDuplicateAndNormalize(self.calendar2)

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
        
        props_changed = {}
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

    def _attendeeDuplicateAndNormalize(self, calendar):
        calendar = calendar.duplicate()
        calendar.normalizePropertyValueLists("EXDATE")
        calendar.removePropertyParameters("ORGANIZER", ("SCHEDULE-STATUS",))
        calendar.normalizeAll()
        calendar.normalizeAttachments()
        iTipGenerator.prepareSchedulingMessage(calendar, reply=True)
        return calendar

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
        addedChanges = False
        
        for prop in propdiff:
            if prop.name() in (
                "TRANSP",
                "DTSTAMP",
                "CREATED",
                "LAST-MODIFIED",
                "SEQUENCE",
                "X-CALENDARSERVER-PRIVATE-COMMENT",
            ):
                continue
            changed.setdefault(prop.name(), set())
            addedChanges = True
            prop1s = tuple(comp1.properties(prop.name()))
            prop2s = tuple(comp2.properties(prop.name()))
            if len(prop1s) == 1 and len(prop2s) == 1:
                param1s = set(["%s=%s" % (name, value) for name, value in prop1s[0].params().iteritems()])
                param2s = set(["%s=%s" % (name, value) for name, value in prop2s[0].params().iteritems()])
                paramDiffs = param1s ^ param2s
                changed[prop.name()].update([param.split("=")[0] for param in paramDiffs])
        
        if addedChanges:
            rid = comp1.getRecurrenceIDUTC()
            rids.add(toString(rid) if rid is not None else "")

    def _logDiffError(self, title):

        diff = "\n".join(unified_diff(
            str(self.calendar1).split("\n"),
            str(self.calendar2).split("\n"),
            fromfile='Existing Calendar Object',
            tofile='New Calendar Object',
        ))
        log.debug("%s:\n%s" % (title, diff,))
