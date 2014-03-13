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
Calendar/Contacts specific methods for DirectoryRecord
"""


import uuid

from twext.python.log import Logger
from twext.who.expression import (
    MatchType, Operand, MatchExpression, CompoundExpression, MatchFlags
)
from twext.who.idirectory import RecordType as BaseRecordType
from twisted.cred.credentials import UsernamePassword
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.caldav.datastore.scheduling.cuaddress import normalizeCUAddr
from txdav.who.idirectory import RecordType as DAVRecordType
from txweb2.auth.digest import DigestedCredentials


log = Logger()


__all__ = [
    "CalendarDirectoryRecordMixin",
    "CalendarDirectoryServiceMixin",
]


class CalendarDirectoryServiceMixin(object):

    guid = "1332A615-4D3A-41FE-B636-FBE25BFB982E"

    # Must maintain the hack for a bit longer:
    def setPrincipalCollection(self, principalCollection):
        """
        Set the principal service that the directory relies on for doing proxy tests.

        @param principalService: the principal service.
        @type principalService: L{DirectoryProvisioningResource}
        """
        self.principalCollection = principalCollection


    @inlineCallbacks
    def recordWithCalendarUserAddress(self, address):
        address = normalizeCUAddr(address)
        record = None
        if address.startswith("urn:uuid:"):
            guid = address[9:]
            record = yield self.recordWithGUID(uuid.UUID(guid))
        elif address.startswith("mailto:"):
            records = yield self.recordsWithEmailAddress(address[7:])
            if records:
                returnValue(records[0])
            else:
                returnValue(None)
        elif address.startswith("/principals/"):
            parts = address.split("/")
            if len(parts) == 4:
                if parts[2] == "__uids__":
                    uid = parts[3]
                    record = yield self.recordWithUID(uid)
                else:
                    recordType = self.fieldName.lookupByName(parts[2])
                    record = yield self.recordWithShortName(recordType, parts[3])

        returnValue(record if record and record.hasCalendars else None)


    def recordsMatchingTokens(self, tokens, context=None, limitResults=50,
                              timeoutSeconds=10):
        fields = [
            ("fullNames", MatchType.contains),
            ("emailAddresses", MatchType.startsWith),
        ]
        outer = []
        for token in tokens:
            inner = []
            for name, matchType in fields:
                inner.append(
                    MatchExpression(
                        self.fieldName.lookupByName(name),
                        token,
                        matchType,
                        MatchFlags.caseInsensitive
                    )
                )
            outer.append(
                CompoundExpression(
                    inner,
                    Operand.OR
                )
            )
        expression = CompoundExpression(outer, Operand.AND)
        return self.recordsFromExpression(expression)


    def recordsMatchingFieldsWithCUType(self, fields, operand=Operand.OR,
                                        cuType=None):
        if cuType:
            recordType = CalendarDirectoryRecordMixin.fromCUType(cuType)
        else:
            recordType = None

        return self.recordsMatchingFields(
            fields, operand=operand, recordType=recordType
        )


    def recordsMatchingFields(self, fields, operand=Operand.OR, recordType=None):
        """
        @param fields: a iterable of tuples, each tuple consisting of:
            directory field name (C{unicode})
            search term (C{unicode})
            match flags (L{twext.who.expression.MatchFlags})
            match type (L{twext.who.expression.MatchType})
        """
        subExpressions = []
        for fieldName, searchTerm, matchFlags, matchType in fields:
            subExpression = MatchExpression(
                self.fieldName.lookupByName(fieldName),
                searchTerm,
                matchType,
                matchFlags
            )
            subExpressions.append(subExpression)

        expression = CompoundExpression(subExpressions, operand)
        return self.recordsFromExpression(expression)


    # FIXME: Existing code assumes record type names are plural. Is there any
    # reason to maintain backwards compatibility?  I suppose there could be
    # scripts referring to record type of "users", "locations"
    def recordTypeToOldName(self, recordType):
        return recordType.name + u"s"


    def oldNameToRecordType(self, oldName):
        return self.recordType.lookupByName(oldName[:-1])



class CalendarDirectoryRecordMixin(object):


    @inlineCallbacks
    def verifyCredentials(self, credentials):

        # XYZZY REMOVE THIS, it bypasses all authentication!:
        returnValue(True)

        if isinstance(credentials, UsernamePassword):
            log.debug("UsernamePassword")
            returnValue(
                (yield self.verifyPlaintextPassword(credentials.password))
            )

        elif isinstance(credentials, DigestedCredentials):
            log.debug("DigestedCredentials")
            returnValue(
                (yield self.verifyHTTPDigest(
                    self.shortNames[0],
                    self.service.realmName,
                    credentials.fields["uri"],
                    credentials.fields["nonce"],
                    credentials.fields.get("cnonce", ""),
                    credentials.fields["algorithm"],
                    credentials.fields.get("nc", ""),
                    credentials.fields.get("qop", ""),
                    credentials.fields["response"],
                    credentials.method
                ))
            )


    @property
    def calendarUserAddresses(self):
        if not self.hasCalendars:
            return frozenset()

        try:
            cuas = set(
                ["mailto:%s" % (emailAddress,)
                 for emailAddress in self.emailAddresses]
            )
        except AttributeError:
            cuas = set()

        try:
            if self.guid:
                if isinstance(self.guid, uuid.UUID):
                    guid = unicode(self.guid).upper()
                else:
                    guid = self.guid
                cuas.add("urn:uuid:{guid}".format(guid=guid))
        except AttributeError:
            # No guid
            pass
        cuas.add("/principals/__uids__/{uid}/".format(uid=self.uid))
        for shortName in self.shortNames:
            cuas.add("/principals/{rt}/{sn}/".format(
                rt=self.recordType.name + "s", sn=shortName)
            )
        return frozenset(cuas)


    # Mapping from directory record.recordType to RFC2445 CUTYPE values
    _cuTypes = {
        BaseRecordType.user: 'INDIVIDUAL',
        BaseRecordType.group: 'GROUP',
        DAVRecordType.resource: 'RESOURCE',
        DAVRecordType.location: 'ROOM',
    }


    def getCUType(self):
        return self._cuTypes.get(self.recordType, "UNKNOWN")


    @classmethod
    def fromCUType(cls, cuType):
        for key, val in cls._cuTypes.iteritems():
            if val == cuType:
                return key
        return None


    def applySACLs(self):
        """
        Disable calendaring and addressbooks as dictated by SACLs
        """

        # FIXME: need to re-implement SACLs
        # if config.EnableSACLs and self.CheckSACL:
        #     username = self.shortNames[0]
        #     if self.CheckSACL(username, "calendar") != 0:
        #         self.log.debug("%s is not enabled for calendaring due to SACL"
        #                        % (username,))
        #         self.enabledForCalendaring = False
        #     if self.CheckSACL(username, "addressbook") != 0:
        #         self.log.debug("%s is not enabled for addressbooks due to SACL"
        #                        % (username,))
        #         self.enabledForAddressBooks = False


    @property
    def displayName(self):
        return self.fullNames[0]


    def cacheToken(self):
        """
        Generate a token that can be uniquely used to identify the state of this record for use
        in a cache.
        """
        return hash((
            self.__class__.__name__,
            self.service.realmName,
            self.recordType.name,
            self.shortNames,
            self.uid,
            self.hasCalendars,
        ))


    def canonicalCalendarUserAddress(self):
        """
            Return a CUA for this record, preferring in this order:
            urn:uuid: form
            mailto: form
            first in calendarUserAddresses list
        """

        cua = ""
        for candidate in self.calendarUserAddresses:
            # Pick the first one, but urn:uuid: and mailto: can override
            if not cua:
                cua = candidate
            # But always immediately choose the urn:uuid: form
            if candidate.startswith("urn:uuid:"):
                cua = candidate
                break
            # Prefer mailto: if no urn:uuid:
            elif candidate.startswith("mailto:"):
                cua = candidate
        return cua


    def enabledAsOrganizer(self):
        # MOVE2WHO FIXME TO LOOK AT CONFIG
        if self.recordType == self.service.recordType.user:
            return True
        elif self.recordType == self.service.recordType.group:
            return False  # config.Scheduling.Options.AllowGroupAsOrganizer
        elif self.recordType == self.service.recordType.location:
            return False  # config.Scheduling.Options.AllowLocationAsOrganizer
        elif self.recordType == self.service.recordType.resource:
            return False  # config.Scheduling.Options.AllowResourceAsOrganizer
        else:
            return False


    #MOVE2WHO
    def thisServer(self):
        return True


    def isLoginEnabled(self):
        return self.loginAllowed


    #MOVE2WHO
    def calendarsEnabled(self):
        # In the old world, this *also* looked at config:
        # return config.EnableCalDAV and self.enabledForCalendaring
        return self.hasCalendars


    def getAutoScheduleMode(self, organizer):
        # MOVE2WHO Fix this to take organizer into account:
        return self.autoScheduleMode


    def canAutoSchedule(self, organizer=None):
        # MOVE2WHO Fix this:
        return True
