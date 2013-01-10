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
CalDAV PUT method.
"""

__all__ = ["http_PUT"]

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.web2 import responsecode
from twext.web2.dav.util import allDataFromStream, parentForURL
from twext.web2.http import HTTPError, StatusResponse

from twext.python.log import Logger
from twext.web2.dav.http import ErrorResponse

from twistedcaldav.caldavxml import caldav_namespace

from twistedcaldav.method.put_common import StoreCalendarObjectResource
from twistedcaldav.resource import isPseudoCalendarCollectionResource,\
    CalDAVResource

log = Logger()

from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.method.put_addressbook_common import StoreAddressObjectResource
from twistedcaldav.resource import isAddressBookCollectionResource

@inlineCallbacks
def http_PUT(self, request):

    parentURL = parentForURL(request.uri)
    parent = (yield request.locateResource(parentURL))

    if isPseudoCalendarCollectionResource(parent):

        # Content-type check
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
            log.err("MIME type %s not allowed in calendar collection" % (content_type,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "supported-calendar-data"),
                "Invalid MIME type for calendar collection",
            ))
            
        # Read the calendar component from the stream
        try:
            calendardata = (yield allDataFromStream(request.stream))
            if not hasattr(request, "extendedLogItems"):
                request.extendedLogItems = {}
            request.extendedLogItems["cl"] = str(len(calendardata)) if calendardata else "0"

            # We must have some data at this point
            if calendardata is None:
                # Use correct DAV:error response
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldav_namespace, "valid-calendar-data"),
                    description="No calendar data"
                ))

            storer = StoreCalendarObjectResource(
                request = request,
                destination = self,
                destination_uri = request.uri,
                destinationcal = True,
                destinationparent = parent,
                calendar = calendardata,
            )
            result = (yield storer.run())

            # Look for Prefer header
            prefer = request.headers.getHeader("prefer", {})
            returnRepresentation = "return-representation" in prefer

            if returnRepresentation and result.code / 100 == 2:
                oldcode = result.code
                result = (yield self.http_GET(request))
                if oldcode == responsecode.CREATED:
                    result.code =  responsecode.CREATED
                result.headers.setHeader("content-location", request.path)

            returnValue(result)

        except ValueError, e:
            log.err("Error while handling (calendar) PUT: %s" % (e,))
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    elif isAddressBookCollectionResource(parent):

        # Content-type check
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "vcard"):
            log.err("MIME type %s not allowed in address book collection" % (content_type,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (carddav_namespace, "supported-address-data"),
                "Invalid MIME type for address book collection",
            ))
            
        # Read the vcard component from the stream
        try:
            vcarddata = (yield allDataFromStream(request.stream))
            if not hasattr(request, "extendedLogItems"):
                request.extendedLogItems = {}
            request.extendedLogItems["cl"] = str(len(vcarddata)) if vcarddata else "0"

            # We must have some data at this point
            if vcarddata is None:
                # Use correct DAV:error response
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (carddav_namespace, "valid-address-data"),
                    description="No vcard data"
                ))

            storer = StoreAddressObjectResource(
                request = request,
                sourceadbk = False,
                vcard = vcarddata,
                destination = self,
                destination_uri = request.uri,
                destinationadbk = True,
                destinationparent = parent,
            )
            result = (yield storer.run())

            # Look for Prefer header
            prefer = request.headers.getHeader("prefer", {})
            returnRepresentation = "return-representation" in prefer

            if returnRepresentation and result.code / 100 == 2:
                oldcode = result.code
                result = (yield self.http_GET(request))
                if oldcode == responsecode.CREATED:
                    result.code =  responsecode.CREATED
                result.headers.setHeader("content-location", request.path)

            returnValue(result)

        except ValueError, e:
            log.err("Error while handling (address book) PUT: %s" % (e,))
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    else:
        result = (yield super(CalDAVResource, self).http_PUT(request))

        if not hasattr(request, "extendedLogItems"):
            request.extendedLogItems = {}
        clength = request.headers.getHeader("content-length", 0)
        if clength == 0:
            clength = self.contentLength()
        request.extendedLogItems["cl"] = str(clength)
        
        returnValue(result)
