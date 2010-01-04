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
from hashlib import md5
from twisted.web2.filter.location import addLocation
import time

"""
CalDAV POST method.
"""

__all__ = ["http_POST"]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twext.web2.dav.davxml import ErrorResponse
from twisted.web2.dav.util import allDataFromStream, joinURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.method.put_common import StoreCalendarObjectResource
from twistedcaldav.log import Logger

log = Logger()

@inlineCallbacks
def http_POST(self, request):

    # POST can support many different APIs
    
    # Handle ;add-member
    if request.params and request.params == "add-member" and self.isCalendarCollection():
        
        parentURL = request.path
        parent = self

        # Content-type check
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
            log.err("MIME type %s not allowed in calendar collection" % (content_type,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
            
        # Read the calendar component from the stream
        try:
            calendardata = (yield allDataFromStream(request.stream))
            if not hasattr(request, "extendedLogItems"):
                request.extendedLogItems = {}
            request.extendedLogItems["cl"] = str(len(calendardata)) if calendardata else "0"

            # We must have some data at this point
            if calendardata is None:
                # Use correct DAV:error response
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"), description="No calendar data"))

            # Create a new name if one was not provided
            name =  md5(str(calendardata) + str(time.time()) + self.fp.path).hexdigest() + ".ics"
        
            # Get a resource for the new item
            newchildURL = joinURL(parentURL, name)
            newchild = (yield request.locateResource(newchildURL))

            storer = StoreCalendarObjectResource(
                request = request,
                destination = newchild,
                destination_uri = newchildURL,
                destinationcal = True,
                destinationparent = parent,
                calendar = calendardata,
            )
            result = (yield storer.run())

            # May need to add a location header
            addLocation(request, request.unparseURL(path=newchildURL, params=""))

            returnValue(result)

        except ValueError, e:
            log.err("Error while handling (calendar) PUT: %s" % (e,))
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    # Default behavior
    returnValue(responsecode.NOT_ALLOWED)
