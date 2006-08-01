##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
CalDAV PUT method.
"""

__version__ = "0.0"

__all__ = ["http_PUT"]

from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.util import allDataFromStream, parentForURL
from twisted.web2.http import HTTPError

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.resource import isPseudoCalendarCollectionResource

def http_PUT(self, request):
    parent = self.locateParent(request, request.uri)

    if isPseudoCalendarCollectionResource(parent):
        self.fp.restat(False)

        # Content-type check
        content_type = request.headers.getHeader("content-type")
        if content_type is not None and (content_type.mediaType, content_type.mediaSubtype) != ("text", "calendar"):
            log.err("MIME type %s not allowed in calendar collection" % (content_type,))
            return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data"))
            
        # Read the calendar component from the stream
        d = allDataFromStream(request.stream)

        def gotCalendarData(calendardata):

            # We must have some data at this point
            if calendardata is None:
                # Use correct DAV:error response
                return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"))

            return storeCalendarObjectResource(
                request = request,
                sourcecal = False,
                calendardata = calendardata,
                destination = self,
                destination_uri = request.uri,
                destinationcal = True,
                destinationparent = parent,
            )
        
        def gotError(f):
            log.err("Error while handling (calendar) PUT: %s" % (f,))
    
            # ValueError is raised on a bad request.  Re-raise others.
            f.trap(ValueError)
    
            # Use correct DAV:error response
            return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data"))
    
        d.addCallback(gotCalendarData)
        d.addErrback(gotError)

        return d

    else:
        return super(CalDAVFile, self).http_PUT(request)
