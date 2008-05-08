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
CalDAV-aware resources.
"""

__all__ = [
    "CalDAVComplianceMixIn",
    "CalDAVResource",
    "CalendarPrincipalCollectionResource",
    "CalendarPrincipalResource",
    "isCalendarCollectionResource",
    "isPseudoCalendarCollectionResource",
]

from zope.interface import implements

from twisted.internet import reactor
from twisted.internet.defer import Deferred, maybeDeferred, succeed
from twisted.internet.defer import waitForDeferred
from twisted.internet.defer import deferredGenerator
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.idav import IDAVPrincipalCollectionResource
from twisted.web2.dav.resource import AccessDeniedError, DAVPrincipalCollectionResource
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
from twistedcaldav import caldavxml, customxml
from twistedcaldav.config import config
from twistedcaldav.customxml import TwistedCalendarAccessProperty
from twistedcaldav.extensions import DAVResource, DAVPrincipalResource
from twistedcaldav.ical import Component
from twistedcaldav.icaldav import ICalDAVResource, ICalendarPrincipalResource
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.ical import allowedComponents
from twistedcaldav.ical import Component as iComponent

if twistedcaldav.__version__:
    serverVersion = twisted.web2.server.VERSION + " TwistedCalDAV/" + twistedcaldav.__version__
else:
    serverVersion = twisted.web2.server.VERSION + " TwistedCalDAV/?"

class CalDAVComplianceMixIn(object):

    def davComplianceClasses(self):
        extra_compliance = caldavxml.caldav_compliance
        if config.EnableProxyPrincipals:
            extra_compliance += customxml.calendarserver_proxy_compliance
        if config.EnablePrivateEvents:
            extra_compliance += customxml.calendarserver_private_events_compliance
        return tuple(super(CalDAVComplianceMixIn, self).davComplianceClasses()) + extra_compliance


class CalDAVResource (CalDAVComplianceMixIn, DAVResource):
    """
    CalDAV resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """
    implements(ICalDAVResource)

    ##
    # HTTP
    ##

    def render(self, request):
        # Send listing instead of iCalendar data to HTML agents
        # This is mostly useful for debugging...
        # FIXME: Add a self-link to the dirlist with a query string so
        #     users can still download the actual iCalendar data?
        agent = request.headers.getHeader("user-agent")
        if agent is not None and agent.startswith("Mozilla/") and agent.find("Gecko") != -1:
            html_agent = True
        else:
            html_agent = False

        if not html_agent and self.isPseudoCalendarCollection():
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

    liveProperties = DAVResource.liveProperties + (
        (dav_namespace,    "owner"),               # Private Events needs this but it is also OK to return empty
        (caldav_namespace, "supported-calendar-component-set"),
        (caldav_namespace, "supported-calendar-data"         ),
    )

    supportedCalendarComponentSet = caldavxml.SupportedCalendarComponentSet(
        *[caldavxml.CalendarComponent(name=item) for item in allowedComponents]
    )

    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname

        if namespace == dav_namespace:
            if name == "owner":
                d = self.owner(request)
                d.addCallback(lambda x: davxml.Owner(x))
                return d
            
        elif namespace == caldav_namespace:
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
                if config.MaximumAttachmentSize:
                    return succeed(caldavxml.MaxResourceSize.fromString(
                        str(config.MaximumAttachmentSize)
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
    @deferredGenerator
    def accessControlList(self, request, *args, **kwargs):
        if self.isDisabled():
            yield None
            return

        d = waitForDeferred(super(CalDAVResource, self).accessControlList(request, *args, **kwargs))
        yield d
        acls = d.getResult()

        # Look for private events access classification
        if self.hasDeadProperty(TwistedCalendarAccessProperty):
            access = self.readDeadProperty(TwistedCalendarAccessProperty)
            if access.getValue() in (Component.ACCESS_PRIVATE, Component.ACCESS_CONFIDENTIAL, Component.ACCESS_RESTRICTED,):
                # Need to insert ACE to prevent non-owner principals from seeing this resource
                d = waitForDeferred(self.owner(request))
                yield d
                owner = d.getResult()
                if access.getValue() == Component.ACCESS_PRIVATE:
                    ace = davxml.ACE(
                        davxml.Invert(
                            davxml.Principal(owner),
                        ),
                        davxml.Deny(
                            davxml.Privilege(
                                davxml.Read(),
                            ),
                            davxml.Privilege(
                                davxml.Write(),
                            ),
                        ),
                        davxml.Protected(),
                    )
                else:
                    ace = davxml.ACE(
                        davxml.Invert(
                            davxml.Principal(owner),
                        ),
                        davxml.Deny(
                            davxml.Privilege(
                                davxml.Write(),
                            ),
                        ),
                        davxml.Protected(),
                    )

                acls = davxml.ACL(ace, *acls.children)
        yield acls

    @deferredGenerator
    def owner(self, request):
        """
        Return the DAV:owner property value (MUST be a DAV:href or None).
        """
        d = waitForDeferred(self.locateParent(request, request.urlForResource(self)))
        yield d
        parent = d.getResult()
        if parent and isinstance(parent, CalDAVResource):
            d = waitForDeferred(parent.owner(request))
            yield d
            yield d.getResult()
        else:
            yield None

    @deferredGenerator
    def isOwner(self, request):
        """
        Determine whether the DAV:owner of this resource matches the currently authorized principal
        in the request.
        """

        d = waitForDeferred(self.owner(request))
        yield d
        owner = d.getResult()
        result = (davxml.Principal(owner) == self.currentPrincipal(request))
        yield result
 
    ##
    # CalDAV
    ##

    def isCalendarCollection(self):
        """
        See L{ICalDAVResource.isCalendarCollection}.
        """
        return self.isSpecialCollection(caldavxml.Calendar)

    def isSpecialCollection(self, collectiontype):
        """
        See L{ICalDAVResource.isSpecialCollection}.
        """
        if not self.isCollection(): return False

        try:
            resourcetype = self.readDeadProperty((dav_namespace, "resourcetype"))
            return bool(resourcetype.childrenOfType(collectiontype))
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

    def principalForCalendarUserAddress(self, address):
        for principalCollection in self.principalCollections():
            principal = principalCollection.principalForCalendarUserAddress(address)
            if principal is not None:
                return principal
        return None

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
        calendar collection have the same privileges unless explicitly overridden. The same applies
        to drop box collections as we want all resources (attachments) to have the same privileges as
        the drop box collection.
        
        @param newaces: C{list} of L{ACE} for ACL being set.
        """
        
        # Do this only for regular calendar collections and Inbox/Outbox
        if self.isPseudoCalendarCollection():
            edited_aces = []
            for ace in newaces:
                if TwistedACLInheritable() not in ace.children:
                    children = list(ace.children)
                    children.append(TwistedACLInheritable())
                    edited_aces.append(davxml.ACE(*children))
                else:
                    edited_aces.append(ace)
        else:
            edited_aces = newaces
        
        # Do inherited with possibly modified set of aces
        super(CalDAVResource, self).writeNewACEs(edited_aces)

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

class CalendarPrincipalCollectionResource (DAVPrincipalCollectionResource, CalDAVResource):
    """
    CalDAV principal collection.
    """
    implements(IDAVPrincipalCollectionResource)

    def isCollection(self):
        return True

    def isCalendarCollection(self):
        return False

    def isPseudoCalendarCollection(self):
        return False

    def principalForCalendarUserAddress(self, address):
        return None

    def supportedReports(self):
        """
        Principal collections are the only resources supporting the
        principal-search-property-set report.
        """
        result = super(CalendarPrincipalCollectionResource, self).supportedReports()
        result.append(davxml.Report(davxml.PrincipalSearchPropertySet(),))
        return result

    def principalSearchPropertySet(self):
        return davxml.PrincipalSearchPropertySet(
            davxml.PrincipalSearchProperty(
                davxml.PropertyContainer(
                    davxml.DisplayName()
                ),
                davxml.Description(
                    davxml.PCDATAElement("Display Name"),
                    **{"xml:lang":"en"}
                ),
            ),
            davxml.PrincipalSearchProperty(
                davxml.PropertyContainer(
                    caldavxml.CalendarUserAddressSet()
                ),
                davxml.Description(
                    davxml.PCDATAElement("Calendar User Addresses"),
                    **{"xml:lang":"en"}
                ),
            ),
        )

class CalendarPrincipalResource (CalDAVComplianceMixIn, DAVPrincipalResource):
    """
    CalDAV principal resource.

    Extends L{DAVPrincipalResource} to provide CalDAV functionality.
    """
    implements(ICalendarPrincipalResource)

    liveProperties = tuple(DAVPrincipalResource.liveProperties) + (
        (caldav_namespace, "calendar-home-set"        ),
        (caldav_namespace, "calendar-user-address-set"),
        (caldav_namespace, "schedule-inbox-URL"       ),
        (caldav_namespace, "schedule-outbox-URL"      ),
    )

    @classmethod
    def enableDropBox(clz, enable):
        qname = (calendarserver_namespace, "dropbox-home-URL" )
        if enable and qname not in clz.liveProperties:
            clz.liveProperties += (qname,)
        elif not enable and qname in clz.liveProperties:
            clz.liveProperties = tuple([p for p in clz.liveProperties if p != qname])

    def isCollection(self):
        return True

    def readProperty(self, property, request):
        def defer():
            if type(property) is tuple:
                qname = property
            else:
                qname = property.qname()

            namespace, name = qname

            if namespace == caldav_namespace:
                if name == "calendar-home-set":
                    return caldavxml.CalendarHomeSet(
                        *[davxml.HRef(url) for url in self.calendarHomeURLs()]
                    )

                if name == "calendar-user-address-set":
                    return succeed(caldavxml.CalendarUserAddressSet(
                        *[davxml.HRef(uri) for uri in self.calendarUserAddresses()]
                    ))

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

            elif namespace == calendarserver_namespace:
                if name == "dropbox-home-URL" and config.EnableDropBox:
                    url = self.dropboxURL()
                    if url is None:
                        return None
                    else:
                        return customxml.DropBoxHomeURL(davxml.HRef(url))

            return super(CalendarPrincipalResource, self).readProperty(property, request)

        return maybeDeferred(defer)

    def groupMembers(self):
        return ()

    def groupMemberships(self):
        return ()

    def calendarHomeURLs(self):
        if self.hasDeadProperty((caldav_namespace, "calendar-home-set")):
            home_set = self.readDeadProperty((caldav_namespace, "calendar-home-set"))
            return [str(h) for h in home_set.children]
        else:
            return ()

    def calendarUserAddresses(self):
        if self.hasDeadProperty((caldav_namespace, "calendar-user-address-set")):
            addresses = self.readDeadProperty((caldav_namespace, "calendar-user-address-set"))
            return [str(h) for h in addresses.children]
        else:
            # Must have a valid address of some kind so use the principal uri
            return (self.principalURL(),)

    def calendarFreeBusyURIs(self, request):
        def gotInbox(inbox):
            if inbox is None:
                return ()

            def getFreeBusy(has):
                if not has:
                    return ()
    
                def parseFreeBusy(freeBusySet):
                    return tuple(str(href) for href in freeBusySet.children)
        
                d = inbox.readProperty((caldav_namespace, "calendar-free-busy-set"), request)
                d.addCallback(parseFreeBusy)
                return d
    
            d = inbox.hasProperty((caldav_namespace, "calendar-free-busy-set"), request)
            d.addCallback(getFreeBusy)
            return d

        d = self.scheduleInbox(request)
        d.addCallback(gotInbox)
        return d

    def scheduleInbox(self, request):
        """
        @return: the deferred schedule inbox for this principal.
        """
        return request.locateResource(self.scheduleInboxURL())

    def scheduleInboxURL(self):
        if self.hasDeadProperty((caldav_namespace, "schedule-inbox-URL")):
            inbox = self.readDeadProperty((caldav_namespace, "schedule-inbox-URL"))
            return str(inbox.children[0])
        else:
            return None

    def scheduleOutboxURL(self):
        """
        @return: the schedule outbox URL for this principal.
        """
        if self.hasDeadProperty((caldav_namespace, "schedule-outbox-URL")):
            outbox = self.readDeadProperty((caldav_namespace, "schedule-outbox-URL"))
            return str(outbox.children[0])        
        else:
            return None
        
    def dropboxURL(self):
        """
        @return: the drop box home collection URL for this principal.
        """
        if self.hasDeadProperty((calendarserver_namespace, "dropbox-home-URL")):
            inbox = self.readDeadProperty((caldav_namespace, "dropbox-home-URL"))
            return str(inbox.children[0])
        else:
            return None
        
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
