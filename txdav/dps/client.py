##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

import cPickle as pickle
import uuid

from twext.python.log import Logger
from twext.who.directory import DirectoryRecord as BaseDirectoryRecord
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.idirectory import RecordType, IDirectoryService
import twext.who.idirectory
from twext.who.util import ConstantsContainer
from twisted.cred.credentials import UsernamePassword
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.internet.protocol import ClientCreator
from twisted.protocols import amp
from twisted.python.constants import Names, NamedConstant
from txdav.caldav.icalendardirectoryservice import ICalendarStoreDirectoryRecord
from txdav.common.idirectoryservice import IStoreDirectoryService
from txdav.dps.commands import (
    RecordWithShortNameCommand, RecordWithUIDCommand, RecordWithGUIDCommand,
    RecordsWithRecordTypeCommand, RecordsWithEmailAddressCommand,
    RecordsMatchingTokensCommand,
    MembersCommand, GroupsCommand, SetMembersCommand,
    VerifyPlaintextPasswordCommand, VerifyHTTPDigestCommand
)
import txdav.who.delegates
import txdav.who.idirectory
from txweb2.auth.digest import DigestedCredentials
from zope.interface import implementer

log = Logger()

##
## Client implementation of Directory Proxy Service
##



## MOVE2WHO TODOs:
## augmented service
## configuration of aggregate services
## hooking up delegates
## calverify needs deferreds, including:
##    component.normalizeCalendarUserAddresses

@implementer(IDirectoryService, IStoreDirectoryService)
class DirectoryService(BaseDirectoryService):
    """
    Client side of directory proxy
    """

    recordType = ConstantsContainer(
        (twext.who.idirectory.RecordType,
         txdav.who.idirectory.RecordType,
         txdav.who.delegates.RecordType)
    )

    fieldName = ConstantsContainer(
        (twext.who.idirectory.FieldName,
         txdav.who.idirectory.FieldName)
    )

    # def __init__(self, fieldNames, recordTypes):
    #     self.fieldName = fieldNames
    #     self.recordType = recordTypes

    # MOVE2WHO
    def getGroups(self, guids=None):
        return succeed(set())

    # Must maintain the hack for a bit longer:
    def setPrincipalCollection(self, principalCollection):
        """
        Set the principal service that the directory relies on for doing proxy tests.

        @param principalService: the principal service.
        @type principalService: L{DirectoryProvisioningResource}
        """
        self.principalCollection = principalCollection

    guid = "1332A615-4D3A-41FE-B636-FBE25BFB982E"

    # END MOVE2WHO




    def _dictToRecord(self, serializedFields):
        """
        Turn a dictionary of fields sent from the server into a directory
        record
        """
        if not serializedFields:
            return None

        # print("FIELDS", serializedFields)

        # MOVE2WHO -- existing code assumes record.emailAddresses always exists,
        # so adding this here, but perhaps we should change the behavior in
        # twext.who itself:
        # Add default empty list of email addresses
        if self.fieldName.emailAddresses.name not in serializedFields:
            serializedFields[self.fieldName.emailAddresses.name] = []

        fields = {}
        for fieldName, value in serializedFields.iteritems():
            try:
                field = self.fieldName.lookupByName(fieldName)
            except ValueError:
                # unknown field
                pass
            else:
                valueType = self.fieldName.valueType(field)
                if valueType in (unicode, bool):
                    fields[field] = value
                elif valueType is uuid.UUID:
                    fields[field] = uuid.UUID(value)
                elif issubclass(valueType, Names):
                    if value is not None:
                        fields[field] = field.valueType.lookupByName(value)
                    else:
                        fields[field] = None
                elif issubclass(valueType, NamedConstant):
                    if fieldName == "recordType":  # Is there a better way?
                        fields[field] = self.recordType.lookupByName(value)

        # print("AFTER:", fields)
        return DirectoryRecord(self, fields)


    def _processSingleRecord(self, result):
        serializedFields = pickle.loads(result['fields'])
        return self._dictToRecord(serializedFields)


    def _processMultipleRecords(self, result):
        serializedFieldsList = pickle.loads(result['fieldsList'])
        results = []
        for serializedFields in serializedFieldsList:
            record = self._dictToRecord(serializedFields)
            if record is not None:
                results.append(record)
        return results


    @inlineCallbacks
    def _getConnection(self):
        # TODO: make socket patch configurable
        # TODO: reconnect if needed

        # path = config.DirectoryProxy.SocketPath
        path = "data/Logs/state/directory-proxy.sock"
        if getattr(self, "_connection", None) is None:
            log.debug("Creating connection")
            connection = (yield ClientCreator(reactor, amp.AMP).connectUNIX(path))
            self._connection = connection
        else:
            log.debug("Already have connection")
        returnValue(self._connection)


    @inlineCallbacks
    def _call(self, command, postProcess, **kwds):
        """
        Execute a remote AMP command, first making the connection to the peer,
        then making the call, then running the results through the postProcess
        callback.  Any kwds are passed on to the AMP command.

        @param command: the AMP command to call
        @type command: L{twisted.protocols.amp.Command}

        @param postProcess: a callable which takes the AMP response dictionary
            and performs any required massaging of the results, returning a
            L{Deferred} which fires with the post-processed results
        @type postProcess: callable
        """
        ampProto = (yield self._getConnection())
        results = (yield ampProto.callRemote(command, **kwds))
        returnValue(postProcess(results))


    def recordWithShortName(self, recordType, shortName):
        # MOVE2WHO
        # temporary hack until we can fix all callers not to pass strings:
        if isinstance(recordType, (str, unicode)):
            recordType = self.recordType.lookupByName(recordType)
        return self._call(
            RecordWithShortNameCommand,
            self._processSingleRecord,
            recordType=recordType.name.encode("utf-8"),
            shortName=shortName.encode("utf-8")
        )


    def recordWithUID(self, uid):
        return self._call(
            RecordWithUIDCommand,
            self._processSingleRecord,
            uid=uid.encode("utf-8")
        )


    def recordWithGUID(self, guid):
        return self._call(
            RecordWithGUIDCommand,
            self._processSingleRecord,
            guid=guid.encode("utf-8")
        )


    def recordsWithRecordType(self, recordType):
        return self._call(
            RecordsWithRecordTypeCommand,
            self._processMultipleRecords,
            recordType=recordType.name.encode("utf-8")
        )


    def recordsWithEmailAddress(self, emailAddress):
        return self._call(
            RecordsWithEmailAddressCommand,
            self._processMultipleRecords,
            emailAddress=emailAddress
        )


    # def listRecords(self, recordType):
    #     # MOVE2WHO
    #     return []


    @inlineCallbacks
    def recordWithCalendarUserAddress(self, address):
        # FIXME: Circular
        from txdav.caldav.datastore.scheduling.cuaddress import normalizeCUAddr
        address = normalizeCUAddr(address)
        record = None
        if address.startswith("urn:uuid:"):
            guid = address[9:]
            record = yield self.recordWithGUID(guid)
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
                    guid = parts[3]
                    record = yield self.recordWithGUID(guid)
                else:
                    recordType = self.fieldName.lookupByName(parts[2])
                    record = yield self.recordWithShortName(recordType, parts[3])

        returnValue(record if record and record.hasCalendars else None)


    def recordsMatchingTokens(self, tokens, context=None, limitResults=50,
                              timeoutSeconds=10):
        return self._call(
            RecordsMatchingTokensCommand,
            self._processMultipleRecords,
            tokens=[t.encode("utf-8") for t in tokens],
            context=context
        )



    # FIXME: Existing code assumes record type names are plural. Is there any
    # reason to maintain backwards compatibility?  I suppose there could be
    # scripts referring to record type of "users", "locations"
    def recordTypeToOldName(self, recordType):
        return recordType.name + u"s"

    def oldNameToRecordType(self, oldName):
        return self.recordType.lookupByName(oldName[:-1])


@implementer(ICalendarStoreDirectoryRecord)
class DirectoryRecord(BaseDirectoryRecord):


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


    def verifyPlaintextPassword(self, password):
        return self.service._call(
            VerifyPlaintextPasswordCommand,
            lambda x: x['authenticated'],
            uid=self.uid.encode("utf-8"),
            password=password.encode("utf-8")
        )


    def verifyHTTPDigest(
        self, username, realm, uri, nonce, cnonce,
        algorithm, nc, qop, response, method,
    ):
        return self.service._call(
            VerifyHTTPDigestCommand,
            lambda x: x['authenticated'],
            uid=self.uid.encode("utf-8"),
            username=username.encode("utf-8"),
            realm=realm.encode("utf-8"),
            uri=uri.encode("utf-8"),
            nonce=nonce.encode("utf-8"),
            cnonce=cnonce.encode("utf-8"),
            algorithm=algorithm.encode("utf-8"),
            nc=nc.encode("utf-8"),
            qop=qop.encode("utf-8"),
            response=response.encode("utf-8"),
            method=method.encode("utf-8"),
        )


    def members(self):
        return self.service._call(
            MembersCommand,
            self.service._processMultipleRecords,
            uid=self.uid.encode("utf-8")
        )


    def groups(self):
        return self.service._call(
            GroupsCommand,
            self.service._processMultipleRecords,
            uid=self.uid.encode("utf-8")
        )


    def setMembers(self, members):
        log.debug("DPS Client setMembers")
        memberUIDs = [m.uid.encode("utf-8") for m in members]
        return self.service._call(
            SetMembersCommand,
            lambda x: x['success'],
            uid=self.uid.encode("utf-8"),
            memberUIDs=memberUIDs
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


    def getCUType(self):
        # Mapping from directory record.recordType to RFC2445 CUTYPE values
        self._cuTypes = {
            self.service.recordType.user: 'INDIVIDUAL',
            self.service.recordType.group: 'GROUP',
            self.service.recordType.resource: 'RESOURCE',
            self.service.recordType.location: 'ROOM',
        }

        return self._cuTypes.get(self.recordType, "UNKNOWN")


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
            self.guid,
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
        elif self.recordType == DirectoryService.recordType_groups:
            return False  # config.Scheduling.Options.AllowGroupAsOrganizer
        elif self.recordType == DirectoryService.recordType_locations:
            return False  # config.Scheduling.Options.AllowLocationAsOrganizer
        elif self.recordType == DirectoryService.recordType_resources:
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


    # For scheduling/freebusy
    # FIXME: doesn't this need to happen in the DPS?
    @inlineCallbacks
    def isProxyFor(self, other):
        for recordType in (
            txdav.who.delegates.RecordType.readDelegatorGroup,
            txdav.who.delegates.RecordType.writeDelegatorGroup,
        ):
            delegatorGroup = yield self.service.recordWithShortName(
                recordType, self.uid
            )
            if delegatorGroup:
                if other in (yield delegatorGroup.members()):
                    returnValue(True)



# Test client:


@inlineCallbacks
def makeEvenBetterRequest():
    ds = DirectoryService(None)
    record = (yield ds.recordWithShortName(RecordType.user, "sagen"))
    print("short name: {r}".format(r=record))
    if record:
        authenticated = (yield record.verifyPlaintextPassword("negas"))
        print("plain auth: {a}".format(a=authenticated))
    """
    record = (yield ds.recordWithUID("__dre__"))
    print("uid: {r}".format(r=record))
    if record:
        authenticated = (yield record.verifyPlaintextPassword("erd"))
        print("plain auth: {a}".format(a=authenticated))
    record = (yield ds.recordWithGUID("A3B1158F-0564-4F5B-81E4-A89EA5FF81B0"))
    print("guid: {r}".format(r=record))
    records = (yield ds.recordsWithRecordType(RecordType.user))
    print("recordType: {r}".format(r=records))
    records = (yield ds.recordsWithEmailAddress("cdaboo@bitbucket.calendarserver.org"))
    print("emailAddress: {r}".format(r=records))
    """



def succeeded(result):
    print("yay")
    reactor.stop()



def failed(failure):
    print("boo: {f}".format(f=failure))
    reactor.stop()


if __name__ == '__main__':
    d = makeEvenBetterRequest()
    d.addCallbacks(succeeded, failed)
    reactor.run()
