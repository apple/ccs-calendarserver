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
CalDAV PUT method.
"""

__all__ = ["http_PUT"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.web2 import responsecode
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.util import allDataFromStream, parentForURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.resource import isPseudoCalendarCollectionResource
from twistedcaldav.log import Logger

log = Logger()

def http_PUT(self, request):

    parentURL = parentForURL(request.uri)
    parent = waitForDeferred(request.locateResource(parentURL))
    yield parent
    parent = parent.getResult()

    if isPseudoCalendarCollectionResource(parent):
        self.fp.restat(False)

        # Content-type check
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
            log.err("MIME type %s not allowed in calendar collection" % (content_type,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
            
        # Read the calendar component from the stream
        try:
            d = waitForDeferred(allDataFromStream(request.stream))
            yield d
            calendardata = d.getResult()

            # We must have some data at this point
            if calendardata is None:
                # Use correct DAV:error response
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))

            d = waitForDeferred(storeCalendarObjectResource(
                request = request,
                sourcecal = False,
                calendardata = calendardata,
                destination = self,
                destination_uri = request.uri,
                destinationcal = True,
                destinationparent = parent,)
            )
            yield d
            yield d.getResult()
            return

        except ValueError, e:
            log.err("Error while handling (calendar) PUT: %s" % (e,))
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    else:
        d = waitForDeferred(super(CalDAVFile, self).http_PUT(request))
        yield d
        yield d.getResult()

http_PUT = deferredGenerator(http_PUT)
