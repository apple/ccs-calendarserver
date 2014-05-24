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
from twext.who.expression import Operand
from twext.who.idirectory import RecordType, IDirectoryService
import twext.who.idirectory
from twext.who.util import ConstantsContainer
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import ClientCreator
from twisted.protocols import amp
from twisted.python.constants import Names, NamedConstant
from txdav.caldav.icalendardirectoryservice import (
    ICalendarStoreDirectoryRecord
)
from txdav.common.idirectoryservice import IStoreDirectoryService
from txdav.dps.commands import (
    RecordWithShortNameCommand, RecordWithUIDCommand, RecordWithGUIDCommand,
    RecordsWithRecordTypeCommand, RecordsWithEmailAddressCommand,
    RecordsMatchingTokensCommand, RecordsMatchingFieldsCommand,
    MembersCommand, GroupsCommand, SetMembersCommand,
    VerifyPlaintextPasswordCommand, VerifyHTTPDigestCommand,
    WikiAccessForUID
)
from txdav.who.directory import (
    CalendarDirectoryRecordMixin, CalendarDirectoryServiceMixin
)
import txdav.who.augment
import txdav.who.delegates
import txdav.who.idirectory
import txdav.who.wiki
from zope.interface import implementer

log = Logger()

##
## Client implementation of Directory Proxy Service
##



## MOVE2WHO TODOs:
## SACLs
## LDAP
## Tests from old twistedcaldav/directory
## Cmd line tools
## Store based directory service (records in the store, i.e.
##    locations/resources)
## Separate store for DPS (augments and delegates separate from calendar data)
## Store autoAcceptGroups in the group db?

@implementer(IDirectoryService, IStoreDirectoryService)
class DirectoryService(BaseDirectoryService, CalendarDirectoryServiceMixin):
    """
    Client side of directory proxy
    """

    # FIXME: somehow these should come from the actual directory:

    recordType = ConstantsContainer(
        (twext.who.idirectory.RecordType,
         txdav.who.idirectory.RecordType,
         txdav.who.delegates.RecordType,
         txdav.who.wiki.RecordType)
    )

    fieldName = ConstantsContainer(
        (twext.who.idirectory.FieldName,
         txdav.who.idirectory.FieldName,
         txdav.who.augment.FieldName)
    )


    def _dictToRecord(self, serializedFields):
        """
        Turn a dictionary of fields sent from the server into a directory
        record
        """
        if not serializedFields:
            return None

        # print("FIELDS", serializedFields)

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
        # TODO: reconnect if needed

        # FIXME:
        from twistedcaldav.config import config
        path = config.DirectoryProxy.SocketPath
        # path = "data/Logs/state/directory-proxy.sock"
        if getattr(self, "_connection", None) is None:
            log.debug("Creating connection")
            connection = (
                yield ClientCreator(reactor, amp.AMP).connectUNIX(path)
            )
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

        # MOVE2WHO, REMOVE THIS HACK TOO:
        if not isinstance(shortName, unicode):
            # log.warn("Need to change shortName to unicode")
            shortName = shortName.decode("utf-8")

        return self._call(
            RecordWithShortNameCommand,
            self._processSingleRecord,
            recordType=recordType.name.encode("utf-8"),
            shortName=shortName.encode("utf-8")
        )


    def recordWithUID(self, uid):
        # MOVE2WHO, REMOVE THIS:
        if not isinstance(uid, unicode):
            # log.warn("Need to change uid to unicode")
            uid = uid.decode("utf-8")

        return self._call(
            RecordWithUIDCommand,
            self._processSingleRecord,
            uid=uid.encode("utf-8")
        )


    def recordWithGUID(self, guid):
        return self._call(
            RecordWithGUIDCommand,
            self._processSingleRecord,
            guid=str(guid)
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
            emailAddress=emailAddress.encode("utf-8")
        )


    def recordsMatchingTokens(
        self, tokens, context=None, limitResults=50, timeoutSeconds=10
    ):
        return self._call(
            RecordsMatchingTokensCommand,
            self._processMultipleRecords,
            tokens=[t.encode("utf-8") for t in tokens],
            context=context
        )


    def recordsMatchingFields(
        self, fields, operand=Operand.OR, recordType=None
    ):
        newFields = []
        for fieldName, searchTerm, matchFlags, matchType in fields:

            if isinstance(searchTerm, uuid.UUID):
                searchTerm = unicode(searchTerm)

            newFields.append(
                (
                    fieldName.encode("utf-8"),
                    searchTerm.encode("utf-8"),
                    matchFlags.name.encode("utf-8"),
                    matchType.name.encode("utf-8")
                )
            )
        if recordType is not None:
            recordType = recordType.name.encode("utf-8")

        return self._call(
            RecordsMatchingFieldsCommand,
            self._processMultipleRecords,
            fields=newFields,
            operand=operand.name.encode("utf-8"),
            recordType=recordType
        )


    def recordsFromExpression(self, expression):
        raise NotImplementedError(
            "This won't work until expressions are serializable to send "
            "across AMP"
        )



@implementer(ICalendarStoreDirectoryRecord)
class DirectoryRecord(BaseDirectoryRecord, CalendarDirectoryRecordMixin):


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


    def _convertAccess(self, results):
        access = results["access"].decode("utf-8")
        return txdav.who.wiki.WikiAccessLevel.lookupByName(access)


    def accessForRecord(self, record):
        log.debug("DPS Client accessForRecord")
        return self.service._call(
            WikiAccessForUID,
            self._convertAccess,
            wikiUID=self.uid.encode("utf-8"),
            uid=record.uid.encode("utf-8")
        )


# Test client:

@inlineCallbacks
def makeEvenBetterRequest():
    ds = DirectoryService(None)
    record = (yield ds.recordWithShortName(RecordType.user, "sagen"))
    print("short name: {r}".format(r=record))
    if record:
        authenticated = (yield record.verifyPlaintextPassword("negas"))
        print("plain auth: {a}".format(a=authenticated))

    # record = (yield ds.recordWithUID("__dre__"))
    # print("uid: {r}".format(r=record))
    # if record:
    #     authenticated = (yield record.verifyPlaintextPassword("erd"))
    #     print("plain auth: {a}".format(a=authenticated))

    # record = yield ds.recordWithGUID(
    #     "A3B1158F-0564-4F5B-81E4-A89EA5FF81B0"
    # )
    # print("guid: {r}".format(r=record))

    # records = yield ds.recordsWithRecordType(RecordType.user)
    # print("recordType: {r}".format(r=records))

    # records = yield ds.recordsWithEmailAddress(
    #     "cdaboo@bitbucket.calendarserver.org"
    # )
    # print("emailAddress: {r}".format(r=records))



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
