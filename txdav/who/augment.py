# -*- test-case-name: txdav.who.test.test_augment -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
Augmenting Directory Service
"""

from twext.who.idirectory import IDirectoryService, RecordType
from twext.who.directory import DirectoryRecord
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.util import ConstantsContainer
from txdav.who.idirectory import AutoScheduleMode, FieldName
from txdav.who.idirectory import RecordType as CalRecordType
from txdav.who.delegates import RecordType as DelegateRecordType
from twisted.internet.defer import inlineCallbacks, returnValue
from zope.interface import implementer

from twext.python.log import Logger
log = Logger()


class AugmentedDirectoryRecord(DirectoryRecord):

    def __init__(self, service, baseRecord, augmentedFields):
        DirectoryRecord.__init__(self, service, augmentedFields)
        self._baseRecord = baseRecord


    @inlineCallbacks
    def members(self):
        augmented = []
        records = yield self._baseRecord.members()
        for record in records:
            augmented.append((yield self.service.augment(record)))
        returnValue(augmented)


    @inlineCallbacks
    def groups(self):
        augmented = []
        txn = self.service._store.newTransaction()
        groupUIDs = yield txn.groupsFor(self.uid)
        print("XYZZY GROU UIDS", groupUIDs)
        for groupUID in groupUIDs:
            groupRecord = yield self.service.recordWithShortName(
                RecordType.group, groupUID
            )
            if groupRecord:
                augmented.append((yield self.service.augment(groupRecord)))
        returnValue(augmented)


@implementer(IDirectoryService)
class AugmentedDirectoryService(BaseDirectoryService):

    fieldName = ConstantsContainer((
        BaseDirectoryService.fieldName,
        FieldName,
    ))

    recordType = ConstantsContainer((
        RecordType.user,
        RecordType.group,
        CalRecordType.location,
        CalRecordType.resource,
        CalRecordType.address,
        DelegateRecordType.readDelegateGroup,
        DelegateRecordType.writeDelegateGroup,
        DelegateRecordType.readDelegatorGroup,
        DelegateRecordType.writeDelegatorGroup,
    ))


    def __init__(self, directory, store, augmentDB):
        BaseDirectoryService.__init__(self, directory.realmName)
        self._directory = directory
        self._store = store
        self._augmentDB = augmentDB


    def recordTypes(self):
        return self._directory.recordTypes()


    @inlineCallbacks
    def recordsFromExpression(self, expression):
        records = yield self._directory.recordsFromExpression(expression)
        augmented = []
        for record in records:
            record = yield self.augment(record)
            augmented.append(record)
        returnValue(augmented)


    @inlineCallbacks
    def recordsWithFieldValue(self, fieldName, value):
        records = yield self._directory.recordsWithFieldValue(
            fieldName, value
        )
        augmented = []
        for record in records:
            record = yield self.augment(record)
            augmented.append(record)
        returnValue(augmented)


    @inlineCallbacks
    def recordWithUID(self, uid):
        record = yield self._directory.recordWithUID(uid)
        record = yield self.augment(record)
        returnValue(record)


    @inlineCallbacks
    def recordWithGUID(self, guid):
        record = yield self._directory.recordWithGUID(guid)
        record = yield self.augment(record)
        returnValue(record)


    @inlineCallbacks
    def recordsWithRecordType(self, recordType):
        records = yield self._directory.recordsWithRecordType(recordType)
        augmented = []
        for record in records:
            record = yield self.augment(record)
            augmented.append(record)
        returnValue(augmented)


    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName):
        record = yield self._directory.recordWithShortName(recordType, shortName)
        record = yield self.augment(record)
        returnValue(record)


    @inlineCallbacks
    def recordsWithEmailAddress(self, emailAddress):
        records = yield self._directory.recordsWithEmailAddress(emailAddress)
        augmented = []
        for record in records:
            record = yield self.augment(record)
            augmented.append(record)
        returnValue(augmented)


    @inlineCallbacks
    def updateRecords(self, records, create=False):
        return self._directory.updateRecords(records, create=create)


    @inlineCallbacks
    def removeRecords(self, uids):
        return self._directory.removeRecords(uids)


    def assignToField(self, fields, name, value):
        field = self.fieldName.lookupByName(name)
        fields[field] = value


    @inlineCallbacks
    def augment(self, record):
        if record is None:
            returnValue(None)

        # MOVE2WHO
        # FIXME: hacked by appending an "s" -- need a mapping
        try:
            augmentRecord = yield self._augmentDB.getAugmentRecord(
                record.uid,
                record.recordType.name + "s"
            )
        except KeyError:
            # Augments does not know about this record type, so return
            # the original record
            returnValue(record)

        fields = record.fields.copy()

        # print("Got augment record", augmentRecord)

        if augmentRecord:
            # record.enabled = augmentRecord.enabled
            # record.serverID = augmentRecord.serverID
            self.assignToField(
                fields, "hasCalendars",
                augmentRecord.enabledForCalendaring
            )
            self.assignToField(
                fields, "hasContacts",
                augmentRecord.enabledForAddressBooks
            )
            autoScheduleMode = {
                "none": AutoScheduleMode.none,
                "accept-always": AutoScheduleMode.accept,
                "decline-always": AutoScheduleMode.decline,
                "accept-if-free": AutoScheduleMode.acceptIfFree,
                "decline-if-busy": AutoScheduleMode.declineIfBusy,
                "automatic": AutoScheduleMode.acceptIfFreeDeclineIfBusy,
            }.get(augmentRecord.autoScheduleMode, None)
            self.assignToField(
                fields, "autoScheduleMode",
                autoScheduleMode
            )
            self.assignToField(
                fields, "autoAcceptGroup",
                unicode(augmentRecord.autoAcceptGroup)
            )
            self.assignToField(
                fields, "loginAllowed",
                augmentRecord.enabledForLogin
            )

            if (
                (
                    fields.get(self.fieldName.lookupByName("hasCalendars"), False) or
                    fields.get(self.fieldName.lookupByName("hasContacts"), False)
                ) and record.recordType == RecordType.group
            ):
                self.assignToField(fields, "hasCalendars", False)
                self.assignToField(fields, "hasContacts", False)

                # For augment records cloned from the Default augment record,
                # don't emit this message:
                if not augmentRecord.clonedFromDefault:
                    log.error("Group '%s(%s)' cannot be enabled for calendaring or address books" % (record.guid, record.shortNames[0],))

        else:
            # Groups are by default always enabled
            # record.enabled = (record.recordType == record.service.recordType_groups)
            # record.serverID = ""
            self.assignToField(fields, "hasCalendars", False)
            self.assignToField(fields, "hasContacts", False)
            self.assignToField(fields, "loginAllowed", False)

        # print("Augmented fields", fields)

        # Clone to a new record with the augmented fields
        returnValue(AugmentedDirectoryRecord(self, record, fields))
