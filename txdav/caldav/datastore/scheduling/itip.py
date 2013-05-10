##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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

from pycalendar.datetime import PyCalendarDateTime

log = Logger()

__all__ = [
    "iTipProcessing",
    "iTipGenerator",
]

class iTipProcessing(object):

    @staticmethod
    def processNewRequest(itip_message, recipient=None, creating=False):
        """
        Process a METHOD=REQUEST for a brand new calendar object.

        @param itip_message: the iTIP message calendar object to process.
        @type itip_message:

        @return: calendar object ready to save
        """
        assert itip_message.propertyValue("METHOD") == "REQUEST", "iTIP message must have METHOD:REQUEST"

        calendar = itip_message.duplicate()
        method = calendar.getProperty("METHOD")
        if method:
            calendar.removeProperty(method)

        if recipient:
            iTipProcessing.addTranspForNeedsAction(calendar.subcomponents(), recipient)

            # Check for incoming DECLINED
            if creating:
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

        @param itip_message: the iTIP message calendar object to process.
        @type itip_message:
        @param calendar: the calendar object to apply the REQUEST to
        @type calendar:

        @return: a C{tuple} of:
            calendar object ready to save, or C{None} (request should be ignored)
            a C{set} of recurrences that changed, or C{None}
        """

        # Check sequencing
        if not iTipProcessing.sequenceComparison(itip_message, calendar):
            # Ignore out of sequence message
            return None, None

        # Merge Organizer data with Attendee's own changes (VALARMs, Comment only for now).
        from txdav.caldav.datastore.scheduling.icaldiff import iCalDiff
        rids = iCalDiff(calendar, itip_message, False).whatIsDifferent()

        # Different behavior depending on whether a master component is present or not
        # Here we cache per-attendee data from the master that we need to use in any new
        # overridden components that the organizer added
        current_master = calendar.masterComponent()
        if current_master:
            master_valarms = [comp for comp in current_master.subcomponents() if comp.name() == "VALARM"]
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
            master_valarms = ()
            private_comments = ()
            transps = ()
            completeds = ()
            organizer_schedule_status = None
            attendee_dtstamp = None
            other_props = {}

        if itip_message.masterComponent() is not None:

            # Get a new calendar object first
            new_calendar = iTipProcessing.processNewRequest(itip_message, recipient)

            # Copy over master alarms, comments
            master_component = new_calendar.masterComponent()
            for alarm in master_valarms:
                master_component.addComponent(alarm)
            for comment in private_comments:
                master_component.addProperty(comment)
            for transp in transps:
                master_component.replaceProperty(transp)
            for completed in completeds:
                master_component.replaceProperty(completed)
            if organizer_schedule_status:
                organizer = master_component.getProperty("ORGANIZER")
                if organizer:
                    organizer.setParameter("SCHEDULE-STATUS", organizer_schedule_status)
            if attendee_dtstamp:
                attendee = master_component.getAttendeeProperty((recipient,))
                if attendee:
                    attendee.setParameter("X-CALENDARSERVER-DTSTAMP", attendee_dtstamp)
            for props in other_props.values():
                [master_component.replaceProperty(prop) for prop in props]

            # Now try to match recurrences in the new calendar
            for component in tuple(new_calendar.subcomponents()):
                if component.name() != "VTIMEZONE" and component.getRecurrenceIDUTC() is not None:
                    iTipProcessing.transferItems(calendar, master_valarms, private_comments, transps, completeds, organizer_schedule_status, attendee_dtstamp, other_props, component, recipient)

            # Now try to match recurrences from the old calendar
            for component in calendar.subcomponents():
                if component.name() != "VTIMEZONE" and component.getRecurrenceIDUTC() is not None:
                    rid = component.getRecurrenceIDUTC()
                    if new_calendar.overriddenComponent(rid) is None:
                        allowCancelled = component.propertyValue("STATUS") == "CANCELLED"
                        new_component = new_calendar.deriveInstance(rid, allowCancelled=allowCancelled)
                        if new_component:
                            new_calendar.addComponent(new_component)
                            iTipProcessing.transferItems(calendar, master_valarms, private_comments, transps, completeds, organizer_schedule_status, attendee_dtstamp, other_props, new_component, recipient)

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
                    missingDeclined = iTipProcessing.transferItems(calendar, master_valarms, private_comments, transps, completeds, organizer_schedule_status, attendee_dtstamp, other_props, component, recipient, remove_matched=True)
                    if not missingDeclined:
                        calendar.addComponent(component)
                        if recipient:
                            iTipProcessing.addTranspForNeedsAction((component,), recipient)

            # Write back the modified object
            return calendar, rids


    @staticmethod
    def processCancel(itip_message, calendar, autoprocessing=False):
        """
        Process a METHOD=CANCEL.

        TODO: Yes, I am going to ignore RANGE= on RECURRENCE-ID for now...

        @param itip_message: the iTIP message calendar object to process.
        @type itip_message:
        @param calendar: the calendar object to apply the CANCEL to
        @type calendar:

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
                # We are cancelling an overridden component.

                if autoprocessing:
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
                    if overridden:
                        overridden.replaceProperty(Property("STATUS", "CANCELLED"))
                        calendar.addComponent(overridden)
                        newseq = component.propertyValue("SEQUENCE")
                        overridden.replacePropertyInAllComponents(Property("SEQUENCE", newseq))

        # If we have any EXDATEs lets add them to the existing calendar object.
        if exdates and calendar_master:
            calendar_master.addProperty(Property("EXDATE", exdates))

        # See if there are still components in the calendar - we might have deleted the last overridden instance
        # in which case the calendar object is empty (except for VTIMEZONEs).
        if calendar.mainType() is None:
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

        @param itip_message: the iTIP message calendar object to process.
        @type itip_message:
        @param calendar: the calendar object to apply the REPLY to
        @type calendar:

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
                if match_component:
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
        Copy the PARTSTAT of the Attendee in the from_component to the matching ATTENDEE
        in the to_component. Ignore if no match found. Also update the private comments.

        @param from_component:
        @type from_component:
        @param to_component:
        @type to_component:
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
        attendees = tuple(from_component.properties("ATTENDEE"))
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
                # Remove all property parameters
                private_comment.removeAllParameters()

                # Add default parameters
                private_comment.setParameter("X-CALENDARSERVER-ATTENDEE-REF", attendee.value())
                private_comment.setParameter("X-CALENDARSERVER-DTSTAMP", PyCalendarDateTime.getNowUTC().getText())

                # Set value empty
                private_comment.setValue("")

                private_comment_changed = True

            elif attendee_comment is not None and private_comment is None:

                # Add new property
                private_comment = Property(
                    "X-CALENDARSERVER-ATTENDEE-COMMENT",
                    attendee_comment.value(),
                    params={
                        "X-CALENDARSERVER-ATTENDEE-REF": attendee.value(),
                        "X-CALENDARSERVER-DTSTAMP": PyCalendarDateTime.getNowUTC().getText(),
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
                    private_comment.setParameter("X-CALENDARSERVER-DTSTAMP", PyCalendarDateTime.getNowUTC().getText())

                    # Set new value
                    private_comment.setValue(attendee_comment.value())

                    private_comment_changed = True

        return attendee.value(), partstat_changed, private_comment_changed


    @staticmethod
    def transferItems(from_calendar, master_valarms, private_comments, transps, completeds, organizer_schedule_status, attendee_dtstamp, other_props, to_component, recipient, remove_matched=False):
        """
        Transfer properties from a calendar to a component by first trying to match the component in the original calendar and
        use the properties from that, or use the values provided as arguments (which have been derived from the original calendar's
        master component).

        @return: C{True} if an EXDATE match occurred requiring the incoming component to be removed.
        """

        rid = to_component.getRecurrenceIDUTC()

        # Is there a matching component
        matched = from_calendar.overriddenComponent(rid)
        if matched:
            # Copy over VALARMs from existing component
            [to_component.addComponent(comp) for comp in matched.subcomponents() if comp.name() == "VALARM"]
            [to_component.addProperty(prop) for prop in matched.properties("X-CALENDARSERVER-ATTENDEE-COMMENT")]
            [to_component.replaceProperty(prop) for prop in matched.properties("TRANSP")]
            [to_component.replaceProperty(prop) for prop in matched.properties("COMPLETED")]

            organizer = matched.getProperty("ORGANIZER")
            organizer_schedule_status = organizer.parameterValue("SCHEDULE-STATUS", None) if organizer else None
            if organizer_schedule_status:
                organizer = to_component.getProperty("ORGANIZER")
                if organizer:
                    organizer.setParameter("SCHEDULE-STATUS", organizer_schedule_status)

            # Remove the old one
            if remove_matched:
                from_calendar.removeComponent(matched)

            # Check for incoming DECLINED
            attendee = to_component.getAttendeeProperty((recipient,))
            if attendee and attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "DECLINED":
                # If existing item has HIDDEN property copy that over
                if matched.hasProperty(Component.HIDDEN_INSTANCE_PROPERTY):
                    to_component.addProperty(Property(Component.HIDDEN_INSTANCE_PROPERTY, "T"))

            if attendee and attendee_dtstamp:
                attendee.setParameter("X-CALENDARSERVER-DTSTAMP", attendee_dtstamp)

            for pname in config.Scheduling.CalDAV.PerAttendeeProperties:
                [to_component.replaceProperty(prop) for prop in matched.properties(pname)]
        else:
            # Check for incoming DECLINED
            attendee = to_component.getAttendeeProperty((recipient,))
            if attendee and attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "DECLINED":
                return True

            # It is a new override - copy any valarms on the existing master component
            # into the new one.
            [to_component.addComponent(alarm) for alarm in master_valarms]
            [to_component.addProperty(comment) for comment in private_comments]
            [to_component.replaceProperty(transp) for transp in transps]
            [to_component.replaceProperty(completed) for completed in completeds]

            if organizer_schedule_status:
                organizer = to_component.getProperty("ORGANIZER")
                if organizer:
                    organizer.setParameter("SCHEDULE-STATUS", organizer_schedule_status)
            if attendee_dtstamp:
                attendee = to_component.getAttendeeProperty((recipient,))
                if attendee:
                    attendee.setParameter("X-CALENDARSERVER-DTSTAMP", attendee_dtstamp)

            for props in other_props.values():
                [to_component.replaceProperty(prop) for prop in props]

        return False


    @staticmethod
    def addTranspForNeedsAction(components, recipient):
        # For each component where the ATTENDEE property of the recipient has PARTSTAT
        # NEEDS-ACTION we add TRANSP:TRANSPARENT for VEVENTs
        for component in components:
            if component.name() != "VEVENT":
                continue
            attendee = component.getAttendeeProperty((recipient,))
            if attendee and attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "NEEDS-ACTION":
                component.replaceProperty(Property("TRANSP", "TRANSPARENT"))


    @staticmethod
    def sequenceComparison(itip, calendar):
        """
        Do appropriate itip message sequencing based by comparison with existing calendar data.

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
    def generateCancel(original, attendees, instances=None, full_cancel=False):
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

            # Create a new component matching the type of the original
            comp = Component(original.mainType())

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
    def generateAttendeeRequest(original, attendees, filter_rids):
        """
        This assumes that SEQUENCE is already at its new value in the original calendar data.
        """

        # Start with a copy of the original as we may have to modify bits of it
        itip = original.duplicate()
        itip.replaceProperty(Property("PRODID", iCalendarProductID))
        itip.addProperty(Property("METHOD", "REQUEST"))

        # Now filter out components that do not contain every attendee
        itip.attendeesView(attendees, onlyScheduleAgentServer=True)

        # Now filter out components except the ones specified
        if itip.filterComponents(filter_rids):
            # Strip out unwanted bits
            iTipGenerator.prepareSchedulingMessage(itip)
            return itip

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
        itip.replacePropertyInAllComponents(Property("DTSTAMP", PyCalendarDateTime.getNowUTC()))

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

        return itip


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
        itip.removePropertyParameters("ORGANIZER", ("SCHEDULE-AGENT", "SCHEDULE-STATUS", "SCHEDULE-FORCE-SEND",))



class iTIPRequestStatus(object):
    """
    String constants for various iTIP status codes we use.
    """

    MESSAGE_PENDING_CODE = "1.0"
    MESSAGE_SENT_CODE = "1.1"
    MESSAGE_DELIVERED_CODE = "1.2"

    SUCCESS_CODE = "2.0"

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

    INVALID_CALENDAR_USER = INVALID_CALENDAR_USER_CODE + ";Invalid Calendar User"
    NO_AUTHORITY = NO_AUTHORITY_CODE + ";No authority"

    BAD_REQUEST = BAD_REQUEST_CODE + ";Service cannot handle request"
    SERVICE_UNAVAILABLE = SERVICE_UNAVAILABLE_CODE + ";Service unavailable"
    INVALID_SERVICE = INVALID_SERVICE_CODE + ";Invalid calendar service"
    NO_USER_SUPPORT = NO_USER_SUPPORT_CODE + ";No scheduling support for user"
