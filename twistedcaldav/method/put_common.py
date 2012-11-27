# -*- test-case-name: twistedcaldav.test.test_validation -*-
##
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

"""
PUT/COPY/MOVE common behavior.
"""

__all__ = ["StoreCalendarObjectResource"]

import types
import uuid
from urlparse import urlparse, urlunparse

from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet.defer import returnValue
from twisted.python import hashlib

from twext.web2.dav.util import joinURL, parentForURL
from twext.web2 import responsecode
from txdav.xml import element as davxml

from twext.web2.http import HTTPError
from twext.web2.http import StatusResponse
from twext.web2.iweb import IResponse
from twext.web2.stream import MemoryStream

from twext.python.log import Logger
from twext.web2.dav.http import ErrorResponse

from txdav.caldav.icalendarstore import AttachmentStoreValidManagedID
from txdav.common.icommondatastore import ReservationError

from twistedcaldav.config import config
from twistedcaldav.caldavxml import caldav_namespace, NoUIDConflict, MaxInstances, MaxAttendeesPerInstance
from twistedcaldav import customxml
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.datafilters.peruserdata import PerUserDataFilter

from twistedcaldav.ical import Component, Property
from twistedcaldav.instance import TooManyInstancesError, \
    InvalidOverriddenInstanceError
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.scheduling.implicit import ImplicitScheduler

log = Logger()

class StoreCalendarObjectResource(object):

    class UIDReservation(object):

        def __init__(self, index, uid, uri, internal_request, transaction):
            if internal_request:
                self.lock = None
            else:
                self.lock = MemcacheLock(
                    "ImplicitUIDLock",
                    uid,
                    timeout=config.Scheduling.Options.UIDLockTimeoutSeconds,
                    expire_time=config.Scheduling.Options.UIDLockExpirySeconds
                )
            self.reserved = False
            self.index = index
            self.uid = uid
            self.uri = uri
            self.transaction = transaction

        @inlineCallbacks
        def reserve(self):

            # Implicit lock
            if self.lock:
                try:
                    yield self.lock.acquire()
                except MemcacheLockTimeoutError:
                    raise HTTPError(StatusResponse(responsecode.CONFLICT, "Resource: %s currently in use on the server." % (self.uri,)))

            # Lets use a deferred for this and loop a few times if we cannot reserve so that we give
            # time to whoever has the reservation to finish and release it.
            failure_count = 0
            while(failure_count < 10):
                try:
                    yield self.index.reserveUID(self.uid)
                    self.reserved = True
                    break
                except ReservationError:
                    self.reserved = False
                failure_count += 1

                pause = Deferred()
                def _timedDeferred():
                    pause.callback(True)
                reactor.callLater(0.5, _timedDeferred)
                yield pause

            if self.uri and not self.reserved:
                if self.lock:
                    # Can release immediately as nothing happened
                    yield self.lock.release()
                raise HTTPError(StatusResponse(responsecode.CONFLICT, "Resource: %s currently in use in calendar." % (self.uri,)))

        @inlineCallbacks
        def unreserve(self):
            if self.reserved:
                yield self.index.unreserveUID(self.uid)
                self.reserved = False
            if self.lock:
                # Release lock after commit or abort
                self.transaction.postCommit(self.lock.clean)
                self.transaction.postAbort(self.lock.clean)


    def __init__(
        self,
        request,
        source=None, source_uri=None, sourceparent=None, sourcecal=False, deletesource=False,
        destination=None, destination_uri=None, destinationparent=None, destinationcal=True,
        calendar=None,
        isiTIP=False,
        allowImplicitSchedule=True,
        internal_request=False,
        processing_organizer=None,
        returnData=False,
    ):
        """
        Function that does common PUT/COPY/MOVE behavior.

        @param request:           the L{twext.web2.server.Request} for the current HTTP request.
        @param source:            the L{CalDAVResource} for the source resource to copy from, or None if source data
            is to be read from the request.
        @param source_uri:        the URI for the source resource.
        @param destination:       the L{CalDAVResource} for the destination resource to copy into.
        @param destination_uri:   the URI for the destination resource.
        @param calendar:          the C{str} or L{Component} calendar data if there is no source, None otherwise.
        @param sourcecal:         True if the source resource is in a calendar collection, False otherwise.
        @param destinationcal:    True if the destination resource is in a calendar collection, False otherwise
        @param sourceparent:      the L{CalDAVResource} for the source resource's parent collection, or None if source is None.
        @param destinationparent: the L{CalDAVResource} for the destination resource's parent collection.
        @param deletesource:      True if the source resource is to be deleted on successful completion, False otherwise.
        @param isiTIP:                True if relaxed calendar data validation is to be done, False otherwise.
        @param allowImplicitSchedule: True if implicit scheduling should be attempted, False otherwise.
        @param internal_request:   True if this request originates internally and needs to bypass scheduling authorization checks.
        @param processing_organizer: True if implicit processing for an organizer, False if for an attendee, None if not implicit processing.
        @param returnData:         True if the caller wants the actual data written to the store returned
        """

        # Check that all arguments are valid
        try:
            assert destination is not None and destinationparent is not None and destination_uri is not None
            assert (source is None and sourceparent is None) or (source is not None and sourceparent is not None)
            assert (calendar is None and source is not None) or (calendar is not None and source is None)
            assert not deletesource or (deletesource and source is not None)
        except AssertionError:
            log.err("Invalid arguments to StoreCalendarObjectResource.__init__():")
            log.err("request=%s\n" % (request,))
            log.err("sourcecal=%s\n" % (sourcecal,))
            log.err("destinationcal=%s\n" % (destinationcal,))
            log.err("source=%s\n" % (source,))
            log.err("source_uri=%s\n" % (source_uri,))
            log.err("sourceparent=%s\n" % (sourceparent,))
            log.err("destination=%s\n" % (destination,))
            log.err("destination_uri=%s\n" % (destination_uri,))
            log.err("destinationparent=%s\n" % (destinationparent,))
            log.err("calendar=%s\n" % (calendar,))
            log.err("deletesource=%s\n" % (deletesource,))
            log.err("isiTIP=%s\n" % (isiTIP,))
            raise

        self.request = request
        self.sourcecal = sourcecal
        self.destinationcal = destinationcal
        self.source = source
        self.source_uri = source_uri
        self.sourceparent = sourceparent
        self.destination = destination
        self.destination_uri = destination_uri
        self.destinationparent = destinationparent
        self.calendar = calendar
        self.deletesource = deletesource
        self.isiTIP = isiTIP
        self.allowImplicitSchedule = allowImplicitSchedule
        self.internal_request = internal_request
        self.processing_organizer = processing_organizer
        self.returnData = returnData

        self.access = None
        self.hasPrivateComments = False
        self.isScheduleResource = False


    @inlineCallbacks
    def fullValidation(self):
        """
        Do full validation of source and destination calendar data.
        """

        # Basic validation
        self.validIfScheduleMatch()

        if self.destinationcal:

            # Skip validation on internal requests
            if not self.internal_request:

                # Valid resource name check
                result, message = self.validResourceName()
                if not result:
                    log.err(message)
                    raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Resource name not allowed"))

                # Valid collection size check on the destination parent resource
                result, message = (yield self.validCollectionSize())
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        customxml.MaxResources(),
                        "Too many resources in collection",
                    ))

                # Valid data sizes - do before parsing the data
                if self.source is not None:
                    # Valid content length check on the source resource
                    result, message = self.validContentLength()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "max-resource-size"),
                            "Calendar data too large",
                        ))
                else:
                    # Valid calendar data size check
                    result, message = self.validSizeCheck()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "max-resource-size"),
                            "Calendar data too large",
                        ))

            if not self.sourcecal:
                # Valid content type check on the source resource if its not in a calendar collection
                if self.source is not None:
                    result, message = self.validContentType()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "supported-calendar-data"),
                            "Invalid content-type for data",
                        ))

                    # At this point we need the calendar data to do more tests
                    try:
                        self.calendar = (yield self.source.iCalendarForUser(self.request))
                    except ValueError, e:
                        log.err(str(e))
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "valid-calendar-data"),
                            description="Can't parse calendar data"
                        ))
                else:
                    try:
                        if type(self.calendar) in (types.StringType, types.UnicodeType,):
                            self.calendar = Component.fromString(self.calendar)
                    except ValueError, e:
                        log.err(str(e))
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "valid-calendar-data"),
                            description="Can't parse calendar data"
                        ))

                # Possible timezone stripping
                if config.EnableTimezonesByReference:
                    self.calendar.stripKnownTimezones()

                # Skip validation on internal requests
                if not self.internal_request:

                    # Valid calendar data check
                    result, message = self.validCalendarDataCheck()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "valid-calendar-data"),
                            description=message
                        ))

                    # Valid calendar data for CalDAV check
                    result, message = self.validCalDAVDataCheck()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "valid-calendar-object-resource"),
                            "Invalid calendar data",
                        ))

                    # Valid calendar component for check
                    result, message = self.validComponentType()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "supported-component"),
                            "Invalid calendar data",
                        ))

                    # Valid attendee list size check
                    result, message = (yield self.validAttendeeListSizeCheck())
                    if not result:
                        log.err(message)
                        raise HTTPError(
                            ErrorResponse(
                                responsecode.FORBIDDEN,
                                MaxAttendeesPerInstance.fromString(str(config.MaxAttendeesPerInstance)),
                                "Too many attendees in calendar data",
                            )
                        )

                    # Normalize the calendar user addresses once we know we have valid
                    # calendar data
                    self.destination.iCalendarAddressDoNormalization(self.calendar)

                # Must have a valid UID at this point
                self.uid = self.calendar.resourceUID()
            else:
                # Get UID from original resource
                self.source_index = self.sourceparent.index()
                self.uid = yield self.source_index.resourceUIDForName(self.source.name())
                if self.uid is None:
                    log.err("Source calendar does not have a UID: %s" % self.source)
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-calendar-object-resource"),
                        "Missing UID in calendar data",
                    ))

                # FIXME: We need this here because we have to re-index the destination. Ideally it
                # would be better to copy the index entries from the source and add to the destination.
                self.calendar = (yield self.source.iCalendarForUser(self.request))

            # Check that moves to shared calendars are OK
            yield self.validCopyMoveOperation()

            # Check access
            if self.destinationcal and config.EnablePrivateEvents:
                result = (yield self.validAccess())
                returnValue(result)
            else:
                returnValue(None)

        elif self.sourcecal:
            self.source_index = self.sourceparent.index()
            self.calendar = (yield self.source.iCalendarForUser(self.request))

        # Check that moves to shared calendars are OK
        yield self.validCopyMoveOperation()


    @inlineCallbacks
    def validCopyMoveOperation(self):
        """
        Check that copy/move type behavior is valid.
        """
        if self.source:
            if not self.destinationcal:
                # Don't care about copies/moves to non-calendar destinations
                # In theory this state should not occur here as COPY/MOVE won't call into this as
                # they detect this state and do regular WebDAV copy/move.
                pass
            elif not self.sourcecal:
                # Moving into a calendar requires regular checks
                pass
            else:
                # Calendar to calendar moves are OK if the resource owner is the same.
                # Use resourceOwnerPrincipal for this as that takes into account sharing such that the
                # returned principal relates to the URI path used to access the resource rather than the
                # underlying resource owner (sharee).
                sourceowner = (yield self.sourceparent.resourceOwnerPrincipal(self.request))
                destowner = (yield self.destinationparent.resourceOwnerPrincipal(self.request))

                if sourceowner != destowner:
                    msg = "Calendar-to-calendar %s with different homes are not supported" % ("moves" if self.deletesource else "copies",)
                    log.debug(msg)
                    raise HTTPError(StatusResponse(responsecode.FORBIDDEN, msg))

                # Calendar to calendar moves where Organizer is present are not OK if the owners are different.
                sourceowner = (yield self.sourceparent.ownerPrincipal(self.request))
                destowner = (yield self.destinationparent.ownerPrincipal(self.request))

                if sourceowner != destowner:
                    # Now check whether an ORGANIZER property is present in either sourcecal or destcal
                    organizer = self.calendar.getOrganizer()
                    if organizer is None and self.destination.exists() and self.destinationcal:
                        oldCal = yield self.destination.iCalendar()
                        organizer = oldCal.getOrganizer()

                    if organizer is not None:
                        msg = "Calendar-to-calendar %s with an organizer property present and different owners are not supported" % ("moves" if self.deletesource else "copies",)
                        log.debug(msg)
                        raise HTTPError(StatusResponse(responsecode.FORBIDDEN, msg))


    def validIfScheduleMatch(self):
        """
        Check for If-ScheduleTag-Match header behavior.
        """
        # Only when a direct request
        self.schedule_tag_match = False
        if not self.isiTIP and not self.internal_request:
            header = self.request.headers.getHeader("If-Schedule-Tag-Match")
            if header:
                # If COPY/MOVE get Schedule-Tag on source, PUT use destination
                if self.source:
                    matcher = self.source
                    self.source.validIfScheduleMatch(self.request)
                else:
                    matcher = self.destination
                matcher.validIfScheduleMatch(self.request)
                self.schedule_tag_match = True
            elif config.Scheduling.CalDAV.ScheduleTagCompatibility:
                # Compatibility with old clients. Policy:
                #
                # 1. If If-Match header is not present, never do smart merge.
                # 2. If If-Match is present and the specified ETag is
                #    considered a "weak" match to the current Schedule-Tag,
                #    then do smart merge, else reject with a 412.
                #
                # Actually by the time we get here the precondition will
                # already have been tested and found to be OK, so we can just
                # always do smart merge now if If-Match is present.
                self.schedule_tag_match = self.request.headers.getHeader("If-Match") is not None


    def validResourceName(self):
        """
        Make sure that the resource name for the new resource is valid.
        """
        result = True
        message = ""
        filename = self.destination.name()
        if filename.startswith("."):
            result = False
            message = "File name %s not allowed in calendar collection" % (filename,)

        return result, message


    def validContentType(self):
        """
        Make sure that the content-type of the source resource is text/calendar.
        This test is only needed when the source is not in a calendar collection.
        """
        result = True
        message = ""
        content_type = self.source.contentType()
        if not ((content_type.mediaType == "text") and (content_type.mediaSubtype == "calendar")):
            result = False
            message = "MIME type %s not allowed in calendar collection" % (content_type,)

        return result, message


    def validContentLength(self):
        """
        Make sure that the length of the source data is within bounds.
        """
        result = True
        message = ""
        if config.MaxResourceSize:
            calsize = self.source.contentLength()
            if calsize is not None and calsize > config.MaxResourceSize:
                result = False
                message = "File size %d bytes is larger than allowed limit %d bytes" % (calsize, config.MaxResourceSize)

        return result, message


    @inlineCallbacks
    def validCollectionSize(self):
        """
        Make sure that any limits on the number of resources in a collection are enforced.
        """
        result = True
        message = ""
        if not self.destination.exists() and \
            config.MaxResourcesPerCollection and \
            (yield self.destinationparent.countChildren()) >= config.MaxResourcesPerCollection:
                result = False
                message = "Too many resources in collection %s" % (self.destinationparent,)

        returnValue((result, message,))


    def validCalendarDataCheck(self):
        """
        Check that the calendar data is valid iCalendar.
        @return:         tuple: (True/False if the calendar data is valid,
                                 log message string).
        """
        result = True
        message = ""
        if self.calendar is None:
            result = False
            message = "Empty resource not allowed in calendar collection"
        else:
            try:
                self.calendar.validCalendarData()
            except ValueError, e:
                result = False
                message = "Invalid calendar data: %s" % (e,)

        return result, message


    def validCalDAVDataCheck(self):
        """
        Check that the calendar data is valid as a CalDAV calendar object resource.
        @return:         tuple: (True/False if the calendar data is valid,
                                 log message string).
        """
        result = True
        message = ""
        try:
            self.calendar.validCalendarForCalDAV(methodAllowed=self.isiTIP)
        except ValueError, e:
            result = False
            message = "Calendar data does not conform to CalDAV requirements: %s" % (e,)

        return result, message


    def validComponentType(self):
        """
        Make sure that any limits on the number of resources in a collection are enforced.
        """
        result = True
        message = ""

        if not self.destinationparent.isSupportedComponent(self.calendar.mainType()):
            result = False
            message = "Invalid component type %s for calendar: %s" % (self.calendar.mainType(), self.destinationparent,)

        return result, message


    def validSizeCheck(self):
        """
        Make sure that the content-type of the source resource is text/calendar.
        This test is only needed when the source is not in a calendar collection.
        """
        result = True
        message = ""
        if config.MaxResourceSize:
            # FIXME PERF could be done more efficiently?
            calsize = len(str(self.calendar))
            if calsize > config.MaxResourceSize:
                result = False
                message = "Data size %d bytes is larger than allowed limit %d bytes" % (calsize, config.MaxResourceSize)

        return result, message


    @inlineCallbacks
    def validAttendeeListSizeCheck(self):
        """
        Make sure that the Attendee list length is within bounds. We don't do this check for inbox because we
        will assume that the limit has been applied on the PUT causing the iTIP message to be created.

        FIXME: The inbox check might not take into account iSchedule stuff from outside. That needs to have
        the max attendees check applied at the time of delivery.
        """
        result = True
        message = ""
        if config.MaxAttendeesPerInstance and not self.isiTIP:
            uniqueAttendees = set()
            for attendee in self.calendar.getAllAttendeeProperties():
                uniqueAttendees.add(attendee.value())
            attendeeListLength = len(uniqueAttendees)
            if attendeeListLength > config.MaxAttendeesPerInstance:

                # Check to see whether we are increasing the count on an existing resource
                if self.destination.exists() and self.destinationcal:
                    oldcalendar = (yield self.destination.iCalendarForUser(self.request))
                    uniqueAttendees = set()
                    for attendee in oldcalendar.getAllAttendeeProperties():
                        uniqueAttendees.add(attendee.value())
                    oldAttendeeListLength = len(uniqueAttendees)
                else:
                    oldAttendeeListLength = 0

                if attendeeListLength > oldAttendeeListLength:
                    result = False
                    message = "Attendee list size %d is larger than allowed limit %d" % (attendeeListLength, config.MaxAttendeesPerInstance)

        returnValue((result, message,))


    def validAccess(self):
        """
        Make sure that the X-CALENDARSERVER-ACCESS property is properly dealt with.
        """

        if self.calendar.hasProperty(Component.ACCESS_PROPERTY):

            # Must be a value we know about
            self.access = self.calendar.accessLevel(default=None)
            if self.access is None:
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (calendarserver_namespace, "valid-access-restriction"),
                    "Private event access level not allowed",
                ))

            # Only DAV:owner is able to set the property to other than PUBLIC
            if not self.internal_request:
                def _callback(parent_owner):

                    authz = self.destinationparent.currentPrincipal(self.request)
                    if davxml.Principal(parent_owner) != authz and self.access != Component.ACCESS_PUBLIC:
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (calendarserver_namespace, "valid-access-restriction-change"),
                            "Private event access level change not allowed",
                        ))

                    return None

                d = self.destinationparent.owner(self.request)
                d.addCallback(_callback)
                return d
        else:
            # Check whether an access property was present before and write that into the calendar data
            if not self.source and self.destination.exists() and self.destination.accessMode:
                old_access = self.destination.accessMode
                self.calendar.addProperty(Property(name=Component.ACCESS_PROPERTY, value=old_access))

        return succeed(None)


    @inlineCallbacks
    def preservePrivateComments(self):
        # Check for private comments on the old resource and the new resource and re-insert
        # ones that are lost.
        #
        # NB Do this before implicit scheduling as we don't want old clients to trigger scheduling when
        # the X- property is missing.
        self.hasPrivateComments = False
        if config.Scheduling.CalDAV.get("EnablePrivateComments", True) and self.calendar is not None:
            old_has_private_comments = self.destination.exists() and self.destinationcal and self.destination.hasPrivateComment
            self.hasPrivateComments = self.calendar.hasPropertyInAnyComponent((
                "X-CALENDARSERVER-PRIVATE-COMMENT",
                "X-CALENDARSERVER-ATTENDEE-COMMENT",
            ))

            if old_has_private_comments and not self.hasPrivateComments:
                # Transfer old comments to new calendar
                log.debug("Private Comments properties were entirely removed by the client. Restoring existing properties.")
                old_calendar = (yield self.destination.iCalendarForUser(self.request))
                self.calendar.transferProperties(old_calendar, (
                    "X-CALENDARSERVER-PRIVATE-COMMENT",
                    "X-CALENDARSERVER-ATTENDEE-COMMENT",
                ))


    @inlineCallbacks
    def replaceMissingToDoProperties(self):
        """
        Recover any lost ORGANIZER or ATTENDEE properties in non-recurring VTODOs.
        """

        if self.destination.exists() and self.calendar.resourceType() == "VTODO" and not self.calendar.isRecurring():

            old_calendar = (yield self.destination.iCalendarForUser(self.request))

            new_organizer = self.calendar.getOrganizer()
            old_organizer = old_calendar.getOrganizerProperty()
            new_attendees = self.calendar.getAttendees()
            old_attendees = tuple(old_calendar.getAllAttendeeProperties())

            new_completed = self.calendar.mainComponent().hasProperty("COMPLETED")
            old_completed = old_calendar.mainComponent().hasProperty("COMPLETED")

            if old_organizer and not new_organizer and len(old_attendees) > 0 and len(new_attendees) == 0:
                # Transfer old organizer and attendees to new calendar
                log.debug("Organizer and attendee properties were entirely removed by the client. Restoring existing properties.")

                # Get the originator who is the owner of the calendar resource being modified
                originatorPrincipal = (yield self.destination.ownerPrincipal(self.request))
                originatorAddresses = originatorPrincipal.calendarUserAddresses()

                for component in self.calendar.subcomponents():
                    if component.name() != "VTODO":
                        continue

                    if not component.hasProperty("DTSTART"):
                        # Need to put DTSTART back in or we get a date mismatch failure later
                        for old_component in old_calendar.subcomponents():
                            if old_component.name() != "VTODO":
                                continue
                            if old_component.hasProperty("DTSTART"):
                                component.addProperty(old_component.getProperty("DTSTART"))
                                break

                    # Add organizer back in from previous resource
                    component.addProperty(old_organizer)

                    # Add attendees back in from previous resource
                    for anAttendee in old_attendees:
                        if component.hasProperty("COMPLETED") and anAttendee.value() in originatorAddresses:
                            anAttendee.setParameter("PARTSTAT", "COMPLETED")
                        component.addProperty(anAttendee)

            elif new_completed ^ old_completed and not self.internal_request:
                # COMPLETED changed - sync up attendee state
                # We need this because many VTODO clients are not aware of scheduling,
                # i.e. they do not adjust any ATTENDEE PARTSTATs. We are going to impose
                # our own requirement that PARTSTAT is set to COMPLETED when the COMPLETED
                # property is added.

                # Transfer old organizer and attendees to new calendar
                log.debug("Sync COMPLETED property change.")

                # Get the originator who is the owner of the calendar resource being modified
                originatorPrincipal = (yield self.destination.ownerPrincipal(self.request))
                originatorAddresses = originatorPrincipal.calendarUserAddresses()

                for component in self.calendar.subcomponents():
                    if component.name() != "VTODO":
                        continue

                    # Change owner partstat
                    for anAttendee in component.properties("ATTENDEE"):
                        if anAttendee.value() in originatorAddresses:
                            oldpartstat = anAttendee.parameterValue("PARTSTAT", "NEEDS-ACTION")
                            newpartstat = "COMPLETED" if component.hasProperty("COMPLETED") else "IN-PROCESS"
                            if newpartstat != oldpartstat:
                                anAttendee.setParameter("PARTSTAT", newpartstat)


    @inlineCallbacks
    def dropboxPathNormalization(self):
        """
        Make sure sharees only use dropbox paths of the sharer.
        """

        # Only relevant if calendar is sharee collection
        changed = False
        if self.destinationparent.isShareeCollection():

            # Get all X-APPLE-DROPBOX's and ATTACH's that are http URIs
            xdropboxes = self.calendar.getAllPropertiesInAnyComponent(
                "X-APPLE-DROPBOX",
                depth=1,
            )
            attachments = self.calendar.getAllPropertiesInAnyComponent(
                "ATTACH",
                depth=1,
            )
            attachments = [
                attachment for attachment in attachments
                if attachment.parameterValue("VALUE", "TEXT") == "URI" and attachment.value().startswith("http")
            ]

            if len(xdropboxes) or len(attachments):

                # Determine owner GUID
                ownerPrincipal = (yield self.destinationparent.ownerPrincipal(self.request))
                owner = ownerPrincipal.principalURL().split("/")[-2]

                def uriNormalize(uri):
                    urichanged = False
                    scheme, netloc, path, params, query, fragment = urlparse(uri)
                    pathbits = path.split("/")
                    if pathbits[1] != "calendars":
                        pathbits[1] = "calendars"
                        urichanged = True
                    if pathbits[2] != "__uids__":
                        pathbits[2] = "__uids__"
                        urichanged = True
                    if pathbits[3] != owner:
                        pathbits[3] = owner
                        urichanged = True
                    if urichanged:
                        return urlunparse((scheme, netloc, "/".join(pathbits), params, query, fragment,))
                    return None

                for xdropbox in xdropboxes:
                    uri = uriNormalize(xdropbox.value())
                    if uri:
                        xdropbox.setValue(uri)
                        changed = True
                for attachment in attachments:
                    uri = uriNormalize(attachment.value())
                    if uri:
                        attachment.setValue(uri)
                        changed = True

        returnValue(changed)


    def processAlarms(self):
        """
        Remove duplicate alarms. Add a default alarm if required.

        @return: indicate whether a change was made
        @rtype: C{bool}
        """

        # Remove duplicate alarms
        changed = False
        if config.RemoveDuplicateAlarms:
            changed = self.calendar.hasDuplicateAlarms(doFix=True)

        # Only if feature enabled
        if not config.EnableDefaultAlarms:
            return changed

        # Check that we are creating and this is not the inbox
        if not self.destinationcal or self.destination.exists() or self.isiTIP:
            return changed

        # Never add default alarms to calendar data in shared calendars
        if self.destinationparent.isShareeCollection():
            return changed

        # Add default alarm for VEVENT and VTODO only
        mtype = self.calendar.mainType().upper()
        if self.calendar.mainType().upper() not in ("VEVENT", "VTODO"):
            return changed
        vevent = mtype == "VEVENT"

        # Check timed or all-day
        start, _ignore_end = self.calendar.mainComponent(allow_multiple=True).getEffectiveStartEnd()
        if start is None:
            # Yes VTODOs might have no DTSTART or DUE - in this case we do not add a default
            return changed
        timed = not start.isDateOnly()

        # See if default exists and add using appropriate logic
        alarm = self.destinationparent.getDefaultAlarm(vevent, timed)
        if alarm:
            changed = self.calendar.addAlarms(alarm)
        return changed


    @inlineCallbacks
    def noUIDConflict(self, uid):
        """
        Check that the UID of the new calendar object conforms to the requirements of
        CalDAV, i.e. it must be unique in the collection and we must not overwrite a
        different UID.
        @param uid: the UID for the resource being stored.
        @return: tuple: (True/False if the UID is valid, log message string,
            name of conflicted resource).
        """

        result = True
        message = ""
        rname = ""

        # Adjust for a move into same calendar collection
        oldname = None
        if self.sourceparent and (self.sourceparent == self.destinationparent) and self.deletesource:
            oldname = self.source.name()

        # UID must be unique
        index = self.destinationparent.index()
        if not (yield index.isAllowedUID(uid, oldname, self.destination.name())):
            rname = yield index.resourceNameForUID(uid)
            # This can happen if two simultaneous PUTs occur with the same UID.
            # i.e. one PUT has reserved the UID but has not yet written the resource,
            # the other PUT tries to reserve and fails but no index entry exists yet.
            if rname is None:
                rname = "<<Unknown Resource>>"
            result = False
            message = "Calendar resource %s already exists with same UID %s" % (rname, uid)
        else:
            # Cannot overwrite a resource with different UID
            if self.destination.exists():
                olduid = yield index.resourceUIDForName(self.destination.name())
                if olduid != uid:
                    rname = self.destination.name()
                    result = False
                    message = "Cannot overwrite calendar resource %s with different UID %s" % (rname, olduid)

        returnValue((result, message, rname))


    @inlineCallbacks
    def doImplicitScheduling(self):

        data_changed = False
        did_implicit_action = False

        # Do scheduling
        if not self.isiTIP:
            scheduler = ImplicitScheduler()

            # Determine type of operation PUT, COPY or DELETE
            if not self.source:
                # PUT
                do_implicit_action, is_scheduling_resource = (yield scheduler.testImplicitSchedulingPUT(
                    self.request,
                    self.destination,
                    self.destination_uri,
                    self.calendar,
                    internal_request=self.internal_request,
                ))
            elif self.deletesource:
                # MOVE
                do_implicit_action, is_scheduling_resource = (yield scheduler.testImplicitSchedulingMOVE(
                    self.request,
                    self.source,
                    self.sourcecal,
                    self.source_uri,
                    self.destination,
                    self.destinationcal,
                    self.destination_uri,
                    self.calendar,
                    internal_request=self.internal_request,
                ))
            else:
                # COPY
                do_implicit_action, is_scheduling_resource = (yield scheduler.testImplicitSchedulingCOPY(
                    self.request,
                    self.source,
                    self.sourcecal,
                    self.source_uri,
                    self.destination,
                    self.destinationcal,
                    self.destination_uri,
                    self.calendar,
                    internal_request=self.internal_request,
                ))

            if do_implicit_action and self.allowImplicitSchedule:

                # Cannot do implicit in sharee's shared calendar
                isShareeCollection = self.destinationparent.isShareeCollection()
                if isShareeCollection:
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (calendarserver_namespace, "sharee-privilege-needed",),
                        description="Sharee's cannot schedule"
                    ))

                new_calendar = (yield scheduler.doImplicitScheduling(self.schedule_tag_match))
                if new_calendar:
                    if isinstance(new_calendar, int):
                        returnValue(new_calendar)
                    else:
                        self.calendar = new_calendar
                        data_changed = True
                did_implicit_action = True
        else:
            is_scheduling_resource = False

        returnValue((is_scheduling_resource, data_changed, did_implicit_action,))


    @inlineCallbacks
    def mergePerUserData(self):
        if self.calendar:
            accessUID = (yield self.destination.resourceOwnerPrincipal(self.request))
            accessUID = accessUID.principalUID() if accessUID else ""
            if self.destination.exists() and self.destinationcal:
                oldCal = yield self.destination.iCalendar()
            else:
                oldCal = None

            # Duplicate before we do the merge because someone else may "own" the calendar object
            # and we should not change it. This is not ideal as we may duplicate it unnecessarily
            # but we currently have no api to let the caller tell us whether it cares about the
            # whether the calendar data is changed or not.
            try:
                self.calendar = PerUserDataFilter(accessUID).merge(self.calendar.duplicate(), oldCal)
            except ValueError:
                log.err("Invalid per-user data merge")
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "valid-calendar-data"),
                    "Cannot merge per-user data",
                ))


    @inlineCallbacks
    def doStore(self, implicit):

        # Stash the current calendar data as we may need to return it
        if self.returnData:
            self.storeddata = str(self.calendar)

        # Always do the per-user data merge right before we store
        yield self.mergePerUserData()

        # Do put or copy based on whether source exists
        source = self.source
        if source is not None:
            # Retrieve information from the source, in case we have to delete
            # it.
            sourceProperties = dict(source.newStoreProperties().iteritems())
            if not implicit:
                # Only needed in implicit case; see below.
                sourceText = yield source.iCalendarText()

            # Delete the original source if needed (for example, if this is a
            # same-calendar MOVE of a calendar object, implemented as an
            # effective DELETE-then-PUT).
            if self.deletesource:
                yield self.doSourceDelete()

            if implicit:
                response = (yield self.doStorePut())
            else:
                response = (yield self.doStorePut(sourceText))
            self.destination.newStoreProperties().update(sourceProperties)
        else:
            response = (yield self.doStorePut())

        returnValue(response)


    @inlineCallbacks
    def doStorePut(self, data=None):

        if data is None:
            # We'll be passing this component directly to storeComponent( )
            componentToStore = self.calendar
            data = str(self.calendar)
        else:
            # We'll be passing data as a stream to storeStream( )
            componentToStore = None

        # Update calendar-access property value on the resource. We need to do this before the
        # store as the store will "commit" the new value.
        if self.access:
            self.destination.accessMode = self.access

        # Do not remove the property if access was not specified and we are storing in a calendar.
        # This ensure that clients that do not preserve the iCalendar property do not cause access
        # restrictions to be lost.
        elif not self.destinationcal:
            self.destination.accessMode = ""

        # Check for existence of private comments and write property
        if config.Scheduling.CalDAV.get("EnablePrivateComments", True):
            self.destination.hasPrivateComment = self.hasPrivateComments

        # Check for scheduling object resource and write property
        self.destination.isScheduleObject = self.isScheduleResource
        if self.isScheduleResource:
            # Need to figure out when to change the schedule tag:
            #
            # 1. If this is not an internal request then the resource is being explicitly changed
            # 2. If it is an internal request for the Organizer, schedule tag never changes
            # 3. If it is an internal request for an Attendee and the message being processed came
            #    from the Organizer then the schedule tag changes.

            change_scheduletag = True
            if self.internal_request:
                # Check what kind of processing is going on
                if self.processing_organizer == True:
                    # All auto-processed updates for an Organizer leave the tag unchanged
                    change_scheduletag = False
                elif self.processing_organizer == False:
                    # Auto-processed updates that are the result of an organizer "refresh" due
                    # to another Attendee's REPLY should leave the tag unchanged
                    change_scheduletag = not hasattr(self.request, "doing_attendee_refresh")

            if change_scheduletag or not self.destination.scheduleTag:
                self.destination.scheduleTag = str(uuid.uuid4())

            # Handle weak etag compatibility
            if config.Scheduling.CalDAV.ScheduleTagCompatibility:
                if change_scheduletag:
                    # Schedule-Tag change => weak ETag behavior must not happen
                    etags = ()
                else:
                    # Schedule-Tag did not change => add current ETag to list of those that can
                    # be used in a weak precondition test
                    etags = self.destination.scheduleEtags
                    if etags is None:
                        etags = ()
                etags += (hashlib.md5(data + (self.destination.scheduleTag if self.destination.scheduleTag else "")).hexdigest(),)
                self.destination.scheduleEtags = etags
            else:
                self.destination.scheduleEtags = ()
        else:
            self.destination.scheduleTag = ""
            self.destination.scheduleEtags = ()

        if componentToStore is None:
            stream = MemoryStream(data)
            response = yield self.destination.storeStream(stream)
        else:
            # Since we already have a component, we can pass it directly
            response = yield self.destination.storeComponent(componentToStore)
        response = IResponse(response)

        if self.isScheduleResource:
            # Add a response header
            response.headers.setHeader("Schedule-Tag", self.destination.scheduleTag)

        returnValue(response)


    @inlineCallbacks
    def doSourceDelete(self):
        # Delete the source resource
        yield self.source.storeRemove(self.request, False, self.source_uri)
        log.debug("Source removed %s" % (self.source,))
        returnValue(None)


    @inlineCallbacks
    def run(self):
        """
        Function that does common PUT/COPY/MOVE behavior.

        @return: a Deferred with a status response result.
        """

        try:
            reservation = None

            # Handle all validation operations here.
            yield self.fullValidation()

            # Reservation and UID conflict checking is next.
            if self.destinationcal:
                # Reserve UID
                self.destination_index = self.destinationparent.index()
                reservation = StoreCalendarObjectResource.UIDReservation(
                    self.destination_index, self.uid, self.destination_uri,
                    self.internal_request or self.isiTIP,
                    self.destination._associatedTransaction,
                )
                yield reservation.reserve()
                # UID conflict check - note we do this after reserving the UID to avoid a race condition where two requests
                # try to write the same calendar data to two different resource URIs.
                if not self.isiTIP:
                    result, message, rname = yield self.noUIDConflict(self.uid)
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            NoUIDConflict(
                                davxml.HRef.fromString(
                                    joinURL(
                                        parentForURL(self.destination_uri),
                                        rname.encode("utf-8")
                                    )
                                )
                            ),
                            "UID already exists",
                        ))

            # Preserve private comments
            yield self.preservePrivateComments()

            # Fix broken VTODOs
            yield self.replaceMissingToDoProperties()

            # Handle sharing dropbox normalization
            dropboxChanged = (yield self.dropboxPathNormalization())

            # Default/duplicate alarms
            alarmChanged = self.processAlarms()

            # Do scheduling
            implicit_result = (yield self.doImplicitScheduling())
            if isinstance(implicit_result, int):
                if implicit_result == ImplicitScheduler.STATUS_ORPHANED_CANCELLED_EVENT:
                    if reservation:
                        yield reservation.unreserve()

                    returnValue(StatusResponse(responsecode.CREATED, "Resource created but immediately deleted by the server."))

                elif implicit_result == ImplicitScheduler.STATUS_ORPHANED_EVENT:
                    if reservation:
                        yield reservation.unreserve()

                    # Now forcibly delete the event
                    if self.destination.exists():
                        yield self.destination.storeRemove(self.request, False, self.destination_uri)
                    else:
                        msg = "Attendee cannot create event for Organizer: %s" % (implicit_result,)
                        log.err(msg)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (caldav_namespace, "attendee-allowed"),
                            description=msg
                        ))

                    returnValue(StatusResponse(responsecode.OK, "Resource modified but immediately deleted by the server."))

                else:
                    msg = "Invalid return status code from ImplicitScheduler: %s" % (implicit_result,)
                    log.err(msg)
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (caldav_namespace, "valid-calendar-data"),
                        description=msg
                    ))
            else:
                self.isScheduleResource, data_changed, did_implicit_action = implicit_result

            # Do the actual put or copy
            response = (yield self.doStore(data_changed))

            # Must not set ETag in response if data changed
            if did_implicit_action or dropboxChanged or alarmChanged:
                def _removeEtag(request, response):
                    response.headers.removeHeader('etag')
                    return response
                _removeEtag.handleErrors = True

                self.request.addResponseFilter(_removeEtag, atEnd=True)

            if reservation:
                yield reservation.unreserve()

            returnValue(response)

        except Exception, err:

            if reservation:
                yield reservation.unreserve()

            if isinstance(err, InvalidOverriddenInstanceError):
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "valid-calendar-data"),
                    description="Invalid overridden instance"
                ))
            elif isinstance(err, TooManyInstancesError):
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    MaxInstances.fromString(str(err.max_allowed)),
                    "Too many recurrence instances",
                ))
            elif isinstance(err, AttachmentStoreValidManagedID):
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "valid-managed-id"),
                    "Invalid Managed-ID parameter in calendar data",
                ))
            else:
                raise err
