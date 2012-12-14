#
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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
from twext.web2.dav.http import ErrorResponse

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.web2 import responsecode
from twext.web2.http import HTTPError

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.directory.principal import DirectoryCalendarPrincipalResource
from twistedcaldav.ical import Property
from twistedcaldav.scheduling import addressmapping
from twistedcaldav.scheduling.cuaddress import InvalidCalendarUser, \
    LocalCalendarUser, PartitionedCalendarUser, OtherServerCalendarUser, \
    normalizeCUAddr
from twistedcaldav.scheduling.icaldiff import iCalDiff
from twistedcaldav.scheduling.itip import iTipGenerator, iTIPRequestStatus
from twistedcaldav.scheduling.caldav.scheduler import CalDAVScheduler
from twistedcaldav.scheduling.utils import getCalendarObjectForPrincipals
from twistedcaldav.config import config

__all__ = [
    "ImplicitScheduler",
]

log = Logger()

# TODO:
#
# Handle the case where a PUT removes the ORGANIZER property. That should be equivalent to cancelling the entire meeting.
# Support Schedule-Reply header
#

class ImplicitScheduler(object):

    # Return Status codes
    STATUS_OK = 0
    STATUS_ORPHANED_CANCELLED_EVENT = 1
    STATUS_ORPHANED_EVENT = 2

    def __init__(self):

        self.return_status = ImplicitScheduler.STATUS_OK


    @inlineCallbacks
    def testImplicitSchedulingPUT(self, request, resource, resource_uri, calendar, internal_request=False):

        self.request = request
        self.resource = resource
        self.calendar = calendar
        self.internal_request = internal_request

        existing_resource = resource.exists()
        is_scheduling_object = (yield self.checkSchedulingObjectResource(resource))
        existing_type = "schedule" if is_scheduling_object else "calendar"
        new_type = "schedule" if (yield self.checkImplicitState()) else "calendar"

        # If the types do not currently match, re-check the stored one. We need this to work around the possibility
        # that data exists using the older algorithm of determining a scheduling object resource, and that could be
        # wrong.
        if existing_type != new_type and resource and resource.exists():
            resource.isScheduleObject = None
            is_scheduling_object = (yield self.checkSchedulingObjectResource(resource))
            existing_type = "schedule" if is_scheduling_object else "calendar"

        if existing_type == "calendar":
            self.action = "create" if new_type == "schedule" else "none"
        else:
            self.action = "modify" if new_type == "schedule" else "remove"

        # Cannot create new resource with existing UID
        if not existing_resource or self.action == "create":
            yield self.hasCalendarResourceUIDSomewhereElse(resource, resource_uri, new_type)

        # If action is remove we actually need to get state from the existing scheduling object resource
        if self.action == "remove":
            # Also make sure that we return the new calendar being written rather than the old one
            # when the implicit action is executed
            self.return_calendar = calendar
            self.calendar = (yield resource.iCalendarForUser(request))
            yield self.checkImplicitState()

        # Once we have collected sufficient information from the calendar data, check validity of organizer and attendees
        self.checkValidOrganizer()

        # Attendees are not allowed to overwrite one type with another
        if (
            not self.internal_request and
            self.state == "attendee" and
            (existing_type != new_type) and
            existing_resource
        ):
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "valid-attendee-change"),
                "Cannot change scheduling object mode",
            ))

        # Organizer events must have a master component
        if self.state == "organizer" and self.calendar.masterComponent() is None:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "organizer-allowed"),
                "Organizer cannot schedule without a master component.",
            ))

        returnValue((self.action != "none", new_type == "schedule",))


    @inlineCallbacks
    def testImplicitSchedulingMOVE(self, request, srcresource, srccal, src_uri, destresource, destcal, dest_uri, calendar, internal_request=False):

        self.request = request
        self.resource = destresource
        self.calendar = calendar
        self.internal_request = internal_request

        new_type = "schedule" if (yield self.checkImplicitState()) else "calendar"

        dest_exists = destresource.exists()
        dest_is_implicit = (yield self.checkSchedulingObjectResource(destresource))
        src_is_implicit = (yield self.checkSchedulingObjectResource(srcresource)) or new_type == "schedule"

        if srccal and destcal:
            if src_is_implicit and dest_exists or dest_is_implicit:
                log.debug("Implicit - cannot MOVE with a scheduling object resource")
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "unique-scheduling-object-resource"),
                    "Cannot MOVE a scheduling object resource",
                ))
            else:
                self.action = "none"
        elif srccal and not destcal:
            result = (yield self.testImplicitSchedulingDELETE(request, srcresource, calendar))
            returnValue((result[0], new_type == "schedule",))
        elif not srccal and destcal:
            result = (yield self.testImplicitSchedulingPUT(request, destresource, dest_uri, calendar))
            returnValue(result)
        else:
            self.action = "none"

        returnValue((self.action != "none", new_type == "schedule",))


    @inlineCallbacks
    def testImplicitSchedulingCOPY(self, request, srcresource, srccal, src_uri, destresource, destcal, dest_uri, calendar, internal_request=False):

        self.request = request
        self.resource = destresource
        self.calendar = calendar
        self.internal_request = internal_request

        new_type = "schedule" if (yield self.checkImplicitState()) else "calendar"

        dest_is_implicit = (yield self.checkSchedulingObjectResource(destresource))
        src_is_implicit = (yield self.checkSchedulingObjectResource(srcresource)) or new_type == "schedule"

        if srccal and destcal:
            if src_is_implicit or dest_is_implicit:
                log.debug("Implicit - cannot COPY with a scheduling object resource")
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "unique-scheduling-object-resource"),
                    "Cannot COPY with a scheduling object resource",
                ))
            else:
                self.action = "none"
        elif srccal and not destcal:
            self.action = "none"
        elif not srccal and destcal:
            result = (yield self.testImplicitSchedulingPUT(request, destresource, dest_uri, calendar))
            returnValue(result)
        else:
            self.action = "none"

        returnValue((self.action != "none", src_is_implicit,))


    @inlineCallbacks
    def testImplicitSchedulingDELETE(self, request, resource, calendar, internal_request=False):

        self.request = request
        self.resource = resource
        self.calendar = calendar
        self.internal_request = internal_request

        yield self.checkImplicitState()

        is_scheduling_object = (yield self.checkSchedulingObjectResource(resource))
        resource_type = "schedule" if is_scheduling_object else "calendar"
        self.action = "remove" if resource_type == "schedule" else "none"

        returnValue((self.action != "none", False,))


    @inlineCallbacks
    def testAttendeeEvent(self, request, resource, calendar):
        """
        Test the existing resource to see if it is an Attendee scheduling object resource.

        @param request: the request object
        @type request: L{Request}
        @param resource: the existing resource to test
        @type resource: L{Resource}
        """

        self.request = request
        self.resource = resource
        self.calendar = calendar
        self.internal_request = False
        self.action = "modify"

        is_scheduling_object = (yield self.checkSchedulingObjectResource(resource))
        if not is_scheduling_object:
            returnValue(False)

        yield self.checkImplicitState()

        returnValue(self.state in ("attendee", "attendee-missing",))


    def checkValidOrganizer(self):
        """
        Make sure the ORGANIZER is allowed to do certain scheduling operations.
        """

        # Check to see whether the organizer principal is enabled for scheduling. If not, do not allow them
        # to create new scheduling resources.
        if self.action == "create":
            if self.organizerPrincipal and not self.organizerPrincipal.enabledAsOrganizer():
                log.err("ORGANIZER not allowed to be an Organizer: %s" % (self.organizer,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "organizer-allowed"),
                    "Organizer cannot schedule",
                ))


    @inlineCallbacks
    def checkSchedulingObjectResource(self, resource):

        if resource and resource.exists():
            implicit = resource.isScheduleObject
            if implicit is not None:
                returnValue(implicit)
            else:
                calendar = (yield resource.iCalendarForUser(self.request))
                # Get the ORGANIZER and verify it is the same for all components
                try:
                    organizer = calendar.validOrganizerForScheduling()
                except ValueError:
                    # We have different ORGANIZERs in the same iCalendar object - this is an error
                    returnValue(False)

                # Any ORGANIZER => a scheduling object resource
                returnValue(organizer is not None)

        returnValue(False)


    @inlineCallbacks
    def checkImplicitState(self):
        # Get some useful information from the calendar
        yield self.extractCalendarData()
        self.calendar_owner = (yield self.resource.owner(self.request))

        # Determine what type of scheduling this is: Organizer triggered or Attendee triggered
        organizer_scheduling = (yield self.isOrganizerScheduling())
        if organizer_scheduling:
            self.state = "organizer"
        elif self.isAttendeeScheduling():
            self.state = "attendee"
        elif self.organizer:
            # There is an ORGANIZER that is not this user but no ATTENDEE property for
            # the user.
            self.state = "attendee-missing"
        else:
            self.state = None

        returnValue(self.state is not None)


    @inlineCallbacks
    def doImplicitScheduling(self, do_smart_merge=False):
        """
        Do implicit scheduling operation based on the data already set by call to checkImplicitScheduling.

        @param do_smart_merge: if True, merge attendee data on disk with new data being stored,
            else overwrite data on disk.
        @return: a new calendar object modified with scheduling information,
            or C{None} if nothing happened or C{int} if some other state occurs
        """

        # Setup some parameters
        self.do_smart_merge = do_smart_merge
        self.except_attendees = ()
        self.only_refresh_attendees = None

        # Determine what type of scheduling this is: Organizer triggered or Attendee triggered
        if self.state == "organizer":
            yield self.doImplicitOrganizer()
        elif self.state == "attendee":
            yield self.doImplicitAttendee()
        elif self.state == "attendee-missing":
            yield self.doImplicitMissingAttendee()
        else:
            returnValue(None)

        if self.return_status:
            returnValue(self.return_status)
        else:
            returnValue(self.return_calendar if hasattr(self, "return_calendar") else self.calendar)


    @inlineCallbacks
    def refreshAllAttendeesExceptSome(self, request, resource, except_attendees=(), only_attendees=None):
        """
        Refresh the iCalendar data for all attendees except the one specified in attendees.
        """

        self.request = request
        self.resource = resource
        self.calendar = (yield self.resource.iCalendarForUser(self.request))
        self.state = "organizer"
        self.action = "modify"

        self.calendar_owner = None
        self.internal_request = True
        self.except_attendees = except_attendees
        self.only_refresh_attendees = only_attendees
        self.changed_rids = None
        self.reinvites = None

        # Get some useful information from the calendar
        yield self.extractCalendarData()
        self.organizerPrincipal = self.resource.principalForCalendarUserAddress(self.organizer)
        self.organizerAddress = (yield addressmapping.mapper.getCalendarUser(self.organizer, self.organizerPrincipal))

        # Originator is the organizer in this case
        self.originatorPrincipal = self.organizerPrincipal
        self.originator = self.organizer

        # We want to suppress chatty iMIP messages when other attendees reply
        self.request.suppressRefresh = False

        for attendee in self.calendar.getAllAttendeeProperties():
            if attendee.parameterValue("PARTSTAT", "NEEDS-ACTION").upper() == "NEEDS-ACTION":
                self.request.suppressRefresh = True

        if hasattr(self.request, "doing_attendee_refresh"):
            self.request.doing_attendee_refresh += 1
        else:
            self.request.doing_attendee_refresh = 1
        try:
            refreshCount = (yield self.processRequests())
        finally:
            self.request.doing_attendee_refresh -= 1
            if self.request.doing_attendee_refresh == 0:
                delattr(self.request, "doing_attendee_refresh")

        if refreshCount:
            if not hasattr(self.request, "extendedLogItems"):
                self.request.extendedLogItems = {}
            self.request.extendedLogItems["itip.refreshes"] = refreshCount


    @inlineCallbacks
    def sendAttendeeReply(self, request, resource, calendar, attendee):

        self.request = request
        self.resource = resource
        self.calendar = calendar
        self.action = "modify"
        self.state = "attendee"

        self.calendar_owner = None
        self.internal_request = True
        self.changed_rids = None

        # Get some useful information from the calendar
        yield self.extractCalendarData()

        self.originator = self.attendee = attendee.principal.canonicalCalendarUserAddress()
        self.attendeePrincipal = attendee.principal

        result = (yield self.scheduleWithOrganizer())

        returnValue(result)


    @inlineCallbacks
    def extractCalendarData(self):

        # Get the originator who is the owner of the calendar resource being modified
        self.originatorPrincipal = None
        self.originator = ""
        if self.resource:
            self.originatorPrincipal = (yield self.resource.ownerPrincipal(self.request))
            if not isinstance(self.originatorPrincipal, DirectoryCalendarPrincipalResource):
                log.error("Originator '%s' is not enabled for calendaring" % (self.originatorPrincipal,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "invalid-originator"),
                    "Originator not enabled",
                ))

            # Pick the canonical CUA:
            self.originator = self.originatorPrincipal.canonicalCalendarUserAddress()

        # Get the ORGANIZER and verify it is the same for all components
        try:
            self.organizer = self.calendar.validOrganizerForScheduling()
        except ValueError:
            # We have different ORGANIZERs in the same iCalendar object - this is an error
            log.error("Only one ORGANIZER is allowed in an iCalendar object:\n%s" % (self.calendar,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "single-organizer"),
                "Only one organizer allowed in scheduling object resource",
            ))

        # Coerce any local with SCHEDULE-AGENT=CLIENT
        yield self.coerceAttendeeScheduleAgent()

        # Get the ATTENDEEs
        self.attendeesByInstance = self.calendar.getAttendeesByInstance(True, onlyScheduleAgentServer=True)
        self.instances = set(self.calendar.getComponentInstances())
        self.attendees = set()
        for attendee, _ignore in self.attendeesByInstance:
            self.attendees.add(attendee)

        # Some other useful things
        self.uid = self.calendar.resourceUID()


    @inlineCallbacks
    def hasCalendarResourceUIDSomewhereElse(self, check_resource, check_uri, type):
        """
        See if a calendar component with a matching UID exists anywhere in the calendar home of the
        current recipient owner and is not the resource being targeted.
        """

        # Don't care in some cases
        if self.internal_request or self.action == "remove":
            returnValue(None)

        # Get owner's calendar-home
        calendar_owner_principal = (yield self.resource.resourceOwnerPrincipal(self.request))
        calendar_home = yield calendar_owner_principal.calendarHome(self.request)

        # Check for matching resource somewhere else in the home
        foundElsewhere = (yield calendar_home.hasCalendarResourceUIDSomewhereElse(self.uid, check_resource, type))
        if foundElsewhere:
            log.debug("Implicit - found component with same UID in a different collection: %s" % (check_uri,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "unique-scheduling-object-resource"),
                "Cannot duplicate scheduling object resource",
            ))


    @inlineCallbacks
    def isOrganizerScheduling(self):
        """
        Test whether this is a scheduling operation by an organizer
        """

        # First must have organizer property
        if not self.organizer:
            returnValue(False)

        # Organizer must map to a valid principal
        self.organizerPrincipal = self.resource.principalForCalendarUserAddress(self.organizer)
        self.organizerAddress = (yield addressmapping.mapper.getCalendarUser(self.organizer, self.organizerPrincipal))
        if not self.organizerPrincipal:
            returnValue(False)

        # Organizer must be the owner of the calendar resource
        if str(self.calendar_owner) != self.organizerPrincipal.principalURL():
            returnValue(False)

        returnValue(True)


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
        yield outbox.authorize(self.request, (caldavxml.ScheduleSend(),))


    def makeScheduler(self):
        """
        Convenience method which we can override in unit tests to make testing easier.
        """
        return CalDAVScheduler(self.request, self.resource)


    @inlineCallbacks
    def doImplicitOrganizer(self):

        # Do access control
        if not self.internal_request:
            yield self.doAccessControl(self.organizerPrincipal, True)

        self.oldcalendar = None
        self.changed_rids = None
        self.cancelledAttendees = ()
        self.reinvites = None
        self.needs_action_rids = None

        self.needs_sequence_change = False

        # Check for a delete
        if self.action == "remove":

            log.debug("Implicit - organizer '%s' is removing UID: '%s'" % (self.organizer, self.uid))
            self.oldcalendar = self.calendar

            # Cancel all attendees
            self.cancelledAttendees = [(attendee, None) for attendee in self.attendees]

            # CANCEL always bumps sequence
            self.needs_sequence_change = True

        # Check for a new resource or an update
        elif self.action == "modify":

            # Read in existing data
            self.oldcalendar = (yield self.resource.iCalendarForUser(self.request))
            self.oldAttendeesByInstance = self.oldcalendar.getAttendeesByInstance(True, onlyScheduleAgentServer=True)
            self.oldInstances = set(self.oldcalendar.getComponentInstances())
            self.coerceAttendeesPartstatOnModify()

            # Don't allow any SEQUENCE to decrease
            if self.oldcalendar:
                self.calendar.sequenceInSync(self.oldcalendar)

            # Significant change
            no_change, self.changed_rids, self.needs_action_rids, reinvites, recurrence_reschedule = self.isOrganizerChangeInsignificant()
            if no_change:
                if reinvites:
                    log.debug("Implicit - organizer '%s' is re-inviting UID: '%s', attendees: %s" % (self.organizer, self.uid, ", ".join(reinvites)))
                    self.reinvites = reinvites
                else:
                    # Nothing to do
                    log.debug("Implicit - organizer '%s' is modifying UID: '%s' but change is not significant" % (self.organizer, self.uid))
                    returnValue(None)
            else:
                log.debug("Implicit - organizer '%s' is modifying UID: '%s'" % (self.organizer, self.uid))

                for rid in self.needs_action_rids:
                    comp = self.calendar.overriddenComponent(rid)

                    for attendee in comp.getAllAttendeeProperties():
                        if attendee.hasParameter("PARTSTAT"):
                            cuaddr = attendee.value()

                            if cuaddr in self.organizerPrincipal.calendarUserAddresses():
                                # If the attendee is the organizer then do not update
                                # the PARTSTAT to NEEDS-ACTION.
                                # The organizer is automatically ACCEPTED to the event.
                                continue

                            attendee.setParameter("PARTSTAT", "NEEDS-ACTION")

                # Check for removed attendees
                if not recurrence_reschedule:
                    self.findRemovedAttendees()

                # For now we always bump the sequence number on modifications because we cannot track DTSTAMP on
                # the Attendee side. But we check the old and the new and only bump if the client did not already do it.
                self.needs_sequence_change = self.calendar.needsiTIPSequenceChange(self.oldcalendar)

        elif self.action == "create":
            log.debug("Implicit - organizer '%s' is creating UID: '%s'" % (self.organizer, self.uid))
            self.coerceAttendeesPartstatOnCreate()

        # Always set RSVP=TRUE for any NEEDS-ACTION
        for attendee in self.calendar.getAllAttendeeProperties():
            if attendee.parameterValue("PARTSTAT", "NEEDS-ACTION").upper() == "NEEDS-ACTION":
                attendee.setParameter("RSVP", "TRUE")

        if self.needs_sequence_change:
            self.calendar.bumpiTIPInfo(oldcalendar=self.oldcalendar, doSequence=True)

        yield self.scheduleWithAttendees()

        # Always clear SCHEDULE-FORCE-SEND from all attendees after scheduling
        for attendee in self.calendar.getAllAttendeeProperties():
            try:
                attendee.removeParameter("SCHEDULE-FORCE-SEND")
            except KeyError:
                pass


    def isOrganizerChangeInsignificant(self):

        rids = None
        date_changed_rids = None
        reinvites = None
        recurrence_reschedule = False
        differ = iCalDiff(self.oldcalendar, self.calendar, self.do_smart_merge)
        no_change = differ.organizerDiff()
        if not no_change:
            # ORGANIZER change is absolutely not allowed!
            diffs = differ.whatIsDifferent()
            rids = set()
            date_changed_rids = set()
            checkOrganizerValue = False
            for rid, props in diffs.iteritems():
                if "ORGANIZER" in props:
                    checkOrganizerValue = True
                rids.add(rid)

                if any([testprop in props for testprop in (
                    "DTSTART",
                    "DTEND",
                    "DURATION",
                    "DUE",
                    "RECURRENCE-ID",
                )]):
                    date_changed_rids.add(rid)

                # Check to see whether a change to R-ID's happened
                if rid == "":

                    if "DTSTART" in props and self.calendar.masterComponent().hasProperty("RRULE"):
                        # DTSTART change with RRULE present is always a reschedule
                        recurrence_reschedule = True

                    elif "RRULE" in props:

                        # Need to see if the RRULE change is a simple truncation or expansion - i.e. a change to
                        # COUNT or UNTIL only. If so we don't need to treat this as a complete re-schedule.

                        # Start off assuming they are different
                        recurrence_reschedule = True

                        # Get each RRULE (can be only one in the master)
                        oldrrule = tuple(self.oldcalendar.masterComponent().properties("RRULE"))
                        oldrrule = oldrrule[0].value() if len(oldrrule) else None
                        newrrule = tuple(self.calendar.masterComponent().properties("RRULE"))
                        newrrule = newrrule[0].value() if len(newrrule) else None

                        if newrrule is not None and oldrrule is not None:

                            # Normalize the rrules by removing COUNT/UNTIL and then compare
                            oldrrule = oldrrule.duplicate()
                            newrrule = newrrule.duplicate()

                            oldrrule.setUseUntil(False)
                            oldrrule.setUntil(None)
                            oldrrule.setUseCount(False)
                            oldrrule.setCount(0)

                            newrrule.setUseUntil(False)
                            newrrule.setUntil(None)
                            newrrule.setUseCount(False)
                            newrrule.setCount(0)

                            # If they are equal we have a simple change - no overall reschedule
                            if newrrule == oldrrule:
                                recurrence_reschedule = False

            if checkOrganizerValue:
                oldOrganizer = self.oldcalendar.getOrganizer()
                newOrganizer = self.calendar.getOrganizer()
                if oldOrganizer != newOrganizer:
                    log.error("Cannot change ORGANIZER: UID:%s" % (self.uid,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-organizer-change"),
                        "Organizer cannot be changed",
                    ))
        else:
            # Special case of SCHEDULE-FORCE-SEND added to attendees and no other change
            reinvites = set()
            for attendee in self.calendar.getAllAttendeeProperties():
                try:
                    if attendee.parameterValue("SCHEDULE-FORCE-SEND", "").upper() == "REQUEST":
                        reinvites.add(attendee.value())
                except KeyError:
                    pass

        return no_change, rids, date_changed_rids, reinvites, recurrence_reschedule


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

        mappedOld = set(self.oldAttendeesByInstance)
        mappedNew = set(self.attendeesByInstance)

        # Get missing instances
        removedInstances = self.oldInstances - self.instances
        addedInstances = self.instances - self.oldInstances

        # Also look for new EXDATEs
        oldexdates = set()
        for property in self.oldcalendar.masterComponent().properties("EXDATE"):
            oldexdates.update([value.getValue() for value in property.value()])
        newexdates = set()
        for property in self.calendar.masterComponent().properties("EXDATE"):
            newexdates.update([value.getValue() for value in property.value()])

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

        master_attendees = self.oldcalendar.masterComponent().getAttendeesByInstance(onlyScheduleAgentServer=True)
        for attendee, _ignore in master_attendees:
            for exdate in addedexdates:
                # Don't remove the master attendee's when an EXDATE is added for a removed overridden component
                # as the set of attendees in the override may be different from the master set, but the override
                # will have been accounted for by the previous attendee/instance logic.
                if exdate not in removedInstances:
                    self.cancelledAttendees.add((attendee, exdate))

        # For overridden instances added, check whether any attendees were removed from the master
        for attendee, _ignore in master_attendees:
            for rid in addedInstances:
                if (attendee, rid) not in mappedNew and rid not in oldexdates:
                    self.cancelledAttendees.add((attendee, rid))


    def coerceAttendeesPartstatOnCreate(self):
        """
        Make sure any attendees handled by the server start off with PARTSTAT=NEEDS-ACTION as
        we do not allow the organizer to forcibly set PARTSTAT to anything else.
        """
        for attendee in self.calendar.getAllAttendeeProperties():
            # Don't adjust ORGANIZER's ATTENDEE
            if attendee.value() in self.organizerPrincipal.calendarUserAddresses():
                continue
            if attendee.parameterValue("SCHEDULE-AGENT", "SERVER").upper() == "SERVER" and attendee.hasParameter("PARTSTAT"):
                attendee.setParameter("PARTSTAT", "NEEDS-ACTION")


    def coerceAttendeesPartstatOnModify(self):
        """
        Make sure that the organizer does not change attendees' PARTSTAT to anything
        other than NEEDS-ACTION for those attendees handled by the server.
        """

        # Get the set of Rids in each calendar
        newRids = set(self.calendar.getComponentInstances())
        oldRids = set(self.oldcalendar.getComponentInstances())

        # Test/fix ones that are the same
        for rid in (newRids & oldRids):
            self.compareAttendeePartstats(self.oldcalendar.overriddenComponent(rid), self.calendar.overriddenComponent(rid))

        # Test/fix ones added
        for rid in (newRids - oldRids):
            # Compare the new one to the old master
            self.compareAttendeePartstats(self.oldcalendar.overriddenComponent(None), self.calendar.overriddenComponent(rid))

        # For removals, we ignore ones that are no longer valid
        valid_old_rids = self.calendar.validInstances(oldRids - newRids)

        # Test/fix ones removed
        for rid in valid_old_rids:
            # Compare the old one to a derived instance, and if there is a change
            # add the derived instance to the new data
            newcomp = self.calendar.deriveInstance(rid)
            changed = self.compareAttendeePartstats(
                self.oldcalendar.overriddenComponent(rid),
                newcomp,
            )
            if changed:
                self.calendar.addComponent(newcomp)


    def compareAttendeePartstats(self, old_component, new_component):
        """
        Compare two components, old and new, and make sure the Organizer has not changed the PARTSTATs
        in the new one to anything other than NEEDS-ACTION. If there is a change, undo it.
        """

        old_attendees = dict([(normalizeCUAddr(attendee.value()), attendee) for attendee in old_component.getAllAttendeeProperties()])
        new_attendees = dict([(normalizeCUAddr(attendee.value()), attendee) for attendee in new_component.getAllAttendeeProperties()])

        changed = False
        for cuaddr, newattendee in new_attendees.items():
            # Don't adjust ORGANIZER's ATTENDEE
            if newattendee.value() in self.organizerPrincipal.calendarUserAddresses():
                continue
            new_partstat = newattendee.parameterValue("PARTSTAT", "NEEDS-ACTION").upper()
            if newattendee.parameterValue("SCHEDULE-AGENT", "SERVER").upper() == "SERVER" and new_partstat != "NEEDS-ACTION":
                old_attendee = old_attendees.get(cuaddr)
                old_partstat = old_attendee.parameterValue("PARTSTAT", "NEEDS-ACTION").upper() if old_attendee else "NEEDS-ACTION"
                if old_attendee is None or old_partstat != new_partstat:
                    newattendee.setParameter("PARTSTAT", old_partstat)
                    changed = True

        return changed


    @inlineCallbacks
    def coerceAttendeeScheduleAgent(self):
        """
        Do not allow SCHEDULE-AGENT=CLIENT/NONE for attendees hosted by this server. Coerce to
        SCHEDULE-AGENT=SERVER.
        """

        coerced = {}
        for attendee in self.calendar.getAllAttendeeProperties():
            if attendee.parameterValue("SCHEDULE-AGENT", "SERVER").upper() == "CLIENT":
                cuaddr = attendee.value()
                if cuaddr not in coerced:
                    attendeePrincipal = self.resource.principalForCalendarUserAddress(cuaddr)
                    attendeeAddress = (yield addressmapping.mapper.getCalendarUser(cuaddr, attendeePrincipal))
                    local_attendee = type(attendeeAddress) in (LocalCalendarUser, PartitionedCalendarUser, OtherServerCalendarUser,)
                    coerced[cuaddr] = local_attendee
                if coerced[cuaddr]:
                    attendee.removeParameter("SCHEDULE-AGENT")


    @inlineCallbacks
    def scheduleWithAttendees(self):

        # First process cancelled attendees
        total = (yield self.processCancels())

        # Process regular requests next
        if self.action in ("create", "modify",):
            total += (yield self.processRequests())

        if not hasattr(self.request, "extendedLogItems"):
            self.request.extendedLogItems = {}
        self.request.extendedLogItems["itip.requests"] = total


    @inlineCallbacks
    def processCancels(self):

        # TODO: a better policy here is to aggregate by attendees with the same set of instances
        # being cancelled, but for now we will do one scheduling message per attendee.

        # Do one per attendee
        aggregated = {}
        for attendee, rid in self.cancelledAttendees:
            aggregated.setdefault(attendee, []).append(rid)

        count = 0
        for attendee, rids in aggregated.iteritems():

            # Don't send message back to the ORGANIZER
            if attendee in self.organizerPrincipal.calendarUserAddresses():
                continue

            # Generate an iTIP CANCEL message for this attendee, cancelling
            # each instance or the whole

            if None in rids:
                # One big CANCEL will do
                itipmsg = iTipGenerator.generateCancel(self.oldcalendar, (attendee,), None, self.action == "remove")
            else:
                # Multiple CANCELs
                itipmsg = iTipGenerator.generateCancel(self.oldcalendar, (attendee,), rids)

            # Send scheduling message
            if itipmsg:
                # This is a local CALDAV scheduling operation.
                scheduler = self.makeScheduler()

                # Do the PUT processing
                log.info("Implicit CANCEL - organizer: '%s' to attendee: '%s', UID: '%s', RIDs: '%s'" % (self.organizer, attendee, self.uid, rids))
                response = (yield scheduler.doSchedulingViaPUT(self.originator, (attendee,), itipmsg, internal_request=True))
                self.handleSchedulingResponse(response, True)

                count += 1

        returnValue(count)


    @inlineCallbacks
    def processRequests(self):

        # TODO: a better policy here is to aggregate by attendees with the same set of instances
        # being requested, but for now we will do one scheduling message per attendee.

        # Do one per attendee
        count = 0
        for attendee in self.attendees:

            # Don't send message back to the ORGANIZER
            if attendee in self.organizerPrincipal.calendarUserAddresses():
                continue

            # Don't send message to specified attendees
            if attendee in self.except_attendees:
                continue

            # Only send to specified attendees
            if self.only_refresh_attendees is not None and attendee not in self.only_refresh_attendees:
                continue

            # If SCHEDULE-FORCE-SEND only change, only send message to those Attendees
            if self.reinvites and attendee in self.reinvites:
                continue

            itipmsg = iTipGenerator.generateAttendeeRequest(self.calendar, (attendee,), self.changed_rids)

            # Send scheduling message
            if itipmsg is not None:
                # This is a local CALDAV scheduling operation.
                scheduler = self.makeScheduler()

                # Do the PUT processing
                log.info("Implicit REQUEST - organizer: '%s' to attendee: '%s', UID: '%s'" % (self.organizer, attendee, self.uid,))
                response = (yield scheduler.doSchedulingViaPUT(self.originator, (attendee,), itipmsg, internal_request=True))
                self.handleSchedulingResponse(response, True)

                count += 1

        returnValue(count)


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
                status.split(";")[0],
                "ATTENDEE" if is_organizer else "ORGANIZER",
                recipient)


    @inlineCallbacks
    def doImplicitAttendee(self):

        # Do access control
        if not self.internal_request:
            yield self.doAccessControl(self.attendeePrincipal, False)

        # Check SCHEDULE-AGENT
        doScheduling = self.checkOrganizerScheduleAgent()

        if self.action == "remove":
            if self.calendar.hasPropertyValueInAllComponents(Property("STATUS", "CANCELLED")):
                log.debug("Implicit - attendee '%s' is removing cancelled UID: '%s'" % (self.attendee, self.uid))
                # Nothing else to do
            elif doScheduling:
                # If attendee is already marked as declined in all components - nothing to do
                attendees = self.calendar.getAttendeeProperties((self.attendee,))
                if all([attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "DECLINED" for attendee in attendees]):
                    log.debug("Implicit - attendee '%s' is removing fully declined UID: '%s'" % (self.attendee, self.uid))
                    # Nothing else to do
                else:
                    log.debug("Implicit - attendee '%s' is cancelling UID: '%s'" % (self.attendee, self.uid))
                    yield self.scheduleCancelWithOrganizer()
            else:
                log.debug("Implicit - attendee '%s' is removing UID without server scheduling: '%s'" % (self.attendee, self.uid))
                # Nothing else to do
            returnValue(None)

        else:
            # Make sure ORGANIZER is not changed
            if self.resource.exists():
                self.oldcalendar = (yield self.resource.iCalendarForUser(self.request))
                oldOrganizer = self.oldcalendar.getOrganizer()
                newOrganizer = self.calendar.getOrganizer()
                if oldOrganizer != newOrganizer:
                    log.error("Cannot change ORGANIZER: UID:%s" % (self.uid,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-attendee-change"),
                        "Cannot change organizer",
                    ))
            else:
                self.oldcalendar = None

            # Get the ORGANIZER's current copy of the calendar object
            yield self.getOrganizersCopy()
            if self.organizer_calendar:

                # If Organizer copy exists we cannot allow SCHEDULE-AGENT=CLIENT or NONE
                if not doScheduling:
                    log.error("Attendee '%s' is not allowed to change SCHEDULE-AGENT on organizer: UID:%s" % (self.attendeePrincipal, self.uid,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-attendee-change"),
                        "Cannot alter organizer",
                    ))

                # Determine whether the current change is allowed
                changeAllowed, doITipReply, changedRids, newCalendar = self.isAttendeeChangeInsignificant()
                if changeAllowed:
                    self.return_calendar = self.calendar = newCalendar

                if not changeAllowed:
                    if self.calendar.hasPropertyValueInAllComponents(Property("STATUS", "CANCELLED")):
                        log.debug("Attendee '%s' is creating CANCELLED event for mismatched UID: '%s' - removing entire event" % (self.attendee, self.uid,))
                        self.return_status = ImplicitScheduler.STATUS_ORPHANED_EVENT
                        returnValue(None)
                    else:
                        log.error("Attendee '%s' is not allowed to make an unauthorized change to an organized event: UID:%s" % (self.attendeePrincipal, self.uid,))
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "valid-attendee-change"),
                            "Attendee changes are not allowed",
                        ))

                # Check that the return calendar actually has any components left - this can happen if a cancelled
                # component is removed and replaced by another cancelled or invalid one
                if self.calendar.mainType() is None:
                    log.debug("Attendee '%s' is replacing CANCELLED event: '%s' - removing entire event" % (self.attendee, self.uid,))
                    self.return_status = ImplicitScheduler.STATUS_ORPHANED_EVENT
                    returnValue(None)

                if not doITipReply:
                    log.debug("Implicit - attendee '%s' is updating UID: '%s' but change is not significant" % (self.attendee, self.uid))
                    returnValue(self.return_calendar)
                log.debug("Attendee '%s' is allowed to update UID: '%s' with local organizer '%s'" % (self.attendee, self.uid, self.organizer))

            elif isinstance(self.organizerAddress, LocalCalendarUser):
                # If Organizer copy does not exists we cannot allow SCHEDULE-AGENT=SERVER
                if doScheduling:
                    # Check to see whether all instances are CANCELLED
                    if self.calendar.hasPropertyValueInAllComponents(Property("STATUS", "CANCELLED")):
                        log.debug("Attendee '%s' is creating CANCELLED event for missing UID: '%s' - removing entire event" % (self.attendee, self.uid,))
                        self.return_status = ImplicitScheduler.STATUS_ORPHANED_CANCELLED_EVENT
                        returnValue(None)
                    else:
                        # Check to see whether existing event is SCHEDULE-AGENT=CLIENT/NONE
                        if self.oldcalendar:
                            oldScheduling = self.oldcalendar.getOrganizerScheduleAgent()
                            if not oldScheduling:
                                log.error("Attendee '%s' is not allowed to set SCHEDULE-AGENT=SERVER on organizer: UID:%s" % (self.attendeePrincipal, self.uid,))
                                raise HTTPError(ErrorResponse(
                                    responsecode.FORBIDDEN,
                                    (caldav_namespace, "valid-attendee-change"),
                                    "Attendee cannot change organizer state",
                                ))

                        log.debug("Attendee '%s' is not allowed to update UID: '%s' - missing organizer copy - removing entire event" % (self.attendee, self.uid,))
                        self.return_status = ImplicitScheduler.STATUS_ORPHANED_EVENT
                        returnValue(None)
                else:
                    log.debug("Implicit - attendee '%s' is modifying UID without server scheduling: '%s'" % (self.attendee, self.uid))
                    # Nothing else to do
                    returnValue(None)

            elif isinstance(self.organizerAddress, InvalidCalendarUser):
                # We will allow the attendee to do anything in this case, but we will mark the organizer
                # with an schedule-status error
                log.debug("Attendee '%s' is allowed to update UID: '%s' with invalid organizer '%s'" % (self.attendee, self.uid, self.organizer))
                if doScheduling:
                    self.calendar.setParameterToValueForPropertyWithValue(
                        "SCHEDULE-STATUS",
                        iTIPRequestStatus.NO_USER_SUPPORT_CODE,
                        "ORGANIZER",
                        self.organizer)
                returnValue(None)

            else:
                # We have a remote Organizer of some kind. For now we will allow the Attendee
                # to make any change they like as we cannot verify what is reasonable. In reality
                # we ought to be comparing the Attendee changes against the attendee's own copy
                # and restrict changes based on that when the organizer's copy is not available.
                log.debug("Attendee '%s' is allowed to update UID: '%s' with remote organizer '%s'" % (self.attendee, self.uid, self.organizer))
                changedRids = None

            if doScheduling:
                log.debug("Implicit - attendee '%s' is updating UID: '%s'" % (self.attendee, self.uid))
                yield self.scheduleWithOrganizer(changedRids)
            else:
                log.debug("Implicit - attendee '%s' is updating UID without server scheduling: '%s'" % (self.attendee, self.uid))
                # Nothing else to do


    @inlineCallbacks
    def doImplicitMissingAttendee(self):

        if self.action == "remove":
            # Nothing else to do
            log.debug("Implicit - missing attendee is removing UID without server scheduling: '%s'" % (self.uid,))

        else:
            # We will allow the attendee to do anything in this case, but we will mark the organizer
            # with an schedule-status error and schedule-agent none
            log.debug("Missing attendee is allowed to update UID: '%s' with invalid organizer '%s'" % (self.uid, self.organizer))

            # Make sure ORGANIZER is not changed if originally SCHEDULE-AGENT=SERVER
            if self.resource.exists():
                self.oldcalendar = (yield self.resource.iCalendarForUser(self.request))
                oldOrganizer = self.oldcalendar.getOrganizer()
                newOrganizer = self.calendar.getOrganizer()
                if oldOrganizer != newOrganizer and self.oldcalendar.getOrganizerScheduleAgent():
                    log.error("Cannot change ORGANIZER: UID:%s" % (self.uid,))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-attendee-change"),
                        "Cannot change organizer",
                    ))

            # Check SCHEDULE-AGENT and coerce SERVER to NONE
            if self.calendar.getOrganizerScheduleAgent():
                self.calendar.setParameterToValueForPropertyWithValue("SCHEDULE-AGENT", "NONE", "ORGANIZER", None)
                self.calendar.setParameterToValueForPropertyWithValue("SCHEDULE-STATUS", iTIPRequestStatus.NO_USER_SUPPORT_CODE, "ORGANIZER", None)


    def checkOrganizerScheduleAgent(self):

        is_server = self.calendar.getOrganizerScheduleAgent()
        local_organizer = type(self.organizerAddress) in (LocalCalendarUser, PartitionedCalendarUser, OtherServerCalendarUser,)

        if config.Scheduling.iMIP.Enabled and self.organizerAddress.cuaddr.lower().startswith("mailto:"):
            return is_server

        if not config.Scheduling.iSchedule.Enabled and not local_organizer and is_server:
            # Coerce ORGANIZER to SCHEDULE-AGENT=NONE
            log.debug("Attendee '%s' is not allowed to use SCHEDULE-AGENT=SERVER on organizer: UID:%s" % (self.attendeePrincipal, self.uid,))
            self.calendar.setParameterToValueForPropertyWithValue("SCHEDULE-AGENT", "NONE", "ORGANIZER", None)
            self.calendar.setParameterToValueForPropertyWithValue("SCHEDULE-STATUS", iTIPRequestStatus.NO_USER_SUPPORT_CODE, "ORGANIZER", None)
            is_server = False

        return is_server


    @inlineCallbacks
    def getOrganizersCopy(self):
        """
        Get the Organizer's copy of the event being processed.

        NB it is possible that the Organizer is not hosted on this server
        so the result here will be None. In that case we have to trust that
        the attendee does the right thing about changing the details in the event.
        """

        self.organizer_calendar = None
        calendar_resource, _ignore_name, _ignore_collection, _ignore_uri = (yield getCalendarObjectForPrincipals(self.request, self.organizerPrincipal, self.uid))
        if calendar_resource:
            self.organizer_calendar = (yield calendar_resource.iCalendarForUser(self.request))
        elif type(self.organizerAddress) in (PartitionedCalendarUser, OtherServerCalendarUser,):
            # For partitioning where the organizer is on a different node, we will assume that the attendee's copy
            # of the event is up to date and "authoritative". So we pretend that is the organizer copy
            self.organizer_calendar = self.oldcalendar


    def isAttendeeChangeInsignificant(self):
        """
        Check whether the change is significant (PARTSTAT) or allowed
        (attendee can only change their property, alarms, TRANSP, and
        instances. Raise an exception if it is not allowed.
        """

        oldcalendar = self.oldcalendar
        if oldcalendar is None:
            oldcalendar = self.organizer_calendar
            oldcalendar.attendeesView((self.attendee,), onlyScheduleAgentServer=True)
        differ = iCalDiff(oldcalendar, self.calendar, self.do_smart_merge)
        return differ.attendeeMerge(self.attendee)


    def scheduleWithOrganizer(self, changedRids=None):

        if not hasattr(self.request, "extendedLogItems"):
            self.request.extendedLogItems = {}
        self.request.extendedLogItems["itip.reply"] = "reply"

        itipmsg = iTipGenerator.generateAttendeeReply(self.calendar, self.attendee, changedRids=changedRids)

        # Send scheduling message
        return self.sendToOrganizer("REPLY", itipmsg)


    def scheduleCancelWithOrganizer(self):

        if not hasattr(self.request, "extendedLogItems"):
            self.request.extendedLogItems = {}
        self.request.extendedLogItems["itip.reply"] = "cancel"

        itipmsg = iTipGenerator.generateAttendeeReply(self.calendar, self.attendee, force_decline=True)

        # Send scheduling message
        return self.sendToOrganizer("CANCEL", itipmsg)


    def sendToOrganizer(self, action, itipmsg):

        # Send scheduling message

        # This is a local CALDAV scheduling operation.
        scheduler = self.makeScheduler()

        # Do the PUT processing
        def _gotResponse(response):
            self.handleSchedulingResponse(response, False)

        log.info("Implicit %s - attendee: '%s' to organizer: '%s', UID: '%s'" % (action, self.attendee, self.organizer, self.uid,))
        d = scheduler.doSchedulingViaPUT(self.originator, (self.organizer,), itipmsg, internal_request=True)
        d.addCallback(_gotResponse)
        return d
