# -*- test-case-name: twistedcaldav.test.test_sharing -*-
##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
Sharing behavior
"""


__all__ = [
    "SharedCollectionMixin",
]

from twext.python.log import LoggingMixIn
from twext.web2 import responsecode
from twext.web2.http import HTTPError, Response, XMLResponse
from twext.web2.dav.http import ErrorResponse, MultiStatusResponse
from twext.web2.dav.resource import TwistedACLInheritable
from twext.web2.dav.util import allDataFromStream, joinURL
from txdav.xml import element

from twisted.internet.defer import succeed, inlineCallbacks, DeferredList,\
    returnValue

from twistedcaldav import customxml, caldavxml
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.directory.wiki import WikiDirectoryService, getWikiAccess
from twistedcaldav.linkresource import LinkFollowerMixIn
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.sql import AbstractSQLDatabase, db_prefix

from pycalendar.datetime import PyCalendarDateTime

from uuid import uuid4
import os
import types

# Types of sharing mode
SHARETYPE_INVITE = "I"  # Invite based sharing
SHARETYPE_DIRECT = "D"  # Direct linking based sharing

class SharedCollectionMixin(object):

    @inlineCallbacks
    def inviteProperty(self, request):
        """
        Calculate the customxml.Invite property (for readProperty) from the
        invites database.
        """
        if config.Sharing.Enabled:
            
            # See if this property is on the shared calendar
            isShared = yield self.isShared(request)
            if isShared:
                yield self.validateInvites()
                records = yield self.invitesDB().allRecords()
                returnValue(customxml.Invite(
                    *[record.makePropertyElement() for record in records]
                ))
                
            # See if it is on the sharee calendar
            if self.isVirtualShare():
                original = (yield request.locateResource(self._share.hosturl))
                yield original.validateInvites()
                records = yield original.invitesDB().allRecords()

                ownerPrincipal = (yield original.ownerPrincipal(request))
                owner = ownerPrincipal.principalURL()
                ownerCN = ownerPrincipal.displayName()

                returnValue(customxml.Invite(
                    customxml.Organizer(
                        element.HRef.fromString(owner),
                        customxml.CommonName.fromString(ownerCN),
                    ),
                    *[record.makePropertyElement(includeUID=False) for record in records]
                ))

        returnValue(None)


    def upgradeToShare(self):
        """ Upgrade this collection to a shared state """
        
        # Change resourcetype
        rtype = self.resourceType()
        rtype = element.ResourceType(*(rtype.children + (customxml.SharedOwner(),)))
        self.writeDeadProperty(rtype)
        
        # Create invites database
        self.invitesDB().create()
    
    @inlineCallbacks
    def downgradeFromShare(self, request):
        
        # Change resource type (note this might be called after deleting a resource
        # so we have to cope with that)
        rtype = self.resourceType()
        rtype = element.ResourceType(*([child for child in rtype.children if child != customxml.SharedOwner()]))
        self.writeDeadProperty(rtype)
        
        # Remove all invitees
        for record in (yield self.invitesDB().allRecords()):
            yield self.uninviteRecordFromShare(record, request)

        # Remove invites database
        self.invitesDB().remove()
        delattr(self, "_invitesDB")
    
        returnValue(True)


    @inlineCallbacks
    def changeUserInviteState(self, request, inviteUID, principalURL, state, summary=None):
        shared = (yield self.isShared(request))
        if not shared:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Invalid share",
            ))
        
        principalUID = principalURL.split("/")[3]
        record = yield self.invitesDB().recordForInviteUID(inviteUID)
        if record is None or record.principalUID != principalUID:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Invalid invitation uid: %s" % (inviteUID,),
            ))
        
        # Only certain states are sharer controlled
        if record.state in ("NEEDS-ACTION", "ACCEPTED", "DECLINED",):
            record.state = state
            if summary is not None:
                record.summary = summary
            yield self.invitesDB().addOrUpdateRecord(record)


    @inlineCallbacks
    def directShare(self, request):
        """
        Directly bind an accessible calendar/address book collection into the current
        principal's calendar/addressbook home.

        @param request: the request triggering this action
        @type request: L{IRequest}
        """
        
        # Need to have at least DAV:read to do this
        yield self.authorize(request, (element.Read(),))
        
        # Find current principal
        authz_principal = self.currentPrincipal(request).children[0]
        if not isinstance(authz_principal, element.HRef):
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "valid-principal"),
                "Current user principal not a DAV:href",
            ))
        principalURL = str(authz_principal)
        if not principalURL:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "valid-principal"),
                "Current user principal not specified",
            ))
        principal = (yield request.locateResource(principalURL))
        
        # Check enabled for service
        from twistedcaldav.directory.principal import DirectoryCalendarPrincipalResource
        if not isinstance(principal, DirectoryCalendarPrincipalResource):
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "invalid-principal"),
                "Current user principal is not a calendar/addressbook enabled principal",
            ))
        
        # Get the home collection
        if self.isCalendarCollection():
            home = yield principal.calendarHome(request)
        elif self.isAddressBookCollection():
            home = yield principal.addressBookHome(request)
        else:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "invalid-principal"),
                "No calendar/addressbook home for principal",
            ))
            
        # TODO: Make sure principal is not sharing back to themselves
        compareURL = (yield self.canonicalURL(request))
        homeURL = home.url()
        if compareURL.startswith(homeURL):
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "invalid-share"),
                "Can't share your own calendar or addressbook",
            ))

        # Accept it
        directID = home.sharesDB().directShareID(home, self)
        response = (yield home.acceptDirectShare(request, compareURL, directID, self.displayName()))

        # Return the URL of the shared calendar
        returnValue(response)


    @inlineCallbacks
    def isShared(self, request):
        """ Return True if this is an owner shared calendar collection """
        returnValue((yield self.isSpecialCollection(customxml.SharedOwner)))


    def setVirtualShare(self, shareePrincipal, share):
        self._isVirtualShare = True
        self._shareePrincipal = shareePrincipal
        self._share = share

        if hasattr(self, "_newStoreObject"):
            self._newStoreObject.setSharingUID(self._shareePrincipal.principalUID())


    def isVirtualShare(self):
        """ Return True if this is a shared calendar collection """
        return hasattr(self, "_isVirtualShare")


    @inlineCallbacks
    def removeVirtualShare(self, request):
        """ Return True if this is a shared calendar collection """
        
        # Remove from sharee's calendar/address book home
        if self.isCalendarCollection():
            shareeHome = yield self._shareePrincipal.calendarHome(request)
        elif self.isAddressBookCollection():
            shareeHome = yield self._shareePrincipal.addressBookHome(request)
        returnValue((yield shareeHome.removeShare(request, self._share)))


    def resourceType(self):
        superObject = super(SharedCollectionMixin, self)
        try:
            superMethod = superObject.resourceType
        except AttributeError:
            rtype = element.ResourceType()
        else:
            rtype = superMethod()

        isVirt = self.isVirtualShare()
        if isVirt:
            rtype = element.ResourceType(
                *(
                    tuple([child for child in rtype.children if child.qname() != customxml.SharedOwner.qname()]) +
                    (customxml.Shared(),)
                )
            )
        return rtype


    def sharedResourceType(self):
        """
        Return the DAV:resourcetype stripped of any shared elements.
        """
        
        if self.isCalendarCollection():
            return "calendar"
        elif self.isAddressBookCollection():
            return "addressbook"
        else:
            return ""


    @inlineCallbacks
    def shareeAccessControlList(self, request, *args, **kwargs):

        assert self._isVirtualShare, "Only call this for a virtual share"

        wikiAccessMethod = kwargs.get("wikiAccessMethod", getWikiAccess)

        # Direct shares use underlying privileges of shared collection
        if self._share.sharetype == SHARETYPE_DIRECT:
            original = (yield request.locateResource(self._share.hosturl))
            owner = yield original.ownerPrincipal(request)
            if owner.record.recordType == WikiDirectoryService.recordType_wikis:
                # Access level comes from what the wiki has granted to the
                # sharee
                userID = self._shareePrincipal.record.guid
                wikiID = owner.record.shortNames[0]
                inviteAccess = (yield wikiAccessMethod(userID, wikiID))
                if inviteAccess == "read":
                    inviteAccess = "read-only"
                elif inviteAccess in ("write", "admin"):
                    inviteAccess = "read-write"
                else:
                    inviteAccess = None
            else:
                result = (yield original.accessControlList(request, *args,
                    **kwargs))
                returnValue(result)
        else:
            # Invite shares use access mode from the invite
    
            # Get the invite for this sharee
            invite = yield self.invitesDB().recordForInviteUID(
                self._share.shareuid
            )
            if invite is None:
                returnValue(element.ACL())
            inviteAccess = invite.access
            
        userprivs = [
        ]
        if inviteAccess in ("read-only", "read-write", "read-write-schedule",):
            userprivs.append(element.Privilege(element.Read()))
            userprivs.append(element.Privilege(element.ReadACL()))
            userprivs.append(element.Privilege(element.ReadCurrentUserPrivilegeSet()))
        if inviteAccess in ("read-only",):
            userprivs.append(element.Privilege(element.WriteProperties()))
        if inviteAccess in ("read-write", "read-write-schedule",):
            userprivs.append(element.Privilege(element.Write()))
        proxyprivs = list(userprivs)
        try:
            proxyprivs.remove(element.Privilege(element.ReadACL()))
        except ValueError:
            # If wiki says no-access then ReadACL won't be in the list
            pass

        aces = (
            # Inheritable specific access for the resource's associated principal.
            element.ACE(
                element.Principal(element.HRef(self._shareePrincipal.principalURL())),
                element.Grant(*userprivs),
                element.Protected(),
                TwistedACLInheritable(),
            ),
        )

        if self.isCalendarCollection():
            aces += (
                # Inheritable CALDAV:read-free-busy access for authenticated users.
                element.ACE(
                    element.Principal(element.Authenticated()),
                    element.Grant(element.Privilege(caldavxml.ReadFreeBusy())),
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
                element.ACE(
                    element.Principal(element.HRef(joinURL(self._shareePrincipal.principalURL(), "calendar-proxy-read/"))),
                    element.Grant(
                        element.Privilege(element.Read()),
                        element.Privilege(element.ReadCurrentUserPrivilegeSet()),
                    ),
                    element.Protected(),
                    TwistedACLInheritable(),
                ),
                # DAV:read/DAV:read-current-user-privilege-set/DAV:write access for this principal's calendar-proxy-write users.
                element.ACE(
                    element.Principal(element.HRef(joinURL(self._shareePrincipal.principalURL(), "calendar-proxy-write/"))),
                    element.Grant(*proxyprivs),
                    element.Protected(),
                    TwistedACLInheritable(),
                ),
            )

        returnValue(element.ACL(*aces))

    def validUserIDForShare(self, userid):
        """
        Test the user id to see if it is a valid identifier for sharing and
        return a "normalized" form for our own use (e.g. convert mailto: to
        urn:uuid).

        @param userid: the userid to test
        @type userid: C{str}
        
        @return: C{str} of normalized userid or C{None} if
            userid is not allowed.
        """
        
        # First try to resolve as a principal
        principal = self.principalForCalendarUserAddress(userid)
        if principal:
            return principal.principalURL()
        
        # TODO: we do not support external users right now so this is being hard-coded
        # off in spite of the config option.
        #elif config.Sharing.AllowExternalUsers:
        #    return userid
        else:
            return None

    def validUserIDWithCommonNameForShare(self, userid, cn):
        """
        Validate user ID and find the common name.

        @param userid: the userid to test
        @type userid: C{str}
        @param cn: default common name to use if principal has none
        @type cn: C{str}
        
        @return: C{tuple} of C{str} of normalized userid or C{None} if
            userid is not allowed, and appropriate common name.
        """
        
        # First try to resolve as a principal
        principal = self.principalForCalendarUserAddress(userid)
        if principal:
            return userid, principal.principalURL(), principal.displayName()
        
        # TODO: we do not support external users right now so this is being hard-coded
        # off in spite of the config option.
        #elif config.Sharing.AllowExternalUsers:
        #    return userid, None, cn
        else:
            return None, None, None


    @inlineCallbacks
    def validateInvites(self):
        """
        Make sure each userid in an invite is valid - if not re-write status.
        """
        
        records = yield self.invitesDB().allRecords()
        for record in records:
            if self.validUserIDForShare(record.userid) is None and record.state != "INVALID":
                record.state = "INVALID"
                yield self.invitesDB().addOrUpdateRecord(record)


    def inviteUserToShare(self, userid, cn, ace, summary, request):
        """ Send out in invite first, and then add this user to the share list
            @param userid: 
            @param ace: Must be one of customxml.ReadWriteAccess or customxml.ReadAccess
        """
        
        # TODO: Check if this collection is shared, and error out if it isn't
        resultIsList = True
        if type(userid) is not list:
            userid = [userid]
            resultIsList = False
        if type(cn) is not list:
            cn = [cn]
            
        dl = [self.inviteSingleUserToShare(user, cn, ace, summary, request) for user, cn in zip(userid, cn)]
        return self._processShareActionList(dl, resultIsList)

    def uninviteUserToShare(self, userid, ace, request):
        """ Send out in uninvite first, and then remove this user from the share list."""
        
        # Do not validate the userid - we want to allow invalid users to be removed because they
        # may have been valid when added, but no longer valid now. Clients should be able to clear out
        # anything known to be invalid.

        # TODO: Check if this collection is shared, and error out if it isn't
        resultIsList = True
        if type(userid) is not list:
            userid = [userid]
            resultIsList = False

        dl = [self.uninviteSingleUserFromShare(user, ace, request) for user in userid]
        return self._processShareActionList(dl, resultIsList)

    def inviteUserUpdateToShare(self, userid, cn, aceOLD, aceNEW, summary, request):

        resultIsList = True
        if type(userid) is not list:
            userid = [userid]
            resultIsList = False
        if type(cn) is not list:
            cn = [cn]
            
        dl = [self.inviteSingleUserUpdateToShare(user, cn, aceOLD, aceNEW, summary, request) for user, cn in zip(userid, cn)]
        return self._processShareActionList(dl, resultIsList)

    def _processShareActionList(self, dl, resultIsList):
        def _defer(resultset):
            results = [result if success else False for success, result in resultset]
            return results if resultIsList else results[0]
        return DeferredList(dl).addCallback(_defer)
        

    @inlineCallbacks
    def _createLock(self, userid, request):
        """
        Create an instance of MemcacheLock whose key is based on the sharee's
        uid and the collection's URL
        """
        returnValue(MemcacheLock(
            "ShareInviteLock",
            (yield self._lockToken(userid, request)),
            timeout=config.Scheduling.Options.UIDLockTimeoutSeconds,
            expire_time=config.Scheduling.Options.UIDLockExpirySeconds,
        ))

    @inlineCallbacks
    def _acquireLock(self, lock):
        """
        Attempt to acquire a lock -- can raise MemcacheLockTimeoutError
        """
        try:
            yield lock.acquire()
        except MemcacheLockTimeoutError:
            self.log_error("Memcache lock timeout for sharing invite")
            raise

    @inlineCallbacks
    def _lockToken(self, userid, request):
        """
        Generate a string we can use for a memcache lock key
        """
        hosturl = (yield self.canonicalURL(request))
        returnValue("%s:%s" % (hosturl, userid))

    @inlineCallbacks
    def inviteSingleUserToShare(self, userid, cn, ace, summary, request):
        
        # Validate userid and cn
        userid, principalURL, cn = self.validUserIDWithCommonNameForShare(userid, cn)
        
        # We currently only handle local users
        if principalURL is None:
            returnValue(False)

        # Acquire a memcache lock based on collection URL and sharee UID
        # TODO: when sharing moves into the store this should be replaced
        # by DB-level locking
        lock = (yield self._createLock(userid, request))
        yield self._acquireLock(lock)

        try:
            # Look for existing invite and update its fields or create new one
            principalUID = principalURL.split("/")[3]
            record = yield self.invitesDB().recordForPrincipalUID(principalUID)
            if record:
                record.name = cn
                record.access = inviteAccessMapFromXML[type(ace)]
                record.summary = summary
            else:
                record = Invite(str(uuid4()), userid, principalUID, cn, inviteAccessMapFromXML[type(ace)], "NEEDS-ACTION", summary)

            # Send invite
            yield self.sendInvite(record, request)

            # Add to database
            yield self.invitesDB().addOrUpdateRecord(record)

        finally:
            lock.clean()

        returnValue(True)


    @inlineCallbacks
    def uninviteSingleUserFromShare(self, userid, aces, request):
        # Cancel invites - we'll just use whatever userid we are given

        # Acquire a memcache lock based on collection URL and sharee UID
        # TODO: when sharing moves into the store this should be replaced
        # by DB-level locking
        lock = (yield self._createLock(userid, request))
        yield self._acquireLock(lock)

        try:
            record = yield self.invitesDB().recordForUserID(userid)
            if record:
                result = (yield self.uninviteRecordFromShare(record, request))
            else:
                result = False
        finally:
            lock.clean()

        returnValue(result)


    @inlineCallbacks
    def uninviteRecordFromShare(self, record, request):
        
        # Remove any shared calendar or address book
        sharee = self.principalForCalendarUserAddress(record.userid)
        if sharee:
            if self.isCalendarCollection():
                shareeHome = yield sharee.calendarHome(request)
            elif self.isAddressBookCollection():
                shareeHome = yield sharee.addressBookHome(request)
            yield shareeHome.removeShareByUID(request, record.inviteuid)
    
            # If current user state is accepted then we send an invite with the new state, otherwise
            # we cancel any existing invites for the user
            if record and record.state != "ACCEPTED":
                yield self.removeInvite(record, request)
            elif record:
                record.state = "DELETED"
                yield self.sendInvite(record, request)
    
        # Remove from database
        yield self.invitesDB().removeRecordForInviteUID(record.inviteuid)
        
        returnValue(True)            

    def inviteSingleUserUpdateToShare(self, userid, commonName, acesOLD, aceNEW, summary, request):
        
        # Just update existing
        return self.inviteSingleUserToShare(userid, commonName, aceNEW, summary, request) 

    @inlineCallbacks
    def sendInvite(self, record, request):
        
        ownerPrincipal = (yield self.ownerPrincipal(request))
        owner = ownerPrincipal.principalURL()
        ownerCN = ownerPrincipal.displayName()
        hosturl = (yield self.canonicalURL(request))

        # Locate notifications collection for user
        sharee = self.principalForCalendarUserAddress(record.userid)
        if sharee is None:
            raise ValueError("sharee is None but userid was valid before")
        
        # We need to look up the resource so that the response cache notifier is properly initialized
        notificationResource = (yield request.locateResource(sharee.notificationURL()))
        notifications = notificationResource._newStoreNotifications
        
        # Look for existing notification
        oldnotification = (yield notifications.notificationObjectWithUID(record.inviteuid))
        if oldnotification:
            # TODO: rollup changes?
            pass
        
        # Generate invite XML
        typeAttr = {'shared-type':self.sharedResourceType()}
        xmltype = customxml.InviteNotification(**typeAttr)
        xmldata = customxml.Notification(
            customxml.DTStamp.fromString(PyCalendarDateTime.getNowUTC().getText()),
            customxml.InviteNotification(
                customxml.UID.fromString(record.inviteuid),
                element.HRef.fromString(record.userid),
                inviteStatusMapToXML[record.state](),
                customxml.InviteAccess(inviteAccessMapToXML[record.access]()),
                customxml.HostURL(
                    element.HRef.fromString(hosturl),
                ),
                customxml.Organizer(
                    element.HRef.fromString(owner),
                    customxml.CommonName.fromString(ownerCN),
                ),
                customxml.InviteSummary.fromString(record.summary),
                self.getSupportedComponentSet() if self.isCalendarCollection() else None,
                **typeAttr
            ),
        ).toxml()
        
        # Add to collections
        yield notifications.writeNotificationObject(record.inviteuid, xmltype, xmldata)

    @inlineCallbacks
    def removeInvite(self, record, request):
        
        # Locate notifications collection for user
        sharee = self.principalForCalendarUserAddress(record.userid)
        if sharee is None:
            raise ValueError("sharee is None but userid was valid before")
        notifications = (yield request.locateResource(sharee.notificationURL()))
        
        # Add to collections
        yield notifications.deleteNotifictionMessageByUID(request, record.inviteuid)

    @inlineCallbacks
    def _xmlHandleInvite(self, request, docroot):
        yield self.authorize(request, (element.Read(), element.Write()))
        result = (yield self._handleInvite(request, docroot))
        returnValue(result)
    
    def _handleInvite(self, request, invitedoc):
        def _handleInviteSet(inviteset):
            userid = None
            cn = None
            access = None
            summary = None
            for item in inviteset.children:
                if isinstance(item, element.HRef):
                    userid = str(item)
                    continue
                if isinstance(item, customxml.CommonName):
                    cn = str(item)
                    continue
                if isinstance(item, customxml.InviteSummary):
                    summary = str(item)
                    continue
                if isinstance(item, customxml.ReadAccess) or isinstance(item, customxml.ReadWriteAccess):
                    access = item
                    continue
            if userid and access and summary:
                return (userid, cn, access, summary)
            else:
                error_text = []
                if userid is None:
                    error_text.append("missing href")
                if access is None:
                    error_text.append("missing access")
                if summary is None:
                    error_text.append("missing summary")
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (customxml.calendarserver_namespace, "valid-request"),
                    "%s: %s" % (", ".join(error_text), inviteset,),
                ))

        def _handleInviteRemove(inviteremove):
            userid = None
            access = []
            for item in inviteremove.children:
                if isinstance(item, element.HRef):
                    userid = str(item)
                    continue
                if isinstance(item, customxml.ReadAccess) or isinstance(item, customxml.ReadWriteAccess):
                    access.append(item)
                    continue
            if userid is None:
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (customxml.calendarserver_namespace, "valid-request"),
                    "Missing href: %s" % (inviteremove,),
                ))
            if len(access) == 0:
                access = None
            else:
                access = set(access)
            return (userid, access)

        def _autoShare(isShared, request):
            if not isShared:
                self.upgradeToShare()

        @inlineCallbacks
        def _processInviteDoc(_, request):
            setDict, removeDict, updateinviteDict = {}, {}, {}
            okusers = set()
            badusers = set()
            for item in invitedoc.children:
                if isinstance(item, customxml.InviteSet):
                    userid, cn, access, summary = _handleInviteSet(item)
                    setDict[userid] = (cn, access, summary)
                
                    # Validate each userid on add only
                    (okusers if self.validUserIDForShare(userid) else badusers).add(userid)
                elif isinstance(item, customxml.InviteRemove):
                    userid, access = _handleInviteRemove(item)
                    removeDict[userid] = access
                    
                    # Treat removed userids as valid as we will fail invalid ones silently
                    okusers.add(userid)

            # Only make changes if all OK
            if len(badusers) == 0:
                okusers = set()
                badusers = set()
                # Special case removing and adding the same user and treat that as an add
                sameUseridInRemoveAndSet = [u for u in removeDict.keys() if u in setDict]
                for u in sameUseridInRemoveAndSet:
                    removeACL = removeDict[u]
                    cn, newACL, summary = setDict[u]
                    updateinviteDict[u] = (cn, removeACL, newACL, summary)
                    del removeDict[u]
                    del setDict[u]
                for userid, access in removeDict.iteritems():
                    result = (yield self.uninviteUserToShare(userid, access, request))
                    # If result is False that means the user being removed was not
                    # actually invited, but let's not return an error in this case.
                    okusers.add(userid)
                for userid, (cn, access, summary) in setDict.iteritems():
                    result = (yield self.inviteUserToShare(userid, cn, access, summary, request))
                    (okusers if result else badusers).add(userid)
                for userid, (cn, removeACL, newACL, summary) in updateinviteDict.iteritems():
                    result = (yield self.inviteUserUpdateToShare(userid, cn, removeACL, newACL, summary, request))
                    (okusers if result else badusers).add(userid)

                # In this case bad items do not prevent ok items from being processed
                ok_code = responsecode.OK
            else:
                # In this case a bad item causes all ok items not to be processed so failed dependency is returned
                ok_code = responsecode.FAILED_DEPENDENCY

            # Do a final validation of the entire set of invites
            yield self.validateInvites()
            
            # Create the multistatus response - only needed if some are bad
            if badusers:
                xml_responses = []
                xml_responses.extend([
                    element.StatusResponse(element.HRef(userid), element.Status.fromResponseCode(ok_code))
                    for userid in sorted(okusers)
                ])
                xml_responses.extend([
                    element.StatusResponse(element.HRef(userid), element.Status.fromResponseCode(responsecode.FORBIDDEN))
                    for userid in sorted(badusers)
                ])
            
                #
                # Return response
                #
                returnValue(MultiStatusResponse(xml_responses))
            else:
                returnValue(responsecode.OK)

        return self.isShared(request).addCallback(_autoShare, request).addCallback(_processInviteDoc, request)

    @inlineCallbacks
    def _xmlHandleInviteReply(self, request, docroot):
        yield self.authorize(request, (element.Read(), element.Write()))
        result = (yield self._handleInviteReply(request, docroot))
        returnValue(result)
    
    def _handleInviteReply(self, request, docroot):
        raise NotImplementedError

    @inlineCallbacks
    def xmlRequestHandler(self, request):
        
        # Need to read the data and get the root element first
        xmldata = (yield allDataFromStream(request.stream))
        try:
            doc = element.WebDAVDocument.fromString(xmldata)
        except ValueError, e:
            self.log_error("Error parsing doc (%s) Doc:\n %s" % (str(e), xmldata,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Invalid XML",
            ))

        root = doc.root_element
        if type(root) in self.xmlDocHandlers:
            result = (yield self.xmlDocHandlers[type(root)](self, request, root))
            returnValue(result)
        else:
            self.log_error("Unsupported XML (%s)" % (root,))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Unsupported XML",
            ))

    xmlDocHandlers = {
        customxml.InviteShare: _xmlHandleInvite,
        customxml.InviteReply: _xmlHandleInviteReply,          
    }

    def POST_handler_content_type(self, request, contentType):
        if self.isCollection():
            if contentType:
                if contentType in self._postHandlers:
                    return self._postHandlers[contentType](self, request)
                else:
                    self.log_info("Get a POST of an unsupported content type on a collection type: %s" % (contentType,))
            else:
                self.log_info("Get a POST with no content type on a collection")
        return succeed(responsecode.FORBIDDEN)

    _postHandlers = {
        ("application", "xml") : xmlRequestHandler,
        ("text", "xml") : xmlRequestHandler,
    }

inviteAccessMapToXML = {
    "read-only"           : customxml.ReadAccess,
    "read-write"          : customxml.ReadWriteAccess,
}
inviteAccessMapFromXML = dict([(v,k) for k,v in inviteAccessMapToXML.iteritems()])

inviteStatusMapToXML = {
    "NEEDS-ACTION" : customxml.InviteStatusNoResponse,
    "ACCEPTED"     : customxml.InviteStatusAccepted,
    "DECLINED"     : customxml.InviteStatusDeclined,
    "DELETED"      : customxml.InviteStatusDeleted,
    "INVALID"      : customxml.InviteStatusInvalid,
}
inviteStatusMapFromXML = dict([(v,k) for k,v in inviteStatusMapToXML.iteritems()])

class Invite(object):
    
    def __init__(self, inviteuid, userid, principalUID, common_name, access, state, summary):
        self.inviteuid = inviteuid
        self.userid = userid
        self.principalUID = principalUID
        self.name = common_name
        self.access = access
        self.state = state
        self.summary = summary
        
    def makePropertyElement(self, includeUID=True):
        
        return customxml.InviteUser(
            customxml.UID.fromString(self.inviteuid) if includeUID else None,
            element.HRef.fromString(self.userid),
            customxml.CommonName.fromString(self.name),
            customxml.InviteAccess(inviteAccessMapToXML[self.access]()),
            inviteStatusMapToXML[self.state](),
        )

class InvitesDatabase(AbstractSQLDatabase, LoggingMixIn):
    
    db_basename = db_prefix + "invites"
    schema_version = "1"
    db_type = "invites"

    def __init__(self, resource):
        """
        @param resource: the L{CalDAVResource} resource for
            the shared collection. C{resource} must be a calendar/addressbook collection.)
        """
        self.resource = resource
        db_filename = os.path.join(self.resource.fp.path, InvitesDatabase.db_basename)
        super(InvitesDatabase, self).__init__(db_filename, True, autocommit=True)

    def create(self):
        """
        Create the index and initialize it.
        """
        self._db()


    def get_dbpath(self):
        return self.resource.fp.child(InvitesDatabase.db_basename).path


    def set_dbpath(self, newpath):
        pass

    dbpath = property(get_dbpath, set_dbpath)

    def allRecords(self):
        
        records = self._db_execute("select * from INVITE order by USERID")
        return [self._makeRecord(row) for row in (records if records is not None else ())]
    
    def recordForUserID(self, userid):
        
        row = self._db_execute("select * from INVITE where USERID = :1", userid)
        return self._makeRecord(row[0]) if row else None
    
    def recordForPrincipalUID(self, principalUID):
        
        row = self._db_execute("select * from INVITE where PRINCIPALUID = :1", principalUID)
        return self._makeRecord(row[0]) if row else None
    
    def recordForInviteUID(self, inviteUID):

        row = self._db_execute("select * from INVITE where INVITEUID = :1", inviteUID)
        return self._makeRecord(row[0]) if row else None
    
    def addOrUpdateRecord(self, record):

        self._db_execute("""insert or replace into INVITE (INVITEUID, USERID, PRINCIPALUID, NAME, ACCESS, STATE, SUMMARY)
            values (:1, :2, :3, :4, :5, :6, :7)
            """, record.inviteuid, record.userid, record.principalUID, record.name, record.access, record.state, record.summary,
        )
    
    def removeRecordForInviteUID(self, inviteUID):

        self._db_execute("delete from INVITE where INVITEUID = :1", inviteUID)
    
    def remove(self):
        
        self._db_close()
        os.remove(self.dbpath)

    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return InvitesDatabase.schema_version

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return InvitesDatabase.db_type

    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """
        #
        # INVITE table is the primary table
        #   INVITEUID: UID for this invite
        #   USERID: identifier of invitee
        #   PRINCIPALUID: principal-UID of invitee
        #   NAME: common name of invitee
        #   ACCESS: Access mode for share
        #   STATE: Invite response status
        #   SUMMARY: Invite summary
        #
        q.execute(
            """
            create table INVITE (
                INVITEUID      text unique,
                USERID         text unique,
                PRINCIPALUID   text unique,
                NAME           text,
                ACCESS         text,
                STATE          text,
                SUMMARY        text
            )
            """
        )

        q.execute(
            """
            create index USERID on INVITE (USERID)
            """
        )
        q.execute(
            """
            create index PRINCIPALUID on INVITE (PRINCIPALUID)
            """
        )
        q.execute(
            """
            create index INVITEUID on INVITE (INVITEUID)
            """
        )

    def _db_upgrade_data_tables(self, q, old_version):
        """
        Upgrade the data from an older version of the DB.
        """

        # Nothing to do as we have not changed the schema
        pass

    def _makeRecord(self, row):
        
        return Invite(*[str(item) if type(item) == types.UnicodeType else item for item in row])

class SharedHomeMixin(LinkFollowerMixIn):
    """
    A mix-in for calendar/addressbook homes that defines the operations for
    manipulating a sharee's set of shared calendars.
    """


    @inlineCallbacks
    def provisionShare(self, name):
        # Try to find a matching share
        child = None
        shares = yield self.allShares()
        if name in shares:
            from twistedcaldav.sharedcollection import SharedCollectionResource
            child = SharedCollectionResource(self, shares[name])
            self.putChild(name, child)
        returnValue(child)


    @inlineCallbacks
    def allShares(self):
        if not hasattr(self, "_allShares"):
            allShareRecords = yield self.sharesDB().allRecords()
            self._allShares = dict([(share.localname, share) for share in
                                    allShareRecords])
        returnValue(self._allShares)


    @inlineCallbacks
    def allShareNames(self):
        allShares = yield self.allShares()
        returnValue(tuple(allShares.keys()))


    @inlineCallbacks
    def acceptInviteShare(self, request, hostUrl, inviteUID, displayname=None):
        
        # Check for old share
        oldShare = yield self.sharesDB().recordForShareUID(inviteUID)

        # Send the invite reply then add the link
        yield self._changeShare(request, "ACCEPTED", hostUrl, inviteUID, displayname)

        response = (yield self._acceptShare(request, oldShare, SHARETYPE_INVITE, hostUrl, inviteUID, displayname))
        returnValue(response)

    @inlineCallbacks
    def acceptDirectShare(self, request, hostUrl, resourceUID, displayname=None):

        # Just add the link
        oldShare = yield self.sharesDB().recordForShareUID(resourceUID)
        response = (yield self._acceptShare(request, oldShare, SHARETYPE_DIRECT, hostUrl, resourceUID, displayname))
        returnValue(response)

    @inlineCallbacks
    def _acceptShare(self, request, oldShare, sharetype, hostUrl, shareUID, displayname=None):

        # Add or update in DB
        if oldShare:
            share = oldShare
        else:
            share = SharedCollectionRecord(shareUID, sharetype, hostUrl, str(uuid4()), displayname)
            yield self.sharesDB().addOrUpdateRecord(share)
        
        # Get shared collection in non-share mode first
        sharedCollection = (yield request.locateResource(hostUrl))
        ownerPrincipal = (yield self.ownerPrincipal(request))

        # For a direct share we will copy any calendar-color over using the owners view
        color = None
        if sharetype == SHARETYPE_DIRECT and not oldShare and sharedCollection.isCalendarCollection():
            try:
                color = (yield sharedCollection.readProperty(customxml.CalendarColor, request))
            except HTTPError:
                pass
        
        # Set per-user displayname or color to whatever was given
        sharedCollection.setVirtualShare(ownerPrincipal, share)
        if displayname:
            yield sharedCollection.writeProperty(element.DisplayName.fromString(displayname), request)
        if color:
            yield sharedCollection.writeProperty(customxml.CalendarColor.fromString(color), request)

        # Calendars always start out transparent and with empty default alarms
        if not oldShare and sharedCollection.isCalendarCollection():
            yield sharedCollection.writeProperty(caldavxml.ScheduleCalendarTransp(caldavxml.Transparent()), request)
            yield sharedCollection.writeProperty(caldavxml.DefaultAlarmVEventDateTime.fromString(""), request)
            yield sharedCollection.writeProperty(caldavxml.DefaultAlarmVEventDate.fromString(""), request)
            yield sharedCollection.writeProperty(caldavxml.DefaultAlarmVToDoDateTime.fromString(""), request)
            yield sharedCollection.writeProperty(caldavxml.DefaultAlarmVToDoDate.fromString(""), request)
 
        # Notify client of changes
        yield self.notifyChanged()

        # Return the URL of the shared collection
        returnValue(XMLResponse(
            code = responsecode.OK,
            element = customxml.SharedAs(
                element.HRef.fromString(joinURL(self.url(), share.localname))
            )
        ))

    def removeShare(self, request, share):
        """ Remove a shared collection named in resourceName """

        # Send a decline when an invite share is removed only
        if share.sharetype == SHARETYPE_INVITE:
            return self.declineShare(request, share.hosturl, share.shareuid)
        else:
            return self.removeDirectShare(request, share)

    @inlineCallbacks
    def removeShareByUID(self, request, shareUID):
        """ Remove a shared collection but do not send a decline back """

        share = yield self.sharesDB().recordForShareUID(shareUID)
        if share:
            yield self.removeDirectShare(request, share)

        returnValue(True)

    @inlineCallbacks
    def removeDirectShare(self, request, share):
        """ Remove a shared collection but do not send a decline back """

        shareURL = joinURL(self.url(), share.localname)

        if self.isCalendarCollection():
            # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
            principal = (yield self.resourceOwnerPrincipal(request))
            inboxURL = principal.scheduleInboxURL()
            if inboxURL:
                inbox = (yield request.locateResource(inboxURL))
                inbox.processFreeBusyCalendar(shareURL, False)

        yield self.sharesDB().removeRecordForShareUID(share.shareuid)
 
        # Notify client of changes
        yield self.notifyChanged()

    @inlineCallbacks
    def declineShare(self, request, hostUrl, inviteUID):

        # Remove it if it is in the DB
        yield self.removeShareByUID(request, inviteUID)

        yield self._changeShare(request, "DECLINED", hostUrl, inviteUID)
        
        returnValue(Response(code=responsecode.NO_CONTENT))

    @inlineCallbacks
    def _changeShare(self, request, state, hostUrl, replytoUID, displayname=None):
        """
        Accept or decline an invite to a shared collection.
        """
        
        # Change state in sharer invite
        ownerPrincipal = (yield self.ownerPrincipal(request))
        owner = ownerPrincipal.principalURL()
        sharedCollection = (yield request.locateResource(hostUrl))
        if sharedCollection is None:
            # Original shared collection is gone - nothing we can do except ignore it
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Invalid shared collection",
            ))
            
        # Change the record
        yield sharedCollection.changeUserInviteState(request, replytoUID, owner, state, displayname)

        yield self.sendReply(request, ownerPrincipal, sharedCollection, state, hostUrl, replytoUID, displayname)

    @inlineCallbacks
    def sendReply(self, request, shareePrincipal, sharedCollection, state, hostUrl, replytoUID, displayname=None):

        # Locate notifications collection for sharer
        sharer = (yield sharedCollection.ownerPrincipal(request))
        notifications = (yield request.locateResource(sharer.notificationURL()))

        # Generate invite XML
        notificationUID = "%s-reply" % (replytoUID,)
        xmltype = customxml.InviteReply()

        # Prefer mailto:, otherwise use principal URL
        for cua in shareePrincipal.calendarUserAddresses():
            if cua.startswith("mailto:"):
                break
        else:
            cua = shareePrincipal.principalURL()

        commonName = shareePrincipal.displayName()
        record = shareePrincipal.record

        xmldata = customxml.Notification(
            customxml.DTStamp.fromString(PyCalendarDateTime.getNowUTC().getText()),
            customxml.InviteReply(
                *(
                    (
                        element.HRef.fromString(cua),
                        inviteStatusMapToXML[state](),
                        customxml.HostURL(
                            element.HRef.fromString(hostUrl),
                        ),
                        customxml.InReplyTo.fromString(replytoUID),
                    ) + ((customxml.InviteSummary.fromString(displayname),) if displayname is not None else ())
                      + ((customxml.CommonName.fromString(commonName),) if commonName is not None else ())
                      + ((customxml.FirstNameProperty(record.firstName),) if record.firstName is not None else ())
                      + ((customxml.LastNameProperty(record.lastName),) if record.lastName is not None else ())
                )
            ),
        ).toxml()
        
        # Add to collections
        yield notifications.addNotification(request, notificationUID, xmltype, xmldata)

    def _handleInviteReply(self, request, invitereplydoc):
        """ Handle a user accepting or declining a sharing invite """
        hostUrl = None
        accepted = None
        summary = None
        replytoUID = None
        for item in invitereplydoc.children:
            if isinstance(item, customxml.InviteStatusAccepted):
                accepted = True
            elif isinstance(item, customxml.InviteStatusDeclined):
                accepted = False
            elif isinstance(item, customxml.InviteSummary):
                summary = str(item)
            elif isinstance(item, customxml.HostURL):
                for hosturlItem in item.children:
                    if isinstance(hosturlItem, element.HRef):
                        hostUrl = str(hosturlItem)
            elif isinstance(item, customxml.InReplyTo):
                replytoUID = str(item)
        
        if accepted is None or hostUrl is None or replytoUID is None:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Missing required XML elements",
            ))
        if accepted:
            return self.acceptInviteShare(request, hostUrl, replytoUID, displayname=summary)
        else:
            return self.declineShare(request, hostUrl, replytoUID)

class SharedCollectionRecord(object):
    
    def __init__(self, shareuid, sharetype, hosturl, localname, summary):
        self.shareuid = shareuid
        self.sharetype = sharetype
        self.hosturl = hosturl
        self.localname = localname
        self.summary = summary

class SharedCollectionsDatabase(AbstractSQLDatabase, LoggingMixIn):
    
    db_basename = db_prefix + "shares"
    schema_version = "1"
    db_type = "shares"

    def __init__(self, resource):   
        """
        @param resource: the L{CalDAVResource} resource for
            the shared collection. C{resource} must be a calendar/addressbook home collection.)
        """
        self.resource = resource
        db_filename = os.path.join(self.resource.fp.path, SharedCollectionsDatabase.db_basename)
        super(SharedCollectionsDatabase, self).__init__(db_filename, True, autocommit=True)


    def get_dbpath(self):
        return self.resource.fp.child(SharedCollectionsDatabase.db_basename).path


    def set_dbpath(self, newpath):
        pass


    dbpath = property(get_dbpath, set_dbpath)


    def create(self):
        """
        Create the index and initialize it.
        """
        self._db()

    def allRecords(self):
        
        records = self._db_execute("select * from SHARES order by LOCALNAME")
        return [self._makeRecord(row) for row in (records if records is not None else ())]


    def recordForShareUID(self, shareUID):

        row = self._db_execute("select * from SHARES where SHAREUID = :1", shareUID)
        return self._makeRecord(row[0]) if row else None
    
    def addOrUpdateRecord(self, record):

        self._db_execute("""insert or replace into SHARES (SHAREUID, SHARETYPE, HOSTURL, LOCALNAME, SUMMARY)
            values (:1, :2, :3, :4, :5)
            """, record.shareuid, record.sharetype, record.hosturl, record.localname, record.summary,
        )
    
    def removeRecordForLocalName(self, localname):

        self._db_execute("delete from SHARES where LOCALNAME = :1", localname)
    
    def removeRecordForShareUID(self, shareUID):

        self._db_execute("delete from SHARES where SHAREUID = :1", shareUID)
    
    def remove(self):
        
        self._db_close()
        os.remove(self.dbpath)

    def directShareID(self, shareeHome, sharerCollection):
        return "Direct-%s-%s" % (shareeHome.resourceID(), sharerCollection.resourceID(),)

    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return SharedCollectionsDatabase.schema_version

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return SharedCollectionsDatabase.db_type

    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """
        #
        # SHARES table is the primary table
        #   SHAREUID: UID for this share
        #   SHARETYPE: type of share: "I" for invite, "D" for direct
        #   HOSTURL: URL for data source
        #   LOCALNAME: local path name
        #   SUMMARY: Share summary
        #
        q.execute(
            """
            create table SHARES (
                SHAREUID       text unique,
                SHARETYPE      text(1),
                HOSTURL        text,
                LOCALNAME      text,
                SUMMARY        text
            )
            """
        )

        q.execute(
            """
            create index SHAREUID on SHARES (SHAREUID)
            """
        )
        q.execute(
            """
            create index HOSTURL on SHARES (HOSTURL)
            """
        )
        q.execute(
            """
            create index LOCALNAME on SHARES (LOCALNAME)
            """
        )

    def _db_upgrade_data_tables(self, q, old_version):
        """
        Upgrade the data from an older version of the DB.
        """

        # Nothing to do as we have not changed the schema
        pass

    def _makeRecord(self, row):
        
        return SharedCollectionRecord(*[str(item) if type(item) == types.UnicodeType else item for item in row])
