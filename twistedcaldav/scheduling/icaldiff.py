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

from twext.python.log import Logger

from twistedcaldav.config import config
from twistedcaldav.ical import Component, Property
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.scheduling.itip import iTipGenerator
from twistedcaldav import accounting

from difflib import unified_diff
from pycalendar.period import PyCalendarPeriod
from pycalendar.datetime import PyCalendarDateTime

"""
Class that handles diff'ing two calendar objects.
"""

__all__ = [
    "iCalDiff",
]

log = Logger()

class iCalDiff(object):
    
    def __init__(self, oldcalendar, newcalendar, smart_merge):
        """
        
        @param oldcalendar:
        @type oldcalendar:
        @param newcalendar:
        @type newcalendar:
        """
        
        self.oldcalendar = oldcalendar
        self.newcalendar = newcalendar
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
            calendar.removeXProperties(keep_properties=(
                "X-APPLE-DROPBOX",
            ))
            calendar.removePropertyParameters("ATTENDEE", ("RSVP", "SCHEDULE-STATUS", "SCHEDULE-FORCE-SEND",))
            calendar.normalizeAll()
            return calendar
        
        # Normalize components for comparison
        oldcalendar_norm = duplicateAndNormalize(self.oldcalendar)
        newcalendar_norm = duplicateAndNormalize(self.newcalendar)

        result = oldcalendar_norm == newcalendar_norm
        return result

    def _organizerMerge(self):
        """
        Merge changes to ATTENDEE properties in oldcalendar into newcalendar.
        """
        organizer = normalizeCUAddr(self.newcalendar.masterComponent().propertyValue("ORGANIZER"))
        self._doSmartMerge(organizer, True)

    def _doSmartMerge(self, ignore_attendee, is_organizer):
        """
        Merge changes to ATTENDEE properties in oldcalendar into newcalendar.
        """
        
        old_master = self.oldcalendar.masterComponent()
        new_master = self.newcalendar.masterComponent()
        
        # Do master merge first
        self._tryComponentMerge(old_master, new_master, ignore_attendee, is_organizer)

        # New check the matching components
        for old_component in self.oldcalendar.subcomponents():
            
            # Make sure we have an appropriate component
            if old_component.name() == "VTIMEZONE":
                continue
            rid = old_component.getRecurrenceIDUTC()
            if rid is None:
                continue

            # Find matching component in new calendar
            new_component = self.newcalendar.overriddenComponent(rid)
            if new_component is None:
                # If the old component was cancelled ignore when an attendee
                if not is_organizer and old_component.propertyValue("STATUS") == "CANCELLED":
                    continue
                
                # Determine whether the instance is still valid in the new calendar
                new_component = self.newcalendar.deriveInstance(rid)
                if new_component:
                    # Derive a new instance from the new calendar and transfer attendee status
                    self.newcalendar.addComponent(new_component)
                    self._tryComponentMerge(old_component, new_component, ignore_attendee, is_organizer)
                else:
                    # Ignore the old instance as it no longer exists
                    pass
            else:
                self._tryComponentMerge(old_component, new_component, ignore_attendee, is_organizer)

        # Check the new instances not in the old calendar
        for new_component in self.newcalendar.subcomponents():
            
            # Make sure we have an appropriate component
            if new_component.name() == "VTIMEZONE":
                continue
            rid = new_component.getRecurrenceIDUTC()
            if rid is None:
                continue

            # Find matching component in old calendar
            old_component = self.oldcalendar.overriddenComponent(rid)
            if old_component is None:
                # If the new component is cancelled ignore when an attendee
                if not is_organizer and new_component.propertyValue("STATUS") == "CANCELLED":
                    continue
                
                # Try to derive a new instance in the client and transfer attendee status
                old_component = self.oldcalendar.deriveInstance(rid)
                if old_component:
                    self.oldcalendar.addComponent(old_component)
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
            
            # Whenever SCHEDULE-FORCE-SEND is explicitly set by the Organizer we assume the Organizer
            # is deliberately overwriting PARTSTAT
            if new_attendee.parameterValue("SCHEDULE-FORCE-SEND", "") == "REQUEST":
                continue

            # Transfer parameters from any old Attendees found
            value = normalizeCUAddr(new_attendee.value())
            old_attendee = old_attendees.get(value)
            if old_attendee:
                self._transferParameter(old_attendee, new_attendee, "PARTSTAT")
                self._transferParameter(old_attendee, new_attendee, "RSVP")
                self._transferParameter(old_attendee, new_attendee, "SCHEDULE-STATUS")
    
    def _transferParameter(self, old_property, new_property, parameter):
        paramvalue = old_property.parameterValue(parameter)
        if paramvalue is None:
            try:
                new_property.removeParameter(parameter)
            except KeyError:
                pass
        else:
            new_property.setParameter(parameter, paramvalue)

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

        if config.MaxInstancesForRRULE != 0:
            try:
                self.oldcalendar.truncateRecurrence(config.MaxInstancesForRRULE)
            except (ValueError, TypeError), ex:
                log.err("Cannot truncate calendar resource: %s" % (ex,))

        self.newCalendar = self.oldcalendar.duplicate()
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
            exdates = None
            if master:
                # Get all EXDATEs in UTC
                exdates = set()
                for exdate in master.properties("EXDATE"):
                    exdates.update([value.getValue().duplicate().adjustToUTC() for value in exdate.value()])
               
            return exdates, map, master
        
        exdatesold, mapold, masterold = mapComponents(self.oldcalendar)
        setold = set(mapold.keys())
        exdatesnew, mapnew, masternew = mapComponents(self.newcalendar)
        setnew = set(mapnew.keys())

        # Handle case where iCal breaks events without a master component
        if masternew is not None and masterold is None:
            masternewStart = masternew.getStartDateUTC()
            keynew = (masternew.name(), masternew.propertyValue("UID"), masternewStart)
            if keynew not in setold:
                # The DTSTART in the fake master does not match a RECURRENCE-ID in the real data.
                # We have to do a brute force search for the component that matches based on DTSTART
                for componentold in self.oldcalendar.subcomponents():
                    if componentold.name() == "VTIMEZONE":
                        continue
                    if masternewStart == componentold.getStartDateUTC():
                        break
                else:
                    # Nothing matches - this has to be treated as an error
                    self._logDiffError("attendeeMerge: Unable to match fake master component: %s" % (keynew,))
                    return False, False, (), None
            else:
                componentold = self.oldcalendar.overriddenComponent(masternewStart)
            
            # Take the recurrence ID from component1 and fix map2/set2
            keynew = (masternew.name(), masternew.propertyValue("UID"), None)
            componentnew = mapnew[keynew]
            del mapnew[keynew]
            
            ridold = componentold.getRecurrenceIDUTC()
            newkeynew = (masternew.name(), masternew.propertyValue("UID"), ridold)
            mapnew[newkeynew] = componentnew
            setnew.remove(keynew)
            setnew.add(newkeynew)
    
        # All the components in oldcalendar must be in newcalendar unless they are CANCELLED
        for key in setold - setnew:
            _ignore_name, _ignore_uid, rid = key
            component = mapold[key]
            if component.propertyValue("STATUS") != "CANCELLED":
                # Attendee may decline by EXDATE'ing an instance - we need to handle that
                if exdatesnew is None or rid in exdatesnew:
                    # Mark Attendee as DECLINED in the server instance
                    if self._attendeeDecline(self.newCalendar.overriddenComponent(rid)):
                        changeCausesReply = True
                        changedRids.append(rid.getText() if rid else "")
                else:
                    # We used to generate a 403 here - but instead we now ignore this error and let the server data
                    # override the client
                    self._logDiffError("attendeeMerge: Missing uncancelled component from first calendar: %s" % (key,))
            else: 
                if exdatesnew is not None and rid not in exdatesnew:
                    # We used to generate a 403 here - but instead we now ignore this error and let the server data
                    # override the client
                    self._logDiffError("attendeeMerge: Missing EXDATE for cancelled components from first calendar: %s" % (key,))
                else:
                    # Remove the CANCELLED component from the new calendar and add an EXDATE
                    overridden = self.newCalendar.overriddenComponent(rid)
                    self.newCalendar.removeComponent(overridden)
                    if self.newMaster:
                        # Use the original R-ID value so we preserve the timezone
                        original_rid = component.propertyValue("RECURRENCE-ID")
                        self.newMaster.addProperty(Property("EXDATE", [original_rid,]))
        
        # Derive a new component in the new calendar for each new one in setnew
        for key in setnew - setold:
            
            # First check if the attendee's copy is cancelled and properly EXDATE'd
            # and skip it if so.
            _ignore_name, _ignore_uid, rid = key
            componentnew = mapnew[key]
            if componentnew.propertyValue("STATUS") == "CANCELLED":
                if exdatesold is None or rid not in exdatesold:
                    # We used to generate a 403 here - but instead we now ignore this error and let the server data
                    # override the client
                    self._logDiffError("attendeeMerge: Cancelled component not found in first calendar (or no EXDATE): %s" % (key,))
                    setnew.remove(key)
                else:
                    # Derive new component with STATUS:CANCELLED and remove EXDATE
                    newOverride = self.newCalendar.deriveInstance(rid, allowCancelled=True)
                    if newOverride is None:
                        # We used to generate a 403 here - but instead we now ignore this error and let the server data
                        # override the client
                        self._logDiffError("attendeeMerge: Could not derive instance for cancelled component: %s" % (key,))
                        setnew.remove(key)
                    else:
                        self.newCalendar.addComponent(newOverride)
            else:
                # Derive new component
                newOverride = self.newCalendar.deriveInstance(rid)
                if newOverride is None:
                    # We used to generate a 403 here - but instead we now ignore this error and let the server data
                    # override the client
                    self._logDiffError("attendeeMerge: Could not derive instance for uncancelled component: %s" % (key,))
                    setnew.remove(key)
                else:
                    self.newCalendar.addComponent(newOverride)

        # So now newCalendar has all the same components as set2. Check changes and do transfers.
        
        # Make sure the same VCALENDAR properties match
        if not self._checkVCALENDARProperties(self.newCalendar, self.newcalendar):
            # We used to generate a 403 here - but instead we now ignore this error and let the server data
            # override the client
            self._logDiffError("attendeeMerge: VCALENDAR properties do not match")

        # Now we transfer per-Attendee
        # data from newcalendar into newCalendar to sync up changes, whilst verifying that other
        # key properties are unchanged
        declines = []
        for key in setnew:
            _ignore_name, _ignore_uid, rid = key
            serverData = self.newCalendar.overriddenComponent(rid)
            clientData = mapnew[key]
            
            allowed, reply = self._transferAttendeeData(serverData, clientData, declines)
            if not allowed:
                # We used to generate a 403 here - but instead we now ignore this error and let the server data
                # override the client
                self._logDiffError("attendeeMerge: Mismatched calendar objects")
                #return False, False, (), None
            changeCausesReply |= reply
            if reply:
                changedRids.append(rid.getText() if rid else "")

        # We need to derive instances for any declined using an EXDATE
        for decline in sorted(declines):
            overridden = self.newCalendar.overriddenComponent(decline)
            if not overridden:
                overridden = self.newCalendar.deriveInstance(decline)
                if overridden:
                    self.newCalendar.addComponent(overridden)
                    if self._attendeeDecline(overridden):
                        changeCausesReply = True
                        changedRids.append(decline.getText() if decline else "")
                else:
                    self._logDiffError("attendeeMerge: Unable to override an instance to mark as DECLINED: %s" % (decline,))
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
        
        # We are skipping this check now - instead we let the server data override the broken client data
        # First check validity of date-time related properties and get removed components which are declines
        self._checkInvalidChanges(serverComponent, clientComponent, declines)
        
        # Now look for items to transfer from one to the other.
        # We care about the ATTENDEE's PARTSTAT, TRANSP, VALARMS, X-APPLE-NEEDS-REPLY,
        # DTSTAMP, LAST-MODIFIED, COMPLETED, and ATTACH's referring to a dropbox
        
        replyNeeded = False

        # ATTENDEE/PARTSTAT/RSVP
        serverAttendee = serverComponent.getAttendeeProperty((self.attendee,))
        clientAttendee = clientComponent.getAttendeeProperty((self.attendee,))
        if serverAttendee.parameterValue("PARTSTAT", "NEEDS-ACTION") != clientAttendee.parameterValue("PARTSTAT", "NEEDS-ACTION"):
            serverAttendee.setParameter("PARTSTAT", clientAttendee.parameterValue("PARTSTAT", "NEEDS-ACTION"))
            replyNeeded = True
        if serverAttendee.parameterValue("RSVP", "FALSE") != clientAttendee.parameterValue("RSVP", "FALSE"):
            if clientAttendee.parameterValue("RSVP", "FALSE") == "FALSE":
                try:
                    serverAttendee.removeParameter("RSVP")
                except KeyError:
                    pass
            else:
                serverAttendee.setParameter("RSVP", "TRUE")

        # Transfer these properties from the client data
        replyNeeded |= self._transferProperty("X-CALENDARSERVER-PRIVATE-COMMENT", serverComponent, clientComponent)
        self._transferProperty("TRANSP", serverComponent, clientComponent)
        self._transferProperty("DTSTAMP", serverComponent, clientComponent)
        self._transferProperty("LAST-MODIFIED", serverComponent, clientComponent)
        self._transferProperty("X-APPLE-NEEDS-REPLY", serverComponent, clientComponent)
        self._transferProperty("COMPLETED", serverComponent, clientComponent)
        
        # Dropbox - this now never returns false
        self._transferDropBoxData(serverComponent, clientComponent)

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
            # Attendee not allowed to add a dropbox - ignore this
            self._logDiffError("Attendee not allowed to add dropbox: %s" % (clientDropbox,))
            return True
        else:
            # Values must be the same - ignore this
            if serverDropbox != clientDropbox:
                self._logDiffError("Attendee not allowed to change dropbox from: %s to: %s" % (serverDropbox, clientDropbox,))
                return True

            # Remove existing ATTACH's from server
            for attachment in tuple(serverComponent.properties("ATTACH")):
                valueType = attachment.parameterValue("VALUE")
                if valueType in (None, "URI"):
                    dataValue = attachment.value()
                    if dataValue.find(serverDropbox) != -1:
                        serverComponent.removeProperty(attachment)
        
            # Copy new ATTACH's to server
            for attachment in tuple(clientComponent.properties("ATTACH")):
                valueType = attachment.parameterValue("VALUE")
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
            propNames = ("DTSTART", "DTEND", "DUE", "RRULE", "RDATE", "EXDATE")
            invalidChanges = [propName for ctr, propName in enumerate(propNames) if serverProps[ctr] != clientProps[ctr]]
            log.debug("Critical properties do not match: %s" % (", ".join(invalidChanges),))
            return False
        elif serverProps[-1] != clientProps[-1]:
            # Bad if EXDATEs have been removed
            missing = serverProps[-1] - clientProps[-1]
            if missing:
                log.debug("EXDATEs missing: %s" % (", ".join([exdate.getText() for exdate in missing]),))
                return False
            declines.extend(clientProps[-1] - serverProps[-1])
            return True
        else:
            return True
        
    def _getNormalizedDateTimeProperties(self, component):
        
        # Basic time properties
        if component.name() in ("VEVENT", "VJOURNAL",):
            dtstart = component.getProperty("DTSTART")
            dtend = component.getProperty("DTEND")
            duration = component.getProperty("DURATION")
            
            timeRange = PyCalendarPeriod(
                start    = dtstart.value()  if dtstart  is not None else None,
                end      = dtend.value()    if dtend    is not None else None,
                duration = duration.value() if duration is not None else None,
            )
            newdue = None
            
        elif component.name() == "VTODO":
            dtstart = component.getProperty("DTSTART")
            duration = component.getProperty("DURATION")
            
            if dtstart or duration:
                timeRange = PyCalendarPeriod(
                    start    = dtstart.value()  if dtstart  is not None else None,
                    duration = duration.value() if duration is not None else None,
                )
            else:
                timeRange = PyCalendarPeriod()

            newdue = component.getProperty("DUE")
            if newdue is not None:
                newdue = newdue.value().duplicate().adjustToUTC()
            
        # Recurrence rules - we need to normalize the order of the value parts
        newrrules = set()
        rrules = component.properties("RRULE")
        for rrule in rrules:
            indexedTokens = {}
            indexedTokens.update([valuePart.split("=") for valuePart in rrule.value().getText().split(";")])
            sortedValue = ";".join(["%s=%s" % (key, value,) for key, value in sorted(indexedTokens.iteritems(), key=lambda x:x[0])])
            newrrules.add(sortedValue)
        
        # RDATEs
        newrdates = set()
        rdates = component.properties("RDATE")
        for rdate in rdates:
            for value in rdate.value():
                if isinstance(PyCalendarDateTime()):
                    value = value.duplicate().adjustToUTC()
                newrdates.add(value)
        
        # EXDATEs
        newexdates = set()
        exdates = component.properties("EXDATE")
        for exdate in exdates:
            newexdates.update([value.getValue().duplicate().adjustToUTC() for value in exdate.value()])

        return timeRange.getStart(), timeRange.getEnd(), newdue, newrrules, newrdates, newexdates

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
        Mark attendee as DECLINED in the component.

        @param component:
        @type component:
        
        @return: C{bool} indicating whether the PARTSTAT value was in fact changed
        """
        attendee = component.getAttendeeProperty((self.attendee,))
        partstatChanged = attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") != "DECLINED"
        attendee.setParameter("PARTSTAT", "DECLINED")
        prop = component.getProperty("X-APPLE-NEEDS-REPLY")
        if prop:
            component.removeProperty(prop)
        return partstatChanged

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
        
        rids = {}

        oldmap = mapComponents(self.oldcalendar)
        oldset = set(oldmap.keys())
        newmap = mapComponents(self.newcalendar)
        newset = set(newmap.keys())

        # Now verify that each component in oldset matches what is in newset
        for key in (oldset & newset):
            component1 = oldmap[key]
            component2 = newmap[key]
            self._diffComponents(component1, component2, rids)
        
        # Now verify that each additional component in oldset matches a derived component in newset
        for key in oldset - newset:
            oldcomponent = oldmap[key]
            newcomponent = self.newcalendar.deriveInstance(key[2])
            if newcomponent is None:
                continue
            self._diffComponents(oldcomponent, newcomponent, rids)
        
        # Now verify that each additional component in oldset matches a derived component in newset
        for key in newset - oldset:
            oldcomponent = self.oldcalendar.deriveInstance(key[2])
            if oldcomponent is None:
                continue
            newcomponent = newmap[key]
            self._diffComponents(oldcomponent, newcomponent, rids)
        
        return rids

    def _componentDuplicateAndNormalize(self, comp):
        comp = comp.duplicate()
        comp.normalizePropertyValueLists("EXDATE")
        comp.removePropertyParameters("ORGANIZER", ("SCHEDULE-STATUS",))
        comp.removePropertyParameters("ATTENDEE", ("SCHEDULE-STATUS", "SCHEDULE-FORCE-SEND",))
        comp.removeAlarms()
        comp.normalizeAll()
        comp.normalizeAttachments()
        iTipGenerator.prepareSchedulingMessage(comp, reply=True)
        return comp

    def _diffComponents(self, comp1, comp2, rids):
        
        assert isinstance(comp1, Component) and isinstance(comp2, Component)
        
        if comp1.name() != comp2.name():
            log.debug("Component names are different: '%s' and '%s'" % (comp1.name(), comp2.name()))
            return
        
        # Duplicate then normalize for comparison
        comp1 = self._componentDuplicateAndNormalize(comp1)
        comp2 = self._componentDuplicateAndNormalize(comp2)

        # Diff all the properties
        propdiff = set(comp1.properties()) ^ set(comp2.properties())
        addedChanges = False
        
        propsChanged = {}
        for prop in propdiff:
            if prop.name() in (
                "TRANSP",
                "DTSTAMP",
                "CREATED",
                "LAST-MODIFIED",
                "X-CALENDARSERVER-PRIVATE-COMMENT",
            ):
                continue
            propsChanged.setdefault(prop.name(), set())
            addedChanges = True
            prop1s = tuple(comp1.properties(prop.name()))
            prop2s = tuple(comp2.properties(prop.name()))
            if len(prop1s) == 1 and len(prop2s) == 1:
                param1s = set(["%s=%s" % (name, prop1s[0].parameterValue(name)) for name in prop1s[0].parameterNames()])
                param2s = set(["%s=%s" % (name, prop2s[0].parameterValue(name)) for name in prop2s[0].parameterNames()])
                paramDiffs = param1s ^ param2s
                propsChanged[prop.name()].update([param.split("=")[0] for param in paramDiffs])
            if "_TZID" in propsChanged[prop.name()]:
                propsChanged[prop.name()].remove("_TZID")
                propsChanged[prop.name()].add("TZID")
        
        if addedChanges:
            rid = comp1.getRecurrenceIDUTC()
            rids[rid.getText() if rid is not None else ""] = propsChanged

    def _logDiffError(self, title):

        strcal1 = str(self.oldcalendar)
        strcal2 = str(self.newcalendar)
        strdiff = "\n".join(unified_diff(
            strcal1.split("\n"),
            strcal2.split("\n"),
            fromfile='Existing Calendar Object',
            tofile='New Calendar Object',
        ))
        
        logstr = """%s

------ Existing Calendar Data ------
%s
------ New Calendar Data ------
%s
------ Diff ------
%s
""" % (title, strcal1, strcal2, strdiff,)

        loggedUID = self.oldcalendar.resourceUID()
        if loggedUID:
            loggedUID = loggedUID.encode("base64")[:-1]
        else:
            loggedUID = "Unknown"
        loggedName = accounting.emitAccounting("Implicit Errors", loggedUID, logstr)
        if loggedName:
            log.err("Generating Implicit Error accounting at path: %s" % (loggedName,))
