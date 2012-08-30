##
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
##

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone
from twext.web2 import responsecode
from twext.web2.dav.noneprops import NonePropertyStore
from twext.web2.http import Response, HTTPError, StatusResponse, XMLResponse
from twext.web2.http_headers import MimeType
from twisted.internet.defer import succeed, returnValue, inlineCallbacks
from twistedcaldav import caldavxml
from twistedcaldav.config import config
from twistedcaldav.extensions import DAVResource
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn
from twistedcaldav.schedule import deliverSchedulePrivilegeSet
from twistedcaldav.scheduling.scheduler import IScheduleScheduler
from txdav.xml import element as davxml
import twistedcaldav.scheduling.ischedule.xml  as ischedulexml

class IScheduleInboxResource (ReadOnlyNoCopyResourceMixIn, DAVResource):
    """
    iSchedule Inbox resource.

    Extends L{DAVResource} to provide iSchedule inbox functionality.
    """

    def __init__(self, parent, store):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        DAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent
        self._newStore = store

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties

    def etag(self):
        return succeed(None)

    def checkPreconditions(self, request):
        return None

    def resourceType(self):
        return davxml.ResourceType.ischeduleinbox

    def contentType(self):
        return MimeType.fromString("text/html; charset=utf-8");

    def isCollection(self):
        return False

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return False

    def principalForCalendarUserAddress(self, address):
        for principalCollection in self.principalCollections():
            principal = principalCollection.principalForCalendarUserAddress(address)
            if principal is not None:
                return principal
        return None

    def render(self, request):
        output = """<html>
<head>
<title>Server To Server Inbox Resource</title>
</head>
<body>
<h1>Server To Server Inbox Resource.</h1>
</body
</html>"""

        response = Response(200, {}, output)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response

    def http_GET(self, request):
        """
        The iSchedule GET method.
        """

        if not request.args:
            # Do normal GET behavior
            return self.render(request)

        query = request.args.get("query", ("",))
        if len(query) != 1:
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid query parameter",
            ))
        query = query[0]
            
        query = {
            "capabilities"  : self.doCapabilities,
        }.get(query, None)
        
        if query is None:
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Unknown query query parameter",
            ))

        return query(request)

    def doCapabilities(self, request):
        """
        Return a list of all timezones known to the server.
        """

        # Determine min/max date-time for iSchedule        
        now = PyCalendarDateTime.getNowUTC()
        minDateTime = PyCalendarDateTime(now.getYear(), 1, 1, 0, 0, 0, PyCalendarTimezone(utc=True))
        minDateTime.offsetYear(-1)
        maxDateTime = PyCalendarDateTime(now.getYear(), 1, 1, 0, 0, 0, PyCalendarTimezone(utc=True))
        maxDateTime.offsetYear(10)

        result = ischedulexml.QueryResult(
            
            ischedulexml.Capabilities(
                ischedulexml.Versions(
                    ischedulexml.Version.fromString("1.0"),
                ),
                ischedulexml.SchedulingMessages(
                    ischedulexml.Component(
                        ischedulexml.Method(name="REQUEST"),
                        ischedulexml.Method(name="CANCEL"),
                        ischedulexml.Method(name="REPLY"),
                        name="VEVENT"
                    ),
                    ischedulexml.Component(
                        ischedulexml.Method(name="REQUEST"),
                        ischedulexml.Method(name="CANCEL"),
                        ischedulexml.Method(name="REPLY"),
                        name="VTODO"
                    ),
                    ischedulexml.Component(
                        ischedulexml.Method(name="REQUEST"),
                        name="VFREEBUSY"
                    ),
                ),
                ischedulexml.CalendarDataTypes(
                    ischedulexml.CalendarDataType(**{
                            "content-type":"text/calendar",
                            "version":"2.0",
                    }),
                ),
                ischedulexml.Attachments(
                    ischedulexml.External(),
                ),
                ischedulexml.MaxContentLength.fromString(config.MaxResourceSize),
                ischedulexml.MinDateTime.fromString(minDateTime.getText()),
                ischedulexml.MaxDateTime.fromString(maxDateTime.getText()),
                ischedulexml.MaxInstances.fromString(config.MaxAllowedInstances),
                ischedulexml.MaxRecipients.fromString(config.MaxAttendeesPerInstance),
                ischedulexml.Administrator.fromString(request.unparseURL(params="", querystring="", fragment="")),
            ),
        )
        return XMLResponse(responsecode.OK, result)

    @inlineCallbacks
    def http_POST(self, request):
        """
        The server-to-server POST method.
        """

        # This is a server-to-server scheduling operation.
        scheduler = IScheduleScheduler(request, self)

        # Need a transaction to work with
        txn = self._newStore.newTransaction("new transaction for Server To Server Inbox Resource")
        request._newStoreTransaction = txn
         
        # Do the POST processing treating this as a non-local schedule
        try:
            result = (yield scheduler.doSchedulingViaPOST(txn, use_request_headers=True))
        except Exception, e:
            yield txn.abort()
            raise e
        else:
            yield txn.commit()
        returnValue(result.response())

    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(deliverSchedulePrivilegeSet)

    def defaultAccessControlList(self):
        privs = (
            davxml.Privilege(davxml.Read()),
            davxml.Privilege(caldavxml.ScheduleDeliver()),
        )

        return davxml.ACL(
            # DAV:Read, CalDAV:schedule-deliver for all principals (includes anonymous)
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(*privs),
                davxml.Protected(),
            ),
        )
