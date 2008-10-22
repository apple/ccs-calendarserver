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
CalDAV scheduling resources.
"""

__all__ = [
    "ScheduleInboxResource",
    "ScheduleOutboxResource",
    "IScheduleInboxResource",
]

from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.idav import IDAVResource
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.dav.util import joinURL, normalizeURL
from twisted.web2.http import HTTPError
from twisted.web2.http import Response
from twisted.web2.http_headers import MimeType

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.scheduling.scheduler import CalDAVScheduler, IScheduleScheduler

class CalendarSchedulingCollectionResource (CalDAVResource):
    """
    CalDAV principal resource.

    Extends L{DAVResource} to provide CalDAV scheduling collection
    functionality.
    """
    def __init__(self, parent):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        CalDAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent

    def isCollection(self):
        return True

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return True

    def supportedReports(self):
        result = super(CalDAVResource, self).supportedReports()
        result.append(davxml.Report(caldavxml.CalendarQuery(),))
        result.append(davxml.Report(caldavxml.CalendarMultiGet(),))
        # free-busy report not allowed
        return result

class ScheduleInboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Inbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """

    liveProperties = CalendarSchedulingCollectionResource.liveProperties + (
        (caldav_namespace, "calendar-free-busy-set"),
        (caldav_namespace, "schedule-default-calendar-URL"),
    )

    def resourceType(self):
        return davxml.ResourceType.scheduleInbox

    def defaultAccessControlList(self):
        return davxml.ACL(
            # CalDAV:schedule for any authenticated user
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(
                    davxml.Privilege(caldavxml.Schedule()),
                ),
            ),
        )

    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == (caldav_namespace, "calendar-free-busy-set"):
            # Always return at least an empty list
            if not self.hasDeadProperty(property):
                return succeed(caldavxml.CalendarFreeBusySet())
        elif qname == (caldav_namespace, "schedule-default-calendar-URL"):
            # Always return at least an empty item
            if not self.hasDeadProperty(property):
                return succeed(caldavxml.ScheduleDefaultCalendarURL())
            
        return super(ScheduleInboxResource, self).readProperty(property, request)

    @inlineCallbacks
    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement)

        # Strictly speaking CS:calendar-availability is a live property in the sense that the
        # server enforces what can be stored, however it need not actually
        # exist so we cannot list it in liveProperties on this resource, since its
        # its presence there means that hasProperty will always return True for it.
        if property.qname() == (calendarserver_namespace, "calendar-availability"):
            if not property.valid():
                raise HTTPError(ErrorResponse(
                    responsecode.CONFLICT,
                    (caldav_namespace, "valid-calendar-data")
                ))

        elif property.qname() == (caldav_namespace, "calendar-free-busy-set"):
            # Verify that the calendars added in the PROPPATCH are valid. We do not check
            # whether existing items in the property are still valid - only new ones.
            property.children = [davxml.HRef(normalizeURL(str(href))) for href in property.children]
            new_calendars = set([str(href) for href in property.children])
            if not self.hasDeadProperty(property):
                old_calendars = set()
            else:
                old_calendars = set([str(href) for href in self.readDeadProperty(property).children])
            added_calendars = new_calendars.difference(old_calendars)
            for href in added_calendars:
                cal = (yield request.locateResource(str(href)))
                if cal is None or not cal.exists() or not isCalendarCollectionResource(cal):
                    # Validate that href's point to a valid calendar.
                    raise HTTPError(ErrorResponse(
                        responsecode.CONFLICT,
                        (caldav_namespace, "valid-calendar-url")
                    ))

        elif property.qname() == (caldav_namespace, "schedule-default-calendar-URL"):
            # Verify that the calendar added in the PROPPATCH is valid.
            property.children = [davxml.HRef(normalizeURL(str(href))) for href in property.children]
            new_calendar = [str(href) for href in property.children]
            if len(new_calendar) == 1:
                cal = (yield request.locateResource(str(new_calendar[0])))
                if cal is None or not cal.exists() or not isCalendarCollectionResource(cal):
                    # Validate that href's point to a valid calendar.
                    raise HTTPError(ErrorResponse(
                        responsecode.CONFLICT,
                        (caldav_namespace, "valid-calendar-url")
                    ))

        yield super(ScheduleInboxResource, self).writeProperty(property, request)

    def processFreeBusyCalendar(self, uri, addit):
        uri = normalizeURL(uri)

        if not self.hasDeadProperty((caldav_namespace, "calendar-free-busy-set")):
            fbset = set()
        else:
            fbset = set([normalizeURL(str(href)) for href in self.readDeadProperty((caldav_namespace, "calendar-free-busy-set")).children])
        if addit:
            if uri not in fbset:
                fbset.add(uri)
                self.writeDeadProperty(caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in fbset]))
        else:
            if uri in fbset:
                fbset.remove(uri)
                self.writeDeadProperty(caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in fbset]))

class ScheduleOutboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Outbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """

    def defaultAccessControlList(self):
        if config.EnableProxyPrincipals:
            myPrincipal = self.parent.principalForRecord()
    
            return davxml.ACL(
                # CalDAV:schedule for associated write proxies
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-write"))),
                    davxml.Grant(davxml.Privilege(caldavxml.Schedule()),),
                    davxml.Protected(),
                ),
            )
        else:
            return super(ScheduleOutboxResource, self).defaultAccessControlList()

    def resourceType(self):
        return davxml.ResourceType.scheduleOutbox

    @inlineCallbacks
    def http_POST(self, request):
        """
        The CalDAV POST method.
    
        This uses a generator function yielding either L{waitForDeferred} objects or L{Response} objects.
        This allows for code that follows a 'linear' execution pattern rather than having to use nested
        L{Deferred} callbacks. The logic is easier to follow this way plus we don't run into deep nesting
        issues which the other approach would have with large numbers of recipients.
        """
        # Check authentication and access controls
        yield self.authorize(request, (caldavxml.Schedule(),))

        # This is a local CALDAV scheduling operation.
        scheduler = CalDAVScheduler(request, self)

        # Do the POST processing treating
        result = (yield scheduler.doSchedulingViaPOST())
        returnValue(result.response())

class IScheduleInboxResource (CalDAVResource):
    """
    iSchedule Inbox resource.

    Extends L{DAVResource} to provide iSchedule inbox functionality.
    """

    def __init__(self, parent):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        CalDAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent

    def defaultAccessControlList(self):
        return davxml.ACL(
            # DAV:Read, CalDAV:schedule for all principals (includes anonymous)
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                    davxml.Privilege(caldavxml.Schedule()),
                ),
                davxml.Protected(),
            ),
        )

    def resourceType(self):
        return davxml.ResourceType.ischeduleinbox

    def isCollection(self):
        return False

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return False

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

    @inlineCallbacks
    def http_POST(self, request):
        """
        The server-to-server POST method.
        """

        # Check authentication and access controls
        yield self.authorize(request, (caldavxml.Schedule(),))

        # This is a server-to-server scheduling operation.
        scheduler = IScheduleScheduler(request, self)

        # Do the POST processing treating this as a non-local schedule
        result = (yield scheduler.doSchedulingViaPOST())
        returnValue(result.response())
