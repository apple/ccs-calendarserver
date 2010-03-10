##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

from twext.python.log import LoggingMixIn
from twext.web2 import responsecode
from twext.web2.dav.element.base import PCDATAElement
from twext.web2.dav.http import ErrorResponse, MultiStatusResponse
from twext.web2.dav.util import allDataFromStream
from twext.web2.http import HTTPError, Response, StatusResponse
from twisted.internet.defer import succeed, inlineCallbacks, DeferredList,\
    returnValue, fail
from twistedcaldav.config import config
from twistedcaldav.sql import AbstractSQLDatabase, db_prefix
from uuid import uuid4
from vobject.icalendar import dateTimeToString, utc
import datetime
import os
import types

__all__ = [
    "SharedCollectionMixin",
]

from twistedcaldav import customxml
from twext.web2.dav import davxml

"""
Sharing behavior
"""

class SharedCollectionMixin(object):
    
    def invitesDB(self):
        
        if not hasattr(self, "_invitesDB"):
            self._invitesDB = InvitesDatabase(self)
        return self._invitesDB

    def inviteProperty(self, request):
        
        # Build the CS:invite property from our DB
        def sharedOK(isShared):
            if config.Sharing.Enabled and isShared:
                self.validateInvites()
                return customxml.Invite(
                    *[record.makePropertyElement() for record in self.invitesDB().allRecords()]
                )
            else:
                return None
        return self.isShared(request).addCallback(sharedOK)

    def upgradeToShare(self, request):
        """ Upgrade this collection to a shared state """
        
        # For calendars we only allow upgrades is shared-scheduling is on
        if request.method not in ("MKCALENDAR", "MKCOL") and self.isCalendarCollection() and not config.Sharing.Calendars.AllowScheduling:
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Cannot upgrade to shared calendar"))

        # Change resourcetype
        rtype = self.resourceType()
        rtype = davxml.ResourceType(*(rtype.children + (customxml.SharedOwner(),)))
        self.writeDeadProperty(rtype)
        
        # Create invites database
        self.invitesDB().create()

        return succeed(True)
    
    @inlineCallbacks
    def downgradeFromShare(self, request):
        
        # Change resource type (note this might be called after deleting a resource
        # so we have to cope with that)
        rtype = self.resourceType()
        rtype = davxml.ResourceType(*([child for child in rtype.children if child != customxml.SharedOwner()]))
        self.writeDeadProperty(rtype)
        
        # Remove all invitees
        records = self.invitesDB().allRecords()
        yield self.uninviteUserToShare([record.userid for record in records], None, request)

        # Remove invites database
        self.invitesDB().remove()
        delattr(self, "_invitesDB")
    
        returnValue(True)

    def removeUserFromInvite(self, userid, request):
        """ Remove a user from this shared calendar """
        self.invitesDB().removeRecordForUserID(userid)            

        return succeed(True)

    @inlineCallbacks
    def changeUserInviteState(self, request, inviteUID, userid, state, summary=None):
        
        shared = (yield self.isShared(request))
        if not shared:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "invalid share",
            ))
            
        record = self.invitesDB().recordForInviteUID(inviteUID)
        if record is None or record.userid != userid:
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "invalid invitation uid: %s" % (inviteUID,),
            ))
        
        # Only certain states are sharer controlled
        if record.state in ("NEEDS-ACTION", "ACCEPTED", "DECLINED",):
            record.state = state
            if summary is not None:
                record.summary = summary
            self.invitesDB().addOrUpdateRecord(record)

    def isShared(self, request):
        """ Return True if this is an owner shared calendar collection """
        return succeed(self.isSpecialCollection(customxml.SharedOwner))

    def isVirtualShare(self, request):
        """ Return True if this is a shared calendar collection """
        return succeed(self.isSpecialCollection(customxml.Shared))

    def sharedResourceType(self):
        """
        Return the DAV:resourcetype stripped of any shared elements.
        """
        
        rtype = self.resourceType()
        newchildren = [child for child in rtype.children if child.qname() not in (
            customxml.SharedOwner.qname(),
        )] if rtype.children else ()
        rtype.children = newchildren if newchildren else None
        return rtype

    def validUserIDForShare(self, userid):
        """
        Test the user id to see if it is a valid identifier for sharing and return a "normalized"
        form for our own use (e.g. convert mailto: to urn:uuid).

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

    def validateInvites(self):
        """
        Make sure each userid in an invite is valid - if not re-write status.
        """
        
        records = self.invitesDB().allRecords()
        for record in records:
            if self.validUserIDForShare(record.userid) is None and record.state != "INVALID":
                record.state = "INVALID"
                self.invitesDB().addOrUpdateRecord(record)
                
    def removeVirtualShare(self, request):
        """ As user of a shared calendar, unlink this calendar collection """
        return succeed(False) 

    def getInviteUsers(self, request):
        return succeed(True)

    def sendNotificationOnChange(self, icalendarComponent, request, state="added"):
        """ Possibly send a push and or email notification on a change to a resource in a shared collection """
        return succeed(True)

    def inviteUserToShare(self, userid, ace, summary, request, commonName="", shareName="", add=True):
        """ Send out in invite first, and then add this user to the share list
            @param userid: 
            @param ace: Must be one of customxml.ReadWriteAccess or customxml.ReadAccess
        """
        
        # Check for valid userid first
        userid = self.validUserIDForShare(userid)
        if userid is None:
            return succeed(False)

        # TODO: Check if this collection is shared, and error out if it isn't
        if type(userid) is not list:
            userid = [userid]
        if type(commonName) is not list:
            commonName = [commonName]
        if type(shareName) is not list:
            shareName = [shareName]
            
        dl = [self.inviteSingleUserToShare(user, ace, summary, request, cn=cn, sn=sn) for user, cn, sn in zip(userid, commonName, shareName)]
        return DeferredList(dl).addCallback(lambda _:True)

    def uninviteUserToShare(self, userid, ace, request):
        """ Send out in uninvite first, and then remove this user from the share list."""
        
        # Do not validate the userid - we want to allow invalid users to be removed because they
        # may have been valid when added, but no longer valid now. Clients should be able to clear out
        # anything known to be invalid.

        # TODO: Check if this collection is shared, and error out if it isn't
        if type(userid) is not list:
            userid = [userid]
        return DeferredList([self.uninviteSingleUserFromShare(user, ace, request) for user in userid]).addCallback(lambda _:True)

    def inviteUserUpdateToShare(self, userid, aceOLD, aceNEW, summary, request, commonName="", shareName=""):

        # Check for valid userid first
        userid = self.validUserIDForShare(userid)
        if userid is None:
            return succeed(False)

        if type(userid) is not list:
            userid = [userid]
        if type(commonName) is not list:
            commonName = [commonName]
        if type(shareName) is not list:
            shareName = [shareName]
        dl = [self.inviteSingleUserUpdateToShare(user, aceOLD, aceNEW, summary, request, commonName=cn, shareName=sn) for user, cn, sn in zip(userid, commonName, shareName)]
        return DeferredList(dl).addCallback(lambda _:True)

    @inlineCallbacks
    def inviteSingleUserToShare(self, userid, ace, summary, request, cn="", sn=""):
        
        # Look for existing invite and update its fields or create new one
        record = self.invitesDB().recordForUserID(userid)
        if record:
            record.sequence += 1
            record.access = inviteAccessMapFromXML[type(ace)]
            record.summary = summary
        else:
            record = Invite(str(uuid4()), 1, userid, inviteAccessMapFromXML[type(ace)], "NEEDS-ACTION", summary)
        
        # Send invite
        yield self.sendInvite(record, request)
        
        # Add to database
        self.invitesDB().addOrUpdateRecord(record)
        
        returnValue(True)            

    @inlineCallbacks
    def uninviteSingleUserFromShare(self, userid, aces, request):
        
        newuserid = self.validUserIDForShare(userid)
        if newuserid:
            userid = newuserid

        # Cancel invites
        record = self.invitesDB().recordForUserID(userid)
        
        # If current user state is accepted then we send an invite with the new state, otherwise
        # we cancel any existing invites for the user
        if record and record.state != "ACCEPTED":
            yield self.removeInvite(record, request)
        elif record:
            record.state = "DELETED"
            yield self.sendInvite(record, request)

        # Remove from database
        self.invitesDB().removeRecordForUserID(userid)
        
        returnValue(True)            

    def inviteSingleUserUpdateToShare(self, userid, acesOLD, aceNEW, summary, request, commonName="", shareName=""):
        
        # Just update existing
        return self.inviteSingleUserToShare(userid, aceNEW, summary, request, commonName, shareName) 

    @inlineCallbacks
    def sendInvite(self, record, request):
        
        owner = (yield self.ownerPrincipal(request))
        owner = owner.principalURL()
        hosturl = (yield self.canonicalURL(request))

        # Locate notifications collection for user
        sharee = self.principalForCalendarUserAddress(record.userid)
        if sharee is None:
            raise ValueError("sharee is None but userid was valid before")
        notifications = (yield request.locateResource(sharee.notificationURL()))
        
        # Look for existing notification
        oldnotification = (yield notifications.getNotifictionMessageByUID(request, record.inviteuid))
        if oldnotification:
            # TODO: rollup changes?
            pass
        
        # Generate invite XML
        xmltype = customxml.InviteNotification.name
        xmldata = customxml.Notification(
            customxml.DTStamp.fromString(dateTimeToString(datetime.datetime.now(tz=utc))),
            customxml.UID.fromString(record.inviteuid),
            customxml.Sequence.fromString(str(record.sequence)),
            customxml.InviteNotification(
                davxml.HRef.fromString(record.userid),
                inviteStatusMapToXML[record.state](),
                customxml.InviteAccess(inviteAccessMapToXML[record.access]()),
                customxml.HostURL(
                    davxml.HRef.fromString(hosturl),
                ),
                self.sharedResourceType(),
                customxml.Organizer(
                    davxml.HRef.fromString(owner),
                ),
                customxml.InviteSummary.fromString(record.summary),
            ),
        ).toxml()
        
        # Add to collections
        yield notifications.addNotification(request, record.inviteuid, xmltype, xmldata)

    @inlineCallbacks
    def removeInvite(self, record, request):
        
        # Locate notifications collection for user
        sharee = self.principalForCalendarUserAddress(record.userid)
        if sharee is None:
            raise ValueError("sharee is None but userid was valid before")
        notifications = (yield request.locateResource(sharee.notificationURL()))
        
        # Add to collections
        yield notifications.deleteNotifictionMessageByUID(request, record.inviteuid)

    def xmlPOSTNoAuth(self, encoding, request):
        def _handleErrorResponse(error):
            if isinstance(error.value, HTTPError) and hasattr(error.value, "response"):
                return error.value.response
            return Response(code=responsecode.BAD_REQUEST)

        def _handleInvite(invitedoc):
            def _handleInviteSet(inviteset):
                userid = None
                access = None
                summary = None
                for item in inviteset.children:
                    if isinstance(item, davxml.HRef):
                        for attendeeItem in item.children:
                            if isinstance(attendeeItem, PCDATAElement):
                                userid = attendeeItem.data
                        continue
                    if isinstance(item, customxml.InviteSummary):
                        for summaryItem in item.children:
                            if isinstance(summaryItem, PCDATAElement):
                                summary = summaryItem.data
                        continue
                    if isinstance(item, customxml.ReadAccess) or isinstance(item, customxml.ReadWriteAccess):
                        access = item
                        continue
                if userid and access and summary:
                    return (userid, access, summary)
                else:
                    if userid is None:
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (customxml.calendarserver_namespace, "valid-request"),
                            "missing href: %s" % (inviteset,),
                        ))
                    if access is None:
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (customxml.calendarserver_namespace, "valid-request"),
                            "missing access: %s" % (inviteset,),
                        ))
                    if summary is None:
                        raise HTTPError(ErrorResponse(
                            responsecode.FORBIDDEN,
                            (customxml.calendarserver_namespace, "valid-request"),
                            "missing summary: %s" % (inviteset,),
                        ))

            def _handleInviteRemove(inviteremove):
                userid = None
                access = []
                for item in inviteremove.children:
                    if isinstance(item, davxml.HRef):
                        for attendeeItem in item.children:
                            if isinstance(attendeeItem, PCDATAElement):
                                userid = attendeeItem.data
                        continue
                    if isinstance(item, customxml.ReadAccess) or isinstance(item, customxml.ReadWriteAccess):
                        access.append(item)
                        continue
                if userid is None:
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (customxml.calendarserver_namespace, "valid-request"),
                        "missing href: %s" % (inviteremove,),
                    ))
                if len(access) == 0:
                    access = None
                else:
                    access = set(access)
                return (userid, access)

            def _autoShare(isShared, request):
                if not isShared:
                    if not self.isCalendarCollection() or config.Sharing.Calendars.AllowScheduling:
                        return self.upgradeToShare(request)
                else:
                    return succeed(True)
                return fail()

            @inlineCallbacks
            def _processInviteDoc(_, request):
                setDict, removeDict, updateinviteDict = {}, {}, {}
                for item in invitedoc.children:
                    if isinstance(item, customxml.InviteSet):
                        userid, access, summary = _handleInviteSet(item)
                        setDict[userid] = (access, summary)
                    elif isinstance(item, customxml.InviteRemove):
                        userid, access = _handleInviteRemove(item)
                        removeDict[userid] = access

                # Special case removing and adding the same user and treat that as an add
                okusers = set()
                badusers = set()
                sameUseridInRemoveAndSet = [u for u in removeDict.keys() if u in setDict]
                for u in sameUseridInRemoveAndSet:
                    removeACL = removeDict[u]
                    newACL, summary = setDict[u]
                    updateinviteDict[u] = (removeACL, newACL, summary)
                    del removeDict[u]
                    del setDict[u]
                for userid, access in removeDict.iteritems():
                    result = (yield self.uninviteUserToShare(userid, access, request))
                    (okusers if result else badusers).add(userid)
                for userid, (access, summary) in setDict.iteritems():
                    result = (yield self.inviteUserToShare(userid, access, summary, request))
                    (okusers if result else badusers).add(userid)
                for userid, (removeACL, newACL, summary) in updateinviteDict.iteritems():
                    result = (yield self.inviteUserUpdateToShare(userid, removeACL, newACL, summary, request))
                    (okusers if result else badusers).add(userid)

                # Do a final validation of the entire set of invites
                self.validateInvites()
                
                # Create the multistatus response - only needed if some are bad
                if badusers:
                    xml_responses = []
                    xml_responses.extend([
                        davxml.StatusResponse(davxml.HRef(userid), davxml.Status.fromResponseCode(responsecode.OK))
                        for userid in sorted(okusers)
                    ])
                    xml_responses.extend([
                        davxml.StatusResponse(davxml.HRef(userid), davxml.Status.fromResponseCode(responsecode.FORBIDDEN))
                        for userid in sorted(badusers)
                    ])
                
                    #
                    # Return response
                    #
                    returnValue(MultiStatusResponse(xml_responses))
                else:
                    returnValue(responsecode.OK)
                    

            return self.isShared(request).addCallback(_autoShare, request).addCallback(_processInviteDoc, request)

        def _getData(data):
            try:
                doc = davxml.WebDAVDocument.fromString(data)
            except ValueError, e:
                self.log_error("Error parsing doc (%s) Doc:\n %s" % (str(e), data,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (customxml.calendarserver_namespace, "valid-request")))

            root = doc.root_element
            xmlDocHanders = {
                customxml.InviteShare: _handleInvite, 
            }
            if type(root) in xmlDocHanders:
                return xmlDocHanders[type(root)](root).addErrback(_handleErrorResponse)
            else:
                self.log_error("Unsupported XML (%s)" % (root,))
                raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (customxml.calendarserver_namespace, "valid-request")))

        return allDataFromStream(request.stream).addCallback(_getData)

    def xmlPOSTPreconditions(self, _, request):
        if request.headers.hasHeader("Content-Type"):
            mimetype = request.headers.getHeader("Content-Type")
            if mimetype.mediaType in ("application", "text",) and mimetype.mediaSubtype == "xml":
                encoding = mimetype.params["charset"] if "charset" in mimetype.params else "utf8"
                return succeed(encoding)
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (customxml.calendarserver_namespace, "valid-request")))

    def xmlPOSTAuth(self, request):
        d = self.authorize(request, (davxml.Read(), davxml.Write()))
        d.addCallback(self.xmlPOSTPreconditions, request)
        d.addCallback(self.xmlPOSTNoAuth, request)
        return d
    
    def http_POST(self, request):
        if self.isCollection():
            contentType = request.headers.getHeader("content-type")
            if contentType:
                contentType = (contentType.mediaType, contentType.mediaSubtype)
                if contentType in self._postHandlers:
                    return self._postHandlers[contentType](self, request)
                else:
                    self.log_info("Get a POST of an unsupported content type on a collection type: %s" % (contentType,))
            else:
                self.log_info("Get a POST with no content type on a collection")
        return responsecode.FORBIDDEN

    _postHandlers = {
        ("application", "xml") : xmlPOSTAuth,
        ("text", "xml") : xmlPOSTAuth,
    }

class SharedHomeMixin(object):
    """
    A mix-in for calendar/addressbook homes that defines the operations for manipulating a sharee's
    set of shared calendfars.
    """
    
    def acceptShare(self, request, hostUrl, inviteUID, displayname=None):
        return self._changeShare(request, "ACCEPTED", hostUrl, inviteUID, displayname)

    def wouldAcceptShare(self, hostUrl, request):
        return succeed(True)

    def removeShare(self, request, hostUrl, resourceName):
        """ Remove a shared calendar named in resourceName """
        return succeed(True)

    def declineShare(self, request, hostUrl, inviteUID):
        return self._changeShare(request, "DECLINED", hostUrl, inviteUID)

    @inlineCallbacks
    def _changeShare(self, request, state, hostUrl, inviteUID, displayname=None):
        """ Accept an invite to a shared calendar """
        
        # Change state in sharer invite
        owner = (yield self.ownerPrincipal(request))
        owner = owner.principalURL()
        sharedCalendar = (yield request.locateResource(hostUrl))
        if sharedCalendar is None:
            # Original shared calendar is gone - nothing we can do except ignore it
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (customxml.calendarserver_namespace, "valid-request"),
                "invalid shared calendar",
            ))
            
        # Change the record
        yield sharedCalendar.changeUserInviteState(request, inviteUID, owner, state, displayname)

    def xmlPOSTNoAuth(self, encoding, request):
        def _handleResponse(result):
            response = Response(code=responsecode.OK)
            return response

        def _handleErrorResponse(error):
            if isinstance(error.value, HTTPError) and hasattr(error.value, "response"):
                return error.value.response
            return Response(code=responsecode.BAD_REQUEST)

        def _handleInviteUpdate(inviteupdatedoc):
            """ Handle a user accepting or declining a sharing invite """
            hostUrl = None
            accepted = None
            summary = None
            inviteUID = None
            for item in inviteupdatedoc.children:
                if isinstance(item, customxml.InviteStatusAccepted):
                    accepted = True
                elif isinstance(item, customxml.InviteStatusDeclined):
                    accepted = False
                elif isinstance(item, customxml.InviteSummary):
                    for summaryitem in item.children:
                        if isinstance(summaryitem, PCDATAElement):
                            summary = summaryitem.data
                elif isinstance(item, customxml.HostURL):
                    for hosturlItem in item.children:
                        if isinstance(hosturlItem, davxml.HRef):
                            for hrefItem in hosturlItem.children:
                                if isinstance(hrefItem, PCDATAElement):
                                    hostUrl = hrefItem.data
                elif isinstance(item, customxml.UID):
                    inviteUID = str(item)
            
            if accepted is None or hostUrl is None or inviteUID is None:
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (customxml.calendarserver_namespace, "valid-request"),
                    "missing required XML elements",
                ))
            if accepted:
                return self.acceptShare(request, hostUrl, inviteUID, displayname=summary)
            else:
                return self.declineShare(request, hostUrl, inviteUID)

        def _getData(data):
            try:
                doc = davxml.WebDAVDocument.fromString(data)
            except ValueError, e:
                print "Error parsing doc (%s) Doc:\n %s" % (str(e), data,)
                raise

            root = doc.root_element
            xmlDocHanders = {
                customxml.InviteNotification: _handleInviteUpdate,          
            }
            if type(root) in xmlDocHanders:
                return xmlDocHanders[type(root)](root).addCallbacks(_handleResponse, errback=_handleErrorResponse)
            else:
                return fail(True)

        return allDataFromStream(request.stream).addCallback(_getData)

inviteAccessMapToXML = {
    "read-only"  : customxml.ReadAccess,
    "read-write" : customxml.ReadWriteAccess,
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
    
    def __init__(self, inviteuid, sequence, userid, access, state, summary):
        self.inviteuid = inviteuid
        self.sequence = sequence
        self.userid = userid
        self.access = access
        self.state = state
        self.summary = summary
        
    def makePropertyElement(self):
        
        return customxml.InviteUser(
            customxml.UID.fromString(self.inviteuid),
            davxml.HRef.fromString(self.userid),
            customxml.InviteAccess(inviteAccessMapToXML[self.access]()),
            inviteStatusMapToXML[self.state](),
        )

class InvitesDatabase(AbstractSQLDatabase, LoggingMixIn):
    
    db_basename = db_prefix + "invites"
    schema_version = "1"
    db_type = "invites"

    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource for
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

    def allRecords(self):
        
        records = self._db_execute("select * from INVITE order by USERID")
        return [self._makeRecord(row) for row in (records if records is not None else ())]
    
    def recordForUserID(self, userid):
        
        row = self._db_execute("select * from INVITE where USERID = :1", userid)
        return self._makeRecord(row[0]) if row else None
    
    def recordForInviteUID(self, inviteUID):

        row = self._db_execute("select * from INVITE where INVITEUID = :1", inviteUID)
        return self._makeRecord(row[0]) if row else None
    
    def addOrUpdateRecord(self, record):

        self._db_execute("""insert or replace into INVITE (INVITEUID, SEQUENCE, USERID, ACCESS, STATE, SUMMARY)
            values (:1, :2, :3, :4, :5, :6)
            """, record.inviteuid, record.sequence, record.userid, record.access, record.state, record.summary,
        )
    
    def removeRecordForUserID(self, userid):

        self._db_execute("delete from INVITE where USERID = :1", userid)
    
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
        #   SEQUENCE: sequence number for this invite
        #   NAME: identifier of invitee
        #   ACCESS: Access mode for share
        #   STATE: Invite response status
        #   SUMMARY: Invite summary
        #
        q.execute(
            """
            create table INVITE (
                INVITEUID      text unique,
                SEQUENCE       integer,
                USERID         text unique,
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

