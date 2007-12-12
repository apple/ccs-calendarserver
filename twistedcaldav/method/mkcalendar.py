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
CalDAV MKCALENDAR method.
"""

__all__ = ["http_MKCALENDAR"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.python import log
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse, MultiStatusResponse, PropertyStatusResponseQueue
from twisted.web2.dav.util import davXMLFromStream
from twisted.web2.dav.util import parentForURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav import caldavxml

def http_MKCALENDAR(self, request):
    """
    Respond to a MKCALENDAR request.
    (CalDAV-access-09, section 5.3.1)
    """

    #
    # Check authentication and access controls
    #
    parent = waitForDeferred(request.locateResource(parentForURL(request.uri)))
    yield parent
    parent = parent.getResult()

    x = waitForDeferred(parent.authorize(request, (davxml.Bind(),)))
    yield x
    x.getResult()

    if self.exists():
        log.err("Attempt to create collection where file exists: %s"
                % (self.fp.path,))
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            (davxml.dav_namespace, "resource-must-be-null"))
        )

    if not parent.isCollection():
        log.err("Attempt to create collection with non-collection parent: %s"
                % (self.fp.path,))
        raise HTTPError(ErrorResponse(
            responsecode.CONFLICT,
            (caldavxml.caldav_namespace, "calendar-collection-location-ok"))
        )

    #
    # Read request body
    #
    try:
        doc = waitForDeferred(davXMLFromStream(request.stream))
        yield doc
        doc = doc.getResult()

        result = waitForDeferred(self.createCalendar(request))
        yield result
        result = result.getResult()
    except ValueError, e:
        log.err("Error while handling MKCALENDAR: %s" % (e,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    if doc is not None:
        makecalendar = doc.root_element
        if not isinstance(makecalendar, caldavxml.MakeCalendar):
            # Clean up
            if self.fp.exists(): self.fp.remove()

            error = ("Non-%s element in MKCALENDAR request body: %s"
                     % (caldavxml.MakeCalendar.name, makecalendar))
            log.err(error)
            raise HTTPError(StatusResponse(responsecode.UNSUPPORTED_MEDIA_TYPE, error))

        errors = PropertyStatusResponseQueue("PROPPATCH", request.uri, responsecode.NO_CONTENT)
        got_an_error = False
    
        if makecalendar.children:
            # mkcalendar -> set -> prop -> property*
            for property in makecalendar.children[0].children[0].children:
                try:
                    if property.qname() == (caldavxml.caldav_namespace, "supported-calendar-component-set"):
                        self.writeDeadProperty(property)
                    else:
                        p = waitForDeferred(self.writeProperty(property, request))
                        yield p
                        p.getResult()
                except HTTPError:
                    errors.add(Failure(), property)
                    got_an_error = True
                else:
                    errors.add(responsecode.OK, property)
    
        if got_an_error:
            # Clean up
            if self.fp.exists(): self.fp.remove()

            errors.error()
            raise HTTPError(MultiStatusResponse([errors.response()]))

    yield responsecode.CREATED

http_MKCALENDAR = deferredGenerator(http_MKCALENDAR)
