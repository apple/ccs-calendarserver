##
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

"""
CalDAV scheduling resources.
"""

__all__ = [
    "ScheduleInboxResource",
    "ScheduleOutboxResource",
]

import md5
import time

from twisted.internet import reactor
from twisted.internet.defer import maybeDeferred, succeed, inlineCallbacks, returnValue
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.http import HTTPError, Response
from twisted.web2.http_headers import MimeType
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse, errorForFailure, messageForFailure, statusForFailure
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.dav.util import joinURL

from twistedcaldav import caldavxml
from twistedcaldav import itip
from twistedcaldav.log import LoggingMixIn
from twistedcaldav.accounting import accountingEnabled, emitAccounting
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.caldavxml import caldav_namespace, TimeRange
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.ical import Component
from twistedcaldav.method import report_common
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.resource import isCalendarCollectionResource

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

    liveProperties = CalendarSchedulingCollectionResource.liveProperties + (
        (caldav_namespace, "calendar-free-busy-set"),
    )

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

    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == (caldav_namespace, "calendar-free-busy-set"):
            # Always return at least an empty list
            if not self.hasDeadProperty(property):
                return succeed(caldavxml.CalendarFreeBusySet())
            
        return super(ScheduleInboxResource, self).readProperty(property, request)

    @inlineCallbacks
    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement)

        # Strictly speaking CS:calendar-availability is a live property in the sense that the
        # server enforces what can be stored, however it need not actually
        # exist so we cannot list it in liveProperties on this resource, since its
        # its presence there means that hasProperty will always return True for it.
        if property.qname() == (calendarserver_namespace, "calendar-availability"):
            if not property.valid():
                raise HTTPError(ErrorResponse(
                    responsecode.CONFLICT,
                    (caldav_namespace, "valid-calendar-data")
                ))

        elif property.qname() == (caldav_namespace, "calendar-free-busy-set"):
            # Verify that the calendars added in the PROPPATCH are valid. We do not check
            # whether existing items in the property are still valid - only new ones.
            new_calendars = set([str(href) for href in property.children])
            if not self.hasDeadProperty(property):
                old_calendars = set()
            else:
                old_calendars = set([str(href) for href in self.readDeadProperty(property).children])
            added_calendars = new_calendars.difference(old_calendars)
            for href in added_calendars:
                cal = yield request.locateResource(str(href))
                if cal is None or not cal.exists() or not isCalendarCollectionResource(cal):
                    # Validate that href's point to a valid calendar.
                    raise HTTPError(ErrorResponse(
                        responsecode.CONFLICT,
                        (caldav_namespace, "valid-calendar-url")
                    ))

        yield super(ScheduleInboxResource, self).writeProperty(property, request)

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
                    davxml.Grant(davxml.Privilege(caldavxml.Schedule()),),
                    davxml.Protected(),
                ),
            )
        else:
            return super(ScheduleOutboxResource, self).defaultAccessControlList()

    def resourceType(self):
        return davxml.ResourceType.scheduleOutbox

    @inlineCallbacks
    def http_POST(self, request):
        """
        The CalDAV POST method.
    
        This uses a generator function yielding either L{waitForDeferred} objects or L{Response} objects.
        This allows for code that follows a 'linear' execution pattern rather than having to use nested
        L{Deferred} callbacks. The logic is easier to follow this way plus we don't run into deep nesting
        issues which the other approach would have with large numbers of recipients.
        """
        # Check authentication and access controls
        yield self.authorize(request, (caldavxml.Schedule(),))

        # Must be content-type text/calendar
        contentType = request.headers.getHeader("content-type")
        if contentType is not None and (contentType.mediaType, contentType.mediaSubtype) != ("text", "calendar"):
            self.log_error("MIME type %s not allowed in calendar collection" % (contentType,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
    
        # Must have Originator header
        originator = request.headers.getRawHeaders("originator")
        if originator is None or (len(originator) != 1):
            self.log_error("POST request must have Originator header")
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-specified")))
        else:
            originator = originator[0]
    
        # Verify that Originator is a valid calendar user (has an INBOX)
        originatorPrincipal = self.principalForCalendarUserAddress(originator)
        if originatorPrincipal is None:
            self.log_error("Could not find principal for originator: %s" % (originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

        inboxURL = originatorPrincipal.scheduleInboxURL()
        if inboxURL is None:
            self.log_error("Could not find inbox for originator: %s" % (originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
    
        # Verify that Originator matches the authenticated user
        if davxml.Principal(davxml.HRef(originatorPrincipal.principalURL())) != self.currentPrincipal(request):
            self.log_error("Originator: %s does not match authorized user: %s" % (originator, self.currentPrincipal(request).children[0],))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

        # Get list of Recipient headers
        rawRecipients = request.headers.getRawHeaders("recipient")
        if rawRecipients is None or (len(rawRecipients) == 0):
            self.log_error("POST request must have at least one Recipient header")
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-specified")))

        # Recipient header may be comma separated list
        recipients = []
        for rawRecipient in rawRecipients:
            for r in rawRecipient.split(","):
                r = r.strip()
                if len(r):
                    recipients.append(r)

        timeRange = TimeRange(start="20000101", end="20000102")
        recipientsState = {"OK":0, "BAD":0}

        # Parse the calendar object from the HTTP request stream
        try:
            calendar = yield Component.fromIStream(request.stream)
        except:
            self.log_error("Error while handling POST: %s" % (Failure(),))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
 
        # Must be a valid calendar
        try:
            calendar.validCalendarForCalDAV()
        except ValueError:
            self.log_error("POST request calendar component is not valid: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

        # Must have a METHOD
        if not calendar.isValidMethod():
            self.log_error("POST request must have valid METHOD property in calendar component: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
        
        # Verify iTIP behaviour
        if not calendar.isValidITIP():
            self.log_error("POST request must have a calendar component that satisfies iTIP requirements: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

        # X-CALENDARSERVER-ACCESS is not allowed in Outbox POSTs
        if calendar.hasProperty(Component.ACCESS_PROPERTY):
            self.log_error("X-CALENDARSERVER-ACCESS not allowed in a calendar component POST request: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (calendarserver_namespace, "no-access-restrictions")))
    
        # Verify that the ORGANIZER's cu address maps to the request.uri
        organizer = calendar.getOrganizer()
        if organizer is None:
            organizerPrincipal = None
        else:
            organizerPrincipal = self.principalForCalendarUserAddress(organizer)

        if organizerPrincipal is None:
            self.log_error("ORGANIZER in calendar data is not valid: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

        # Prevent spoofing of ORGANIZER with specific METHODs
        if (
            calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER") and
            organizerPrincipal.record != self.parent.record
        ):
            self.log_error("ORGANIZER in calendar data does not match owner of Outbox: %s" % (calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

        # Prevent spoofing when doing reply-like METHODs
        if calendar.propertyValue("METHOD") in ("REPLY", "COUNTER", "REFRESH"):
            # Verify that there is a single ATTENDEE property and that the Originator has permission
            # to send on behalf of that ATTENDEE
            attendees = calendar.getAttendees()
        
            # Must have only one
            if len(attendees) != 1:
                self.log_error("ATTENDEE list in calendar data is wrong: %s" % (calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
            
            # Attendee's Outbox MUST be the request URI
            attendeePrincipal = self.principalForCalendarUserAddress(attendees[0])
            if attendeePrincipal is None or attendeePrincipal.record != self.parent.record:
                self.log_error("ATTENDEE in calendar data does not match owner of Outbox: %s" % (calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))

        # For free-busy do immediate determination of iTIP result rather than fan-out
        self.log_debug("METHOD: %s, Component: %s" % (calendar.propertyValue("METHOD"), calendar.mainType(),))
        if (calendar.propertyValue("METHOD") == "REQUEST") and (calendar.mainType() == "VFREEBUSY"):
            # Extract time range from VFREEBUSY object
            vfreebusies = [v for v in calendar.subcomponents() if v.name() == "VFREEBUSY"]
            if len(vfreebusies) != 1:
                self.log_error("iTIP data is not valid for a VFREEBUSY request: %s" % (calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
            dtstart = vfreebusies[0].getStartDateUTC()
            dtend = vfreebusies[0].getEndDateUTC()
            if dtstart is None or dtend is None:
                self.log_error("VFREEBUSY start/end not valid: %s" % (calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
            timeRange.start = dtstart
            timeRange.end = dtend

            # Look for maksed UID
            excludeUID = calendar.getMaskUID()

            # Do free busy operation
            freebusy = True
        else:
            # Do regular invite (fan-out)
            freebusy = False

        #
        # Accounting
        #
        # Note that we associate logging with the organizer, not the
        # originator, which is good for looking for why something
        # shows up in a given principal's calendars, rather than
        # tracking the activities of a specific user.
        #
        if accountingEnabled("iTIP", organizerPrincipal):
            emitAccounting(
                "iTIP", organizerPrincipal,
                "Originator: %s\nRecipients: %s\n\n%s"
                % (originator, ", ".join(recipients), str(calendar))
            )

        # Prepare for multiple responses
        responses = ScheduleResponseQueue("POST", responsecode.OK)
    
        # Loop over each recipient and do appropriate action.
        autoresponses = []
        for recipient in recipients:
            # Get the principal resource for this recipient
            principal = self.principalForCalendarUserAddress(recipient)

            # Map recipient to their inbox
            inbox = None
            if principal is None:
                self.log_error("No schedulable principal for calendar user address: %r" % (recipient,))
            else:
                inboxURL = principal.scheduleInboxURL()
                if inboxURL:
                    inbox = yield request.locateResource(inboxURL)
                else:
                    self.log_error("No schedule inbox for principal: %s" % (principal,))

            if inbox is None:
                err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-exists")))
                responses.add(recipient, Failure(exc_value=err), reqstatus="3.7;Invalid Calendar User")
                recipientsState["BAD"] += 1
            
                # Process next recipient
                continue
            else:
                #
                # Check access controls
                #
                try:
                    yield inbox.checkPrivileges(request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef(organizerPrincipal.principalURL())))
                except AccessDeniedError:
                    self.log_error("Could not access Inbox for recipient: %s" % (recipient,))
                    err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-permisions")))
                    responses.add(recipient, Failure(exc_value=err), reqstatus="3.8;No authority")
                    recipientsState["BAD"] += 1
                
                    # Process next recipient
                    continue
    
                # Different behaviour for free-busy vs regular invite
                if freebusy:
                    # Extract the ATTENDEE property matching current recipient from the calendar data
                    cuas = principal.calendarUserAddresses()
                    attendeeProp = calendar.getAttendeeProperty(cuas)
            
                    # Find the current recipients calendar-free-busy-set
                    fbset = yield principal.calendarFreeBusyURIs(request)

                    # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
                    fbinfo = ([], [], [])
                
                    try:
                        # Process the availability property from the Inbox.
                        has_prop = yield inbox.hasProperty((calendarserver_namespace, "calendar-availability"), request)
                        if has_prop:
                            availability = yield inbox.readProperty((calendarserver_namespace, "calendar-availability"), request)
                            availability = availability.calendar()
                            report_common.processAvailabilityFreeBusy(availability, fbinfo, timeRange)

                        # Check to see if the recipient is the same calendar user as the organizer.
                        # Needed for masked UID stuff.
                        same_calendar_user = organizerPrincipal.principalURL() == principal.principalURL()

                        # Now process free-busy set calendars
                        matchtotal = 0
                        for calendarResourceURL in fbset:
                            calendarResource = yield request.locateResource(calendarResourceURL)
                            if calendarResource is None or not calendarResource.exists() or not isCalendarCollectionResource(calendarResource):
                                # We will ignore missing calendars. If the recipient has failed to
                                # properly manage the free busy set that should not prevent us from working.
                                continue
                         
                            matchtotal = yield report_common.generateFreeBusyInfo(
                                request,
                                calendarResource,
                                fbinfo,
                                timeRange,
                                matchtotal,
                                excludeuid = excludeUID,
                                organizer = organizer,
                                same_calendar_user = same_calendar_user
                            )
                    
                        # Build VFREEBUSY iTIP reply for this recipient
                        fbresult = report_common.buildFreeBusyResult(
                            fbinfo,
                            timeRange,
                            organizer = calendar.getOrganizerProperty(),
                            attendee = attendeeProp,
                            uid = calendar.resourceUID(),
                            method="REPLY"
                        )

                        responses.add(recipient, responsecode.OK, reqstatus="2.0;Success", calendar=fbresult)
                        recipientsState["OK"] += 1
                
                    except:
                        self.log_error("Could not determine free busy information: %s" % (recipient,))
                        err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
                        responses.add(recipient, Failure(exc_value=err), reqstatus="3.8;No authority")
                        recipientsState["BAD"] += 1
                
                else:
                    # Hash the iCalendar data for use as the last path element of the URI path
                    name = md5.new(str(calendar) + str(time.time()) + inbox.fp.path).hexdigest() + ".ics"
                
                    # Get a resource for the new item
                    childURL = joinURL(inboxURL, name)
                    child = yield request.locateResource(childURL)
            
                    try:
                        # Copy calendar to inbox (doing fan-out)
                        yield maybeDeferred(
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
                    except: # FIXME: bare except
                        self.log_error("Could not store data in Inbox : %s" % (inbox,))
                        err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
                        responses.add(recipient, Failure(exc_value=err), reqstatus="3.8;No authority")
                        recipientsState["BAD"] += 1
                    else:
                        responses.add(recipient, responsecode.OK, reqstatus="2.0;Success")
                        recipientsState["OK"] += 1
        
                        # Store CALDAV:originator property
                        child.writeDeadProperty(caldavxml.Originator(davxml.HRef(originator)))
                    
                        # Store CALDAV:recipient property
                        child.writeDeadProperty(caldavxml.Recipient(davxml.HRef(recipient)))
                    
                        # Look for auto-schedule option
                        if principal.autoSchedule():
                            autoresponses.append((principal, inbox, child))

        # Now we have to do auto-respond
        if len(autoresponses) != 0:
            # First check that we have a method that we can auto-respond to
            if not itip.canAutoRespond(calendar):
                autoresponses = []
            
        # Now do the actual auto response
        for principal, inbox, child in autoresponses:
            # Add delayed reactor task to handle iTIP responses
            reactor.callLater(0.0, itip.handleRequest, *(request, principal, inbox, calendar.duplicate(), child)) #@UndefinedVariable
            #reactor.callInThread(itip.handleRequest, *(request, principal, inbox, calendar.duplicate(), child)) #@UndefinedVariable

        # Return with final response if we are done
        returnValue(responses.response())

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

class ScheduleResponseQueue (LoggingMixIn):
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
            self.log_error("Error during %s for %s: %s" % (self.method, recipient, message))

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
