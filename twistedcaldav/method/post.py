# #
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
# #

from hashlib import md5

from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.util import allDataFromStream, joinURL
from twext.web2.filter.location import addLocation
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.method.put_addressbook_common import StoreAddressObjectResource
from twistedcaldav.method.put_common import StoreCalendarObjectResource

import time

"""
CalDAV POST method.
"""

__all__ = ["http_POST"]

from twisted.internet.defer import inlineCallbacks, returnValue

from twext.web2 import responsecode

from twistedcaldav.config import config

@inlineCallbacks
def http_POST(self, request):

    # POST can support many different APIs

    # First look at query params
    if request.params:
        if request.params == "add-member":
            if config.EnableAddMember:
                result = (yield POST_handler_add_member(self, request))
                returnValue(result)

    # Look for query arguments
    if request.args:
        action = request.args.get("action", ("",))
        if len(action) == 1:
            action = action[0]
            if action in ("attachment-add", "attachment-update", "attachment-remove") and \
                hasattr(self, "POST_handler_attachment"):
                if config.EnableManagedAttachments:
                    result = (yield self.POST_handler_attachment(request, action))
                    returnValue(result)
                else:
                    returnValue(StatusResponse(responsecode.FORBIDDEN, "Managed Attachments not supported."))

    # Content-type handlers
    contentType = request.headers.getHeader("content-type")
    if contentType:
        if hasattr(self, "POST_handler_content_type"):
            result = (yield self.POST_handler_content_type(request, (contentType.mediaType, contentType.mediaSubtype)))
            returnValue(result)

    returnValue(responsecode.FORBIDDEN)



@inlineCallbacks
def POST_handler_add_member(self, request):

    # Handle ;add-member
    if self.isCalendarCollection():

        parentURL = request.path
        parent = self

        # Content-type check
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
            self.log_error("MIME type %s not allowed in calendar collection" % (content_type,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "supported-calendar-data"),
                "Wrong MIME type for calendar collection",
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

            # Create a new name if one was not provided
            name = md5(str(calendardata) + str(time.time()) + request.path).hexdigest() + ".ics"

            # Get a resource for the new item
            newchildURL = joinURL(parentURL, name)
            newchild = (yield request.locateResource(newchildURL))

            storer = StoreCalendarObjectResource(
                request=request,
                destination=newchild,
                destination_uri=newchildURL,
                destinationcal=True,
                destinationparent=parent,
                calendar=calendardata,
            )
            result = (yield storer.run())

            # May need to add a location header
            addLocation(request, request.unparseURL(path=newchildURL, params=""))

            # Look for Prefer header
            prefer = request.headers.getHeader("prefer", {})
            returnRepresentation = "return-representation" in prefer

            if returnRepresentation and result.code / 100 == 2:
                result = (yield newchild.http_GET(request))
                result.code = responsecode.CREATED
                result.headers.removeHeader("content-location")
                result.headers.setHeader("content-location", newchildURL)

            returnValue(result)

        except ValueError, e:
            self.log_error("Error while handling (calendar) POST: %s" % (e,))
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    elif self.isAddressBookCollection():

        parentURL = request.path
        parent = self

        # Content-type check
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "vcard"):
            self.log_error("MIME type %s not allowed in address book collection" % (content_type,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (carddav_namespace, "supported-address-data"),
                "Wrong MIME type for address book collection",
            ))

        # Read the calendar component from the stream
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
                    description="No address data"
                ))

            # Create a new name if one was not provided
            name = md5(str(vcarddata) + str(time.time()) + request.path).hexdigest() + ".vcf"

            # Get a resource for the new item
            newchildURL = joinURL(parentURL, name)
            newchild = (yield request.locateResource(newchildURL))

            storer = StoreAddressObjectResource(
                request=request,
                sourceadbk=False,
                destination=newchild,
                destination_uri=newchildURL,
                destinationadbk=True,
                destinationparent=parent,
                vcard=vcarddata,
            )
            result = (yield storer.run())

            # May need to add a location header
            addLocation(request, request.unparseURL(path=newchildURL, params=""))

            # Look for Prefer header
            prefer = request.headers.getHeader("prefer", {})
            returnRepresentation = "return-representation" in prefer

            if returnRepresentation and result.code / 100 == 2:
                result = (yield newchild.http_GET(request))
                result.code = responsecode.CREATED
                result.headers.removeHeader("content-location")
                result.headers.setHeader("content-location", newchildURL)

            returnValue(result)

        except ValueError, e:
            self.log_error("Error while handling (calendar) POST: %s" % (e,))
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    # Default behavior
    returnValue(responsecode.FORBIDDEN)
