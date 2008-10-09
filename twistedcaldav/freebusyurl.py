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
Free-busy-URL resources.
"""

__all__ = [
    "FreeBusyURLResource",
]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.http import HTTPError
from twisted.web2.http import Response
from twisted.web2.http import StatusResponse
from twisted.web2.http_headers import MimeType
from twisted.web2.stream import MemoryStream

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.ical import Property
from twistedcaldav.ical import parse_datetime
from twistedcaldav.ical import parse_duration
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.scheduling.caldav import ScheduleViaCalDAV
from twistedcaldav.scheduling.cuaddress import LocalCalendarUser
from twistedcaldav.scheduling.scheduler import Scheduler

from vobject.icalendar import utc

import datetime

class FreeBusyURLResource (CalDAVResource):
    """
    Free-busy URL resource.

    Extends L{DAVResource} to provide free-busy URL functionality.
    """

    def __init__(self, parent):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        CalDAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent

    def defaultAccessControlList(self):
        aces = (
            # DAV:Read, CalDAV:schedule for all principals (does not include anonymous)
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                    davxml.Privilege(caldavxml.Schedule()),
                ),
                davxml.Protected(),
            ),
        )
        if config.FreeBusyURL["AnonymousAccess"]:
            aces += (
                # DAV:Read, for unauthenticated principals
                davxml.ACE(
                    davxml.Principal(davxml.Unauthenticated()),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                    ),
                    davxml.Protected(),
                ),
            )
        return davxml.ACL(*aces)

    def resourceType(self):
        return davxml.ResourceType.freebusyurl

    def isCollection(self):
        return False

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return False

    def render(self, request):
        output = """<html>
<head>
<title>Free-Busy URL Resource</title>
</head>
<body>
<h1>Free-busy URL Resource.</h1>
</body
</html>"""

        response = Response(200, {}, output)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response

    def http_GET(self, request):
        """
        The free-busy URL POST method.
        """
        return self._processFBURL(request)

    def http_POST(self, request):
        """
        The free-busy URL POST method.
        """
        return self._processFBURL(request)

    @inlineCallbacks
    def _processFBURL(self, request):
        
        #
        # Check authentication and access controls
        #
        yield self.authorize(request, (davxml.Read(),))
        
        # Extract query parameters from the URL
        args = ('start', 'end', 'duration', 'token', 'format', 'user',)
        for arg in args:
            setattr(self, arg, request.args.get(arg, [None])[0])
        
        # Some things we do not handle
        if self.token or self.user:
            raise HTTPError(ErrorResponse(responsecode.NOT_ACCEPTABLE, (calendarserver_namespace, "supported-query-parameter")))
        
        # Check format
        if self.format:
            self.format = self.format.split(";")[0]
            if self.format not in ("text/calendar", "text/plain"):
                raise HTTPError(ErrorResponse(responsecode.NOT_ACCEPTABLE, (calendarserver_namespace, "supported-format")))
        else:
            self.format = "text/calendar"
            
        # Start/end/duration must be valid iCalendar DATE-TIME UTC or DURATION values
        try:
            if self.start:
                self.start = parse_datetime(self.start)
                if self.start.tzinfo != utc:
                    raise ValueError()
            if self.end:
                self.end = parse_datetime(self.end)
                if self.end.tzinfo != utc:
                    raise ValueError()
            if self.duration:
                self.duration = parse_duration(self.duration)
        except ValueError:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "valid-query-parameters")))
        
        # Sanity check start/end/duration

        # End and duration cannot both be present
        if self.end and self.duration:
            raise HTTPError(ErrorResponse(responsecode.NOT_ACCEPTABLE, (calendarserver_namespace, "valid-query-parameters")))
        
        # Duration must be positive
        if self.duration and self.duration.days < 0:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "valid-query-parameters")))
        
        # Now fill in the missing pieces
        if self.start is None:
            now = datetime.datetime.now()
            self.start = now.replace(hour=0, minute=0, second=0, tzinfo=utc)
        if self.duration:
            self.end = self.start + self.duration
        if self.end is None:
            self.end = self.start + datetime.timedelta(days=config.FreeBusyURL["TimePeriod"])
            
        # End > start
        if self.end <= self.start:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "valid-query-parameters")))
        
        # TODO: We should probably verify that the actual time-range is within sensible bounds (e.g. not too far in the past or future and not too long)
        
        # Now lookup the principal details for the targeted user
        principal = self.parent.principalForRecord()
        
        # Pick the first mailto cu address or the first other type
        cuaddr = None
        for item in principal.calendarUserAddresses():
            if cuaddr is None:
                cuaddr = item
            if item.startswith("mailto"):
                cuaddr = item
                break

        # Get inbox details
        inboxURL = principal.scheduleInboxURL()
        if inboxURL is None:
            raise HTTPError(StatusResponse(responsecode.INTERNAL_SERVER_ERROR, "No schedule inbox URL for principal: %s" % (principal,)))
        try:
            inbox = (yield request.locateResource(inboxURL))
        except:
            log.err("No schedule inbox for principal: %s" % (principal,))
            inbox = None
        if inbox is None:
            raise HTTPError(StatusResponse(responsecode.INTERNAL_SERVER_ERROR, "No schedule inbox for principal: %s" % (principal,)))
            
        scheduler = Scheduler(request, self)
        scheduler.timeRange = TimeRange(start="20000101T000000Z", end="20070102T000000Z")
        scheduler.timeRange.start = self.start
        scheduler.timeRange.end = self.end
        
        scheduler.organizer = LocalCalendarUser(cuaddr, principal, inbox, inboxURL)
        
        attendeeProp = Property("ATTENDEE", scheduler.organizer.cuaddr)

        requestor = ScheduleViaCalDAV(scheduler, (), [], True)
        fbresult = (yield requestor.generateAttendeeFreeBusyResponse(
            scheduler.organizer,
            None,
            None,
            attendeeProp,
            True,
        ))
        
        response = Response()
        response.stream = MemoryStream(str(fbresult))
        response.headers.setHeader("content-type", MimeType.fromString("%s; charset=utf-8" % (self.format,)))
    
        returnValue(response)
