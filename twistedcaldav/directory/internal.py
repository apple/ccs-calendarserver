##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
Directory service implementation for internal purposes - e.g. public
calendars, addressbooks, directory gateway, global address book.
"""

__all__ = [
    "InternalDirectoryService",
]

from twext.web2.dav.auth import IPrincipalCredentials

from twisted.cred.error import UnauthorizedLogin

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import UnknownRecordTypeError

class InternalDirectoryService(DirectoryService):
    """
    L{IDirectoryService} implementation for internal record types.
    """
    baseGUID = "80DED344-B79F-46AF-B05B-E35D737BC19A"

    realmName = None

    plistFile = None

    supportedRecordTypes = ("public",)

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.realmName)

    def __init__(self, realm):
        super(InternalDirectoryService, self).__init__()

        self.realmName = realm
        self._records()

    def _records(self):
        """
        Build the list of records.
        
        Right now we want public/global and public/directory for
        global and directory address books.
        """
        
        if not hasattr(self, "_cachedRecords"):
            self._cachedRecords = (
                InternalDirectoryRecord(
                    self,
                    "public",
                    "4F00E8BA-7B45-42E9-B9D1-F499B6A2E887",
                    "global",
                    False,
                    True
                ),
                InternalDirectoryRecord(
                    self,
                    "public",
                    "1BC554CC-DBD6-4454-8423-2637A9B681DC",
                    "directory",
                    False,
                    True
                ),
            )
        return self._cachedRecords

    def recordTypes(self):
        return InternalDirectoryService.supportedRecordTypes

    def listRecords(self, recordType):
        if recordType not in InternalDirectoryService.supportedRecordTypes:
            raise UnknownRecordTypeError(recordType)

        return self._records()

    def recordWithShortName(self, recordType, shortName):
        if recordType not in InternalDirectoryService.supportedRecordTypes:
            raise UnknownRecordTypeError(recordType)

        for record in self._records():
            if shortName in record.shortNames:
                return record

    def requestAvatarId(self, credentials):
        credentials = IPrincipalCredentials(credentials)
        raise UnauthorizedLogin("No such user: %s" % (credentials.credentials.username,))


class InternalDirectoryRecord(DirectoryRecord):
    """
    L{DirectoryRecord} implementation for internal records.
    """

    def __init__(self, service, recordType, guid, shortName,
                enabledForCalendaring=None, enabledForAddressBooks=None,):
        super(InternalDirectoryRecord, self).__init__(
            service=service,
            recordType=recordType,
            guid=guid,
            shortNames=(shortName,),
            fullName=shortName,
            enabledForCalendaring=enabledForCalendaring,
            enabledForAddressBooks=enabledForAddressBooks,
        )

        self.enabled = True     # Explicitly enabled

    def verifyCredentials(self, credentials):
        return False
