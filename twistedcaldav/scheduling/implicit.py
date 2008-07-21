#
# Copyright (c) 2005-2008 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.http import HTTPError
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.itip import iTipGenerator
from twistedcaldav.log import Logger
from twistedcaldav.scheduling.scheduler import CalDAVScheduler

__all__ = [
    "ImplicitScheduler",
]

log = Logger()

class ImplicitScheduler(object):
    
    def __init__(self):
        pass

    @inlineCallbacks
    def doImplicitScheduling(self, request, resource, calendar):
        """
        Do implicit scheduling operation based on the calendar data that is being PUT

        @param request:
        @type request:
        @param resource:
        @type resource:
        @param calendar:
        @type calendar:
        
        @return: a new calendar object modified with scheduling information
        """
        
        self.request = request
        self.resource = resource
        self.calendar = calendar
        self.calendar_owner = (yield self.resource.owner(self.request))

        
        # Get some useful information from the calendar
        self.extractCalendarData()

        # Determine what type of scheduling this is: Organizer triggered or Attendee triggered
        if self.isOrganizerScheduling():
            yield self.doImplicitOrganizer()
        elif self.isAttendeeScheduling():
            yield self.doImplicitAttendee()

        returnValue(self.calendar)

    def extractCalendarData(self):
        
        # Get the ORGANIZER and verify it is the same for all components
        organizers = self.calendar.getOrganizersByInstance()
        self.organizer = None
        for organizer, _ignore in organizers:
            if self.organizer:
                if organizer != self.organizer:
                    # We have different ORGANIZERs in the same iCalendar object - this is an error
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "single-organizer")))
            else:
                self.organizer = organizer
        
        # Get the ATTENDEEs
        self.attendeesByInstance = self.calendar.getAttendeesByInstance()
        self.attendees = set()
        for attendee, _ignore in self.attendeesByInstance:
            self.attendees.add(attendee)
    
    def isOrganizerScheduling(self):
        """
        Test whether this is a scheduling operation by an organizer
        """
        
        # First must have organizer property
        if not self.organizer:
            return False
        
        # Organizer must map to a valid principal
        self.organizerPrincipal = self.resource.principalForCalendarUserAddress(self.organizer)
        if not self.organizerPrincipal:
            return False
        
        # Organizer must be the owner of the calendar resource
        if str(self.calendar_owner) != self.organizerPrincipal.principalURL():
            return False

        return True

    def isAttendeeScheduling(self):
        
        # First must have organizer property
        if not self.organizer:
            return False
        
        # Check to see whether any attendee is the owner
        for attendee in self.attendees:
            attendeePrincipal = self.resource.principalForCalendarUserAddress(attendee)
            if attendeePrincipal and attendeePrincipal.principalURL() == str(self.calendar_owner):
                self.attendee = attendee
                self.attendeePrincipal = attendeePrincipal
                return True
        
        return False

    @inlineCallbacks
    def doImplicitOrganizer(self):
        
        # Check for a new resource or an update
        if self.resource.exists():
            
            # Read in existing data
            self.oldcalendar = self.resource.iCalendar()
            
            # Significant change
            if not self.isChangeSignificant():
                # Nothing to do
                return
            
            # Check for removed attendees
            self.findRemovedAttendees()
        else:
            self.oldcalendar = None
            self.cancelledAttendees = ()   
            
        yield self.scheduleWithAttendees()

    def isChangeSignificant(self):
        
        # TODO: diff two calendars and see what happened. For now treat any change as significant.
        return True
    
    def findRemovedAttendees(self):
        """
        Look for attendees that have been removed from any instances. Save those off
        as users that need to be sent a cancel.
        """
        
        oldAttendeesByInstance = self.oldcalendar.getAttendeesByInstance()
        
        mappedOld = set(oldAttendeesByInstance)
        mappedNew = set(self.attendeesByInstance)
        
        self.cancelledAttendees = mappedOld.difference(mappedNew)

    @inlineCallbacks
    def scheduleWithAttendees(self):
        
        # First process cancelled attendees
        yield self.processCancels()
        
        # Process regular requests next
        yield self.processRequests()

    @inlineCallbacks
    def processCancels(self):
        
        # TODO: a better policy here is to aggregate by attendees with the same set of instances
        # being cancelled, but for now we will do one scheduling message per attendee.

        # Do one per attendee
        aggregated = {}
        for attendee, rid in self.cancelledAttendees:
            aggregated.setdefault(attendee, []).append(rid)
            
        for attendee, rids in aggregated.iteritems():
            
            # Don't send message back to the ORGANIZER
            if attendee in self.organizerPrincipal.calendarUserAddresses():
                continue

            # Generate an iTIP CANCEL message for this attendee, cancelling
            # each instance or the whole
            
            if None in rids:
                # One big CANCEL will do
                itipmsg = iTipGenerator.generateCancel(self.oldcalendar, (attendee,), None)
            else:
                # Multiple CANCELs
                itipmsg = iTipGenerator.generateCancel(self.oldcalendar, (attendee,), rids)

            # Send scheduling message
            
            # This is a local CALDAV scheduling operation.
            scheduler = CalDAVScheduler(self.request, self.resource)
    
            # Do the PUT processing
            response = (yield scheduler.doSchedulingViaPUT(self.organizer, (attendee,), itipmsg))
            
            # TODO: need to figure out how to process the response for a CANCEL
            returnValue(response)
            
    @inlineCallbacks
    def processRequests(self):
        
        # TODO: a better policy here is to aggregate by attendees with the same set of instances
        # being requested, but for now we will do one scheduling message per attendee.

        # Do one per attendee
        for attendee, _ignore in self.attendeesByInstance:

            # Don't send message back to the ORGANIZER
            if attendee in self.organizerPrincipal.calendarUserAddresses():
                continue

            itipmsg = iTipGenerator.generateAttendeeRequest(self.calendar, (attendee,))

            # Send scheduling message

            # This is a local CALDAV scheduling operation.
            scheduler = CalDAVScheduler(self.request, self.resource)
    
            # Do the PUT processing
            response = (yield scheduler.doSchedulingViaPUT(self.organizer, (attendee,), itipmsg))
            
            # TODO: need to figure out how to process the response for a REQUEST
            returnValue(response)
            
    @inlineCallbacks
    def doImplicitAttendee(self):

        # Get the ORGANIZER's current copy of the calendar object
        self.orgcalendar = self.getOrganizersCopy()
        
        # Determine whether the current change is allowed
        if not self.isAttendeeChangeSignificant():
            return
            
        yield self.scheduleWithOrganizer()

    def getOrganizersCopy(self):
        """
        Get the Organizer's copy of the event being processed.
        
        NB it is possible that the Organizer is not hosted on this server
        so the result here will be None. In that case we have to trust that
        the attendee does the right thing about changing the details in the event.
        """
        
        # TODO: extract UID and ORGANIZER, find match in ORGANIZER's calendars.

        return None
    
    def isAttendeeChangeSignificant(self):
        """
        Check whether the change is significant (PARTSTAT) or allowed
        (attendee can only change their property, alarms, TRANSP, and
        instances. Raise an exception if it is not allowed.
        """
        
        # TODO: all of the above.
        return True

    @inlineCallbacks
    def scheduleWithOrganizer(self):

        itipmsg = iTipGenerator.generateAttendeeReply(self.calendar, self.attendee)

        # Send scheduling message

        # This is a local CALDAV scheduling operation.
        scheduler = CalDAVScheduler(self.request, self.resource)

        # Do the PUT processing
        response = (yield scheduler.doSchedulingViaPUT(self.attendee, (self.organizer,), itipmsg))
        
        # TODO: need to figure out how to process the response for a REQUEST
        returnValue(response)
