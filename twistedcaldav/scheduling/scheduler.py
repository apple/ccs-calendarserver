
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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

import itertools
import re
import socket
import urlparse

from twisted.internet.abstract import isIPAddress
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.failure import Failure

from twext.python.log import Logger, LoggingMixIn
from twext.web2 import responsecode
from twext.web2.http import HTTPError, Response, StatusResponse
from twext.web2.http_headers import MimeType
from twext.web2.dav import davxml
from twext.web2.dav.http import errorForFailure, messageForFailure, statusForFailure
from twext.web2.dav.http import ErrorResponse

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.accounting import accountingEnabled, emitAccounting
from twistedcaldav.config import config
from twistedcaldav.ical import Component
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.scheduling import addressmapping
from twistedcaldav.scheduling.caldav import ScheduleViaCalDAV
from twistedcaldav.scheduling.cuaddress import InvalidCalendarUser,\
    calendarUserFromPrincipal, OtherServerCalendarUser
from twistedcaldav.scheduling.cuaddress import LocalCalendarUser
from twistedcaldav.scheduling.cuaddress import RemoteCalendarUser
from twistedcaldav.scheduling.cuaddress import EmailCalendarUser
from twistedcaldav.scheduling.cuaddress import PartitionedCalendarUser
from twistedcaldav.scheduling.imip import ScheduleViaIMip
from twistedcaldav.scheduling.ischedule import ScheduleViaISchedule
from twistedcaldav.scheduling.ischeduleservers import IScheduleServers
from twistedcaldav.scheduling.itip import iTIPRequestStatus
from twistedcaldav.servers import Servers

"""
CalDAV/Server-to-Server scheduling behavior.
"""

__all__ = [
    "Scheduler",
    "CalDAVScheduler",
    "IScheduleScheduler",
    "IMIPScheduler",
    "DirectScheduler",
]


log = Logger()

class Scheduler(object):
    
    def __init__(self, request, resource):
        self.request = request
        self.resource = resource
        self.originator = None
        self.recipients = None
        self.calendar = None
        self.organizer = None
        self.attendee = None
        self.isiTIPRequest = None
        self.timeRange = None
        self.excludeUID = None
        self.fakeTheResult = False
        self.method = "Unknown"
        self.internal_request = False
    
    @inlineCallbacks
    def doSchedulingViaPOST(self, transaction, use_request_headers=False):
        """
        The Scheduling POST operation on an Outbox.
        """
    
        self.method = "POST"

        # Load various useful bits doing some basic checks on those
        yield self.loadCalendarFromRequest()
        
        if use_request_headers:
            self.loadFromRequestHeaders()
        else:
            yield self.loadFromRequestData()

        if not hasattr(self.request, "extendedLogItems"):
            self.request.extendedLogItems = {}
        self.request.extendedLogItems["recipients"] = len(self.recipients)
        self.request.extendedLogItems["cl"] = str(len(self.calendardata))
    
        # Do some extra authorization checks
        self.checkAuthorization()

        # We might trigger an implicit scheduling operation here that will require consistency
        # of data for all events with the same UID. So detect this and use a lock
        lock = None
        if self.calendar.resourceType() != "VFREEBUSY":
            uid = self.calendar.resourceUID()
            lock = MemcacheLock("ImplicitUIDLock", uid, timeout=60.0, expire_time=5*60)

        # Implicit lock
        if lock:
            try:
                yield lock.acquire()
            except MemcacheLockTimeoutError:
                raise HTTPError(StatusResponse(responsecode.CONFLICT, "Resource: %s currently in use on the server." % (self.uri,)))
            else:
                # Release lock after commit or abort
                transaction.postCommit(lock.clean)
                transaction.postAbort(lock.clean)
                
        result = (yield self.doScheduling())
        returnValue(result)

    def doSchedulingViaPUT(self, originator, recipients, calendar, internal_request=False):
        """
        The implicit scheduling PUT operation.
        """
    
        self.method = "PUT"

        # Load various useful bits doing some basic checks on those
        self.originator = originator
        self.recipients = recipients
        self.calendar = calendar
        self.calendardata = str(self.calendar)
        self.internal_request = internal_request

        # Do some extra authorization checks
        self.checkAuthorization()

        return self.doScheduling()

    @inlineCallbacks
    def doScheduling(self):
        # Check validity of Originator header.
        yield self.checkOriginator()
    
        # Get recipient details.
        yield self.checkRecipients()
    
        # Check calendar data.
        self.checkCalendarData()
    
        # Check validity of ORGANIZER
        yield self.checkOrganizer()
    
        # Do security checks (e.g. spoofing)
        yield self.securityChecks()
    
        # Generate accounting information
        self.doAccounting()

        # Do some final checks after we have gathered all our information
        self.finalChecks()

        # Do scheduling tasks
        result = (yield self.generateSchedulingResponse())

        returnValue(result)

    @inlineCallbacks
    def loadFromRequestData(self):
        yield self.loadOriginatorFromRequestDetails()
        self.loadRecipientsFromCalendarData()
        
    @inlineCallbacks
    def loadOriginatorFromRequestDetails(self):
        # Get the originator who is the authenticated user
        originatorPrincipal = None
        originator = ""
        authz_principal = self.resource.currentPrincipal(self.request).children[0]
        if isinstance(authz_principal, davxml.HRef):
            originatorPrincipalURL = str(authz_principal)
            if originatorPrincipalURL:
                originatorPrincipal = (yield self.request.locateResource(originatorPrincipalURL))
                if originatorPrincipal:
                    # Pick the canonical CUA:
                    originator = originatorPrincipal.canonicalCalendarUserAddress()

        if not originator:
            log.err("%s request must have Originator" % (self.method,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-specified"),
                "Missing originator",
            ))
        else:
            self.originator = originator

    def loadRecipientsFromCalendarData(self):

        # Get the ATTENDEEs
        attendees = list()
        unique_set = set()
        for attendee, _ignore in self.calendar.getAttendeesByInstance():
            if attendee not in unique_set:
                attendees.append(attendee)
                unique_set.add(attendee)
        
        if not attendees:
            log.err("%s request must have at least one Recipient" % (self.method,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "recipient-specified"),
                "Must have recipients",
            ))
        else:
            self.recipients = list(attendees)

    def loadFromRequestHeaders(self):
        """
        Load Originator and Recipient from request headers.
        """
        self.loadOriginatorFromRequestHeaders()
        self.loadRecipientsFromRequestHeaders()

    def loadOriginatorFromRequestHeaders(self):
        # Must have Originator header
        originator = self.request.headers.getRawHeaders("originator")
        if originator is None or (len(originator) != 1):
            log.err("%s request must have Originator header" % (self.method,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-specified"),
                "Missing originator",
            ))
        else:
            self.originator = originator[0]
    
    def loadRecipientsFromRequestHeaders(self):
        # Get list of Recipient headers
        rawRecipients = self.request.headers.getRawHeaders("recipient")
        if rawRecipients is None or (len(rawRecipients) == 0):
            log.err("%s request must have at least one Recipient header" % (self.method,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "recipient-specified"),
                "No recipients",
            ))
    
        # Recipient header may be comma separated list
        self.recipients = []
        for rawRecipient in rawRecipients:
            for r in rawRecipient.split(","):
                r = r.strip()
                if len(r):
                    self.recipients.append(r)
        
    @inlineCallbacks
    def loadCalendarFromRequest(self):
        # Must be content-type text/calendar
        contentType = self.request.headers.getHeader("content-type")
        if contentType is not None and (contentType.mediaType, contentType.mediaSubtype) != ("text", "calendar"):
            log.err("MIME type %s not allowed in calendar collection" % (contentType,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "supported-calendar-data"),
                "Data is not calendar data",
            ))
    
        # Parse the calendar object from the HTTP request stream
        try:
            self.calendar = (yield Component.fromIStream(self.request.stream))
            
            self.preProcessCalendarData()
            self.calendardata = str(self.calendar)
        except:
            # FIXME: Bare except
            log.err("Error while handling %s: %s" % (self.method, Failure(),))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "valid-calendar-data"),
                description="Can't parse calendar data"
            ))

    def preProcessCalendarData(self):
        """
        After loading calendar data from the request, do some optional processing of it. This method will be
        overridden by those schedulers that need to do special things to the data.
        """
        pass

    def checkAuthorization(self):
        raise NotImplementedError

    def checkOriginator(self):
        raise NotImplementedError

    def checkRecipients(self):
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
            self.calendar.validCalendarData()
        except ValueError, e:
            log.err("%s request calendar component is not valid:%s %s" % (self.method, e, self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "valid-calendar-data"),
                description="Calendar component is not valid"
            ))
    
        # Must have a METHOD
        if not self.calendar.isValidMethod():
            log.err("%s request must have valid METHOD property in calendar component: %s" % (self.method, self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "valid-calendar-data"),
                description="Must have valid METHOD property"
            ))
        
        # Verify iTIP behavior
        if not self.calendar.isValidITIP():
            log.err("%s request must have a calendar component that satisfies iTIP requirements: %s" % (self.method, self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "valid-calendar-data"),
                description="Must have a calendar component that satisfies iTIP requirements"
            ))

        # X-CALENDARSERVER-ACCESS is not allowed in Outbox POSTs
        if self.calendar.hasProperty(Component.ACCESS_PROPERTY):
            log.err("X-CALENDARSERVER-ACCESS not allowed in a calendar component %s request: %s" % (self.method, self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "no-access-restrictions"),
                "Private events cannot be scheduled",
            ))
    
        # Determine iTIP method mode
        if self.calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER"):
            self.isiTIPRequest = True

        elif self.calendar.propertyValue("METHOD") in ("REPLY", "COUNTER", "REFRESH"):
            self.isiTIPRequest = False

            # Verify that there is a single ATTENDEE property
            attendees = self.calendar.getAttendees()
        
            # Must have only one
            if len(attendees) != 1:
                log.err("Wrong number of ATTENDEEs in calendar data: %s" % (self.calendardata,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "attendee-allowed"),
                    "Wrong number of attendees",
                ))
            self.attendee = attendees[0]

        else:
            msg = "Unknown iTIP METHOD: %s" % (self.calendar.propertyValue("METHOD"),)
            log.err(msg)
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "valid-calendar-data"),
                description=msg
            ))

    def checkForFreeBusy(self):
        if not hasattr(self, "isfreebusy"):
            if (self.calendar.propertyValue("METHOD") == "REQUEST") and (self.calendar.mainType() == "VFREEBUSY"):
                # Extract time range from VFREEBUSY object
                vfreebusies = [v for v in self.calendar.subcomponents() if v.name() == "VFREEBUSY"]
                if len(vfreebusies) != 1:
                    log.err("iTIP data is not valid for a VFREEBUSY request: %s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-calendar-data"),
                        "iTIP data is not valid for a VFREEBUSY request",
                    ))
                dtstart = vfreebusies[0].getStartDateUTC()
                dtend = vfreebusies[0].getEndDateUTC()
                if dtstart is None or dtend is None:
                    log.err("VFREEBUSY start/end not valid: %s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-calendar-data"),
                        "VFREEBUSY start/end not valid",
                    ))

                # Some clients send floating instead of UTC - coerce to UTC
                if not dtstart.utc() or not dtend.utc():
                    log.err("VFREEBUSY start or end not UTC: %s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-calendar-data"),
                        "VFREEBUSY start or end not UTC",
                    ))

                self.timeRange = caldavxml.TimeRange(start=dtstart.getText(), end=dtend.getText())
                self.timeRange.start = dtstart
                self.timeRange.end = dtend
        
                # Look for masked UID
                self.excludeUID = self.calendar.getMaskUID()
        
                # Do free busy operation
                self.isfreebusy = True
            else:
                # Do regular invite (fan-out)
                self.isfreebusy = False
        
        return self.isfreebusy
    
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
        if isinstance(self.organizer, LocalCalendarUser):
            accountingType = "iTIP-VFREEBUSY" if self.calendar.mainType() == "VFREEBUSY" else "iTIP"
            if accountingEnabled(accountingType, self.organizer.principal):
                emitAccounting(
                    accountingType, self.organizer.principal,
                    "Originator: %s\nRecipients:\n%sServer Instance:%s\nMethod:%s\n\n%s"
                    % (
                        str(self.originator),
                        str("".join(["    %s\n" % (recipient,) for recipient in self.recipients])),
                        str(self.request.serverInstance),
                        str(self.method),
                        self.calendardata,
                    )
                )

    def finalChecks(self):
        """
        Final checks before doing the actual scheduling.
        """
        pass

    @inlineCallbacks
    def generateSchedulingResponse(self):

        log.info("METHOD: %s, Component: %s" % (self.calendar.propertyValue("METHOD"), self.calendar.mainType(),))

        # For free-busy do immediate determination of iTIP result rather than fan-out
        freebusy = self.checkForFreeBusy()

        # Prepare for multiple responses
        responses = ScheduleResponseQueue(self.method, responsecode.OK)
    
        # Loop over each recipient and aggregate into lists by service types.
        caldav_recipients = []
        partitioned_recipients = []
        otherserver_recipients = []
        remote_recipients = []
        imip_recipients = []
        for ctr, recipient in enumerate(self.recipients):
    
            # Check for freebusy limit
            if freebusy and config.Scheduling.Options.LimitFreeBusyAttendees and ctr >= config.Scheduling.Options.LimitFreeBusyAttendees:
                err = HTTPError(ErrorResponse(
                    responsecode.NOT_FOUND,
                    (caldav_namespace, "recipient-limit"),
                    "Too many attendees",
                ))
                responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus=iTIPRequestStatus.SERVICE_UNAVAILABLE)
                continue
                
            if self.fakeTheResult:
                responses.add(recipient.cuaddr, responsecode.OK, reqstatus=iTIPRequestStatus.SUCCESS if freebusy else iTIPRequestStatus.MESSAGE_DELIVERED)
                
            elif isinstance(recipient, LocalCalendarUser):
                caldav_recipients.append(recipient)

            elif isinstance(recipient, PartitionedCalendarUser):
                partitioned_recipients.append(recipient)

            elif isinstance(recipient, OtherServerCalendarUser):
                otherserver_recipients.append(recipient)

            elif isinstance(recipient, RemoteCalendarUser):
                remote_recipients.append(recipient)

            elif isinstance(recipient, EmailCalendarUser):
                imip_recipients.append(recipient)

            else:
                err = HTTPError(ErrorResponse(
                    responsecode.NOT_FOUND,
                    (caldav_namespace, "recipient-exists"),
                    "Unknown recipient",
                ))
                responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus=iTIPRequestStatus.INVALID_CALENDAR_USER)

        # Now process local recipients
        if caldav_recipients:
            yield self.generateLocalSchedulingResponses(caldav_recipients, responses, freebusy)

        # Now process partitioned recipients
        if partitioned_recipients:
            yield self.generateRemoteSchedulingResponses(partitioned_recipients, responses, freebusy, getattr(self.request, 'doing_attendee_refresh', False))

        # Now process other server recipients
        if otherserver_recipients:
            yield self.generateRemoteSchedulingResponses(otherserver_recipients, responses, freebusy, getattr(self.request, 'doing_attendee_refresh', False))

        # To reduce chatter, we suppress certain messages
        if not getattr(self.request, 'suppressRefresh', False):

            # Now process remote recipients
            if remote_recipients:
                yield self.generateRemoteSchedulingResponses(remote_recipients, responses, freebusy)

            # Now process iMIP recipients
            if imip_recipients:
                yield self.generateIMIPSchedulingResponses(imip_recipients, responses, freebusy)

        # Return with final response if we are done
        returnValue(responses)
    
    def generateLocalSchedulingResponses(self, recipients, responses, freebusy):
        """
        Generate scheduling responses for CalDAV recipients.
        """

        # Create the scheduler and run it.
        requestor = ScheduleViaCalDAV(self, recipients, responses, freebusy)
        return requestor.generateSchedulingResponses()

    def generateRemoteSchedulingResponses(self, recipients, responses, freebusy, refreshOnly=False):
        """
        Generate scheduling responses for remote recipients.
        """

        # Create the scheduler and run it.
        requestor = ScheduleViaISchedule(self, recipients, responses, freebusy)
        return requestor.generateSchedulingResponses(refreshOnly)

    def generateIMIPSchedulingResponses(self, recipients, responses, freebusy):
        """
        Generate scheduling responses for iMIP recipients.
        """

        # Create the scheduler and run it.
        requestor = ScheduleViaIMip(self, recipients, responses, freebusy)
        return requestor.generateSchedulingResponses()

class CalDAVScheduler(Scheduler):

    def __init__(self, request, resource):
        super(CalDAVScheduler, self).__init__(request, resource)
        self.doingPOST = False

    def doSchedulingViaPOST(self, transaction):
        """
        The Scheduling POST operation on an Outbox.
        """
        self.doingPOST = True
        return super(CalDAVScheduler, self).doSchedulingViaPOST(transaction)

    def checkAuthorization(self):
        # Must have an authenticated user
        if not self.internal_request and self.resource.currentPrincipal(self.request) == davxml.Principal(davxml.Unauthenticated()):
            log.err("Unauthenticated originators not allowed: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-allowed"),
                "Invalid originator",
            ))

    def checkOriginator(self):
        """
        Check the validity of the Originator header. Extract the corresponding principal.
        """
    
        # Verify that Originator is a valid calendar user
        originatorPrincipal = self.resource.principalForCalendarUserAddress(self.originator)
        if originatorPrincipal is None:
            # Local requests MUST have a principal.
            log.err("Could not find principal for originator: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-allowed"),
                "No principal for originator",
            ))
        else:
            # Must have a valid Inbox.
            inboxURL = originatorPrincipal.scheduleInboxURL()
            if inboxURL is None:
                log.err("Could not find inbox for originator: %s" % (self.originator,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "originator-allowed"),
                    "Originator cannot be scheduled",
                ))

            self.originator = LocalCalendarUser(self.originator, originatorPrincipal)

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
                address = (yield addressmapping.mapper.getCalendarUser(recipient, principal))
                if isinstance(address, InvalidCalendarUser):
                    log.err("Unknown calendar user address: %s" % (recipient,))
                results.append(address)
            else:
                # Map recipient to their inbox
                inboxURL = principal.scheduleInboxURL()
                inbox = (yield self.request.locateResource(inboxURL)) if principal.locallyHosted() else "dummy"

                if inbox:
                    results.append(calendarUserFromPrincipal(recipient, principal, inbox, inboxURL))
                else:
                    log.err("No schedule inbox for principal: %s" % (principal,))
                    results.append(InvalidCalendarUser(recipient))
        
        self.recipients = results

    @inlineCallbacks
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
                    if not organizerPrincipal.enabledAsOrganizer():
                        log.err("ORGANIZER not allowed to be an Organizer: %s" % (self.calendar,))
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "organizer-allowed"),
                            "Organizer cannot schedule",
                        ))

                    self.organizer = LocalCalendarUser(organizer, organizerPrincipal)
                else:
                    log.err("No outbox for ORGANIZER in calendar data: %s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "organizer-allowed"),
                        "Organizer cannot schedule",
                    ))
            else:
                localUser = (yield addressmapping.mapper.isCalendarUserInMyDomain(organizer))
                if localUser:
                    log.err("No principal for ORGANIZER in calendar data: %s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "organizer-allowed"),
                        "No principal for organizer",
                    ))
                else:
                    self.organizer = RemoteCalendarUser(organizer) 
        else:
            log.err("ORGANIZER missing in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "organizer-allowed"),
                "Missing organizer",
            ))

    def checkOrganizerAsOriginator(self):

        # Make sure that the ORGANIZER is local
        if not isinstance(self.organizer, LocalCalendarUser):
            log.err("ORGANIZER is not local to server in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "organizer-allowed"),
                "Organizer is not local to server",
            ))

        # Make sure that the ORGANIZER's Outbox is the request URI
        if self.doingPOST and self.organizer.principal.scheduleOutboxURL() != self.request.uri:
            log.err("Wrong outbox for ORGANIZER in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "organizer-allowed"),
                "Outbox does not belong to organizer",
            ))

    def checkAttendeeAsOriginator(self):
        """
        Check the validity of the ATTENDEE value as this is the originator of the iTIP message.
        Only local attendees are allowed for message originating from this server.
        """
        
        # Attendee's Outbox MUST be the request URI
        attendeePrincipal = self.resource.principalForCalendarUserAddress(self.attendee)
        if attendeePrincipal:
            if self.doingPOST and attendeePrincipal.scheduleOutboxURL() != self.request.uri:
                log.err("ATTENDEE in calendar data does not match owner of Outbox: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "attendee-allowed"),
                    "Outbox does not belong to attendee",
                ))
        else:
            log.err("Unknown ATTENDEE in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "attendee-allowed"),
                "No principal for attendee",
            ))
    
    def securityChecks(self):
        """
        Check that the originator has the appropriate rights to send this type of iTIP message.
        """
    
        # Prevent spoofing of ORGANIZER with specific METHODs when local
        if self.isiTIPRequest:
            self.checkOrganizerAsOriginator()
    
        # Prevent spoofing when doing reply-like METHODs
        else:
            self.checkAttendeeAsOriginator()

    def finalChecks(self):
        """
        Final checks before doing the actual scheduling.
        """
        
        # With implicit scheduling only certain types of iTIP operations are allowed for POST.
        
        if self.doingPOST:
            # Freebusy requests always processed
            if self.checkForFreeBusy():
                return
            
            # COUNTER and DECLINE-COUNTER allowed
            if self.calendar.propertyValue("METHOD") in ("COUNTER", "DECLINECOUNTER"):
                return
            
            # Anything else is not allowed. However, for compatibility we will optionally 
            # return a success response for all attendees.
            if config.Scheduling.CalDAV.OldDraftCompatibility:
                self.fakeTheResult = True
            else:
                raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Invalid iTIP message for implicit scheduling"))

class RemoteScheduler(Scheduler):

    def checkOrganizer(self):
        """
        Delay ORGANIZER check until we know what their role is.
        """
        pass

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
                localUser = (yield addressmapping.mapper.isCalendarUserInMyDomain(recipient))
                if localUser:
                    log.err("No principal for calendar user address: %s" % (recipient,))
                else:
                    log.err("Unknown calendar user address: %s" % (recipient,))
                results.append(InvalidCalendarUser(recipient))
            else:
                # Map recipient to their inbox
                inboxURL = principal.scheduleInboxURL()
                inbox = (yield self.request.locateResource(inboxURL)) if principal.locallyHosted() else "dummy"

                if inbox:
                    results.append(calendarUserFromPrincipal(recipient, principal, inbox, inboxURL))
                else:
                    log.err("No schedule inbox for principal: %s" % (principal,))
                    results.append(InvalidCalendarUser(recipient))
        
        self.recipients = results

class IScheduleScheduler(RemoteScheduler):

    def loadFromRequestHeaders(self):
        """
        Load Originator and Recipient from request headers.
        """
        super(IScheduleScheduler, self).loadFromRequestHeaders()
        
        if self.request.headers.getRawHeaders('x-calendarserver-itip-refreshonly', ("F"))[0] == "T":
            self.request.doing_attendee_refresh = 1
        
    def preProcessCalendarData(self):
        """
        For data coming in from outside we need to normalize the calendar user addresses so that later iTIP
        processing will match calendar users against those in stored calendar data. Only do that for invites
        not freebusy.
        """

        if not self.checkForFreeBusy():
            def lookupFunction(cuaddr):
                principal = self.resource.principalForCalendarUserAddress(cuaddr)
                if principal is None:
                    return (None, None, None)
                else:
                    return (
                        principal.record.fullName.decode("utf-8"),
                        principal.record.guid,
                        principal.record.calendarUserAddresses
                    )
    
            self.calendar.normalizeCalendarUserAddresses(lookupFunction)

    def checkAuthorization(self):
        # Must have an unauthenticated user
        if self.resource.currentPrincipal(self.request) != davxml.Principal(davxml.Unauthenticated()):
            log.err("Authenticated originators not allowed: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-allowed"),
                "Authentication not allowed",
            ))

    @inlineCallbacks
    def checkOriginator(self):
        """
        Check the validity of the Originator header.
        """
    
        # For remote requests we do not allow the originator to be a local user or one within our domain.
        originatorPrincipal = self.resource.principalForCalendarUserAddress(self.originator)
        localUser = (yield addressmapping.mapper.isCalendarUserInMyDomain(self.originator))
        if originatorPrincipal or localUser:
            if originatorPrincipal.locallyHosted():
                log.err("Cannot use originator that is on this server: %s" % (self.originator,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "originator-allowed"),
                    "Originator cannot be local to server",
                ))
            else:
                self.originator = calendarUserFromPrincipal(self.originator, originatorPrincipal)
                self._validAlternateServer(originatorPrincipal)
        else:
            self.originator = RemoteCalendarUser(self.originator)
            self._validiScheduleServer()

    def _validiScheduleServer(self):
        """
        Check the validity of the iSchedule host.
        """
    
        # We will only accept originator in known domains.
        servermgr = IScheduleServers()
        server = servermgr.mapDomain(self.originator.domain)
        if not server or not server.allow_from:
            log.err("Originator not on recognized server: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-allowed"),
                "Originator not recognized by server",
            ))
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
                try:
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
                except socket.herror, e:
                    log.debug("iSchedule cannot lookup client ip '%s': %s" % (clientip, str(e),))
                        
            if not matched:
                log.err("Originator not on allowed server: %s" % (self.originator,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "originator-allowed"),
                    "Originator not allowed to send to this server",
                ))

    def _validAlternateServer(self, principal):
        """
        Check the validity of the partitioned host.
        """

        # Extract expected host/port. This will be the partitionURI, or if no partitions,
        # the serverURI
        expected_uri = principal.partitionURI()
        if expected_uri is None:
            expected_uri = principal.serverURI()
        expected_uri = urlparse.urlparse(expected_uri)
        
        # Get the request IP and map to hostname.
        clientip = self.request.remoteAddr.host
        
        # Check against this server (or any of its partitions). We need this because an external iTIP message
        # may be addressed to users on different partitions, and the node receiving the iTIP message will need to
        # forward it to the partition nodes, thus the client ip seen by the partitions will in fact be the initial
        # receiving node.
        matched = False
        if Servers.getThisServer().checkThisIP(clientip):
            matched = True
    
        # Checked allowed IPs - if any were defined we only check against them, we do not
        # go on to check the expected server host ip
        elif Servers.getThisServer().hasAllowedFromIP():
            matched = Servers.getThisServer().checkAllowedFromIP(clientip)
            if not matched:
                log.error("Invalid iSchedule connection from client: %s" % (clientip,))

        # Next compare as dotted IP
        elif isIPAddress(expected_uri.hostname):
            if clientip == expected_uri.hostname:
                matched = True
        else:
            # Now do expected hostname -> IP lookup
            try:
                # So now try the lookup of the expected host
                _ignore_host, _ignore_aliases, ips = socket.gethostbyname_ex(expected_uri.hostname)
                for ip in ips:
                    if ip == clientip:
                        matched = True
                        break
            except socket.herror, e:
                log.debug("iSchedule cannot lookup client ip '%s': %s" % (clientip, str(e),))
        
        # Check possible shared secret
        if matched and not Servers.getThisServer().checkSharedSecret(self.request):
            log.err("Invalid iSchedule shared secret")
            matched = False

        if not matched:
            log.err("Originator not on allowed server: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-allowed"),
                "Originator not allowed to send to this server",
            ))

    @inlineCallbacks
    def checkOrganizerAsOriginator(self):
        """
        Check the validity of the ORGANIZER value. ORGANIZER must not be local.
        """
        
        # Verify that the ORGANIZER's cu address does not map to a valid user
        organizer = self.calendar.getOrganizer()
        if organizer:
            organizerPrincipal = self.resource.principalForCalendarUserAddress(organizer)
            if organizerPrincipal:
                if organizerPrincipal.locallyHosted():
                    log.err("Invalid ORGANIZER in calendar data: %s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "organizer-allowed"),
                        "Organizer is not local to server",
                    ))
                else:
                    # Check that the origin server is the correct partition
                    self.organizer = calendarUserFromPrincipal(organizer, organizerPrincipal)
                    self._validAlternateServer(self.organizer.principal)
            else:
                localUser = (yield addressmapping.mapper.isCalendarUserInMyDomain(organizer))
                if localUser:
                    log.err("Unsupported ORGANIZER in calendar data: %s" % (self.calendar,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "organizer-allowed"),
                        "Organizer not allowed to be originator",
                    ))
                else:
                    self.organizer = RemoteCalendarUser(organizer)
        else:
            log.err("ORGANIZER missing in calendar data: %s" % (self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "organizer-allowed"),
                "No organizer in calendar data",
            ))

    @inlineCallbacks
    def checkAttendeeAsOriginator(self):
        """
        Check the validity of the ATTENDEE value as this is the originator of the iTIP message.
        Only local attendees are allowed for message originating from this server.
        """
        
        # Attendee cannot be local.
        attendeePrincipal = self.resource.principalForCalendarUserAddress(self.attendee)
        if attendeePrincipal:
            if attendeePrincipal.locallyHosted():
                log.err("Invalid ATTENDEE in calendar data: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "attendee-allowed"),
                    "Local attendee cannot send to this server",
                ))
            else:
                self._validAlternateServer(attendeePrincipal)
        else:
            localUser = (yield addressmapping.mapper.isCalendarUserInMyDomain(self.attendee))
            if localUser:
                log.err("Unknown ATTENDEE in calendar data: %s" % (self.calendar,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "attendee-allowed"),
                    "Attendee not allowed to schedule",
                ))
    
        # TODO: in this case we should check that the ORGANIZER is the sole recipient.

    @inlineCallbacks
    def securityChecks(self):
        """
        Check that the originator has the appropriate rights to send this type of iTIP message.
        """

        # Prevent spoofing of ORGANIZER with specific METHODs when local
        if self.calendar.propertyValue("METHOD") in ("PUBLISH", "REQUEST", "ADD", "CANCEL", "DECLINECOUNTER"):
            yield self.checkOrganizerAsOriginator()
    
        # Prevent spoofing when doing reply-like METHODs
        elif self.calendar.propertyValue("METHOD") in ("REPLY", "COUNTER", "REFRESH"):
            yield self.checkAttendeeAsOriginator()
            
        else:
            log.err("Unknown iTIP METHOD for security checks: %s" % (self.calendar.propertyValue("METHOD"),))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "valid-calendar-data"),
                "Unknown iTIP method",
            ))


class DirectScheduler(Scheduler):
    """ An implicit scheduler meant for use by local processes which don't
        need to go through all these checks. """

    def checkAuthorization(self):
        pass

    def checkOrganizer(self):
        pass

    def checkOrganizerAsOriginator(self):
        pass

    def checkAttendeeAsOriginator(self):
        pass

    def securityChecks(self):
        pass

    def checkOriginator(self):
        pass

    def checkRecipients(self):
        pass


class IMIPScheduler(RemoteScheduler):

    def checkAuthorization(self):
        pass

    @inlineCallbacks
    def checkOriginator(self):
        """
        Check the validity of the Originator header.
        """
    
        # For remote requests we do not allow the originator to be a local user or one within our domain.
        originatorPrincipal = self.resource.principalForCalendarUserAddress(self.originator)
        localUser = (yield addressmapping.mapper.isCalendarUserInMyDomain(self.originator))
        if originatorPrincipal or localUser:
            log.err("Cannot use originator that is on this server: %s" % (self.originator,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-allowed"),
                "Originator cannot be local to server",
            ))
        else:
            self.originator = RemoteCalendarUser(self.originator)

    def checkOrganizerAsOriginator(self):
        pass

    def checkAttendeeAsOriginator(self):
        pass

    def securityChecks(self):
        """
        Check that the connection is from the mail gateway
        """
        allowed = config.Scheduling['iMIP']['MailGatewayServer']
        # Get the request IP and map to hostname.
        clientip = self.request.remoteAddr.host
        host, aliases, _ignore_ips = socket.gethostbyaddr(clientip)
        for host in itertools.chain((host, clientip), aliases):
            if host == allowed:
                break
        else:
            log.err("Only %s is allowed to submit internal scheduling requests, not %s" % (allowed, host))
            # TODO: verify this is the right response:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-allowed"),
                "Originator server not allowed to send to this server",
            ))


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
