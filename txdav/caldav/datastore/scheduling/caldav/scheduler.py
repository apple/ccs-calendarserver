##
# Copyright (c) 2012-2015 Apple Inc. All rights reserved.
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

from twext.python.log import Logger
from txweb2 import responsecode
from txweb2.dav.http import ErrorResponse
from txweb2.http import HTTPError, StatusResponse

from twisted.internet.defer import inlineCallbacks

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config

from txdav.caldav.datastore.scheduling import addressmapping
from txdav.caldav.datastore.scheduling.cuaddress import LocalCalendarUser, \
    OtherServerCalendarUser, InvalidCalendarUser, \
    calendarUserFromCalendarUserAddress
from txdav.caldav.datastore.scheduling.scheduler import Scheduler, ScheduleResponseQueue


"""
L{CalDAVScheduler} - handles deliveries for scheduling messages within the CalDAV server.
"""

__all__ = [
    "CalDAVScheduler",
]


log = Logger()

class CalDAVScheduler(Scheduler):

    scheduleResponse = ScheduleResponseQueue

    errorResponse = ErrorResponse

    errorElements = {
        "originator-missing": (caldav_namespace, "originator-specified"),
        "originator-invalid": (caldav_namespace, "originator-allowed"),
        "originator-denied": (caldav_namespace, "originator-allowed"),
        "recipient-missing": (caldav_namespace, "recipient-specified"),
        "recipient-invalid": (caldav_namespace, "recipient-exists"),
        "organizer-denied": (caldav_namespace, "organizer-allowed"),
        "attendee-denied": (caldav_namespace, "attendee-allowed"),
        "invalid-calendar-data-type": (caldav_namespace, "supported-calendar-data"),
        "invalid-calendar-data": (caldav_namespace, "valid-calendar-data"),
        "invalid-scheduling-message": (caldav_namespace, "valid-calendar-data"),
        "max-recipients": (caldav_namespace, "recipient-limit"),
    }

    def __init__(self, txn, originator_uid, **kwargs):
        super(CalDAVScheduler, self).__init__(txn, originator_uid, **kwargs)
        self.doingPOST = False


    def doSchedulingViaPOST(self, originator, recipients, calendar):
        """
        The Scheduling POST operation on an Outbox.
        """
        self.doingPOST = True
        return super(CalDAVScheduler, self).doSchedulingViaPOST(originator, recipients, calendar)


    def checkAuthorization(self):
        # Must have an authenticated user
        if not self.internal_request and self.originator_uid == None:
            log.error(
                "Unauthenticated originators not allowed: {o}",
                o=self.originator,
            )
            raise HTTPError(self.errorResponse(
                responsecode.FORBIDDEN,
                self.errorElements["originator-denied"],
                "Invalid originator",
            ))


    @inlineCallbacks
    def checkOriginator(self):
        """
        Check the validity of the Originator header. Extract the corresponding principal.
        """

        # Verify that Originator is a valid calendar user
        originatorAddress = yield calendarUserFromCalendarUserAddress(self.originator, self.txn)
        if not originatorAddress.hosted():
            # Local requests MUST have a principal.
            log.error(
                "Could not find principal for originator: {o}",
                o=self.originator,
            )
            raise HTTPError(self.errorResponse(
                responsecode.FORBIDDEN,
                self.errorElements["originator-denied"],
                "No principal for originator",
            ))
        else:
            if not originatorAddress.validOriginator() or isinstance(originatorAddress, OtherServerCalendarUser):
                log.error(
                    "Originator not enabled or hosted on this server: {o}",
                    o=self.originator,
                )
                raise HTTPError(self.errorResponse(
                    responsecode.FORBIDDEN,
                    self.errorElements["originator-denied"],
                    "Originator cannot be scheduled",
                ))

            self.originator = originatorAddress


    @inlineCallbacks
    def checkRecipients(self):
        """
        Check the validity of the Recipient header values. Map these into local or
        remote CalendarUsers.
        """

        results = []
        for recipient in self.recipients:
            # Get the calendar user object for this recipient
            recipientAddress = yield calendarUserFromCalendarUserAddress(recipient, self.txn)

            # If no principal we may have a remote recipient but we should check whether
            # the address is one that ought to be on our server and treat that as a missing
            # user. Also if server-to-server is not enabled then remote addresses are not allowed.
            if not recipientAddress.hosted():
                if isinstance(recipientAddress, InvalidCalendarUser):
                    log.error("Unknown calendar user address: {r}", r=recipient,)
                results.append(recipientAddress)
            else:
                # Map recipient to their inbox and cache on calendar user object
                inbox = None
                if recipientAddress.validRecipient():
                    if isinstance(recipientAddress, LocalCalendarUser):
                        recipient_home = yield self.txn.calendarHomeWithUID(recipientAddress.record.uid, create=True)
                        if recipient_home:
                            inbox = (yield recipient_home.calendarWithName("inbox"))
                    else:
                        inbox = "dummy"
                    recipientAddress.inbox = inbox

                if inbox:
                    results.append(recipientAddress)
                else:
                    log.error("No scheduling for calendar user: {r}", r=recipient,)
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
            organizerAddress = yield calendarUserFromCalendarUserAddress(organizer, self.txn)
            if organizerAddress.hosted():
                if organizerAddress.validOriginator():

                    # Only do this check for a freebusy request. A check for an invite needs
                    # to be handled later when we know whether a new invite is being added
                    # (which we reject) vs an update to an existing one (which we allow).
                    if self.checkForFreeBusy() and not organizerAddress.record.enabledAsOrganizer():
                        log.error("ORGANIZER not allowed to be an Organizer: {cal}", cal=self.calendar,)
                        raise HTTPError(self.errorResponse(
                            responsecode.FORBIDDEN,
                            self.errorElements["organizer-denied"],
                            "Organizer cannot schedule",
                        ))

                    self.organizer = organizerAddress
                else:
                    log.error("No scheduling for ORGANIZER: {o}", o=organizer,)
                    raise HTTPError(self.errorResponse(
                        responsecode.FORBIDDEN,
                        self.errorElements["organizer-denied"],
                        "Organizer cannot schedule",
                    ))
            else:
                localUser = (yield addressmapping.mapper.isCalendarUserInMyDomain(organizer))
                if localUser:
                    log.error("No principal for ORGANIZER in calendar data: {cal}", cal=self.calendar,)
                    raise HTTPError(self.errorResponse(
                        responsecode.FORBIDDEN,
                        self.errorElements["organizer-denied"],
                        "No principal for organizer",
                    ))
                else:
                    self.organizer = organizerAddress
        else:
            log.error("ORGANIZER missing in calendar data: {cal}", cal=self.calendar,)
            raise HTTPError(self.errorResponse(
                responsecode.FORBIDDEN,
                self.errorElements["invalid-scheduling-message"],
                "Missing organizer",
            ))


    def checkOrganizerAsOriginator(self):

        # Make sure that the ORGANIZER is local
        if not isinstance(self.organizer, LocalCalendarUser):
            log.error("ORGANIZER is not local to server in calendar data: {cal}", cal=self.calendar,)
            raise HTTPError(self.errorResponse(
                responsecode.FORBIDDEN,
                self.errorElements["organizer-denied"],
                "Organizer is not local to server",
            ))

        # Make sure that the ORGANIZER's is the request URI owner
        if self.doingPOST is not None and self.organizer.record.uid != self.originator_uid:
            log.error("Wrong outbox for ORGANIZER in calendar data: {cal}", cal=self.calendar,)
            raise HTTPError(self.errorResponse(
                responsecode.FORBIDDEN,
                self.errorElements["organizer-denied"],
                "Outbox does not belong to organizer",
            ))


    @inlineCallbacks
    def checkAttendeeAsOriginator(self):
        """
        Check the validity of the ATTENDEE value as this is the originator of the iTIP message.
        Only local attendees are allowed for message originating from this server.
        """

        # Attendee's MUST be the request URI owner
        attendeeAddress = yield calendarUserFromCalendarUserAddress(self.attendee, self.txn)
        if attendeeAddress.hosted():
            if self.doingPOST is not None and attendeeAddress.record.uid != self.originator_uid:
                log.error("ATTENDEE in calendar data does not match owner of Outbox: {a}", a=self.attendee,)
                raise HTTPError(self.errorResponse(
                    responsecode.FORBIDDEN,
                    self.errorElements["attendee-denied"],
                    "Outbox does not belong to attendee",
                ))
        else:
            log.error("Unknown ATTENDEE in calendar data: {a}", a=self.attendee,)
            raise HTTPError(self.errorResponse(
                responsecode.FORBIDDEN,
                self.errorElements["attendee-denied"],
                "No principal for attendee",
            ))


    def securityChecks(self):
        """
        Check that the originator has the appropriate rights to send this type of iTIP message.
        """

        # Prevent spoofing of ORGANIZER with specific METHODs when local
        if self.isiTIPRequest:
            return self.checkOrganizerAsOriginator()

        # Prevent spoofing when doing reply-like METHODs
        else:
            return self.checkAttendeeAsOriginator()


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
