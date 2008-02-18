##
# Copyright (c) 2005-2008 Apple Inc. All rights reserved.
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
CalDAV GET method.
"""

__all__ = ["http_GET"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.web2.dav import davxml
from twisted.web2.http import HTTPError
from twisted.web2.http import Response
from twisted.web2.http_headers import MimeType
from twisted.web2.stream import MemoryStream

from twistedcaldav import caldavxml
from twistedcaldav.customxml import TwistedCalendarAccessProperty
from twistedcaldav.ical import Component

def http_GET(self, request):

    # Look for calendar access restriction on existing resource.
    if self.exists():
        try:
            access = self.readDeadProperty(TwistedCalendarAccessProperty)
        except HTTPError:
            access = None
            
        if access in (Component.ACCESS_CONFIDENTIAL, Component.ACCESS_RESTRICTED):
    
            # Check authorization first
            d = waitForDeferred(self.authorize(request, (davxml.Read(),)))
            yield d
            d.getResult()

            # Non DAV:owner's have limited access to the data
            d = waitForDeferred(self.isOwner(request))
            yield d
            isowner = d.getResult()
            
            if not isowner:

                # Now "filter" the resource calendar data through the CALDAV:calendar-data element and apply
                # access restrictions to the data.
                caldata = caldavxml.CalendarData().elementFromResourceWithAccessRestrictions(self, access).calendarData()

                response = Response()
                response.stream = MemoryStream(caldata)
                response.headers.setHeader("content-type", MimeType.fromString("text/calendar; charset=utf-8"))
                yield response
                return

    # Do normal GET behavior
    d = waitForDeferred(super(CalDAVFile, self).http_GET(request))
    yield d
    yield d.getResult()

http_GET = deferredGenerator(http_GET)
