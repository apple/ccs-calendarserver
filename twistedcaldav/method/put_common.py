##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##
from twisted.python import failure

"""
PUT/COPY/MOVE common behavior.
"""

__version__ = "0.0"

__all__ = ["storeCalendarObjectResource"]

from twisted.internet.defer import maybeDeferred
from twisted.python import log
from twisted.python.filepath import FilePath
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import PCDATAElement
from twisted.web2.dav.fileop import copy
from twisted.web2.dav.fileop import delete
from twisted.web2.dav.fileop import put
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.util import joinURL, parentForURL
from twisted.web2.iweb import IResponse
from twisted.web2.stream import MemoryStream

from twistedcaldav import logging
from twistedcaldav.caldavxml import NoUIDConflict
from twistedcaldav.caldavxml import NumberOfRecurrencesWithinLimits
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.ical import Component
from twistedcaldav.instance import TooManyInstancesError

def storeCalendarObjectResource(
    request,
    sourcecal, destinationcal,
    source=None, source_uri=None, sourceparent=None,
    destination=None, destination_uri=None, destinationparent=None,
    calendardata=None,
    deletesource=False,
    isiTIP=False
):
    """
    Function that does common PUT/COPY/MOVE behaviour.
    
    @param request:           the L{Request} for the current HTTP request.
    @param source:            the L{CalDAVFile} for the source resource to copy from, or None if source data
                              is to be read from the request.
    @param source_uri:        the URI for the source resource.
    @param destination:       the L{CalDAVFile} for the destination resource to copy into.
    @param destination_uri:   the URI for the destination resource.
    @param calendardata:      the string data read directly from the request body if there is no source, None otherwise.
    @param sourcecal:         True if the source resource is in a calendar collection, False otherwise.
    @param destinationcal:    True if the destination resource is in a calendar collection, False otherwise
    @param sourceparent:      the L{CalDAVFile} for the source resource's parent collection, or None if source is None.
    @param destinationparent: the L{CalDAVFile} for the destination resource's parent collection.
    @param deletesource:      True if the source resource is to be deleted on successful completion, False otherwise.
    @param isiTIP:            True if relaxed calendar data validation is to be done, False otehrwise.
    @return:                  status response.
    """
    
    try:
        assert request is not None and destination is not None and destination_uri is not None and destinationparent is not None
        assert (source is None and sourceparent is None) or (source is not None and sourceparent is not None)
        assert (calendardata is None and source is not None) or (calendardata is not None and source is None)
        assert not deletesource or (deletesource and source is not None)
    except AssertionError:
        log.err("Invalid arguments to storeCalendarObjectResource():")
        log.err("request=%s\n" % (request,))
        log.err("sourcecal=%s\n" % (sourcecal,))
        log.err("destinationcal=%s\n" % (destinationcal,))
        log.err("source=%s\n" % (source,))
        log.err("source_uri=%s\n" % (source_uri,))
        log.err("sourceparent=%s\n" % (sourceparent,))
        log.err("destination=%s\n" % (destination,))
        log.err("destination_uri=%s\n" % (destination_uri,))
        log.err("destinationparent=%s\n" % (destinationparent,))
        log.err("calendardata=%s\n" % (calendardata,))
        log.err("deletesource=%s\n" % (deletesource,))
        log.err("isiTIP=%s\n" % (isiTIP,))
        raise

    class RollbackState(object):
        """
        This class encapsulates the state needed to rollback the entire PUT/COPY/MOVE
        transaction, leaving the server state the same as it was before the request was
        processed. The DoRollback method will actually execute the rollback operations.
        """
        
        def __init__(self):
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
                if logging.canLog("debug"):    
                    logging.debug("Rollback: rollback", system="Store Resource")
                try:
                    if self.source_copy and self.source_deleted:
                        self.source_copy.moveTo(source.fp)
                        logging.debug("Rollback: source restored %s to %s" % (self.source_copy.path, source.fp.path), system="Store Resource")
                        self.source_copy = None
                        self.source_deleted = False
                    if self.destination_copy:
                        destination.fp.remove()
                        logging.debug("Rollback: destination restored %s to %s" % (self.destination_copy.path, destination.fp.path), system="Store Resource")
                        self.destination_copy.moveTo(destination.fp)
                        self.destination_copy = None
                    elif self.destination_created:
                        if destinationcal:
                            doRemoveDestinationIndex()
                            logging.debug("Rollback: destination index removed %s" % (destination.fp.path,), system="Store Resource")
                            self.destination_index_deleted = False
                        destination.fp.remove()
                        logging.debug("Rollback: destination removed %s" % (destination.fp.path,), system="Store Resource")
                        self.destination_created = False
                    if self.destination_index_deleted:
                        # Must read in calendar for destination being re-indexed
                        doDestinationIndex(destination.iCalendar())
                        self.destination_index_deleted = False
                        logging.debug("Rollback: destination re-indexed %s" % (destination.fp.path,), system="Store Resource")
                    if self.source_index_deleted:
                        doSourceIndexRecover()
                        self.destination_index_deleted = False
                        logging.debug("Rollback: soyurce re-indexed %s" % (source.fp.path,), system="Store Resource")
                except:
                    log.err("Rollback: exception caught and not handled: %s" % failure.Failure())

        def Commit(self):
            """
            Commit the resource changes by wiping the rollback state.
            """
            if self.active:
                logging.debug("Rollback: commit", system="Store Resource")
                self.active = False
                if self.source_copy:
                    self.source_copy.remove()
                    logging.debug("Rollback: removed source backup %s" % (self.source_copy.path,), system="Store Resource")
                    self.source_copy = None
                if self.destination_copy:
                    self.destination_copy.remove()
                    logging.debug("Rollback: removed destination backup %s" % (self.destination_copy.path,), system="Store Resource")
                    self.destination_copy = None
                self.destination_created = False
                self.source_deleted = False
                self.source_index_deleted = False
                self.destination_index_deleted = False
    
    rollback = RollbackState()

    def validContentType():
        """
        Make sure that the content-type of the source resource is text/calendar.
        This test is only needed when the source is not in a calendar collection.
        @param request: the L{Request} for the current HTTP request.
        @param source:  the L{Component} for the calendar to test.
        """
        result = True
        message = ""
        content_type = source.contentType()
        if not ((content_type.mediaType == "text") and (content_type.mediaSubtype == "calendar")):
            result = False
            message = "MIME type %s not allowed in calendar collection" % (content_type,)

        return result, message
        
    def validCalendarDataCheck():
        """
        Check that the calendar data is valid iCalendar.
         
        @param request:  the L{Request} for the current HTTP request.
        @param calendar: the L{Component} for the calendar to test.
        @return:         tuple: (True/False if the calendra data is valid,
                                 log message string).
        """
        result = True
        message = ""
        if calendar is None:
            result = False
            message = "Empty resource not allowed in calendar collection"
        else:
            try:
                calendar.validCalendarForCalDAV()
            except ValueError, e:
                result = False
                message = "Invalid calendar data: %s" % (e,)
        
        return result, message
    
    def validCalDAVDataCheck():
        """
        Check that the calendar data is valid as a CalDAV calendar object resource.
         
        @param request:  the L{Request} for the current HTTP request.
        @param calendar: the L{Component} for the calendar to test.
        @return:         tuple: (True/False if the calendar data is valid,
                                 log message string).
        """
        result = True
        message = ""
        try:
            if isiTIP:
                calendar.validateComponentsForCalDAV(True)
            else:
                calendar.validateForCalDAV()
        except ValueError, e:
            result = False
            message = "Calendar data does not conform to CalDAV requirements: %s" % (e,)
        
        return result, message
    
    def noUIDConflict(uid):
        """
        Check that the UID of the new calendar object conforms to the requirements of
        CalDAV, i.e. it must be unique in the collection and we must not overwrite a
        different UID.

        @param request:           the L{Request} for the current HTTP request.
        @param uid:               the UID for the resource being stored.
        @param destination:       the L{CalDAVFile} for the destination resource to copy into.
        @param destinationparent: the L{CalDAVFile} for the destination resource's parent collection.
        @return:                  tuple: (True/False if the uid is valid,
                                          log message string,
                                          name of conflicted resource).
        """

        result = True
        message = ""
        rname = ""

        # Adjust for a move into same calendar collection
        oldname = None
        if sourceparent and (sourceparent.fp.path == destinationparent.fp.path) and deletesource:
            oldname = source.fp.basename()

        # UID must be unqiue
        index = destinationparent.index()
        if not index.isAllowedUID(uid, oldname, destination.fp.basename()):
            rname = index.resourceNameForUID(uid)
            # This can happen if two simulataneous PUTs occur with the same UID.
            # i.e. one PUT has reserved the UID but has not yet written the resource,
            # the other PUT tries to reserve and fails but no index entry exists yets.
            if rname is None:
                rname = "<<Unknown Resource>>"
            
            result = False
            message = "Calendar resource %s already exists with same UID %s" % (rname, uid)
        else:
            # Cannot overwrite different UID
            overwrite = destination.fp.exists()
            if overwrite:
                olduid = index.resourceUIDForName(destination.fp.basename())
                if olduid != uid:
                    rname = destination.fp.basename()
                    result = False
                    message = "Cannot overwrite calendar resource %s with different UID %s" % (rname, olduid)
        
        return result, message, rname


    try:
        """
        Handle validation operations here.
        """

        if destinationcal:
            if not sourcecal:
                # Valid content type check on the source resource if its not in a calendar collection
                if source is not None:
                    result, message = validContentType()
                    if not result:
                        log.err(message)
                        return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data"))
                
                    # At this point we need the calendar data to do more tests
                    calendar = source.iCalendar()
                else:
                    calendar = Component.fromString(calendardata)
                        
                # Valid calendar data check
                result, message = validCalendarDataCheck()
                if not result:
                    log.err(message)
                    return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"))
                    
                # Valid calendar data for CalDAV check
                result, message = validCalDAVDataCheck()
                if not result:
                    log.err(message)
                    return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-object-resource"))

                # Must have a valid UID at this point
                uid = calendar.resourceUID()
            else:
                # Get uid from original resource
                source_index = sourceparent.index()
                uid = source_index.resourceUIDForName(source.fp.basename())
                if uid is None:
                    log.err("Source calendar does not have a UID: %s" % source.fp.basename())
                    return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-object-resource"))

                # FIXME: We need this here because we have to re-index the destination. Ideally it
                # would be better to copy the index entries from the source and add to the destination.
                calendar = source.iCalendar()
                
            # uid conflict check
            if not isiTIP:
                result, message, rname = noUIDConflict(uid)
                if not result:
                    log.err(message)
                    return ErrorResponse(responsecode.FORBIDDEN,
                        NoUIDConflict(davxml.HRef.fromString(joinURL(parentForURL(destination_uri), rname)))
                    )
            
            # Reserve UID
            # FIXME: A race-condition could exist here if a deferred action were to be inserted between this statement
            # and the isAllowedUID statement above. It would probably be best to merge isAllowedUID and reserveUID
            # into a single 'atomic' 'test-and-set' operation to avoid this. Right now just make sure there are no
            # deferreds.
            destination_index = destinationparent.index()
            destination_index.reserveUID(uid)
        
        """
        Handle rollback setup here.
        """

        # We may need to restore the original resource data if the PUT/COPY/MOVE fails,
        # so rename the original file in case we need to rollback.
        overwrite = destination.exists()
        if overwrite:
            rollback.destination_copy = FilePath(destination.fp.path)
            rollback.destination_copy.path += ".rollback"
            destination.fp.copyTo(rollback.destination_copy)
            logging.debug("Rollback: backing up destination %s to %s" % (destination.fp.path, rollback.destination_copy.path), system="Store Resource")
        else:
            rollback.destination_created = True
            logging.debug("Rollback: will create new destination %s" % (destination.fp.path,), system="Store Resource")

        if deletesource:
            rollback.source_copy = FilePath(source.fp.path)
            rollback.source_copy.path += ".rollback"
            source.fp.copyTo(rollback.source_copy)
            logging.debug("Rollback: backing up source %s to %s" % (source.fp.path, rollback.source_copy.path), system="Store Resource")
    
        """
        Handle actual store oeprations here.
        
        The order in which this is done is import:
            
            1. Do store operation for new data
            2. Delete source and source index if needed
            3. Do new indexing if needed
            
        Note that we need to remove the source index BEFORE doing the destination index to cover the
        case of a resource being 'renamed', i.e. moved within the same collection. Since the index UID
        column must be unique in SQL, we cannot add the new index before remove the old one.
        """

        # Do put or copy based on whether source exists
        if source is not None:
            d = maybeDeferred(copy, source.fp, destination.fp, destination_uri, "0")
        else:
            d = maybeDeferred(put, MemoryStream(calendardata), destination.fp)
        
        def doDestinationIndex(caltoindex):
            """
            Do destination resource indexing, replacing any index previous stored.
            
            @return: None if successful, ErrorResponse on failure
            """
            
            # Delete index for original item
            if overwrite:
                doRemoveDestinationIndex()
            
            # Add or update the index for this resource.
            try:
                destination_index.addResource(destination.fp.basename(), caltoindex)
                logging.debug("Destination indexed %s" % (destination.fp.path,), system="Store Resource")
            except TooManyInstancesError, ex:
                log.err("Cannot index calendar resource as there are too many recurrence instances %s" % destination)
                return ErrorResponse(
                    responsecode.FORBIDDEN,
                    NumberOfRecurrencesWithinLimits(PCDATAElement(str(ex.max_allowed)))
                )

            destination.writeProperty(davxml.GETContentType.fromString("text/calendar"), request)
            return None

        def doRemoveDestinationIndex():
            """
            Remove any existing destination index.
            """
            
            # Delete index for original item
            if destinationcal:
                destination_index.deleteResource(destination.fp.basename())
                rollback.destination_index_deleted = True
                logging.debug("Destination index removed %s" % (destination.fp.path,), system="Store Resource")

        def doSourceDelete():
            # Delete index for original item
            if sourcecal:
                source_index.deleteResource(source.fp.basename())
                rollback.source_index_deleted = True
                logging.debug("Source index removed %s" % (source.fp.path,), system="Store Resource")

            # Delete the source resource
            delete(source_uri, source.fp, "0")
            rollback.source_deleted = True
            logging.debug("Source removed %s" % (source.fp.path,), system="Store Resource")
        
        def doSourceIndexRecover():
            """
            Do source resource indexing. This only gets called when restoring
            the source after its index has been deleted.
            
            @return: None if successful, ErrorResponse on failure
            """
            
            # Add or update the index for this resource.
            try:
                source_index.addResource(source.fp.basename(), calendar)
            except TooManyInstancesError, ex:
                return ErrorResponse(
                    responsecode.FORBIDDEN,
                    NumberOfRecurrencesWithinLimits(PCDATAElement(str(ex.max_allowed)))
                )

            source.writeProperty(davxml.GETContentType.fromString("text/calendar"), request)
            return None

        def doIndexing(response):
            """
            Callback after initial store operation succeeds.
            """
            logging.debug("Write to destination completed %r" % response, system="Store Resource")
            response = IResponse(response)
            if response.code in [responsecode.NO_CONTENT, responsecode.CREATED]:
                if deletesource:
                    doSourceDelete()
        
                if destinationcal:
                    result = doDestinationIndex(calendar)
                    if result is not None:
                        rollback.Rollback()
                        return result
    
                # Can now commit changes and forget the rollback details
                rollback.Commit()

            return response

        def cleanUpIndex(f):
            if destinationcal:
                destination_index.unreserveUID(uid)
            
            # Always do the rollback operation: actually this will not
            # rollback if the PUT was successful as the rollback will have
            # been deactivated by a commit.
            rollback.Rollback()

            return f

        d.addCallback(doIndexing)
        d.addBoth(cleanUpIndex)

        return d

    except:
        # Roll back changes to original server state. Note this may do nothing
        # if the rollback has already ocurred or changes already committed.
        rollback.Rollback()
        raise
