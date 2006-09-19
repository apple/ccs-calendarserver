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

from twisted.internet import reactor
from twisted.internet.defer import Deferred, maybeDeferred, succeed
from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.web2 import responsecode
from twisted.web2.dav import auth, davxml
from twisted.web2.dav.resource import DAVPrincipalResource
from twisted.web2.dav.davxml import dav_namespace
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.resource import DAVResource, TwistedACLInheritable
from twisted.web2.dav.util import joinURL, parentForURL, unimplemented
from twisted.web2.http import HTTPError, RedirectResponse, StatusResponse, Response
from twisted.web2.http_headers import MimeType
from twisted.web2.iweb import IResponse
from twisted.web2.stream import MemoryStream
import twisted.web2.server

import twistedcaldav
from twistedcaldav import caldavxml
from twistedcaldav.icaldav import ICalDAVResource, ICalendarPrincipalResource, ICalendarSchedulingCollectionResource
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.ical import Component as iComponent

if twistedcaldav.__version__:
    serverVersion = twisted.web2.server.VERSION + " TwistedCalDAV/" + twistedcaldav.__version__
else:
    serverVersion = twisted.web2.server.VERSION + " TwistedCalDAV/?"

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

            def _defer(data):
                response = Response()
                response.stream = MemoryStream(str(data))
                response.headers.setHeader("content-type", MimeType.fromString("text/calendar"))
                return response

            d = self.iCalendarRolledup(request)
            d.addCallback(_defer)
            return d
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
        return tuple(super(CalDAVResource, self).davComplianceClasses()) + ("calendar-access", "calendar-schedule")

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
        else:
            qname = property.qname()

        namespace, name = qname

        if namespace == caldav_namespace:
            if name == "supported-calendar-component-set":
                # CalDAV-access-09, section 5.2.3
                if self.deadProperties().contains(qname):
                    return succeed(self.deadProperties().get(qname))
                return succeed(self.supportedCalendarComponentSet)
            elif name == "supported-calendar-data":
                # CalDAV-access-09, section 5.2.4
                return succeed(caldavxml.SupportedCalendarData(
                    caldavxml.CalendarData(**{
                        "content-type": "text/calendar",
                        "version"     : "2.0",
                    }),
                ))

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

    def findCalendarCollections(self, depth, request, callback, privileges=None):
        """
        See L{IDAVResource.findChildren}.

        This implementation works for C{depth} values of C{"0"}, C{"1"}, 
        and C{"infinity"}.  As long as C{self.listChildren} is implemented
        """
        assert depth in ("0", "1", "infinity"), "Invalid depth: %s" % (depth,)

        def checkPrivilegesError(failure):
            from twisted.web2.dav.acl import AccessDeniedError
            failure.trap(AccessDeniedError)
            
            reactor.callLater(0, getChild)

        def checkPrivileges(child):
            if privileges is None:
                return child
   
            ca = child.checkPrivileges(request, privileges)
            ca.addCallback(lambda ign: child)
            return ca

        def gotChild(child, childpath):
            if child.isCalendarCollection():
                callback(child, childpath)
            elif child.isCollection():
                if depth == 'infinity': 
                    fc = child.findCalendarCollections(depth, request, callback, privileges)
                    fc.addCallback(lambda x: reactor.callLater(0, getChild))
                    return fc

            reactor.callLater(0, getChild)

        def getChild():
            try:
                childname = children.pop()
            except IndexError:
                completionDeferred.callback(None)
            else:
                childpath = joinURL(basepath, childname)
                child = request.locateResource(childpath)
                child.addCallback(checkPrivileges)
                child.addCallbacks(gotChild, checkPrivilegesError, (childpath,))
                child.addErrback(completionDeferred.errback)

        completionDeferred = Deferred()

        if depth != "0" and self.isCollection():
            basepath = request.urlForResource(self)
            children = self.listChildren()
            getChild()
        else:
            completionDeferred.callback(None)

        return completionDeferred

    def createCalendar(self, request):
        """
        See L{ICalDAVResource.createCalendar}.
        This implementation raises L{NotImplementedError}; a subclass must
        override it.
        """
        unimplemented(self)

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

    def iCalendarRolledup(self, request):
        """
        See L{ICalDAVResource.iCalendarRolledup}.

        This implementation raises L{NotImplementedError}; a subclass must
        override it.
        """
        unimplemented(self)

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
        return request.locateResource(parentForURL(uri))

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
        
        def _defer(principal):
            if principal:
                return principal.scheduleOutboxURL()
            else:
                return None

        d = findAnyCalendarUser(request, address)
        d.addCallback(_defer)
        return d

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
        
        def _defer(principal):
            if principal:
                return principal.scheduleInboxURL()
            else:
                return None

        d = findAnyCalendarUser(request, address)
        d.addCallback(_defer)
        return d

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
            child_url = joinURL(self._url, childname)
            child = waitForDeferred(request.locateResource(child_url))
            yield child
            child = child.getResult()
            if not isinstance(child, CalendarPrincipalResource):
                continue
            if child.matchesCalendarUserAddress(request, address):
                yield child
                return
        
        yield None

    findCalendarUser = deferredGenerator(findCalendarUser)

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

def findAnyCalendarUser(request, address):
    """
    Find the calendar user principal associated with the specified calendar
    user address in any of the currently defined principal collections.
    @param request: an L{IRequest} object for the request being processed.
    @param address: the calendar user address to look up.
    @return: the L{CalendarPrincipalResource} for the specified calendar
        user, or C{None} if the user is not found.
    """
    for url in CalendarPrincipalCollectionResource._principleCollectionSet.keys():
        try:
            pcollection = CalendarPrincipalCollectionResource._principleCollectionSet[url]
            if isinstance(pcollection, CalendarPrincipalCollectionResource):
                principal = waitForDeferred(pcollection.findCalendarUser(request, address))
                yield principal
                principal = principal.getResult()
                if principal is not None:
                    yield principal
                    return
        except ReferenceError:
            pass

    yield None

findAnyCalendarUser = deferredGenerator(findAnyCalendarUser)

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
        return self.readDeadProperty((caldav_namespace, "calendar-home-set"))

    def scheduleInboxURL(self):
        """
        @return: the schedule INBOX URL for this principal.
        """
        if self.hasDeadProperty((caldav_namespace, "schedule-inbox-URL")):
            inbox = self.readDeadProperty((caldav_namespace, "schedule-inbox-URL"))
            assert isinstance(inbox, caldavxml.ScheduleInboxURL)
            inbox.removeWhitespaceNodes()
            if len(inbox.children) == 1:
                return str(inbox.children[0])
        
        return ""

    def scheduleOutboxURL(self):
        """
        @return: the schedule OUTBOX URL for this principal.
        """
        if self.hasDeadProperty((caldav_namespace, "schedule-outbox-URL")):
            outbox = self.readDeadProperty((caldav_namespace, "schedule-outbox-URL"))
            assert isinstance(outbox, caldavxml.ScheduleOutboxURL)
            outbox.removeWhitespaceNodes()
            if len(outbox.children) == 1:
                return str(outbox.children[0])
        
        return ""
        
    def calendarUserAddressSet(self):
        """
        @return: a list of calendar user addresses for this principal.
        """
        if self.hasDeadProperty((caldav_namespace, "calendar-user-address-set")):
            return self.readDeadProperty((caldav_namespace, "calendar-user-address-set"))
            
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
        for cua in self.calendarUserAddressSet().children:
            if str(cua) == address:
                return True
        
        return False

    def calendarFreeBusySet(self, request):
        """
        @return: L{Deferred} whose result is a list of calendars that contribute to free-busy for this
            principal's calendar user.
        """
        
        def _defer(inbox):
            if inbox and inbox.hasDeadProperty((caldav_namespace, "calendar-free-busy-set")):
                return inbox.readDeadProperty((caldav_namespace, "calendar-free-busy-set"))
            return caldavxml.CalendarFreeBusySet()

        inbox_url = self.scheduleInboxURL()
        d = request.locateResource(inbox_url)
        d.addCallback(_defer)
        return d

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

                return succeed(davxml.ResourceType(*types))

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
