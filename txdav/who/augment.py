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

__all__ = [
    "AugmentedDirectoryService",
]

from zope.interface import implementer

from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav.directory.augment import AugmentRecord
from twext.python.log import Logger
from twext.who.directory import DirectoryRecord
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.idirectory import (
    IDirectoryService, RecordType, FieldName as BaseFieldName
)
from twext.who.util import ConstantsContainer

from txdav.common.idirectoryservice import IStoreDirectoryService
from txdav.who.directory import (
    CalendarDirectoryRecordMixin, CalendarDirectoryServiceMixin,
)
from txdav.who.idirectory import (
    AutoScheduleMode, FieldName, RecordType as CalRecordType
)

log = Logger()



@implementer(IDirectoryService, IStoreDirectoryService)
class AugmentedDirectoryService(
    BaseDirectoryService, CalendarDirectoryServiceMixin
):
    """
    Augmented directory service.

    This is a directory service that wraps an L{IDirectoryService} and augments
    directory records with additional or modified fields.
    """

    fieldName = ConstantsContainer((
        BaseFieldName,
        FieldName,
    ))


    def __init__(self, directory, store, augmentDB):
        BaseDirectoryService.__init__(self, directory.realmName)
        self._directory = directory
        self._store = store
        self._augmentDB = augmentDB


    @property
    def recordType(self):
        # Defer to the directory service we're augmenting
        return self._directory.recordType


    def recordTypes(self):
        # Defer to the directory service we're augmenting
        return self._directory.recordTypes()


    @inlineCallbacks
    def recordsFromExpression(self, expression):
        records = yield self._directory.recordsFromExpression(expression)
        augmented = []
        for record in records:
            record = yield self._augment(record)
            augmented.append(record)
        returnValue(augmented)


    @inlineCallbacks
    def recordsWithFieldValue(self, fieldName, value):
        records = yield self._directory.recordsWithFieldValue(
            fieldName, value
        )
        augmented = []
        for record in records:
            record = yield self._augment(record)
            augmented.append(record)
        returnValue(augmented)


    @inlineCallbacks
    def recordWithUID(self, uid):
        # MOVE2WHO, REMOVE THIS:
        if not isinstance(uid, unicode):
            # log.warn("Need to change uid to unicode")
            uid = uid.decode("utf-8")

        record = yield self._directory.recordWithUID(uid)
        record = yield self._augment(record)
        returnValue(record)


    @inlineCallbacks
    def recordWithGUID(self, guid):
        record = yield self._directory.recordWithGUID(guid)
        record = yield self._augment(record)
        returnValue(record)


    @inlineCallbacks
    def recordsWithRecordType(self, recordType):
        records = yield self._directory.recordsWithRecordType(recordType)
        augmented = []
        for record in records:
            record = yield self._augment(record)
            augmented.append(record)
        returnValue(augmented)


    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName):
        # MOVE2WHO, REMOVE THIS:
        if not isinstance(shortName, unicode):
            # log.warn("Need to change shortName to unicode")
            shortName = shortName.decode("utf-8")

        record = yield self._directory.recordWithShortName(
            recordType, shortName
        )
        record = yield self._augment(record)
        returnValue(record)


    @inlineCallbacks
    def recordsWithEmailAddress(self, emailAddress):
        # MOVE2WHO, REMOVE THIS:
        if not isinstance(emailAddress, unicode):
            # log.warn("Need to change emailAddress to unicode")
            emailAddress = emailAddress.decode("utf-8")

        records = yield self._directory.recordsWithEmailAddress(emailAddress)
        augmented = []
        for record in records:
            record = yield self._augment(record)
            augmented.append(record)
        returnValue(augmented)


    @inlineCallbacks
    def updateRecords(self, records, create=False):
        """
        Pull out the augmented fields from each record, apply those to the
        augments database, then update the base records.
        """

        baseRecords = []
        augmentRecords = []

        for record in records:

            # Split out the base fields from the augment fields
            baseFields, augmentFields = self._splitFields(record)

            if augmentFields:
                # Create an AugmentRecord
                autoScheduleMode = {
                    AutoScheduleMode.none: "none",
                    AutoScheduleMode.accept: "accept-always",
                    AutoScheduleMode.decline: "decline-always",
                    AutoScheduleMode.acceptIfFree: "accept-if-free",
                    AutoScheduleMode.declineIfBusy: "decline-if-busy",
                    AutoScheduleMode.acceptIfFreeDeclineIfBusy: "automatic",
                }.get(augmentFields.get(FieldName.autoScheduleMode, None), None)

                kwargs = {
                    "uid": record.uid,
                    "autoScheduleMode": autoScheduleMode,
                }
                if FieldName.hasCalendars in augmentFields:
                    kwargs["enabledForCalendaring"] = augmentFields[FieldName.hasCalendars]
                if FieldName.hasContacts in augmentFields:
                    kwargs["enabledForAddressBooks"] = augmentFields[FieldName.hasContacts]
                if FieldName.loginAllowed in augmentFields:
                    kwargs["enabledForLogin"] = augmentFields[FieldName.loginAllowed]
                if FieldName.autoAcceptGroup in augmentFields:
                    kwargs["autoAcceptGroup"] = augmentFields[FieldName.autoAcceptGroup]
                if FieldName.serviceNodeUID in augmentFields:
                    kwargs["serverID"] = augmentFields[FieldName.serviceNodeUID]
                augmentRecord = AugmentRecord(**kwargs)

                augmentRecords.append(augmentRecord)

            # Create new base records:
            baseRecords.append(DirectoryRecord(self._directory, baseFields))

        # Apply the augment records
        if augmentRecords:
            yield self._augmentDB.addAugmentRecords(augmentRecords)

        # Apply the base records
        if baseRecords:
            yield self._directory.updateRecords(baseRecords, create=create)


    def _splitFields(self, record):
        """
        Returns a tuple of two dictionaries; the first contains all the non
        augment fields, and the second contains all the augment fields.
        """
        if record is None:
            return None

        augmentFields = {}
        baseFields = record.fields.copy()
        for field in (
            FieldName.loginAllowed,
            FieldName.hasCalendars, FieldName.hasContacts,
            FieldName.autoScheduleMode, FieldName.autoAcceptGroup,
            FieldName.serviceNodeUID
        ):
            if field in baseFields:
                augmentFields[field] = baseFields[field]
                del baseFields[field]

        return (baseFields, augmentFields)


    def removeRecords(self, uids):
        self._augmentDB.removeAugmentRecords(uids)
        return self._directory.removeRecords(uids)


    def _assignToField(self, fields, name, value):
        field = self.fieldName.lookupByName(name)
        fields[field] = value


    @inlineCallbacks
    def _augment(self, record):
        if record is None:
            returnValue(None)

        augmentRecord = yield self._augmentDB.getAugmentRecord(
            record.uid,
            self.recordTypeToOldName(record.recordType)
        )
        if augmentRecord is None:
            # Augments does not know about this record type, so return
            # the original record
            returnValue(record)

        fields = record.fields.copy()

        # print("Got augment record", augmentRecord)

        if augmentRecord:

            self._assignToField(
                fields, "hasCalendars",
                augmentRecord.enabledForCalendaring
            )

            self._assignToField(
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

            # Resources/Locations default to automatic
            if record.recordType in (
                CalRecordType.location,
                CalRecordType.resource
            ):
                if autoScheduleMode is None:
                    autoScheduleMode = AutoScheduleMode.acceptIfFreeDeclineIfBusy

            self._assignToField(
                fields, "autoScheduleMode",
                autoScheduleMode
            )

            if augmentRecord.autoAcceptGroup is not None:
                self._assignToField(
                    fields, "autoAcceptGroup",
                    augmentRecord.autoAcceptGroup.decode("utf-8")
                )

            self._assignToField(
                fields, "loginAllowed",
                augmentRecord.enabledForLogin
            )

            self._assignToField(
                fields, "serviceNodeUID",
                augmentRecord.serverID.decode("utf-8")
            )

            if (
                (
                    fields.get(
                        self.fieldName.lookupByName("hasCalendars"), False
                    ) or
                    fields.get(
                        self.fieldName.lookupByName("hasContacts"), False
                    )
                ) and
                record.recordType == RecordType.group
            ):
                self._assignToField(fields, "hasCalendars", False)
                self._assignToField(fields, "hasContacts", False)

                # For augment records cloned from the Default augment record,
                # don't emit this message:
                if not augmentRecord.clonedFromDefault:
                    log.error(
                        "Group {record} cannot be enabled for "
                        "calendaring or address books",
                        record=record
                    )

        else:
            self._assignToField(fields, "hasCalendars", False)
            self._assignToField(fields, "hasContacts", False)
            self._assignToField(fields, "loginAllowed", False)

        # print("Augmented fields", fields)

        # Clone to a new record with the augmented fields
        returnValue(AugmentedDirectoryRecord(self, record, fields))



class AugmentedDirectoryRecord(DirectoryRecord, CalendarDirectoryRecordMixin):
    """
    Augmented directory record.
    """

    def __init__(self, service, baseRecord, augmentedFields):
        DirectoryRecord.__init__(self, service, augmentedFields)
        self._baseRecord = baseRecord


    @inlineCallbacks
    def members(self):
        augmented = []
        records = yield self._baseRecord.members()

        for record in records:
            augmented.append((yield self.service._augment(record)))

        returnValue(augmented)


    @inlineCallbacks
    def groups(self):
        augmented = []

        def _groupsFor(txn):
            return txn.groupsFor(self.uid)

        groupUIDs = yield self.service._store.inTransaction(
            "AugmentedDirectoryRecord.groups",
            _groupsFor
        )

        for groupUID in groupUIDs:
            groupRecord = yield self.service.recordWithUID(
                groupUID
            )
            if groupRecord:
                augmented.append((yield self.service._augment(groupRecord)))

        returnValue(augmented)


    def verifyPlaintextPassword(self, password):
        return self._baseRecord.verifyPlaintextPassword(password)


    def verifyHTTPDigest(self, *args):
        return self._baseRecord.verifyHTTPDigest(*args)


    def accessForRecord(self, record):
        return self._baseRecord.accessForRecord(record)
