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
##

"""
CalDAV/Server-to-Server scheduling behavior.
"""

__all__ = [
    "Scheduler",
    "CalDAVScheduler",
    "ServerToServerScheduler",
]

from twisted.internet import reactor
from twisted.internet.defer import DeferredList
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse, errorForFailure, messageForFailure, statusForFailure
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError, Response
from twisted.web2.http_headers import MimeType
from twistedcaldav import caldavxml
from twistedcaldav.accounting import accountingEnabled, emitAccounting
from twistedcaldav.log import Logger, LoggingMixIn
from twistedcaldav.caldavxml import caldav_namespace, TimeRange
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.ical import Component
from twistedcaldav.itip import iTipProcessor
from twistedcaldav.method import report_common
from twistedcaldav.method.put_common import StoreCalendarObjectResource
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.schedule_imip import ServerToIMip
from twistedcaldav.servertoserver import ServerToServer
from twistedcaldav.servertoserver import ServerToServerRequest
import itertools
import md5
import re
import socket
import time

log = Logger()

class Scheduler(object):
    
    class CalendarUser(object):
        def __init__(self, cuaddr):
            self.cuaddr = cuaddr

    class LocalCalendarUser(CalendarUser):
        def __init__(self, cuaddr, principal, inbox=None, inboxURL=None):
            self.cuaddr = cuaddr
            self.principal = principal
            self.inbox = inbox
            self.inboxURL = inboxURL
        
        def __str__(self):
            return "Local calendar user: %s" % (self.cuaddr,)

    class RemoteCalendarUser(CalendarUser):
        def __init__(self, cuaddr):
            self.cuaddr = cuaddr
            self.extractDomain()

        def __str__(self):
            return "Remote calendar user: %s" % (self.cuaddr,)
        
        def extractDomain(self):
            if self.cuaddr.startswith("mailto:"):
                splits = self.cuaddr[7:].split("?")
                self.domain = splits[0].split("@")[1]
            elif self.cuaddr.startswith("http://") or self.cuaddr.startswith("https://"):
                splits = self.cuaddr.split(":")[1][2:].split("/")
                self.domain = splits[0]
            else:
                self.domain = ""

    class InvalidCalendarUser(CalendarUser):
        
        def __str__(self):
            return "Invalid calendar user: %s" % (self.cuaddr,)

            
    def __init__(self, request, resource):
        self.request = request
        self.resource = resource
        self.originator = None
        self.recipients = None
        self.calendar = None
        self.organizer = None
        self.timeRange = None
        self.excludeUID = None
    
    @inlineCallbacks
    def doSchedulingViaPOST(self):
        """
        The Scheduling POST operation.
        """
    
        # Do some extra authorization checks
        self.checkAuthorization()

        #d = waitForDeferred(log.logRequest("debug", "Received POST request:", self.request))
        #yield d
        #d.getResult()

        # Load various useful bits doing some basic checks on those
        self.loadOriginator()
        self.loadRecipients()
        yield self.loadCalendar()

        # Check validity of Originator header.
        self.checkOriginator()
    
        # Get recipient details.
        yield self.checkRecipients()
    
        # Check calendar data.
        self.checkCalendarData()
    
        # Check validity of ORGANIZER
        self.checkOrganizer()
    
        # Do security checks (e.g. spoofing)
        self.securityChecks()
    
        # Generate accounting information
        self.doAccounting()

        # Do scheduling tasks
        response = yield self.generateSchedulingResponse()

        #yield log.logResponse("debug", "Sending POST response:", response)

        returnValue(response)

    def loadOriginator(self):
        # Must have Originator header
        originator = self.request.headers.getRawHeaders("originator")
        if originator is None or (len(originator) != 1):
            log.err("POST request must have Originator header")
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-specified")))
        else:
            self.originator = originator[0]
    
    def loadRecipients(self):
        # Get list of Recipient headers
        rawRecipients = self.request.headers.getRawHeaders("recipient")
        if rawRecipients is None or (len(rawRecipients) == 0):
            log.err("POST request must have at least one Recipient header")
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-specified")))
    
        # Recipient header may be comma separated list
        self.recipients = []
        for rawRecipient in rawRecipients:
            for r in rawRecipient.split(","):
                r = r.strip()
                if len(r):
                    self.recipients.append(r)
        
    @inlineCallbacks
    def loadCalendar(self):
        # Must be content-type text/calendar
        contentType = self.request.headers.getHeader("content-type")
        if contentType is not None and (contentType.mediaType, contentType.mediaSubtype) != ("text", "calendar"):
            log.err("MIME type %s not allowed in calendar collection" % (contentType,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
    
        # Parse the calendar object from the HTTP request stream
        try:
            self.calendar = yield Component.fromIStream(self.request.stream)
        except:
            # FIXME: Bare except
            log.err("Error while handling POST: %s" % (Failure(),))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

    def checkAuthorization(self):
        raise NotImplementedError

    def checkOriginator(self):
        raise NotImplementedError

    def checkRecipient(self):
        raise NotImplementedError

    def checkOrganizer(self):
        raise NotImplementedError

    def checkOrganizerAsOriginator(self):
        raise NotImplementedError

    def checkAttendeeAsOriginator(self):
        raise NotImplementedError

    def checkCalendarData(self):
        # Must be a valid calendar
        try:
            self.calendar.validCalendarForCalDAV()
        except ValueError:
            log.err("POST request calendar component is not valid: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
    
        # Must have a METHOD
        if not self.calendar.isValidMethod():
            log.err("POST request must have valid METHOD property in calendar component: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
        
        # Verify iTIP behavior
        if not self.calendar.isValidITIP():
            log.err("POST request must have a calendar component that satisfies iTIP requirements: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

        # X-CALENDARSERVER-ACCESS is not allowed in Outbox POSTs
        if self.calendar.hasProperty(Component.ACCESS_PROPERTY):
            log.err("X-CALENDARSERVER-ACCESS not allowed in a calendar component POST request: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (calendarserver_namespace, "no-access-restrictions")))
    
    def checkForFreeBusy(self):
        if (self.calendar.propertyValue("METHOD") == "REQUEST") and (self.calendar.mainType() == "VFREEBUSY"):
            # Extract time range from VFREEBUSY object
            vfreebusies = [v for v in self.calendar.subcomponents() if v.name() == "VFREEBUSY"]
            if len(vfreebusies) != 1:
                log.err("iTIP data is not valid for a VFREEBUSY request: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
            dtstart = vfreebusies[0].getStartDateUTC()
            dtend = vfreebusies[0].getEndDateUTC()
            if dtstart is None or dtend is None:
                log.err("VFREEBUSY start/end not valid: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
            self.timeRange = TimeRange(start="20000101T000000Z", end="20070102T000000Z")
            self.timeRange.start = dtstart
            self.timeRange.end = dtend
    
            # Look for masked UID
            self.excludeUID = self.calendar.getMaskUID()
    
            # Do free busy operation
            return True
        else:
            # Do regular invite (fan-out)
            return False
    
    def securityChecks(self):
        raise NotImplementedError

    def doAccounting(self):
        #
        # Accounting
        #
        # Note that we associate logging with the organizer, not the
        # originator, which is good for looking for why something
        # shows up in a given principal's calendars, rather than
        # tracking the activities of a specific user.
        #
        if isinstance(self.organizer, Scheduler.LocalCalendarUser):
            if accountingEnabled("iTIP", self.organizer.principal):
                emitAccounting(
                    "iTIP", self.organizer.principal,
                    "Originator: %s\nRecipients:\n%s\n%s"
                    % (
                        str(self.originator),
                        "".join(["    %s\n" % (recipient,) for recipient in self.recipients]),
                        str(self.calendar)
                    )
                )

    @staticmethod
    def isCalendarUserAddressInMyDomain(cuaddr):
        """
        Check whether the supplied calendar user address corresponds to one that ought to be within
        this server's domain.
        
        For now we will try to match email and http domains against ones in our config.
         
        @param cuaddr: the calendar user address to check.
        @type cuaddr: C{str}
        
        @return: C{True} if the address is within the server's domain,
            C{False} otherwise.
        """
        
        if config.ServerToServer["Email Domain"] and cuaddr.startswith("mailto:"):
            splits = cuaddr[7:].split("?")
            domain = config.ServerToServer["Email Domain"]
            return splits[0].endswith(domain)
        elif config.ServerToServer["HTTP Domain"] and (cuaddr.startswith("http://") or cuaddr.startswith("https://")):
            splits = cuaddr.split(":")[0][2:].split("?")
            domain = config.ServerToServer["HTTP Domain"]
            return splits[0].endswith(domain)
        elif cuaddr.startswith("/"):
            # Assume relative HTTP URL - i.e. on this server
            return True
        
        result = False
        
        for pattern in config.ServerToServer["Local Addresses"]:
            try:
                if re.match(pattern, cuaddr) is not None:
                    result = True
            except re.error:
                log.debug("Invalid regular expression for ServerToServer configuration 'Local Addresses': %s" % (pattern,))
            
        for pattern in config.ServerToServer["Remote Addresses"]:
            try:
                if re.match(pattern, cuaddr) is not None:
                    result = False
            except re.error:
                log.debug("Invalid regular expression for ServerToServer configuration 'Remote Addresses': %s" % (pattern,))
        
        return result
    
    @inlineCallbacks
    def generateSchedulingResponse(self):

        log.info("METHOD: %s, Component: %s" % (self.calendar.propertyValue("METHOD"), self.calendar.mainType(),))

        # For free-busy do immediate determination of iTIP result rather than fan-out
        freebusy = self.checkForFreeBusy()

        # Prepare for multiple responses
        responses = ScheduleResponseQueue("POST", responsecode.OK)
    
        # Extract the ORGANIZER property and UID value from the calendar data for use later
        organizerProp = self.calendar.getOrganizerProperty()
        uid = self.calendar.resourceUID()

        # Loop over each recipient and do appropriate action.
        remote_recipients = []
        autoresponses = []
        for recipient in self.recipients:
    
            if isinstance(recipient, Scheduler.InvalidCalendarUser):
                err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-exists")))
                responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="3.7;Invalid Calendar User")
            
                # Process next recipient
                continue
            elif isinstance(recipient, Scheduler.RemoteCalendarUser):
                # Pool remote recipients into a separate list for processing after the local ones.
                remote_recipients.append(recipient)
            
                # Process next recipient
                continue
            elif isinstance(recipient, Scheduler.LocalCalendarUser):
                #
                # Check access controls
                #
                if isinstance(self.organizer, Scheduler.LocalCalendarUser):
                    try:
                        yield recipient.inbox.checkPrivileges(self.request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef(self.organizer.principal.principalURL())))
                    except AccessDeniedError:
                        log.err("Could not access Inbox for recipient: %s" % (recipient.cuaddr,))
                        err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-permissions")))
                        responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="3.8;No authority")
                    
                        # Process next recipient
                        continue
                else:
                    # TODO: need to figure out how best to do server-to-server authorization.
                    # First thing would be to check for DAV:unauthenticated privilege.
                    # Next would be to allow the calendar user address of the organizer/originator to be used
                    # as a principal. 
                    pass
    
                # Different behavior for free-busy vs regular invite
                if freebusy:
                    yield self.generateLocalFreeBusyResponse(recipient, responses, organizerProp, uid)
                else:
                    yield self.generateLocalResponse(recipient, responses, autoresponses)
    
        # Now process remote recipients
        if remote_recipients:
            #yield self.generateRemoteSchedulingResponses(remote_recipients, responses, freebusy)
            yield self.generateIMIPSchedulingResponses(remote_recipients, responses, freebusy)

        # Now we have to do auto-respond
        if len(autoresponses) != 0:
            # First check that we have a method that we can auto-respond to
            if not iTipProcessor.canAutoRespond(self.calendar):
                autoresponses = []
            
        # Now do the actual auto response
        for principal, inbox, child in autoresponses:
            # Add delayed reactor task to handle iTIP responses
            itip = iTipProcessor()
            reactor.callLater(0.0, itip.handleRequest, *(self.request, principal, inbox, self.calendar.duplicate(), child)) #@UndefinedVariable
    
        # Return with final response if we are done
        returnValue(responses.response())
    
    @inlineCallbacks
    def generateRemoteSchedulingResponses(self, recipients, responses, freebusy):
        """
        Generate scheduling responses for remote recipients.
        """
        
        # Group recipients by server so that we can do a single request with multiple recipients
        # to each different server.
        groups = {}
        servermgr = ServerToServer()
        for recipient in recipients:
            # Map the recipient's domain to a server
            server = servermgr.mapDomain(recipient.domain)
            if not server:
                # Cannot do server-to-server for this recipient.
                err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-allowed")))
                responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="5.3;No scheduling support for user")
            
                # Process next recipient
                continue
            
            if not server.allow_to:
                # Cannot do server-to-server outgoing requests for this server.
                err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-allowed")))
                responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="5.1;Service unavailable")
            
                # Process next recipient
                continue
            
            groups.setdefault(server, []).append(recipient)
        
        if len(groups) == 0:
            returnValue(None)

        # Now we process each server: let's use a DeferredList to aggregate all the Deferred's
        # we will generate for each request. That way we can have parallel requests in progress
        # rather than serialize them.
        deferreds = []
        for server, recipients in groups.iteritems():
            requestor = ServerToServerRequest(self, server, recipients, responses)
            deferreds.append(requestor.doRequest())

        yield DeferredList(deferreds)

    @inlineCallbacks
    def generateIMIPSchedulingResponses(self, recipients, responses, freebusy):
        """
        Generate scheduling responses for iMIP recipients.
        """
        
        # Now we process each server: let's use a DeferredList to aggregate all the Deferred's
        # we will generate for each request. That way we can have parallel requests in progress
        # rather than serialize them.
        
        requestor = ServerToIMip(self, recipients, responses)
        yield requestor.doEMail(freebusy)

    @inlineCallbacks
    def generateLocalResponse(self, recipient, responses, autoresponses):
        # Hash the iCalendar data for use as the last path element of the URI path
        calendar_str = str(self.calendar)
        name = md5.new(calendar_str + str(time.time()) + recipient.inbox.fp.path).hexdigest() + ".ics"
    
        # Get a resource for the new item
        childURL = joinURL(recipient.inboxURL, name)
        child = yield self.request.locateResource(childURL)

        # Copy calendar to inbox (doing fan-out)
        try:
            yield StoreCalendarObjectResource(
                         request=self.request,
                         destination = child,
                         destination_uri = childURL,
                         destinationparent = recipient.inbox,
                         destinationcal = True,
                         calendar = self.calendar,
                         isiTIP = True
                     ).run()
        except:
            # FIXME: Bare except
            log.err("Could not store data in Inbox : %s" % (recipient.inbox,))
            err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
            responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="3.8;No authority")
            returnValue(False)
        else:
            responses.add(recipient.cuaddr, responsecode.OK, reqstatus="2.0;Success")

            # Store CALDAV:originator property
            child.writeDeadProperty(caldavxml.Originator(davxml.HRef(self.originator.cuaddr)))
        
            # Store CALDAV:recipient property
            child.writeDeadProperty(caldavxml.Recipient(davxml.HRef(recipient.cuaddr)))
        
            # Look for auto-schedule option
            if recipient.principal.autoSchedule():
                autoresponses.append((recipient.principal, recipient.inbox, child))
                
            returnValue(True)
    
    @inlineCallbacks
    def generateLocalFreeBusyResponse(self, recipient, responses, organizerProp, uid):

        # Extract the ATTENDEE property matching current recipient from the calendar data
        cuas = recipient.principal.calendarUserAddresses()
        attendeeProp = self.calendar.getAttendeeProperty(cuas)

        remote = isinstance(self.organizer, Scheduler.RemoteCalendarUser)

        try:
            fbresult = yield self.generateAttendeeFreeBusyResponse(
                recipient,
                organizerProp,
                uid,
                attendeeProp,
                remote,
            )
        except:
            log.err("Could not determine free busy information: %s" % (recipient.cuaddr,))
            err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
            responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="3.8;No authority")
            returnValue(False)
        else:
            responses.add(recipient.cuaddr, responsecode.OK, reqstatus="2.0;Success", calendar=fbresult)
            returnValue(True)
    
    @inlineCallbacks
    def generateAttendeeFreeBusyResponse(self, recipient, organizerProp, uid, attendeeProp, remote):

        # Find the current recipients calendar-free-busy-set
        fbset = yield recipient.principal.calendarFreeBusyURIs(self.request)

        # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
        fbinfo = ([], [], [])
    
        # Process the availability property from the Inbox.
        has_prop = yield recipient.inbox.hasProperty((calendarserver_namespace, "calendar-availability"), self.request)
        if has_prop:
            availability = yield recipient.inbox.readProperty((calendarserver_namespace, "calendar-availability"), self.request)
            availability = availability.calendar()
            report_common.processAvailabilityFreeBusy(availability, fbinfo, self.timeRange)

        # Check to see if the recipient is the same calendar user as the organizer.
        # Needed for masked UID stuff.
        if isinstance(self.organizer, Scheduler.LocalCalendarUser):
            same_calendar_user = self.organizer.principal.principalURL() == recipient.principal.principalURL()
        else:
            same_calendar_user = False

        # Now process free-busy set calendars
        matchtotal = 0
        for calendarResourceURL in fbset:
            calendarResource = yield self.request.locateResource(calendarResourceURL)
            if calendarResource is None or not calendarResource.exists() or not isCalendarCollectionResource(calendarResource):
                # We will ignore missing calendars. If the recipient has failed to
                # properly manage the free busy set that should not prevent us from working.
                continue
         
            matchtotal = yield report_common.generateFreeBusyInfo(
                self.request,
                calendarResource,
                fbinfo,
                self.timeRange,
                matchtotal,
                excludeuid = self.excludeUID,
                organizer = self.organizer.cuaddr,
                same_calendar_user = same_calendar_user,
                servertoserver=remote)
    
        # Build VFREEBUSY iTIP reply for this recipient
        fbresult = report_common.buildFreeBusyResult(
            fbinfo,
            self.timeRange,
            organizer = organizerProp,
            attendee = attendeeProp,
            uid = uid,
            method = "REPLY"
        )

        returnValue(fbresult)
        
class CalDAVScheduler(Scheduler):

    def checkAuthorization(self):
        # Must have an authenticated user
        if self.resource.currentPrincipal(self.request) == davxml.Principal(davxml.Unauthenticated()):
            log.err("Unauthenticated originators not allowed: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

    def checkOriginator(self):
        """
        Check the validity of the Originator header. Extract the corresponding principal.
        """
    
        # Verify that Originator is a valid calendar user
        originatorPrincipal = self.resource.principalForCalendarUserAddress(self.originator)
        if originatorPrincipal is None:
            # Local requests MUST have a principal.
            log.err("Could not find principal for originator: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
        else:
            # Must have a valid Inbox.
            inboxURL = originatorPrincipal.scheduleInboxURL()
            if inboxURL is None:
                log.err("Could not find inbox for originator: %s" % (self.originator,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
        
            # Verify that Originator matches the authenticated user.
            authn_principal = self.resource.currentPrincipal(self.request)
            if davxml.Principal(davxml.HRef(originatorPrincipal.principalURL())) != authn_principal:
                log.err("Originator: %s does not match authorized user: %s" % (self.originator, authn_principal.children[0],))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

            self.originator = Scheduler.LocalCalendarUser(self.originator, originatorPrincipal)

    @inlineCallbacks
    def checkRecipients(self):
        """
        Check the validity of the Recipient header values. Map these into local or
        remote CalendarUsers.
        """
        
        results = []
        for recipient in self.recipients:
            # Get the principal resource for this recipient
            principal = self.resource.principalForCalendarUserAddress(recipient)
            
            # If no principal we may have a remote recipient but we should check whether
            # the address is one that ought to be on our server and treat that as a missing
            # user. Also if server-to-server is not enabled then remote addresses are not allowed.
            if principal is None:
                if self.isCalendarUserAddressInMyDomain(recipient):
                    log.err("No schedulable principal for calendar user address: %s" % (recipient,))
                    results.append(Scheduler.InvalidCalendarUser(recipient))
                elif not config.ServerToServer["Enabled"]:
                    log.err("Unknown calendar user address: %s" % (recipient,))
                    results.append(Scheduler.InvalidCalendarUser(recipient))
                else:
                    results.append(Scheduler.RemoteCalendarUser(recipient))
            else:
                # Map recipient to their inbox
                inbox = None
                inboxURL = principal.scheduleInboxURL()
                if inboxURL:
                    inbox = yield self.request.locateResource(inboxURL)

                if inbox:
                    results.append(Scheduler.LocalCalendarUser(recipient, principal, inbox, inboxURL))
                else:
                    log.err("No schedule inbox for principal: %s" % (principal,))
                    results.append(Scheduler.InvalidCalendarUser(recipient))
        
        self.recipients = results

    def checkOrganizer(self):
        """
        Check the validity of the ORGANIZER value. ORGANIZER must be local.
        """
        
        # Verify that the ORGANIZER's cu address maps to a valid user
        organizer = self.calendar.getOrganizer()
        if organizer:
            organizerPrincipal = self.resource.principalForCalendarUserAddress(organizer)
            if organizerPrincipal:
                outboxURL = organizerPrincipal.scheduleOutboxURL()
                if outboxURL:
                    self.organizer = Scheduler.LocalCalendarUser(organizer, organizerPrincipal)
                else:
                    log.err("No outbox for ORGANIZER in calendar data: %s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
            elif self.isCalendarUserAddressInMyDomain(organizer):
                log.err("No principal for ORGANIZER in calendar data: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
            else:
                self.organizer = Scheduler.RemoteCalendarUser(organizer) 
        else:
            log.err("ORGANIZER missing in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

    def checkOrganizerAsOriginator(self):

        # Make sure that the ORGANIZER is local
        if not isinstance(self.organizer, Scheduler.LocalCalendarUser):
            log.err("ORGANIZER is not local to server in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

        # Make sure that the ORGANIZER's Outbox is the request URI
        if self.organizer.principal.scheduleOutboxURL() != self.request.uri:
            log.err("Wrong outbox for ORGANIZER in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

    def checkAttendeeAsOriginator(self):
        """
        Check the validity of the ATTENDEE value as this is the originator of the iTIP message.
        Only local attendees are allowed for message originating from this server.
        """
        
        # Verify that there is a single ATTENDEE property
        attendees = self.calendar.getAttendees()
    
        # Must have only one
        if len(attendees) != 1:
            log.err("Wrong number of ATTENDEEs in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
        attendee = attendees[0]
    
        # Attendee's Outbox MUST be the request URI
        attendeePrincipal = self.resource.principalForCalendarUserAddress(attendee)
        if attendeePrincipal:
            aoutboxURL = attendeePrincipal.scheduleOutboxURL()
            if aoutboxURL is None or aoutboxURL != self.request.uri:
                log.err("ATTENDEE in calendar data does not match owner of Outbox: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
        else:
            log.err("Unknown ATTENDEE in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
    
    def securityChecks(self):
        """
        Check that the originator has the appropriate rights to send this type of iTIP message.
        """
    
        # Prevent spoofing of ORGANIZER with specific METHODs when local
        if self.calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER"):
            self.checkOrganizerAsOriginator()
    
        # Prevent spoofing when doing reply-like METHODs
        elif self.calendar.propertyValue("METHOD") in ("REPLY", "COUNTER", "REFRESH"):
            self.checkAttendeeAsOriginator()
            
        else:
            log.err("Unknown iTIP METHOD for security checks: %s" % (self.calendar.propertyValue("METHOD"),))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

class ServerToServerScheduler(Scheduler):

    def checkAuthorization(self):
        # Must have an unauthenticated user
        if self.resource.currentPrincipal(self.request) != davxml.Principal(davxml.Unauthenticated()):
            log.err("Authenticated originators not allowed: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

    def checkOriginator(self):
        """
        Check the validity of the Originator header.
        """
    
        # For remote requests we do not allow the originator to be a local user or one within our domain.
        originatorPrincipal = self.resource.principalForCalendarUserAddress(self.originator)
        if originatorPrincipal or self.isCalendarUserAddressInMyDomain(self.originator):
            log.err("Cannot use originator that is on this server: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
        else:
            self.originator = Scheduler.RemoteCalendarUser(self.originator)
            
        # We will only accept originator in known domains.
        servermgr = ServerToServer()
        server = servermgr.mapDomain(self.originator.domain)
        if not server or not server.allow_from:
            log.err("Originator not on recognized server: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
        else:
            # Get the request IP and map to hostname.
            clientip = self.request.remoteAddr.host
            
            # First compare as dotted IP
            matched = False
            compare_with = (server.host,) + tuple(server.client_hosts)
            if clientip in compare_with:
                matched = True
            else:
                # Now do hostname lookup
                host, aliases, _ignore_ips = socket.gethostbyaddr(clientip)
                for host in itertools.chain((host,), aliases):
                    # Try simple match first
                    if host in compare_with:
                        matched = True
                        break
                    
                    # Try pattern match next
                    for pattern in compare_with:
                        try:
                            if re.match(pattern, host) is not None:
                                matched = True
                                break
                        except re.error:
                            log.debug("Invalid regular expression for ServerToServer white list for server domain %s: %s" % (self.originator.domain, pattern,))
                    else:
                        continue
                    break
                        
            if not matched:
                log.err("Originator not on allowed server: %s" % (self.originator,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

    @inlineCallbacks
    def checkRecipients(self):
        """
        Check the validity of the Recipient header values. These must all be local as there
        is no concept of server-to-server relaying.
        """
        
        results = []
        for recipient in self.recipients:
            # Get the principal resource for this recipient
            principal = self.resource.principalForCalendarUserAddress(recipient)
            
            # If no principal we may have a remote recipient but we should check whether
            # the address is one that ought to be on our server and treat that as a missing
            # user. Also if server-to-server is not enabled then remote addresses are not allowed.
            if principal is None:
                if self.isCalendarUserAddressInMyDomain(recipient):
                    log.err("No principal for calendar user address: %s" % (recipient,))
                    results.append(Scheduler.InvalidCalendarUser(recipient))
                else:
                    log.err("Unknown calendar user address: %s" % (recipient,))
                    results.append(Scheduler.InvalidCalendarUser(recipient))
            else:
                # Map recipient to their inbox
                inbox = None
                inboxURL = principal.scheduleInboxURL()
                if inboxURL:
                    inbox = yield self.request.locateResource(inboxURL)

                if inbox:
                    results.append(Scheduler.LocalCalendarUser(recipient, principal, inbox, inboxURL))
                else:
                    log.err("No schedule inbox for principal: %s" % (principal,))
                    results.append(Scheduler.InvalidCalendarUser(recipient))
        
        self.recipients = results

    def checkOrganizer(self):
        """
        Delay ORGANIZER check until we know what their role is.
        """
        pass

    def checkOrganizerAsOriginator(self):
        """
        Check the validity of the ORGANIZER value. ORGANIZER must not be local.
        """
        
        # Verify that the ORGANIZER's cu address does not map to a valid user
        organizer = self.calendar.getOrganizer()
        if organizer:
            organizerPrincipal = self.resource.principalForCalendarUserAddress(organizer)
            if organizerPrincipal:
                log.err("Invalid ORGANIZER in calendar data: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
            elif self.isCalendarUserAddressInMyDomain(organizer):
                log.err("Unsupported ORGANIZER in calendar data: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
            else:
                self.organizer = Scheduler.RemoteCalendarUser(organizer)
        else:
            log.err("ORGANIZER missing in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

    def checkAttendeeAsOriginator(self):
        """
        Check the validity of the ATTENDEE value as this is the originator of the iTIP message.
        Only local attendees are allowed for message originating from this server.
        """
        
        # Verify that there is a single ATTENDEE property
        attendees = self.calendar.getAttendees()
    
        # Must have only one
        if len(attendees) != 1:
            log.err("Wrong number of ATTENDEEs in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
        attendee = attendees[0]
    
        # Attendee cannot be local.
        attendeePrincipal = self.resource.principalForCalendarUserAddress(attendee)
        if attendeePrincipal:
            log.err("Invalid ATTENDEE in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
        elif self.isCalendarUserAddressInMyDomain(attendee):
            log.err("Unknown ATTENDEE in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
    
        # TODO: in this case we should check that the ORGANIZER is the sole recipient.

    def securityChecks(self):
        """
        Check that the originator has the appropriate rights to send this type of iTIP message.
        """

        # Prevent spoofing of ORGANIZER with specific METHODs when local
        if self.calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER"):
            self.checkOrganizerAsOriginator()
    
        # Prevent spoofing when doing reply-like METHODs
        elif self.calendar.propertyValue("METHOD") in ("REPLY", "COUNTER", "REFRESH"):
            self.checkAttendeeAsOriginator()
            
        else:
            log.err("Unknown iTIP METHOD for security checks: %s" % (self.calendar.propertyValue("METHOD"),))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

class ScheduleResponseResponse (Response):
    """
    ScheduleResponse L{Response} object.
    Renders itself as a CalDAV:schedule-response XML document.
    """
    def __init__(self, xml_responses, location=None):
        """
        @param xml_responses: an iterable of davxml.Response objects.
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

    def clone(self, clone):
        """
        Add a response cloned from an existing caldavxml.Response element.
        @param clone: the response to clone.
        """
        if not isinstance(clone, caldavxml.Response):
            raise AssertionError("Incorrect element type: %r" % (clone,))

        recipient = clone.childOfType(caldavxml.Recipient)
        request_status = clone.childOfType(caldavxml.RequestStatus)
        calendar_data = clone.childOfType(caldavxml.CalendarData)
        error = clone.childOfType(davxml.Error)
        desc = clone.childOfType(davxml.ResponseDescription)

        children = []
        children.append(recipient)
        children.append(request_status)
        if calendar_data is not None:
            children.append(calendar_data)
        if error is not None:
            children.append(error)
        if desc is not None:
            children.append(desc)
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
