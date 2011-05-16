# -*- test-case-name: twistedcaldav.test.test_resource,twistedcaldav.test.test_wrapping -*-
##
# Copyright (c) 2005-2011 Apple Inc. All rights reserved.
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
    "isAddressBookCollectionResource",
]

from urlparse import urlsplit
import urllib
import uuid


from zope.interface import implements

from twext.python.log import LoggingMixIn
from twext.web2.dav.davxml import SyncCollection
from twext.web2.dav.http import ErrorResponse

from twisted.internet.defer import succeed, maybeDeferred, fail
from twisted.internet.defer import inlineCallbacks, returnValue

from twext.web2 import responsecode, http, http_headers
from twext.web2.dav import davxml
from twext.web2.dav.auth import AuthenticationWrapper as SuperAuthenticationWrapper
from twext.web2.dav.davxml import dav_namespace
from twext.web2.dav.idav import IDAVPrincipalCollectionResource
from twext.web2.dav.resource import AccessDeniedError, DAVPrincipalCollectionResource,\
    davPrivilegeSet
from twext.web2.dav.resource import TwistedACLInheritable
from twext.web2.dav.util import joinURL, parentForURL, normalizeURL,\
    unimplemented
from twext.web2.http import HTTPError, RedirectResponse, StatusResponse, Response
from twext.web2.http_headers import MimeType
from twext.web2.stream import MemoryStream

from twistedcaldav import caldavxml, customxml
from twistedcaldav import carddavxml
from twistedcaldav.cache import PropfindCacheMixin, DisabledCacheNotifier,\
    CacheStoreNotifier
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.datafilters.peruserdata import PerUserDataFilter
from twistedcaldav.datafilters.privateevents import PrivateEventFilter
from twistedcaldav.directory.internal import InternalDirectoryRecord
from twistedcaldav.extensions import DAVResource, DAVPrincipalResource,\
    PropertyNotFoundError, DAVResourceWithChildrenMixin
from twistedcaldav.ical import Component

from twistedcaldav.ical import allowedComponents
from twistedcaldav.icaldav import ICalDAVResource, ICalendarPrincipalResource
from twistedcaldav.linkresource import LinkResource
from twistedcaldav.notify import (
    getPubSubConfiguration, getPubSubXMPPURI, getPubSubHeartbeatURI,
    getPubSubAPSConfiguration,
)
from twistedcaldav.sharing import SharedCollectionMixin, SharedHomeMixin
from twistedcaldav.vcard import Component as vComponent

from txdav.common.icommondatastore import InternalDataStoreError, \
    SyncTokenValidException

##
# Sharing Conts
##
SHARE_ACCEPT_STATE_NEEDS_ACTION = "0"
SHARE_ACCEPT_STATE_ACCEPTED = "1"
SHARE_ACCEPT_STATE_DECLINED = "2"
SHARE_ACCEPT_STATE_DELETED = "-1"

shareAccpetStates = {}
shareAccpetStates[SHARE_ACCEPT_STATE_NEEDS_ACTION] = "NEEDS-ACTION"
shareAccpetStates[SHARE_ACCEPT_STATE_ACCEPTED] = "ACCEPTED"
shareAccpetStates[SHARE_ACCEPT_STATE_DECLINED] = "DECLINED"
shareAccpetStates[SHARE_ACCEPT_STATE_DELETED] = "DELETED"

shareAcceptStatesByXML = {}
shareAcceptStatesByXML["NEEDS-ACTION"] = customxml.InviteStatusNoResponse()
shareAcceptStatesByXML["ACCEPTED"] = customxml.InviteStatusAccepted()
shareAcceptStatesByXML["DECLINED"] = customxml.InviteStatusDeclined()
shareAcceptStatesByXML["DELETED"] = customxml.InviteStatusDeleted()

class CalDAVComplianceMixIn(object):
    def davComplianceClasses(self):
        return (
            tuple(super(CalDAVComplianceMixIn, self).davComplianceClasses())
            + config.CalDAVComplianceClasses
        )

class ReadOnlyResourceMixIn (object):
    """
    Read only resource.
    """

    def writeProperty(self, property, request):
        raise HTTPError(self.readOnlyResponse)

    def http_ACL(self, request):       return responsecode.FORBIDDEN
    def http_DELETE(self, request):    return responsecode.FORBIDDEN
    def http_MKCOL(self, request):     return responsecode.FORBIDDEN
    def http_MOVE(self, request):      return responsecode.FORBIDDEN
    def http_PROPPATCH(self, request): return responsecode.FORBIDDEN
    def http_PUT(self, request):       return responsecode.FORBIDDEN

    def http_MKCALENDAR(self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (caldav_namespace, "calendar-collection-location-ok"),
            "Resource is read-only",
        )

class ReadOnlyNoCopyResourceMixIn (ReadOnlyResourceMixIn):
    """
    Read only resource that disallows COPY.
    """

    def http_COPY(self, request): return responsecode.FORBIDDEN

def _calendarPrivilegeSet ():
    edited = False

    top_supported_privileges = []

    for supported_privilege in davPrivilegeSet.childrenOfType(davxml.SupportedPrivilege):
        all_privilege = supported_privilege.childOfType(davxml.Privilege)
        if isinstance(all_privilege.children[0], davxml.All):
            all_description = supported_privilege.childOfType(davxml.Description)
            all_supported_privileges = []
            for all_supported_privilege in supported_privilege.childrenOfType(davxml.SupportedPrivilege):
                read_privilege = all_supported_privilege.childOfType(davxml.Privilege)
                if isinstance(read_privilege.children[0], davxml.Read):
                    read_description = all_supported_privilege.childOfType(davxml.Description)
                    read_supported_privileges = list(all_supported_privilege.childrenOfType(davxml.SupportedPrivilege))
                    read_supported_privileges.append(
                        davxml.SupportedPrivilege(
                            davxml.Privilege(caldavxml.ReadFreeBusy()),
                            davxml.Description("allow free busy report query", **{"xml:lang": "en"}),
                        )
                    )
                    all_supported_privileges.append(
                        davxml.SupportedPrivilege(read_privilege, read_description, *read_supported_privileges)
                    )
                    edited = True
                else:
                    all_supported_privileges.append(all_supported_privilege)
            top_supported_privileges.append(
                davxml.SupportedPrivilege(all_privilege, all_description, *all_supported_privileges)
            )
        else:
            top_supported_privileges.append(supported_privilege)

    assert edited, "Structure of davPrivilegeSet changed in a way that I don't know how to extend for calendarPrivilegeSet"

    return davxml.SupportedPrivilegeSet(*top_supported_privileges)

calendarPrivilegeSet = _calendarPrivilegeSet()

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


class CalDAVResource (
        CalDAVComplianceMixIn, SharedCollectionMixin,
        DAVResourceWithChildrenMixin, DAVResource, LoggingMixIn
    ):
    """
    CalDAV resource.

    Extends L{DAVResource} to provide CalDAV functionality.
    """
    implements(ICalDAVResource)

    ##
    # HTTP
    ##

    def render(self, request):

        if not self.exists():
            return responsecode.NOT_FOUND

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


    _associatedTransaction = None
    _transactionError = False

    def associateWithTransaction(self, transaction):
        """
        Associate this resource with a L{txdav.caldav.idav.ITransaction}; when this
        resource (or any of its children) are rendered successfully, commit the
        transaction.  Otherwise, abort the transaction.

        @param transaction: the transaction to associate this resource and its
            children with.

        @type transaction: L{txdav.caldav.idav.ITransaction} 
        """
        # FIXME: needs to reject association with transaction if it's already
        # got one (resources associated with a transaction are not reusable)
        self._associatedTransaction = transaction


    def propagateTransaction(self, otherResource):
        """
        Propagate the transaction associated with this resource to another
        resource (which should ostensibly be a child resource).

        @param otherResource: Another L{CalDAVResource}, usually one being
            constructed as a child of this one.

        @type otherResource: L{CalDAVResource} (or a subclass thereof)
        """
        if not self._associatedTransaction:
            raise RuntimeError("No associated transaction to propagate")
        otherResource.associateWithTransaction(self._associatedTransaction)


    def transactionError(self):
        self._transactionError = True


    @inlineCallbacks
    def renderHTTP(self, request, transaction=None):
        """
        Override C{renderHTTP} to commit the transaction when the resource is
        successfully rendered.

        @param request: the request to generate a response for.
        @type request: L{twext.web2.iweb.IRequest}
        @param transaction: optional transaction to use instead of associated transaction
        @type transaction: L{txdav.caldav.idav.ITransaction}
        """
        result = yield super(CalDAVResource, self).renderHTTP(request)
        if transaction is None:
            transaction = self._associatedTransaction
        if transaction is not None:
            if self._transactionError:
                yield transaction.abort()
            else:
                yield transaction.commit()
        returnValue(result)


    # Begin transitional new-store resource interface:

    def copyDeadPropertiesTo(self, other):
        """
        Copy this resource's dead properties to another resource.  This requires
        that the new resource have a back-end store.

        @param other: a resource to copy all properites to.
        @type other: subclass of L{CalDAVResource}
        """
        self.newStoreProperties().update(other.newStoreProperties())


    def newStoreProperties(self):
        """
        Return an L{IMapping} that represents properties.  Only available on
        new-storage objects.
        """
        raise NotImplementedError("%s does not implement newStoreProperties" %
                                  (self,))
        
    
    def storeRemove(self, *a, **kw):
        """
        Remove this resource from storage.
        """
        raise NotImplementedError("%s does not implement storeRemove" %
                                  (self,))


    def storeStream(self, stream):
        """
        Store the content of the stream in this resource, as it would via a PUT.

        @param stream: The stream containing the data to be stored.
        @type stream: L{IStream}
        
        @return: a L{Deferred} which fires with an HTTP response.
        @rtype: L{Deferred}
        """
        raise NotImplementedError("%s does not implement storeStream"  %
                                  (self,))

    # End transitional new-store interface 

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

    def liveProperties(self):
        baseProperties = (
            davxml.Owner.qname(),               # Private Events needs this but it is also OK to return empty
        )
        
        if self.isPseudoCalendarCollection():
            baseProperties += (
                caldavxml.SupportedCalendarComponentSet.qname(),
                caldavxml.SupportedCalendarData.qname(),
                customxml.GETCTag.qname(),
            )
            if config.MaxResourceSize:
                baseProperties += (
                    caldavxml.MaxResourceSize.qname(),
                )
            if config.MaxAttendeesPerInstance:
                baseProperties += (
                    caldavxml.MaxAttendeesPerInstance.qname(),
                )

        if self.isCalendarCollection():
            baseProperties += (
                davxml.ResourceID.qname(),
                customxml.PubSubXMPPPushKeyProperty.qname(),
            )

        if self.isAddressBookCollection():
            baseProperties += (
                davxml.ResourceID.qname(),
                carddavxml.SupportedAddressData.qname(),
                customxml.GETCTag.qname(),
                customxml.PubSubXMPPPushKeyProperty.qname(),
            )
            if config.MaxResourceSize:
                baseProperties += (
                    carddavxml.MaxResourceSize.qname(),
                )

        if hasattr(self, "scheduleTag") and self.scheduleTag:
            baseProperties += (
                caldavxml.ScheduleTag.qname(),
            )
            
        if config.EnableSyncReport and (davxml.Report(SyncCollection(),) in self.supportedReports()):
            baseProperties += (davxml.SyncToken.qname(),)
            
        if config.EnableAddMember and (self.isCalendarCollection() or self.isAddressBookCollection()):
            baseProperties += (davxml.AddMember.qname(),)
            
        if config.Sharing.Enabled:
            if config.Sharing.Calendars.Enabled and self.isCalendarCollection():
                baseProperties += (
                    customxml.Invite.qname(),
                    customxml.AllowedSharingModes.qname(),
                    customxml.SharedURL.qname(),
                )

            elif config.Sharing.AddressBooks.Enabled and self.isAddressBookCollection():
                baseProperties += (
                    customxml.Invite.qname(),
                    customxml.AllowedSharingModes.qname(),
                )
                
        return super(CalDAVResource, self).liveProperties() + baseProperties

    supportedCalendarComponentSet = caldavxml.SupportedCalendarComponentSet(
        *[caldavxml.CalendarComponent(name=item) for item in allowedComponents]
    )

    def isShadowableProperty(self, qname):
        """
        Shadowable properties are ones on shared resources where a "default" exists until
        a user overrides with their own value.
        """
        return qname in (
            caldavxml.CalendarDescription.qname(),
            caldavxml.CalendarTimeZone.qname(),
            carddavxml.AddressBookDescription.qname(),
        )

    def isGlobalProperty(self, qname):
        """
        A global property is one that is the same for all users.
        """
        if qname in self.liveProperties():
            if qname in (
                davxml.DisplayName.qname(),
                customxml.Invite.qname(),
            ):
                return False
            else:
                return True
        else:
            return False

    @inlineCallbacks
    def hasProperty(self, property, request):
        """
        Need to special case schedule-calendar-transp for backwards compatability.
        """
        
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        isvirt = self.isVirtualShare()
        if isvirt:
            if self.isShadowableProperty(qname):
                ownerPrincipal = (yield self.resourceOwnerPrincipal(request))
                p = self.deadProperties().contains(qname, uid=ownerPrincipal.principalUID())
                if p:
                    returnValue(p)
                
            elif (not self.isGlobalProperty(qname)):
                ownerPrincipal = (yield self.resourceOwnerPrincipal(request))
                p = self.deadProperties().contains(qname, uid=ownerPrincipal.principalUID())
                returnValue(p)

        res = (yield self._hasGlobalProperty(property, request))
        returnValue(res)

    def _hasGlobalProperty(self, property, request):
        """
        Need to special case schedule-calendar-transp for backwards compatability.
        """
        
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        # Force calendar collections to always appear to have the property
        if qname == caldavxml.ScheduleCalendarTransp.qname() and self.isCalendarCollection():
            return succeed(True)
        else:
            return super(CalDAVResource, self).hasProperty(property, request)

    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        isvirt = self.isVirtualShare()

        if self.isCalendarCollection() or self.isAddressBookCollection():

            # Push notification DAV property "pushkey"
            if qname == customxml.PubSubXMPPPushKeyProperty.qname():

                # FIXME: is there a better way to get back to the associated
                # datastore object?
                dataObject = None
                if hasattr(self, "_newStoreObject"):
                    dataObject = getattr(self, "_newStoreObject")
                if dataObject:
                    label = "collection" if isvirt else "default"
                    nodeName = (yield dataObject.nodeName(label=label))
                    if nodeName:
                        propVal = customxml.PubSubXMPPPushKeyProperty(nodeName)
                        returnValue(propVal)

                returnValue(customxml.PubSubXMPPPushKeyProperty())


        if isvirt:
            if self.isShadowableProperty(qname):
                ownerPrincipal = (yield self.resourceOwnerPrincipal(request))
                try:
                    p = self.deadProperties().get(qname, uid=ownerPrincipal.principalUID())
                    returnValue(p)
                except PropertyNotFoundError:
                    pass
                
            elif (not self.isGlobalProperty(qname)):
                ownerPrincipal = (yield self.resourceOwnerPrincipal(request))
                p = self.deadProperties().get(qname, uid=ownerPrincipal.principalUID())
                returnValue(p)

        res = (yield self._readGlobalProperty(qname, property, request))
        returnValue(res)

    @inlineCallbacks
    def _readGlobalProperty(self, qname, property, request):

        if qname == davxml.Owner.qname():
            owner = (yield self.owner(request))
            returnValue(davxml.Owner(owner))

        elif qname == davxml.ResourceType.qname():
            returnValue(self.resourceType())

        elif qname == davxml.ResourceID.qname():
            returnValue(davxml.ResourceID(davxml.HRef.fromString(self.resourceID())))

        elif qname == customxml.GETCTag.qname() and (
            self.isPseudoCalendarCollection() or self.isAddressBookCollection()
        ):
            returnValue(customxml.GETCTag.fromString((yield self.getInternalSyncToken())))

        elif qname == davxml.SyncToken.qname() and config.EnableSyncReport and (
            davxml.Report(SyncCollection(),) in self.supportedReports()
        ):
            returnValue(davxml.SyncToken.fromString((yield self.getSyncToken())))

        elif qname == davxml.AddMember.qname() and config.EnableAddMember and (
            self.isCalendarCollection() or self.isAddressBookCollection()
        ):
            url = (yield self.canonicalURL(request))
            returnValue(davxml.AddMember(davxml.HRef.fromString(url + "/;add-member")))

        elif qname == caldavxml.SupportedCalendarComponentSet.qname():
            # CalDAV-access-09, section 5.2.3
            if self.hasDeadProperty(qname):
                returnValue(self.readDeadProperty(qname))
            returnValue(self.supportedCalendarComponentSet)

        elif qname == caldavxml.SupportedCalendarData.qname():
            # CalDAV-access-09, section 5.2.4
            returnValue(caldavxml.SupportedCalendarData(
                caldavxml.CalendarData(**{
                    "content-type": "text/calendar",
                    "version"     : "2.0",
                }),
            ))

        elif qname == caldavxml.MaxResourceSize.qname():
            # CalDAV-access-15, section 5.2.5
            if config.MaxResourceSize:
                returnValue(caldavxml.MaxResourceSize.fromString(
                    str(config.MaxResourceSize)
                ))

        elif qname == caldavxml.MaxAttendeesPerInstance.qname():
            # CalDAV-access-15, section 5.2.9
            if config.MaxAttendeesPerInstance:
                returnValue(caldavxml.MaxAttendeesPerInstance.fromString(
                    str(config.MaxAttendeesPerInstance)
                ))

        elif qname == caldavxml.ScheduleTag.qname():
            # CalDAV-scheduling
            if hasattr(self, "scheduleTag") and self.scheduleTag:
                returnValue(caldavxml.ScheduleTag.fromString(
                    self.scheduleTag
                ))

        elif qname == caldavxml.ScheduleCalendarTransp.qname():
            # For backwards compatibility, if the property does not exist we need to create
            # it and default to the old free-busy-set value.
            if self.isCalendarCollection() and not self.hasDeadProperty(property):
                # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
                principal = (yield self.resourceOwnerPrincipal(request))
                fbset = (yield principal.calendarFreeBusyURIs(request))
                url = (yield self.canonicalURL(request))
                opaque = url in fbset
                self.writeDeadProperty(caldavxml.ScheduleCalendarTransp(caldavxml.Opaque() if opaque else caldavxml.Transparent()))

        elif qname == carddavxml.SupportedAddressData.qname():
            # CardDAV, section 6.2.2
            returnValue(carddavxml.SupportedAddressData(
                carddavxml.AddressDataType(**{
                    "content-type": "text/vcard",
                    "version"     : "3.0",
                }),
            ))

        elif qname == carddavxml.MaxResourceSize.qname():
            # CardDAV, section 6.2.3
            if config.MaxResourceSize:
                returnValue(carddavxml.MaxResourceSize.fromString(
                    str(config.MaxResourceSize)
                ))

        elif qname == customxml.Invite.qname():
            if config.Sharing.Enabled and (
                config.Sharing.Calendars.Enabled and self.isCalendarCollection() or 
                config.Sharing.AddressBooks.Enabled and self.isAddressBookCollection()
            ):
                result = (yield self.inviteProperty(request))
                returnValue(result)

        elif qname == customxml.AllowedSharingModes.qname():
            if config.Sharing.Enabled and config.Sharing.Calendars.Enabled and self.isCalendarCollection():
                returnValue(customxml.AllowedSharingModes(customxml.CanBeShared()))
            elif config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled and self.isAddressBookCollection():
                returnValue(customxml.AllowedSharingModes(customxml.CanBeShared()))

        elif qname == customxml.SharedURL.qname():
            isvirt = self.isVirtualShare()
            
            if isvirt:
                returnValue(customxml.SharedURL(davxml.HRef.fromString(self._share.hosturl)))
            else:
                returnValue(None)

        result = (yield super(CalDAVResource, self).readProperty(property, request))
        returnValue(result)

    @inlineCallbacks
    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement), (
            "%r is not a WebDAVElement instance" % (property,)
        )
        
        # Per-user Dav props currently only apply to a sharee's copy of a calendar
        isvirt = self.isVirtualShare()
        if isvirt and (self.isShadowableProperty(property.qname()) or (not self.isGlobalProperty(property.qname()))):
            yield self._preProcessWriteProperty(property, request)
            ownerPrincipal = (yield self.resourceOwnerPrincipal(request))
            p = self.deadProperties().set(property, uid=ownerPrincipal.principalUID())
            returnValue(p)
 
        res = (yield self._writeGlobalProperty(property, request))
        returnValue(res)

    @inlineCallbacks
    def _preProcessWriteProperty(self, property, request):
        if property.qname() == caldavxml.SupportedCalendarComponentSet.qname():
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
        elif property.qname() == caldavxml.CalendarTimeZone.qname():
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

        elif property.qname() == caldavxml.ScheduleCalendarTransp.qname():
            if not self.isCalendarCollection():
                raise HTTPError(StatusResponse(
                    responsecode.FORBIDDEN,
                    "Property %s may only be set on calendar collection." % (property,)
                ))

            # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
            principal = (yield self.resourceOwnerPrincipal(request))
            
            # Map owner to their inbox
            inboxURL = principal.scheduleInboxURL()
            if inboxURL:
                inbox = (yield request.locateResource(inboxURL))
                myurl = (yield self.canonicalURL(request))
                inbox.processFreeBusyCalendar(myurl, property.children[0] == caldavxml.Opaque())

    @inlineCallbacks
    def _writeGlobalProperty(self, property, request):

        yield self._preProcessWriteProperty(property, request)

        if property.qname() == davxml.ResourceType.qname():
            if self.isCalendarCollection() or self.isAddressBookCollection():
                sawShare = [child for child in property.children if child.qname() == (calendarserver_namespace, "shared-owner")]
                if sawShare:
                    if self.isCalendarCollection() and not (config.Sharing.Enabled and config.Sharing.Calendars.Enabled):
                        raise HTTPError(StatusResponse(
                            responsecode.FORBIDDEN,
                            "Cannot create shared calendars on this server.",
                        ))
                    elif self.isAddressBookCollection() and not (config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled):
                        raise HTTPError(StatusResponse(
                            responsecode.FORBIDDEN,
                            "Cannot create shared address books on this server.",
                        ))

                # Check if adding or removing share
                shared = (yield self.isShared(request))
                for child in property.children:
                    if child.qname() == davxml.Collection.qname():
                        break
                else:
                    raise HTTPError(StatusResponse(
                        responsecode.FORBIDDEN,
                        "Protected property %s may not be set." % (property.sname(),)
                    ))
                for child in property.children:
                    if self.isCalendarCollection and child.qname() == caldavxml.Calendar.qname() or \
                       self.isAddressBookCollection and child.qname() == carddavxml.AddressBook.qname():
                        break
                else:
                    raise HTTPError(StatusResponse(
                        responsecode.FORBIDDEN,
                        "Protected property %s may not be set." % (property.sname(),)
                    ))
                sawShare = [child for child in property.children if child.qname() == (calendarserver_namespace, "shared-owner")]
                if not shared and sawShare:
                    # Owner is trying to share a collection
                    self.upgradeToShare()
                elif shared and not sawShare:
                    # Remove share
                    yield self.downgradeFromShare(request)
                returnValue(None)
            else:
                # resourcetype cannot be changed but we will allow it to be set to the same value
                currentType = self.resourceType()
                if currentType == property:
                    returnValue(None)

        result = (yield super(CalDAVResource, self).writeProperty(property, request))
        returnValue(result)

    ##
    # ACL
    ##

    def _get_accessMode(self):
        """
        Needed as a stub because only calendar object resources use this but we need to do ACL
        determination on the generic CalDAVResource for now.
        """
        return ""

    def _set_accessMode(self, value):
        raise NotImplementedError

    accessMode = property(_get_accessMode, _set_accessMode)

    # FIXME: Perhaps this is better done in authorize() instead.
    @inlineCallbacks
    def accessControlList(self, request, *args, **kwargs):

        acls = None
        isvirt = self.isVirtualShare()
        if isvirt:
            acls = (yield self.shareeAccessControlList(request, *args, **kwargs))

        if acls is None:
            acls = (yield super(CalDAVResource, self).accessControlList(request, *args, **kwargs))

        # Look for private events access classification
        if self.accessMode:
            if self.accessMode in (Component.ACCESS_PRIVATE, Component.ACCESS_CONFIDENTIAL, Component.ACCESS_RESTRICTED,):
                # Need to insert ACE to prevent non-owner principals from seeing this resource
                owner = (yield self.owner(request))
                newacls = []
                if self.accessMode == Component.ACCESS_PRIVATE:
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

    @inlineCallbacks
    def owner(self, request):
        """
        Return the DAV:owner property value (MUST be a DAV:href or None).
        """

        isVirt = self.isVirtualShare()
        if isVirt:
            parent = (yield self.locateParent(request, self._share.hosturl))
        else:
            parent = (yield self.locateParent(request, request.urlForResource(self)))
        if parent and isinstance(parent, CalDAVResource):
            result = (yield parent.owner(request))
            returnValue(result)
        else:
            returnValue(None)

    @inlineCallbacks
    def ownerPrincipal(self, request):
        """
        Return the DAV:owner property value (MUST be a DAV:href or None).
        """
        isVirt = self.isVirtualShare()
        if isVirt:
            parent = (yield self.locateParent(request, self._share.hosturl))
        else:
            parent = (yield self.locateParent(request, request.urlForResource(self)))
        if parent and isinstance(parent, CalDAVResource):
            result = (yield parent.ownerPrincipal(request))
            returnValue(result)
        else:
            returnValue(None)


    @inlineCallbacks
    def resourceOwnerPrincipal(self, request):
        """
        This is the owner of the resource based on the URI used to access it. For a shared
        collection it will be the sharee, otherwise it will be the regular the ownerPrincipal.
        """

        isVirt = self.isVirtualShare()
        if isVirt:
            returnValue(self._shareePrincipal)
        else:
            parent = (yield self.locateParent(
                request, request.urlForResource(self)
            ))
        if parent and isinstance(parent, CalDAVResource):
            result = (yield parent.resourceOwnerPrincipal(request))
            returnValue(result)
        else:
            returnValue(None)


    @inlineCallbacks
    def isOwner(self, request):
        """
        Determine whether the DAV:owner of this resource matches the currently
        authorized principal in the request, or if the user is a read-only or
        read-write administrator.
        """
        current = self.currentPrincipal(request)
        if current in config.AllAdminPrincipalObjects:
            returnValue(True)
        if davxml.Principal((yield self.owner(request))) == current:
            returnValue(True)
        returnValue(False)


    ##
    # DAVResource
    ##

    def displayName(self):
        if self.isAddressBookCollection() and not self.hasDeadProperty((davxml.dav_namespace, "displayname")):
            return None
        
        if 'record' in dir(self):
            if self.record.fullName:
                return self.record.fullName
            elif self.record.shortNames:
                return self.record.shortNames[0]
            else:
                return super(DAVResource, self).displayName()
        else:
            result = super(DAVResource, self).displayName()
            if not result:
                result = self.name()
            return result

    def name(self):
        return None

    def resourceID(self):
        if not self.hasDeadProperty(davxml.ResourceID.qname()):
            uuidval = uuid.uuid4()
            self.writeDeadProperty(davxml.ResourceID(davxml.HRef.fromString(uuidval.urn)))
        return str(self.readDeadProperty(davxml.ResourceID.qname()).children[0])

    ##
    # CalDAV
    ##

    def isCalendarCollection(self):
        """
        See L{ICalDAVResource.isCalendarCollection}.
        """
        return self.isSpecialCollection(caldavxml.Calendar)

    def isAddressBookCollection(self):
        """
        See L{ICalDAVResource.isAddressBookCollection}.
        """
        return self.isSpecialCollection(carddavxml.AddressBook)

    def isNotificationCollection(self):
        """
        See L{ICalDAVResource.isNotificationCollection}.
        """
        return self.isSpecialCollection(customxml.Notification)

    def isDirectoryBackedAddressBookCollection(self):       # ATM - temporary fix? (this one worked)
        return False

    def isSpecialCollection(self, collectiontype):
        """
        See L{ICalDAVResource.isSpecialCollection}.
        """
        if not self.isCollection(): return False

        try:
            resourcetype = self.resourceType()
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
        return self.findSpecialCollections(caldavxml.Calendar, depth, request, callback, privileges)

    def findAddressBookCollections(self, depth, request, callback, privileges=None):
        return self.findSpecialCollections(carddavxml.AddressBook, depth, request, callback, privileges)

    @inlineCallbacks
    def findSpecialCollectionsFaster(self, type, depth, request, callback, privileges=None):
        assert depth in ("0", "1", "infinity"), "Invalid depth: %s" % (depth,)

        if depth != "0" and self.isCollection():
            basepath = request.urlForResource(self)
            for childname in (yield self.listChildren()):
                childpath = joinURL(basepath, childname)
                child = (yield request.locateResource(childpath))
                if child:
                    if privileges:
                        try:
                            yield child.checkPrivileges(request, privileges)
                        except AccessDeniedError:
                            continue
                    if child.isSpecialCollection(type):
                        callback(child, childpath)
                        
                    # No more regular collections. If we leave this in then dropbox is scanned at depth:infinity
                    # and that is very painful as it requires scanning all calendar resources too. Eventually we need
                    # to fix drop box and probably re-enable this for the generic case.
    #                elif child.isCollection():
    #                    if depth == "infinity":
    #                        yield child.findSpecialCollectionsFaster(type, depth, request, callback, privileges)                

    findSpecialCollections = findSpecialCollectionsFaster

    @inlineCallbacks
    def deletedCalendar(self, request):
        """
        Calendar has been deleted. Need to do some extra clean-up.

        @param request:
        @type request:
        """
        
        # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
        principal = (yield self.resourceOwnerPrincipal(request))
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
        principal = (yield self.resourceOwnerPrincipal(request))
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
        principal = (yield self.resourceOwnerPrincipal(request))
        inboxURL = principal.scheduleInboxURL()
        if inboxURL:
            inbox = (yield request.locateResource(inboxURL))
            default = (yield inbox.readProperty((caldav_namespace, "schedule-default-calendar-URL"), request))
            if default and len(default.children) == 1:
                defaultURL = normalizeURL(str(default.children[0]))
                myURL = (yield self.canonicalURL(request))
                returnValue(defaultURL == myURL)

        returnValue(False)

    @inlineCallbacks
    def iCalendarForUser(self, request):

        caldata = yield self.iCalendar()

        accessUID = (yield self.resourceOwnerPrincipal(request))
        if accessUID is None:
            accessUID = ""
        else:
            accessUID = accessUID.principalUID()

        returnValue(PerUserDataFilter(accessUID).filter(caldata))


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
                return (principal.record.fullName,
                    principal.record.guid,
                    principal.record.calendarUserAddresses)

        ical.normalizeCalendarUserAddresses(lookupFunction)


    def principalForCalendarUserAddress(self, address):
        for principalCollection in self.principalCollections():
            principal = principalCollection.principalForCalendarUserAddress(address)
            if principal is not None:
                return principal
        return None

    def principalForUID(self, principalUID):
        for principalCollection in self.principalCollections():
            principal = principalCollection.principalForUID(principalUID)
            if principal is not None:
                return principal
        return None


    @inlineCallbacks
    def movedAddressBook(self, request, defaultAddressBook, destination, destination_uri):
        """
        AddressBook has been moved. Need to do some extra clean-up.
        """
        
        # Adjust the default addressbook setting if necessary
        if defaultAddressBook:
            principal = (yield self.resourceOwnerPrincipal(request))
            home = (yield principal.addressBookHome(request))
            (_ignore_scheme, _ignore_host, destination_path, _ignore_query, _ignore_fragment) = urlsplit(normalizeURL(destination_uri))
            yield home.writeProperty(carddavxml.DefaultAddressBookURL(davxml.HRef(destination_path)), request)               

    @inlineCallbacks
    def isDefaultAddressBook(self, request):
        
        assert self.isAddressBookCollection()
        
        # Not allowed to delete the default address book
        principal = (yield self.resourceOwnerPrincipal(request))
        home = (yield principal.addressBookHome(request))
        default = (yield home.readProperty(carddavxml.DefaultAddressBookURL.qname(), request))
        if default and len(default.children) == 1:
            defaultURL = normalizeURL(str(default.children[0]))
            myURL = (yield self.canonicalURL(request))
            returnValue(defaultURL == myURL)

        returnValue(False)

    @inlineCallbacks
    def vCard(self):
        """
        See L{ICalDAVResource.vCard}.

        This implementation returns the an object created from the data returned
        by L{vCardText} when given the same arguments.

        Note that L{vCardText} by default calls this method, which creates
        an infinite loop.  A subclass must override one of both of these
        methods.
        """
        try:
            vcard_data = yield self.vCardText()
        except InternalDataStoreError:
            returnValue(None)

        if vcard_data is None:
            returnValue(None)

        try:
            returnValue(vComponent.fromString(vcard_data))
        except ValueError:
            returnValue(None)


    def supportedReports(self):
        result = super(CalDAVResource, self).supportedReports()
        result.append(davxml.Report(caldavxml.CalendarQuery(),))
        result.append(davxml.Report(caldavxml.CalendarMultiGet(),))
        if self.isCollection():
            # Only allowed on collections
            result.append(davxml.Report(caldavxml.FreeBusyQuery(),))
        if config.EnableCardDAV:
            result.append(davxml.Report(carddavxml.AddressBookQuery(),))
            result.append(davxml.Report(carddavxml.AddressBookMultiGet(),))
        if (
            self.isPseudoCalendarCollection() or
            self.isAddressBookCollection() or
            self.isNotificationCollection()
        ) and config.EnableSyncReport:
            # Only allowed on calendar/inbox/addressbook/notification collections
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
        if self.isPseudoCalendarCollection() or self.isAddressBookCollection():
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
            if parent and isinstance(parent, CalDAVResource):
                canonical_parent = (yield parent.canonicalURL(request))
                self._canonical_url = joinURL(canonical_parent, lastpath)
            else:
                self._canonical_url = myurl

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

    @inlineCallbacks
    def quotaRootResource(self, request):
        """
        Return the quota root for this resource.
        
        @return: L{DAVResource} or C{None}
        """

        sharedParent = None
        isvirt = self.isVirtualShare()
        if isvirt:
            # A virtual share's quota root is the resource owner's root
            sharedParent = (yield request.locateResource(parentForURL(self._share.hosturl)))
        else:
            parent = (yield self.locateParent(request, request.urlForResource(self)))
            if isCalendarCollectionResource(parent) or isAddressBookCollectionResource(parent):
                isvirt = parent.isVirtualShare()
                if isvirt:
                    # A virtual share's quota root is the resource owner's root
                    sharedParent = (yield request.locateResource(parentForURL(parent._share.hosturl)))

        if sharedParent:
            result = (yield sharedParent.quotaRootResource(request))
        else:
            result = (yield super(CalDAVResource, self).quotaRootResource(request))

        returnValue(result)

    # Collection sync stuff


    @inlineCallbacks
    def whatchanged(self, client_token, depth):
        current_token = (yield self.getSyncToken())
        current_uuid, current_revision = current_token[6:].split("_", 1)
        current_revision = int(current_revision)

        if client_token:
            try:
                if not client_token.startswith("data:,"):
                    raise ValueError
                caluuid, revision = client_token[6:].split("_", 1)
                revision = int(revision)
                
                # Check client token validity
                if caluuid != current_uuid:
                    raise ValueError
                if revision > current_revision:
                    raise ValueError
            except ValueError:
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (dav_namespace, "valid-sync-token"),
                    "Sync token is invalid",
                ))
        else:
            revision = 0

        try:
            changed, removed, notallowed = yield self._indexWhatChanged(revision, depth)
        except SyncTokenValidException:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (dav_namespace, "valid-sync-token"),
                "Sync token not recognized",
            ))

        returnValue((changed, removed, notallowed, current_token))

    def _indexWhatChanged(self, revision, depth):
        # Now handled directly by newstore
        raise NotImplementedError

    @inlineCallbacks
    def getSyncToken(self):
        """
        Return current sync-token value.
        """
        
        internal_token = (yield self.getInternalSyncToken())
        returnValue("data:,%s" % (internal_token,))

    def getInternalSyncToken(self):
        """
        Return current internal sync-token value.
        """
        raise HTTPError(StatusResponse(responsecode.NOT_FOUND, "Property not supported"))

    #
    # Stuff from CalDAVFile
    #

    def checkPreconditions(self, request):
        """
        We override the base class to handle the special implicit scheduling weak ETag behavior
        for compatibility with old clients using If-Match.
        """
        
        if config.Scheduling.CalDAV.ScheduleTagCompatibility:
            
            if self.exists() and hasattr(self, "scheduleEtags"):
                etags = self.scheduleEtags
                if len(etags) > 1:
                    # This is almost verbatim from twext.web2.static.checkPreconditions
                    if request.method not in ("GET", "HEAD"):
                        
                        # Always test against the current etag first just in case schedule-etags is out of sync
                        etags = (self.etag(), ) + tuple([http_headers.ETag(etag) for etag in etags])

                        # Loop over each tag and succeed if any one matches, else re-raise last exception
                        exists = self.exists()
                        last_modified = self.lastModified()
                        last_exception = None
                        for etag in etags:
                            try:
                                http.checkPreconditions(
                                    request,
                                    entityExists = exists,
                                    etag = etag,
                                    lastModified = last_modified,
                                )
                            except HTTPError, e:
                                last_exception = e
                            else:
                                break
                        else:
                            if last_exception:
                                raise last_exception
            
                    # Check per-method preconditions
                    method = getattr(self, "preconditions_" + request.method, None)
                    if method:
                        response = maybeDeferred(method, request)
                        response.addCallback(lambda _: request)
                        return response
                    else:
                        return None

        return super(CalDAVResource, self).checkPreconditions(request)

    @inlineCallbacks
    def createCalendar(self, request):
        """
        External API for creating a calendar.  Verify that the parent is a
        collection, exists, is I{not} a calendar collection; that this resource
        does not yet exist, then create it.

        @param request: the request used to look up parent resources to
            validate.

        @type request: L{twext.web2.iweb.IRequest}

        @return: a deferred that fires when a calendar collection has been
            created in this resource.
        """
        if self.exists():
            self.log_error("Attempt to create collection where file exists: %s" % (self,))
            raise HTTPError(StatusResponse(responsecode.NOT_ALLOWED, "File exists"))

        # newStore guarantees that we always have a parent calendar home
        #if not self.fp.parent().isdir():
        #    log.err("Attempt to create collection with no parent: %s" % (self.fp.path,))
        #    raise HTTPError(StatusResponse(responsecode.CONFLICT, "No parent collection"))

        #
        # Verify that no parent collection is a calendar also
        #

        parent = (yield self._checkParents(request, isPseudoCalendarCollectionResource))

        if parent is not None:
            self.log_error("Cannot create a calendar collection within a calendar collection %s" % (parent,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldavxml.caldav_namespace, "calendar-collection-location-ok"),
                "Cannot create a calendar collection inside another calendar collection",
            ))

        # Check for any quota limits
        if config.MaxCollectionsPerHome:
            parent = (yield self.locateParent(request, request.urlForResource(self)))
            if (yield parent.countOwnedChildren()) >= config.MaxCollectionsPerHome: # NB this ignores shares
                self.log_error("Cannot create a calendar collection because there are too many already present in %s" % (parent,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    customxml.MaxCollections(),
                    "Too many calendar collections",
                ))
                
        returnValue((yield self.createCalendarCollection()))


    def createCalendarCollection(self):
        """
        Internal API for creating a calendar collection.

        @return: a L{Deferred} which fires when the underlying collection has
            actually been created.
        """
        return fail(NotImplementedError())


    def iCalendarRolledup(self):
        """
        Only implemented by calendar collections; see storebridge.
        """
        


    @inlineCallbacks
    def iCalendarTextFiltered(self, isowner, accessUID=None):

        # Now "filter" the resource calendar data
        caldata = PrivateEventFilter(self.accessMode, isowner).filter(
            (yield self.iCalendarText())
        )
        if accessUID:
            caldata = PerUserDataFilter(accessUID).filter(caldata)
        returnValue(str(caldata))


    def iCalendarText(self):
        # storebridge handles this method
        raise NotImplementedError()


    def iCalendar(self):
        # storebridge handles this method
        raise NotImplementedError()


    @inlineCallbacks
    def createAddressBook(self, request):
        """
        External API for creating an addressbook.  Verify that the parent is a
        collection, exists, is I{not} an addressbook collection; that this resource
        does not yet exist, then create it.

        @param request: the request used to look up parent resources to
            validate.

        @type request: L{twext.web2.iweb.IRequest}

        @return: a deferred that fires when an addressbook collection has been
            created in this resource.
        """
        #
        # request object is required because we need to validate against parent
        # resources, and we need the request in order to locate the parents.
        #

        if self.exists():
            self.log_error("Attempt to create collection where file exists: %s" % (self,))
            raise HTTPError(StatusResponse(responsecode.NOT_ALLOWED, "File exists"))

        # newStore guarantees that we always have a parent calendar home
        #if not os.path.isdir(os.path.dirname(self.fp.path)):
        #    log.err("Attempt to create collection with no parent: %s" % (self.fp.path,))
        #    raise HTTPError(StatusResponse(responsecode.CONFLICT, "No parent collection"))

        #
        # Verify that no parent collection is a calendar also
        #

        parent = (yield self._checkParents(request, isAddressBookCollectionResource))
        if parent is not None:
            self.log_error("Cannot create an address book collection within an address book collection %s" % (parent,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (carddavxml.carddav_namespace, "addressbook-collection-location-ok"),
                "Cannot create an address book collection inside of an address book collection",
            ))

        # Check for any quota limits
        if config.MaxCollectionsPerHome:
            parent = (yield self.locateParent(request, request.urlForResource(self)))
            if (yield parent.countOwnedChildren()) >= config.MaxCollectionsPerHome: # NB this ignores shares
                self.log_error("Cannot create a calendar collection because there are too many already present in %s" % (parent,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    customxml.MaxCollections(),
                    "Too many address book collections",
                ))
                
        returnValue((yield self.createAddressBookCollection()))

    def createAddressBookCollection(self):
        """
        Internal API for creating an addressbook collection.

        @return: a L{Deferred} which fires when the underlying collection has
            actually been created.
        """
        return fail(NotImplementedError())

    @inlineCallbacks
    def vCardRolledup(self, request):
        # TODO: just catenate all the vCards together 
        yield fail(HTTPError((ErrorResponse(responsecode.BAD_REQUEST))))


    @inlineCallbacks
    def vCardText(self, name=None):
        if self.isAddressBookCollection():
            if name is None:
                returnValue(str((yield self.vCard())))
            vcard_resource = yield self.getChild(name)
            returnValue((yield vcard_resource.vCardText()))
        elif self.isCollection():
            returnValue(None)
        else:
            if name is not None:
                raise AssertionError("name must be None for non-collection vcard resource")
        # FIXME: StoreBridge handles this case
        raise NotImplementedError


    def supportedPrivileges(self, request):
        # read-free-busy support on calendar collection and calendar object resources
        if self.isCollection():
            return succeed(calendarPrivilegeSet)
        else:
            def gotParent(parent):
                if parent and isCalendarCollectionResource(parent):
                    return succeed(calendarPrivilegeSet)
                else:
                    return super(CalDAVResource, self).supportedPrivileges(request)

            d = self.locateParent(request, request.urlForResource(self))
            d.addCallback(gotParent)
            return d

        return super(CalDAVResource, self).supportedPrivileges(request)

    ##
    # Quota
    ##

    def quotaSize(self, request):
        """
        Get the size of this resource.
        TODO: Take into account size of dead-properties. Does stat include xattrs size?

        @return: an L{Deferred} with a C{int} result containing the size of the resource.
        """
#        if self.isCollection():
#            @inlineCallbacks
#            def walktree(top):
#                """
#                Recursively descend the directory tree rooted at top,
#                calling the callback function for each regular file
#
#                @param top: L{FilePath} for the directory to walk.
#                """
#
#                total = 0
#                for f in top.listdir():
#
#                    # Ignore the database
#                    if f.startswith("."):
#                        continue
#
#                    child = top.child(f)
#                    if child.isdir():
#                        # It's a directory, recurse into it
#                        total += yield walktree(child)
#                    elif child.isfile():
#                        # It's a file, call the callback function
#                        total += child.getsize()
#                    else:
#                        # Unknown file type, print a message
#                        pass
#
#                returnValue(total)
#
#            return walktree(self.fp)
#        else:
#            return succeed(self.fp.getsize())
        return succeed(0)

    ##
    # Utilities
    ##

    @staticmethod
    def _isChildURI(request, uri, immediateChild=True):
        """
        Verify that the supplied URI represents a resource that is a child
        of the request resource.
        @param request: the request currently in progress
        @param uri: the URI to test
        @return: True if the supplied URI is a child resource
                 False if not
        """
        if uri is None: return False

        #
        # Parse the URI
        #

        (scheme, host, path, query, fragment) = urlsplit(uri) #@UnusedVariable

        # Request hostname and child uri hostname have to be the same.
        if host and host != request.headers.getHeader("host"):
            return False

        # Child URI must start with request uri text.
        parent = request.uri
        if not parent.endswith("/"):
            parent += "/"

        return path.startswith(parent) and (len(path) > len(parent)) and (not immediateChild or (path.find("/", len(parent)) == -1))

    @inlineCallbacks
    def _checkParents(self, request, test):
        """
        @param request: the request being processed.
        @param test: a callable
        @return: the closest parent for this resource using the request URI from
            the given request for which C{test(parent)} evaluates to a true
            value, or C{None} if no parent matches.
        """
        parent = self
        parent_uri = request.uri

        while True:
            parent_uri = parentForURL(parent_uri)
            if not parent_uri: break

            parent = yield request.locateResource(parent_uri)

            if test(parent):
                returnValue(parent)

class CalendarPrincipalCollectionResource (DAVPrincipalCollectionResource, CalDAVResource):
    """
    CalDAV principal collection.
    """
    implements(IDAVPrincipalCollectionResource)

    def isCollection(self):
        return True

    def isCalendarCollection(self):
        return False

    def isAddressBookCollection(self):
        return False

    def isDirectoryBackedAddressBookCollection(self):
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

class CalendarPrincipalResource (CalDAVComplianceMixIn, DAVResourceWithChildrenMixin, DAVPrincipalResource):
    """
    CalDAV principal resource.

    Extends L{DAVPrincipalResource} to provide CalDAV functionality.
    """
    implements(ICalendarPrincipalResource)

    def liveProperties(self):
        
        baseProperties = ()
        
        if self.calendarsEnabled():
            baseProperties += (
                (caldav_namespace, "calendar-home-set"        ),
                (caldav_namespace, "calendar-user-address-set"),
                (caldav_namespace, "schedule-inbox-URL"       ),
                (caldav_namespace, "schedule-outbox-URL"      ),
                (caldav_namespace, "calendar-user-type"       ),
                (calendarserver_namespace, "calendar-proxy-read-for"  ),
                (calendarserver_namespace, "calendar-proxy-write-for" ),
                (calendarserver_namespace, "auto-schedule" ),
            )
        
        if self.addressBooksEnabled():
            baseProperties += (carddavxml.AddressBookHomeSet.qname(),)
            if self.directoryAddressBookEnabled():
                baseProperties += (carddavxml.DirectoryGateway.qname(),)

        if config.EnableDropBox:
            baseProperties += (customxml.DropBoxHomeURL.qname(),)

        if config.Sharing.Enabled:
            baseProperties += (customxml.NotificationURL.qname(),)

        return super(CalendarPrincipalResource, self).liveProperties() + baseProperties

    def isCollection(self):
        return True

    def calendarsEnabled(self):
        return config.EnableCalDAV

    def addressBooksEnabled(self):
        return config.EnableCardDAV

    def directoryAddressBookEnabled(self):
        return config.DirectoryAddressBook.Enabled and config.EnableSearchAddressBook

    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname

        if namespace == caldav_namespace and self.calendarsEnabled():
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

            elif name == "notification-URL" and config.Sharing.Enabled:
                url = yield self.notificationURL()
                if url is None:
                    returnValue(None)
                else:
                    returnValue(customxml.NotificationURL(davxml.HRef(url)))

            elif name == "calendar-proxy-read-for" and self.calendarsEnabled():
                results = (yield self.proxyFor(False))
                returnValue(customxml.CalendarProxyReadFor(
                    *[davxml.HRef(principal.principalURL()) for principal in results]
                ))

            elif name == "calendar-proxy-write-for" and self.calendarsEnabled():
                results = (yield self.proxyFor(True))
                returnValue(customxml.CalendarProxyWriteFor(
                    *[davxml.HRef(principal.principalURL()) for principal in results]
                ))

            elif name == "auto-schedule" and self.calendarsEnabled():
                autoSchedule = self.getAutoSchedule()
                returnValue(customxml.AutoSchedule("true" if autoSchedule else "false"))

        elif namespace == carddav_namespace and self.addressBooksEnabled():
            if name == "addressbook-home-set":
                returnValue(carddavxml.AddressBookHomeSet(
                    *[davxml.HRef(url) for url in self.addressBookHomeURLs()]
                 ))
            elif name == "directory-gateway" and self.directoryAddressBookEnabled():
                returnValue(carddavxml.DirectoryGateway(
                    davxml.HRef.fromString(joinURL("/", config.DirectoryAddressBook.name, "/"))
                ))

        result = (yield super(CalendarPrincipalResource, self).readProperty(property, request))
        returnValue(result)

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

class CommonHomeResource(PropfindCacheMixin, SharedHomeMixin, CalDAVResource):
    """
    Logic common to Calendar and Addressbook home resources.
    """
    cacheNotifierFactory = DisabledCacheNotifier

    def __init__(self, parent, name, transaction, home):
        self.parent = parent
        self.name = name
        self.associateWithTransaction(transaction)
        self._provisionedChildren = {}
        self._provisionedLinks = {}
        self._setupProvisions()
        self._newStoreHome = home
        self.cacheNotifier = self.cacheNotifierFactory(self)
        self._newStoreHome.addNotifier(CacheStoreNotifier(self))
        CalDAVResource.__init__(self)

        from twistedcaldav.storebridge import _NewStorePropertiesWrapper
        self._dead_properties = _NewStorePropertiesWrapper(
            self._newStoreHome.properties()
        )


    @classmethod
    @inlineCallbacks
    def createHomeResource(cls, parent, name, transaction):
        home, created = yield cls.homeFromTransaction(
            transaction, name)
        resource = cls(parent, name, transaction, home)
        if created:
            yield resource.postCreateHome()
        returnValue(resource)


    @classmethod
    def homeFromTransaction(cls, transaction, uid):
        """
        Create or retrieve an appropriate back-end-home object from a
        transaction and a home UID.

        @return: a L{Deferred} which fires a 2-tuple of C{(created, home)}
            where C{created} is a boolean indicating whether this call created
            the home in the back-end, and C{home} is the home object itself.
        """
        raise NotImplementedError("Subclasses must implement.")


    def _setupProvisions(self):
        pass

    def postCreateHome(self):
        pass

    def liveProperties(self):

        props = super(CommonHomeResource, self).liveProperties() + (
            (customxml.calendarserver_namespace, "push-transports"),
            (customxml.calendarserver_namespace, "pushkey"),
        )
        
        if config.MaxCollectionsPerHome:
            props += (customxml.MaxCollections.qname(),)

        return props

    def sharesDB(self):
        """
        Retrieve the new-style shares DB wrapper.
        """
        if not hasattr(self, "_sharesDB"):
            self._sharesDB = self._newStoreHome.retrieveOldShares()
        return self._sharesDB


    def url(self):
        return joinURL(self.parent.url(), self.name, "/")

    def canonicalURL(self, request):
        return succeed(self.url())

    def exists(self):
        # FIXME: tests
        return True

    def isCollection(self):
        return True

    def quotaSize(self, request):
        # FIXME: tests, workingness
        return succeed(0)

    def hasQuotaRoot(self, request):
        """
        Always get quota root value from config.

        @return: a C{True} if this resource has quota root, C{False} otherwise.
        """
        return config.UserQuota != 0
    
    def quotaRoot(self, request):
        """
        Always get quota root value from config.

        @return: a C{int} containing the maximum allowed bytes if this
            collection is quota-controlled, or C{None} if not quota controlled.
        """
        return config.UserQuota if config.UserQuota != 0 else None

    def currentQuotaUse(self, request):
        """
        Get the quota use value
        """  
        return maybeDeferred(self._newStoreHome.quotaUsedBytes)

    def supportedReports(self):
        result = super(CommonHomeResource, self).supportedReports()
        if config.EnableSyncReport:
            # Allowed on any home
            result.append(davxml.Report(SyncCollection(),))
        return result

    def _mergeSyncTokens(self, hometoken, notificationtoken):
        """
        Merge two sync tokens, choosing the higher revision number of the two,
        but keeping the home resource-id intact.
        """
        homekey, homerev = hometoken.split("_", 1)
        notrev = notificationtoken.split("_", 1)[1]
        if int(notrev) > int(homerev):
            hometoken = "%s_%s" % (homekey, notrev,)
        return hometoken

    def canShare(self):
        raise NotImplementedError


    @inlineCallbacks
    def findChildrenFaster(
        self, depth, request, okcallback, badcallback,
        names, privileges, inherited_aces
    ):
        """
        Override to pre-load children in certain collection types for better performance.
        """
        
        if depth == "1":
            yield self._newStoreHome.loadChildren()
        
        result = (yield super(CommonHomeResource, self).findChildrenFaster(
            depth, request, okcallback, badcallback, names, privileges, inherited_aces
        ))
        
        returnValue(result)
    
    @inlineCallbacks
    def makeChild(self, name):
        # Try built-in children first
        if name in self._provisionedChildren:
            cls = self._provisionedChildren[name]
            from twistedcaldav.notifications import NotificationCollectionResource
            if cls is NotificationCollectionResource:
                returnValue((yield self.createNotificationsCollection()))
            child = yield self._provisionedChildren[name](self)
            self.propagateTransaction(child)
            self.putChild(name, child)
            returnValue(child)

        # Try built-in links next
        if name in self._provisionedLinks:
            child = LinkResource(self, self._provisionedLinks[name])
            self.putChild(name, child)
            returnValue(child)

        # Try normal child type
        child = (yield self.makeRegularChild(name))

        # Try shares next if child does not exist
        if not child.exists() and self.canShare():
            sharedchild = yield self.provisionShare(name)
            if sharedchild:
                returnValue(sharedchild)

        returnValue(child)


    @inlineCallbacks
    def createNotificationsCollection(self):
        txn = self._associatedTransaction
        notifications = yield txn.notificationsWithUID(self._newStoreHome.uid())

        from twistedcaldav.storebridge import StoreNotificationCollectionResource
        similar = StoreNotificationCollectionResource(
            notifications,
            self,
            self._newStoreHome,
            principalCollections = self.principalCollections(),
        )
        self.propagateTransaction(similar)
        returnValue(similar)


    def makeRegularChild(self, name):
        raise NotImplementedError


    @inlineCallbacks
    def listChildren(self):
        """
        @return: a sequence of the names of all known children of this resource.
        """
        children = set(self._provisionedChildren.keys())
        children.update(self._provisionedLinks.keys())
        children.update((yield self._newStoreHome.listChildren()))
        children.update((yield self._newStoreHome.listSharedChildren()))
        returnValue(children)


    @inlineCallbacks
    def countOwnedChildren(self):
        """
        @return: the number of children (not shared ones).
        """
        returnValue(len(list((yield self._newStoreHome.listChildren()))))


    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == customxml.MaxCollections.qname() and config.MaxCollectionsPerHome:
            returnValue(customxml.MaxCollections.fromString(config.MaxCollectionsPerHome))
            
        elif qname == (customxml.calendarserver_namespace, "push-transports"):
            if config.Notifications.Services.XMPPNotifier.Enabled:
                nodeName = (yield self._newStoreHome.nodeName())
                if nodeName:
                    notifierID = self._newStoreHome.notifierID()
                    if notifierID:
                        children = []

                        apsConfiguration = getPubSubAPSConfiguration(notifierID, config)
                        if apsConfiguration:
                            children.append(
                                customxml.PubSubTransportProperty(
                                    customxml.PubSubSubscriptionProperty(
                                        davxml.HRef(
                                            apsConfiguration["SubscriptionURL"]
                                        ),
                                    ),
                                    customxml.PubSubAPSBundleIDProperty(
                                        apsConfiguration["APSBundleID"]
                                    ),
                                    type="APSD",
                                )
                            )

                        pubSubConfiguration = getPubSubConfiguration(config)
                        if pubSubConfiguration['xmpp-server']:
                            children.append(
                                customxml.PubSubTransportProperty(
                                    customxml.PubSubXMPPServerProperty(
                                        pubSubConfiguration['xmpp-server']
                                    ),
                                    customxml.PubSubXMPPURIProperty(
                                        getPubSubXMPPURI(notifierID, pubSubConfiguration)
                                    ),
                                    type="XMPP",
                                )
                            )

                        returnValue(customxml.PubSubPushTransportsProperty(*children))
            returnValue(None)

        elif qname == (customxml.calendarserver_namespace, "pushkey"):
            if config.Notifications.Services.XMPPNotifier.Enabled:
                nodeName = (yield self._newStoreHome.nodeName())
                if nodeName:
                    returnValue(customxml.PubSubXMPPPushKeyProperty(nodeName))
            returnValue(None)

        elif qname == (customxml.calendarserver_namespace, "xmpp-uri"):
            if config.Notifications.Services.XMPPNotifier.Enabled:
                nodeName = (yield self._newStoreHome.nodeName())
                if nodeName:
                    notifierID = self._newStoreHome.notifierID()
                    if notifierID:
                        pubSubConfiguration = getPubSubConfiguration(config)
                        returnValue(customxml.PubSubXMPPURIProperty(
                            getPubSubXMPPURI(notifierID, pubSubConfiguration)))

            returnValue(None)

        elif qname == (customxml.calendarserver_namespace, "xmpp-heartbeat-uri"):
            if config.Notifications.Services.XMPPNotifier.Enabled:
                # Look up node name not because we want to return it, but
                # to see if XMPP server is actually responding.  If it comes
                # back with an empty nodeName, don't advertise
                # xmpp-heartbeat-uri
                nodeName = (yield self._newStoreHome.nodeName())
                if nodeName:
                    pubSubConfiguration = getPubSubConfiguration(config)
                    returnValue(
                        customxml.PubSubHeartbeatProperty(
                            customxml.PubSubHeartbeatURIProperty(
                                getPubSubHeartbeatURI(pubSubConfiguration)
                            ),
                            customxml.PubSubHeartbeatMinutesProperty(
                                str(pubSubConfiguration['heartrate'])
                            )
                        )
                    )
            returnValue(None)

        elif qname == (customxml.calendarserver_namespace, "xmpp-server"):
            if config.Notifications.Services.XMPPNotifier.Enabled:
                # Look up node name not because we want to return it, but
                # to see if XMPP server is actually responding.  If it comes
                # back with an empty nodeName, don't advertise xmpp-server
                nodeName = (yield self._newStoreHome.nodeName())
                if nodeName:
                    pubSubConfiguration = getPubSubConfiguration(config)
                    returnValue(customxml.PubSubXMPPServerProperty(
                        pubSubConfiguration['xmpp-server']))
            returnValue(None)

        returnValue((yield super(CommonHomeResource, self).readProperty(property, request)))

    ##
    # ACL
    ##

    def owner(self, request):
        return succeed(davxml.HRef(self.principalForRecord().principalURL()))

    def ownerPrincipal(self, request):
        return succeed(self.principalForRecord())

    def resourceOwnerPrincipal(self, request):
        return succeed(self.principalForRecord())

    def defaultAccessControlList(self):
        myPrincipal = self.principalForRecord()

        aces = (
            # Inheritable DAV:all access for the resource's associated principal.
            davxml.ACE(
                davxml.Principal(davxml.HRef(myPrincipal.principalURL())),
                davxml.Grant(davxml.Privilege(davxml.All())),
                davxml.Protected(),
                TwistedACLInheritable(),
            ),
        )

        # Give read access to config.ReadPrincipals
        aces += config.ReadACEs

        # Give all access to config.AdminPrincipals
        aces += config.AdminACEs
        
        return davxml.ACL(*aces)

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return succeed(self.defaultAccessControlList())

    def principalCollections(self):
        return self.parent.principalCollections()

    def principalForRecord(self):
        raise NotImplementedError("Subclass must implement principalForRecord()")

    def notifierID(self, label="default"):
        self._newStoreHome.notifierID(label)

    def notifyChanged(self):
        self._newStoreHome.notifyChanged()

    # Methods not supported
    http_ACL = None
    http_COPY = None
    http_MOVE = None


class CalendarHomeResource(CommonHomeResource):
    """
    Calendar home collection classmethod.
    """

    @classmethod
    @inlineCallbacks
    def homeFromTransaction(cls, transaction, uid):
        storeHome = yield transaction.calendarHomeWithUID(uid)
        if storeHome is not None:
            created = False
        else:
            storeHome = yield transaction.calendarHomeWithUID(uid, create=True)
            created = True
        returnValue((storeHome, created))


    def _setupProvisions(self):

        # Cache children which must be of a specific type
        from twistedcaldav.storebridge import StoreScheduleInboxResource
        self._provisionedChildren["inbox"] = StoreScheduleInboxResource.maybeCreateInbox

        from twistedcaldav.schedule import ScheduleOutboxResource
        self._provisionedChildren["outbox"] = ScheduleOutboxResource

        if config.EnableDropBox:
            from twistedcaldav.storebridge import DropboxCollection
            self._provisionedChildren["dropbox"] = DropboxCollection

        if config.FreeBusyURL.Enabled:
            from twistedcaldav.freebusyurl import FreeBusyURLResource
            self._provisionedChildren["freebusy"] = FreeBusyURLResource

        if config.Sharing.Enabled and config.Sharing.Calendars.Enabled:
            from twistedcaldav.notifications import NotificationCollectionResource
            self._provisionedChildren["notification"] = NotificationCollectionResource


    @inlineCallbacks
    def postCreateHome(self):
        # This is a bit of a hack.  Really we ought to be always generating
        # this URL live from a back-end method that tells us what the
        # default calendar is.
        inbox = yield self.getChild("inbox")
        childURL = joinURL(self.url(), "calendar")
        inbox.processFreeBusyCalendar(childURL, True)


    def canShare(self):
        return config.Sharing.Enabled and config.Sharing.Calendars.Enabled and self.exists()


    @inlineCallbacks
    def makeRegularChild(self, name):
        newCalendar = yield self._newStoreHome.calendarWithName(name)
        from twistedcaldav.storebridge import CalendarCollectionResource
        similar = CalendarCollectionResource(
            newCalendar, self, name=name,
            principalCollections=self.principalCollections()
        )
        self.propagateTransaction(similar)
        returnValue(similar)


    def hasCalendarResourceUIDSomewhereElse(self, uid, ok_object, type):
        """
        Test if there are other child object resources with the specified UID.
        
        Pass through direct to store.
        """
        return self._newStoreHome.hasCalendarResourceUIDSomewhereElse(uid, ok_object._newStoreObject, type)

    def getCalendarResourcesForUID(self, uid, allow_shared=False):
        """
        Return all child object resources with the specified UID.
        
        Pass through direct to store.
        """
        return self._newStoreHome.getCalendarResourcesForUID(uid, allow_shared)

    def defaultAccessControlList(self):
        myPrincipal = self.principalForRecord()

        aces = (
            # Inheritable DAV:all access for the resource's associated principal.
            davxml.ACE(
                davxml.Principal(davxml.HRef(myPrincipal.principalURL())),
                davxml.Grant(davxml.Privilege(davxml.All())),
                davxml.Protected(),
                TwistedACLInheritable(),
            ),
            # Inheritable CALDAV:read-free-busy access for authenticated users.
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(davxml.Privilege(caldavxml.ReadFreeBusy())),
                TwistedACLInheritable(),
            ),
        )

        # Give read access to config.ReadPrincipals
        aces += config.ReadACEs

        # Give all access to config.AdminPrincipals
        aces += config.AdminACEs
        
        if config.EnableProxyPrincipals:
            aces += (
                # DAV:read/DAV:read-current-user-privilege-set access for this principal's calendar-proxy-read users.
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-read/"))),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ),
                # DAV:read/DAV:read-current-user-privilege-set/DAV:write access for this principal's calendar-proxy-write users.
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-write/"))),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                        davxml.Privilege(davxml.Write()),
                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ),
            )

        return davxml.ACL(*aces)


    @inlineCallbacks
    def getInternalSyncToken(self):
        # The newstore implementation supports this directly
        caltoken = yield self._newStoreHome.syncToken()

        if config.Sharing.Enabled and config.Sharing.Calendars.Enabled:
            notificationtoken = yield (yield self.getChild("notification")).getInternalSyncToken()

            # Merge tokens
            caltoken = self._mergeSyncTokens(caltoken, notificationtoken)

        returnValue(caltoken)


    @inlineCallbacks
    def _indexWhatChanged(self, revision, depth):
        # The newstore implementation supports this directly
        changed, deleted = yield self._newStoreHome.resourceNamesSinceToken(
            revision, depth
        )
        notallowed = []

        # Need to insert some addition items on first sync
        if revision == 0:
            changed.append("outbox/")

            if config.FreeBusyURL.Enabled:
                changed.append("freebusy")

            if config.Sharing.Enabled and config.Sharing.Calendars.Enabled:
                changed.append("notification/")

            # Dropbox is never synchronized
            if config.EnableDropBox:
                notallowed.append("dropbox/")

        # Add in notification changes
        if config.Sharing.Enabled and config.Sharing.Calendars.Enabled:
            noti_changed, noti_deleted, noti_notallowed = yield (yield self.getChild("notification"))._indexWhatChanged(revision, depth)

            changed.extend([joinURL("notification", name) for name in noti_changed])
            deleted.extend([joinURL("notification", name) for name in noti_deleted])
            notallowed.extend([joinURL("notification", name) for name in noti_notallowed])

        returnValue((changed, deleted, notallowed))


    def liveProperties(self):

        return super(CalendarHomeResource, self).liveProperties() + (
            (customxml.calendarserver_namespace, "xmpp-uri"),
            (customxml.calendarserver_namespace, "xmpp-heartbeat-uri"),
            (customxml.calendarserver_namespace, "xmpp-server"),
        )

class AddressBookHomeResource (CommonHomeResource):
    """
    Address book home collection resource.
    """

    @classmethod
    @inlineCallbacks
    def homeFromTransaction(cls, transaction, uid):
        storeHome = yield transaction.addressbookHomeWithUID(uid)
        if storeHome is not None:
            created = False
        else:
            storeHome = yield transaction.addressbookHomeWithUID(uid, create=True)
            created = True
        returnValue((storeHome, created))


    def liveProperties(self):
        
        return super(AddressBookHomeResource, self).liveProperties() + (
            carddavxml.DefaultAddressBookURL.qname(),
        )

    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        if qname == carddavxml.DefaultAddressBookURL.qname():
            # Must have a valid default
            try:
                defaultAddressBookProperty = self.readDeadProperty(property)
            except HTTPError:
                defaultAddressBookProperty = None
            if defaultAddressBookProperty and len(defaultAddressBookProperty.children) == 1:
                defaultAddressBook = str(defaultAddressBookProperty.children[0])
                adbk = (yield request.locateResource(str(defaultAddressBook)))
                if adbk is not None and adbk.exists() and isAddressBookCollectionResource(adbk):
                    returnValue(defaultAddressBookProperty) 
            
            # Default is not valid - we have to try to pick one
            defaultAddressBookProperty = (yield self.pickNewDefaultAddressBook(request))
            returnValue(defaultAddressBookProperty)
            
        result = (yield super(AddressBookHomeResource, self).readProperty(property, request))
        returnValue(result)

    @inlineCallbacks
    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement)

        if property.qname() == carddavxml.DefaultAddressBookURL.qname():
            # Verify that the address book added in the PROPPATCH is valid.
            property.children = [davxml.HRef(normalizeURL(str(href))) for href in property.children]
            new_adbk = [str(href) for href in property.children]
            adbk = None
            if len(new_adbk) == 1:
                adbkURI = str(new_adbk[0])
                adbk = (yield request.locateResource(str(new_adbk[0])))
            if adbk is None or not adbk.exists() or not isAddressBookCollectionResource(adbk):
                # Validate that href's point to a valid addressbook.
                raise HTTPError(ErrorResponse(
                    responsecode.CONFLICT,
                    (carddav_namespace, "valid-default-addressbook-URL"),
                    "Invalid URI",
                ))
            else:
                # Canonicalize the URL to __uids__ form
                adbkURI = (yield adbk.canonicalURL(request))
                property = carddavxml.DefaultAddressBookURL(davxml.HRef(adbkURI))

        yield super(AddressBookHomeResource, self).writeProperty(property, request)

    def _setupProvisions(self):

        # Cache children which must be of a specific type
        if config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled and not config.Sharing.Calendars.Enabled:
            from twistedcaldav.notifications import NotificationCollectionResource
            self._provisionedChildren["notification"] = NotificationCollectionResource

        if config.GlobalAddressBook.Enabled:
            self._provisionedLinks[config.GlobalAddressBook.Name] = "/addressbooks/public/global/addressbook/"

    def makeNewStore(self):
        return self._associatedTransaction.addressbookHomeWithUID(self.name, create=True), False     # Don't care about created

    def canShare(self):
        return config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled and self.exists()

    @inlineCallbacks
    def makeRegularChild(self, name):

        # Check for public/global path
        from twistedcaldav.storebridge import (
            AddressBookCollectionResource,
            GlobalAddressBookCollectionResource,
        )
        mainCls = AddressBookCollectionResource
        if isinstance(self.record, InternalDirectoryRecord):
            if "global" in self.record.shortNames:
                mainCls = GlobalAddressBookCollectionResource

        newAddressBook = yield self._newStoreHome.addressbookWithName(name)
        similar = mainCls(
            newAddressBook, self, name,
            principalCollections=self.principalCollections()
        )
        self.propagateTransaction(similar)
        returnValue(similar)


    @inlineCallbacks
    def pickNewDefaultAddressBook(self, request):
        """
        First see if "addressbook" exists in the addressbook home and pick that. Otherwise
        pick the first one we see.
        """
        defaultAddressBookURL = joinURL(self.url(), "addressbook")
        defaultAddressBook = (yield self.makeRegularChild("addressbook"))
        if defaultAddressBook is None or not defaultAddressBook.exists():
            getter = iter((yield self._newStoreHome.addressbooks()))
            # FIXME: the back-end should re-provision a default addressbook here.
            # Really, the dead property shouldn't be necessary, and this should
            # be entirely computed by a back-end method like 'defaultAddressBook()'
            try:
                anAddressBook = getter.next()
            except StopIteration:
                raise RuntimeError("No address books at all.")

            defaultAddressBookURL = joinURL(self.url(), anAddressBook.name())

        self.writeDeadProperty(
            carddavxml.DefaultAddressBookURL(
                davxml.HRef(defaultAddressBookURL)
            )
        )
        returnValue(carddavxml.DefaultAddressBookURL(
            davxml.HRef(defaultAddressBookURL))
        )

    @inlineCallbacks
    def getInternalSyncToken(self):
        # The newstore implementation supports this directly
        adbktoken = yield self._newStoreHome.syncToken()

        if config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled and not config.Sharing.Calendars.Enabled:
            notifcationtoken = yield (yield self.getChild("notification")).getInternalSyncToken()
            
            # Merge tokens
            adbkkey, adbkrev = adbktoken.split("_", 1)
            notrev = notifcationtoken.split("_", 1)[1]
            if int(notrev) > int(adbkrev):
                adbktoken = "%s_%s" % (adbkkey, notrev,)

        returnValue(adbktoken)


    @inlineCallbacks
    def _indexWhatChanged(self, revision, depth):
        # The newstore implementation supports this directly
        changed, deleted = yield self._newStoreHome.resourceNamesSinceToken(
            revision, depth
        )
        notallowed = []

        # Need to insert some addition items on first sync
        if revision == 0:
            if config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled and not config.Sharing.Calendars.Enabled:
                changed.append("notification/")

        # Add in notification changes
        if config.Sharing.Enabled and config.Sharing.AddressBooks.Enabled and not config.Sharing.Calendars.Enabled:
            noti_changed, noti_deleted, noti_notallowed = yield (yield self.getChild("notification"))._indexWhatChanged(revision, depth)

            changed.extend([joinURL("notification", name) for name in noti_changed])
            deleted.extend([joinURL("notification", name) for name in noti_deleted])
            notallowed.extend([joinURL("notification", name) for name in noti_notallowed])

        returnValue((changed, deleted, notallowed))


class GlobalAddressBookResource (ReadOnlyResourceMixIn, CalDAVResource):
    """
    Global address book. All we care about is making sure permissions are setup.
    """

    def resourceType(self):
        return davxml.ResourceType.sharedaddressbook #@UndefinedVariable

    def defaultAccessControlList(self):

        aces = (
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                    davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                    davxml.Privilege(davxml.Write()),
                ),
                davxml.Protected(),
                TwistedACLInheritable(),
           ),
        )
        
        if config.GlobalAddressBook.EnableAnonymousReadAccess:
            aces += (
                davxml.ACE(
                    davxml.Principal(davxml.Unauthenticated()),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
               ),
            )
        return davxml.ACL(*aces)

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return succeed(self.defaultAccessControlList())


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


def isAddressBookCollectionResource(resource):
    try:
        resource = ICalDAVResource(resource)
    except TypeError:
        return False
    else:
        return resource.isAddressBookCollection()

