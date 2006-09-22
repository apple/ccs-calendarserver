##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
CalDAV Schedule processing.
"""

__all__ = ["processScheduleRequest"]

from twisted.internet import reactor
from twisted.internet.defer import deferredGenerator, maybeDeferred, waitForDeferred
from twisted.python import failure, log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError
from twistedcaldav.resource import findAnyCalendarUser

from twistedcaldav import caldavxml
from twistedcaldav import customxml
from twistedcaldav import itip
from twistedcaldav.caldavxml import caldav_namespace, TimeRange
from twistedcaldav.http import ScheduleResponseQueue
from twistedcaldav.ical import Component
from twistedcaldav.method import report_common
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.resource import CalendarPrincipalCollectionResource, isScheduleOutboxResource, isCalendarCollectionResource
from twistedcaldav.static import CalDAVFile

import md5
import os
import time

def processScheduleRequest(self, method, request):
    """
    This is a generator function that yields L{waitForDeffered} or L{Response} objects. It handles processing of scheduling
    requests on an Outbox. These can currently come from either a SCHEDULE or POST method. SCHEDULE will be deprecated soon.

    @param method: the C{str} containing the current HTTP method.
    @param request: the L{twisted.web2.server.Request} for the current HTTP request.
    """

    # Must be targetting an OUTBOX
    if not isScheduleOutboxResource(self):
        log.err("%s must target an schedule Outbox collection: %s" % (method, self,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-collection")))

    # Must be content-type text/calendar
    content_type = request.headers.getHeader("content-type")
    if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
        log.err("MIME type %s not allowed in calendar collection" % (content_type,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
    
    # Must have Originator header
    originator = request.headers.getRawHeaders("originator")
    if originator is None or (len(originator) != 1):
        log.err("%s request must have Originator header" % (method,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-specified")))
    else:
        originator = originator[0]
    
    # Verify that Originator is a valid calendar user (has an INBOX)
    inboxURL = waitForDeferred(CalendarPrincipalCollectionResource.inboxForCalendarUser(request, originator))
    yield inboxURL
    inboxURL = inboxURL.getResult()
    if inboxURL is None:
        log.err("Could not find Inbox for originator: %s" % (originator,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
    
    # Get list of Recipient headers
    rawrecipients = request.headers.getRawHeaders("recipient")
    if rawrecipients is None or (len(rawrecipients) == 0):
        log.err("%s request must have at least one Recipient header" % (method,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-specified")))

    # Recipient header may be comma separated list
    recipients = []
    for rawrecipient in rawrecipients:
        for r in rawrecipient.split(","):
            r = r.strip()
            if len(r):
                recipients.append(r)

    timerange = TimeRange(start="20000101", end="20000102")
    recipients_state = {"OK":0, "BAD":0}

    # Parse the calendar object from the HTTP request stream
    try:
        d = waitForDeferred(Component.fromIStream(request.stream))
        yield d
        calendar = d.getResult()
    except:
        log.err("Error while handling %s: %s" % (method, failure.Failure(),))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
 
    # Must be a valid calendar
    try:
        calendar.validCalendarForCalDAV()
    except ValueError:
        log.err("%s request calendar component is not valid: %s" % (method, calendar,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

    # Must have a METHOD
    if not calendar.isValidMethod():
        log.err("%s request must have valid METHOD property in calendar component: %s" % (method, calendar,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
        
    # Verify iTIP behaviour
    if not calendar.isValidITIP():
        log.err("%s request must have a calendar component that satisfies iTIP requirements: %s" % (method, calendar,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
    
    # Verify that the ORGANIZER's cu address maps to the request.uri
    organizer = calendar.getOrganizer()
    if organizer:
        outboxURL = waitForDeferred(CalendarPrincipalCollectionResource.outboxForCalendarUser(request, organizer))
        yield outboxURL
        outboxURL = outboxURL.getResult()
    if (organizer is None) or (outboxURL is None):
        log.err("ORGANIZER in calendar data is not valid: %s" % (calendar,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

    # Prevent spoofing of ORGANIZER with specific METHODs
    if (calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER")) and (outboxURL != request.uri):
        log.err("ORGANIZER in calendar data does not match owner of Outbox: %s" % (calendar,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
    oprincipal = waitForDeferred(findAnyCalendarUser(request, organizer))
    yield oprincipal
    oprincipal = oprincipal.getResult()

    # Prevent spoofing when doing reply-like METHODs
    if calendar.propertyValue("METHOD") in ("REPLY", "COUNTER", "REFRESH"):
        # Verify that there is a single ATTENDEE property and that the Originator has permission
        # to send on behalf of that ATTENDEE
        attendees = calendar.getAttendees()
        
        # Must have only one
        if len(attendees) != 1:
            log.err("ATTENDEE list in calendar data is wrong: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
            
        # Attendee's Outbox MUST be the request URI
        aoutboxURL = waitForDeferred(CalendarPrincipalCollectionResource.outboxForCalendarUser(request, attendees[0]))
        yield aoutboxURL
        aoutboxURL = aoutboxURL.getResult()
        if (aoutboxURL is None) or (aoutboxURL != request.uri):
            log.err("ATTENDEE in calendar data does not match owner of Outbox: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))

    # For free-busy do immediate determination of iTIP result rather than fan-out
    if (calendar.propertyValue("METHOD") == "REQUEST") and (calendar.mainType() == "VFREEBUSY"):
        # Extract time range from VFREEBUSY object
        vfreebusies = [v for v in calendar.subcomponents() if v.name() == "VFREEBUSY"]
        if len(vfreebusies) != 1:
            log.err("iTIP data is not valid for a VFREEBUSY request: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
        dtstart = vfreebusies[0].getStartDateUTC()
        dtend = vfreebusies[0].getEndDateUTC()
        if dtstart is None or dtend is None:
            log.err("VFREEBUSY start/end not valid: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
        timerange.start = dtstart
        timerange.end = dtend

        # Do free busy operation
        freebusy = True
    else:
        # Do regular invite (fan-out)
        freebusy = False

    # Prepare for multiple responses
    responses = ScheduleResponseQueue(method, responsecode.OK)
    
    # Outbox copy is saved when not doing free busy request
    if not freebusy:
        # Hash the iCalendar data for use as the last path element of the URI path
        name = md5.new(str(calendar) + str(time.time()) + self.fp.path).hexdigest() + ".ics"
        
        # Save a copy of the calendar data into the Outbox
        child = CalDAVFile(os.path.join(self.fp.path, name))
        childURL = request.uri + name
        responses.setLocation(childURL)
        
        d = waitForDeferred(
                maybeDeferred(
                    storeCalendarObjectResource,
                    request=request,
                    sourcecal = False,
                    destination = child,
                    destination_uri = childURL,
                    calendardata = str(calendar),
                    destinationparent = self,
                    destinationcal = True,
                    isiTIP = True
                )
            )
        yield d

        try:
            d.getResult()
        except:
            log.err("Error while handling %s: %s" % (method, failure.Failure(),))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "outbox-copy")))
        
        # Store CALDAV:originator property
        child.writeDeadProperty(caldavxml.Originator(davxml.HRef.fromString(originator)))
        
        # Store CALDAV:recipient property
        child.writeDeadProperty(caldavxml.Recipient(*map(davxml.HRef.fromString, recipients)))
 
        # Extract the ORGANIZER property and UID value from the calendar data  for use later
    organizerProp = calendar.getOrganizerProperty()
    uid = calendar.resourceUID()

    # Loop over each recipient and do appropriate action.
    autoresponses = []
    for recipient in recipients:
        # Get the principal resource for this recipient
        principal = waitForDeferred(findAnyCalendarUser(request, recipient))
        yield principal
        principal = principal.getResult()

        # Map recipient to their inbox
        if principal is not None:
            inboxURL = principal.scheduleInboxURL()
            if inboxURL:
                inbox = waitForDeferred(request.locateResource(inboxURL))
                yield inbox
                inbox = inbox.getResult()
        if principal is None or inboxURL is None or inbox is None:
            log.err("Could not find Inbox for recipient: %s" % (recipient,))
            err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-exists")))
            responses.add(recipient, failure.Failure(exc_value=err), reqstatus="3.7;Invalid Calendar User")
            recipients_state["BAD"] += 1
            
            # Process next recipient
            continue
        else:

            #
            # Check access controls
            #
            try:
                d = waitForDeferred(inbox.checkPrivileges(request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef.fromString(oprincipal))))
                yield d
                d.getResult()
            except:
                log.err("Could not access Inbox for recipient: %s" % (recipient,))
                err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-permisions")))
                responses.add(recipient, failure.Failure(exc_value=err), reqstatus="3.8;No authority")
                recipients_state["BAD"] += 1
                
                # Process next recipient
                continue
    
            # Different behaviour for free-busy vs regular invite
            if freebusy:
                # Extract the ATTENDEE property matching current recipient from the calendar data
                cuas = principal.calendarUserAddressSet()
                attendeeProp = calendar.getAttendeeProperty(cuas)
            
                # Find the current recipients calendar-free-busy-set
                fbset = waitForDeferred(principal.calendarFreeBusySet(request))
                yield fbset
                fbset = fbset.getResult()

                # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
                fbinfo = ([], [], [])
                
                try:
                    matchtotal = 0
                    for href in fbset.children:
                        calURL = str(href)
                        cal = waitForDeferred(request.locateResource(calURL))
                        yield cal
                        cal = cal.getResult()
                        if cal is None or not cal.exists() or not isCalendarCollectionResource(cal):
                            # We will ignore missing calendars. If the recipient has failed to
                            # properly manage the free busy set that should not prevent us from working.
                            continue
                         
                        # TODO: make this a waitForDeferred and yield it
                        matchtotal = waitForDeferred(report_common.generateFreeBusyInfo(request, cal, fbinfo, timerange, matchtotal))
                        yield matchtotal
                        matchtotal = matchtotal.getResult()
                    
                    # Build VFREEBUSY iTIP reply for this recipient
                    fbresult = report_common.buildFreeBusyResult(fbinfo, timerange, organizer=organizerProp, attendee=attendeeProp, uid=uid)

                    responses.add(recipient, responsecode.OK, reqstatus="2.0;Success", calendar=fbresult)
                    recipients_state["OK"] += 1
                
                except:
                    log.err("Could not determine free busy information: %s" % (recipient,))
                    err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
                    responses.add(recipient, failure.Failure(exc_value=err), reqstatus="3.8;No authority")
                    recipients_state["BAD"] += 1
                
            else:
                # Hash the iCalendar data for use as the last path element of the URI path
                name = md5.new(str(calendar) + str(time.time()) + inbox.fp.path).hexdigest() + ".ics"
                
                # Get a resource for the new item
                child = CalDAVFile(os.path.join(inbox.fp.path, name))
                childURL = joinURL(inboxURL, name)
            
                # Copy calendar to inbox (doing fan-out)
                d = waitForDeferred(
                        maybeDeferred(
                            storeCalendarObjectResource,
                            request=request,
                            sourcecal = False,
                            destination = child,
                            destination_uri = childURL,
                            calendardata = str(calendar),
                            destinationparent = inbox,
                            destinationcal = True,
                            isiTIP = True
                        )
                     )
                yield d
                try:
                    d.getResult()
                    responses.add(recipient, responsecode.OK, reqstatus="2.0;Success")
                    recipients_state["OK"] += 1
        
                    # Store CALDAV:originator property
                    child.writeDeadProperty(caldavxml.Originator(davxml.HRef.fromString(originator)))
                    
                    # Store CALDAV:recipient property
                    child.writeDeadProperty(caldavxml.Recipient(davxml.HRef.fromString(recipient)))
                    
                    # Store CALDAV:schedule-state property
                    child.writeDeadProperty(caldavxml.ScheduleState(caldavxml.NotProcessed()))
                    
                    # Look for auto-respond option
                    if inbox.hasDeadProperty(customxml.TwistedScheduleAutoRespond):
                        autoresponses.append((principal, inbox, child))
                except:
                    log.err("Could not store data in Inbox : %s" % (inbox,))
                    err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
                    responses.add(recipient, failure.Failure(exc_value=err), reqstatus="3.8;No authority")
                    recipients_state["BAD"] += 1

    # Now we have to do auto-respond
    if len(autoresponses) != 0:
        # First check that we have a method that we can auto-respond to
        if not itip.canAutoRespond(calendar):
            autoresponses = []
            
    # Now do the actual auto response
    for principal, inbox, child in autoresponses:
        # Add delayed reactor task to handle iTIP responses
        reactor.callLater(5.0, itip.handleRequest, *(request, principal, inbox, calendar.duplicate(), child)) #@UndefinedVariable
        #reactor.callInThread(itip.handleRequest, *(request, principal, inbox, calendar.duplicate(), child)) #@UndefinedVariable

    # Return with final response if we are done
    yield responses.response()

processScheduleRequest = deferredGenerator(processScheduleRequest)

