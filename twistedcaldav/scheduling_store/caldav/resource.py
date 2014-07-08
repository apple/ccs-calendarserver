# -*- test-case-name: twistedcaldav.directory.test.test_calendar -*-
##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
    "deliverSchedulePrivilegeSet",
]


from twistedcaldav.config import config
# _schedulePrivilegeSet implicitly depends on config being initialized. The
# following line is wrong because _schedulePrivilegeSet won't actually use the
# config file, it will pick up stdconfig whenever it is imported, so this works
# around that for now.
__import__("twistedcaldav.stdconfig") # FIXME

from txweb2 import responsecode
from txweb2.dav.http import ErrorResponse, MultiStatusResponse
from txweb2.dav.resource import davPrivilegeSet
from txweb2.dav.util import joinURL, normalizeURL
from txweb2.http import HTTPError

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python.failure import Failure

from twistedcaldav import caldavxml, customxml
from twistedcaldav.caldavxml import caldav_namespace, CalendarFreeBusySet
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.ical import Component, allowedSchedulingComponents
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.resource import isCalendarCollectionResource

from txdav.caldav.datastore.scheduling.caldav.scheduler import CalDAVScheduler
from txdav.caldav.icalendarstore import InvalidDefaultCalendar
from txdav.xml import element as davxml
from txdav.xml.rfc2518 import HRef

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
            result.append(davxml.Report(davxml.SyncCollection(),))
        return result



class ScheduleInboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Inbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """

    def liveProperties(self):

        return super(ScheduleInboxResource, self).liveProperties() + (
            caldavxml.CalendarFreeBusySet.qname(),
            caldavxml.ScheduleDefaultCalendarURL.qname(),
            customxml.ScheduleDefaultTasksURL.qname(),
        )


    def resourceType(self):
        return davxml.ResourceType.scheduleInbox


    def hasProperty(self, property, request):
        """
        Need to special case calendar-free-busy-set for backwards compatibility.
        """

        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        # Force calendar collections to always appear to have the property
        if qname == caldavxml.CalendarFreeBusySet.qname():
            return succeed(True)

        elif qname == customxml.CalendarAvailability.qname():
            return succeed(self.parent._newStoreHome.getAvailability() is not None)

        else:
            return super(ScheduleInboxResource, self).hasProperty(property, request)


    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == caldavxml.CalendarFreeBusySet.qname():
            # Synthesize value for calendar transparency state
            top = self.parent.url()
            values = []
            for cal in (yield self.parent._newStoreHome.calendars()):
                if cal.isUsedForFreeBusy():
                    values.append(HRef(joinURL(top, cal.name()) + "/"))
            returnValue(CalendarFreeBusySet(*values))

        elif qname == customxml.CalendarAvailability.qname():
            availability = self.parent._newStoreHome.getAvailability()
            returnValue(customxml.CalendarAvailability.fromString(str(availability)) if availability else None)

        elif qname in (caldavxml.ScheduleDefaultCalendarURL.qname(), customxml.ScheduleDefaultTasksURL.qname()):
            result = (yield self.readDefaultCalendarProperty(request, qname))
            returnValue(result)

        result = (yield super(ScheduleInboxResource, self).readProperty(property, request))
        returnValue(result)


    @inlineCallbacks
    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement)

        # Strictly speaking CS:calendar-availability is a live property in the sense that the
        # server enforces what can be stored, however it need not actually
        # exist so we cannot list it in liveProperties on this resource, since its
        # its presence there means that hasProperty will always return True for it.
        if property.qname() == customxml.CalendarAvailability.qname():
            if not property.valid():
                raise HTTPError(ErrorResponse(
                    responsecode.CONFLICT,
                    (caldav_namespace, "valid-calendar-data"),
                    description="Invalid property"
                ))
            yield self.parent._newStoreHome.setAvailability(property.calendar())
            returnValue(None)

        elif property.qname() == caldavxml.CalendarFreeBusySet.qname():
            # Verify that the calendars added in the PROPPATCH are valid. We do not check
            # whether existing items in the property are still valid - only new ones.
            property.children = [davxml.HRef(normalizeURL(str(href))) for href in property.children]
            new_calendars = set([str(href) for href in property.children])
            old_calendars = set()
            for cal in (yield self.parent._newStoreHome.calendars()):
                if cal.isUsedForFreeBusy():
                    old_calendars.add(HRef(joinURL(self.parent.url(), cal.name())))
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

            # Remove old ones
            for href in old_calendars.difference(new_calendars):
                cal = (yield request.locateResource(str(href)))
                if cal is not None and cal.exists() and isCalendarCollectionResource(cal) and cal._newStoreObject.isUsedForFreeBusy():
                    yield cal._newStoreObject.setUsedForFreeBusy(False)

            # Add new ones
            for href in new_calendars:
                cal = (yield request.locateResource(str(href)))
                if cal is not None and cal.exists() and isCalendarCollectionResource(cal) and not cal._newStoreObject.isUsedForFreeBusy():
                    yield cal._newStoreObject.setUsedForFreeBusy(True)

            returnValue(None)

        elif property.qname() in (caldavxml.ScheduleDefaultCalendarURL.qname(), customxml.ScheduleDefaultTasksURL.qname()):
            yield self.writeDefaultCalendarProperty(request, property)
            returnValue(None)

        yield super(ScheduleInboxResource, self).writeProperty(property, request)


    @inlineCallbacks
    def removeProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == customxml.CalendarAvailability.qname():
            yield self.parent._newStoreHome.setAvailability(None)
            returnValue(None)

        result = (yield super(ScheduleInboxResource, self).removeProperty(property, request))
        returnValue(result)


    @inlineCallbacks
    def readDefaultCalendarProperty(self, request, qname):
        """
        Read either the default VEVENT or VTODO calendar property. Try to pick one if not present.
        """

        tasks = qname == customxml.ScheduleDefaultTasksURL.qname()
        componentType = "VTODO" if tasks else "VEVENT"
        prop_to_set = customxml.ScheduleDefaultTasksURL if tasks else caldavxml.ScheduleDefaultCalendarURL

        # This property now comes direct from the calendar home new store object
        default = (yield self.parent._newStoreHome.defaultCalendar(componentType, create=False))
        if default is None:
            returnValue(prop_to_set())
        else:
            defaultURL = joinURL(self.parent.url(), default.name())
            returnValue(prop_to_set(davxml.HRef(defaultURL)))


    @inlineCallbacks
    def writeDefaultCalendarProperty(self, request, property):
        """
        Write either the default VEVENT or VTODO calendar property, validating and canonicalizing the value
        """
        if property.qname() == caldavxml.ScheduleDefaultCalendarURL.qname():
            ctype = "VEVENT"
            error_element = (caldav_namespace, "valid-schedule-default-calendar-URL")
        elif property.qname() == customxml.ScheduleDefaultTasksURL.qname():
            ctype = "VTODO"
            error_element = (calendarserver_namespace, "valid-schedule-default-tasks-URL")
        else:
            returnValue(None)

        # Verify that the calendar added in the PROPPATCH is valid.
        property.children = [davxml.HRef(normalizeURL(str(href))) for href in property.children]
        new_calendar = [str(href) for href in property.children]
        cal = None
        if len(new_calendar) == 1:
            cal = (yield request.locateResource(str(new_calendar[0])))
        else:
            raise HTTPError(ErrorResponse(
                responsecode.BAD_REQUEST,
                error_element,
                "Invalid HRef in property",
            ))

        if cal is None or not cal.exists():
            raise HTTPError(ErrorResponse(
                responsecode.BAD_REQUEST,
                error_element,
                "HRef is not a valid calendar",
            ))

        try:
            # Now set it on the new store object
            yield self.parent._newStoreHome.setDefaultCalendar(cal._newStoreObject, ctype)
        except InvalidDefaultCalendar as e:
            raise HTTPError(ErrorResponse(
                responsecode.CONFLICT,
                error_element,
                str(e),
            ))


    @inlineCallbacks
    def defaultCalendar(self, request, componentType):
        """
        Find the default calendar for the supplied iCalendar component type. If one does
        not exist, automatically provision it.
        """

        # This property now comes direct from the calendar home new store object
        default = (yield self.parent._newStoreHome.defaultCalendar(componentType, create=False))

        # Need L{DAVResource} object to return not new store object
        if default is not None:
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

        return succeed(
            davxml.ACL(
                # CalDAV:schedule-deliver for any authenticated user
                davxml.ACE(
                    davxml.Principal(davxml.Authenticated()),
                    davxml.Grant(*privs),
                ),
            )
        )



class ScheduleOutboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Outbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """

    def resourceType(self):
        return davxml.ResourceType.scheduleOutbox


    def getSupportedComponentSet(self):
        return caldavxml.SupportedCalendarComponentSet(
            *[caldavxml.CalendarComponent(name=item) for item in allowedSchedulingComponents]
        )


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

        calendar, format = (yield self.loadCalendarFromRequest(request))
        originator = (yield self.loadOriginatorFromRequestDetails(request))
        recipients = self.loadRecipientsFromCalendarData(calendar)

        # Log extended item
        if not hasattr(request, "extendedLogItems"):
            request.extendedLogItems = {}

        # This is a local CALDAV scheduling operation.
        scheduler = CalDAVScheduler(self._associatedTransaction, self.parent._newStoreHome.uid(), logItems=request.extendedLogItems)

        # Do the POST processing treating
        result = (yield scheduler.doSchedulingViaPOST(originator, recipients, calendar))
        returnValue(result.response(format=format))


    def determineType(self, content_type):
        """
        Determine if the supplied content-type is valid for storing and return the matching PyCalendar type.
        """
        format = None
        if content_type is not None:
            format = "%s/%s" % (content_type.mediaType, content_type.mediaSubtype,)
        return format if format in Component.allowedTypes() else None


    @inlineCallbacks
    def loadCalendarFromRequest(self, request):
        # Must be content-type text/calendar
        contentType = request.headers.getHeader("content-type")
        format = self.determineType(contentType)
        if format is None:
            self.log.error("MIME type %s not allowed in calendar collection" % (contentType,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "supported-calendar-data"),
                "Data is not calendar data",
            ))

        # Parse the calendar object from the HTTP request stream
        try:
            calendar = (yield Component.fromIStream(request.stream, format=format))
        except:
            # FIXME: Bare except
            self.log.error("Error while handling POST: %s" % (Failure(),))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "valid-calendar-data"),
                description="Can't parse calendar data"
            ))

        returnValue((calendar, format,))


    @inlineCallbacks
    def loadOriginatorFromRequestDetails(self, request):
        # The originator is the owner of the Outbox. We will have checked prior to this
        # that the authenticated user has privileges to schedule as the owner.
        originator = ""
        originatorPrincipal = (yield self.ownerPrincipal(request))
        if originatorPrincipal:
            # Pick the canonical CUA:
            originator = originatorPrincipal.canonicalCalendarUserAddress()

        if not originator:
            self.log.error("%s request must have Originator" % (self.method,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "originator-specified"),
                "Missing originator",
            ))
        else:
            returnValue(originator)


    def loadRecipientsFromCalendarData(self, calendar):

        # Get the ATTENDEEs
        attendees = list()
        unique_set = set()
        for attendee, _ignore in calendar.getAttendeesByInstance():
            if attendee not in unique_set:
                attendees.append(attendee)
                unique_set.add(attendee)

        if not attendees:
            self.log.error("POST request must have at least one ATTENDEE")
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "recipient-specified"),
                "Must have recipients",
            ))
        else:
            return(list(attendees))


    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(sendSchedulePrivilegeSet)


    @inlineCallbacks
    def defaultAccessControlList(self):
        if config.EnableProxyPrincipals:
            myPrincipal = yield self.parent.principalForRecord()

            privs = (
                davxml.Privilege(caldavxml.ScheduleSend()),
            )
            if config.Scheduling.CalDAV.OldDraftCompatibility:
                privs += (davxml.Privilege(caldavxml.Schedule()),)

            returnValue(
                davxml.ACL(
                    # CalDAV:schedule for associated write proxies
                    davxml.ACE(
                        davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-write"))),
                        davxml.Grant(*privs),
                        davxml.Protected(),
                    ),
                )
            )
        else:
            result = yield super(ScheduleOutboxResource, self).defaultAccessControlList()
            returnValue(result)


    def report_urn_ietf_params_xml_ns_caldav_calendar_query(self, request, calendar_query):
        return succeed(MultiStatusResponse(()))


    def report_urn_ietf_params_xml_ns_caldav_calendar_multiget(self, request, multiget):
        responses = [davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)) for href in multiget.resources]
        return succeed(MultiStatusResponse((responses)))
