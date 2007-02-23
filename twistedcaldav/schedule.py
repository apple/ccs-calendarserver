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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
CalDAV scheduling resources.
"""

__all__ = [
    "ScheduleInboxResource",
    "ScheduleOutboxResource",
]

from twisted.internet import reactor
from twisted.internet.defer import deferredGenerator, maybeDeferred, waitForDeferred
from twisted.python import log
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.http import HTTPError, Response
from twisted.web2.http_headers import MimeType
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse, errorForFailure, messageForFailure, statusForFailure
from twisted.web2.dav.util import joinURL, parentForURL

from twistedcaldav import caldavxml
from twistedcaldav import customxml
from twistedcaldav import itip
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.caldavxml import caldav_namespace, TimeRange
from twistedcaldav.config import config
from twistedcaldav.ical import Component
from twistedcaldav.method import report_common
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.resource import isCalendarCollectionResource

import md5
import time

class CalendarSchedulingCollectionResource (CalDAVResource):
    """
    CalDAV principal resource.

    Extends L{DAVResource} to provide CalDAV scheduling collection
    functionality.
    """
    def __init__(self, parent):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        CalDAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent

    def isCollection(self):
        return True

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return True

    def supportedReports(self):
        result = super(CalDAVResource, self).supportedReports()
        result.append(davxml.Report(caldavxml.CalendarQuery(),))
        result.append(davxml.Report(caldavxml.CalendarMultiGet(),))
        # free-busy report not allowed
        return result

class ScheduleInboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Inbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """
    def resourceType(self):
        return davxml.ResourceType.scheduleInbox

    def defaultAccessControlList(self):
        return davxml.ACL(
            # CalDAV:schedule for any authenticated user
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(
                    davxml.Privilege(caldavxml.Schedule()),
                ),
            ),
        )

class ScheduleOutboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Outbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """

    def defaultAccessControlList(self):
        if config.EnableProxyPrincipals:
            myPrincipal = self.parent.principalForRecord()
    
            return davxml.ACL(
                # CalDAV:schedule for associated write proxies
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-write"))),
                    davxml.Grant(
                        davxml.Privilege(caldavxml.Schedule()),
                    ),
                ),
            )
        else:
            return super(ScheduleOutboxResource, self).defaultAccessControlList()

    def resourceType(self):
        return davxml.ResourceType.scheduleOutbox

    @deferredGenerator
    def http_POST(self, request):
        """
        The CalDAV POST method.
    
        This uses a generator function yielding either L{waitForDeferred} objects or L{Response} objects.
        This allows for code that follows a 'linear' execution pattern rather than having to use nested
        L{Deferred} callbacks. The logic is easier to follow this way plus we don't run into deep nesting
        issues which the other approach would have with large numbers of recipients.
        """
        # Check authentication and access controls
        parent = waitForDeferred(request.locateResource(parentForURL(request.uri)))
        yield parent
        parent = parent.getResult()
        x = waitForDeferred(parent.authorize(request, (caldavxml.Schedule(),)))
        yield x
        x.getResult()

        # Must be content-type text/calendar
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
            log.err("MIME type %s not allowed in calendar collection" % (content_type,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
    
        # Must have Originator header
        originator = request.headers.getRawHeaders("originator")
        if originator is None or (len(originator) != 1):
            log.err("POST request must have Originator header")
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-specified")))
        else:
            originator = originator[0]
    
        # Verify that Originator is a valid calendar user (has an INBOX)
        oprincipal = self.principalForCalendarUserAddress(originator)
        if oprincipal is None:
            log.err("Could not find principal for originator: %s" % (originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

        inboxURL = oprincipal.scheduleInboxURL()
        if inboxURL is None:
            log.err("Could not find inbox for originator: %s" % (originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
    
        # Get list of Recipient headers
        rawrecipients = request.headers.getRawHeaders("recipient")
        if rawrecipients is None or (len(rawrecipients) == 0):
            log.err("POST request must have at least one Recipient header")
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
            log.err("Error while handling POST: %s" % (Failure(),))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
 
        # Must be a valid calendar
        try:
            calendar.validCalendarForCalDAV()
        except ValueError:
            log.err("POST request calendar component is not valid: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

        # Must have a METHOD
        if not calendar.isValidMethod():
            log.err("POST request must have valid METHOD property in calendar component: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
        
        # Verify iTIP behaviour
        if not calendar.isValidITIP():
            log.err("POST request must have a calendar component that satisfies iTIP requirements: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
    
        # Verify that the ORGANIZER's cu address maps to the request.uri
        outboxURL = None
        organizer = calendar.getOrganizer()
        if organizer is not None:
            oprincipal = self.principalForCalendarUserAddress(organizer)
            if oprincipal is not None:
                outboxURL = oprincipal.scheduleOutboxURL()
        if outboxURL is None:
            log.err("ORGANIZER in calendar data is not valid: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

        # Prevent spoofing of ORGANIZER with specific METHODs
        if (calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER")) and (outboxURL != request.uri):
            log.err("ORGANIZER in calendar data does not match owner of Outbox: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

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
            aoutboxURL = None
            aprincipal = self.principalForCalendarUserAddress(attendees[0])
            if aprincipal is not None:
                aoutboxURL = aprincipal.scheduleOutboxURL()
            if aoutboxURL is None or aoutboxURL != request.uri:
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
        responses = ScheduleResponseQueue("POST", responsecode.OK)
    
        # Outbox copy is saved when not doing free busy request
        if not freebusy:
            # Hash the iCalendar data for use as the last path element of the URI path
            name = md5.new(str(calendar) + str(time.time()) + self.fp.path).hexdigest() + ".ics"
        
            # Save a copy of the calendar data into the Outbox
            childURL = joinURL(request.uri, name)
            child = waitForDeferred(request.locateResource(childURL))
            yield child
            child = child.getResult()
            responses.setLocation(childURL)
        
            try:
                d = waitForDeferred(
                        maybeDeferred(
                            storeCalendarObjectResource,
                            request = request,
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
                d.getResult()
            except:
                log.err("Error while handling POST: %s" % (Failure(),))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "outbox-copy")))
        
            # Store CALDAV:originator property
            child.writeDeadProperty(caldavxml.Originator(davxml.HRef(originator)))
        
            # Store CALDAV:recipient property
            child.writeDeadProperty(caldavxml.Recipient(*map(davxml.HRef, recipients)))
 
        # Extract the ORGANIZER property and UID value from the calendar data  for use later
        organizerProp = calendar.getOrganizerProperty()
        uid = calendar.resourceUID()

        # Loop over each recipient and do appropriate action.
        autoresponses = []
        for recipient in recipients:
            # Get the principal resource for this recipient
            principal = self.principalForCalendarUserAddress(recipient)

            # Map recipient to their inbox
            inbox = None
            if principal is None:
                log.err("No principal for calendar user address: %s" % (recipient,))
            else:
                inboxURL = principal.scheduleInboxURL()
                if inboxURL:
                    inbox = waitForDeferred(request.locateResource(inboxURL))
                    yield inbox
                    inbox = inbox.getResult()
                else:
                    log.err("No schedule inbox for principal: %s" % (principal,))

            if inbox is None:
                err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-exists")))
                responses.add(recipient, Failure(exc_value=err), reqstatus="3.7;Invalid Calendar User")
                recipients_state["BAD"] += 1
            
                # Process next recipient
                continue
            else:
                #
                # Check access controls
                #
                try:
                    d = waitForDeferred(inbox.checkPrivileges(request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef(oprincipal.principalURL()))))
                    yield d
                    d.getResult()
                except:
                    log.err("Could not access Inbox for recipient: %s" % (recipient,))
                    err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-permisions")))
                    responses.add(recipient, Failure(exc_value=err), reqstatus="3.8;No authority")
                    recipients_state["BAD"] += 1
                
                    # Process next recipient
                    continue
    
                # Different behaviour for free-busy vs regular invite
                if freebusy:
                    # Extract the ATTENDEE property matching current recipient from the calendar data
                    cuas = principal.calendarUserAddresses()
                    attendeeProp = calendar.getAttendeeProperty(cuas)
            
                    # Find the current recipients calendar-free-busy-set
                    fbset = waitForDeferred(principal.calendarFreeBusyURIs(request))
                    yield fbset
                    fbset = fbset.getResult()

                    # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
                    fbinfo = ([], [], [])
                
                    try:
                        matchtotal = 0
                        for calURL in fbset:
                            cal = waitForDeferred(request.locateResource(calURL))
                            yield cal
                            cal = cal.getResult()
                            if cal is None or not cal.exists() or not isCalendarCollectionResource(cal):
                                # We will ignore missing calendars. If the recipient has failed to
                                # properly manage the free busy set that should not prevent us from working.
                                continue
                         
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
                        responses.add(recipient, Failure(exc_value=err), reqstatus="3.8;No authority")
                        recipients_state["BAD"] += 1
                
                else:
                    # Hash the iCalendar data for use as the last path element of the URI path
                    name = md5.new(str(calendar) + str(time.time()) + inbox.fp.path).hexdigest() + ".ics"
                
                    # Get a resource for the new item
                    childURL = joinURL(inboxURL, name)
                    child = waitForDeferred(request.locateResource(childURL))
                    yield child
                    child = child.getResult()
            
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
                        child.writeDeadProperty(caldavxml.Originator(davxml.HRef(originator)))
                    
                        # Store CALDAV:recipient property
                        child.writeDeadProperty(caldavxml.Recipient(davxml.HRef(recipient)))
                    
                        # Store CALDAV:schedule-state property
                        child.writeDeadProperty(caldavxml.ScheduleState(caldavxml.NotProcessed()))
                    
                        # Look for auto-respond option
                        if inbox.hasDeadProperty(customxml.TwistedScheduleAutoRespond):
                            autoresponses.append((principal, inbox, child))
                    except:
                        log.err("Could not store data in Inbox : %s" % (inbox,))
                        err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
                        responses.add(recipient, Failure(exc_value=err), reqstatus="3.8;No authority")
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

class ScheduleResponseResponse (Response):
    """
    ScheduleResponse L{Response} object.
    Renders itself as a CalDAV:schedule-response XML document.
    """
    def __init__(self, xml_responses, location=None):
        """
        @param xml_responses: an interable of davxml.Response objects.
        @param location:      the value of the location header to return in the response,
                              or None.
        """

        Response.__init__(self, code=responsecode.OK,
                          stream=caldavxml.ScheduleResponse(*xml_responses).toxml())

        self.headers.setHeader("content-type", MimeType("text", "xml"))
    
        if location is not None:
            self.headers.setHeader("location", location)

class ScheduleResponseQueue (object):
    """
    Stores a list of (typically error) responses for use in a
    L{ScheduleResponse}.
    """
    def __init__(self, method, success_response):
        """
        @param method: the name of the method generating the queue.
        @param success_response: the response to return in lieu of a
            L{ScheduleResponse} if no responses are added to this queue.
        """
        self.responses         = []
        self.method            = method
        self.success_response  = success_response
        self.location          = None

    def setLocation(self, location):
        """
        @param location:      the value of the location header to return in the response,
                              or None.
        """
        self.location = location

    def add(self, recipient, what, reqstatus=None, calendar=None):
        """
        Add a response.
        @param recipient: the recipient for this response.
        @param what: a status code or a L{Failure} for the given recipient.
        @param status: the iTIP request-status for the given recipient.
        @param calendar: the calendar data for the given recipient response.
        """
        if type(what) is int:
            code    = what
            error   = None
            message = responsecode.RESPONSES[code]
        elif isinstance(what, Failure):
            code    = statusForFailure(what)
            error   = errorForFailure(what)
            message = messageForFailure(what)
        else:
            raise AssertionError("Unknown data type: %r" % (what,))

        if code > 400: # Error codes only
            log.err("Error during %s for %s: %s" % (self.method, recipient, message))

        children = []
        children.append(caldavxml.Recipient(davxml.HRef.fromString(recipient)))
        children.append(caldavxml.RequestStatus(reqstatus))
        if calendar is not None:
            children.append(caldavxml.CalendarData.fromCalendar(calendar))
        if error is not None:
            children.append(error)
        if message is not None:
            children.append(davxml.ResponseDescription(message))
        self.responses.append(caldavxml.Response(*children))

    def response(self):
        """
        Generate a L{ScheduleResponseResponse} with the responses contained in the
        queue or, if no such responses, return the C{success_response} provided
        to L{__init__}.
        @return: the response.
        """
        if self.responses:
            return ScheduleResponseResponse(self.responses, self.location)
        else:
            return self.success_response
