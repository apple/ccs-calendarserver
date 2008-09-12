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

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.web2 import responsecode
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.http import HTTPError
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.scheduling.itip import iTipGenerator
from twistedcaldav.log import Logger
from twistedcaldav.scheduling.scheduler import CalDAVScheduler
from twistedcaldav.method import report_common
from twistedcaldav.scheduling.icaldiff import iCalDiff
from twistedcaldav import caldavxml
from twisted.web2.dav import davxml

__all__ = [
    "ImplicitScheduler",
]

log = Logger()

# TODO:
#
# Handle the case where a PUT removes the ORGANIZER property. That should be equivalent to cancelling the entire meeting.
# Support SCHEDULE-AGENT property
# Support SCHEDULE-STATUS property
# Support live calendars
# Support Schedule-Reply header
#

class ImplicitScheduler(object):
    
    def __init__(self):
        pass

    @inlineCallbacks
    def doImplicitScheduling(self, request, resource, calendar, deleting, internal_request=False):
        """
        Do implicit scheduling operation based on the calendar data that is being PUT

        @param request:
        @type request:
        @param resource:
        @type resource:
        @param calendar: the calendar data being written, or None if deleting
        @type calendar: L{Component} or C{None}
        @param deleting: C{True} if the resource is being deleting
        @type deleting: bool

        @return: a new calendar object modified with scheduling information,
            or C{None} if nothing happened
        """
        
        self.request = request
        self.resource = resource
        self.calendar = calendar
        self.calendar_owner = (yield self.resource.owner(self.request))
        self.deleting = deleting
        self.internal_request = internal_request
        self.except_attendees = ()

        # When deleting we MUST have the calendar as the actual resource
        # will have been deleted by now
        assert deleting and calendar or not deleting

        # Get some useful information from the calendar
        yield self.extractCalendarData()

        # Determine what type of scheduling this is: Organizer triggered or Attendee triggered
        if self.isOrganizerScheduling():
            yield self.doImplicitOrganizer()
        elif self.isAttendeeScheduling():
            yield self.doImplicitAttendee()
        else:
            returnValue(None)

        returnValue(self.calendar)

    @inlineCallbacks
    def refreshAllAttendeesExceptSome(self, request, resource, calendar, attendees):
        """
        
        @param request:
        @type request:
        @param attendee:
        @type attendee:
        @param calendar:
        @type calendar:
        """

        self.request = request
        self.resource = resource
        self.calendar = calendar
        self.calendar_owner = None
        self.deleting = False
        self.internal_request = True
        self.except_attendees = attendees
        
        # Get some useful information from the calendar
        yield self.extractCalendarData()
        self.organizerPrincipal = self.resource.principalForCalendarUserAddress(self.organizer)
        
        result = (yield self.processRequests())

        returnValue(result)

    @inlineCallbacks
    def extractCalendarData(self):
        
        # Get the originator who is the authenticated user
        self.originatorPrincipal = None
        self.originator = ""
        authz_principal = self.resource.currentPrincipal(self.request).children[0]
        if isinstance(authz_principal, davxml.HRef):
            originatorPrincipalURL = str(authz_principal)
            if originatorPrincipalURL:
                self.originatorPrincipal = (yield self.request.locateResource(originatorPrincipalURL))
                if self.originatorPrincipal:
                    # Pick the first mailto cu address or the first other type
                    for item in self.originatorPrincipal.calendarUserAddresses():
                        if not self.originator:
                            self.originator = item
                        if item.startswith("mailto:"):
                            self.originator = item
                            break

        # Get the ORGANIZER and verify it is the same for all components
        organizers = self.calendar.getOrganizersByInstance()
        self.organizer = None
        for organizer, _ignore in organizers:
            if self.organizer:
                if organizer != self.organizer:
                    # We have different ORGANIZERs in the same iCalendar object - this is an error
                    log.error("Only one ORGANIZER is allowed in an iCalendar object:\n%s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "single-organizer")))
            else:
                self.organizer = organizer
        
        # Get the ATTENDEEs
        self.attendeesByInstance = self.calendar.getAttendeesByInstance()
        self.attendees = set()
        for attendee, _ignore in self.attendeesByInstance:
            self.attendees.add(attendee)
            
        # Some other useful things
        self.uid = self.calendar.resourceUID()
    
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
    def doAccessControl(self, principal, is_organizer):
        """
        Check that the currently authorized user has the appropriate scheduling privilege
        on the principal's Outbox.

        @param principal:
        @type principal:
        @param is_organizer:
        @type is_organizer:
        """
        
        # Find outbox
        outboxURL = principal.scheduleOutboxURL()
        outbox = (yield self.request.locateResource(outboxURL))
        yield outbox.authorize(self.request, (caldavxml.Schedule(),))

    @inlineCallbacks
    def doImplicitOrganizer(self):
        
        # Do access control
        if not self.internal_request:
            yield self.doAccessControl(self.organizerPrincipal, True)

        # Check for a delete
        if self.deleting:

            log.debug("Implicit - organizer '%s' is deleting UID: '%s'" % (self.organizer, self.uid))
            self.oldcalendar = self.calendar

            # Cancel all attendees
            self.cancelledAttendees = [(attendee, None) for attendee in self.attendees]

        # Check for a new resource or an update
        elif self.resource.exists():

            # Read in existing data
            self.oldcalendar = self.resource.iCalendar()
            
            # Significant change
            if self.isChangeInsignificant():
                # Nothing to do
                log.debug("Implicit - organizer '%s' is updating UID: '%s' but change is not significant" % (self.organizer, self.uid))
                returnValue(None)
            
            log.debug("Implicit - organizer '%s' is updating UID: '%s'" % (self.organizer, self.uid))

            # Check for removed attendees
            self.findRemovedAttendees()
        else:
            log.debug("Implicit - organizer '%s' is creating UID: '%s'" % (self.organizer, self.uid))
            self.oldcalendar = None
            self.cancelledAttendees = ()   
            
        yield self.scheduleWithAttendees()

    def isChangeInsignificant(self):
        
        differ = iCalDiff(self.oldcalendar, self.calendar)
        return differ.organizerDiff()
    
    def findRemovedAttendees(self):
        """
        Look for attendees that have been removed from any instances. Save those off
        as users that need to be sent a cancel.
        """
        
        # Several possibilities for when CANCELs need to be sent:
        #
        # Remove ATTENDEE property
        # Add EXDATE
        # Remove overridden component
        # Remove RDATE
        # Truncate RRULE
        # Change RRULE
        
        # TODO: the later three will be ignored for now.

        oldAttendeesByInstance = self.oldcalendar.getAttendeesByInstance()
        
        mappedOld = set(oldAttendeesByInstance)
        mappedNew = set(self.attendeesByInstance)
        
        # Get missing instances
        oldInstances = set(self.oldcalendar.getComponentInstances())
        newInstances = set(self.calendar.getComponentInstances())
        removedInstances = oldInstances - newInstances

        # Also look for new EXDATEs
        oldexdates = set()
        for property in self.oldcalendar.masterComponent().properties("EXDATE"):
            oldexdates.update(property.value())
        newexdates = set()
        for property in self.calendar.masterComponent().properties("EXDATE"):
            newexdates.update(property.value())

        addedexdates = newexdates - oldexdates

        # Now figure out the attendees that need to be sent CANCELs
        self.cancelledAttendees = set()
        
        for item in mappedOld:
            if item not in mappedNew:
                
                # Several possibilities:
                #
                # 1. removed from master component - always a CANCEL
                # 2. removed from overridden component - always a CANCEL
                # 3. removed overridden component - only CANCEL if not in master or exdate added
                 
                new_attendee, rid = item
                
                # 1. & 2.
                if rid is None or rid not in removedInstances:
                    self.cancelledAttendees.add(item)
                else:
                    # 3.
                    if (new_attendee, None) not in mappedNew or rid in addedexdates:
                        self.cancelledAttendees.add(item)

        master_attendees = self.oldcalendar.masterComponent().getAttendeesByInstance()
        for attendee, _ignore in master_attendees:
            for exdate in addedexdates:
                # Don't remove the master attendee's when an EXDATE is added for a removed overridden component
                # as the set of attendees in the override may be different from the master set, but the override
                # will have been accounted for by the previous attendee/instance logic.
                if exdate not in removedInstances:
                    self.cancelledAttendees.add((attendee, exdate))

    @inlineCallbacks
    def scheduleWithAttendees(self):
        
        # First process cancelled attendees
        yield self.processCancels()
        
        # Process regular requests next
        if not self.deleting:
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
            log.info("Implicit CANCEL - organizer: '%s' to attendee: '%s', UID: '%s', RIDs: '%s'" % (self.organizer, attendee, self.uid, rids))
            response = (yield scheduler.doSchedulingViaPUT(self.originator, (attendee,), itipmsg, self.internal_request))
            self.handleSchedulingResponse(response, True)
            
    @inlineCallbacks
    def processRequests(self):
        
        # TODO: a better policy here is to aggregate by attendees with the same set of instances
        # being requested, but for now we will do one scheduling message per attendee.

        # Do one per attendee
        for attendee in self.attendees:

            # Don't send message back to the ORGANIZER
            if attendee in self.organizerPrincipal.calendarUserAddresses():
                continue

            # Don't send message to specified attendees
            if attendee in self.except_attendees:
                continue

            itipmsg = iTipGenerator.generateAttendeeRequest(self.calendar, (attendee,))

            # Send scheduling message

            # This is a local CALDAV scheduling operation.
            scheduler = CalDAVScheduler(self.request, self.resource)
    
            # Do the PUT processing
            log.info("Implicit REQUEST - organizer: '%s' to attendee: '%s', UID: '%s'" % (self.organizer, attendee, self.uid,))
            response = (yield scheduler.doSchedulingViaPUT(self.originator, (attendee,), itipmsg, self.internal_request))
            self.handleSchedulingResponse(response, True)

    def handleSchedulingResponse(self, response, is_organizer):
        
        # Map each recipient in the response to a status code
        responses = {}
        for item in response.responses:
            assert isinstance(item, caldavxml.Response), "Wrong element in response"
            recipient = str(item.children[0].children[0])
            status = str(item.children[1])
            responses[recipient] = status
            
        # Now apply to each ATTENDEE/ORGANIZER in the original data
        self.calendar.setParameterToValueForPropertyWithValue(
            "SCHEDULE-STATUS",
            status,
            "ATTENDEE" if is_organizer else "ORGANIZER",
            recipient)

    @inlineCallbacks
    def doImplicitAttendee(self):

        # Do access control
        if not self.internal_request:
            yield self.doAccessControl(self.attendeePrincipal, False)

        if self.deleting:
            #log.error("Attendee '%s' is not allowed to delete an organized event: UID:%s" % (self.attendeePrincipal, self.uid,))
            #raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-attendee-change")))
            log.debug("Implicit - attendee '%s' is cancelling UID: '%s'" % (self.attendee, self.uid))
            yield self.scheduleCancelWithOrganizer()
        
        else:
            # Get the ORGANIZER's current copy of the calendar object
            yield self.getOrganizersCopy()
            assert self.organizer_calendar, "Must have the organizer's copy of an invite"
            
            # Determine whether the current change is allowed
            if self.isAttendeeChangeInsignificant():
                log.debug("Implicit - attendee '%s' is updating UID: '%s' but change is not significant" % (self.attendee, self.uid))
                returnValue(None)
                
            log.debug("Implicit - attendee '%s' is updating UID: '%s'" % (self.attendee, self.uid))
            yield self.scheduleWithOrganizer()

    @inlineCallbacks
    def getOrganizersCopy(self):
        """
        Get the Organizer's copy of the event being processed.
        
        NB it is possible that the Organizer is not hosted on this server
        so the result here will be None. In that case we have to trust that
        the attendee does the right thing about changing the details in the event.
        """
        
        self.organizer_calendar = None
        if self.organizerPrincipal:
            # Get Organizer's calendar-home
            calendar_home = self.organizerPrincipal.calendarHome()
            
            # FIXME: because of the URL->resource request mapping thing, we have to force the request
            # to recognize this resource
            self.request._rememberResource(calendar_home, calendar_home.url())
    
            # Run a UID query against the UID

            def queryCalendarCollection(collection, uri):
                rname = collection.index().resourceNameForUID(self.uid)
                if rname:
                    self.organizer_calendar = collection.iCalendar(rname)
                    return succeed(False)
                else:
                    return succeed(True)
            
            # NB We are by-passing privilege checking here. That should be OK as the data found is not
            # exposed to the user.
            yield report_common.applyToCalendarCollections(calendar_home, self.request, calendar_home.url(), "infinity", queryCalendarCollection, None)
    
    def isAttendeeChangeInsignificant(self):
        """
        Check whether the change is significant (PARTSTAT) or allowed
        (attendee can only change their property, alarms, TRANSP, and
        instances. Raise an exception if it is not allowed.
        """
        
        differ = iCalDiff(self.organizer_calendar, self.calendar)
        change_allowed, no_itip = differ.attendeeMerge(self.attendee)
        if not change_allowed:
            log.error("Attendee '%s' is not allowed to make an unauthorized change to an organized event: UID:%s" % (self.attendeePrincipal, self.uid,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-attendee-change")))

        return no_itip

    def scheduleWithOrganizer(self):

        itipmsg = iTipGenerator.generateAttendeeReply(self.calendar, self.attendee)

        # Send scheduling message
        return self.sendToOrganizer("REPLY", itipmsg)

    def scheduleCancelWithOrganizer(self):

        itipmsg = iTipGenerator.generateAttendeeReply(self.calendar, self.attendee, True)

        # Send scheduling message
        return self.sendToOrganizer("CANCEL", itipmsg)

    def sendToOrganizer(self, action, itipmsg):

        # Send scheduling message

        # This is a local CALDAV scheduling operation.
        scheduler = CalDAVScheduler(self.request, self.resource)

        # Do the PUT processing
        def _gotResponse(response):
            self.handleSchedulingResponse(response, False)
            
        log.info("Implicit %s - attendee: '%s' to organizer: '%s', UID: '%s'" % (action, self.attendee, self.organizer, self.uid,))
        d = scheduler.doSchedulingViaPUT(self.originator, (self.organizer,), itipmsg, self.internal_request)
        d.addCallback(_gotResponse)
        return d
