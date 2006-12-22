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
# DRI: David reid, dreid@apple.com
##

"""
Directory service implementation for users who are allowed to authorize
as other principals.
"""

__all__ = [
    "SudoDirectoryService",
]

from twisted.python.filepath import FilePath

from twisted.cred.credentials import (IUsernamePassword, 
                                      IUsernameHashedPassword)

from twistedcaldav.py.plistlib import readPlist
from twistedcaldav.directory.directory import (DirectoryService, 
                                               DirectoryRecord,
                                               UnknownRecordTypeError)

class SudoDirectoryService(DirectoryService):
    """
    L{IDirectoryService} implementation for Sudo users.
    """
    baseGUID = "1EE00E46-1885-4DBC-A001-590AFA76A8E3"

    realmName = None

    plistFile = None

    recordType = "sudoer"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName,
                                self.plistFile)

    def __init__(self, plistFile):
        super(SudoDirectoryService, self).__init__()

        if isinstance(plistFile, (unicode, str)):
            plistFile = FilePath(plistFile)
            
        self.plistFile = plistFile
        self._fileInfo = None
        self._accounts()

    def _accounts(self):
        fileInfo = (self.plistFile.getmtime(), self.plistFile.getsize())
        if fileInfo != self._fileInfo:
            self._plist = readPlist(self.plistFile.path)

        return self._plist

    def recordTypes(self):
        return (self.recordType,)

    def _recordForEntry(self, entry):
        return SudoDirectoryRecord(
            service=self,
            recordType=self.recordType,
            shortName=entry['username'],
            entry=entry)


    def listRecords(self, recordType):
        if recordType != self.recordType:
            raise UnknownRecordTypeError(recordType)

        for entry in self._accounts()['users']:
            yield self._recordForEntry(entry)

    def recordWithShortName(self, recordType, shortName):
        if recordType != self.recordType:
            raise UnknownRecordTypeError(recordType)

        for entry in self._accounts()['users']:
            if entry['username'] == shortName:
                return self._recordForEntry(entry)

    def requestAvatarId(self, credentials):
        # FIXME: ?
        # We were checking if principal is enabled; seems unnecessary in current
        # implementation because you shouldn't have a principal object for a
        # disabled directory principal.

        user = self.recordWithShortName("sudoer", 
                                        credentials.credentials.username)
        if user is None:
            raise UnauthorizedLogin("No such user: %s" % (user,))

        if user.verifyCredentials(credentials.credentials):
            return (
                credentials.authnPrincipal.principalURL(),
                credentials.authzPrincipal.principalURL(),
            )
        else:
            raise UnauthorizedLogin("Incorrect credentials for %s" % (user,)) 

class SudoDirectoryRecord(DirectoryRecord):
    """
    L{DirectoryRecord} implementation for Sudo users.
    """

    def __init__(self, service, recordType, shortName, entry):
        super(SudoDirectoryRecord, self).__init__(
            service=service,
            recordType=recordType,
            guid=None,
            shortName=shortName,
            fullName=shortName,
            calendarUserAddresses=set())

        self.password = entry['password']

    def verifyCredentials(self, credentials):
        if IUsernamePassword.providedBy(credentials):
            return credentials.checkPassword(self.password)
        elif IUsernameHashedPassword.providedBy(credentials):
            return credentials.checkPassword(self.password)
        
        return super(SudoDirectoryRecord, self).verifyCredentials(credentials)
