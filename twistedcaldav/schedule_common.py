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
from twisted.internet.defer import deferredGenerator, maybeDeferred, waitForDeferred
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse, errorForFailure, messageForFailure, statusForFailure
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError, Response
from twisted.web2.http_headers import MimeType
from twistedcaldav import caldavxml
from twistedcaldav import logging
from twistedcaldav.caldavxml import caldav_namespace, TimeRange
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.ical import Component
from twistedcaldav.itip import iTipProcessor
from twistedcaldav.method import report_common
from twistedcaldav.method.put_common import StoreCalendarObjectResource
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.servertoserver import ServerToServer
from twistedcaldav.servertoserver import ServerToServerRequest
import itertools
import md5
import re
import socket
import time



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
        self.timerange = None
        self.excludeuid = None
        self.logsystem = "Scheduling"
    
    @deferredGenerator
    def doSchedulingViaPOST(self):
        """
        The Scheduling POST operation.
        """
    
        # Do some extra authorization checks
        self.checkAuthorization()

        if logging.canLog("debug"):
            d = waitForDeferred(logging.logRequest("Received POST request:", self.request, system=self.logsystem))
            yield d
            d.getResult()

        # Load various useful bits doing some basic checks on those
        self.loadOriginator()
        self.loadRecipients()
        d = waitForDeferred(self.loadCalendar())
        yield d
        d.getResult()

        # Check validity of Originator header.
        self.checkOriginator()
    
        # Get recipient details.
        d = waitForDeferred(self.checkRecipients())
        yield d
        d.getResult()
    
        # Check calendar data.
        self.checkCalendarData()
    
        # Check validity of ORGANIZER
        self.checkOrganizer()
    
        # Do security checks (e.g. spoofing)
        self.securityChecks()
    
        # Do scheduling tasks
        response = waitForDeferred(self.generateSchedulingResponse())
        yield response
        response = response.getResult()

        if logging.canLog("debug"):
            d = waitForDeferred(logging.logResponse("Sending POST response:", response, system=self.logsystem))
            yield d
            d.getResult()

        yield response

    def loadOriginator(self):
        # Must have Originator header
        originator = self.request.headers.getRawHeaders("originator")
        if originator is None or (len(originator) != 1):
            logging.err("POST request must have Originator header", system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-specified")))
        else:
            self.originator = originator[0]
    
    def loadRecipients(self):
        # Get list of Recipient headers
        rawrecipients = self.request.headers.getRawHeaders("recipient")
        if rawrecipients is None or (len(rawrecipients) == 0):
            logging.err("POST request must have at least one Recipient header", system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-specified")))
    
        # Recipient header may be comma separated list
        self.recipients = []
        for rawrecipient in rawrecipients:
            for r in rawrecipient.split(","):
                r = r.strip()
                if len(r):
                    self.recipients.append(r)
        
    @deferredGenerator
    def loadCalendar(self):
        # Must be content-type text/calendar
        content_type = self.request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
            logging.err("MIME type %s not allowed in calendar collection" % (content_type,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
    
        # Parse the calendar object from the HTTP request stream
        try:
            d = waitForDeferred(Component.fromIStream(self.request.stream))
            yield d
            self.calendar = d.getResult()
        except:
            logging.err("Error while handling POST: %s" % (Failure(),), system=self.logsystem)
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
            logging.err("POST request calendar component is not valid: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
    
        # Must have a METHOD
        if not self.calendar.isValidMethod():
            logging.err("POST request must have valid METHOD property in calendar component: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
        
        # Verify iTIP behaviour
        if not self.calendar.isValidITIP():
            logging.err("POST request must have a calendar component that satisfies iTIP requirements: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

    def checkForFreeBusy(self):
        if (self.calendar.propertyValue("METHOD") == "REQUEST") and (self.calendar.mainType() == "VFREEBUSY"):
            # Extract time range from VFREEBUSY object
            vfreebusies = [v for v in self.calendar.subcomponents() if v.name() == "VFREEBUSY"]
            if len(vfreebusies) != 1:
                logging.err("iTIP data is not valid for a VFREEBUSY request: %s" % (self.calendar,), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
            dtstart = vfreebusies[0].getStartDateUTC()
            dtend = vfreebusies[0].getEndDateUTC()
            if dtstart is None or dtend is None:
                logging.err("VFREEBUSY start/end not valid: %s" % (self.calendar,), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
            self.timerange = TimeRange(start="20000101T000000Z", end="20070102T000000Z")
            self.timerange.start = dtstart
            self.timerange.end = dtend
    
            # Look for maksed UID
            self.excludeuid = self.calendar.getMaskUID()
    
            # Do free busy operation
            return True
        else:
            # Do regular invite (fan-out)
            return False
    
    def securityChecks(self):
        raise NotImplementedError

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
        
        result = False
        
        for pattern in config.ServerToServer["Local Addresses"]:
            if re.match(pattern, cuaddr) is not None:
                result = True
        
        for pattern in config.ServerToServer["Remote Addresses"]:
            if re.match(pattern, cuaddr) is not None:
                result = False
        
        return result
    
    @deferredGenerator
    def generateSchedulingResponse(self):

        logging.info("METHOD: %s, Component: %s" % (self.calendar.propertyValue("METHOD"), self.calendar.mainType(),), system=self.logsystem)

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
                # Pool remote recipients into a seperate list for processing after the local ones.
                remote_recipients.append(recipient)
            
                # Process next recipient
                continue
            elif isinstance(recipient, Scheduler.LocalCalendarUser):
                #
                # Check access controls
                #
                if isinstance(self.organizer, Scheduler.LocalCalendarUser):
                    try:
                        d = waitForDeferred(recipient.inbox.checkPrivileges(self.request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef(self.organizer.principal.principalURL()))))
                        yield d
                        d.getResult()
                    except AccessDeniedError:
                        logging.err("Could not access Inbox for recipient: %s" % (recipient.cuaddr,), system=self.logsystem)
                        err = HTTPError(ErrorResponse(responsecode.NOT_FOUND, (caldav_namespace, "recipient-permisions")))
                        responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="3.8;No authority")
                    
                        # Process next recipient
                        continue
                else:
                    # TODO: need to figure out how best to do server-to-server authorization.
                    # First thing would be to checkk for DAV:unauthenticated privilege.
                    # Next would be to allow the calendar user address of the organizer/originator to be used
                    # as a principal. 
                    pass
    
                # Different behaviour for free-busy vs regular invite
                if freebusy:
                    d = waitForDeferred(self.generateLocalFreeBusyResponse(recipient, responses, organizerProp, uid))
                else:
                    d = waitForDeferred(self.generateLocalResponse(recipient, responses, autoresponses))
                yield d
                d.getResult()
    
        # Now process remote recipients
        if remote_recipients:
            d = waitForDeferred(self.generateRemoteSchedulingResponses(remote_recipients, responses))
            yield d
            d.getResult()

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
        yield responses.response()
    
    @deferredGenerator
    def generateRemoteSchedulingResponses(self, recipients, responses):
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
            yield None
            return

        # Now we process each server: let's use a DeferredList to aggregate all the Deferred's
        # we will generate for each request. That way we can have parallel requests in progress
        # rather than serialize them.
        deferreds = []
        for server, recipients in groups.iteritems():
            requestor = ServerToServerRequest(self, server, recipients, responses)
            deferreds.append(requestor.doRequest())

        d = waitForDeferred(DeferredList(deferreds))
        yield d
        d.getResult()

    @deferredGenerator
    def generateLocalResponse(self, recipient, responses, autoresponses):
        # Hash the iCalendar data for use as the last path element of the URI path
        calendar_str = str(self.calendar)
        name = md5.new(calendar_str + str(time.time()) + recipient.inbox.fp.path).hexdigest() + ".ics"
    
        # Get a resource for the new item
        childURL = joinURL(recipient.inboxURL, name)
        child = waitForDeferred(self.request.locateResource(childURL))
        yield child
        child = child.getResult()

        # Copy calendar to inbox (doing fan-out)
        try:
            storer = StoreCalendarObjectResource(
                         request=self.request,
                         destination = child,
                         destination_uri = childURL,
                         destinationparent = recipient.inbox,
                         destinationcal = True,
                         calendar = self.calendar,
                         isiTIP = True
                     )
            d = waitForDeferred(storer.run())
            yield d
            d.getResult()
            responses.add(recipient.cuaddr, responsecode.OK, reqstatus="2.0;Success")

            # Store CALDAV:originator property
            child.writeDeadProperty(caldavxml.Originator(davxml.HRef(self.originator.cuaddr)))
        
            # Store CALDAV:recipient property
            child.writeDeadProperty(caldavxml.Recipient(davxml.HRef(recipient.cuaddr)))
        
            # Look for auto-schedule option
            if recipient.principal.autoSchedule():
                autoresponses.append((recipient.principal, recipient.inbox, child))
                
            yield True
        except:
            logging.err("Could not store data in Inbox : %s" % (recipient.inbox,), system=self.logsystem)
            err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
            responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="3.8;No authority")
            yield False
    
    @deferredGenerator
    def generateLocalFreeBusyResponse(self, recipient, responses, organizerProp, uid):

        # Extract the ATTENDEE property matching current recipient from the calendar data
        cuas = recipient.principal.calendarUserAddresses()
        attendeeProp = self.calendar.getAttendeeProperty(cuas)

        remote = isinstance(self.organizer, Scheduler.RemoteCalendarUser)

        try:
            d = waitForDeferred(self.generateAttendeeFreeBusyResponse(
                recipient,
                organizerProp,
                uid,
                attendeeProp,
                remote,
            ))
            yield d
            fbresult = d.getResult()

            responses.add(recipient.cuaddr, responsecode.OK, reqstatus="2.0;Success", calendar=fbresult)
            
            yield True
        except:
            logging.err("Could not determine free busy information: %s" % (recipient.cuaddr,), system=self.logsystem)
            err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-permissions")))
            responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="3.8;No authority")
            
            yield False
    
    @deferredGenerator
    def generateAttendeeFreeBusyResponse(self, recipient, organizerProp, uid, attendeeProp, remote):

        # Find the current recipients calendar-free-busy-set
        fbset = waitForDeferred(recipient.principal.calendarFreeBusyURIs(self.request))
        yield fbset
        fbset = fbset.getResult()

        # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
        fbinfo = ([], [], [])
    
        # Process the availability property from the Inbox.
        has_prop = waitForDeferred(recipient.inbox.hasProperty((calendarserver_namespace, "calendar-availability"), self.request))
        yield has_prop
        has_prop = has_prop.getResult()
        if has_prop:
            availability = waitForDeferred(recipient.inbox.readProperty((calendarserver_namespace, "calendar-availability"), self.request))
            yield availability
            availability = availability.getResult()
            availability = availability.calendar()
            report_common.processAvailabilityFreeBusy(availability, fbinfo, self.timerange)

        # Check to see if the recipient is the same calendar user as the organizer.
        # Needed for masked UID stuff.
        if isinstance(self.organizer, Scheduler.LocalCalendarUser):
            same_calendar_user = self.organizer.principal.principalURL() == recipient.principal.principalURL()
        else:
            same_calendar_user = False

        # Now process free-busy set calendars
        matchtotal = 0
        for calURL in fbset:
            cal = waitForDeferred(self.request.locateResource(calURL))
            yield cal
            cal = cal.getResult()
            if cal is None or not cal.exists() or not isCalendarCollectionResource(cal):
                # We will ignore missing calendars. If the recipient has failed to
                # properly manage the free busy set that should not prevent us from working.
                continue
         
            matchtotal = waitForDeferred(report_common.generateFreeBusyInfo(
                self.request,
                cal,
                fbinfo,
                self.timerange,
                matchtotal,
                excludeuid=self.excludeuid,
                organizer=self.organizer.cuaddr,
                same_calendar_user=same_calendar_user,
                servertoserver=remote))
            yield matchtotal
            matchtotal = matchtotal.getResult()
    
        # Build VFREEBUSY iTIP reply for this recipient
        fbresult = report_common.buildFreeBusyResult(fbinfo, self.timerange, organizer=organizerProp, attendee=attendeeProp, uid=uid, method="REPLY")

        yield fbresult
    
    def generateRemoteResponse(self):
        raise NotImplementedError
    
    def generateRemoteFreeBusyResponse(self):
        raise NotImplementedError
        
class CalDAVScheduler(Scheduler):

    def __init__(self, request, resource):
        super(CalDAVScheduler, self).__init__(request, resource)
        self.logsystem = ("caldav", "Scheduling",)

    def checkAuthorization(self):
        # Must have an authenticated user
        if self.resource.currentPrincipal(self.request) == davxml.Principal(davxml.Unauthenticated()):
            logging.err("Unauthenticated originators not allowed: %s" % (self.originator,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

    def checkOriginator(self):
        """
        Check the validity of the Originator header. Extract the corresponding principal.
        """
    
        # Verify that Originator is a valid calendar user
        originator_principal = self.resource.principalForCalendarUserAddress(self.originator)
        if originator_principal is None:
            # Local requests MUST have a principal.
            logging.err("Could not find principal for originator: %s" % (self.originator,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
        else:
            # Must have a valid Inbox.
            inboxURL = originator_principal.scheduleInboxURL()
            if inboxURL is None:
                logging.err("Could not find inbox for originator: %s" % (self.originator,), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
        
            # Verify that Originator matches the authenticated user.
            authn_principal = self.resource.currentPrincipal(self.request)
            if davxml.Principal(davxml.HRef(originator_principal.principalURL())) != authn_principal:
                logging.err("Originator: %s does not match authorized user: %s" % (self.originator, authn_principal.children[0],), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

            self.originator = Scheduler.LocalCalendarUser(self.originator, originator_principal)

    @deferredGenerator
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
                    logging.err("No principal for calendar user address: %s" % (recipient,), system=self.logsystem)
                    results.append(Scheduler.InvalidCalendarUser(recipient))
                elif not config.ServerToServer["Enabled"]:
                    logging.err("Unknown calendar user address: %s" % (recipient,), system=self.logsystem)
                    results.append(Scheduler.InvalidCalendarUser(recipient))
                else:
                    results.append(Scheduler.RemoteCalendarUser(recipient))
            else:
                # Map recipient to their inbox
                inbox = None
                inboxURL = principal.scheduleInboxURL()
                if inboxURL:
                    inbox = waitForDeferred(self.request.locateResource(inboxURL))
                    yield inbox
                    inbox = inbox.getResult()

                if inbox:
                    results.append(Scheduler.LocalCalendarUser(recipient, principal, inbox, inboxURL))
                else:
                    logging.err("No schedule inbox for principal: %s" % (principal,), system=self.logsystem)
                    results.append(Scheduler.InvalidCalendarUser(recipient))
        
        self.recipients = results

    def checkOrganizer(self):
        """
        Check the validity of the ORGANIZER value. ORGANIZER must be local.
        """
        
        # Verify that the ORGANIZER's cu address maps to a valid user
        organizer = self.calendar.getOrganizer()
        if organizer:
            orgprincipal = self.resource.principalForCalendarUserAddress(organizer)
            if orgprincipal:
                outboxURL = orgprincipal.scheduleOutboxURL()
                if outboxURL:
                    self.organizer = Scheduler.LocalCalendarUser(organizer, orgprincipal)
                else:
                    logging.err("No outbox for ORGANIZER in calendar data: %s" % (self.calendar,), system=self.logsystem)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
            elif self.isCalendarUserAddressInMyDomain(organizer):
                logging.err("No principal for ORGANIZER in calendar data: %s" % (self.calendar,), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
            else:
                self.organizer = Scheduler.RemoteCalendarUser(organizer) 
        else:
            logging.err("ORGANIZER missing in calendar data: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))

    def checkOrganizerAsOriginator(self):
        # Make sure that the ORGANIZER's Outbox is the request URI
        if self.organizer.principal.scheduleOutboxURL() != self.request.uri:
            logging.err("Wrong outbox for ORGANIZER in calendar data: %s" % (self.calendar,), system=self.logsystem)
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
            logging.err("Wrong number of ATTENDEEs in calendar data: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
        attendee = attendees[0]
    
        # Attendee's Outbox MUST be the request URI
        aprincipal = self.resource.principalForCalendarUserAddress(attendee)
        if aprincipal:
            aoutboxURL = aprincipal.scheduleOutboxURL()
            if aoutboxURL is None or aoutboxURL != self.request.uri:
                logging.err("ATTENDEE in calendar data does not match owner of Outbox: %s" % (self.calendar,), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
        else:
            logging.err("Unkown ATTENDEE in calendar data: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
    
    def securityChecks(self):
        """
        Check that the orginator has the appropriate rights to send this type of iTIP message.
        """
    
        # Prevent spoofing of ORGANIZER with specific METHODs when local
        if self.calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER"):
            self.checkOrganizerAsOriginator()
    
        # Prevent spoofing when doing reply-like METHODs
        elif self.calendar.propertyValue("METHOD") in ("REPLY", "COUNTER", "REFRESH"):
            self.checkAttendeeAsOriginator()
            
        else:
            logging.err("Unknown iTIP METHOD for security checks: %s" % (self.calendar.propertyValue("METHOD"),), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

class ServerToServerScheduler(Scheduler):

    def __init__(self, request, resource):
        super(ServerToServerScheduler, self).__init__(request, resource)
        self.logsystem = ("Server-to-server Recieve", "Scheduling",)

    def checkAuthorization(self):
        # Must have an unauthenticated user
        if self.resource.currentPrincipal(self.request) != davxml.Principal(davxml.Unauthenticated()):
            logging.err("Authenticated originators not allowed: %s" % (self.originator,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

    def checkOriginator(self):
        """
        Check the validity of the Originator header.
        """
    
        # For remote requests we do not allow the originator to be a local user or one within our domain.
        originator_principal = self.resource.principalForCalendarUserAddress(self.originator)
        if originator_principal or self.isCalendarUserAddressInMyDomain(self.originator):
            logging.err("Cannot use originator that is on this server: %s" % (self.originator,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))
        else:
            self.originator = Scheduler.RemoteCalendarUser(self.originator)
            
        # We will only accept originator in known domains.
        servermgr = ServerToServer()
        server = servermgr.mapDomain(self.originator.domain)
        if not server or not server.allow_from:
            logging.err("Originator not on recognized server: %s" % (self.originator,), system=self.logsystem)
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
                        if re.match(pattern, host) is not None:
                            matched = True
                            break
                    else:
                        continue
                    break
                        
            if not matched:
                logging.err("Originator not on allowed server: %s" % (self.originator,), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "originator-allowed")))

    @deferredGenerator
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
                    logging.err("No principal for calendar user address: %s" % (recipient,), system=self.logsystem)
                    results.append(Scheduler.InvalidCalendarUser(recipient))
                else:
                    logging.err("Unknown calendar user address: %s" % (recipient,), system=self.logsystem)
                    results.append(Scheduler.InvalidCalendarUser(recipient))
            else:
                # Map recipient to their inbox
                inbox = None
                inboxURL = principal.scheduleInboxURL()
                if inboxURL:
                    inbox = waitForDeferred(self.request.locateResource(inboxURL))
                    yield inbox
                    inbox = inbox.getResult()

                if inbox:
                    results.append(Scheduler.LocalCalendarUser(recipient, principal, inbox, inboxURL))
                else:
                    logging.err("No schedule inbox for principal: %s" % (principal,), system=self.logsystem)
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
            orgprincipal = self.resource.principalForCalendarUserAddress(organizer)
            if orgprincipal:
                logging.err("Invalid ORGANIZER in calendar data: %s" % (self.calendar,), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
            elif self.isCalendarUserAddressInMyDomain(organizer):
                logging.err("Unsupported ORGANIZER in calendar data: %s" % (self.calendar,), system=self.logsystem)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "organizer-allowed")))
            else:
                self.organizer = Scheduler.RemoteCalendarUser(organizer)
        else:
            logging.err("ORGANIZER missing in calendar data: %s" % (self.calendar,), system=self.logsystem)
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
            logging.err("Wrong number of ATTENDEEs in calendar data: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
        attendee = attendees[0]
    
        # Attendee cannot be local.
        aprincipal = self.resource.principalForCalendarUserAddress(attendee)
        if aprincipal:
            logging.err("Invalid ATTENDEE in calendar data: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
        elif self.isCalendarUserAddressInMyDomain(attendee):
            logging.err("Unkown ATTENDEE in calendar data: %s" % (self.calendar,), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "attendee-allowed")))
    
        # TODO: in this case we should check that the ORGANIZER is the sole recipient.

    def securityChecks(self):
        """
        Check that the orginator has the appropriate rights to send this type of iTIP message.
        """

        # Prevent spoofing of ORGANIZER with specific METHODs when local
        if self.calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER"):
            self.checkOrganizerAsOriginator()
    
        # Prevent spoofing when doing reply-like METHODs
        elif self.calendar.propertyValue("METHOD") in ("REPLY", "COUNTER", "REFRESH"):
            self.checkAttendeeAsOriginator()
            
        else:
            logging.err("Unknown iTIP METHOD for security checks: %s" % (self.calendar.propertyValue("METHOD"),), system=self.logsystem)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

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
            logging.err("Error during %s for %s: %s" % (self.method, recipient, message), system="Scheduling")

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
