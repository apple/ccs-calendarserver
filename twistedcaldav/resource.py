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
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.resource import AccessDeniedError, DAVPrincipalResource
from twisted.web2.dav.davxml import dav_namespace
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.resource import TwistedACLInheritable
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
from twistedcaldav.extensions import DAVResource

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

    # A global limit for the size of calendar object resources. Either a C{int} (size in bytes) to limit
    # resources to that size, or C{None} for no limit.
    sizeLimit = None

    # Set containing user ids of all the users who have been given
    # the right to authorize as someone else.
    proxyUsers = set()

    ##
    # HTTP
    ##

    def render(self, request):
        if self.isPseudoCalendarCollection():
            # Render a monolithic iCalendar file
            if request.uri[-1] != "/":
                # Redirect to include trailing '/' in URI
                return RedirectResponse(request.unparseURL(path=request.path+"/"))

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
                if self.hasDeadProperty(qname):
                    return succeed(self.readDeadProperty(qname))
                return succeed(self.supportedCalendarComponentSet)
            elif name == "supported-calendar-data":
                # CalDAV-access-09, section 5.2.4
                return succeed(caldavxml.SupportedCalendarData(
                    caldavxml.CalendarData(**{
                        "content-type": "text/calendar",
                        "version"     : "2.0",
                    }),
                ))
            elif name == "max-resource-size":
                # CalDAV-access-15, section 5.2.5
                if CalDAVResource.sizeLimit is not None:
                    return succeed(caldavxml.MaxResourceSize.fromString(
                        str(CalDAVResource.sizeLimit)
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
    # ACL
    ##

    def disable(self, disabled=True):
        """
        Completely disables all access to this resource, regardless of ACL
        settings.
        @param disabled: If true, disabled all access. If false, enables access.
        """
        if disabled:
            self.writeDeadProperty(AccessDisabled())
        else:
            self.removeDeadProperty(AccessDisabled())

    def isDisabled(self):
        """
        @return: C{True} if access to this resource is disabled, C{False}
            otherwise.
        """
        return self.hasDeadProperty(AccessDisabled)

    # FIXME: Perhaps this is better done in authorize() instead.
    def accessControlList(self, *args, **kwargs):
        if self.isDisabled():
            return succeed(None)

        return super(CalDAVResource, self).accessControlList(*args, **kwargs)

    def authorizationPrincipal(self, request, authid, authnPrincipal, authnURI):
        """
        Determine the authorization principal for the given request and authentication principal.
        This implementation looks for an X-Authorize-As header value to use as the authoization principal.
        
        @param request: the L{IRequest} for the request in progress.
        @param authid: a string containing the uthentication/authorization identifier
            for the principal to lookup.
        @param authnPrincipal: the L{IDAVPrincipal} for the authenticated principal
        @param authnURI: a C{str} containing the URI of the authenticated principal
        @return: a deferred result C{tuple} of (L{IDAVPrincipal}, C{str}) containing the authorization principal
            resource and URI respectively.
        """

        # Look for X-Authorize-As Header
        authz = request.headers.getRawHeaders("x-authorize-as")
        if authz is not None and (len(authz) == 1):
            # Substitute the authz value for principal look up
            authz = authz[0]

        # See if authenticated uid is a proxy user
        if authid in CalDAVResource.proxyUsers:
            if authz:
                if authz in CalDAVResource.proxyUsers:
                    log.msg("Cannot proxy as another proxy: user '%s' as user '%s'" % (authid, authz))
                    raise HTTPError(responsecode.UNAUTHORIZED)
                else:
                    d = waitForDeferred(self.findPrincipalForAuthID(request, authz))
                    yield d
                    result = d.getResult()

                    if result is not None:
                        log.msg("Allow proxy: user '%s' as '%s'" % (authid, authz,))
                        authzPrincipal = result[0]
                        authzURI = result[1]
                        yield authzPrincipal, authzURI
                        return
                    else:
                        log.msg("Could not find proxy user id: '%s'" % authid)
                        raise HTTPError(responsecode.UNAUTHORIZED)
            else:
                log.msg("Cannot authenticate proxy user '%s' without X-Authorize-As header" % (authid, ))
                raise HTTPError(responsecode.UNAUTHORIZED)
        elif authz:
            log.msg("Cannot proxy: user '%s' as '%s'" % (authid, authz,))
            raise HTTPError(responsecode.UNAUTHORIZED)
        else:
            # No proxy - do default behavior
            d = waitForDeferred(super(CalDAVResource, self).authorizationPrincipal(request, authid, authnPrincipal, authnURI))
            yield d
            yield d.getResult()
            return

    authorizationPrincipal = deferredGenerator(authorizationPrincipal)

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
        See L{ICalDAVResource.findCalendarCollections}.
        """
        assert depth in ("0", "1", "infinity"), "Invalid depth: %s" % (depth,)

        def checkPrivilegesError(failure):
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
                if depth == "infinity": 
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
        if url not in CalendarPrincipalCollectionResource._principleCollectionSet:
            CalendarPrincipalCollectionResource._principleCollectionSet[url] = self

    def isCollection(self):
        return True

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return False

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
            child = waitForDeferred(request.locateChildResource(self, childname))
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

    liveProperties = DAVPrincipalResource.liveProperties + (
        (caldav_namespace, "calendar-home-set"        ),
        (caldav_namespace, "calendar-user-address-set"),
        (caldav_namespace, "schedule-inbox-URL"       ),
        (caldav_namespace, "schedule-outbox-URL"      ),
    )

    def readProperty(self, property, request):
        def defer():
            if type(property) is tuple:
                qname = property
                sname = "{%s}%s" % property
            else:
                qname = property.qname()
                sname = property.sname()

            namespace, name = qname

            if namespace == caldav_namespace:
                if name == "calendar-home-set":
                    return caldavxml.CalendarHomeSet(
                        *[davxml.HRef(url) for url in self.calendarHomeURLs()]
                    )

                if name == "calendar-user-address-set":
                    return caldavxml.CalendarUserAddressSet(
                        *[davxml.HRef(url) for url in self.calendarHomeURLs()]
                    )

                if name == "schedule-inbox-URL":
                    url = self.scheduleInboxURL()
                    if url is None:
                        return None
                    else:
                        return caldavxml.ScheduleInboxURL(davxml.HRef(url))

                if name == "schedule-outbox-URL":
                    url = self.scheduleOutboxURL()
                    if url is None:
                        return None
                    else:
                        return caldavxml.ScheduleOutboxURL(davxml.HRef(url))

            return super(CalendarPrincipalResource, self).readProperty(property, request)

        return maybeDeferred(defer)

    def calendarHomeURLs(self):
        """
        See L{ICalendarPrincipalResource.calendarHomeURLs}.
        This implementation raises L{NotImplementedError} if the dead property
        C{(caldav_namespace, "calendar-home-set")} is not set.
        """
        if self.hasDeadProperty((caldav_namespace, "calendar-home-set")):
            home_set = self.readDeadProperty((caldav_namespace, "calendar-home-set"))
            return [str(h) for h in home_set.children]
        else:
            raise NotImplementedError()

    def calendarUserAddresses(self):
        """
        See L{ICalendarPrincipalResource.calendarUserAddresses}.
        """
        if self.hasDeadProperty((caldav_namespace, "calendar-user-address-set")):
            addresses = self.readDeadProperty((caldav_namespace, "calendar-user-address-set"))
            return [str(h) for h in addresses.children]
        else:
            # Must have a valid address of some kind so use the principal uri
            return (self.principalURL(),)

    @deferredGenerator
    def calendarFreeBusyURIs(self, request):
        """
        See L{ICalendarPrincipalResource.calendarFreeBusyURIs}.
        """
        inbox = waitForDeferred(maybeDeferred(request.locateResource, self.scheduleInboxURL()))
        yield inbox
        inbox = inbox.getResult()

        if inbox is None:
            yield ()
            return

        has = waitForDeferred(inbox.hasProperty((caldav_namespace, "calendar-free-busy-set"), request))
        yield has
        has = has.getResult()
        
        if not has:
            yield ()
            return

        fbset = waitForDeferred(inbox.readProperty((caldav_namespace, "calendar-free-busy-set"), request))
        yield fbset
        fbset = fbset.getResult()

        yield [str(h) for h in fbset.children]

    def scheduleInboxURL(self):
        """
        @return: the schedule INBOX URL for this principal.
        """
        if self.hasDeadProperty((caldav_namespace, "schedule-inbox-URL")):
            inbox = self.readDeadProperty((caldav_namespace, "schedule-inbox-URL"))
            return str(inbox.children[0])
        else:
            return None

    def scheduleOutboxURL(self):
        """
        @return: the schedule OUTBOX URL for this principal.
        """
        if self.hasDeadProperty((caldav_namespace, "schedule-outbox-URL")):
            outbox = self.readDeadProperty((caldav_namespace, "schedule-outbox-URL"))
            return str(outbox.children[0])        
        else:
            return None
        
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
        for cua in self.calendarUserAddresses():
            if cua == address:
                return True
        
        return False

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

class AccessDisabled (davxml.WebDAVEmptyElement):
    namespace = davxml.twisted_private_namespace
    name = "caldav-access-disabled"

davxml.registerElement(AccessDisabled)


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
