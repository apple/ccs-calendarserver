##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
Directory service implementation for users who are allowed to authorize
as other principals.
"""

__all__ = [
    "WikiDirectoryService",
]

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.web2.dav import davxml
from twisted.web.xmlrpc import Proxy, Fault
from twext.web2.http import HTTPError, StatusResponse
from twext.web2.auth.wrapper import UnauthorizedResponse
from twext.web2 import responsecode

from twext.python.log import Logger

from twext.web2.dav.resource import TwistedACLInheritable
from twistedcaldav.config import config
from twistedcaldav.directory.directory import (DirectoryService,
                                               DirectoryRecord,
                                               UnknownRecordTypeError)

log = Logger()

class WikiDirectoryService(DirectoryService):
    """
    L{IDirectoryService} implementation for Wikis.
    """
    baseGUID = "D79EF1E0-9A42-11DD-AD8B-0800200C9A66"

    realmName = None

    recordType_wikis = "wikis"

    UIDPrefix = "wiki-"


    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.realmName)

    def __init__(self):
        super(WikiDirectoryService, self).__init__()
        self.byUID = {}
        self.byShortName = {}

    def recordTypes(self):
        return (WikiDirectoryService.recordType_wikis,)

    def listRecords(self, recordType):
        return ()

    def recordWithShortName(self, recordType, shortName):
        if recordType != WikiDirectoryService.recordType_wikis:
            raise UnknownRecordTypeError(recordType)

        if self.byShortName.has_key(shortName):
            record = self.byShortName[shortName]
            self.log_info("Returning existing wiki record with UID %s" %
                (record.uid,))
            return record

        record = self._addRecord(shortName)
        return record

    def recordWithUID(self, uid):

        if self.byUID.has_key(uid):
            record = self.byUID[uid]
            self.log_info("Returning existing wiki record with UID %s" %
                (record.uid,))
            return record

        if uid.startswith(self.UIDPrefix):
            shortName = uid[len(self.UIDPrefix):]
            record = self._addRecord(shortName)
            return record
        else:
            return None

    def _addRecord(self, shortName):

        record = WikiDirectoryRecord(
            self,
            WikiDirectoryService.recordType_wikis,
            shortName,
            None
        )
        self.log_info("Creating wiki record with GUID %s" % (record.guid,))
        self.byUID[record.uid] = record
        self.byShortName[shortName] = record
        return record


class WikiDirectoryRecord(DirectoryRecord):
    """
    L{DirectoryRecord} implementation for Wikis.
    """

    def __init__(self, service, recordType, shortName, entry):
        super(WikiDirectoryRecord, self).__init__(
            service=service,
            recordType=recordType,
            guid=None,
            shortNames=(shortName,),
            fullName=shortName,
            enabledForCalendaring=True,
            uid="%s%s" % (WikiDirectoryService.UIDPrefix, shortName),
        )
        # Wiki enabling doesn't come from augments db, so enable here...
        self.enabled = True


@inlineCallbacks
def getWikiAccess(userID, wikiID, method=None):
    """
    Ask the wiki server we're paired with what level of access the userID has
    for the given wikiID.  Possible values are "read", "write", and "admin"
    (which we treat as "write").
    """
    wikiConfig = config.Authentication.Wiki
    if method is None:
        method = Proxy(wikiConfig["URL"]).callRemote
    try:

        log.debug("Looking up Wiki ACL for: user [%s], wiki [%s]" % (userID,
            wikiID))
        access = (yield method(wikiConfig["WikiMethod"],
            userID, wikiID))

        log.debug("Wiki ACL result: user [%s], wiki [%s], access [%s]" % (userID,
            wikiID, access))
        returnValue(access)

    except Fault, fault:

        log.debug("Wiki ACL result: user [%s], wiki [%s], FAULT [%s]" % (userID,
            wikiID, fault))

        if fault.faultCode == 2: # non-existent user
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN,
                fault.faultString))

        elif fault.faultCode == 12: # non-existent wiki
            raise HTTPError(StatusResponse(responsecode.NOT_FOUND,
                fault.faultString))

        else: # Unknown fault returned from wiki server.  Log the error and
              # return 503 Service Unavailable to the client.
            log.error("Wiki ACL error: user [%s], wiki [%s], FAULT [%s]" %
                (userID, wikiID, fault))
            raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE,
                fault.faultString))


@inlineCallbacks
def getWikiACL(resource, request):
    """
    Ask the wiki server we're paired with what level of access the authnUser has.

    Returns an ACL.

    Wiki authentication is a bit tricky because the end-user accessing a group
    calendar may not actually be enabled for calendaring.  Therefore in that
    situation, the authzUser will have been replaced with the wiki principal
    in locateChild( ), so that any changes the user makes will have the wiki
    as the originator.  The authnUser will always be the end-user.
    """
    from twistedcaldav.directory.principal import DirectoryPrincipalResource

    if (not hasattr(resource, "record") or
        resource.record.recordType != WikiDirectoryService.recordType_wikis):
        returnValue(None)

    if hasattr(request, 'wikiACL'):
        returnValue(request.wikiACL)

    userID = "unauthenticated"
    wikiID = resource.record.shortNames[0]

    try:
        url = str(request.authnUser.children[0])
        principal = (yield request.locateResource(url))
        if isinstance(principal, DirectoryPrincipalResource):
            userID = principal.record.guid
    except:
        # TODO: better error handling
        pass

    try:
        access = (yield getWikiAccess(userID, wikiID))

        # The ACL we returns has ACEs for the end-user and the wiki principal
        # in case authzUser is the wiki principal.
        if access == "read":
            request.wikiACL =   davxml.ACL(
                                    davxml.ACE(
                                        request.authnUser,
                                        davxml.Grant(
                                            davxml.Privilege(davxml.Read()),
                                            davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                                            
                                            # We allow write-properties so that direct sharees can change
                                            # e.g. calendar color properties
                                            davxml.Privilege(davxml.WriteProperties()),
                                        ),
                                        TwistedACLInheritable(),
                                    ),
                                    davxml.ACE(
                                        davxml.Principal(
                                            davxml.HRef.fromString("/principals/wikis/%s/" % (wikiID,))
                                        ),
                                        davxml.Grant(
                                            davxml.Privilege(davxml.Read()),
                                            davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                                        ),
                                        TwistedACLInheritable(),
                                    )
                                )
            returnValue(request.wikiACL)

        elif access in ("write", "admin"):
            request.wikiACL =   davxml.ACL(
                                    davxml.ACE(
                                        request.authnUser,
                                        davxml.Grant(
                                            davxml.Privilege(davxml.Read()),
                                            davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                                            davxml.Privilege(davxml.Write()),
                                        ),
                                        TwistedACLInheritable(),
                                    ),
                                    davxml.ACE(
                                        davxml.Principal(
                                            davxml.HRef.fromString("/principals/wikis/%s/" % (wikiID,))
                                        ),
                                        davxml.Grant(
                                            davxml.Privilege(davxml.Read()),
                                            davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                                            davxml.Privilege(davxml.Write()),
                                        ),
                                        TwistedACLInheritable(),
                                    )
                                )
            returnValue(request.wikiACL)

        else: # "no-access":

            if userID == "unauthenticated":
                # Return a 401 so they have an opportunity to log in
                response = (yield UnauthorizedResponse.makeResponse(
                    request.credentialFactories,
                    request.remoteAddr,
                ))
                raise HTTPError(response)

            raise HTTPError(
                StatusResponse(
                    responsecode.FORBIDDEN,
                    "You are not allowed to access this wiki"
                )
            )

    except HTTPError:
        # pass through the HTTPError we might have raised above
        raise

    except Exception, e:
        log.error("Wiki ACL RPC failed: %s" % (e,))
        raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE, "Wiki ACL RPC failed"))
