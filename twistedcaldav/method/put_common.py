##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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

import os
import types
import uuid

from twext.web2.dav.davxml import ErrorResponse

from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet.defer import returnValue
from twisted.python import failure
from twisted.python.filepath import FilePath
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.element.base import PCDATAElement
from twisted.web2.dav.fileop import delete
from twisted.web2.dav.resource import TwistedGETContentMD5
from twisted.web2.dav.stream import MD5StreamWrapper
from twisted.web2.dav.util import joinURL, parentForURL
from twisted.web2.http import HTTPError
from twisted.web2.http import StatusResponse
from twisted.web2.http_headers import generateContentType, MimeType
from twisted.web2.iweb import IResponse
from twisted.web2.stream import MemoryStream

from twistedcaldav.config import config
from twistedcaldav.caldavxml import NoUIDConflict, ScheduleTag
from twistedcaldav.caldavxml import NumberOfRecurrencesWithinLimits
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.customxml import calendarserver_namespace ,\
    TwistedCalendarHasPrivateCommentsProperty, TwistedSchedulingObjectResource,\
    TwistedScheduleMatchETags
from twistedcaldav.customxml import TwistedCalendarAccessProperty
from twistedcaldav.fileops import copyToWithXAttrs, copyXAttrs
from twistedcaldav.fileops import putWithXAttrs
from twistedcaldav.fileops import copyWithXAttrs
from twistedcaldav.ical import Component, Property
from twistedcaldav.index import ReservationError
from twistedcaldav.instance import TooManyInstancesError,\
    InvalidOverriddenInstanceError
from twistedcaldav.log import Logger
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.method.delete_common import DeleteResource
from twistedcaldav.scheduling.implicit import ImplicitScheduler

log = Logger()

class StoreCalendarObjectResource(object):
    
    class RollbackState(object):
        """
        This class encapsulates the state needed to rollback the entire PUT/COPY/MOVE
        transaction, leaving the server state the same as it was before the request was
        processed. The DoRollback method will actually execute the rollback operations.
        """
        
        def __init__(self, storer):
            self.storer = storer
            self.active = True
            self.source_copy = None
            self.destination_copy = None
            self.destination_created = False
            self.source_deleted = False
            self.source_index_deleted = False
            self.destination_index_deleted = False
        
        def Rollback(self):
            """
            Rollback the server state. Do not allow this to raise another exception. If
            rollback fails then we are going to be left in an awkward state that will need
            to be cleaned up eventually.
            """
            if self.active:
                self.active = False
                log.debug("Rollback: rollback")
                try:
                    if self.source_copy and self.source_deleted:
                        self.source_copy.moveTo(self.storer.source.fp)
                        log.debug("Rollback: source restored %s to %s" % (self.source_copy.path, self.storer.source.fp.path))
                        self.source_copy = None
                        self.source_deleted = False
                    if self.destination_copy:
                        self.storer.destination.fp.remove()
                        log.debug("Rollback: destination restored %s to %s" % (self.destination_copy.path, self.storer.destination.fp.path))
                        self.destination_copy.moveTo(self.storer.destination.fp)
                        self.destination_copy = None
                    elif self.destination_created:
                        if self.storer.destinationcal:
                            self.storer.doRemoveDestinationIndex()
                            log.debug("Rollback: destination index removed %s" % (self.storer.destination.fp.path,))
                            self.destination_index_deleted = False
                        self.storer.destination.fp.remove()
                        log.debug("Rollback: destination removed %s" % (self.storer.destination.fp.path,))
                        self.destination_created = False
                    if self.destination_index_deleted:
                        # Must read in calendar for destination being re-indexed
                        self.storer.destination.iCalendar().addCallback(self.storer.doDestinationIndex)
                        self.destination_index_deleted = False
                        log.debug("Rollback: destination re-indexed %s" % (self.storer.destination.fp.path,))
                    if self.source_index_deleted:
                        self.storer.doSourceIndexRecover()
                        self.destination_index_deleted = False
                        log.debug("Rollback: source re-indexed %s" % (self.storer.source.fp.path,))
                except:
                    log.err("Rollback: exception caught and not handled: %s" % failure.Failure())

        def Commit(self):
            """
            Commit the resource changes by wiping the rollback state.
            """
            if self.active:
                log.debug("Rollback: commit")
                self.active = False
                if self.source_copy:
                    self.source_copy.remove()
                    log.debug("Rollback: removed source backup %s" % (self.source_copy.path,))
                    self.source_copy = None
                if self.destination_copy:
                    self.destination_copy.remove()
                    log.debug("Rollback: removed destination backup %s" % (self.destination_copy.path,))
                    self.destination_copy = None
                self.destination_created = False
                self.source_deleted = False
                self.source_index_deleted = False
                self.destination_index_deleted = False

    class UIDReservation(object):
        
        def __init__(self, index, uid, uri, internal_request):
            if internal_request:
                self.lock = None
            else:
                self.lock = MemcacheLock("ImplicitUIDLock", uid, timeout=60.0)
            self.reserved = False
            self.index = index
            self.uid = uid
            self.uri = uri
            
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
                    yield self.lock.release()
                raise HTTPError(StatusResponse(responsecode.CONFLICT, "Resource: %s currently in use in calendar." % (self.uri,)))
        
        @inlineCallbacks
        def unreserve(self):
            if self.reserved:
                yield self.index.unreserveUID(self.uid)
                self.reserved = False
            if self.lock:
                yield self.lock.clean()

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
    ):
        """
        Function that does common PUT/COPY/MOVE behavior.
        
        @param request:           the L{twisted.web2.server.Request} for the current HTTP request.
        @param source:            the L{CalDAVFile} for the source resource to copy from, or None if source data
            is to be read from the request.
        @param source_uri:        the URI for the source resource.
        @param destination:       the L{CalDAVFile} for the destination resource to copy into.
        @param destination_uri:   the URI for the destination resource.
        @param calendar:          the C{str} or L{Component} calendar data if there is no source, None otherwise.
        @param sourcecal:         True if the source resource is in a calendar collection, False otherwise.
        @param destinationcal:    True if the destination resource is in a calendar collection, False otherwise
        @param sourceparent:      the L{CalDAVFile} for the source resource's parent collection, or None if source is None.
        @param destinationparent: the L{CalDAVFile} for the destination resource's parent collection.
        @param deletesource:      True if the source resource is to be deleted on successful completion, False otherwise.
        @param isiTIP:                True if relaxed calendar data validation is to be done, False otherwise.
        @param allowImplicitSchedule: True if implicit scheduling should be attempted, False otherwise.
        @param internal_request:   True if this request originates internally and needs to bypass scheduling authorization checks.
        @param processing_organizer: True if implicit processing for an organizer, False if for an attendee, None if not implicit processing.
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
        self.calendardata = None
        self.deletesource = deletesource
        self.isiTIP = isiTIP
        self.allowImplicitSchedule = allowImplicitSchedule
        self.internal_request = internal_request
        self.processing_organizer = processing_organizer
        
        self.rollback = None
        self.access = None

    @inlineCallbacks
    def fullValidation(self):
        """
        Do full validation of source and destination calendar data.
        """

        # Basic validation
        yield self.validCopyMoveOperation()
        self.validIfScheduleMatch()

        if self.destinationcal:
            # Valid resource name check
            result, message = self.validResourceName()
            if not result:
                log.err(message)
                raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Resource name not allowed"))

            # Valid data sizes - do before parsing the data
            if self.source is not None:
                # Valid content length check on the source resource
                result, message = self.validContentLength()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "max-resource-size")))
            else:
                # Valid calendar data size check
                result, message = self.validSizeCheck()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "max-resource-size")))

            if not self.sourcecal:
                # Valid content type check on the source resource if its not in a calendar collection
                if self.source is not None:
                    result, message = self.validContentType()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
                
                    # At this point we need the calendar data to do more tests
                    self.calendar = yield self.source.iCalendar()
                else:
                    try:
                        if type(self.calendar) in (types.StringType, types.UnicodeType,):
                            self.calendardata = self.calendar
                            self.calendar = Component.fromString(self.calendar)
                    except ValueError, e:
                        log.err(str(e))
                        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"), description="Can't parse calendar data"))
                        
                # Valid calendar data check
                result, message = self.validCalendarDataCheck()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"), description=message))
                    
                # Valid calendar data for CalDAV check
                result, message = self.validCalDAVDataCheck()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-object-resource")))

                # Valid attendee list size check
                result, message = self.validAttendeeListSizeCheck()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "max-attendees-per-instance")))

                # Normalize the calendar user addresses once we know we have valid
                # calendar data
                self.destination.iCalendarAddressDoNormalization(self.calendar)

                # Must have a valid UID at this point
                self.uid = self.calendar.resourceUID()
            else:
                # Get UID from original resource
                self.source_index = self.sourceparent.index()
                self.uid = self.source_index.resourceUIDForName(self.source.fp.basename())
                if self.uid is None:
                    log.err("Source calendar does not have a UID: %s" % self.source.fp.basename())
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-object-resource")))

                # FIXME: We need this here because we have to re-index the destination. Ideally it
                # would be better to copy the index entries from the source and add to the destination.
                self.calendar = yield self.source.iCalendar()

            # Check access
            if self.destinationcal and config.EnablePrivateEvents:
                result = (yield self.validAccess())
                returnValue(result)
            else:
                returnValue(None)

        elif self.sourcecal:
            self.source_index = self.sourceparent.index()
            self.calendar = yield self.source.iCalendar()
    
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
                # Calendar to calendar moves are OK if the owner is the same
                sourceowner = (yield self.sourceparent.owner(self.request))
                destowner = (yield self.destinationparent.owner(self.request))
                if sourceowner != destowner:
                    msg = "Calendar-to-calendar %s with different owners are not supported" % ("moves" if self.deletesource else "copies",)
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
                # Do "precondition" test
                
                # If COPY/MOVE get Schedule-Tag on source, else use destination
                def _getScheduleTag(resource):
                    return resource.readDeadProperty(ScheduleTag) if resource.exists() and resource.hasDeadProperty(ScheduleTag) else None

                scheduletag = _getScheduleTag(self.source if self.source else self.destination)
                if scheduletag != header:
                    log.debug("If-Schedule-Tag-Match: header value '%s' does not match resource value '%s'" % (header, scheduletag,))
                    raise HTTPError(responsecode.PRECONDITION_FAILED)
                self.schedule_tag_match = True
            
            elif config.Scheduling.CalDAV.ScheduleTagCompatibility:
                # Compatibility with old clients. Policy:
                #
                # 1. If If-Match header is not present, never do smart merge.
                # 2. If If-Match is present and the specified ETag is considered a "weak" match to the
                #    current Schedule-Tag, then do smart merge, else reject with a 412.
                #
                # Actually by the time we get here the pre-condition will already have been tested and found to be OK,
                # so we can just always do smart merge now if If-Match is present.

                self.schedule_tag_match = self.request.headers.getHeader("If-Match") is not None

    def validResourceName(self):
        """
        Make sure that the resource name for the new resource is valid.
        """
        result = True
        message = ""
        filename = self.destination.fp.basename()
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
        if config.MaximumAttachmentSize:
            calsize = self.source.contentLength()
            if calsize is not None and calsize > config.MaximumAttachmentSize:
                result = False
                message = "File size %d bytes is larger than allowed limit %d bytes" % (calsize, config.MaximumAttachmentSize)

        return result, message
        
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
                self.calendar.validCalendarForCalDAV()
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
            if self.isiTIP:
                self.calendar.validateComponentsForCalDAV(True)
            else:
                self.calendar.validateForCalDAV()
        except ValueError, e:
            result = False
            message = "Calendar data does not conform to CalDAV requirements: %s" % (e,)
        
        return result, message
    
    def validSizeCheck(self):
        """
        Make sure that the content-type of the source resource is text/calendar.
        This test is only needed when the source is not in a calendar collection.
        """
        result = True
        message = ""
        if config.MaximumAttachmentSize:
            calsize = len(str(self.calendar))
            if calsize > config.MaximumAttachmentSize:
                result = False
                message = "Data size %d bytes is larger than allowed limit %d bytes" % (calsize, config.MaximumAttachmentSize)

        return result, message

    def validAttendeeListSizeCheck(self):
        """
        Make sure that the Attendee list length is within bounds.
        """
        result = True
        message = ""
        if config.MaxAttendeesPerInstance:
            uniqueAttendees = set()
            for attendee in self.calendar.getAllAttendeeProperties():
                uniqueAttendees.add(attendee.value())
            attendeeListLength = len(uniqueAttendees)
            if attendeeListLength > config.MaxAttendeesPerInstance:
                result = False
                message = "Attendee list size %d is larger than allowed limit %d" % (attendeeListLength, config.MaxAttendeesPerInstance)

        return result, message

    def validAccess(self):
        """
        Make sure that the X-CALENDARSERVER-ACCESS property is properly dealt with.
        """
        
        if self.calendar.hasProperty(Component.ACCESS_PROPERTY):
            
            # Must be a value we know about
            self.access = self.calendar.accessLevel(default=None)
            if self.access is None:
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (calendarserver_namespace, "valid-access-restriction")))
                
            # Only DAV:owner is able to set the property to other than PUBLIC
            if not self.internal_request:
                def _callback(parent_owner):
                    
                    authz = self.destinationparent.currentPrincipal(self.request)
                    if davxml.Principal(parent_owner) != authz and self.access != Component.ACCESS_PUBLIC:
                        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (calendarserver_namespace, "valid-access-restriction-change")))
                    
                    return None
    
                d = self.destinationparent.owner(self.request)
                d.addCallback(_callback)
                return d
        else:
            # Check whether an access property was present before and write that into the calendar data
            if not self.source and self.destination.exists() and self.destination.hasDeadProperty(TwistedCalendarAccessProperty):
                old_access = str(self.destination.readDeadProperty(TwistedCalendarAccessProperty))
                self.calendar.addProperty(Property(name=Component.ACCESS_PROPERTY, value=old_access))
                self.calendardata = str(self.calendar)
                
        return succeed(None)

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
        if self.sourceparent and (self.sourceparent.fp.path == self.destinationparent.fp.path) and self.deletesource:
            oldname = self.source.fp.basename()

        # UID must be unique
        index = self.destinationparent.index()
        if not index.isAllowedUID(uid, oldname, self.destination.fp.basename()):
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
            if self.destination.fp.exists():
                olduid = index.resourceUIDForName(self.destination.fp.basename())
                if olduid != uid:
                    rname = self.destination.fp.basename()
                    result = False
                    message = "Cannot overwrite calendar resource %s with different UID %s" % (rname, olduid)
        
        returnValue((result, message, rname))

    @inlineCallbacks
    def checkQuota(self):
        """
        Get quota details for destination and source before we start messing with adding other files.
        """

        if self.request is None:
            self.destquota = None
        else:
            self.destquota = (yield self.destination.quota(self.request))
            if self.destquota is not None and self.destination.exists():
                self.old_dest_size = (yield self.destination.quotaSize(self.request))
            else:
                self.old_dest_size = 0
            
        if self.request is None:
            self.sourcequota = None
        elif self.source is not None:
            self.sourcequota = (yield self.source.quota(self.request))
            if self.sourcequota is not None and self.source.exists():
                self.old_source_size = (yield self.source.quotaSize(self.request))
            else:
                self.old_source_size = 0
        else:
            self.sourcequota = None
            self.old_source_size = 0

        returnValue(None)

    def setupRollback(self):
        """
        We may need to restore the original resource data if the PUT/COPY/MOVE fails,
        so rename the original file in case we need to rollback.
        """

        def _createRollbackPath(path):
            parent, child = os.path.split(path)
            child = "." + child + ".rollback"
            return os.path.join(parent, child)

        self.rollback = StoreCalendarObjectResource.RollbackState(self)
        self.overwrite = self.destination.exists()
        if self.overwrite:
            self.rollback.destination_copy = FilePath(_createRollbackPath(self.destination.fp.path))
            copyToWithXAttrs(self.destination.fp, self.rollback.destination_copy)
            log.debug("Rollback: backing up destination %s to %s" % (self.destination.fp.path, self.rollback.destination_copy.path))
        else:
            self.rollback.destination_created = True
            log.debug("Rollback: will create new destination %s" % (self.destination.fp.path,))

        if self.deletesource:
            self.rollback.source_copy = FilePath(_createRollbackPath(self.source.fp.path))
            copyToWithXAttrs(self.source.fp, self.rollback.source_copy)
            log.debug("Rollback: backing up source %s to %s" % (self.source.fp.path, self.rollback.source_copy.path))

    def truncateRecurrence(self):
        
        if config.MaxInstancesForRRULE != 0:
            try:
                result = self.calendar.truncateRecurrence(config.MaxInstancesForRRULE)
            except (ValueError, TypeError), ex:
                msg = "Cannot truncate calendar resource: %s" % (ex,)
                log.err(msg)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"), description=msg))
            if result:
                self.calendardata = str(self.calendar)
                return result
        else:
            return False

    def preservePrivateComments(self):
        # Check for private comments on the old resource and the new resource and re-insert
        # ones that are lost.
        #
        # NB Do this before implicit scheduling as we don't want old clients to trigger scheduling when
        # the X- property is missing.
        new_has_private_comments = False
        if config.Scheduling.CalDAV.get("EnablePrivateComments", True) and self.calendar is not None:
            old_has_private_comments = self.destination.exists() and self.destinationcal and self.destination.hasDeadProperty(TwistedCalendarHasPrivateCommentsProperty)
            new_has_private_comments = self.calendar.hasPropertyInAnyComponent((
                "X-CALENDARSERVER-PRIVATE-COMMENT",
                "X-CALENDARSERVER-ATTENDEE-COMMENT",
            ))
            
            if old_has_private_comments and not new_has_private_comments:
                # Transfer old comments to new calendar
                log.debug("Private Comments properties were entirely removed by the client. Restoring existing properties.")
                self.destination.iCalendar().addCallback(self.calendar.transferProperties,
                                                         "X-CALENDARSERVER-PRIVATE-COMMENT",
                                                         "X-CALENDARSERVER-ATTENDEE-COMMENT")
                self.calendardata = None
        
        return new_has_private_comments

    @inlineCallbacks
    def doImplicitScheduling(self):

        # Get any existing schedule-tag property on the resource
        if self.destination.exists() and self.destination.hasDeadProperty(ScheduleTag):
            self.scheduletag = self.destination.readDeadProperty(ScheduleTag)
            if self.scheduletag:
                self.scheduletag = str(self.scheduletag)
        else:
            self.scheduletag = None

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
                new_calendar = (yield scheduler.doImplicitScheduling(self.schedule_tag_match))
                if new_calendar:
                    if isinstance(new_calendar, int):
                        returnValue(new_calendar)
                    else:
                        self.calendar = new_calendar
                        self.calendardata = str(self.calendar)
                        data_changed = True
                did_implicit_action = True
        else:
            is_scheduling_resource = False
            
        returnValue((is_scheduling_resource, data_changed, did_implicit_action,))

    @inlineCallbacks
    def doStore(self, implicit):
        # Do put or copy based on whether source exists
        if self.source is not None:
            if implicit:
                response = (yield self.doStorePut())
                copyXAttrs(self.source.fp, self.destination.fp)
            else:
                response = (yield copyWithXAttrs(self.source.fp, self.destination.fp, self.destination_uri))
        else:
            response = (yield self.doStorePut())
    
        # Update calendar-access property value on the resource
        if self.access:
            self.destination.writeDeadProperty(TwistedCalendarAccessProperty(self.access))
            
        # Do not remove the property if access was not specified and we are storing in a calendar.
        # This ensure that clients that do not preserve the iCalendar property do not cause access
        # restrictions to be lost.
        elif not self.destinationcal:
            self.destination.removeDeadProperty(TwistedCalendarAccessProperty)                

        returnValue(IResponse(response))

    @inlineCallbacks
    def doStorePut(self):

        if self.calendardata is None:
            self.calendardata = str(self.calendar)
        md5 = MD5StreamWrapper(MemoryStream(self.calendardata))
        response = (yield putWithXAttrs(md5, self.destination.fp))

        # Finish MD5 calculation and write dead property
        md5.close()
        md5 = md5.getMD5()
        self.destination.writeDeadProperty(TwistedGETContentMD5.fromString(md5))

        returnValue(response)

    @inlineCallbacks
    def doSourceDelete(self):
        # Delete index for original item
        if self.sourcecal:
            self.source_index.deleteResource(self.source.fp.basename())
            self.rollback.source_index_deleted = True
            log.debug("Source index removed %s" % (self.source.fp.path,))

        # Delete the source resource
        delete(self.source_uri, self.source.fp, "0")
        self.rollback.source_deleted = True
        log.debug("Source removed %s" % (self.source.fp.path,))

        # Change CTag on the parent calendar collection
        if self.sourcecal:
            yield self.sourceparent.updateCTag()
  
        returnValue(None)

    @inlineCallbacks
    def doSourceQuotaCheck(self):
        # Update quota
        if self.sourcequota is not None:
            delete_size = 0 - self.old_source_size
            yield self.source.quotaSizeAdjust(self.request, delete_size)
  
        returnValue(None)

    @inlineCallbacks
    def doDestinationQuotaCheck(self):
        # Get size of new/old resources
        new_dest_size = (yield self.destination.quotaSize(self.request))

        diff_size = new_dest_size - self.old_dest_size

        if diff_size >= self.destquota[0]:
            log.err("Over quota: available %d, need %d" % (self.destquota[0], diff_size))
            raise HTTPError(ErrorResponse(responsecode.INSUFFICIENT_STORAGE_SPACE, (dav_namespace, "quota-not-exceeded")))
        yield self.destination.quotaSizeAdjust(self.request, diff_size)

        returnValue(None)

    def doSourceIndexRecover(self):
        """
        Do source resource indexing. This only gets called when restoring
        the source after its index has been deleted.
        
        @return: None if successful, ErrorResponse on failure
        """
        
        # Add or update the index for this resource.
        try:
            self.source_index.addResource(self.source.fp.basename(), self.calendar)
        except TooManyInstancesError, ex:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                    NumberOfRecurrencesWithinLimits(PCDATAElement(str(ex.max_allowed)))
                ))
            return None

    def doDestinationIndex(self, caltoindex):
        """
        Do destination resource indexing, replacing any index previous stored.
        
        @return: None if successful, ErrorResponse on failure
        """
        
        # Delete index for original item
        if self.overwrite:
            self.doRemoveDestinationIndex()
        
        # Add or update the index for this resource.
        try:
            self.destination_index.addResource(self.destination.fp.basename(), caltoindex)
            log.debug("Destination indexed %s" % (self.destination.fp.path,))
        except TooManyInstancesError, ex:
            log.err("Cannot index calendar resource as there are too many recurrence instances %s" % self.destination)
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                NumberOfRecurrencesWithinLimits(PCDATAElement(str(ex.max_allowed)))
            ))
        except (ValueError, TypeError), ex:
            msg = "Cannot index calendar resource: %s" % (ex,)
            log.err(msg)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"), description=msg))

        content_type = self.request.headers.getHeader("content-type")
        if not self.internal_request and content_type is not None:
            self.destination.writeDeadProperty(davxml.GETContentType.fromString(generateContentType(content_type)))
        else:
            self.destination.writeDeadProperty(davxml.GETContentType.fromString(generateContentType(MimeType("text", "calendar", params={"charset":"utf-8"}))))
        return None

    def doRemoveDestinationIndex(self):
        """
        Remove any existing destination index.
        """
        
        # Delete index for original item
        if self.destinationcal:
            self.destination_index.deleteResource(self.destination.fp.basename())
            self.rollback.destination_index_deleted = True
            log.debug("Destination index removed %s" % (self.destination.fp.path,))

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
                reservation = StoreCalendarObjectResource.UIDReservation(self.destination_index, self.uid, self.destination_uri, self.internal_request or self.isiTIP)
                yield reservation.reserve()
            
                # UID conflict check - note we do this after reserving the UID to avoid a race condition where two requests
                # try to write the same calendar data to two different resource URIs.
                if not self.isiTIP:
                    result, message, rname = yield self.noUIDConflict(self.uid)
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN,
                            NoUIDConflict(davxml.HRef.fromString(joinURL(parentForURL(self.destination_uri), rname.encode("utf-8"))))
                        ))
            
            # Get current quota state.
            yield self.checkQuota()
    
            # Handle RRULE truncation
            rruleChanged = self.truncateRecurrence()

            # Preserve private comments
            new_has_private_comments = self.preservePrivateComments()
    
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
                    deleter = DeleteResource(self.request, self.destination, self.destination_uri, self.destinationparent, "0", internal_request=True)
                    yield deleter.run()

                    returnValue(StatusResponse(responsecode.OK, "Resource modified but immediately deleted by the server."))

                else:
                    msg = "Invalid return status code from ImplicitScheduler: %s" % (implicit_result,)
                    log.err(msg)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"), description=msg))
            else:
                is_scheduling_resource, data_changed, did_implicit_action = implicit_result

            # Initialize the rollback system
            self.setupRollback()

            """
            Handle actual store operations here.
            
            The order in which this is done is import:
                
                1. Do store operation for new data
                2. Delete source and source index if needed
                3. Do new indexing if needed
                
            Note that we need to remove the source index BEFORE doing the destination index to cover the
            case of a resource being 'renamed', i.e. moved within the same collection. Since the index UID
            column must be unique in SQL, we cannot add the new index before remove the old one.
            """
    
            # Do the actual put or copy
            response = (yield self.doStore(data_changed))
            
            # Must not set ETag in response if data changed
            if did_implicit_action or rruleChanged:
                def _removeEtag(request, response):
                    response.headers.removeHeader('etag')
                    return response
                _removeEtag.handleErrors = True

                self.request.addResponseFilter(_removeEtag, atEnd=True)

            # Check for scheduling object resource and write property
            if is_scheduling_resource:
                self.destination.writeDeadProperty(TwistedSchedulingObjectResource.fromString("true"))

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
                        # Auto-processed updates that are the result of an organizer "refresh' due
                        # to another Attendee's REPLY should leave the tag unchanged
                        change_scheduletag = not hasattr(self.request, "doing_attendee_refresh")

                if change_scheduletag or self.scheduletag is None:
                    self.scheduletag = str(uuid.uuid4())
                self.destination.writeDeadProperty(ScheduleTag.fromString(self.scheduletag))

                # Add a response header
                response.headers.setHeader("Schedule-Tag", self.scheduletag)                

                # Handle weak etag compatibility
                if config.Scheduling.CalDAV.ScheduleTagCompatibility:
                    if change_scheduletag:
                        # Schedule-Tag change => weak ETag behavior must not happen
                        etags = ()
                    else:
                        # Schedule-Tag did not change => add current ETag to list of those that can
                        # be used in a weak pre-condition test
                        if self.destination.hasDeadProperty(TwistedScheduleMatchETags):
                            etags = self.destination.readDeadProperty(TwistedScheduleMatchETags).children
                        else:
                            etags = ()
                    etags += (davxml.GETETag.fromString(self.destination.etag().tag),)
                    self.destination.writeDeadProperty(TwistedScheduleMatchETags(*etags))
                else:
                    self.destination.removeDeadProperty(TwistedScheduleMatchETags)                
            else:
                self.destination.writeDeadProperty(TwistedSchedulingObjectResource.fromString("false"))                
                self.destination.removeDeadProperty(ScheduleTag)                
                self.destination.removeDeadProperty(TwistedScheduleMatchETags)                

            # Check for existence of private comments and write property
            if config.Scheduling.CalDAV.get("EnablePrivateComments", True):
                if new_has_private_comments:
                    self.destination.writeDeadProperty(TwistedCalendarHasPrivateCommentsProperty())
                elif not self.destinationcal:
                    self.destination.removeDeadProperty(TwistedCalendarHasPrivateCommentsProperty)                

            # Delete the original source if needed.
            if self.deletesource:
                yield self.doSourceDelete()
    
            # Index the new resource if storing to a calendar.
            if self.destinationcal:
                result = self.doDestinationIndex(self.calendar)
                if result is not None:
                    self.rollback.Rollback()
                    returnValue(result)
    
            # Delete the original source if needed.
            if self.deletesource:
                yield self.doSourceQuotaCheck()

            # Do quota check on destination
            if self.destquota is not None:
                yield self.doDestinationQuotaCheck()
    
            if self.destinationcal:
                # Change CTag on the parent calendar collection
                yield self.destinationparent.updateCTag()
    
            # Can now commit changes and forget the rollback details
            self.rollback.Commit()
    
            if reservation:
                yield reservation.unreserve()
    
            returnValue(response)
    
        except Exception, err:
            if reservation:
                yield reservation.unreserve()
    
            # Roll back changes to original server state. Note this may do nothing
            # if the rollback has already occurred or changes already committed.
            if self.rollback:
                self.rollback.Rollback()

            if isinstance(err, InvalidOverriddenInstanceError):
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"), description="Invalid overridden instance"))
            elif isinstance(err, TooManyInstancesError):
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                        NumberOfRecurrencesWithinLimits(PCDATAElement(str(err.max_allowed)))
                    ))
            else:
                raise err
