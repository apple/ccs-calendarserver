##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
iTIP (RFC2446) processing.
"""

#
# This is currently used for handling auto-replies to schedule requests arriving
# in an inbox. It is called in a delayed fashion via reactor.callLater.
#
# We assume that all the components/calendars we deal with have been determined
# as being 'valid for CalDAV/iTIP', i.e. they contain UIDs, single component
# types, etc.
#
# The logic for component matching needs a lot more work as it currently does not
# know how to deal with overridden instances.
#

import datetime

from twistedcaldav.log import Logger
from twistedcaldav.ical import Property, iCalendarProductID, Component

from vobject.icalendar import utc
from vobject.icalendar import dateTimeToString

log = Logger()

__version__ = "0.0"

__all__ = [
    "iTipProcessing",
    "iTipGenerator",
]

class iTipProcessing(object):

    @staticmethod
    def processNewRequest(itip_message):
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
            
        return calendar
        
    @staticmethod
    def processRequest(itip_message, calendar):
        """
        Process a METHOD=REQUEST.
        
        @param itip_message: the iTIP message calendar object to process.
        @type itip_message:
        @param calendar: the calendar object to apply the REQUEST to
        @type calendar:
        
        @return: calendar object ready to save, or C{None} (request should be ignored)
        """
        
        # Merge Organizer data with Attendee's own changes (VALARMs only for now).
        
        # Different behavior depending on whether a master component is present or not
        current_master = calendar.masterComponent()
        if current_master:
            master_valarms = [comp for comp in current_master.subcomponents() if comp.name() == "VALARM"]
        else:
            master_valarms = ()

        if itip_message.masterComponent() is not None:
            
            # Get a new calendar object first
            new_calendar = iTipProcessing.processNewRequest(itip_message)
            
            # Copy over master alarms
            master_component = new_calendar.masterComponent()
            for alarm in master_valarms:
                master_component.addComponent(alarm)
                
            # Now try to match recurrences
            for component in new_calendar.subcomponents():
                if component.name() != "VTIMEZONE" and component.getRecurrenceIDUTC() is not None:
                    iTipProcessing.transferAlarms(calendar, master_valarms, component)
            
            # Replace the entire object
            return new_calendar

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
                    iTipProcessing.transferAlarms(calendar, master_valarms, component, remove_matched=True)
                    calendar.addComponent(component)

            # Write back the modified object
            return calendar

    @staticmethod
    def processCancel(itip_message, calendar):
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
        """
        
        assert itip_message.propertyValue("METHOD") == "CANCEL", "iTIP message must have METHOD:CANCEL"
        assert itip_message.resourceUID() == calendar.resourceUID(), "UIDs must be the same to process iTIP message"

        # Check to see if this is a cancel of the entire event
        if itip_message.masterComponent() is not None:
            return True, True

        # iTIP CANCEL can contain multiple components being cancelled in the RECURRENCE-ID case.
        # So we need to iterate over each iTIP component.

        # Get the existing calendar master object if it exists
        calendar_master = calendar.masterComponent()
        exdates = []

        # Look at each component in the iTIP message
        for component in itip_message.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
        
            # Extract RECURRENCE-ID value from component
            rid = component.getRecurrenceIDUTC()
            
            # Get the one that matches in the calendar
            overridden = calendar.overriddenComponent(rid)
            
            if overridden:
                # We are cancelling an overridden component.

                # Exclude the cancelled instance
                exdates.append(component.getRecurrenceIDUTC())
                
                # Remove the existing component.
                calendar.removeComponent(overridden)
            elif calendar_master:
                # We are trying to CANCEL a non-overridden instance.

                # Exclude the cancelled instance
                exdates.append(component.getRecurrenceIDUTC())

        # If we have any EXDATEs lets add them to the existing calendar object.
        if exdates and calendar_master:
            calendar_master.addProperty(Property("EXDATE", exdates))

        # See if there are still components in the calendar - we might have deleted the last overridden instance
        # in which case the calendar object is empty (except for VTIMEZONEs).
        if calendar.mainType() is None:
            # Delete the now empty calendar object
            return True, True
        else:
            return True, False
    
    @staticmethod
    def processReply(itip_message, calendar):
        """
        Process a METHOD=REPLY.
        
        TODO: Yes, I am going to ignore RANGE= on RECURRENCE-ID for now...
        
        @param itip_message: the iTIP message calendar object to process.
        @type itip_message:
        @param calendar: the calendar object to apply the REPLY to
        @type calendar:
        
        @return: C{True} if processed, C{False} if scheduling message should be ignored
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
        if new_master:
            attendees.add(iTipProcessing.updateAttendeeData(new_master, old_master))

        # Now do all overridden ones
        for itip_component in itip_message.subcomponents():
            
            # Make sure we have an appropriate component
            if itip_component.name() == "VTIMEZONE":
                continue
            rid = itip_component.getRecurrenceIDUTC()
            if rid is None:
                continue
            
            # Find matching component in organizer's copy
            match_component = calendar.overriddenComponent(rid)
            if match_component is None:
                # Attendee is overriding an instance themselves - we need to create a derived one
                # for the Organizer
                match_component = calendar.deriveInstance(rid)
                calendar.addComponent(match_component)

            attendees.add(iTipProcessing.updateAttendeeData(itip_component, match_component))
                
        return True, attendees

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
        
        # Get attendee in from_component - there MUST be only one
        attendees = tuple(from_component.properties("ATTENDEE"))
        assert len(attendees) == 1, "There must be one and only one ATTENDEE property in a REPLY"
        attendee = attendees[0]
        partstat = attendee.params().get("PARTSTAT", ("NEEDS-ACTION",))[0]
        
        # Now find matching ATTENDEE in to_component
        existing_attendee = to_component.getAttendeeProperty((attendee.value(),))
        if existing_attendee:
            existing_attendee.params().setdefault("PARTSTAT", [partstat])[0] = partstat
            
            # Handle attendee comments
            
            # Look for X-CALENDARSERVER-PRIVATE-COMMENT property in iTIP component (State 1 in spec)
            attendee_comment = tuple(from_component.properties("X-CALENDARSERVER-PRIVATE-COMMENT"))
            attendee_comment = attendee_comment[0] if len(attendee_comment) else None
            
            # Look for matching X-CALENDARSERVER-ATTENDEE-COMMENT property in existing data (State 2 in spec)
            private_comments = tuple(to_component.properties("X-CALENDARSERVER-ATTENDEE-COMMENT"))
            for comment in private_comments:
                params = comment.params()["X-CALENDARSERVER-ATTENDEE-REF"]
                assert len(params) == 1, "Must be one and only one X-CALENDARSERVER-ATTENDEE-REF parameter in X-CALENDARSERVER-ATTENDEE-COMMENT"
                param = params[0]
                if param == attendee.value():
                    private_comment = comment
                    break
            else:
                private_comment = None
                
            # Now do update logic
            if attendee_comment is None and private_comment is None:
                # Nothing to do
                pass
 
            elif attendee_comment is None and private_comment is not None:
                # Remove all property parameters
                private_comment.params().clear()
                
                # Add default parameters
                private_comment.params()["X-CALENDARSERVER-ATTENDEE-REF"] = [attendee.value()]
                private_comment.params()["X-CALENDARSERVER-DTSTAMP"] = [dateTimeToString(datetime.datetime.now(tz=utc))]
                
                # Set value empty
                private_comment.setValue("")
                
            elif attendee_comment is not None and private_comment is None:
                
                # Add new property
                private_comment = Property(
                    "X-CALENDARSERVER-ATTENDEE-COMMENT",
                    attendee_comment.value(),
                    params = {
                        "X-CALENDARSERVER-ATTENDEE-REF":     [attendee.value()],
                        "X-CALENDARSERVER-DTSTAMP": [dateTimeToString(datetime.datetime.now(tz=utc))],
                    }
                )
                to_component.addProperty(private_comment)
            
            else:
                # Remove all property parameters
                private_comment.params().clear()
                
                # Add default parameters
                private_comment.params()["X-CALENDARSERVER-ATTENDEE-REF"] = [attendee.value()]
                private_comment.params()["X-CALENDARSERVER-DTSTAMP"] = [dateTimeToString(datetime.datetime.now(tz=utc))]
                
                # Set new value
                private_comment.setValue(attendee_comment.value())

        return attendee.value()

    @staticmethod
    def transferAlarms(from_calendar, master_valarms, to_component, remove_matched=False):

        rid = to_component.getRecurrenceIDUTC()

        # Is there a matching component
        matched = from_calendar.overriddenComponent(rid)
        if matched:
            # Copy over VALARMs from existing component
            [to_component.addComponent(comp) for comp in matched.subcomponents() if comp.name() == "VALARM"]

            # Remove the old one
            if remove_matched:
                from_calendar.removeComponent(matched)
                
        else:
            # It is a new override - copy any valarms on the existing master component
            # into the new one.
            for alarm in master_valarms:
                # Just copy in the new override
                to_component.addComponent(alarm)
    
class iTipGenerator(object):
    
    @staticmethod
    def generateCancel(original, attendees, instances=None):
        
        itip = Component("VCALENDAR")
        itip.addProperty(Property("VERSION", "2.0"))
        itip.addProperty(Property("PRODID", iCalendarProductID))
        itip.addProperty(Property("METHOD", "CANCEL"))

        if instances is None:
            instances = (None,)

        tzids = set()
        for instance_rid in instances:
            
            # Create a new component matching the type of the original
            comp = Component(original.mainType())
            itip.addComponent(comp)

            # Use the master component when the instance is None
            if not instance_rid:
                instance = original.masterComponent()
            else:
                instance = original.overriddenComponent(instance_rid)
                if instance is None:
                    instance = original.masterComponent()
            assert instance is not None, "Need a master component"

            # Add some required properties extracted from the original
            comp.addProperty(Property("DTSTAMP", datetime.datetime.now(tz=utc)))
            comp.addProperty(Property("UID", instance.propertyValue("UID")))
            seq = instance.propertyValue("SEQUENCE")
            seq = str(int(seq) + 1) if seq else "1"
            comp.addProperty(Property("SEQUENCE", seq))
            comp.addProperty(instance.getOrganizerProperty())
            if instance_rid:
                comp.addProperty(Property("RECURRENCE-ID", instance_rid))
            
            def addProperties(propname):
                for property in instance.properties(propname):
                    comp.addProperty(property)
                    
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
                attendeeProp = instance.getAttendeeProperty((attendee,))
                assert attendeeProp is not None, "Must have matching ATTENDEE property"
                comp.addProperty(attendeeProp)

            tzids.update(comp.timezoneIDs())
            
        # Now include any referenced tzids
        for comp in original.subcomponents():
            if comp.name() == "VTIMEZONE":
                tzid = comp.propertyValue("TZID")
                if tzid in tzids:
                    itip.addComponent(comp)

        # Strip out unwanted bits
        iTipGenerator.prepareSchedulingMessage(itip)

        return itip

    @staticmethod
    def generateAttendeeRequest(original, attendees):

        # Start with a copy of the original as we may have to modify bits of it
        itip = original.duplicate()
        itip.replaceProperty(Property("PRODID", iCalendarProductID))
        itip.addProperty(Property("METHOD", "REQUEST"))
        
        # Force update to DTSTAMP everywhere
        itip.replacePropertyInAllComponents(Property("DTSTAMP", datetime.datetime.now(tz=utc)))

        # Now filter out components that do not contain every attendee
        itip.attendeesView(attendees)
        
        # Strip out unwanted bits
        iTipGenerator.prepareSchedulingMessage(itip)

        return itip
        
    @staticmethod
    def generateAttendeeReply(original, attendee, force_decline=False):

        # Start with a copy of the original as we may have to modify bits of it
        itip = original.duplicate()
        itip.replaceProperty(Property("PRODID", iCalendarProductID))
        itip.addProperty(Property("METHOD", "REPLY"))
        
        # Force update to DTSTAMP everywhere
        itip.replacePropertyInAllComponents(Property("DTSTAMP", datetime.datetime.now(tz=utc)))

        # Remove all attendees except the one we want
        itip.removeAllButOneAttendee(attendee)
        
        # No alarms
        itip.removeAlarms()

        # Remove all but essential properties
        itip.filterProperties(keep=(
            "UID",
            "RECURRENCE-ID",
            "SEQUENCE",
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
        ))
        
        # Now set each ATTENDEE's PARTSTAT to DECLINED
        if force_decline:
            attendeeProps = itip.getAttendeeProperties((attendee,))
            assert attendeeProps, "Must have some matching ATTENDEEs"
            for attendeeProp in attendeeProps:
                if "PARTSTAT" in attendeeProp.params():
                    attendeeProp.params()["PARTSTAT"][0] = "DECLINED"
                else:
                    attendeeProp.params()["PARTSTAT"] = ["DECLINED"]
        
        # Add REQUEST-STATUS to each top-level component
        itip.addPropertyToAllComponents(Property("REQUEST-STATUS", "2.0;Success"))
        return itip

    @staticmethod
    def prepareSchedulingMessage(itip):
        """
        Remove properties and parameters that should not be sent in an iTIP message
        """

        # Component properties
        def stripSubComponents(component, strip):
            
            for subcomponent in tuple(component.subcomponents()):
                if subcomponent.name() in strip:
                    component.removeComponent(subcomponent)

        # Component properties
        def stripComponentProperties(component, properties):
            
            for property in tuple(component.properties()):
                if property.name() in properties:
                    component.removeProperty(property)

        # Property parameters
        def stripPropertyParameters(properties, parameters):
            
            for property in properties:
                for parameter in parameters:
                    try:
                        del property.params()[parameter]
                    except KeyError:
                        pass

        # Top-level properties
        stripComponentProperties(itip, ("X-CALENDARSERVER-ACCESS",))
                
        # Component properties
        for component in itip.subcomponents():
            stripSubComponents(component, ("VALARM",))
            stripComponentProperties(component, (
                "X-CALENDARSERVER-ATTENDEE-COMMENT",
            ))
            stripPropertyParameters(component.properties("ATTENDEE"), (
                "SCHEDULE-AGENT",
                "SCHEDULE-STATUS",
            ))
            stripPropertyParameters(component.properties("ORGANIZER"), (
                "SCHEDULE-STATUS",
            ))
