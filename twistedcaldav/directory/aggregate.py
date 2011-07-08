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
Directory service implementation which aggregates multiple directory
services.
"""

__all__ = [
    "AggregateDirectoryService",
    "DuplicateRecordTypeError",
]

import itertools
from twisted.cred.error import UnauthorizedLogin

from twistedcaldav.directory.idirectory import IDirectoryService
from twistedcaldav.directory.directory import DirectoryService, DirectoryError
from twistedcaldav.directory.directory import UnknownRecordTypeError
from twisted.internet.defer import inlineCallbacks, returnValue

class AggregateDirectoryService(DirectoryService):
    """
    L{IDirectoryService} implementation which aggregates multiple directory services.
    """
    baseGUID = "06FB225F-39E7-4D34-B1D1-29925F5E619B"

    def __init__(self, services, groupMembershipCache):
        super(AggregateDirectoryService, self).__init__()

        realmName = None
        recordTypes = {}
        self.groupMembershipCache = groupMembershipCache

        for service in services:
            service = IDirectoryService(service)

            if service.realmName != realmName:
                assert realmName is None, (
                    "Aggregated directory services must have the same realm name: %r != %r\nServices: %r"
                    % (service.realmName, realmName, services)
                )
                realmName = service.realmName

            if not hasattr(service, "recordTypePrefix"):
                service.recordTypePrefix = ""
            prefix = service.recordTypePrefix

            for recordType in (prefix + r for r in service.recordTypes()):
                if recordType in recordTypes:
                    raise DuplicateRecordTypeError(
                        "%r is in multiple services: %s, %s"
                        % (recordType, recordTypes[recordType], service)
                    )
                recordTypes[recordType] = service

        self.realmName = realmName
        self._recordTypes = recordTypes

        # FIXME: This is a temporary workaround until new data store is in
        # place.  During the purging of deprovisioned users' data, we need
        # to be able to look up records by guid and shortName.  The purge
        # tool sticks temporary fake records in here.
        self._tmpRecords = {
            "guids" : { },
            "shortNames" : { },
        }

    def __repr__(self):
        return "<%s (%s): %r>" % (self.__class__.__name__, self.realmName, self._recordTypes)

    #
    # Define calendarHomesCollection as a property so we can set it on contained services
    #
    def _getCalendarHomesCollection(self):
        return self._calendarHomesCollection

    def _setCalendarHomesCollection(self, value):
        for service in self._recordTypes.values():
            service.calendarHomesCollection = value
        self._calendarHomesCollection = value

    calendarHomesCollection = property(_getCalendarHomesCollection, _setCalendarHomesCollection)

    #
    # Define addressBookHomesCollection as a property so we can set it on contained services
    #
    def _getAddressBookHomesCollection(self):
        return self._addressBookHomesCollection

    def _setAddressBookHomesCollection(self, value):
        for service in self._recordTypes.values():
            service.addressBookHomesCollection = value
        self._addressBookHomesCollection = value

    addressBookHomesCollection = property(_getAddressBookHomesCollection, _setAddressBookHomesCollection)

    def recordTypes(self):
        return set(self._recordTypes)

    def listRecords(self, recordType):
        records = self._query("listRecords", recordType)
        if records is None:
            return ()
        else:
            return records

    def recordWithShortName(self, recordType, shortName):

        # FIXME: These temporary records shouldn't be needed when we move
        # to the new data store API.  They're currently needed when purging
        # deprovisioned users' data.
        record = self._tmpRecords["shortNames"].get(shortName, None)
        if record:
            return record

        return self._query("recordWithShortName", recordType, shortName)

    def recordWithUID(self, uid):

        # FIXME: These temporary records shouldn't be needed when we move
        # to the new data store API.  They're currently needed when purging
        # deprovisioned users' data.
        record = self._tmpRecords["guids"].get(uid, None)
        if record:
            return record

        return self._queryAll("recordWithUID", uid)

    recordWithGUID = recordWithUID

    def recordWithAuthID(self, authID):
        return self._queryAll("recordWithAuthID", authID)

    def recordWithCalendarUserAddress(self, address):
        return self._queryAll("recordWithCalendarUserAddress", address)

    @inlineCallbacks
    def recordsMatchingFields(self, fields, operand="or", recordType=None):

        if recordType:
            services = (self.serviceForRecordType(recordType),)
        else:
            services = set(self._recordTypes.values())

        generators = []
        for service in services:
            generator = (yield service.recordsMatchingFields(fields,
                operand=operand, recordType=recordType))
            generators.append(generator)

        returnValue(itertools.chain(*generators))



    def serviceForRecordType(self, recordType):
        try:
            return self._recordTypes[recordType]
        except KeyError:
            raise UnknownRecordTypeError(recordType)

    def _query(self, query, recordType, *args):
        try:
            service = self.serviceForRecordType(recordType)
        except UnknownRecordTypeError:
            return None

        return getattr(service, query)(
            recordType[len(service.recordTypePrefix):],
            *[a[len(service.recordTypePrefix):] for a in args]
        )

    def _queryAll(self, query, *args):
        for service in self._recordTypes.values():
            try:
                record = getattr(service, query)(*args)
            except UnknownRecordTypeError:
                record = None
            if record is not None:
                return record
        else:
            return None

    def flushCaches(self):
        for service in self._recordTypes.values():
            if hasattr(service, "_initCaches"):
                service._initCaches()

    userRecordTypes = [DirectoryService.recordType_users]

    def requestAvatarId(self, credentials):
        
        if credentials.authnPrincipal:
            return credentials.authnPrincipal.record.service.requestAvatarId(credentials)
        
        raise UnauthorizedLogin("No such user: %s" % (credentials.credentials.username,))

    def getResourceInfo(self):
        results = []
        for service in self._recordTypes.values():
            for result in service.getResourceInfo():
                if result:
                    results.append(result)
        return results

    def createRecord(self, recordType, guid=None, shortNames=(), authIDs=set(),
        fullName=None, firstName=None, lastName=None, emailAddresses=set(),
        uid=None, password=None, **kwargs):
        service = self.serviceForRecordType(recordType)
        return service.createRecord(recordType, guid=guid,
            shortNames=shortNames, authIDs=authIDs, fullName=fullName,
            firstName=firstName, lastName=lastName,
            emailAddresses=emailAddresses, uid=uid, password=password, **kwargs)

    def updateRecord(self, recordType, guid=None, shortNames=(), authIDs=set(),
        fullName=None, firstName=None, lastName=None, emailAddresses=set(),
        uid=None, password=None, **kwargs):
        service = self.serviceForRecordType(recordType)
        return service.updateRecord(recordType, guid=guid,
            shortNames=shortNames,
            authIDs=authIDs, fullName=fullName, firstName=firstName,
            lastName=lastName, emailAddresses=emailAddresses, uid=uid,
            password=password, **kwargs)

    def destroyRecord(self, recordType, guid=None):
        service = self.serviceForRecordType(recordType)
        return service.destroyRecord(recordType, guid=guid)

    def setRealm(self, realmName):
        """
        Set a new realm name for this and nested services
        """
        self.realmName = realmName
        for service in self._recordTypes.values():
            service.setRealm(realmName)

class DuplicateRecordTypeError(DirectoryError):
    """
    Duplicate record type.
    """
