##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
iTIP (RFC5546) scheduling message processing and generation.


This is currently used for handling auto-replies to schedule requests arriving
in an inbox. It is called in a delayed fashion via reactor.callLater.

We assume that all the components/calendars we deal with have been determined
as being 'valid for CalDAV/iTIP', i.e. they contain UIDs, single component
types, etc.
"""


from twext.python.log import Logger

from twistedcaldav.config import config
from twistedcaldav.ical import Property, iCalendarProductID, Component, \
    ignoredComponents

from pycalendar.datetime import DateTime

log = Logger()

__all__ = [
    "iTipProcessing",
    "iTipGenerator",
]


class iTipProcessing(object):

    @staticmethod
    def processNewRequest(itip_message, recipient=None, creating=False):
        """
        Process a METHOD=REQUEST for a brand new calendar object (for creating set to C{True}. This is also
        called by L{processRequest} with creating set to C{False} to do some common update behavior.

        @param itip_message: the iTIP message to process.
        @type itip_message: L{Component}
        @param recipient: the attendee calendar user address to whom the message was sent
        @type recipient: C{str}
        @param creating: whether or not a new resource is being created
        @type creating: C{bool}

        @return: calendar object ready to save
        """
        assert itip_message.propertyValue("METHOD") == "REQUEST", "iTIP message must have METHOD:REQUEST"

        calendar = itip_message.duplicate()
        method = calendar.getProperty("METHOD")
        if method:
            calendar.removeProperty(method)

        if recipient:

            # Check for incoming DECLINED
            if creating:
                iTipProcessing.addTranspForNeedsAction(calendar.subcomponents(), recipient)

                master = calendar.masterComponent()
                for component in tuple(calendar.subcomponents()):
                    if component in ignoredComponents or component is master:
                        continue
                    attendee = component.getAttendeeProperty((recipient,))
                    if attendee and attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "DECLINED":
                        # Mark as hidden if we have a master, otherwise remove
                        if master is not None:
                            component.addProperty(Property(Component.HIDDEN_INSTANCE_PROPERTY, "T"))
                        else:
                            calendar.removeComponent(component)

        return calendar


    @staticmethod
    def processRequest(itip_message, calendar, recipient):
        """
        Process a METHOD=REQUEST. We need to merge per-attendee properties such as TRANPS, COMPLETED etc
        with the data coming from the organizer.

        @param itip_message: the iTIP message to process.
        @type itip_message: L{Component}
        @param calendar: the calendar object to apply the REQUEST to
        @type calendar: L{Component}
        @param recipient: the attendee calendar user address to whom the message was sent
        @type recipient: C{str}

        @return: a C{tuple} of:
            calendar object ready to save, or C{None} (request should be ignored)
            a C{set} of recurrences that changed, or C{None}
        """

        # Check sequencing
        if not iTipProcessing.sequenceComparison(itip_message, calendar):
            # Ignore out of sequence message
            return None, None

        # Special check: if the SCHEDULE-AGENT is being changed throw away all the existing data
        if calendar.getOrganizerScheduleAgent() != itip_message.getOrganizerScheduleAgent():
            return (iTipProcessing.processNewRequest(itip_message, recipient, creating=True), {})

        # Merge Organizer data with Attendee's own changes (VALARMs, Comment only for now).
        from txdav.caldav.datastore.scheduling.icaldiff import iCalDiff
        differ = iCalDiff(calendar, itip_message, False)
        rids = differ.whatIsDifferent()
        needs_action_rids, reschedule = differ.attendeeNeedsAction(rids)

        # Different behavior depending on whether a master component is present or not
        # Here we cache per-attendee data from the existing master that we need to use in any new
        # overridden components that the organizer added
        current_master = calendar.masterComponent()
        if current_master:
            valarms = [comp for comp in current_master.subcomponents() if comp.name() == "VALARM"]
            private_comments = current_master.properties("X-CALENDARSERVER-PRIVATE-COMMENT")
            transps = current_master.properties("TRANSP")
            completeds = current_master.properties("COMPLETED")
            organizer = current_master.getProperty("ORGANIZER")
            organizer_schedule_status = organizer.parameterValue("SCHEDULE-STATUS", None) if organizer else None
            attendee = current_master.getAttendeeProperty((recipient,))
            attendee_dtstamp = attendee.parameterValue("X-CALENDARSERVER-DTSTAMP") if attendee else None
            other_props = {}
            for pname in config.Scheduling.CalDAV.PerAttendeeProperties:
                props = tuple(current_master.properties(pname))
                if props:
                    other_props[pname] = props
        else:
            valarms = ()
            private_comments = ()
            transps = ()
            completeds = ()
            organizer_schedule_status = None
            attendee = None
            attendee_dtstamp = None
            other_props = {}

        if itip_message.masterComponent() is not None:

            # Get a new calendar object first
            new_calendar = iTipProcessing.processNewRequest(itip_message, recipient)

            # Copy over master alarms, comments etc
            master_component = new_calendar.masterComponent()
            transfer_partstat = None not in needs_action_rids and not reschedule
            seq_change = Component.compareComponentsForITIP(master_component, current_master, use_dtstamp=False) <= 0 if current_master is not None else False
            iTipProcessing._transferItems(master_component, transfer_partstat and seq_change, valarms, private_comments, transps, completeds, organizer_schedule_status, attendee, attendee_dtstamp, other_props, recipient)

            # Now try to match recurrences in the new calendar
            for component in tuple(new_calendar.subcomponents()):
                if component.name() != "VTIMEZONE" and component.getRecurrenceIDUTC() is not None:
                    iTipProcessing.transferItems(calendar, component, needs_action_rids, reschedule, valarms, private_comments, transps, completeds, organizer_schedule_status, attendee, attendee_dtstamp, other_props, recipient)

            # Now try to match recurrences from the old calendar
            for component in calendar.subcomponents():
                if component.name() != "VTIMEZONE" and component.getRecurrenceIDUTC() is not None:
                    rid = component.getRecurrenceIDUTC()
                    if new_calendar.overriddenComponent(rid) is None:
                        allowCancelled = component.propertyValue("STATUS") == "CANCELLED"
                        hidden = component.hasProperty(Component.HIDDEN_INSTANCE_PROPERTY)
                        new_component = new_calendar.deriveInstance(rid, allowCancelled=allowCancelled and not hidden)
                        if new_component is not None:
                            # If the new component is not CANCELLED then add the one derived from the new master and
                            # sync over attendee properties from the existing attendee data. However, if the new
                            # component is cancelled, we need to preserve the original state of the attendee's
                            # version as it may differ from the one derived from the new master.
                            if allowCancelled:
                                new_calendar.addComponent(component.duplicate())
                            else:
                                new_calendar.addComponent(new_component)
                                iTipProcessing.transferItems(calendar, new_component, needs_action_rids, reschedule, valarms, private_comments, transps, completeds, organizer_schedule_status, attendee, attendee_dtstamp, other_props, recipient)
                                if hidden:
                                    new_component.addProperty(Property(Component.HIDDEN_INSTANCE_PROPERTY, "T"))

            iTipProcessing.addTranspForNeedsAction(new_calendar.subcomponents(), recipient)

            # Replace the entire object
            return new_calendar, rids

        else:
            # Need existing tzids
            tzids = calendar.timezones()

            # Update existing instances
            for component in itip_message.subcomponents():
                if component.name() == "VTIMEZONE":
                    # May need to add a new VTIMEZONE
                    if component.propertyValue("TZID") not in tzids:
                        calendar.addComponent(component)
                else:
                    component = component.duplicate()
                    missingDeclined = iTipProcessing.transferItems(calendar, component, needs_action_rids, reschedule, valarms, private_comments, transps, completeds, organizer_schedule_status, attendee, attendee_dtstamp, other_props, recipient, remove_matched=True)
                    if not missingDeclined:
                        # Add the component and make sure to remove any matching EXDATE
                        calendar.addComponent(component)
                        if current_master is not None:
                            current_master.removeExdate(component.getRecurrenceIDUTC())

            iTipProcessing.addTranspForNeedsAction(calendar.subcomponents(), recipient)

            # Write back the modified object
            return calendar, rids


    @staticmethod
    def processCancel(itip_message, calendar, autoprocessing=False):
        """
        Process a METHOD=CANCEL.

        TODO: Yes, I am going to ignore RANGE= on RECURRENCE-ID for now...

        @param itip_message: the iTIP message to process.
        @type itip_message: L{Component}
        @param calendar: the calendar object to apply the CANCEL to
        @type calendar: L{Component}
        @param autoprocessing: whether or not auto-processing is occurring
        @type autoprocessing: C{bool}

        @return: C{tuple} of:
            C{bool} : C{True} if processed, C{False} if scheduling message should be ignored
            C{bool} : C{True} if calendar object should be deleted, C{False} otherwise
            C{set}  : set of Recurrence-IDs for cancelled instances, or C{None} if all cancelled
        """

        assert itip_message.propertyValue("METHOD") == "CANCEL", "iTIP message must have METHOD:CANCEL"
        assert itip_message.resourceUID() == calendar.resourceUID(), "UIDs must be the same to process iTIP message"

        # Check sequencing
        if not iTipProcessing.sequenceComparison(itip_message, calendar):
            # Ignore out of sequence message
            return False, False, None

        # Check to see if this is a cancel of the entire event
        if itip_message.masterComponent() is not None:
            if autoprocessing:
                # Delete the entire event off the auto-processed calendar
                return True, True, None
            else:
                # Cancel every instance in the existing event and sync over SEQUENCE
                calendar.replacePropertyInAllComponents(Property("STATUS", "CANCELLED"))
                newseq = itip_message.masterComponent().propertyValue("SEQUENCE")
                calendar.replacePropertyInAllComponents(Property("SEQUENCE", newseq))
                return True, False, None

        # iTIP CANCEL can contain multiple components being cancelled in the RECURRENCE-ID case.
        # So we need to iterate over each iTIP component.

        # Get the existing calendar master object if it exists
        calendar_master = calendar.masterComponent()
        exdates = []
        rids = set()

        # Look at each component in the iTIP message
        for component in itip_message.subcomponents():
            if component.name() == "VTIMEZONE":
                continue

            # Extract RECURRENCE-ID value from component
            rid = component.getRecurrenceIDUTC()
            rids.add(rid)

            # Get the one that matches in the calendar
            overridden = calendar.overriddenComponent(rid)

            if overridden:
                # We are cancelling an overridden component. Check to see if the existing override
                # is marked as hidden and if so remove it and add an EXDATE (also always do that if
                # auto-processing). Otherwise we will mark the override as cancelled so the attendee
                # can see what happened).
                hidden = overridden.hasProperty(Component.HIDDEN_INSTANCE_PROPERTY)

                if autoprocessing or hidden:
                    # Exclude the cancelled instance
                    exdates.append(component.getRecurrenceIDUTC())

                    # Remove the existing component.
                    calendar.removeComponent(overridden)
                else:
                    # Existing component is cancelled.
                    overridden.replaceProperty(Property("STATUS", "CANCELLED"))
                    newseq = component.propertyValue("SEQUENCE")
                    overridden.replaceProperty(Property("SEQUENCE", newseq))

            elif calendar_master:
                # We are trying to CANCEL a non-overridden instance.

                if autoprocessing:
                    # Exclude the cancelled instance
                    exdates.append(component.getRecurrenceIDUTC())
                else:
                    # Derive a new component and cancel it.
                    overridden = calendar.deriveInstance(rid)
                    if overridden is not None:
                        overridden.replaceProperty(Property("STATUS", "CANCELLED"))
                        calendar.addComponent(overridden)
                        newseq = component.propertyValue("SEQUENCE")
                        overridden.replaceProperty(Property("SEQUENCE", newseq))

        # If we have any EXDATEs lets add them to the existing calendar object.
        if exdates and calendar_master:
            for exdate in exdates:
                calendar_master.addExdate(exdate)

        # See if there are still components in the calendar - we might have deleted the last overridden instance
        # in which case the calendar object is empty (except for VTIMEZONEs) or has only hidden components.
        if calendar.mainType() is None or calendar.hasPropertyValueInAllComponents(Property(Component.HIDDEN_INSTANCE_PROPERTY, "T")):
            # Delete the now empty calendar object
            return True, True, None
        else:
            return True, False, rids


    @staticmethod
    def processReply(itip_message, calendar):
        """
        Process a METHOD=REPLY.

        TODO: Yes, I am going to ignore RANGE= on RECURRENCE-ID for now...
        TODO: We have no way to track SEQUENCE/DTSTAMP on a per-attendee basis to correctly serialize out-of-order
              replies.

        @param itip_message: the iTIP message to process.
        @type itip_message: L{Component}
        @param calendar: the calendar object to apply the REPLY to
        @type calendar: L{Component}

        @return: a C{tuple} of:
            C{True} if processed, C{False} if scheduling message should be ignored
            C{tuple} of change info
        """

        assert itip_message.propertyValue("METHOD") == "REPLY", "iTIP message must have METHOD:REPLY"
        assert itip_message.resourceUID() == calendar.resourceUID(), "UIDs must be the same to process iTIP message"

        # Take each component in the reply and update the corresponding component
        # in the organizer's copy (possibly generating new ones) so that the ATTENDEE
        # PARTSTATs match up.

        # Do the master first
        old_master = calendar.masterComponent()
        new_master = itip_message.masterComponent()
        attendees = set()
        rids = set()
        if new_master is not None and old_master is not None:
            attendee, partstat, private_comment = iTipProcessing.updateAttendeeData(new_master, old_master)
            if attendee:
                attendees.add(attendee)
                if partstat or private_comment:
                    rids.add(("", partstat, private_comment,))

        # Now do all overridden ones (sort by RECURRENCE-ID)
        sortedComponents = []
        for itip_component in itip_message.subcomponents():

            # Make sure we have an appropriate component
            if itip_component.name() == "VTIMEZONE":
                continue
            rid = itip_component.getRecurrenceIDUTC()
            if rid is None:
                continue
            sortedComponents.append((rid, itip_component,))

        sortedComponents.sort(key=lambda x: x[0])

        for rid, itip_component in sortedComponents:
            # Find matching component in organizer's copy
            match_component = calendar.overriddenComponent(rid)
            if match_component is None:
                # Attendee is overriding an instance themselves - we need to create a derived one
                # for the Organizer
                match_component = calendar.deriveInstance(rid)
                if match_component is not None:
                    calendar.addComponent(match_component)
                else:
                    log.error("Ignoring instance: %s in iTIP REPLY for: %s" % (rid, itip_message.resourceUID()))
                    continue

            attendee, partstat, private_comment = iTipProcessing.updateAttendeeData(itip_component, match_component)
            if attendee:
                attendees.add(attendee)
                if rids is not None and (partstat or private_comment):
                    rids.add((rid.getText(), partstat, private_comment,))

        # Check for an invalid instance by itself
        len_attendees = len(attendees)
        if len_attendees == 0:
            return False, None
        elif len_attendees == 1:
            return True, (attendees.pop(), rids)
        else:
            log.error("ATTENDEE property in a REPLY must be the same in all components\n%s" % (str(itip_message),))
            return False, None


    @staticmethod
    def updateAttendeeData(from_component, to_component):
        """
        Called when processing a REPLY only.

        Copy the PARTSTAT of the Attendee in the from_component to the matching ATTENDEE
        in the to_component. Ignore if no match found. Also update the private comments.

        For VPOLL we need to copy POLL-ITEM-ID response values into the actual matching
        polled sub-components as VOTER properties.

        @param from_component: component to copy from
        @type from_component: L{Component}
        @param to_component: component to copy to
        @type to_component: L{Component}
        """

        # Track what changed
        partstat_changed = False
        private_comment_changed = False

        # Get REQUEST-STATUS as we need to write that into the saved ATTENDEE property
        reqstatus = tuple(from_component.properties("REQUEST-STATUS"))
        if reqstatus:
            reqstatus = ",".join(status.value()[0] for status in reqstatus)
        else:
            reqstatus = "2.0"

        # Get attendee in from_component - there MUST be only one
        attendees = tuple(from_component.properties(from_component.recipientPropertyName()))
        if len(attendees) != 1:
            log.error("There must be one and only one ATTENDEE property in a REPLY\n%s" % (str(from_component),))
            return None, False, False

        attendee = attendees[0]
        partstat = attendee.parameterValue("PARTSTAT", "NEEDS-ACTION")

        # Now find matching ATTENDEE in to_component
        existing_attendee = to_component.getAttendeeProperty((attendee.value(),))
        if existing_attendee:
            oldpartstat = existing_attendee.parameterValue("PARTSTAT", "NEEDS-ACTION")
            existing_attendee.setParameter("PARTSTAT", partstat)
            existing_attendee.setParameter("SCHEDULE-STATUS", reqstatus)
            partstat_changed = (oldpartstat != partstat)

            # Always delete RSVP on PARTSTAT change
            if partstat_changed:
                try:
                    existing_attendee.removeParameter("RSVP")
                except KeyError:
                    pass

            # Handle attendee comments
            if config.Scheduling.CalDAV.get("EnablePrivateComments", True):
                # Look for X-CALENDARSERVER-PRIVATE-COMMENT property in iTIP component (State 1 in spec)
                attendee_comment = tuple(from_component.properties("X-CALENDARSERVER-PRIVATE-COMMENT"))
                attendee_comment = attendee_comment[0] if len(attendee_comment) else None

                # Look for matching X-CALENDARSERVER-ATTENDEE-COMMENT property in existing data (State 2 in spec)
                private_comments = tuple(to_component.properties("X-CALENDARSERVER-ATTENDEE-COMMENT"))
                for comment in private_comments:
                    attendeeref = comment.parameterValue("X-CALENDARSERVER-ATTENDEE-REF")
                    if attendeeref == attendee.value():
                        private_comment = comment
                        break
                else:
                    private_comment = None
            else:
                attendee_comment = None
                private_comment = None

            # Now do update logic
            if attendee_comment is None and private_comment is None:
                # Nothing to do
                pass

            elif attendee_comment is None and private_comment is not None:
                # We now remove the private comment on the organizer's side if the attendee removed it
                to_component.removeProperty(private_comment)

                private_comment_changed = True

            elif attendee_comment is not None and private_comment is None:

                # Add new property
                private_comment = Property(
                    "X-CALENDARSERVER-ATTENDEE-COMMENT",
                    attendee_comment.value(),
                    params={
                        "X-CALENDARSERVER-ATTENDEE-REF": attendee.value(),
                        "X-CALENDARSERVER-DTSTAMP": DateTime.getNowUTC().getText(),
                    }
                )
                to_component.addProperty(private_comment)

                private_comment_changed = True

            else:
                # Only change if different
                if private_comment.value() != attendee_comment.value():
                    # Remove all property parameters
                    private_comment.removeAllParameters()

                    # Add default parameters
                    private_comment.setParameter("X-CALENDARSERVER-ATTENDEE-REF", attendee.value())
                    private_comment.setParameter("X-CALENDARSERVER-DTSTAMP", DateTime.getNowUTC().getText())

                    # Set new value
                    private_comment.setValue(attendee_comment.value())

                    private_comment_changed = True

            # Do VPOLL transfer
            if from_component.name() == "VPOLL":
                # TODO: figure out how to report changes back
                iTipProcessing.updateVPOLLData(from_component, to_component, attendee)

        return attendee.value(), partstat_changed, private_comment_changed


    @staticmethod
    def updateVPOLLData(from_component, to_component, attendee):
        """
        Update VPOLL sub-components with voter's response.

        @param from_component: component to copy from
        @type from_component: L{Component}
        @param to_component: component to copy to
        @type to_component: L{Component}
        @param attendee: attendee being processed
        @type attendee: L{Property}
        """

        responses = {}
        for prop in from_component.properties("POLL-ITEM-ID"):
            responses[prop.value()] = prop

        for component in to_component.subcomponents():
            if component.name() in ignoredComponents:
                continue
            poll_item_id = component.propertyValue("POLL-ITEM-ID")
            if poll_item_id is None:
                continue
            voter = component.getVoterProperty((attendee.value(),))

            # If no response - remove
            if poll_item_id not in responses or not responses[poll_item_id].hasParameter("RESPONSE"):
                if voter is not None:
                    component.removeProperty(voter)
                continue

            # Add or update voter
            if voter is None:
                voter = Property("VOTER", attendee.value())
                component.addProperty(voter)
            voter.setParameter("RESPONSE", responses[poll_item_id].parameterValue("RESPONSE"))


    @staticmethod
    def transferItems(from_calendar, to_component, needs_action_rids, reschedule, valarms, private_comments, transps, completeds, organizer_schedule_status, attendee, attendee_dtstamp, other_props, recipient, remove_matched=False):
        """
        Transfer properties from a calendar to a component by first trying to match the component in the original calendar and
        use the properties from that, or use the values provided as arguments (which have been derived from the original calendar's
        master component).

        @param from_calendar: the old calendar data to transfer items from
        @type from_calendar: L{Component}
        @param to_component: the new component to transfer items to
        @type to_component: L{Component}
        @param valarms: a C{list} of VALARM components from the old master to use
        @type valarms: C{list}
        @param private_comments: a C{list} of private comment properties from the old master to use
        @type private_comments: C{list}
        @param transps: a C{list} of TRANSP properties from the old master to use
        @type transps: C{list}
        @param completeds: a C{list} of COMPLETED properties from the old master to use
        @type completeds: C{list}
        @param organizer_schedule_status: a the SCHEDULE-STATUS value for the organizer from the old master to use
        @type organizer_schedule_status: C{str}
        @param attendee_dtstamp: an the ATTENDEE DTSTAMP parameter value from the old master to use
        @type attendee_dtstamp: C{str}
        @param other_props: other properties from the old master to use
        @type other_props: C{list}
        @param recipient: the calendar user address of the attendee whose data is being processed
        @type recipient: C{str}
        @param remove_matched: whether or not to remove the matching component rather than transfer items
        @type remove_matched: C{bool}

        @return: C{True} if an EXDATE match occurred requiring the incoming component to be removed.
        """

        rid = to_component.getRecurrenceIDUTC()

        transfer_partstat = rid not in needs_action_rids and not reschedule

        # Is there a matching component
        matched = from_calendar.overriddenComponent(rid)
        if matched:
            valarms = [comp for comp in matched.subcomponents() if comp.name() == "VALARM"]
            private_comments = matched.properties("X-CALENDARSERVER-PRIVATE-COMMENT")
            transps = matched.properties("TRANSP")
            completeds = matched.properties("COMPLETED")
            organizer = matched.getProperty("ORGANIZER")
            organizer_schedule_status = organizer.parameterValue("SCHEDULE-STATUS", None) if organizer else None
            attendee = matched.getAttendeeProperty((recipient,))
            attendee_dtstamp = attendee.parameterValue("X-CALENDARSERVER-DTSTAMP") if attendee else None
            other_props = {}
            for pname in config.Scheduling.CalDAV.PerAttendeeProperties:
                props = tuple(matched.properties(pname))
                if props:
                    other_props[pname] = props

            seq_change = Component.compareComponentsForITIP(to_component, matched, use_dtstamp=False) <= 0
            iTipProcessing._transferItems(to_component, transfer_partstat and seq_change, valarms, private_comments, transps, completeds, organizer_schedule_status, attendee, attendee_dtstamp, other_props, recipient)

            # Check for incoming DECLINED
            to_attendee = to_component.getAttendeeProperty((recipient,))
            if to_attendee and to_attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "DECLINED":
                # If existing item has HIDDEN property copy that over
                if matched.hasProperty(Component.HIDDEN_INSTANCE_PROPERTY):
                    to_component.addProperty(Property(Component.HIDDEN_INSTANCE_PROPERTY, "T"))

            # Remove the old one
            if remove_matched:
                from_calendar.removeComponent(matched)

            # Check to see if the new component is cancelled as that could mean we are copying in the wrong attendee state
            if to_component.propertyValue("STATUS") == "CANCELLED":
                if attendee and to_attendee:
                    to_attendee.setParameter("PARTSTAT", attendee.parameterValue("PARTSTAT", "NEEDS-ACTION"))

        else:
            # Check for incoming DECLINED
            attendee = to_component.getAttendeeProperty((recipient,))
            if attendee and attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "DECLINED":
                return True

            master_component = from_calendar.masterComponent()
            seq_change = (Component.compareComponentsForITIP(to_component, master_component, use_dtstamp=False) <= 0) if master_component is not None else True
            iTipProcessing._transferItems(to_component, transfer_partstat and seq_change, valarms, private_comments, transps, completeds, organizer_schedule_status, attendee, attendee_dtstamp, other_props, recipient)

        return False


    @staticmethod
    def _transferItems(to_component, transfer_partstat, valarms, private_comments, transps, completeds, organizer_schedule_status, old_attendee, attendee_dtstamp, other_props, recipient):
        """
        Transfer properties the key per-attendee properties from one component to another. Note that the key properties are pulled out into separate items, because they
        may have been derived from the master.

        @param to_component: the new component to transfer items to
        @type to_component: L{Component}
        @param partstat_change: whether not to transfer the old PARTSTAT over
        @type partstat_change: C{bool}
        @param valarms: a C{list} of VALARM components from the old master to use
        @type valarms: C{list}
        @param private_comments: a C{list} of private comment properties from the old master to use
        @type private_comments: C{list}
        @param transps: a C{list} of TRANSP properties from the old master to use
        @type transps: C{list}
        @param completeds: a C{list} of COMPLETED properties from the old master to use
        @type completeds: C{list}
        @param organizer_schedule_status: a the SCHEDULE-STATUS value for the organizer from the old master to use
        @type organizer_schedule_status: C{str}
        @param attendee_dtstamp: an the ATTENDEE DTSTAMP parameter value from the old master to use
        @type attendee_dtstamp: C{str}
        @param other_props: other properties from the old master to use
        @type other_props: C{list}
        @param recipient: the calendar user address of the attendee whose data is being processed
        @type recipient: C{str}

        @return: C{True} if an EXDATE match occurred requiring the incoming component to be removed.
        """

        # It is a new override - copy any valarms on the existing master component
        # into the new one.
        [to_component.addComponent(alarm) for alarm in valarms]
        [to_component.addProperty(comment) for comment in private_comments]
        [to_component.replaceProperty(transp) for transp in transps]
        [to_component.replaceProperty(completed) for completed in completeds]

        if organizer_schedule_status:
            organizer = to_component.getProperty("ORGANIZER")
            if organizer:
                organizer.setParameter("SCHEDULE-STATUS", organizer_schedule_status)

        # ATTENDEE property merge
        attendee = to_component.getAttendeeProperty((recipient,))
        if old_attendee and attendee and transfer_partstat:
            iTipProcessing.mergePartStat(old_attendee, attendee)

        if attendee_dtstamp and attendee:
            attendee.setParameter("X-CALENDARSERVER-DTSTAMP", attendee_dtstamp)

        for props in other_props.values():
            [to_component.replaceProperty(prop) for prop in props]

        return False


    @staticmethod
    def mergePartStat(from_attendee, to_attendee):
        """
        Make sure the existing attendee PARTSTAT is preserved and also get rid of any RSVP
        if the new PARTSTAT is not NEEDS-ACTION.

        @param from_attendee: attendee property to copy PARTSTAT from
        @type from_attendee: L{twistedcaldav.ical.Property}
        @param to_attendee: attendee property to copy PARTSTAT to
        @type to_attendee: L{twistedcaldav.ical.Property}
        """

        preserve = from_attendee.parameterValue("PARTSTAT", "NEEDS-ACTION")
        if preserve != to_attendee.parameterValue("PARTSTAT", "NEEDS-ACTION"):
            to_attendee.setParameter("PARTSTAT", preserve)
        if preserve != "NEEDS-ACTION":
            to_attendee.removeParameter("RSVP")


    @staticmethod
    def addTranspForNeedsAction(components, recipient):
        """
        For each component where the ATTENDEE property of the recipient has PARTSTAT
        NEEDS-ACTION we add TRANSP:TRANSPARENT for VEVENTs.

        @param components: list of components to process
        @type components: C{list}
        @param recipient: calendar user address of attendee to process
        @type recipient: C{str}
        """

        for component in components:
            if component.name() != "VEVENT":
                continue
            attendee = component.getAttendeeProperty((recipient,))
            if attendee and attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "NEEDS-ACTION":
                component.replaceProperty(Property("TRANSP", "TRANSPARENT"))


    @staticmethod
    def sequenceComparison(itip, calendar):
        """
        Check the iTIP SEQUENCE values for the incoming iTIP message against the existing calendar data to determine
        whether the iTIP message is old and should be ignored.

        @param itip: the iTIP message to process
        @type itip: L{Component}
        @param calendar: the existing calendar data to compare with
        @type calendar: L{Component}

        @return: C{True} if the itip message is new and should be processed, C{False}
            if no processing is needed
        @rtype: C{bool}
        """

        # Master component comparison trumps all else
        itip_master = itip.masterComponent()
        cal_master = calendar.masterComponent()

        # If master component exists, compare all in iTIP and update if any are new
        if cal_master:
            for itip_component in itip.subcomponents():
                if itip_component.name() in ignoredComponents:
                    continue
                cal_component = calendar.overriddenComponent(itip_component.getRecurrenceIDUTC())
                if cal_component is None:
                    cal_component = cal_master

                # TODO: No DTSTAMP comparison because we do not track DTSTAMPs
                # Treat components the same as meaning so an update - in theory no harm in doing that
                if Component.compareComponentsForITIP(itip_component, cal_component, use_dtstamp=False) >= 0:
                    return True

            return False

        elif itip_master:

            # Do comparison of each appropriate component if any one is new, process the itip
            for cal_component in calendar.subcomponents():
                if cal_component.name() in ignoredComponents:
                    continue
                itip_component = itip.overriddenComponent(cal_component.getRecurrenceIDUTC())
                if itip_component is None:
                    itip_component = itip_master

                # TODO: No DTSTAMP comparison because we do not track DTSTAMPs
                # Treat components the same as meaning so an update - in theory no harm in doing that
                if Component.compareComponentsForITIP(itip_component, cal_component, use_dtstamp=False) >= 0:
                    return True

            return False

        else:
            # Do comparison of each matching component if any one is new, process the entire itip.
            # There is a race condition here, similar to REPLY, where we could reinstate an instance
            # that has been removed. Not much we can do about it without additional tracking.

            cal_rids = set()
            for cal_component in calendar.subcomponents():
                if cal_component.name() in ignoredComponents:
                    continue
                cal_rids.add(cal_component.getRecurrenceIDUTC())
            itip_rids = set()
            for itip_component in itip.subcomponents():
                if itip_component.name() in ignoredComponents:
                    continue
                itip_rids.add(itip_component.getRecurrenceIDUTC())

            # Compare ones that match
            for rid in cal_rids & itip_rids:
                cal_component = calendar.overriddenComponent(rid)
                itip_component = itip.overriddenComponent(rid)

                # TODO: No DTSTAMP comparison because we do not track DTSTAMPs
                # Treat components the same as meaning so an update - in theory no harm in doing that
                if Component.compareComponentsForITIP(itip_component, cal_component, use_dtstamp=False) >= 0:
                    return True

            # If there are others in one set and not the other - always process, else no process
            return len(cal_rids ^ itip_rids) > 0



class iTipGenerator(object):
    """
    This assumes that DTSTAMP and SEQUENCE are already at their new values in the original calendar
    data passed in to each generateXXX() call.
    """

    @staticmethod
    def generateCancel(original, attendees, instances=None, full_cancel=False, test_only=False):
        """
        This assumes that SEQUENCE is not already at its new value in the original calendar data. This
        is because the component passed in is the one that originally contained the attendee that is
        being removed.
        """

        itip = Component("VCALENDAR")
        itip.addProperty(Property("VERSION", "2.0"))
        itip.addProperty(Property("PRODID", iCalendarProductID))
        itip.addProperty(Property("METHOD", "CANCEL"))

        if instances is None:
            instances = (None,)

        tzids = set()
        added = False
        for instance_rid in instances:

            # Use the master component when the instance is None
            if not instance_rid:
                instance = original.masterComponent()
                assert instance is not None, "Need a master component"
            else:
                instance = original.overriddenComponent(instance_rid)
                if instance is None:
                    instance = original.deriveInstance(instance_rid)

                # If the instance to be cancelled did not exist in the original, then
                # do nothing
                if instance is None:
                    continue

            # If testing, skip the rest
            if test_only:
                added = True
                continue

            # Create a new component matching the type of the original
            comp = Component(original.mainType())

            # Add some required properties extracted from the original
            comp.addProperty(Property("DTSTAMP", instance.propertyValue("DTSTAMP")))
            comp.addProperty(Property("UID", instance.propertyValue("UID")))
            seq = instance.propertyValue("SEQUENCE")
            seq = int(seq) + 1 if seq else 1
            comp.addProperty(Property("SEQUENCE", seq))
            comp.addProperty(instance.getOrganizerProperty())
            if instance_rid:
                comp.addProperty(Property("RECURRENCE-ID", instance_rid.duplicate().adjustToUTC()))

            def addProperties(propname):
                for icalproperty in instance.properties(propname):
                    comp.addProperty(icalproperty)

            addProperties("SUMMARY")
            addProperties("DTSTART")
            addProperties("DTEND")
            addProperties("DURATION")
            if not instance_rid:
                addProperties("RRULE")
                addProperties("RDATE")
                addProperties("EXDATE")

            # Extract the matching attendee property
            for attendee in attendees:
                if full_cancel:
                    attendeeProp = original.getAttendeeProperty((attendee,))
                else:
                    attendeeProp = instance.getAttendeeProperty((attendee,))
                assert attendeeProp is not None, "Must have matching ATTENDEE property"
                comp.addProperty(attendeeProp)

            tzids.update(comp.timezoneIDs())

            itip.addComponent(comp)
            added = True

        # When testing only need to return whether an itip would have been created or not
        if test_only:
            return added

        # Handle actual iTIP message
        if added:
            # Now include any referenced tzids
            for comp in original.subcomponents():
                if comp.name() == "VTIMEZONE":
                    tzid = comp.propertyValue("TZID")
                    if tzid in tzids:
                        itip.addComponent(comp)

            # Strip out unwanted bits
            iTipGenerator.prepareSchedulingMessage(itip)

            return itip
        else:
            return None


    @staticmethod
    def generateAttendeeRequest(original, attendees, filter_rids, test_only=False):
        """
        This assumes that SEQUENCE is already at its new value in the original calendar data.
        """

        # Start with a copy of the original as we may have to modify bits of it
        itip = original.duplicate()
        itip.replaceProperty(Property("PRODID", iCalendarProductID))
        itip.addProperty(Property("METHOD", "REQUEST"))

        return iTipGenerator.generateAttendeeView(itip, attendees, filter_rids, test_only)


    @staticmethod
    def generateAttendeeView(calendar, attendees, filter_rids, test_only=False):
        """
        Generate an attendee's view of an iCalendar object. The object might be an iTIP
        message derived from the organizer's event, or it might be a copy of
        the organizer's event itself. The later is used when "fixing" broken attendee
        data that needs to be made to look consistent with the organizer's.

        @param calendar: the calendar data to process
        @type calendar: L{Component}
        @param attendees: list of attendees to view for
        @type attendees: L{list}
        @param filter_rids: list of instances to include, of L{None} for all
        @type filter_rids: L{list} or L{None}
        @param test_only: for unit testing only
        @type test_only: L{bool}
        """
        # Now filter out components that do not contain every attendee
        calendar.attendeesView(attendees, onlyScheduleAgentServer=True)

        # Now filter out components except the ones specified
        if calendar.filterComponents(filter_rids):
            # Strip out unwanted bits
            if not test_only:
                iTipGenerator.prepareSchedulingMessage(calendar)
            return calendar

        else:
            return None


    @staticmethod
    def generateAttendeeReply(original, attendee, changedRids=None, force_decline=False):

        # Start with a copy of the original as we may have to modify bits of it
        itip = original.duplicate()
        itip.replaceProperty(Property("PRODID", iCalendarProductID))
        itip.addProperty(Property("METHOD", "REPLY"))

        # Now filter out components except the ones specified
        itip.filterComponents(changedRids)

        # Force update to DTSTAMP everywhere so reply sequencing will work
        itip.replacePropertyInAllComponents(Property("DTSTAMP", DateTime.getNowUTC()))

        # Remove all attendees except the one we want
        itip.removeAllButOneAttendee(attendee)

        # Remove all components which are missing the attendee
        for component in itip.subcomponents():
            if component.name() in ignoredComponents:
                continue
            if not component.getAttendeeProperty((attendee,)):
                itip.removeComponent(component)

        # No alarms
        itip.removeAlarms()

        # Remove all but essential properties
        itip.filterProperties(keep=(
            "UID",
            "RECURRENCE-ID",
            "SEQUENCE",
            "STATUS",
            "DTSTAMP",
            "DTSTART",
            "DTEND",
            "DURATION",
            "RRULE",
            "RDATE",
            "EXDATE",
            "ORGANIZER",
            "ATTENDEE",
            "VOTER",
            "X-CALENDARSERVER-PRIVATE-COMMENT",
            "SUMMARY",
            "LOCATION",
            "DESCRIPTION",
        ))

        # Now set each ATTENDEE's PARTSTAT to DECLINED
        if force_decline:
            attendeeProps = itip.getAttendeeProperties((attendee,))
            assert attendeeProps, "Must have some matching ATTENDEEs"
            for attendeeProp in attendeeProps:
                attendeeProp.setParameter("PARTSTAT", "DECLINED")

        # Add REQUEST-STATUS to each top-level component
        itip.addPropertyToAllComponents(Property("REQUEST-STATUS", ["2.0", "Success", ]))

        # Strip out unwanted bits
        iTipGenerator.prepareSchedulingMessage(itip, reply=True)

        # Handle VPOLL behavior
        for component in itip.subcomponents():
            if component.name() == "VPOLL":
                iTipGenerator.generateVPOLLReply(component, attendee)

        return itip


    @staticmethod
    def generateVPOLLReply(vpoll, attendee):
        """
        Generate the proper poll response in a reply for each component being voted on.

        @param vpoll: the VPOLL component to process
        @type vpoll: L{Component}
        @param attendee: calendar user address of attendee replying
        @type attendee: C{str}
        """

        for component in tuple(vpoll.subcomponents()):
            if component.name() in ignoredComponents:
                continue
            poll_item_id = component.propertyValue("POLL-ITEM-ID")
            if poll_item_id is None:
                continue
            voter = component.getVoterProperty((attendee,))
            if voter is not None and voter.hasParameter("RESPONSE"):
                vpoll.addProperty(Property("POLL-ITEM-ID", poll_item_id, {"RESPONSE": voter.parameterValue("RESPONSE")}))
            vpoll.removeComponent(component)


    @staticmethod
    def prepareSchedulingMessage(itip, reply=False):
        """
        Remove properties and parameters that should not be sent in an iTIP message
        """

        # All X- components go away
        itip.removeXComponents()

        # Alarms
        itip.removeAlarms()

        # Top-level properties - remove all X-
        itip.removeXProperties(do_subcomponents=False)

        # Component properties - remove all X- except for those specified
        if not reply:
            # Organizer properties that need to go to the Attendees
            keep_properties = config.Scheduling.CalDAV.OrganizerPublicProperties
        else:
            # Attendee properties that need to go to the Organizer
            keep_properties = ("X-CALENDARSERVER-PRIVATE-COMMENT",)
        itip.removeXProperties(keep_properties=keep_properties)

        # Property Parameters
        itip.removePropertyParameters("ATTENDEE", ("SCHEDULE-AGENT", "SCHEDULE-STATUS", "SCHEDULE-FORCE-SEND", "X-CALENDARSERVER-DTSTAMP",))
        itip.removePropertyParameters("VOTER", ("SCHEDULE-AGENT", "SCHEDULE-STATUS", "SCHEDULE-FORCE-SEND", "X-CALENDARSERVER-DTSTAMP",))
        itip.removePropertyParameters("ORGANIZER", ("SCHEDULE-AGENT", "SCHEDULE-STATUS", "SCHEDULE-FORCE-SEND",))



class iTIPRequestStatus(object):
    """
    String constants for various iTIP status codes we use.
    """

    MESSAGE_PENDING_CODE = "1.0"
    MESSAGE_SENT_CODE = "1.1"
    MESSAGE_DELIVERED_CODE = "1.2"

    SUCCESS_CODE = "2.0"
    REQUEST_FORWARDED_CODE = "2.7"

    INVALID_CALENDAR_USER_CODE = "3.7"
    NO_AUTHORITY_CODE = "3.8"

    BAD_REQUEST_CODE = "5.0"
    SERVICE_UNAVAILABLE_CODE = "5.1"
    INVALID_SERVICE_CODE = "5.2"
    NO_USER_SUPPORT_CODE = "5.3"

    MESSAGE_PENDING = MESSAGE_PENDING_CODE + ";Scheduling message send is pending"
    MESSAGE_SENT = MESSAGE_SENT_CODE + ";Scheduling message has been sent"
    MESSAGE_DELIVERED = MESSAGE_DELIVERED_CODE + ";Scheduling message has been delivered"

    SUCCESS = SUCCESS_CODE + ";Success"
    REQUEST_FORWARDED = REQUEST_FORWARDED_CODE + ";Success; request forwarded to Calendar User."

    INVALID_CALENDAR_USER = INVALID_CALENDAR_USER_CODE + ";Invalid Calendar User"
    NO_AUTHORITY = NO_AUTHORITY_CODE + ";No authority"

    BAD_REQUEST = BAD_REQUEST_CODE + ";Service cannot handle request"
    SERVICE_UNAVAILABLE = SERVICE_UNAVAILABLE_CODE + ";Service unavailable"
    INVALID_SERVICE = INVALID_SERVICE_CODE + ";Invalid calendar service"
    NO_USER_SUPPORT = NO_USER_SUPPORT_CODE + ";No scheduling support for user"
