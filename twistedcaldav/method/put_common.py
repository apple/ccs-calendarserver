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
PUT/COPY/MOVE common behavior.
"""

__all__ = ["StoreCalendarObjectResource"]

import types

from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet.defer import maybeDeferred, returnValue
from twisted.python import failure
from twisted.python.filepath import FilePath
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.element.base import PCDATAElement
from twisted.web2.dav.fileop import delete
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.resource import TwistedGETContentMD5
from twisted.web2.dav.stream import MD5StreamWrapper
from twisted.web2.dav.util import joinURL, parentForURL
from twisted.web2.http import HTTPError
from twisted.web2.http import StatusResponse
from twisted.web2.iweb import IResponse
from twisted.web2.stream import MemoryStream

from twistedcaldav.config import config
from twistedcaldav.caldavxml import NoUIDConflict
from twistedcaldav.caldavxml import NumberOfRecurrencesWithinLimits
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.customxml import calendarserver_namespace 
from twistedcaldav.customxml import TwistedCalendarAccessProperty
from twistedcaldav.fileops import copyToWithXAttrs
from twistedcaldav.fileops import putWithXAttrs
from twistedcaldav.fileops import copyWithXAttrs
from twistedcaldav.ical import Component, Property
from twistedcaldav.index import ReservationError
from twistedcaldav.instance import TooManyInstancesError
from twistedcaldav.log import Logger
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
                        self.storer.doDestinationIndex(self.storer.destination.iCalendar())
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
        
        def __init__(self, index, uid, uri):
            self.reserved = False
            self.index = index
            self.uid = uid
            self.uri = uri
            
        @inlineCallbacks
        def reserve(self):
            
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
                raise HTTPError(StatusResponse(responsecode.CONFLICT, "Resource: %s currently in use." % (self.uri,)))
        
        @inlineCallbacks
        def unreserve(self):
            if self.reserved:
                yield self.index.unreserveUID(self.uid)
                self.reserved = False

    def __init__(
        self,
        request,
        source=None, source_uri=None, sourceparent=None, sourcecal=False, deletesource=False,
        destination=None, destination_uri=None, destinationparent=None, destinationcal=True,
        calendar=None,
        isiTIP=False,
        allowImplicitSchedule=True,
        internal_request=False,
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
        
        self.rollback = None
        self.access = None

    def fullValidation(self):
        """
        Do full validation of source and destination calendar data.
        """

        if self.destinationcal:
            # Valid resource name check
            result, message = self.validResourceName()
            if not result:
                log.err(message)
                raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Resource name not allowed"))

            if not self.sourcecal:
                # Valid content type check on the source resource if its not in a calendar collection
                if self.source is not None:
                    result, message = self.validContentType()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
                
                    # At this point we need the calendar data to do more tests
                    self.calendar = self.source.iCalendar()
                else:
                    try:
                        if type(self.calendar) in (types.StringType, types.UnicodeType,):
                            self.calendardata = self.calendar
                            self.calendar = Component.fromString(self.calendar)
                    except ValueError, e:
                        log.err(str(e))
                        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
                        
                # Valid calendar data check
                result, message = self.validCalendarDataCheck()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
                    
                # Valid calendar data for CalDAV check
                result, message = self.validCalDAVDataCheck()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-object-resource")))

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
                self.calendar = self.source.iCalendar()

            # Valid calendar data size check
            result, message = self.validSizeCheck()
            if not result:
                log.err(message)
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "max-resource-size")))

            # Check access
            if self.destinationcal and config.EnablePrivateEvents:
                return self.validAccess()
            else:
                return succeed(None)
    
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
            rname = index.resourceNameForUID(uid)
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
        
        return result, message, rname

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

        self.rollback = StoreCalendarObjectResource.RollbackState(self)
        self.overwrite = self.destination.exists()
        if self.overwrite:
            self.rollback.destination_copy = FilePath(self.destination.fp.path)
            self.rollback.destination_copy.path += ".rollback"
            copyToWithXAttrs(self.destination.fp, self.rollback.destination_copy)
            log.debug("Rollback: backing up destination %s to %s" % (self.destination.fp.path, self.rollback.destination_copy.path))
        else:
            self.rollback.destination_created = True
            log.debug("Rollback: will create new destination %s" % (self.destination.fp.path,))

        if self.deletesource:
            self.rollback.source_copy = FilePath(self.source.fp.path)
            self.rollback.source_copy.path += ".rollback"
            copyToWithXAttrs(self.source.fp, self.rollback.source_copy)
            log.debug("Rollback: backing up source %s to %s" % (self.source.fp.path, self.rollback.source_copy.path))

    @inlineCallbacks
    def doStore(self):
        # Do put or copy based on whether source exists
        if self.source is not None:
            response = maybeDeferred(copyWithXAttrs, self.source.fp, self.destination.fp, self.destination_uri)
        else:
            if self.calendardata is None:
                self.calendardata = str(self.calendar)
            md5 = MD5StreamWrapper(MemoryStream(self.calendardata))
            response = maybeDeferred(putWithXAttrs, md5, self.destination.fp)
        response = (yield response)

        # Update the MD5 value on the resource
        if self.source is not None:
            # Copy MD5 value from source to destination
            if self.source.hasDeadProperty(TwistedGETContentMD5):
                md5 = self.source.readDeadProperty(TwistedGETContentMD5)
                self.destination.writeDeadProperty(md5)
        else:
            # Finish MD5 calculation and write dead property
            md5.close()
            md5 = md5.getMD5()
            self.destination.writeDeadProperty(TwistedGETContentMD5.fromString(md5))
    
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

        # Update quota
        if self.sourcequota is not None:
            delete_size = 0 - self.old_source_size
            yield self.source.quotaSizeAdjust(self.request, delete_size)

        # Change CTag on the parent calendar collection
        if self.sourcecal:
            yield self.sourceparent.updateCTag()
  
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

            self.source.writeDeadProperty(davxml.GETContentType.fromString("text/calendar"))
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
            log.err("Cannot index calendar resource: %s" % (ex,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

        self.destination.writeDeadProperty(davxml.GETContentType.fromString("text/calendar"))
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
                reservation = StoreCalendarObjectResource.UIDReservation(self.destination_index, self.uid, self.destination_uri)
                yield reservation.reserve()
            
                # UID conflict check - note we do this after reserving the UID to avoid a race condition where two requests
                # try to write the same calendar data to two different resource URIs.
                if not self.isiTIP:
                    result, message, rname = self.noUIDConflict(self.uid)
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN,
                            NoUIDConflict(davxml.HRef.fromString(joinURL(parentForURL(self.destination_uri), rname.encode("utf-8"))))
                        ))
            
            # Get current quota state.
            yield self.checkQuota()

            # Do scheduling
            if not self.isiTIP and self.allowImplicitSchedule:
                scheduler = ImplicitScheduler()
                new_calendar = (yield scheduler.doImplicitScheduling(self.request, self.destination, self.calendar, False, internal_request=self.internal_request))
                if new_calendar:
                    self.calendar = new_calendar
                    self.calendardata = str(self.calendar)

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
            response = (yield self.doStore())
            
            # Delete the original source if needed.
            if self.deletesource:
                yield self.doSourceDelete()
    
            # Index the new resource if storing to a calendar.
            if self.destinationcal:
                result = self.doDestinationIndex(self.calendar)
                if result is not None:
                    self.rollback.Rollback()
                    returnValue(result)
    
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

            raise err
