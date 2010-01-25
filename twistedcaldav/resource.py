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

import urllib

from zope.interface import implements

from twext.web2.dav.davxml import ErrorResponse, SyncCollection

from twisted.internet import reactor
from twisted.internet.defer import Deferred, maybeDeferred, succeed
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.auth import AuthenticationWrapper as SuperAuthenticationWrapper
from twisted.web2.dav.davxml import dav_namespace
from twisted.web2.dav.idav import IDAVPrincipalCollectionResource
from twisted.web2.dav.resource import AccessDeniedError, DAVPrincipalCollectionResource
from twisted.web2.dav.resource import TwistedACLInheritable
from twisted.web2.dav.util import joinURL, parentForURL, unimplemented, normalizeURL
from twisted.web2.http import HTTPError, RedirectResponse, StatusResponse, Response
from twisted.web2.http_headers import MimeType
from twisted.web2.iweb import IResponse
from twisted.web2.stream import MemoryStream
import twisted.web2.server

import twistedcaldav
from twistedcaldav import caldavxml, customxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.customxml import TwistedCalendarAccessProperty
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.extensions import DAVResource, DAVPrincipalResource
from twistedcaldav.ical import Component
from twistedcaldav.ical import Component as iComponent
from twistedcaldav.ical import allowedComponents
from twistedcaldav.icaldav import ICalDAVResource, ICalendarPrincipalResource
from twistedcaldav.log import LoggingMixIn

from urlparse import urlsplit

if twistedcaldav.__version__:
    serverVersion = twisted.web2.server.VERSION + " TwistedCalDAV/" + twistedcaldav.__version__
else:
    serverVersion = twisted.web2.server.VERSION + " TwistedCalDAV/?"

class CalDAVComplianceMixIn(object):

    def davComplianceClasses(self):
        if config.Scheduling.CalDAV.OldDraftCompatibility:
            extra_compliance = caldavxml.caldav_full_compliance
        else:
            extra_compliance = caldavxml.caldav_implicit_compliance
        if config.EnableProxyPrincipals:
            extra_compliance += customxml.calendarserver_proxy_compliance
        if config.EnablePrivateEvents:
            extra_compliance += customxml.calendarserver_private_events_compliance
        if config.Scheduling.CalDAV.get("EnablePrivateComments", True):
            extra_compliance += customxml.calendarserver_private_comments_compliance
        extra_compliance += customxml.calendarserver_principal_property_search
        return tuple(super(CalDAVComplianceMixIn, self).davComplianceClasses()) + extra_compliance


def updateCacheTokenOnCallback(f):
    def fun(self, *args, **kwargs):
        def _updateToken(response):
            return self.cacheNotifier.changed().addCallback(
                lambda _: response)

        d = maybeDeferred(f, self, *args, **kwargs)

        if hasattr(self, 'cacheNotifier'):
            d.addCallback(_updateToken)

        return d

    return fun


class CalDAVResource (CalDAVComplianceMixIn, DAVResource, LoggingMixIn):
    """
    CalDAV resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """
    implements(ICalDAVResource)

    ##
    # HTTP
    ##

    def render(self, request):
        if config.EnableMonolithicCalendars:
            #
            # Send listing instead of iCalendar data to HTML agents
            # This is mostly useful for debugging...
            #
            # FIXME: Add a self-link to the dirlist with a query string so
            #     users can still download the actual iCalendar data?
            #
            # FIXME: Are there better ways to detect this than hacking in
            #     user agents?
            #
            # FIXME: In the meantime, make this a configurable regex list?
            #
            agent = request.headers.getHeader("user-agent")
            if agent is not None and (
                agent.startswith("Mozilla/") and agent.find("Gecko") != -1
            ):
                renderAsHTML = True
            else:
                renderAsHTML = False
        else:
            renderAsHTML = True

        if not renderAsHTML and self.isPseudoCalendarCollection():
            # Render a monolithic iCalendar file
            if request.path[-1] != "/":
                # Redirect to include trailing '/' in URI
                return RedirectResponse(request.unparseURL(path=urllib.quote(urllib.unquote(request.path), safe=':/')+'/'))

            def _defer(data):
                response = Response()
                response.stream = MemoryStream(str(data))
                response.headers.setHeader("content-type", MimeType.fromString("text/calendar"))
                return response

            d = self.iCalendarRolledup(request)
            d.addCallback(_defer)
            return d

        return super(CalDAVResource, self).render(request)

    def renderHTTP(self, request):
        response = maybeDeferred(super(CalDAVResource, self).renderHTTP, request)

        def setHeaders(response):
            response = IResponse(response)
            response.headers.setHeader("server", serverVersion)

            return response

        response.addCallback(setHeaders)

        return response

    @updateCacheTokenOnCallback
    def http_PROPPATCH(self, request):
        return super(CalDAVResource, self).http_PROPPATCH(request)

    @updateCacheTokenOnCallback
    def http_DELETE(self, request):
        return super(CalDAVResource, self).http_DELETE(request)

    @updateCacheTokenOnCallback
    def http_ACL(self, request):
        return super(CalDAVResource, self).http_ACL(request)


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

    def hasProperty(self, property, request):
        """
        Need to special case schedule-calendar-transp for backwards compatability.
        """
        
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        # Force calendar collections to always appear to have the property
        if qname == (caldav_namespace, "schedule-calendar-transp") and self.isCalendarCollection():
            return succeed(True)
        else:
            return super(CalDAVResource, self).hasProperty(property, request)

    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname

        if namespace == dav_namespace:
            if name == "owner":
                owner = (yield self.owner(request))
                returnValue(davxml.Owner(owner))

        elif namespace == caldav_namespace:
            if name == "supported-calendar-component-set":
                # CalDAV-access-09, section 5.2.3
                if self.hasDeadProperty(qname):
                    returnValue(self.readDeadProperty(qname))
                returnValue(self.supportedCalendarComponentSet)
            elif name == "supported-calendar-data":
                # CalDAV-access-09, section 5.2.4
                returnValue(caldavxml.SupportedCalendarData(
                    caldavxml.CalendarData(**{
                        "content-type": "text/calendar",
                        "version"     : "2.0",
                    }),
                ))
            elif name == "max-resource-size":
                # CalDAV-access-15, section 5.2.5
                if config.MaximumAttachmentSize:
                    returnValue(caldavxml.MaxResourceSize.fromString(
                        str(config.MaximumAttachmentSize)
                    ))

            elif name == "max-attendees-per-instance":
                # CalDAV-access-15, section 5.2.9
                if config.MaxAttendeesPerInstance:
                    returnValue(caldavxml.MaxAttendeesPerInstance.fromString(
                        str(config.MaxAttendeesPerInstance)
                    ))

            elif name == "schedule-calendar-transp":
                # For backwards compatibility, if the property does not exist we need to create
                # it and default to the old free-busy-set value.
                if self.isCalendarCollection() and not self.hasDeadProperty(property):
                    # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
                    principal = (yield self.ownerPrincipal(request))
                    fbset = (yield principal.calendarFreeBusyURIs(request))
                    url = (yield self.canonicalURL(request))
                    opaque = url in fbset
                    self.writeDeadProperty(caldavxml.ScheduleCalendarTransp(caldavxml.Opaque() if opaque else caldavxml.Transparent()))

        result = (yield super(CalDAVResource, self).readProperty(property, request))
        returnValue(result)

    @inlineCallbacks
    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement), (
            "%r is not a WebDAVElement instance" % (property,)
        )

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
                    (caldav_namespace, "valid-calendar-data"),
                    description="Invalid property"
                ))

        elif property.qname() == (caldav_namespace, "schedule-calendar-transp"):
            if not self.isCalendarCollection():
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Property %s may only be set on calendar collection." % (property,)
                ))

            # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
            principal = (yield self.ownerPrincipal(request))
            
            # Map owner to their inbox
            inboxURL = principal.scheduleInboxURL()
            if inboxURL:
                inbox = (yield request.locateResource(inboxURL))
                myurl = (yield self.canonicalURL(request))
                inbox.processFreeBusyCalendar(myurl, property.children[0] == caldavxml.Opaque())

        result = (yield super(CalDAVResource, self).writeProperty(property, request))
        returnValue(result)

    def writeDeadProperty(self, property):
        val = super(CalDAVResource, self).writeDeadProperty(property)

        return val


    ##
    # ACL
    ##

    # FIXME: Perhaps this is better done in authorize() instead.
    @inlineCallbacks
    def accessControlList(self, request, *args, **kwargs):
        acls = (yield super(CalDAVResource, self).accessControlList(request, *args, **kwargs))

        # Look for private events access classification
        if self.hasDeadProperty(TwistedCalendarAccessProperty):
            access = self.readDeadProperty(TwistedCalendarAccessProperty)
            if access.getValue() in (Component.ACCESS_PRIVATE, Component.ACCESS_CONFIDENTIAL, Component.ACCESS_RESTRICTED,):
                # Need to insert ACE to prevent non-owner principals from seeing this resource
                owner = (yield self.owner(request))
                newacls = []
                if access.getValue() == Component.ACCESS_PRIVATE:
                    newacls.extend(config.AdminACEs)
                    newacls.extend(config.ReadACEs)
                    newacls.append(davxml.ACE(
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
                    ))
                else:
                    newacls.extend(config.AdminACEs)
                    newacls.extend(config.ReadACEs)
                    newacls.append(davxml.ACE(
                        davxml.Invert(
                            davxml.Principal(owner),
                        ),
                        davxml.Deny(
                            davxml.Privilege(
                                davxml.Write(),
                            ),
                        ),
                        davxml.Protected(),
                    ))
                newacls.extend(acls.children)

                acls = davxml.ACL(*newacls)
 
        returnValue(acls)

    def owner(self, request):
        """
        Return the DAV:owner property value (MUST be a DAV:href or None).
        """
        
        def _gotParent(parent):
            if parent and isinstance(parent, CalDAVResource):
                return parent.owner(request)

        d = self.locateParent(request, request.urlForResource(self))
        d.addCallback(_gotParent)
        return d

    def ownerPrincipal(self, request):
        """
        Return the DAV:owner property value (MUST be a DAV:href or None).
        """
        def _gotParent(parent):
            if parent and isinstance(parent, CalDAVResource):
                return parent.ownerPrincipal(request)

        d = self.locateParent(request, request.urlForResource(self))
        d.addCallback(_gotParent)
        return d

    def isOwner(self, request, adminprincipals=False, readprincipals=False):
        """
        Determine whether the DAV:owner of this resource matches the currently authorized principal
        in the request. Optionally test for admin or read principals and allow those.
        """

        def _gotOwner(owner):
            current = self.currentPrincipal(request)
            if davxml.Principal(owner) == current:
                return True
            
            if adminprincipals:
                for principal in config.AdminPrincipals:
                    if davxml.Principal(davxml.HRef(principal)) == current:
                        return True

            if readprincipals:
                for principal in config.AdminPrincipals:
                    if davxml.Principal(davxml.HRef(principal)) == current:
                        return True
                
            return False

        d = self.owner(request)
        d.addCallback(_gotOwner)
        return d

    ##
    # DAVResource
    ##

    def displayName(self):
        if 'record' in dir(self):
            if self.record.fullName:
                return self.record.fullName
            elif self.record.shortNames:
                return self.record.shortNames[0]
            else:
                return super(DAVResource, self).displayName()
        else:
            return super(DAVResource, self).displayName()

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
        except HTTPError, e:
            assert e.response.code == responsecode.NOT_FOUND, (
                "Unexpected response code: %s" % (e.response.code,)
            )
            return False
        return bool(resourcetype.childrenOfType(collectiontype))

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

    @inlineCallbacks
    def deletedCalendar(self, request):
        """
        Calendar has been deleted. Need to do some extra clean-up.

        @param request:
        @type request:
        """
        
        # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
        principal = (yield self.ownerPrincipal(request))
        inboxURL = principal.scheduleInboxURL()
        if inboxURL:
            inbox = (yield request.locateResource(inboxURL))
            inbox.processFreeBusyCalendar(request.path, False)

    @inlineCallbacks
    def movedCalendar(self, request, defaultCalendar, destination, destination_uri):
        """
        Calendar has been moved. Need to do some extra clean-up.
        """
        
        # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
        principal = (yield self.ownerPrincipal(request))
        inboxURL = principal.scheduleInboxURL()
        if inboxURL:
            (_ignore_scheme, _ignore_host, destination_path, _ignore_query, _ignore_fragment) = urlsplit(normalizeURL(destination_uri))

            inbox = (yield request.locateResource(inboxURL))
            inbox.processFreeBusyCalendar(request.path, False)
            inbox.processFreeBusyCalendar(destination_uri, destination.isCalendarOpaque())
            
            # Adjust the default calendar setting if necessary
            if defaultCalendar:
                yield inbox.writeProperty(caldavxml.ScheduleDefaultCalendarURL(davxml.HRef(destination_path)), request)               

    def isCalendarOpaque(self):
        
        assert self.isCalendarCollection()
        
        if self.hasDeadProperty((caldav_namespace, "schedule-calendar-transp")):
            property = self.readDeadProperty((caldav_namespace, "schedule-calendar-transp"))
            return property.children[0] == caldavxml.Opaque()
        else:
            return False

    @inlineCallbacks
    def isDefaultCalendar(self, request):
        
        assert self.isCalendarCollection()
        
        # Not allowed to delete the default calendar
        principal = (yield self.ownerPrincipal(request))
        inboxURL = principal.scheduleInboxURL()
        if inboxURL:
            inbox = (yield request.locateResource(inboxURL))
            default = (yield inbox.readProperty((caldav_namespace, "schedule-default-calendar-URL"), request))
            if default and len(default.children) == 1:
                defaultURL = normalizeURL(str(default.children[0]))
                myURL = (yield self.canonicalURL(request))
                returnValue(defaultURL == myURL)

        returnValue(False)

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

    def iCalendarAddressDoNormalization(self, ical):
        """
        Normalize calendar user addresses in the supplied iCalendar object into their
        urn:uuid form where possible. Also reset CN= property and add EMAIL property.

        @param ical: calendar object to normalize.
        @type ical: L{Component}
        """

        def lookupFunction(cuaddr):
            principal = self.principalForCalendarUserAddress(cuaddr)
            if principal is None:
                return (None, None, None)
            else:
                return (principal.record.fullName.decode("utf-8"),
                    principal.record.guid,
                    principal.record.calendarUserAddresses)

        ical.normalizeCalendarUserAddresses(lookupFunction)


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
        if self.isCollection():
            # Only allowed on collections
            result.append(davxml.Report(caldavxml.FreeBusyQuery(),))
        if self.isPseudoCalendarCollection() and config.EnableSyncReport:
            # Only allowed on calendar/inbox collections
            result.append(davxml.Report(SyncCollection(),))
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

    @inlineCallbacks
    def canonicalURL(self, request):
        
        if not hasattr(self, "_canonical_url"):
    
            myurl = request.urlForResource(self)
            _ignore_scheme, _ignore_host, path, _ignore_query, _ignore_fragment = urlsplit(normalizeURL(myurl))
            lastpath = path.split("/")[-1]
            
            parent = (yield request.locateResource(parentForURL(myurl)))
            canonical_parent = (yield parent.canonicalURL(request))
            self._canonical_url = joinURL(canonical_parent, lastpath)

        returnValue(self._canonical_url)

    ##
    # Quota
    ##

    def hasQuotaRoot(self, request):
        """
        Quota root only ever set on calendar homes.
        """
        return False
    
    def quotaRoot(self, request):
        """
        Quota root only ever set on calendar homes.
        """
        return None

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
        (caldav_namespace, "calendar-user-type"       ),
        (calendarserver_namespace, "calendar-proxy-read-for"  ),
        (calendarserver_namespace, "calendar-proxy-write-for" ),
        (calendarserver_namespace, "auto-schedule" ),
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

    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname

        if namespace == caldav_namespace:
            if name == "calendar-home-set":
                returnValue(caldavxml.CalendarHomeSet(
                    *[davxml.HRef(url) for url in self.calendarHomeURLs()]
                ))

            elif name == "calendar-user-address-set":
                returnValue(caldavxml.CalendarUserAddressSet(
                    *[davxml.HRef(uri) for uri in self.calendarUserAddresses()]
                ))

            elif name == "schedule-inbox-URL":
                url = self.scheduleInboxURL()
                if url is None:
                    returnValue(None)
                else:
                    returnValue(caldavxml.ScheduleInboxURL(davxml.HRef(url)))

            elif name == "schedule-outbox-URL":
                url = self.scheduleOutboxURL()
                if url is None:
                    returnValue(None)
                else:
                    returnValue(caldavxml.ScheduleOutboxURL(davxml.HRef(url)))

            elif name == "calendar-user-type":
                returnValue(caldavxml.CalendarUserType(self.record.getCUType()))

        elif namespace == calendarserver_namespace:
            if name == "dropbox-home-URL" and config.EnableDropBox:
                url = self.dropboxURL()
                if url is None:
                    returnValue(None)
                else:
                    returnValue(customxml.DropBoxHomeURL(davxml.HRef(url)))

            elif name == "calendar-proxy-read-for":
                results = (yield self.proxyFor(False))
                returnValue(customxml.CalendarProxyReadFor(
                    *[davxml.HRef(principal.principalURL()) for principal in results]
                ))

            elif name == "calendar-proxy-write-for":
                results = (yield self.proxyFor(True))
                returnValue(customxml.CalendarProxyWriteFor(
                    *[davxml.HRef(principal.principalURL()) for principal in results]
                ))

            elif name == "auto-schedule":
                autoSchedule = self.getAutoSchedule()
                returnValue(customxml.AutoSchedule("true" if autoSchedule else "false"))

        result = (yield super(CalendarPrincipalResource, self).readProperty(property, request))
        returnValue(result)

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
    # Quota
    ##

    def hasQuotaRoot(self, request):
        """
        Quota root only ever set on calendar homes.
        """
        return False
    
    def quotaRoot(self, request):
        """
        Quota root only ever set on calendar homes.
        """
        return None


class AuthenticationWrapper(SuperAuthenticationWrapper):

    """ AuthenticationWrapper implementation which allows overriding
        credentialFactories on a per-resource-path basis """

    def __init__(self, resource, portal, credentialFactories, loginInterfaces,
        overrides=None):

        super(AuthenticationWrapper, self).__init__(resource, portal,
            credentialFactories, loginInterfaces)

        self.overrides = {}
        if overrides:
            for path, factories in overrides.iteritems():
                self.overrides[path] = dict([(factory.scheme, factory)
                    for factory in factories])

    def hook(self, req):
        """ Uses the default credentialFactories unless the request is for
            one of the overridden paths """

        super(AuthenticationWrapper, self).hook(req)

        factories = self.overrides.get(req.path.rstrip("/"),
            self.credentialFactories)
        req.credentialFactories = factories


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


