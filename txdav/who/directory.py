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
from twistedcaldav.config import config
from twistedcaldav.ical import Property
from txdav.caldav.datastore.scheduling.utils import normalizeCUAddr
from txdav.who.delegates import RecordType as DelegateRecordType
from txdav.who.idirectory import (
    RecordType as DAVRecordType, AutoScheduleMode
)
from txweb2.auth.digest import DigestedCredentials


log = Logger()


__all__ = [
    "CalendarDirectoryRecordMixin",
    "CalendarDirectoryServiceMixin",
]



class CalendarDirectoryServiceMixin(object):

    guid = "1332A615-4D3A-41FE-B636-FBE25BFB982E"

    serversDB = None

    def setServersDB(self, serversDB):
        self.serversDB = serversDB


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

        if address.startswith("urn:x-uid:"):
            uid = address[10:]
            record = yield self.recordWithUID(uid)

        elif address.startswith("urn:uuid:"):
            try:
                guid = uuid.UUID(address[9:])
            except ValueError:
                log.info("Invalid GUID: {guid}", guid=address[9:])
                returnValue(None)
            record = yield self.recordWithGUID(guid)

        elif address.startswith("mailto:"):
            records = yield self.recordsWithEmailAddress(address[7:])
            record = records[0] if records else None

        elif address.startswith("/principals/"):
            parts = address.split("/")
            if len(parts) == 4:
                if parts[2] == "__uids__":
                    uid = parts[3]
                    record = yield self.recordWithUID(uid)
                else:
                    recordType = self.oldNameToRecordType(parts[2])
                    record = yield self.recordWithShortName(recordType, parts[3])

        if record:
            if record.hasCalendars or (
                config.GroupAttendees.Enabled and
                record.recordType == BaseRecordType.group
            ):
                returnValue(record)

        returnValue(None)

    searchContext_location = "location"
    searchContext_resource = "resource"
    searchContext_user     = "user"
    searchContext_group    = "group"
    searchContext_attendee = "attendee"


    def recordTypesForSearchContext(self, context):
        """
        Map calendarserver-principal-search REPORT context value to applicable record types

        @param context: The context value to map
        @type context: C{unicode}
        @returns: The list of record types the context maps to
        @rtype: C{list} of C{NamedConstant}
        """
        if context == "location":
            recordTypes = [self.recordType.location]
        elif context == "resource":
            recordTypes = [self.recordType.resource]
        elif context == "user":
            recordTypes = [self.recordType.user]
        elif context == "group":
            recordTypes = [self.recordType.group]
        elif context == "attendee":
            recordTypes = [
                self.recordType.user,
                self.recordType.group,
                self.recordType.resource
            ]
        else:
            recordTypes = list(self.recordTypes())
        return recordTypes


    @inlineCallbacks
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

        if len(outer) == 1:
            expression = outer[0]
        else:
            expression = CompoundExpression(outer, Operand.AND)

        results = []

        if context is not None:
            # We're limiting record types, so for each recordType, build a
            # CompoundExpression that ANDs the original expression with a
            # typeSpecific one.  Collect all the results from these expressions.
            recordTypes = self.recordTypesForSearchContext(context)
            log.debug("Tokens: {t}, recordTypes {r}", t=tokens, r=recordTypes)
            for recordType in recordTypes:
                typeSpecific = MatchExpression(
                    self.fieldName.recordType,
                    recordType,
                    MatchType.equals,
                    MatchFlags.none
                )

                typeSpecific = CompoundExpression(
                    [expression, typeSpecific],
                    Operand.AND
                )

                subResults = yield self.recordsFromExpression(typeSpecific)
                log.debug(
                    "Tokens ({t}) matched {n} of {r}",
                    t=tokens, n=len(subResults), r=recordType
                )
                results.extend(subResults)

        else:
            # No record type limits
            results = yield self.recordsFromExpression(expression)
            log.debug(
                "Tokens ({t}) matched {n} records",
                t=tokens, n=len(results)
            )

        log.debug("Tokens ({t}) matched records {r}", t=tokens, r=results)

        returnValue(results)


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
            try:
                field = self.fieldName.lookupByName(fieldName)
            except ValueError:
                log.debug(
                    "Unsupported field name: {fieldName}",
                    fieldName=fieldName
                )
                continue
            subExpression = MatchExpression(
                field,
                searchTerm,
                matchType,
                matchFlags
            )
            subExpressions.append(subExpression)

        expression = CompoundExpression(subExpressions, operand)

        # AND in the recordType if passed in
        if recordType is not None:
            typeExpression = MatchExpression(
                self.fieldName.recordType,
                recordType,
                MatchType.equals,
                MatchFlags.none
            )
            expression = CompoundExpression(
                [
                    expression,
                    typeExpression
                ],
                Operand.AND
            )
        return self.recordsFromExpression(expression)

    _oldRecordTypeNames = {
        "address": "addresses",
        "group": "groups",
        "location": "locations",
        "resource": "resources",
        "user": "users",
        "macOSXServerWiki": "wikis",
        "readDelegateGroup": "readDelegateGroups",
        "writeDelegateGroup": "writeDelegateGroups",
        "readDelegatorGroup": "readDelegatorGroups",
        "writeDelegatorGroup": "writeDelegatorGroups",
    }


    # Maps record types <--> url path segments, i.e. the segment after
    # /principals/ e.g. "users" or "groups"

    def recordTypeToOldName(self, recordType):
        return self._oldRecordTypeNames[recordType.name]


    def oldNameToRecordType(self, oldName):
        for name, value in self._oldRecordTypeNames.iteritems():
            if oldName == value:
                return self.recordType.lookupByName(name)
        return None



class CalendarDirectoryRecordMixin(object):
    """
    Calendar (and Contacts) specific logic for directory records lives in this
    class
    """

    @inlineCallbacks
    def verifyCredentials(self, credentials):

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


    def _calendarAddresses(self):
        cuas = set()

        # urn:x-uid:
        cuas.add("urn:x-uid:{}".format(self.uid))

        # urn:uuid:
        try:
            if self.guid:
                if isinstance(self.guid, uuid.UUID):
                    guid = unicode(self.guid).upper()
                else:
                    guid = self.guid
                cuas.add("urn:uuid:{}".format(guid))
        except AttributeError:
            # No guid
            pass

        # mailto:
        try:
            for emailAddress in self.emailAddresses:
                cuas.add(u"mailto:{}".format(emailAddress))
        except AttributeError:
            # No emailAddresses
            pass

        return frozenset(cuas)


    @property
    def calendarUserAddresses(self):
        try:
            if not (
                self.hasCalendars or (
                    config.GroupAttendees.Enabled and
                    self.recordType == BaseRecordType.group
                )
            ):
                return frozenset()
        except AttributeError:
            pass

        return self._calendarAddresses()

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
        try:
            return self.fullNames[0]
        except AttributeError:
            return u""


    def cacheToken(self):
        """
        Generate a token that can be uniquely used to identify the state of this record for use
        in a cache.
        """
        return hash((
            self.__class__.__name__,
            self.service.realmName,
            self.recordType.name,
            # self.shortNames, # MOVE2WHO FIXME: is this needed? it's not hashable
            self.uid,
            self.hasCalendars,
        ))


    def canonicalCalendarUserAddress(self, checkCal=True):
        """
            Return a CUA for this record, preferring in this order:
            urn:x-uid: form
            urn:uuid: form
            mailto: form
            /principals/__uids__/ form
            first in calendarUserAddresses list (sorted)
        """

        if checkCal:
            cuas = self.calendarUserAddresses
        else:
            cuas = self._calendarAddresses()

        sortedCuas = sorted(cuas)

        for prefix in (
            "urn:x-uid:",
            "urn:uuid:",
            "mailto:",
            "/principals/__uids__/"
        ):
            for candidate in sortedCuas:
                if candidate.startswith(prefix):
                    return candidate

        # fall back to using the first one
        return sortedCuas[0] if sortedCuas else None  # groups may not have cua


    def enabledAsOrganizer(self):
        if self.recordType == self.service.recordType.user:
            return True
        elif self.recordType == self.service.recordType.group:
            return config.Scheduling.Options.AllowGroupAsOrganizer
        elif self.recordType == self.service.recordType.location:
            return config.Scheduling.Options.AllowLocationAsOrganizer
        elif self.recordType == self.service.recordType.resource:
            return config.Scheduling.Options.AllowResourceAsOrganizer
        else:
            return False


    def serverURI(self):
        """
        URL of the server hosting this record. Return None if hosted on this server.
        """
        if (
            self.service.serversDB is not None and
            getattr(self, "serviceNodeUID", None)
        ):
            return self.service.serversDB.getServerURIById(self.serviceNodeUID)
        else:
            return None


    def server(self):
        """
        Server hosting this record. Return None if hosted on this server.
        """
        if (
            self.service.serversDB is not None and
            getattr(self, "serviceNodeUID", None)
        ):
            return self.service.serversDB.getServerById(self.serviceNodeUID)
        else:
            return None


    def thisServer(self):
        s = self.server()
        return s.thisServer if s is not None else True


    def isLoginEnabled(self):
        return self.loginAllowed


    def calendarsEnabled(self):
        return config.EnableCalDAV and self.hasCalendars


    @inlineCallbacks
    def canAutoSchedule(self, organizer=None):
        if config.Scheduling.Options.AutoSchedule.Enabled:
            if (
                config.Scheduling.Options.AutoSchedule.Always or
                getattr(self, "autoScheduleMode", None) not in (AutoScheduleMode.none, None) or  # right???
                (
                    yield self.autoAcceptFromOrganizer(organizer)
                )
            ):
                if (
                    self.getCUType() != "INDIVIDUAL" or
                    config.Scheduling.Options.AutoSchedule.AllowUsers
                ):
                    returnValue(True)
        returnValue(False)


    @inlineCallbacks
    def getAutoScheduleMode(self, organizer):
        autoScheduleMode = self.autoScheduleMode
        if (
            autoScheduleMode not in
            (
                AutoScheduleMode.accept,
                AutoScheduleMode.acceptIfFree,
                AutoScheduleMode.acceptIfFreeDeclineIfBusy
            )
        ):
            if (yield self.autoAcceptFromOrganizer(organizer)):
                autoScheduleMode = AutoScheduleMode.acceptIfFreeDeclineIfBusy

        returnValue(autoScheduleMode)


    @inlineCallbacks
    def autoAcceptFromOrganizer(self, organizer):
        try:
            autoAcceptGroup = self.autoAcceptGroup
        except AttributeError:
            autoAcceptGroup = None

        if (
            organizer is not None and
            autoAcceptGroup is not None
        ):
            service = self.service
            organizerRecord = yield service.recordWithCalendarUserAddress(organizer)
            if organizerRecord is not None:
                autoAcceptGroup = yield service.recordWithUID(autoAcceptGroup)
                members = yield autoAcceptGroup.expandedMembers()
                if organizerRecord.uid in ([m.uid for m in members]):
                    returnValue(True)
        returnValue(False)


    @inlineCallbacks
    def expandedMembers(self, members=None):

        if members is None:
            members = set()

        for member in (yield self.members()):
            if member.recordType == BaseRecordType.user:
                if member not in members:
                    members.add(member)
            yield member.expandedMembers(members)

        returnValue(members)


    # For scheduling/freebusy
    @inlineCallbacks
    def isProxyFor(self, other):
        for recordType in (
            DelegateRecordType.readDelegatorGroup,
            DelegateRecordType.writeDelegatorGroup,
        ):
            delegatorGroup = yield self.service.recordWithShortName(
                recordType, self.uid
            )
            if delegatorGroup:
                if other in (yield delegatorGroup.members()):
                    returnValue(True)


    def attendeeProperty(self, params={}):
        """
        Returns a pycalendar ATTENDEE property for this record.

        @params: extra parameters such as MEMBER to add to ATTENDEE property
        @type: C{dict}

        @return: the attendee property
        @rtype: C{Property}
        """
        params = params.copy() if params else params
        if "PARTSTAT" not in params:
            params["PARTSTAT"] = "NEEDS-ACTION"
        if "CN"not in params:
            if self.displayName:
                params["CN"] = self.displayName.encode("utf-8")
        if "EMAIL" not in params:
            if hasattr(self, "emailAddresses"):
                params["EMAIL"] = list(self.emailAddresses)[0].encode("utf-8")
        if "CUTYPE" not in params:
            cuType = self.getCUType()
            if cuType is not "INDIVIDUAL":
                params["CUTYPE"] = cuType

        return Property("ATTENDEE", self.canonicalCalendarUserAddress().encode("utf-8"), params=params)
