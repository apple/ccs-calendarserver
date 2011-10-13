# -*- test-case-name: twistedcaldav.directory.test.test_calendar -*-
##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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


from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.dav.element.extensions import SyncCollection
from twext.web2.dav.element.rfc2518 import HRef
from twext.web2.dav.http import ErrorResponse, MultiStatusResponse
from twext.web2.dav.noneprops import NonePropertyStore
from twext.web2.dav.resource import davPrivilegeSet
from twext.web2.dav.util import joinURL, normalizeURL
from twext.web2.http import HTTPError
from twext.web2.http import Response
from twext.web2.http_headers import MimeType

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import caldav_namespace, Opaque,\
    CalendarFreeBusySet, ScheduleCalendarTransp
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.extensions import DAVResource
from twistedcaldav.resource import CalDAVResource, ReadOnlyNoCopyResourceMixIn
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.scheduling.scheduler import CalDAVScheduler, IScheduleScheduler

from txdav.base.propertystore.base import PropertyName

def _schedulePrivilegeSet(deliver):
    edited = False

    top_supported_privileges = []

    for supported_privilege in davPrivilegeSet.childrenOfType(davxml.SupportedPrivilege):
        all_privilege = supported_privilege.childOfType(davxml.Privilege)
        if isinstance(all_privilege.children[0], davxml.All):
            all_description = supported_privilege.childOfType(davxml.Description)
            all_supported_privileges = list(supported_privilege.childrenOfType(davxml.SupportedPrivilege))
            all_supported_privileges.append(
                davxml.SupportedPrivilege(
                    davxml.Privilege(caldavxml.ScheduleDeliver() if deliver else caldavxml.ScheduleSend()),
                    davxml.Description("schedule privileges for current principal", **{"xml:lang": "en"}),
                ),
            )
            if config.Scheduling.CalDAV.OldDraftCompatibility:
                all_supported_privileges.append(
                    davxml.SupportedPrivilege(
                        davxml.Privilege(caldavxml.Schedule()),
                        davxml.Description("old-style schedule privileges for current principal", **{"xml:lang": "en"}),
                    ),
                )
            top_supported_privileges.append(
                davxml.SupportedPrivilege(all_privilege, all_description, *all_supported_privileges)
            )
            edited = True
        else:
            top_supported_privileges.append(supported_privilege)

    assert edited, "Structure of davPrivilegeSet changed in a way that I don't know how to extend for schedulePrivilegeSet"

    return davxml.SupportedPrivilegeSet(*top_supported_privileges)

deliverSchedulePrivilegeSet = _schedulePrivilegeSet(True)
sendSchedulePrivilegeSet = _schedulePrivilegeSet(False)

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

        super(CalendarSchedulingCollectionResource, self).__init__(principalCollections=parent.principalCollections())

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
        if config.EnableSyncReport:
            # Only allowed on calendar/inbox/addressbook collections
            result.append(davxml.Report(SyncCollection(),))
        return result

class ScheduleInboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Inbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """

    def liveProperties(self):
        
        return super(ScheduleInboxResource, self).liveProperties() + (
            (caldav_namespace, "calendar-free-busy-set"),
            (caldav_namespace, "schedule-default-calendar-URL"),
        )

    def resourceType(self):
        return davxml.ResourceType.scheduleInbox

    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == (caldav_namespace, "calendar-free-busy-set"):
            # Always return at least an empty list
            if not self.hasDeadProperty(property):
                top = self.parent.url()
                values = []
                for cal in (yield self.parent._newStoreHome.calendars()):
                    prop = cal.properties().get(PropertyName.fromString(ScheduleCalendarTransp.sname())) 
                    if prop == ScheduleCalendarTransp(Opaque()):
                        values.append(HRef(joinURL(top, cal.name())))
                returnValue(CalendarFreeBusySet(*values))
        elif qname == (caldav_namespace, "schedule-default-calendar-URL"):
            # Must have a valid default
            try:
                defaultCalendarProperty = self.readDeadProperty(property)
            except HTTPError:
                defaultCalendarProperty = None
            if defaultCalendarProperty and len(defaultCalendarProperty.children) == 1:
                defaultCalendar = str(defaultCalendarProperty.children[0])
                cal = (yield request.locateResource(str(defaultCalendar)))
                if cal is not None and isCalendarCollectionResource(cal) and cal.exists() and not cal.isVirtualShare():
                    returnValue(defaultCalendarProperty) 
            
            # Default is not valid - we have to try to pick one
            defaultCalendarProperty = (yield self.pickNewDefaultCalendar(request))
            returnValue(defaultCalendarProperty)
            
        result = (yield super(ScheduleInboxResource, self).readProperty(property, request))
        returnValue(result)

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
                    (caldav_namespace, "valid-calendar-data"),
                    description="Invalid property"
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
                        (caldav_namespace, "valid-calendar-url"),
                        "Invalid URI",
                    ))

        elif property.qname() == (caldav_namespace, "schedule-default-calendar-URL"):
            # Verify that the calendar added in the PROPPATCH is valid.
            property.children = [davxml.HRef(normalizeURL(str(href))) for href in property.children]
            new_calendar = [str(href) for href in property.children]
            cal = None
            if len(new_calendar) == 1:
                calURI = str(new_calendar[0])
                cal = (yield request.locateResource(str(new_calendar[0])))
            # TODO: check that owner of the new calendar is the same as owner of this inbox
            if cal is None or not cal.exists() or not isCalendarCollectionResource(cal) or cal.isVirtualShare():
                # Validate that href's point to a valid calendar.
                raise HTTPError(ErrorResponse(
                    responsecode.CONFLICT,
                    (caldav_namespace, "valid-schedule-default-calendar-URL"),
                    "Invalid URI",
                ))
            else:
                # Canonicalize the URL to __uids__ form
                calURI = (yield cal.canonicalURL(request))
                property = caldavxml.ScheduleDefaultCalendarURL(davxml.HRef(calURI))

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

    @inlineCallbacks
    def pickNewDefaultCalendar(self, request):
        """
        First see if "calendar" exists in the calendar home and pick that. Otherwise
        create "calendar" in the calendar home.
        """
        calendarHomeURL = self.parent.url()
        defaultCalendarURL = joinURL(calendarHomeURL, "calendar")
        defaultCalendar = (yield request.locateResource(defaultCalendarURL))
        if defaultCalendar is None or not defaultCalendar.exists():
            # FIXME: the back-end should re-provision a default calendar here.
            # Really, the dead property shouldn't be necessary, and this should
            # be entirely computed by a back-end method like 'defaultCalendar()'
            for calendarName in (yield self.parent._newStoreHome.listCalendars()):  # These are only unshared children
                if calendarName != "inbox":
                    aCalendar = calendarName
                    break
            else:
                raise RuntimeError("No valid calendars to use as a default calendar.")

            defaultCalendarURL = joinURL(calendarHomeURL, aCalendar)

        self.writeDeadProperty(
            caldavxml.ScheduleDefaultCalendarURL(
                davxml.HRef(defaultCalendarURL)
            )
        )
        returnValue(caldavxml.ScheduleDefaultCalendarURL(
            davxml.HRef(defaultCalendarURL))
        )

    @inlineCallbacks
    def defaultCalendar(self, request, componentType):
        """
        Find the default calendar for the supplied iCalendar component type. If one does
        not exist, automatically provision it. 
        """

        # Check any default calendar property first
        default = (yield self.readProperty((caldav_namespace, "schedule-default-calendar-URL"), request))
        if len(default.children) == 1:
            defaultURL = str(default.children[0])
            default = (yield request.locateResource(defaultURL))
        else:
            default = None

        # Check that default handles the component type
        if default is not None:
            if not default.isSupportedComponent(componentType):
                default = None
        
        # Must have a default - provision one if not
        if default is None:
            
            # Try to find a calendar supporting the required component type. If there are multiple, pick
            # the one with the oldest created timestamp as that will likely be the initial provision.
            for calendarName in (yield self.parent._newStoreHome.listCalendars()):  # These are only unshared children
                if calendarName == "inbox":
                    continue
                calendar = (yield self.parent._newStoreHome.calendarWithName(calendarName))
                if not calendar.isSupportedComponent(componentType):
                    continue
                if default is None or calendar.created() < default.created():
                    default = calendar
            
            # If none can be found, provision one
            if default is None:
                new_name = "%ss" % (componentType.lower()[1:],)
                default = yield self.parent._newStoreHome.createCalendarWithName(new_name)
                default.setSupportedComponents(componentType.upper())
            
            # Need L{DAVResource} object to return not new store object
            default = (yield request.locateResource(joinURL(self.parent.url(), default.name())))
        
        returnValue(default)

    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(deliverSchedulePrivilegeSet)

    def defaultAccessControlList(self):
        
        privs = (
            davxml.Privilege(caldavxml.ScheduleDeliver()),
        )
        if config.Scheduling.CalDAV.OldDraftCompatibility:
            privs += (davxml.Privilege(caldavxml.Schedule()),)

        return davxml.ACL(
            # CalDAV:schedule-deliver for any authenticated user
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(*privs),
            ),
        )

class ScheduleOutboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Outbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """

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
        yield self.authorize(request, (caldavxml.ScheduleSend(),))

        # This is a local CALDAV scheduling operation.
        scheduler = CalDAVScheduler(request, self)

        # Do the POST processing treating
        result = (yield scheduler.doSchedulingViaPOST())
        returnValue(result.response())


    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(sendSchedulePrivilegeSet)

    def defaultAccessControlList(self):
        if config.EnableProxyPrincipals:
            myPrincipal = self.parent.principalForRecord()
    
            privs = (
                davxml.Privilege(caldavxml.ScheduleSend()),
            )
            if config.Scheduling.CalDAV.OldDraftCompatibility:
                privs += (davxml.Privilege(caldavxml.Schedule()),)
    
            return davxml.ACL(
                # CalDAV:schedule for associated write proxies
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-write"))),
                    davxml.Grant(*privs),
                    davxml.Protected(),
                ),
            )
        else:
            return super(ScheduleOutboxResource, self).defaultAccessControlList()

    def report_urn_ietf_params_xml_ns_caldav_calendar_query(self, request, calendar_query):
        return succeed(MultiStatusResponse(()))
        
    def report_urn_ietf_params_xml_ns_caldav_calendar_multiget(self, request, multiget):
        responses = [davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)) for href in multiget.resources]
        return succeed(MultiStatusResponse((responses)))

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
        return None

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

    @inlineCallbacks
    def http_POST(self, request):
        """
        The server-to-server POST method.
        """

        # Check authentication and access controls
        yield self.authorize(request, (caldavxml.ScheduleDeliver(),))

        # This is a server-to-server scheduling operation.
        scheduler = IScheduleScheduler(request, self)

        # Need a transaction to work with
        txn = self._newStore.newTransaction("new transaction for Server To Server Inbox Resource")
        request._newStoreTransaction = txn
         
        # Do the POST processing treating this as a non-local schedule
        try:
            result = (yield scheduler.doSchedulingViaPOST(use_request_headers=True))
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
        if config.Scheduling.CalDAV.OldDraftCompatibility:
            privs += (davxml.Privilege(caldavxml.Schedule()),)

        return davxml.ACL(
            # DAV:Read, CalDAV:schedule-deliver for all principals (includes anonymous)
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(*privs),
                davxml.Protected(),
            ),
        )
