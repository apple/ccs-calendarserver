##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twext.python.log import Logger, LogLevel
from twext.web2.dav.http import ErrorResponse

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python.failure import Failure
from twext.web2 import responsecode
from twext.web2.http import HTTPError

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config

from txdav.caldav.datastore.scheduling.cuaddress import LocalCalendarUser, RemoteCalendarUser, \
    PartitionedCalendarUser, OtherServerCalendarUser
from txdav.caldav.datastore.scheduling.delivery import DeliveryService
from txdav.caldav.datastore.scheduling.itip import iTIPRequestStatus
from txdav.caldav.datastore.scheduling.processing import ImplicitProcessor, ImplicitProcessorException

import hashlib
import uuid
from txdav.base.propertystore.base import PropertyName
from txdav.caldav.icalendarstore import ComponentUpdateState
from txdav.caldav.datastore.scheduling.freebusy import processAvailabilityFreeBusy, \
    generateFreeBusyInfo, buildFreeBusyResult


"""
Handles the sending of scheduling messages to the server itself. This will cause
actual processing of the delivery of the message to the recipient's inbox, via the
L{ImplicitProcessor} class.
"""

__all__ = [
    "ScheduleViaCalDAV",
]

log = Logger()

class ScheduleViaCalDAV(DeliveryService):

    def __init__(self, scheduler, recipients, responses, freebusy):

        self.scheduler = scheduler
        self.recipients = recipients
        self.responses = responses
        self.freebusy = freebusy


    @classmethod
    def serviceType(cls):
        return DeliveryService.serviceType_caldav


    @classmethod
    def matchCalendarUserAddress(cls, cuaddr):

        # Check for local address matches first
        if cuaddr.startswith("mailto:") and config.Scheduling[cls.serviceType()]["EmailDomain"]:
            addr = cuaddr[7:].split("?")[0]
            domain = config.Scheduling[cls.serviceType()]["EmailDomain"]
            _ignore_account, addrDomain = addr.split("@")
            if addrDomain == domain:
                return succeed(True)

        elif (cuaddr.startswith("http://") or cuaddr.startswith("https://")) and config.Scheduling[cls.serviceType()]["HTTPDomain"]:
            splits = cuaddr.split(":")[0][2:].split("?")
            domain = config.Scheduling[cls.serviceType()]["HTTPDomain"]
            if splits[0].endswith(domain):
                return succeed(True)

        elif cuaddr.startswith("/"):
            # Assume relative HTTP URL - i.e. on this server
            return succeed(True)

        # Do default match
        return super(ScheduleViaCalDAV, cls).matchCalendarUserAddress(cuaddr)


    @inlineCallbacks
    def generateSchedulingResponses(self):

        # Extract the ORGANIZER property and UID value from the calendar data for use later
        organizerProp = self.scheduler.calendar.getOrganizerProperty()
        uid = self.scheduler.calendar.resourceUID()

        organizerPrincipal = None
        if type(self.scheduler.organizer) in (LocalCalendarUser, PartitionedCalendarUser, OtherServerCalendarUser,):
            organizerPrincipal = self.scheduler.organizer.principal.uid

        for recipient in self.recipients:

            #
            # Check access controls - we do not do this right now. But if we ever implement access controls to
            # determine which users can schedule with other users, here is where we would do that test.
            #

            # Different behavior for free-busy vs regular invite
            if self.freebusy:
                # Look for special delegate extended free-busy request
                event_details = [] if self.scheduler.calendar.getExtendedFreeBusy() else None

                yield self.generateFreeBusyResponse(recipient, self.responses, organizerProp, organizerPrincipal, uid, event_details)
            else:
                yield self.generateResponse(recipient, self.responses)


    @inlineCallbacks
    def generateResponse(self, recipient, responses):
        # Hash the iCalendar data for use as the last path element of the URI path
        name = "%s-%s.ics" % (hashlib.md5(self.scheduler.calendar.resourceUID()).hexdigest(), str(uuid.uuid4())[:8],)

        # Do implicit scheduling message processing.
        try:
            processor = ImplicitProcessor()
            _ignore_processed, autoprocessed, store_inbox, changes = (yield processor.doImplicitProcessing(
                self.scheduler.txn,
                self.scheduler.calendar,
                self.scheduler.originator,
                recipient,
                noAttendeeRefresh=self.scheduler.noAttendeeRefresh,
            ))
        except ImplicitProcessorException, e:
            log.error("Could not store data in Inbox : %s" % (recipient.inbox,))
            if log.willLogAtLevel(LogLevel.debug):
                log.debug("%s: %s" % (e, Failure().getTraceback(),))
            err = HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "recipient-permissions"),
                "Could not store data in inbox",
            ))
            responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus=e.msg)
            returnValue(False)

        if store_inbox:
            # Copy calendar to inbox
            try:
                child = yield recipient.inbox._createCalendarObjectWithNameInternal(name, self.scheduler.calendar, ComponentUpdateState.INBOX)
            except Exception as e:
                # FIXME: Bare except
                log.error("Could not store data in Inbox : %s %s" % (recipient.inbox, e,))
                if log.willLogAtLevel(LogLevel.debug):
                    log.debug("Bare Exception: %s" % (Failure().getTraceback(),))
                err = HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "recipient-permissions"),
                    "Could not store data in inbox",
                ))
                responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus=iTIPRequestStatus.NO_AUTHORITY)
                returnValue(False)
            else:
                # Store CS:schedule-changes property if present
                if changes is not None:
                    props = child.properties()
                    props[PropertyName.fromElement(changes)] = changes

        responses.add(recipient.cuaddr, responsecode.OK, reqstatus=iTIPRequestStatus.MESSAGE_DELIVERED)
        if autoprocessed:
            if self.scheduler.logItems is not None:
                self.scheduler.logItems["itip.auto"] = self.scheduler.logItems.get("itip.auto", 0) + 1
        returnValue(True)


    @inlineCallbacks
    def generateFreeBusyResponse(self, recipient, responses, organizerProp, organizerPrincipal, uid, event_details):

        # Extract the ATTENDEE property matching current recipient from the calendar data
        cuas = recipient.principal.calendarUserAddresses
        attendeeProp = self.scheduler.calendar.getAttendeeProperty(cuas)

        remote = isinstance(self.scheduler.organizer, RemoteCalendarUser)

        try:
            fbresult = (yield self.generateAttendeeFreeBusyResponse(
                recipient,
                organizerProp,
                organizerPrincipal,
                uid,
                attendeeProp,
                remote,
                event_details,
            ))
        except:
            log.error("Could not determine free busy information: %s" % (recipient.cuaddr,))
            if log.willLogAtLevel(LogLevel.debug):
                log.debug("Bare Exception: %s" % (Failure().getTraceback(),))
            err = HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "recipient-permissions"),
                "Could not determine free busy information",
            ))
            responses.add(
                recipient.cuaddr,
                Failure(exc_value=err),
                reqstatus=iTIPRequestStatus.NO_AUTHORITY
            )
            returnValue(False)
        else:
            responses.add(
                recipient.cuaddr,
                responsecode.OK,
                reqstatus=iTIPRequestStatus.SUCCESS,
                calendar=fbresult
            )
            returnValue(True)


    @inlineCallbacks
    def generateAttendeeFreeBusyResponse(self, recipient, organizerProp, organizerPrincipal, uid, attendeeProp, remote, event_details=None):

        # Find the current recipients calendars that are not transparent
        fbset = (yield recipient.inbox.ownerHome().loadCalendars())
        fbset = [calendar for calendar in fbset if calendar.isUsedForFreeBusy()]

        # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
        fbinfo = ([], [], [])

        # Process the availability property from the Inbox.
        availability = recipient.inbox.ownerHome().getAvailability()
        if availability is not None:
            processAvailabilityFreeBusy(availability, fbinfo, self.scheduler.timeRange)

        # Check to see if the recipient is the same calendar user as the organizer.
        # Needed for masked UID stuff.
        if isinstance(self.scheduler.organizer, LocalCalendarUser):
            same_calendar_user = self.scheduler.organizer.principal.uid == recipient.principal.uid
        else:
            same_calendar_user = False

        # Now process free-busy set calendars
        matchtotal = 0
        for calendar in fbset:
            matchtotal = (yield generateFreeBusyInfo(
                calendar,
                fbinfo,
                self.scheduler.timeRange,
                matchtotal,
                excludeuid=self.scheduler.excludeUID,
                organizer=self.scheduler.organizer.cuaddr,
                organizerPrincipal=organizerPrincipal,
                same_calendar_user=same_calendar_user,
                servertoserver=remote,
                event_details=event_details,
                logItems=self.scheduler.logItems,
            ))

        # Build VFREEBUSY iTIP reply for this recipient
        fbresult = buildFreeBusyResult(
            fbinfo,
            self.scheduler.timeRange,
            organizer=organizerProp,
            attendee=attendeeProp,
            uid=uid,
            method="REPLY",
            event_details=event_details,
        )

        returnValue(fbresult)
