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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
CalDAV MKCALENDAR method.
"""

__version__ = "0.0"

__all__ = ["http_MKCALENDAR"]

import os

from twisted.internet.defer import maybeDeferred
from twisted.python import log
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse, MultiStatusResponse, PropertyStatusResponseQueue
from twisted.web2.dav.util import davXMLFromStream
from twisted.web2.http import HTTPError, StatusResponse
from twisted.web2.iweb import IResponse

from twistedcaldav import caldavxml

def http_MKCALENDAR(self, request):
    """
    Respond to a MKCALENDAR request.
    (CalDAV-access-09, section 5.3.1)
    """
    self.fp.restat(False)

    if self.exists():
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (davxml.dav_namespace, "resource-must-be-null")
        )

    if not os.path.isdir(self.fp.dirname()):
        return ErrorResponse(
            responsecode.CONFLICT,
            (caldavxml.caldav_namespace, "calendar-collection-location-ok")
        )

    #
    # Check authentication and access controls
    #
    parent = self.locateParent(request, request.uri)
    parent.securityCheck(request, (davxml.Bind(),))

    #
    # Read request body
    #
    d = davXMLFromStream(request.stream)

    def gotError(f):
        log.err("Error while handling MKCALENDAR: %s" % (f,))

        # Clean up
        if self.fp.exists(): self.fp.remove()

        if f.check(ValueError):
            return StatusResponse(responsecode.BAD_REQUEST, str(f))
        elif f.check(HTTPError):
            return f.value.response
        else:
            return f

    def gotXML(doc):
        # FIXME: if we get any errors, we need to delete the calendar

        d = maybeDeferred(self.createCalendar, request)

        if doc:
            makecalendar = doc.root_element
            if not isinstance(makecalendar, caldavxml.MakeCalendar):
                error = ("Non-%s element in MKCALENDAR request body: %s"
                         % (caldavxml.MakeCalendar.name, makecalendar))
                log.err(error)
                raise HTTPError(StatusResponse(responsecode.UNSUPPORTED_MEDIA_TYPE, error))

            def finish(response):
                errors = PropertyStatusResponseQueue("PROPPATCH", request.uri, responsecode.NO_CONTENT)
                got_an_error = False

                if makecalendar.children:
                    # mkcalendar -> set -> prop -> property*
                    for property in makecalendar.children[0].children[0].children:
                        try:
                            if property.qname() == (caldavxml.caldav_namespace, "supported-calendar-component-set"):
                                self.writeDeadProperty(property)
                            else:
                                self.writeProperty(property, request)
                        except:
                            errors.add(Failure(), property)
                            got_an_error = True
                        else:
                            errors.add(responsecode.OK, property)

                if got_an_error:
                    errors.error()
                    raise HTTPError(MultiStatusResponse([errors.response()]))
                else:
                    response = IResponse(response)
                    response.headers.setHeader("cache-control", { "no-cache": None })
                    return response

            d.addCallback(finish)
            d.addErrback(gotError)

        return d

    d.addCallback(gotXML)
    d.addErrback(gotError)

    return d
