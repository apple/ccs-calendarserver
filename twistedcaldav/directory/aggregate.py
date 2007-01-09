##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Directory service implementation which aggregates multiple directory
services.
"""

__all__ = [
    "AggregateDirectoryService",
    "DuplicateRecordTypeError",
]

from twisted.cred.error import UnauthorizedLogin

from twistedcaldav.directory.idirectory import IDirectoryService
from twistedcaldav.directory.directory import DirectoryService, DirectoryError
from twistedcaldav.directory.directory import UnknownRecordTypeError

class AggregateDirectoryService(DirectoryService):
    """
    L{IDirectoryService} implementation which aggregates multiple directory services.
    """
    baseGUID = "06FB225F-39E7-4D34-B1D1-29925F5E619B"

    def __init__(self, services):
        DirectoryService.__init__(self)

        realmName = None
        recordTypes = {}

        for service in services:
            service = IDirectoryService(service)

            if service.realmName != realmName:
                assert realmName is None, (
                    "Aggregated directory services must have the same realm name: %r != %r"
                    % (service.realmName, realmName)
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

    def recordTypes(self):
        return set(self._recordTypes)

    def listRecords(self, recordType):
        return self._query("listRecords", recordType)

    def recordWithShortName(self, recordType, shortName):
        return self._query("recordWithShortName", recordType, shortName)

    def recordWithGUID(self, guid):
        return self._queryAll("recordWithGUID", guid)

    def recordWithCalendarUserAddress(self, address):
        return self._queryAll("recordWithCalendarUserAddress", address)

    def serviceForRecordType(self, recordType):
        try:
            return self._recordTypes[recordType]
        except KeyError:
            raise UnknownRecordTypeError(recordType)

    def _query(self, query, recordType, *args):
        service = self.serviceForRecordType(recordType)
        return getattr(service, query)(
            recordType[len(service.recordTypePrefix):],
            *[a[len(service.recordTypePrefix):] for a in args]
        )

    def _queryAll(self, query, *args):
        for service in self._recordTypes.values():
            record = getattr(service, query)(*args)
            if record is not None:
                return record
        else:
            return None

    userRecordTypes = [DirectoryService.recordType_users]

    def requestAvatarId(self, credentials):
        for type in self.userRecordTypes:
            user = self.recordWithShortName(
                type,
                credentials.credentials.username)

            if user:
                return self.serviceForRecordType(
                    type).requestAvatarId(credentials)
        
        raise UnauthorizedLogin("No such user: %s" % (
                credentials.credentials.username,))

class DuplicateRecordTypeError(DirectoryError):
    """
    Duplicate record type.
    """
