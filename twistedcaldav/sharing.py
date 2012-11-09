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
from txdav.common.datastore.sql_tables import _BIND_MODE_OWN, \
    _BIND_MODE_READ, _BIND_MODE_WRITE, _BIND_STATUS_INVITED, \
    _BIND_MODE_DIRECT, _BIND_STATUS_ACCEPTED, _BIND_STATUS_DECLINED, \
    _BIND_STATUS_INVALID, _ABO_KIND_GROUP
from txdav.xml import element

from twisted.internet.defer import succeed, inlineCallbacks, DeferredList, \
    returnValue

from twistedcaldav import customxml, caldavxml
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.directory.wiki import WikiDirectoryService, getWikiAccess
from twistedcaldav.linkresource import LinkFollowerMixIn
from twistedcaldav.sql import AbstractSQLDatabase, db_prefix

from pycalendar.datetime import PyCalendarDateTime

import os
import types

# FIXME: Get rid of these imports
from twistedcaldav.directory.util import TRANSACTION_KEY
# circular import
#from txdav.common.datastore.sql import ECALENDARTYPE, EADDRESSBOOKTYPE
ECALENDARTYPE = 0
EADDRESSBOOKTYPE = 1
#ENOTIFICATIONTYPE = 2


class SharedCollectionMixin(object):

    @inlineCallbacks
    def inviteProperty(self, request):
        """
        Calculate the customxml.Invite property (for readProperty) from the
        invites database.
        """
        if config.Sharing.Enabled:

            def invitePropertyElement(invitation, includeUID=True):

                userid = "urn:uuid:" + invitation.shareeUID()
                principal = self.principalForUID(invitation.shareeUID())
                cn = principal.displayName() if principal else invitation.shareeUID()
                return customxml.InviteUser(
                    customxml.UID.fromString(invitation.uid()) if includeUID else None,
                    element.HRef.fromString(userid),
                    customxml.CommonName.fromString(cn),
                    customxml.InviteAccess(invitationAccessMapToXML[invitation.access()]()),
                    invitationStatusMapToXML[invitation.state()](),
                )

            # See if this property is on the shared calendar
            isShared = yield self.isShared(request)
            if isShared:
                yield self.validateInvites(request)
                invitations = yield self._allInvitations()
                returnValue(customxml.Invite(
                    *[invitePropertyElement(invitation) for invitation in invitations]
                ))

            # See if it is on the sharee calendar
            if self.isShareeCollection():
                original = (yield request.locateResource(self._share.url()))
                yield original.validateInvites(request)
                invitations = yield original._allInvitations()

                ownerPrincipal = (yield original.ownerPrincipal(request))
                owner = ownerPrincipal.principalURL()
                ownerCN = ownerPrincipal.displayName()

                returnValue(customxml.Invite(
                    customxml.Organizer(
                        element.HRef.fromString(owner),
                        customxml.CommonName.fromString(ownerCN),
                    ),
                    *[invitePropertyElement(invitation, includeUID=False) for invitation in invitations]
                ))

        returnValue(None)


    def upgradeToShare(self):
        """ Upgrade this collection to a shared state """

        if self.isCollection():
            # Change resourcetype
            rtype = self.resourceType()
            rtype = element.ResourceType(*(rtype.children + (customxml.SharedOwner(),)))
            self.writeDeadProperty(rtype)
        # TODO: set group resource type?

    @inlineCallbacks
    def downgradeFromShare(self, request):

        if self.isCollection():
            # Change resource type (note this might be called after deleting a resource
            # so we have to cope with that)
            rtype = self.resourceType()
            rtype = element.ResourceType(*([child for child in rtype.children if child != customxml.SharedOwner()]))
            self.writeDeadProperty(rtype)

        # Remove all invitees
        for invitation in (yield self._allInvitations()):
            yield self.uninviteFromShare(invitation, request)

        returnValue(True)


    @inlineCallbacks
    def changeUserInviteState(self, request, inviteUID, shareeUID, state, summary=None):
        shared = (yield self.isShared(request))
        if not shared:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Invalid share",
            ))

        invitation = yield self._invitationForUID(inviteUID)
        if invitation is None or invitation.shareeUID() != shareeUID:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Invalid invitation uid: %s" % (inviteUID,),
            ))

        # Only certain states are sharer controlled
        if invitation.state() in ("NEEDS-ACTION", "ACCEPTED", "DECLINED",):
            yield self._updateInvitation(invitation, state=state, summary=summary)


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
        sharee = (yield request.locateResource(principalURL))

        # Check enabled for service
        from twistedcaldav.directory.principal import DirectoryCalendarPrincipalResource
        if not isinstance(sharee, DirectoryCalendarPrincipalResource):
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "invalid-principal"),
                "Current user principal is not a calendar/addressbook enabled principal",
            ))

        # Get the home collection
        if self.isCalendarCollection():
            shareeHomeResource = yield sharee.calendarHome(request)
        elif self.isAddressBookCollection() or self.isGroup():
            shareeHomeResource = yield sharee.addressBookHome(request)
        else:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "invalid-principal"),
                "No calendar/addressbook home for principal",
            ))

        # TODO: Make sure principal is not sharing back to themselves
        hostURL = (yield self.canonicalURL(request))
        shareeHomeURL = shareeHomeResource.url()
        if hostURL.startswith(shareeHomeURL):
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "invalid-share"),
                "Can't share your own calendar or addressbook",
            ))

        # Accept it
        directUID = Share.directUID(shareeHomeResource._newStoreHome, self._newStoreObject)
        response = (yield shareeHomeResource.acceptDirectShare(request, hostURL, directUID, self.displayName()))

        # Return the URL of the shared calendar
        returnValue(response)


    @inlineCallbacks
    def isShared(self, request):
        """ Return True if this is an owner shared calendar collection """
        returnValue((yield self.isSpecialCollection(customxml.SharedOwner)) or
                    bool((yield self._allInvitations()))) # same as, len(SharedAs() + InvitedAs())


    def setShare(self, share):
        self._isShareeCollection = True #  _isShareeCollection attr is used by self tests
        self._share = share


    def isShareeCollection(self):
        """ Return True if this is a sharee view of a shared calendar collection """
        return hasattr(self, "_isShareeCollection")


    @inlineCallbacks
    def removeShareeCollection(self, request):

        sharee = self.principalForUID(self._share.shareeUID())

        # Remove from sharee's calendar/address book home
        if self.isCalendarCollection():
            shareeHome = yield sharee.calendarHome(request)
        elif self.isAddressBookCollection() or self.isGroup():
            shareeHome = yield sharee.addressBookHome(request)
        returnValue((yield shareeHome.removeShare(request, self._share)))


    def resourceType(self):
        superObject = super(SharedCollectionMixin, self)
        try:
            superMethod = superObject.resourceType
        except AttributeError:
            rtype = element.ResourceType()
        else:
            rtype = superMethod()

        isShareeCollection = self.isShareeCollection()
        if isShareeCollection:
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
        elif self.isGroup():
            #TODO: Add group xml resource type ?
            return "group"
        else:
            return ""


    @inlineCallbacks
    def shareeAccessControlList(self, request, *args, **kwargs):

        assert self._isShareeCollection, "Only call this for a sharee collection"

        wikiAccessMethod = kwargs.get("wikiAccessMethod", getWikiAccess)

        sharee = self.principalForUID(self._share.shareeUID())

        # Direct shares use underlying privileges of shared collection
        if self._share.direct():
            original = (yield request.locateResource(self._share.url()))
            owner = yield original.ownerPrincipal(request)
            if owner.record.recordType == WikiDirectoryService.recordType_wikis:
                # Access level comes from what the wiki has granted to the
                # sharee
                userID = sharee.record.guid
                wikiID = owner.record.shortNames[0]
                access = (yield wikiAccessMethod(userID, wikiID))
                if access == "read":
                    access = "read-only"
                elif access in ("write", "admin"):
                    access = "read-write"
                else:
                    access = None
            else:
                result = (yield original.accessControlList(request, *args,
                    **kwargs))
                returnValue(result)
        else:
            # Invited shares use access mode from the invite
            # Get the access for self
            access = Invitation(self._newStoreObject).access()

        userprivs = [
        ]
        if access in ("read-only", "read-write",):
            userprivs.append(element.Privilege(element.Read()))
            userprivs.append(element.Privilege(element.ReadACL()))
            userprivs.append(element.Privilege(element.ReadCurrentUserPrivilegeSet()))
        if access in ("read-only",):
            userprivs.append(element.Privilege(element.WriteProperties()))
        if access in ("read-write",):
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
                element.Principal(element.HRef(sharee.principalURL())),
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
                    element.Principal(element.HRef(joinURL(sharee.principalURL(), "calendar-proxy-read/"))),
                    element.Grant(
                        element.Privilege(element.Read()),
                        element.Privilege(element.ReadCurrentUserPrivilegeSet()),
                    ),
                    element.Protected(),
                    TwistedACLInheritable(),
                ),
                # DAV:read/DAV:read-current-user-privilege-set/DAV:write access for this principal's calendar-proxy-write users.
                element.ACE(
                    element.Principal(element.HRef(joinURL(sharee.principalURL(), "calendar-proxy-write/"))),
                    element.Grant(*proxyprivs),
                    element.Protected(),
                    TwistedACLInheritable(),
                ),
            )

        returnValue(element.ACL(*aces))


    @inlineCallbacks
    def validUserIDForShare(self, userid, request=None):
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
            if request:
                ownerPrincipal = (yield self.ownerPrincipal(request))
                owner = ownerPrincipal.principalURL()
                if owner == principal.principalURL():
                    returnValue(None)
            returnValue(principal.principalURL())

        # TODO: we do not support external users right now so this is being hard-coded
        # off in spite of the config option.
        #elif config.Sharing.AllowExternalUsers:
        #    return userid
        else:
            returnValue(None)


    @inlineCallbacks
    def validateInvites(self, request):
        """
        Make sure each userid in an invite is valid - if not re-write status.
        """
        #assert request
        invitations = yield self._allInvitations()
        for invitation in invitations:
            if invitation.state() != "INVALID":
                if not (yield self.validUserIDForShare("urn:uuid:" + invitation.shareeUID(), request)):
                    yield self._updateInvitation(invitation, state="INVALID")

        returnValue(len(invitations))


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
    def _createInvitation(self, shareeUID, access, summary,):
        '''
        Create a new homeChild and wrap it in an Invitation
        '''
        if self.isCalendarCollection():
            shareeHome = yield self._newStoreObject._txn.calendarHomeWithUID(shareeUID, create=True)
        elif self.isAddressBookCollection() or self.isGroup():
            shareeHome = yield self._newStoreObject._txn.addressbookHomeWithUID(shareeUID, create=True)

        sharedName = yield self._newStoreObject.shareWith(shareeHome,
                                                    mode=invitationAccessToBindModeMap[access],
                                                    status=_BIND_STATUS_INVITED,
                                                    message=summary)

        shareeHomeChild = yield shareeHome.invitedChildWithName(sharedName)
        invitation = Invitation(shareeHomeChild)
        returnValue(invitation)

    @inlineCallbacks
    def _updateInvitation(self, invitation, access=None, state=None, summary=None):
        mode = None if access is None else invitationAccessToBindModeMap[access]
        status = None if state is None else invitationStateToBindStatusMap[state]

        yield self._newStoreObject.updateShare(invitation._shareeHomeChild, mode=mode, status=status, message=summary)
        assert not access or access == invitation.access(), "access=%s != invitation.access()=%s" % (access, invitation.access())
        assert not state or state == invitation.state(), "state=%s != invitation.state()=%s" % (state, invitation.state())
        assert not summary or summary == invitation.summary(), "summary=%s != invitation.summary()=%s" % (summary, invitation.summary())


    @inlineCallbacks
    def _allInvitations(self, includeAccepted=True):
        """
        Get list of all invitations to this object
        
        For legacy reasons, all invitations are all invited + shared (accepted, not direct).
        Combine these two into a single sorted list so code is similar to that for legacy invite db
        """
        if not self.exists():
            returnValue([])

        invitedHomeChildren = yield self._newStoreObject.asInvited()
        if includeAccepted:
            acceptedHomeChildren = yield self._newStoreObject.asShared()
            # remove direct shares (it might be OK not to remove these, that would be different from legacy code)
            indirectAccceptedHomeChildren = [homeChild for homeChild in acceptedHomeChildren
                                             if homeChild.shareMode() != _BIND_MODE_DIRECT]
            invitedHomeChildren += indirectAccceptedHomeChildren

        invitations = [Invitation(homeChild) for homeChild in invitedHomeChildren]
        invitations.sort(key=lambda invitation:invitation.shareeUID())

        returnValue(invitations)

    @inlineCallbacks
    def _invitationForShareeUID(self, shareeUID, includeAccepted=True):
        """
        Get an invitation for this sharee principal UID
        """
        invitations = yield self._allInvitations(includeAccepted=includeAccepted)
        for invitation in invitations:
            if invitation.shareeUID() == shareeUID:
                returnValue(invitation)
        returnValue(None)


    @inlineCallbacks
    def _invitationForUID(self, uid, includeAccepted=True):
        """
        Get an invitation for an invitations uid 
        """
        invitations = yield self._allInvitations(includeAccepted=includeAccepted)
        for invitation in invitations:
            if invitation.uid() == uid:
                returnValue(invitation)
        returnValue(None)



    @inlineCallbacks
    def inviteSingleUserToShare(self, userid, cn, ace, summary, request):

        # We currently only handle local users
        sharee = self.principalForCalendarUserAddress(userid)
        if not sharee:
            returnValue(False)

        shareeUID = sharee.principalUID()

        # Look for existing invite and update its fields or create new one
        invitation = yield self._invitationForShareeUID(shareeUID)
        if invitation:
            yield self._updateInvitation(invitation, access=invitationAccessMapFromXML[type(ace)], summary=summary)
        else:
            invitation = yield self._createInvitation(
                                shareeUID=shareeUID,
                                access=invitationAccessMapFromXML[type(ace)],
                                summary=summary)
        # Send invite notification
        yield self.sendInviteNotification(invitation, request)

        returnValue(True)


    @inlineCallbacks
    def uninviteSingleUserFromShare(self, userid, aces, request):
        # Cancel invites - we'll just use whatever userid we are given

        sharee = self.principalForCalendarUserAddress(userid)
        if not sharee:
            returnValue(False)

        shareeUID = sharee.principalUID()

        invitation = yield self._invitationForShareeUID(shareeUID)
        if invitation:
            result = (yield self.uninviteFromShare(invitation, request))
        else:
            result = False

        returnValue(result)


    @inlineCallbacks
    def uninviteFromShare(self, invitation, request):

        # Remove any shared calendar or address book
        sharee = self.principalForUID(invitation.shareeUID())
        if sharee:
            if self.isCalendarCollection():
                shareeHomeResource = yield sharee.calendarHome(request)
            elif self.isAddressBookCollection() or self.isGroup():
                shareeHomeResource = yield sharee.addressBookHome(request)
            displayName = (yield shareeHomeResource.removeShareByUID(request, invitation.uid()))
            # If current user state is accepted then we send an invite with the new state, otherwise
            # we cancel any existing invites for the user
            if invitation and invitation.state() != "ACCEPTED":
                yield self.removeInviteNotification(invitation, request)
            elif invitation:
                yield self.sendInviteNotification(invitation, request, displayName=displayName, notificationState="DELETED")

        # Direct shares for  with valid sharee principal will already be deleted
        yield self._newStoreObject.unshareWith(invitation._shareeHomeChild.viewerHome())

        returnValue(True)


    def inviteSingleUserUpdateToShare(self, userid, commonName, acesOLD, aceNEW, summary, request):

        # Just update existing
        return self.inviteSingleUserToShare(userid, commonName, aceNEW, summary, request)


    @inlineCallbacks
    def sendInviteNotification(self, invitation, request, notificationState=None, displayName=None):

        ownerPrincipal = (yield self.ownerPrincipal(request))
        owner = ownerPrincipal.principalURL()
        ownerCN = ownerPrincipal.displayName()
        hosturl = (yield self.canonicalURL(request))

        # Locate notifications collection for user
        sharee = self.principalForUID(invitation.shareeUID())
        if sharee is None:
            raise ValueError("sharee is None but principalUID was valid before")

        # We need to look up the resource so that the response cache notifier is properly initialized
        notificationResource = (yield request.locateResource(sharee.notificationURL()))
        notifications = notificationResource._newStoreNotifications

        '''
        # Look for existing notification
        # oldnotification is not used don't query for it
        oldnotification = (yield notifications.notificationObjectWithUID(invitation.uid()))
        if oldnotification:
            # TODO: rollup changes?
            pass
        '''

        # Generate invite XML
        userid = "urn:uuid:" + invitation.shareeUID()
        state = notificationState if notificationState else invitation.state()
        summary = invitation.summary() if displayName is None else displayName

        typeAttr = {'shared-type':self.sharedResourceType()}
        xmltype = customxml.InviteNotification(**typeAttr)
        xmldata = customxml.Notification(
            customxml.DTStamp.fromString(PyCalendarDateTime.getNowUTC().getText()),
            customxml.InviteNotification(
                customxml.UID.fromString(invitation.uid()),
                element.HRef.fromString(userid),
                invitationStatusMapToXML[state](),
                customxml.InviteAccess(invitationAccessMapToXML[invitation.access()]()),
                customxml.HostURL(
                    element.HRef.fromString(hosturl),
                ),
                customxml.Organizer(
                    element.HRef.fromString(owner),
                    customxml.CommonName.fromString(ownerCN),
                ),
                customxml.InviteSummary.fromString(summary),
                self.getSupportedComponentSet() if self.isCalendarCollection() else None,
                **typeAttr
            ),
        ).toxml()

        # Add to collections
        yield notifications.writeNotificationObject(invitation.uid(), xmltype, xmldata)

    @inlineCallbacks
    def removeInviteNotification(self, invitation, request):

        # Locate notifications collection for user
        sharee = self.principalForUID(invitation.shareeUID())
        if sharee is None:
            raise ValueError("sharee is None but principalUID was valid before")
        notificationResource = (yield request.locateResource(sharee.notificationURL()))
        notifications = notificationResource._newStoreNotifications

        # Add to collections
        yield notifications.removeNotificationObjectWithUID(invitation.uid())

    @inlineCallbacks
    def _xmlHandleInvite(self, request, docroot):
        yield self.authorize(request, (element.Read(), element.Write()))
        result = (yield self._handleInvite(request, docroot))
        returnValue(result)


    @inlineCallbacks
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

        setDict, removeDict, updateinviteDict = {}, {}, {}
        okusers = set()
        badusers = set()
        for item in invitedoc.children:
            if isinstance(item, customxml.InviteSet):
                userid, cn, access, summary = _handleInviteSet(item)
                setDict[userid] = (cn, access, summary)

                # Validate each userid on add only
                uid = (yield self.validUserIDForShare(userid, request))
                (okusers if uid is not None else badusers).add(userid)
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
        numRecords = (yield self.validateInvites(request))

        # Set the sharing state on the collection
        shared = (yield self.isShared(request))
        if shared and numRecords == 0:
            yield self.downgradeFromShare(request)
        elif not shared and numRecords != 0:
            self.upgradeToShare()

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

    def isGroup(self):
        try:
            return self._newStoreObject._kind == _ABO_KIND_GROUP
        except AttributeError:
            return False


    def POST_handler_content_type(self, request, contentType):
        if self.isCollection() or self.isGroup():
            if contentType:
                if contentType in self._postHandlers:
                    return self._postHandlers[contentType](self, request)
                else:
                    self.log_info("Got a POST on collection or group with an unsupported content type: %s" % (contentType,))
            else:
                self.log_info("Got a POST on collection or group with no content type")
        return succeed(responsecode.FORBIDDEN)

    _postHandlers = {
        ("application", "xml") : xmlRequestHandler,
        ("text", "xml") : xmlRequestHandler,
    }

invitationAccessMapToXML = {
    "read-only"           : customxml.ReadAccess,
    "read-write"          : customxml.ReadWriteAccess,
}
invitationAccessMapFromXML = dict([(v, k) for k, v in invitationAccessMapToXML.iteritems()])

invitationStatusMapToXML = {
    "NEEDS-ACTION" : customxml.InviteStatusNoResponse,
    "ACCEPTED"     : customxml.InviteStatusAccepted,
    "DECLINED"     : customxml.InviteStatusDeclined,
    "DELETED"      : customxml.InviteStatusDeleted,
    "INVALID"      : customxml.InviteStatusInvalid,
}
invitationStatusMapFromXML = dict([(v, k) for k, v in invitationStatusMapToXML.iteritems()])

invitationStateToBindStatusMap = {
    "NEEDS-ACTION": _BIND_STATUS_INVITED,
    "ACCEPTED": _BIND_STATUS_ACCEPTED,
    "DECLINED": _BIND_STATUS_DECLINED,
    "INVALID": _BIND_STATUS_INVALID,
}
invitationStateFromBindStatusMap = dict((v, k) for k, v in invitationStateToBindStatusMap.iteritems())
invitationAccessToBindModeMap = {
    "own": _BIND_MODE_OWN,
    "read-only": _BIND_MODE_READ,
    "read-write": _BIND_MODE_WRITE,
    }
invitationAccessFromBindModeMap = dict((v, k) for k, v in invitationAccessToBindModeMap.iteritems())

class Invitation(object):
    """
        Invitation is a read-only wrapper for CommonHomeChild, that uses terms similar LegacyInvite sharing.py code base.
    """
    def __init__(self, shareeHomeChild):
        self._shareeHomeChild = shareeHomeChild

    def uid(self):
        return self._shareeHomeChild.shareUID()

    def shareeUID(self):
        return self._shareeHomeChild.viewerHome().uid()

    def access(self):
        return invitationAccessFromBindModeMap.get(self._shareeHomeChild.shareMode())

    def state(self):
        return invitationStateFromBindStatusMap.get(self._shareeHomeChild.shareStatus())

    def summary(self):
        return self._shareeHomeChild.shareMessage()


class SharedHomeMixin(LinkFollowerMixIn):
    """
    A mix-in for calendar/addressbook homes that defines the operations for
    manipulating a sharee's set of shared calendars.
    """


    @inlineCallbacks
    def provisionShare(self, child, request=None):
        share = yield self._shareForHomeChild(child._newStoreObject, request)
        if share:
            child.setShare(share)

    @inlineCallbacks
    def _shareForHomeChild(self, child, request=None):
        # Try to find a matching share
        if not child or child.owned():
            returnValue(None)

        # get the shared object's URL
        sharer = self.principalForUID(child.ownerHome().uid())

        if not request:
            # FIXEME:  Fake up a request that can be used to get the sharer home resource
            class _FakeRequest(object):pass
            fakeRequest = _FakeRequest()
            setattr(fakeRequest, TRANSACTION_KEY, self._newStoreHome._txn)
            request = fakeRequest

        if self._newStoreHome._homeType == ECALENDARTYPE:
            sharerHomeCollection = yield sharer.calendarHome(request)
        elif self._newStoreHome._homeType == EADDRESSBOOKTYPE:
            sharerHomeCollection = yield sharer.addressBookHome(request)

        itemShared = yield child.ownerHome().childWithID(child._resourceID)
        if itemShared:
            url = joinURL(sharerHomeCollection.url(), itemShared.name())
        else:
            for sharerHomeChild in (yield child.ownerHome().children()):
                itemShared = yield sharerHomeChild.objectResourceWithID(child._resourceID)
                if itemShared:
                    url = joinURL(sharerHomeCollection.url(), itemShared._parentCollection.name(), itemShared.name())
                    break

        share = Share(shareeHomeChild=child, sharerHomeChild=itemShared, url=url)

        returnValue(share)

    @inlineCallbacks
    def _shareForUID(self, shareUID, request):

        # since child.shareUID() == child.name() for indirect shares
        child = yield self._newStoreHome.childWithName(shareUID)
        if child:
            share = yield self._shareForHomeChild(child, request)
            if share and share.uid() == shareUID:
                returnValue(share)

        # find direct shares
        children = yield self._newStoreHome.children()
        for child in children:
            share = yield self._shareForHomeChild(child, request)
            if share and share.uid() == shareUID:
                returnValue(share)

        returnValue(None)

    @inlineCallbacks
    def acceptInviteShare(self, request, hostUrl, inviteUID, displayname=None):

        # Check for old share
        oldShare = yield self._shareForUID(inviteUID, request)

        # Send the invite reply then add the link
        yield self._changeShare(request, "ACCEPTED", hostUrl, inviteUID, displayname)
        if oldShare:
            share = oldShare
        else:
            sharedCollection = yield request.locateResource(hostUrl)
            shareeHomeChild = yield self._newStoreHome.childWithName(inviteUID)
            share = Share(shareeHomeChild=shareeHomeChild, sharerHomeChild=sharedCollection._newStoreObject, url=hostUrl)

        response = yield self._acceptShare(request, not oldShare, share, displayname)
        returnValue(response)


    @inlineCallbacks
    def acceptDirectShare(self, request, hostUrl, resourceUID, displayname=None):

        # Just add the link
        oldShare = yield self._shareForUID(resourceUID, request)
        if oldShare:
            share = oldShare
        else:
            sharedCollection = yield request.locateResource(hostUrl)
            sharedName = yield sharedCollection._newStoreObject.shareWith(shareeHome=self._newStoreHome,
                                                    mode=_BIND_MODE_DIRECT,
                                                    status=_BIND_STATUS_ACCEPTED,
                                                    message=displayname)

            shareeHomeChild = yield self._newStoreHome.childWithName(sharedName)
            share = Share(shareeHomeChild=shareeHomeChild, sharerHomeChild=sharedCollection._newStoreObject, url=hostUrl)

        response = yield self._acceptShare(request, not oldShare, share, displayname)
        returnValue(response)

    @inlineCallbacks
    def _acceptShare(self, request, isNewShare, share, displayname=None):

        # Get shared collection in non-share mode first
        sharedCollection = yield request.locateResource(share.url())

        # For a direct share we will copy any calendar-color over using the owners view
        color = None
        if share.direct() and isNewShare and sharedCollection.isCalendarCollection():
            try:
                color = (yield sharedCollection.readProperty(customxml.CalendarColor, request))
            except HTTPError:
                pass

        sharee = self.principalForUID(share.shareeUID())
        if sharedCollection.isCalendarCollection():
            shareeHomeResource = yield sharee.calendarHome(request)
        elif sharedCollection.isAddressBookCollection() or sharedCollection.isGroup():
            shareeHomeResource = yield sharee.addressBookHome(request)
        shareeURL = joinURL(shareeHomeResource.url(), share.name())
        shareeCollection = yield request.locateResource(shareeURL)
        shareeCollection.setShare(share)

        # Set per-user displayname or color to whatever was given
        if displayname:
            yield shareeCollection.writeProperty(element.DisplayName.fromString(displayname), request)
        if color:
            yield shareeCollection.writeProperty(customxml.CalendarColor.fromString(color), request)

        # Calendars always start out transparent and with empty default alarms
        if isNewShare and shareeCollection.isCalendarCollection():
            yield shareeCollection.writeProperty(caldavxml.ScheduleCalendarTransp(caldavxml.Transparent()), request)
            yield shareeCollection.writeProperty(caldavxml.DefaultAlarmVEventDateTime.fromString(""), request)
            yield shareeCollection.writeProperty(caldavxml.DefaultAlarmVEventDate.fromString(""), request)
            yield shareeCollection.writeProperty(caldavxml.DefaultAlarmVToDoDateTime.fromString(""), request)
            yield shareeCollection.writeProperty(caldavxml.DefaultAlarmVToDoDate.fromString(""), request)

        # Notify client of changes
        yield self.notifyChanged()

        # Return the URL of the shared collection
        returnValue(XMLResponse(
            code=responsecode.OK,
            element=customxml.SharedAs(
                element.HRef.fromString(joinURL(self.url(), share.name()))
            )
        ))


    @inlineCallbacks
    def removeShare(self, request, share):
        """
        Remove a shared collection named in resourceName
        """

        if share.direct():
            yield self.removeDirectShare(request, share)
            returnValue(None)
        else:
            # Send a decline when an invite share is removed only
            result = yield self.declineShare(request, share.url(), share.uid())
            returnValue(result)


    @inlineCallbacks
    def removeShareByUID(self, request, shareUID):
        """
        Remove a shared collection but do not send a decline back. Return the
        current display name of the shared collection.
        """

        share = yield self._shareForUID(shareUID, request)
        if share:
            displayName = (yield self.removeDirectShare(request, share))
            returnValue(displayName)
        else:
            returnValue(None)

    @inlineCallbacks
    def removeDirectShare(self, request, share):
        """
        Remove a shared collection but do not send a decline back. Return the
        current display name of the shared collection.
        """

        shareURL = joinURL(self.url(), share.name())
        shared = (yield request.locateResource(shareURL))
        displayname = shared.displayName()

        if self.isCalendarCollection():
            # For backwards compatibility we need to sync this up with the calendar-free-busy-set on the inbox
            principal = (yield self.resourceOwnerPrincipal(request))
            inboxURL = principal.scheduleInboxURL()
            if inboxURL:
                inbox = (yield request.locateResource(inboxURL))
                inbox.processFreeBusyCalendar(shareURL, False)


        if share.direct():
            yield share._sharerHomeChild.unshareWith(share._shareeHomeChild.viewerHome())
        else:
            yield share._sharerHomeChild.updateShare(share._shareeHomeChild, status=_BIND_STATUS_DECLINED)

        returnValue(displayname)


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
        ownerPrincipalUID = ownerPrincipal.principalUID()
        sharedCollection = (yield request.locateResource(hostUrl))
        if sharedCollection is None:
            # Original shared collection is gone - nothing we can do except ignore it
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "Invalid shared collection",
            ))

        # Change the record
        yield sharedCollection.changeUserInviteState(request, replytoUID, ownerPrincipalUID, state, displayname)

        yield self.sendReply(request, ownerPrincipal, sharedCollection, state, hostUrl, replytoUID, displayname)


    @inlineCallbacks
    def sendReply(self, request, shareePrincipal, sharedCollection, state, hostUrl, replytoUID, displayname=None):

        # Locate notifications collection for sharer
        sharer = (yield sharedCollection.ownerPrincipal(request))
        notificationResource = (yield request.locateResource(sharer.notificationURL()))
        notifications = notificationResource._newStoreNotifications

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
                        invitationStatusMapToXML[state](),
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
        yield notifications.writeNotificationObject(notificationUID, xmltype, xmldata)


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

class Share(object):

    def __init__(self, sharerHomeChild, shareeHomeChild, url):
        self._shareeHomeChild = shareeHomeChild
        self._sharerHomeChild = sharerHomeChild
        self._sharedResourceURL = url

    @classmethod
    def directUID(cls, shareeHome, sharerHomeChild):
        return "Direct-%s-%s" % (shareeHome._resourceID, sharerHomeChild._resourceID,)

    def uid(self):
        # Move to CommonHomeChild shareUID?
        if self._shareeHomeChild.shareMode() == _BIND_MODE_DIRECT:
            return self.directUID(shareeHome=self._shareeHomeChild.viewerHome(), sharerHomeChild=self._sharerHomeChild,)
        else:
            return self._shareeHomeChild.shareUID()

    def direct(self):
        return self._shareeHomeChild.shareMode() == _BIND_MODE_DIRECT

    def url(self):
        return self._sharedResourceURL

    def name(self):
        return self._shareeHomeChild.name()

    def summary(self):
        return self._shareeHomeChild.shareMessage()

    def shareeUID(self):
        return self._shareeHomeChild.viewerHome().uid()

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
