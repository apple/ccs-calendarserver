##
# Copyright (c) 2008-2015 Apple Inc. All rights reserved.
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
Timezone service resource and operations.
"""

__all__ = [
    "TimezoneServiceResource",
]

from txweb2.dav.http import ErrorResponse

from txweb2 import responsecode
from txdav.xml import element as davxml
from txweb2.dav.method.propfind import http_PROPFIND
from txweb2.dav.noneprops import NonePropertyStore
from txweb2.http import HTTPError
from txweb2.http import Response
from txweb2.http import XMLResponse
from txweb2.http_headers import MimeType
from txweb2.stream import MemoryStream

from twisted.internet.defer import succeed

from twistedcaldav import customxml
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.extensions import DAVResource,\
    DAVResourceWithoutChildrenMixin
from twistedcaldav.ical import tzexpand
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn
from twistedcaldav.timezones import TimezoneException
from twistedcaldav.timezones import listTZs
from twistedcaldav.timezones import readTZ

from pycalendar.datetime import DateTime

class TimezoneServiceResource (ReadOnlyNoCopyResourceMixIn, DAVResourceWithoutChildrenMixin, DAVResource):
    """
    Timezone Service resource.

    Extends L{DAVResource} to provide timezone service functionality.
    """

    def __init__(self, parent):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        DAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent
        self.cache = {}


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def etag(self):
        return succeed(None)


    def checkPreconditions(self, request):
        return None


    def checkPrivileges(self, request, privileges, recurse=False, principal=None, inherited_aces=None):
        return succeed(None)


    def defaultAccessControlList(self):
        return succeed(
            davxml.ACL(
                # DAV:Read for all principals (includes anonymous)
                davxml.ACE(
                    davxml.Principal(davxml.All()),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                    ),
                    davxml.Protected(),
                ),
            )
        )


    def contentType(self):
        return MimeType.fromString("text/xml")


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

    http_PROPFIND = http_PROPFIND

    def http_GET(self, request):
        """
        The timezone service POST method.
        """

        # GET and POST do the same thing
        return self.http_POST(request)


    def http_POST(self, request):
        """
        The timezone service POST method.
        """

        # Check authentication and access controls
        def _gotResult(_):

            if not request.args:
                # Do normal GET behavior
                return self.render(request)

            method = request.args.get("method", ("",))
            if len(method) != 1:
                raise HTTPError(ErrorResponse(
                    responsecode.BAD_REQUEST,
                    (calendarserver_namespace, "valid-method"),
                    "Invalid method query parameter",
                ))
            method = method[0]

            action = {
                "list"   : self.doPOSTList,
                "get"    : self.doPOSTGet,
                "expand" : self.doPOSTExpand,
            }.get(method, None)

            if action is None:
                raise HTTPError(ErrorResponse(
                    responsecode.BAD_REQUEST,
                    (calendarserver_namespace, "supported-method"),
                    "Unknown method query parameter",
                ))

            return action(request)

        d = self.authorize(request, (davxml.Read(),))
        d.addCallback(_gotResult)
        return d


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
            raise HTTPError(ErrorResponse(
                responsecode.BAD_REQUEST,
                (calendarserver_namespace, "valid-timezone"),
                "Invalid tzid query parameter",
            ))
        tzid = tzid[0]

        try:
            tzdata = readTZ(tzid)
        except TimezoneException:
            raise HTTPError(ErrorResponse(
                responsecode.NOT_FOUND,
                (calendarserver_namespace, "timezone-available"),
                "Timezone not found",
            ))

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
            raise HTTPError(ErrorResponse(
                responsecode.BAD_REQUEST,
                (calendarserver_namespace, "valid-timezone"),
                "Invalid tzid query parameter",
            ))
        tzid = tzid[0]
        try:
            tzdata = readTZ(tzid)
        except TimezoneException:
            raise HTTPError(ErrorResponse(
                responsecode.NOT_FOUND,
                (calendarserver_namespace, "timezone-available"),
                "Timezone not found",
            ))

        try:
            start = request.args.get("start", ())
            if len(start) != 1:
                raise ValueError()
            start = DateTime.parseText(start[0])
        except ValueError:
            raise HTTPError(ErrorResponse(
                responsecode.BAD_REQUEST,
                (calendarserver_namespace, "valid-start-date"),
                "Invalid start query parameter",
            ))

        try:
            end = request.args.get("end", ())
            if len(end) != 1:
                raise ValueError()
            end = DateTime.parseText(end[0])
            if end <= start:
                raise ValueError()
        except ValueError:
            raise HTTPError(ErrorResponse(
                responsecode.BAD_REQUEST,
                (calendarserver_namespace, "valid-end-date"),
                "Invalid end query parameter",
            ))

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
