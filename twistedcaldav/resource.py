##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
CalDAV-aware static resources.
"""

__all__ = [
    "CalDAVResource",
    "CalendarPrincipalCollectionResource",
    "CalendarPrincipalResource",
    "CalendarSchedulingCollectionResource",
    "ScheduleInboxResource",
    "ScheduleOutboxResource",
    "isCalendarCollectionResource",
    "isPseudoCalendarCollectionResource",
    "isScheduleInboxResource",
    "isScheduleOutboxResource",
]

from weakref import WeakValueDictionary

from zope.interface import implements
import twisted.web2.server
from twisted.internet.defer import maybeDeferred
from twisted.web2 import responsecode
from twisted.web2.iweb import IResponse
from twisted.web2.http import HTTPError, RedirectResponse, StatusResponse, Response
from twisted.web2.http_headers import MimeType
from twisted.web2.stream import MemoryStream
from twisted.web2.dav import auth
from twisted.web2.dav import davxml
from twisted.web2.dav.acl import DAVPrincipalResource
from twisted.web2.dav.davxml import dav_namespace
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.resource import DAVResource
from twisted.web2.dav.resource import TwistedACLInheritable
from twisted.web2.dav.util import parentForURL

import twistedcaldav
from twistedcaldav import authkerb
from twistedcaldav import caldavxml
from twistedcaldav.icaldav import ICalDAVResource, ICalendarPrincipalResource, ICalendarSchedulingCollectionResource
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.ical import Component as iComponent

if twistedcaldav.__version__:
    serverVersion = twisted.web2.server.VERSION + " TwistedCalDAV/" + twistedcaldav.__version__
else:
    serverVersion = twisted.web2.server.VERSION + " TwistedCalDAV/?"

# Need to replace global DAVResource authenticator with the one we want for our server
def getAuthenticator(self, request):
    """
    See L{DAVResource.getAuthenticator}.
    
    This implementation picks a suitable authorizer from a list of available auth mechanisms.
    
    TODO: We need some way to input a 'realm' to the authorizer. Right now it is empty.
    """

    validAuths = [auth.BasicAuthorizer]
    #validAuths = [auth.DigestAuthorizer]
    #validAuths = [auth.BasicAuthorizer, auth.DigestAuthorizer]
    #validAuths = [authkerb.BasicKerberosAuthorizer]
    #validAuths = [authkerb.NegotiateAuthorizer]
    for authert in validAuths:
        auther = authert("")
        if auther.validForRequest(request):
            return auther
    else:
        return None

DAVResource.getAuthenticator = getAuthenticator

class CalDAVResource (DAVResource):
    """
    CalDAV resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """
    implements(ICalDAVResource)

    ##
    # HTTP
    ##

    def render(self, request):
        if self.isPseudoCalendarCollection():
            # Render a monolithic iCalendar file
            if request.uri[-1] != "/":
                # Redirect to include trailing '/' in URI
                return RedirectResponse(request.unparseURL(path=request.path+'/'))

            response = Response()
            response.stream = MemoryStream(str(self.iCalendar(request=request)))
            response.headers.setHeader("content-type", MimeType.fromString("text/calendar"))

            return response
        else:
            return super(CalDAVResource, self).render(request)

    def renderHTTP(self, request):
        response = maybeDeferred(super(CalDAVResource, self).renderHTTP, request)

        def setHeaders(response):
            response = IResponse(response)
            response.headers.setHeader("server", serverVersion)

            return response

        response.addCallback(setHeaders)

        return response

    ##
    # WebDAV
    ##

    def davComplianceClasses(self):
        return tuple(super(CalDAVResource, self).davComplianceClasses()) + ("calendar-access",)

    liveProperties = DAVResource.liveProperties + (
        (caldav_namespace, "supported-calendar-component-set"),
        (caldav_namespace, "supported-calendar-data"         ),
    )

    supportedCalendarComponentSet = caldavxml.SupportedCalendarComponentSet(
        caldavxml.CalendarComponent(name="VEVENT"   ),
        caldavxml.CalendarComponent(name="VTODO"    ),
        caldavxml.CalendarComponent(name="VTIMEZONE"),
        caldavxml.CalendarComponent(name="VJOURNAL" ),
        caldavxml.CalendarComponent(name="VFREEBUSY"),
    )

    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
            sname = "{%s}%s" % property
        else:
            qname = property.qname()
            sname = property.sname()

        namespace, name = qname

        if namespace == caldav_namespace:
            if name == "supported-calendar-component-set":
                # CalDAV-access-09, section 5.2.3
                if self.deadProperties().contains(qname):
                    return self.deadProperties().get(qname)
                return self.supportedCalendarComponentSet
            elif name == "supported-calendar-data":
                # CalDAV-access-09, section 5.2.4
                return caldavxml.SupportedCalendarData(
                    caldavxml.CalendarData(**{
                        "content-type": "text/calendar",
                        "version"     : "2.0",
                    }),
                )

        return super(CalDAVResource, self).readProperty(property, request)

    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement)

        if property.qname() == (caldav_namespace, "supported-calendar-component-set"):
            if not self.isPseudoCalendarCollection():
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Property %s may only be set on calendar collection." % (property,)
                ))
            for component in property.children:
                if component not in self.supportedCalendarComponentSet:
                    raise HTTPError(StatusResponse(
                        responsecode.NOT_IMPLEMENTED,
                        "Component %s is not supported by this server" % (component.toxml(),)
                    ))
                    
        # Strictly speaking CalDAV:timezone is a live property in the sense that the
        # server enforces what can be stored, however it need not actually
        # exist so we cannot list it in liveProperties on this resource, since its
        # its presence there means that hasProperty will always return True for it.
        elif property.qname() == (caldav_namespace, "calendar-timezone"):
            if not self.isCalendarCollection():
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Property %s may only be set on calendar collection." % (property,)
                ))
            if not property.valid():
                raise HTTPError(ErrorResponse(
                    responsecode.CONFLICT,
                    (caldav_namespace, "valid-calendar-data")
                ))

        return super(CalDAVResource, self).writeProperty(property, request)

    ##
    # CalDAV
    ##

    def isCalendarCollection(self):
        """
        See L{ICalDAVResource.isCalendarCollection}.
        """
        if not self.isCollection(): return False

        try:
            resourcetype = self.readDeadProperty((dav_namespace, "resourcetype"))
            return resourcetype.isCalendar()
        except HTTPError, e:
            assert e.response.code == responsecode.NOT_FOUND
            return False

    def isPseudoCalendarCollection(self):
        """
        See L{ICalDAVResource.isPseudoCalendarCollection}.
        """
        return self.isCalendarCollection()

    def findCalendarCollections(self, depth):
        """
        See L{ICalDAVResource.findCalendarCollections}.
        This implementation raises L{NotImplementedError}; a subclass must
        override it.
        """
        # FIXME: Can this be implemented genericly by using findChildren()?
        return NotImplementedError("Subclass must implement findCalendarCollections()")

    def findCalendarCollectionsWithPrivileges(self, depth, privileges, request):
        """
        See L{ICalDAVResource.findCalendarCollectionsWithPrivileges}.
        This implementation raises L{NotImplementedError}; a subclass must
        override it.
        """
        # FIXME: Can this be implemented genericly by using findChildren()?
        return NotImplementedError("Subclass must implement findCalendarCollectionsWithPrivileges()")

    def createCalendar(self, request):
        """
        See L{ICalDAVResource.createCalendar}.
        This implementation raises L{NotImplementedError}; a subclass must
        override it.
        """
        return NotImplementedError("Subclass must implement createCalendar()")

    def iCalendar(self, name=None):
        """
        See L{ICalDAVResource.iCalendar}.

        This implementation returns the an object created from the data returned
        by L{iCalendarText} when given the same arguments.

        Note that L{iCalendarText} by default calls this method, which creates
        an infinite loop.  A subclass must override one of both of these
        methods.
        """
        calendar_data = self.iCalendarText(name)

        if calendar_data is None: return None

        try:
            return iComponent.fromString(calendar_data)
        except ValueError:
            return None

    def iCalendarText(self, name=None):
        """
        See L{ICalDAVResource.iCalendarText}.

        This implementation returns the string representation (according to
        L{str}) of the object returned by L{iCalendar} when given the same
        arguments.

        Note that L{iCalendar} by default calls this method, which creates
        an infinite loop.  A subclass must override one of both of these
        methods.
        """
        return str(self.iCalendar(name))

    def iCalendarXML(self, name=None):
        """
        See L{ICalDAVResource.iCalendarXML}.
        This implementation returns an XML element constructed from the object
        returned by L{iCalendar} when given the same arguments.
        """
        return caldavxml.CalendarData.fromCalendar(self.iCalendar(name))

    def supportedReports(self):
        result = super(CalDAVResource, self).supportedReports()
        result.append(davxml.Report(caldavxml.CalendarQuery(),))
        result.append(davxml.Report(caldavxml.CalendarMultiGet(),))
        if (self.isCollection()):
            # Only allowed on collections
            result.append(davxml.Report(caldavxml.FreeBusyQuery(),))
        return result

    def writeNewACEs(self, newaces):
        """
        Write a new ACL to the resource's property store. We override this for calendar collections
        and force all the ACEs to be inheritable so that all calendar object resources within the
        calendar collection have the same privileges unless explicitly overridden.
        
        @param newaces: C{list} of L{ACE} for ACL being set.
        """
        
        # Do this only for regular calendar collections and Inbox/Outbox
        if self.isPseudoCalendarCollection():
            # Add inheritable option to each ACE in the list
            for ace in newaces:
                if TwistedACLInheritable() not in ace.children:
                    children = list(ace.children)
                    children.append(TwistedACLInheritable())
                    ace.children = children
        
        # Do inherited with possibly modified set of aces
        super(CalDAVResource, self).writeNewACEs(newaces)

    ##
    # Utilities
    ##

    def locateParent(self, request, uri):
        """
        Locates the parent resource of the resource with the given URI.
        @param request: an L{IRequest} object for the request being processed.
        @param uri: the URI whose parent resource is desired.
        """
        return self.locateSiblingResource(request, parentForURL(uri))

class CalendarPrincipalCollectionResource (CalDAVResource):
    """
    CalDAV principal collection.
    """
    # Use a WeakKeyDictionary to keep track of all instances.
    # A WeakKeySet would be more appropriate, but there is no such class yet.
    _principleCollectionSet = WeakValueDictionary()

    @classmethod
    def outboxForCalendarUser(clazz, request, address):
        """
        Find the URL of the calendar outbox for the specified calendar user
        address.
        @param request: an L{IRequest} object for the request being processed.
        @param address: the calendar user address to look up.
        @return: the URI of the calendar outbox, or C{None} if no outbox for
            exists for the user.
        """
        principal = clazz.findAnyCalendarUser(request, address)
        if principal:
            return principal.scheduleOutboxURL()
        else:
            return None

    @classmethod
    def inboxForCalendarUser(clazz, request, address):
        """
        Find the URL of the calendar inbox for the specified calendar user
        address.
        @param request: an L{IRequest} object for the request being processed.
        @param address: the calendar user address to look up.
        @return: the URI of the calendar inbox, or C{None} if no inbox exists
            for the user
        """
        principal = clazz.findAnyCalendarUser(request, address)
        if principal:
            return principal.scheduleInboxURL()
        else:
            return None

    @classmethod
    def findAnyCalendarUser(clazz, request, address):
        """
        Find the calendar user principal associated with the specified calendar
        user address in any of the currently defined principal collections.
        @param request: an L{IRequest} object for the request being processed.
        @param address: the calendar user address to look up.
        @return: the L{CalendarPrincipalResource} for the specified calendar
            user, or C{None} if the user is not found.
        """
        for url in clazz._principleCollectionSet.keys():
            try:
                pcollection = clazz._principleCollectionSet[url]
                if isinstance(pcollection, CalendarPrincipalCollectionResource):
                    principal = pcollection.findCalendarUser(request, address)
                    if principal is not None:
                        return principal
            except ReferenceError:
                pass

        return None


    def __init__(self, url):
        self._url = url

        # Register self with class
        CalendarPrincipalCollectionResource._principleCollectionSet[url] = self

    def findCalendarUser(self, request, address):
        """
        Find the calendar user principal associated with the specified calendar
        user address.
        @param request: an L{IRequest} object for the request being processed.
        @param address: the calendar user address to lookup.
        @return: the L{CalendarPrincipalResource} for the specified calendar
            user, or C{None} if the user is not found.
        """
        
        # Look at cuaddress property on each child and do attempt a match
        for childname in self.listChildren():
            child = self.getChild(childname)
            if not isinstance(child, CalendarPrincipalResource):
                continue
            if child.matchesCalendarUserAddress(request, address):
                return child
        
        return None

    def principalCollectionURL(self):
        return self._url

    def supportedReports(self):
        """
        Principal collections are the only resources supporting the
        principal-search-property-set report.
        """
        result = super(CalendarPrincipalCollectionResource, self).supportedReports()
        result.append(davxml.Report(davxml.PrincipalSearchPropertySet(),))
        return result

class CalendarPrincipalResource (DAVPrincipalResource):
    """
    CalDAV principal resource.

    Extends L{DAVPrincipalResource} to provide CalDAV functionality.
    """
    implements(ICalendarPrincipalResource)

    def calendarHomeSet(self):
        """
        @return: a list of calendar user home URLs for this principal.
        """
        return self.readDeadProperty((caldavxml.caldav_namespace, "calendar-home-set"))

    def scheduleInboxURL(self):
        """
        @return: the schedule INBOX URL for this principal.
        """
        if self.hasDeadProperty((caldavxml.caldav_namespace, "schedule-inbox-url")):
            inbox = self.readDeadProperty((caldavxml.caldav_namespace, "schedule-inbox-url"))
            assert isinstance(inbox, caldavxml.ScheduleInboxURL)
            inbox.removeWhitespaceNodes()
            if len(inbox.children) == 1:
                return str(inbox.children[0])
        
        return ""

    def scheduleOutboxURL(self):
        """
        @return: the schedule OUTBOX URL for this principal.
        """
        if self.hasDeadProperty((caldavxml.caldav_namespace, "schedule-outbox-url")):
            outbox = self.readDeadProperty((caldavxml.caldav_namespace, "schedule-outbox-url"))
            assert isinstance(outbox, caldavxml.ScheduleOutboxURL)
            outbox.removeWhitespaceNodes()
            if len(outbox.children) == 1:
                return str(outbox.children[0])
        
        return ""
        
    def calendarUserAddressSet(self):
        """
        @return: a list of calendar user addresses for this principal.
        """
        if self.hasDeadProperty((caldavxml.caldav_namespace, "calendar-user-address-set")):
            return self.readDeadProperty((caldavxml.caldav_namespace, "calendar-user-address-set"))
            
        # Must have a valid address of some kind so use the principal uri
        return caldavxml.CalendarUserAddressSet(davxml.HRef().fromString(self._url))

    def matchesCalendarUserAddress(self, request, address):
        """
        Determine whether this principal matches the supplied calendar user
        address.
        @param address: the calendar user address to match.
        @return: C{True} if the principal matches, C{False} otherwise.
        """

        # By default we will always allow either a relative or absolute URI to the principal to
        # be supplied as a valid calendar user address.

        # Try relative URI
        if self._url == address:
            return True
        
        # Try absolute URI
        absurl = request.unparseURL(path=self._url)
        if absurl == address:
            return True

        # Look at the property if URI lookup does not work
        if self.hasProperty((caldav_namespace, "calendar-user-address-set"), request):
            addresses = self.readProperty((caldav_namespace, "calendar-user-address-set"), request)
            for cua in addresses.childrenOfType(davxml.HRef):
                if str(cua) == address:
                    return True
        
        return False

    def calendarFreeBusySet(self, request):
        """
        @return: a list of calendars that contribute to free-busy for this
            principal's calendar user.
        """
        inbox = self.scheduleInboxURL()
        resource = self.locateSiblingResource(request, inbox)
        if resource and resource.hasDeadProperty((caldavxml.caldav_namespace, "calendar-free-busy-set")):
            return resource.readDeadProperty((caldavxml.caldav_namespace, "calendar-free-busy-set"))
        return caldavxml.CalendarFreeBusySet()

class CalendarSchedulingCollectionResource (CalDAVResource):
    """
    CalDAV principal resource.

    Extends L{DAVResource} to provide CalDAV scheduling collection
    functionality.
    """
    implements(ICalendarSchedulingCollectionResource)

    def isCollection(self):
        return True

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return True

    def isScheduleInbox(self):
        return False
    
    def isScheduleOutbox(self):
        return False

    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname

        if namespace == dav_namespace:
            if name == "resourcetype":
                types = [davxml.Collection()]

                if self.isScheduleInbox(): types.append(caldavxml.ScheduleInbox())
                if self.isScheduleOutbox(): types.append(caldavxml.ScheduleOutbox())

                return davxml.ResourceType(*types)

        return super(CalendarSchedulingCollectionResource, self).readProperty(property, request)

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
    def isScheduleInbox(self):
        return True

class ScheduleOutboxResource (CalendarSchedulingCollectionResource):
    """
    CalDAV schedule Outbox resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """
    def isScheduleOutbox(self):
        return True

##
# Utilities
##

def isCalendarCollectionResource(resource):
    try:
        resource = ICalDAVResource(resource)
    except TypeError:
        return False
    else:
        return resource.isCalendarCollection()

def isPseudoCalendarCollectionResource(resource):
    try:
        resource = ICalDAVResource(resource)
    except TypeError:
        return False
    else:
        return resource.isPseudoCalendarCollection()

def isScheduleInboxResource(resource):
    try:
        resource = ICalendarSchedulingCollectionResource(resource)
    except TypeError:
        return False
    else:
        return resource.isScheduleInbox()

def isScheduleOutboxResource(resource):
    try:
        resource = ICalendarSchedulingCollectionResource(resource)
    except TypeError:
        return False
    else:
        return resource.isScheduleOutbox()
