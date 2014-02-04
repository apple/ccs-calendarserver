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

from twext.who.idirectory import RecordType
from twisted.protocols import amp
from twisted.internet.defer import inlineCallbacks, returnValue
from twext.python.log import Logger
import uuid
import cPickle as pickle

log = Logger()



class RecordWithShortNameCommand(amp.Command):
    arguments = [
        ('recordType', amp.String()),
        ('shortName', amp.String()),
    ]
    response = [
        ('fields', amp.String()),
    ]


class RecordWithUIDCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
    ]
    response = [
        ('fields', amp.String()),
    ]


class RecordWithGUIDCommand(amp.Command):
    arguments = [
        ('guid', amp.String()),
    ]
    response = [
        ('fields', amp.String()),
    ]


class RecordsWithRecordTypeCommand(amp.Command):
    arguments = [
        ('recordType', amp.String()),
    ]
    response = [
        ('fieldsList', amp.String()),
    ]


class RecordsWithEmailAddressCommand(amp.Command):
    arguments = [
        ('emailAddress', amp.String()),
    ]
    response = [
        ('fieldsList', amp.String()),
    ]


class UpdateRecordsCommand(amp.Command):
    arguments = [
        ('fieldsList', amp.String()),
        ('create', amp.Boolean(optional=True)),
    ]
    response = [
        ('success', amp.Boolean()),
    ]


class RemoveRecordsCommand(amp.Command):
    arguments = [
        ('uids', amp.ListOf(amp.String())),
    ]
    response = [
        ('success', amp.Boolean()),
    ]


class DirectoryProxyAMPProtocol(amp.AMP):
    """
    Server side of directory proxy
    """

    def __init__(self, directory):
        """
        """
        amp.AMP.__init__(self)
        self._directory = directory


    def recordToDict(self, record):
        """
        This to be replaced by something awesome
        """
        fields = {}
        if record is not None:
            for field, value in record.fields.iteritems():
                # print("%s: %s" % (field.name, value))
                valueType = self._directory.fieldName.valueType(field)
                if valueType is unicode:
                    fields[field.name] = value
        return fields


    @RecordWithShortNameCommand.responder
    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName):
        recordType = recordType.decode("utf-8")
        shortName = shortName.decode("utf-8")
        log.debug("RecordWithShortName: {r} {n}", r=recordType, n=shortName)
        record = (yield self._directory.recordWithShortName(
            RecordType.lookupByName(recordType), shortName)
        )
        fields = self.recordToDict(record)
        response = {
            "fields": pickle.dumps(fields),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordWithUIDCommand.responder
    @inlineCallbacks
    def recordWithUID(self, uid):
        uid = uid.decode("utf-8")
        log.debug("RecordWithUID: {u}", u=uid)
        record = (yield self._directory.recordWithUID(uid))
        fields = self.recordToDict(record)
        response = {
            "fields": pickle.dumps(fields),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordWithGUIDCommand.responder
    @inlineCallbacks
    def recordWithGUID(self, guid):
        guid = uuid.UUID(guid)
        log.debug("RecordWithGUID: {g}", g=guid)
        record = (yield self._directory.recordWithGUID(guid))
        fields = self.recordToDict(record)
        response = {
            "fields": pickle.dumps(fields),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordsWithRecordTypeCommand.responder
    @inlineCallbacks
    def recordsWithRecordType(self, recordType):
        recordType = recordType.decode("utf-8")
        log.debug("RecordsWithRecordType: {r}", r=recordType)
        records = (yield self._directory.recordsWithRecordType(
            RecordType.lookupByName(recordType))
        )
        fieldsList = []
        for record in records:
            fieldsList.append(self.recordToDict(record))
        response = {
            "fieldsList": pickle.dumps(fieldsList),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)
