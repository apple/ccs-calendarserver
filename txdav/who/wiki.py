##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
Mac OS X Server Wiki directory service.
"""

__all__ = [
    "DirectoryService",
    "WikiAccessLevel",
]

from calendarserver.platform.darwin.wiki import accessForUserToWiki
from twext.internet.gaiendpoint import MultiFailure
from twext.python.log import Logger
from twext.who.directory import (
    DirectoryService as BaseDirectoryService,
    DirectoryRecord as BaseDirectoryRecord
)
from twext.who.idirectory import FieldName as BaseFieldName
from twext.who.util import ConstantsContainer
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python.constants import Names, NamedConstant
from twisted.web.error import Error as WebError
from txdav.who.idirectory import FieldName
from txdav.who.directory import CalendarDirectoryRecordMixin
from txdav.xml import element as davxml
from txweb2 import responsecode
from txweb2.auth.wrapper import UnauthorizedResponse
from txweb2.dav.resource import TwistedACLInheritable
from txweb2.http import HTTPError, StatusResponse


log = Logger()


# FIXME: Should this be Flags?
class WikiAccessLevel(Names):
    none  = NamedConstant()
    read  = NamedConstant()
    write = NamedConstant()



class RecordType(Names):
    macOSXServerWiki = NamedConstant()
    macOSXServerWiki.description = u"Mac OS X Server Wiki"



class DirectoryService(BaseDirectoryService):
    """
    Mac OS X Server Wiki directory service.
    """

    uidPrefix = u"[wiki]"

    recordType = RecordType

    fieldName = ConstantsContainer((
        BaseFieldName,
        FieldName,
    ))


    def __init__(self, realmName, wikiHost, wikiPort):
        BaseDirectoryService.__init__(self, realmName)
        self.wikiHost = wikiHost
        self.wikiPort = wikiPort
        self._recordsByName = {}


    # This directory service is rather limited in its skills.
    # We don't attempt to implement any expression handling (ie.
    # recordsFromNonCompoundExpression), and only support a couple of the
    # recordWith* convenience methods.

    def _recordWithName(self, name):
        record = self._recordsByName.get(name)

        if record is not None:
            return succeed(record)

        # FIXME: RPC to the wiki and check for existance of a wiki with the
        # given name...
        #
        # NOTE: Don't use the config module here; pass whatever info we need to
        # __init__().
        wikiExists = True

        if wikiExists:
            record = DirectoryRecord(
                self,
                {
                    self.fieldName.uid: u"{}{}".format(self.uidPrefix, name),
                    self.fieldName.recordType: RecordType.macOSXServerWiki,
                    self.fieldName.shortNames: [name],
                    self.fieldName.fullNames: [u"Wiki: {}".format(name)],
                }
            )
            self._recordsByName[name] = record
            return succeed(record)

        return succeed(None)


    def recordWithUID(self, uid):
        if uid.startswith(self.uidPrefix):
            return self._recordWithName(uid[len(self.uidPrefix):])
        return succeed(None)


    def recordWithShortName(self, recordType, shortName):
        if recordType is RecordType.macOSXServerWiki:
            return self._recordWithName(shortName)
        return succeed(None)


    def recordsFromExpression(self, expression, records=None):
        return succeed(())



class DirectoryRecord(BaseDirectoryRecord, CalendarDirectoryRecordMixin):
    """
    Mac OS X Server Wiki directory record.
    """

    log = Logger()


    @property
    def name(self):
        return self.shortNames[0]


    @inlineCallbacks
    def accessForRecord(self, record):
        """
        Look up the access level for a record in this wiki.

        @param user: The record to check access for.  A value of None means
            unauthenticated
        """
        if record is None:
            uid = u"unauthenticated"
        else:
            uid = record.uid

        try:
            # FIXME: accessForUserToWiki() API is lame.
            # There are no other callers except the old directory API, so
            # nuke it from the originating module and move that logic here
            # once the old API is removed.
            # When we do that note: isn't there a getPage() in twisted.web?

            access = yield accessForUserToWiki(
                uid, self.shortNames[0],
                host=self.service.wikiHost,
                port=self.service.wikiPort,
            )

        except MultiFailure as e:
            self.log.error(
                "Unable to look up access for record {record} "
                "in wiki {log_source}: {error}",
                record=record, error=e
            )

        except WebError as e:
            status = int(e.status)

            if status == responsecode.FORBIDDEN:  # Unknown user
                self.log.debug(
                    "No such record (according to wiki): {record}",
                    record=record, error=e
                )
                returnValue(WikiAccessLevel.none)

            if status == responsecode.NOT_FOUND:  # Unknown wiki
                self.log.error(
                    "No such wiki: {log_source.name}",
                    record=record, error=e
                )
                returnValue(WikiAccessLevel.none)

            self.log.error(
                "Unable to look up wiki access: {error}",
                record=record, error=e
            )

        try:
            returnValue({
                "no-access": WikiAccessLevel.none,
                "read": WikiAccessLevel.read,
                "write": WikiAccessLevel.write,
                "admin": WikiAccessLevel.write,
            }[access])

        except KeyError:
            self.log.error("Unknown wiki access level: {level}", level=access)
            returnValue(WikiAccessLevel.none)


@inlineCallbacks
def getWikiACL(resource, request):
    """
    Ask the wiki server we're paired with what level of access the authnUser
    has.

    Returns an ACL.

    Wiki authentication is a bit tricky because the end-user accessing a group
    calendar may not actually be enabled for calendaring.  Therefore in that
    situation, the authzUser will have been replaced with the wiki principal
    in locateChild( ), so that any changes the user makes will have the wiki
    as the originator.  The authnUser will always be the end-user.
    """
    from twistedcaldav.directory.principal import DirectoryPrincipalResource

    if (
        not hasattr(resource, "record") or
        resource.record.recordType != RecordType.macOSXServerWiki
    ):
        returnValue(None)

    if hasattr(request, 'wikiACL'):
        returnValue(request.wikiACL)

    wikiRecord = resource.record
    wikiID = wikiRecord.shortNames[0]
    userRecord = None

    try:
        url = str(request.authnUser.children[0])
        principal = (yield request.locateResource(url))
        if isinstance(principal, DirectoryPrincipalResource):
            userRecord = principal.record
    except:
        # TODO: better error handling
        pass

    try:
        access = yield wikiRecord.accessForRecord(userRecord)

        # The ACL we returns has ACEs for the end-user and the wiki principal
        # in case authzUser is the wiki principal.
        if access == WikiAccessLevel.read:
            request.wikiACL = davxml.ACL(
                davxml.ACE(
                    request.authnUser,
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),

                        # We allow write-properties so that direct sharees can
                        # change e.g. calendar color properties
                        davxml.Privilege(davxml.WriteProperties()),
                    ),
                    TwistedACLInheritable(),
                ),
                davxml.ACE(
                    davxml.Principal(
                        davxml.HRef.fromString(
                            "/principals/wikis/{}/".format(wikiID)
                        )
                    ),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                    ),
                    TwistedACLInheritable(),
                )
            )
            returnValue(request.wikiACL)

        elif access == WikiAccessLevel.write:
            request.wikiACL = davxml.ACL(
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
                        davxml.HRef.fromString(
                            "/principals/wikis/{}/".format(wikiID)
                        )
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

        else:  # "no-access":

            if userRecord is None:
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

    except Exception as e:
        log.error("Wiki ACL lookup failed: {error}", error=e)
        raise HTTPError(StatusResponse(
            responsecode.SERVICE_UNAVAILABLE, "Wiki ACL lookup failed"
        ))
