##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from pycalendar.datetime import DateTime
from pycalendar.timezone import Timezone

from twext.web2 import responsecode
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.noneprops import NonePropertyStore
from twext.web2.dav.util import allDataFromStream
from twext.web2.http import Response, HTTPError, StatusResponse, XMLResponse
from twext.web2.http_headers import MimeType

from twisted.internet.defer import succeed, returnValue, inlineCallbacks
from twisted.python.failure import Failure

from twistedcaldav import caldavxml
from twistedcaldav.config import config
from twistedcaldav.directory.util import transactionFromRequest
from twistedcaldav.extensions import DAVResource, DAVResourceWithoutChildrenMixin
from twistedcaldav.ical import Component
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn
from twistedcaldav.scheduling_store.caldav.resource import deliverSchedulePrivilegeSet

from txdav.caldav.datastore.scheduling.ischedule.dkim import ISCHEDULE_CAPABILITIES
from txdav.caldav.datastore.scheduling.ischedule.scheduler import IScheduleScheduler
from txdav.caldav.datastore.scheduling.ischedule.xml import ischedule_namespace
from txdav.xml import element as davxml
import txdav.caldav.datastore.scheduling.ischedule.xml  as ischedulexml

__all__ = [
    "IScheduleInboxResource",
]

class IScheduleInboxResource (ReadOnlyNoCopyResourceMixIn, DAVResourceWithoutChildrenMixin, DAVResource):
    """
    iSchedule Inbox resource.

    Extends L{DAVResource} to provide iSchedule inbox functionality.
    """

    def __init__(self, parent, store, podding=False):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        DAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent
        self._newStore = store
        self._podding = podding


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
        return MimeType.fromString("text/html; charset=utf-8")


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
<title>%(rtype)s Inbox Resource</title>
</head>
<body>
<h1>%(rtype)s Inbox Resource.</h1>
</body
</html>""" % {"rtype" : "Podding" if self._podding else "iSchedule", }

        response = Response(200, {}, output)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response


    def http_GET(self, request):
        """
        The iSchedule GET method.
        """

        if not request.args or self._podding:
            # Do normal GET behavior
            return self.render(request)

        action = request.args.get("action", ("",))
        if len(action) != 1:
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid action parameter",
            ))
        action = action[0]

        action = {
            "capabilities"  : self.doCapabilities,
        }.get(action, None)

        if action is None:
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Unknown action action parameter",
            ))

        return action(request)


    def doCapabilities(self, request):
        """
        Return a list of all timezones known to the server.
        """

        # Determine min/max date-time for iSchedule
        now = DateTime.getNowUTC()
        minDateTime = DateTime(now.getYear(), 1, 1, 0, 0, 0, Timezone(utc=True))
        minDateTime.offsetYear(-1)
        maxDateTime = DateTime(now.getYear(), 1, 1, 0, 0, 0, Timezone(utc=True))
        maxDateTime.offsetYear(10)

        dataTypes = []
        dataTypes.append(
            ischedulexml.CalendarDataType(**{
                "content-type": "text/calendar",
                "version": "2.0",
            })
        )
        if config.EnableJSONData:
            dataTypes.append(
                ischedulexml.CalendarDataType(**{
                    "content-type": "application/calendar+json",
                    "version": "2.0",
                })
            )
        result = ischedulexml.QueryResult(

            ischedulexml.Capabilities(
                ischedulexml.Version.fromString(config.Scheduling.iSchedule.SerialNumber),
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
                ischedulexml.CalendarDataTypes(*dataTypes),
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
        response = XMLResponse(responsecode.OK, result)
        response.headers.addRawHeader(ISCHEDULE_CAPABILITIES, str(config.Scheduling.iSchedule.SerialNumber))
        return response


    @inlineCallbacks
    def http_POST(self, request):
        """
        The server-to-server POST method.
        """

        # Need a transaction to work with
        txn = transactionFromRequest(request, self._newStore)

        # This is a server-to-server scheduling operation.
        scheduler = IScheduleScheduler(txn, None, podding=self._podding)

        # Check content first
        contentType = request.headers.getHeader("content-type")
        format = self.determineType(contentType)

        if format is None:
            msg = "MIME type %s not allowed in iSchedule request" % (contentType,)
            self.log.error(msg)
            raise HTTPError(scheduler.errorResponse(
                responsecode.FORBIDDEN,
                (ischedule_namespace, "invalid-calendar-data-type"),
                msg,
            ))

        originator = self.loadOriginatorFromRequestHeaders(request)
        recipients = self.loadRecipientsFromRequestHeaders(request)
        body = (yield allDataFromStream(request.stream))
        calendar = Component.fromString(body, format=format)

        # Do the POST processing treating this as a non-local schedule
        try:
            result = (yield scheduler.doSchedulingViaPOST(request.remoteAddr, request.headers, body, calendar, originator, recipients))
        except Exception:
            ex = Failure()
            yield txn.abort()
            ex.raiseException()
        else:
            yield txn.commit()
        response = result.response(format=format)
        if not self._podding:
            response.headers.addRawHeader(ISCHEDULE_CAPABILITIES, str(config.Scheduling.iSchedule.SerialNumber))
        returnValue(response)


    def determineType(self, content_type):
        """
        Determine if the supplied content-type is valid for storing and return the matching PyCalendar type.
        """
        format = None
        if content_type is not None:
            format = "%s/%s" % (content_type.mediaType, content_type.mediaSubtype,)
        return format if format in Component.allowedTypes() else None


    def loadOriginatorFromRequestHeaders(self, request):
        # Must have Originator header
        originator = request.headers.getRawHeaders("originator")
        if originator is None or (len(originator) != 1):
            self.log.error("iSchedule POST request must have Originator header")
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (ischedule_namespace, "originator-missing"),
                "Missing originator",
            ))
        else:
            originator = originator[0]
        return originator


    def loadRecipientsFromRequestHeaders(self, request):
        # Get list of Recipient headers
        rawRecipients = request.headers.getRawHeaders("recipient")
        if rawRecipients is None or (len(rawRecipients) == 0):
            self.log.error("%s request must have at least one Recipient header" % (self.method,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (ischedule_namespace, "recipient-missing"),
                "No recipients",
            ))

        # Recipient header may be comma separated list
        recipients = []
        for rawRecipient in rawRecipients:
            for r in rawRecipient.split(","):
                r = r.strip()
                if len(r):
                    recipients.append(r)

        return recipients


    @inlineCallbacks
    def loadCalendarFromRequest(self, request):
        # Must be content-type text/calendar
        contentType = request.headers.getHeader("content-type")
        if contentType is not None and (contentType.mediaType, contentType.mediaSubtype) != ("text", "calendar"):
            self.log.error("MIME type %s not allowed in iSchedule POST request" % (contentType,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (ischedule_namespace, "invalid-calendar-data-type"),
                "Data is not calendar data",
            ))

        # Parse the calendar object from the HTTP request stream
        try:
            calendar = (yield Component.fromIStream(request.stream))
        except:
            # FIXME: Bare except
            self.log.error("Error while handling iSchedule POST: %s" % (Failure(),))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (ischedule_namespace, "invalid-calendar-data"),
                description="Can't parse calendar data"
            ))

        returnValue(calendar)


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
