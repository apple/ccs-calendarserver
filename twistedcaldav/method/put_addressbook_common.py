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

"""
PUT/COPY/MOVE common behavior.
"""

__all__ = ["StoreAddressObjectResource"]

import types

from twisted.internet import reactor

from txdav.common.icommondatastore import ReservationError

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.defer import returnValue
from twext.web2 import responsecode
from txdav.xml import element as davxml
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.util import joinURL, parentForURL
from twext.web2.http import HTTPError
from twext.web2.http import StatusResponse
from twext.web2.stream import MemoryStream

from twistedcaldav.config import config
from twistedcaldav.carddavxml import NoUIDConflict, carddav_namespace
from twistedcaldav import customxml
from twistedcaldav.vcard import Component
from twext.python.log import Logger

log = Logger()

class StoreAddressObjectResource(object):

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
                reactor.callLater(0.5, _timedDeferred) #@UndefinedVariable
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
        source=None, source_uri=None, sourceparent=None, sourceadbk=False, deletesource=False,
        destination=None, destination_uri=None, destinationparent=None, destinationadbk=True,
        vcard=None,
        indexdestination=True,
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
        @param vcard:             the C{str} or L{Component} vcard data if there is no source, None otherwise.
        @param sourceadbk:        True if the source resource is in a vcard collection, False otherwise.
        @param destinationadbk:   True if the destination resource is in a vcard collection, False otherwise
        @param sourceparent:      the L{CalDAVResource} for the source resource's parent collection, or None if source is None.
        @param destinationparent: the L{CalDAVResource} for the destination resource's parent collection.
        @param deletesource:      True if the source resource is to be deleted on successful completion, False otherwise.
        @param returnData:         True if the caller wants the actual data written to the store returned
        """

        # Check that all arguments are valid
        try:
            assert destination is not None and destinationparent is not None and destination_uri is not None
            assert (source is None and sourceparent is None) or (source is not None and sourceparent is not None)
            assert (vcard is None and source is not None) or (vcard is not None and source is None)
            assert not deletesource or (deletesource and source is not None)
        except AssertionError:
            log.err("Invalid arguments to StoreAddressObjectResource.__init__():")
            log.err("request=%s\n" % (request,))
            log.err("sourceadbk=%s\n" % (sourceadbk,))
            log.err("destinationadbk=%s\n" % (destinationadbk,))
            log.err("source=%s\n" % (source,))
            log.err("source_uri=%s\n" % (source_uri,))
            log.err("sourceparent=%s\n" % (sourceparent,))
            log.err("destination=%s\n" % (destination,))
            log.err("destination_uri=%s\n" % (destination_uri,))
            log.err("destinationparent=%s\n" % (destinationparent,))
            log.err("vcard=%s\n" % (vcard,))
            log.err("deletesource=%s\n" % (deletesource,))
            raise

        self.request = request
        self.sourceadbk = sourceadbk
        self.destinationadbk = destinationadbk
        self.source = source
        self.source_uri = source_uri
        self.sourceparent = sourceparent
        self.destination = destination
        self.destination_uri = destination_uri
        self.destinationparent = destinationparent
        self.vcard = vcard
        self.vcarddata = None
        self.deletesource = deletesource
        self.indexdestination = indexdestination
        self.returnData = returnData

        self.access = None


    @inlineCallbacks
    def fullValidation(self):
        """
        Do full validation of source and destination vcard data.
        """

        if self.destinationadbk:
            # Valid resource name check
            result, message = self.validResourceName()
            if not result:
                log.err(message)
                raise HTTPError(StatusResponse(responsecode.FORBIDDEN, message))

            # Valid collection size check on the destination parent resource
            result, message = (yield self.validCollectionSize())
            if not result:
                log.err(message)
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    customxml.MaxResources(),
                    message,
                ))

            if not self.sourceadbk:
                # Valid content type check on the source resource if its not in a vcard collection
                if self.source is not None:
                    result, message = self.validContentType()
                    if not result:
                        log.err(message)
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (carddav_namespace, "supported-address-data"),
                            message,
                        ))

                    # At this point we need the calendar data to do more tests
                    self.vcard = (yield self.source.vCard())
                else:
                    try:
                        if type(self.vcard) in (types.StringType, types.UnicodeType,):
                            self.vcard = Component.fromString(self.vcard)
                    except ValueError, e:
                        log.err(str(e))
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (carddav_namespace, "valid-address-data"),
                            "Could not parse vCard",
                        ))

                # Valid vcard data check
                result, message = self.validAddressDataCheck()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (carddav_namespace, "valid-address-data"),
                        message
                    ))

                # Valid vcard data for CalDAV check
                result, message = self.validCardDAVDataCheck()
                if not result:
                    log.err(message)
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (carddav_namespace, "valid-addressbook-object-resource"),
                        message,
                    ))

                # Must have a valid UID at this point
                self.uid = self.vcard.resourceUID()
            else:
                # Get UID from original resource
                self.source_index = self.sourceparent.index()
                self.uid = yield self.source_index.resourceUIDForName(self.source.name())
                if self.uid is None:
                    log.err("Source vcard does not have a UID: %s" % self.source.name())
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (carddav_namespace, "valid-addressbook-object-resource"),
                        "Missing UID in vCard",
                    ))

                # FIXME: We need this here because we have to re-index the destination. Ideally it
                # would be better to copy the index entries from the source and add to the destination.
                self.vcard = (yield self.source.vCard())

            # Valid vcard data size check
            result, message = self.validSizeCheck()
            if not result:
                log.err(message)
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (carddav_namespace, "max-resource-size"),
                    message,
                ))

            # Check access
            returnValue(None)


    def validResourceName(self):
        """
        Make sure that the resource name for the new resource is valid.
        """
        result = True
        message = ""
        filename = self.destination.name()
        if filename.startswith("."):
            result = False
            message = "Resource name %s not allowed in vcard collection" % (filename,)

        return result, message


    def validContentType(self):
        """
        Make sure that the content-type of the source resource is text/vcard.
        This test is only needed when the source is not in a vcard collection.
        """
        result = True
        message = ""
        content_type = self.source.contentType()
        if not ((content_type.mediaType == "text") and (content_type.mediaSubtype == "vcard")):
            result = False
            message = "MIME type %s not allowed in vcard collection" % (content_type,)

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


    def validAddressDataCheck(self):
        """
        Check that the calendar data is valid iCalendar.
        @return:         tuple: (True/False if the calendar data is valid,
                                 log message string).
        """
        result = True
        message = ""
        if self.vcard is None:
            result = False
            message = "Empty resource not allowed in vcard collection"
        else:
            try:
                self.vcard.validVCardData()
            except ValueError, e:
                result = False
                message = "Invalid vcard data: %s" % (e,)

        return result, message


    def validCardDAVDataCheck(self):
        """
        Check that the vcard data is valid vCard.
        @return:         tuple: (True/False if the vcard data is valid,
                                 log message string).
        """
        result = True
        message = ""
        try:
            self.vcard.validForCardDAV()
        except ValueError, e:
            result = False
            message = "vCard data does not conform to CardDAV requirements: %s" % (e,)

        return result, message


    def validSizeCheck(self):
        """
        Make sure that the content-type of the source resource is text/vcard.
        This test is only needed when the source is not in a vcard collection.
        """
        result = True
        message = ""
        if config.MaxResourceSize:
            vcardsize = len(str(self.vcard))
            if vcardsize > config.MaxResourceSize:
                result = False
                message = "Data size %d bytes is larger than allowed limit %d bytes" % (vcardsize, config.MaxResourceSize)

        return result, message


    @inlineCallbacks
    def noUIDConflict(self, uid):
        """
        Check that the UID of the new vcard object conforms to the requirements of
        CardDAV, i.e. it must be unique in the collection and we must not overwrite a
        different UID.
        @param uid: the UID for the resource being stored.
        @return: tuple: (True/False if the UID is valid, log message string,
            name of conflicted resource).
        """

        result = True
        message = ""
        rname = ""

        # Adjust for a move into same vcard collection
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
            message = "Address book resource %s already exists with same UID %s" % (rname, uid)
        else:
            # Cannot overwrite a resource with different UID
            if self.destination.exists():
                olduid = yield index.resourceUIDForName(self.destination.name())
                if olduid != uid:
                    rname = self.destination.name()
                    result = False
                    message = "Cannot overwrite vcard resource %s with different UID %s" % (rname, olduid)

        returnValue((result, message, rname))


    @inlineCallbacks
    def doStore(self):
        # Do put or copy based on whether source exists
        source = self.source
        if source is not None:
            # Retrieve information from the source, in case we have to delete
            # it.
            sourceProperties = dict(source.newStoreProperties().iteritems())
            sourceText = yield source.vCardText()

            # Delete the original source if needed (for example, if this is a
            # same-calendar MOVE of a calendar object, implemented as an
            # effective DELETE-then-PUT).
            if self.deletesource:
                yield self.doSourceDelete()

            response = (yield self.destination.storeStream(MemoryStream(sourceText)))
            self.destination.newStoreProperties().update(sourceProperties)
        else:
            response = (yield self.doStorePut())

        returnValue(response)


    @inlineCallbacks
    def doStorePut(self):

        stream = MemoryStream(str(self.vcard))
        response = (yield self.destination.storeStream(stream))
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
            if self.destinationadbk:
                # Reserve UID
                self.destination_index = self.destinationparent.index()
                reservation = StoreAddressObjectResource.UIDReservation(
                    self.destination_index, self.uid, self.destination_uri
                )
                if self.indexdestination:
                    yield reservation.reserve()

                # UID conflict check - note we do this after reserving the UID to avoid a race condition where two requests
                # try to write the same vcard data to two different resource URIs.
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
                        "UID already used in another resource",
                    ))

            # Do the actual put or copy
            response = (yield self.doStore())

            if reservation:
                yield reservation.unreserve()

            returnValue(response)

        except Exception, err:

            if reservation:
                yield reservation.unreserve()

            raise err


    @inlineCallbacks
    def moveValidation(self):
        """
        Do full validation of source and destination calendar data.
        """

        # Valid resource name check
        result, message = self.validResourceName()
        if not result:
            log.err(message)
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, message))

        # Valid collection size check on the destination parent resource
        result, message = (yield self.validCollectionSize())
        if not result:
            log.err(message)
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                customxml.MaxResources(),
                message,
            ))

        returnValue(None)


    @inlineCallbacks
    def doStoreMove(self):

        # Do move
        response = (yield self.source.storeMove(self.request, self.destinationparent, self.destination._name))
        returnValue(response)


    @inlineCallbacks
    def move(self):
        """
        Function that does common MOVE behavior.

        @return: a Deferred with a status response result.
        """

        try:
            reservation = None

            # Handle all validation operations here.
            yield self.moveValidation()

            # Reservation and UID conflict checking is next.

            # Reserve UID
            self.destination_index = self.destinationparent.index()
            reservation = StoreAddressObjectResource.UIDReservation(
                self.destination_index, self.source.uid(), self.destination_uri
            )
            if self.indexdestination:
                yield reservation.reserve()

            # UID conflict check - note we do this after reserving the UID to avoid a race condition where two requests
            # try to write the same vcard data to two different resource URIs.
            result, message, rname = yield self.noUIDConflict(self.source.uid())
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
                    "UID already used in another resource",
                ))

            # Do the actual put or copy
            response = (yield self.doStoreMove())

            if reservation:
                yield reservation.unreserve()

            returnValue(response)

        except Exception, err:

            if reservation:
                yield reservation.unreserve()

            raise err
