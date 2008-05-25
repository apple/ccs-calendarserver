##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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
from twistedcaldav.ical import tzexpand

"""
Timezone service resource and operations.
"""

__all__ = [
    "TimezoneServiceResource",
]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.http import HTTPError
from twisted.web2.http import Response
from twisted.web2.http_headers import MimeType
from twisted.web2.stream import MemoryStream

from twistedcaldav import customxml
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.extensions import XMLResponse
from twistedcaldav.ical import parse_date_or_datetime
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.timezones import TimezoneException
from twistedcaldav.timezones import listTZs
from twistedcaldav.timezones import readTZ

class TimezoneServiceResource (CalDAVResource):
    """
    Timezone Service resource.

    Extends L{DAVResource} to provide timezone service functionality.
    """

    def __init__(self, parent):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        CalDAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent
        self.cache = {}

    def defaultAccessControlList(self):
        return davxml.ACL(
            # DAV:Read for all principals (includes anonymous)
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                ),
                davxml.Protected(),
            ),
        )

    def resourceType(self):
        return davxml.ResourceType.timezones

    def isCollection(self):
        return False

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return False

    def render(self, request):
        output = """<html>
<head>
<title>Timezone Service Resource</title>
</head>
<body>
<h1>Timezone Service Resource.</h1>
</body
</html>"""

        response = Response(200, {}, output)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response

    def http_GET(self, request):
        """
        The timezone service POST method.
        """
        
        # GET and POST do the same thing
        return self.http_POST(request)

    @inlineCallbacks
    def http_POST(self, request):
        """
        The timezone service POST method.
        """

        # Check authentication and access controls
        yield self.authorize(request, (davxml.Read(),))
        
        if not request.args:
            # Do normal GET behavior
            response = yield self.render(request)
            returnValue(response)

        method = request.args.get("method", ("",))
        if len(method) != 1:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "valid-method")))
        method = method[0]
            
        action = {
            "list"   : self.doPOSTList,
            "get"    : self.doPOSTGet,
            "expand" : self.doPOSTExpand,
        }.get(method, None)
        
        if action is None:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "supported-method")))

        returnValue(action(request))

    def doPOSTList(self, request):
        """
        Return a list of all timezones known to the server.
        """
        
        tzids = listTZs()
        tzids.sort()
        result = customxml.TZIDs(*[customxml.TZID(tzid) for tzid in tzids])
        return XMLResponse(responsecode.OK, result)

    def doPOSTGet(self, request):
        """
        Return the specified timezone data.
        """
        
        tzid = request.args.get("tzid", ())
        if len(tzid) != 1:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "valid-timezone")))
        tzid = tzid[0]

        try:
            tzdata = readTZ(tzid)
        except TimezoneException:
            raise HTTPError(ErrorResponse(responsecode.NOT_FOUND, (calendarserver_namespace, "timezone-available")))

        response = Response()
        response.stream = MemoryStream(tzdata)
        response.headers.setHeader("content-type", MimeType.fromString("text/calendar; charset=utf-8"))
        return response

    def doPOSTExpand(self, request):
        """
        Expand a timezone within specified start/end dates.
        """

        tzid = request.args.get("tzid", ())
        if len(tzid) != 1:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "valid-timezone")))
        tzid = tzid[0]
        try:
            tzdata = readTZ(tzid)
        except TimezoneException:
            raise HTTPError(ErrorResponse(responsecode.NOT_FOUND, (calendarserver_namespace, "timezone-available")))

        try:
            start = request.args.get("start", ())
            if len(start) != 1:
                raise ValueError()
            start = parse_date_or_datetime(start[0])
        except ValueError:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "valid-start-date")))

        try:
            end = request.args.get("end", ())
            if len(end) != 1:
                raise ValueError()
            end = parse_date_or_datetime(end[0])
            if end <= start:
                raise ValueError()
        except ValueError:
            raise HTTPError(ErrorResponse(responsecode.BAD_REQUEST, (calendarserver_namespace, "valid-end-date")))

        # Now do the expansion (but use a cache to avoid re-calculating TZs)
        observances = self.cache.get((tzid, start, end), None)
        if observances is None:
            observances = tzexpand(tzdata, start, end)
            self.cache[(tzid, start, end)] = observances

        # Turn into XML
        result = customxml.TZData(
            *[customxml.Observance(customxml.Onset(onset), customxml.UTCOffset(utc_offset)) for onset, utc_offset in observances]
        )
        return XMLResponse(responsecode.OK, result)
