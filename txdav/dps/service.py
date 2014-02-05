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


from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.directory import DirectoryRecord as BaseDirectoryRecord
from twext.who.util import ConstantsContainer
import twext.who.idirectory
import txdav.who.idirectory

from zope.interface import implementer
from twext.python.log import Logger

from .commands import (
    RecordWithShortNameCommand, RecordWithUIDCommand,
    RecordWithGUIDCommand, RecordsWithRecordTypeCommand,
    RecordsWithEmailAddressCommand
)

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import ClientCreator
from twisted.protocols import amp
import cPickle as pickle

log = Logger()


@implementer(twext.who.idirectory.IDirectoryService)
class DirectoryService(BaseDirectoryService):
    """
    Client side of directory proxy
    """

    recordType = ConstantsContainer(
        (twext.who.idirectory.RecordType,
         txdav.who.idirectory.RecordType)
    )


    def _dictToRecord(self, serializedFields):
        """
        This to be replaced by something awesome
        """
        if not serializedFields:
            return None

        fields = {}
        for fieldName, value in serializedFields.iteritems():
            try:
                field = self.fieldName.lookupByName(fieldName)
            except ValueError:
                # unknown field
                pass
            else:
                fields[field] = value
        fields[self.fieldName.recordType] = self.recordType.user
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
        # path = config.DirectoryProxy.SocketPath
        path = "data/Logs/state/directory-proxy.sock"
        if getattr(self, "_connection", None) is None:
            log.debug("Creating connection")
            connection = (yield ClientCreator(reactor, amp.AMP).connectUNIX(path))
            self._connection = connection
        else:
            log.debug("Already have connection")
        returnValue(self._connection)


    def recordWithShortName(self, recordType, shortName):

        def _call(ampProto):
            return ampProto.callRemote(
                RecordWithShortNameCommand,
                recordType=recordType.description.encode("utf-8"),
                shortName=shortName.encode("utf-8")
            )

        d = self._getConnection()
        d.addCallback(_call)
        d.addCallback(self._processSingleRecord)
        return d


    def recordWithUID(self, uid):

        def _call(ampProto):
            return ampProto.callRemote(
                RecordWithUIDCommand,
                uid=uid.encode("utf-8")
            )

        d = self._getConnection()
        d.addCallback(_call)
        d.addCallback(self._processSingleRecord)
        return d


    def recordWithGUID(self, guid):

        def _call(ampProto):
            return ampProto.callRemote(
                RecordWithGUIDCommand,
                guid=guid.encode("utf-8")
            )

        d = self._getConnection()
        d.addCallback(_call)
        d.addCallback(self._processSingleRecord)
        return d


    def recordsWithRecordType(self, recordType):

        def _call(ampProto):
            return ampProto.callRemote(
                RecordsWithRecordTypeCommand,
                recordType=recordType.description.encode("utf-8")
            )

        d = self._getConnection()
        d.addCallback(_call)
        d.addCallback(self._processMultipleRecords)
        return d


    def recordsWithEmailAddress(self, emailAddress):

        def _call(ampProto):
            return ampProto.callRemote(
                RecordsWithEmailAddressCommand,
                emailAddress=emailAddress
            )

        d = self._getConnection()
        d.addCallback(_call)
        d.addCallback(self._processMultipleRecords)
        return d


class DirectoryRecord(BaseDirectoryRecord):
    pass
