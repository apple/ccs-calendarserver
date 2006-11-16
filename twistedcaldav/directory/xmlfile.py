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
# DRI: Cyrus Daboo, cdaboo@apple.com
##
from twistedcaldav.directory.xmlaccountsparser import XMLAccountsParser


"""
XML based user/group/resource directory service implementation.
"""

__all__ = [
    "XMLFileService",
    "XMLFileRecord",
]

from twisted.cred.credentials import UsernamePassword
from twisted.python.filepath import FilePath

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord

class XMLFileService(DirectoryService):
    """
    XML based implementation of L{IDirectoryService}.
    """
    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.xmlFile)

    def __init__(self, xmlFile):
        if type(xmlFile) is str:
            xmlFile = FilePath(xmlFile)

        self.xmlAccounts = XMLAccountsParser(xmlFile)

    def recordTypes(self):
        recordTypes = ("user", "group", "resource")
        return recordTypes

    def listRecords(self, recordType):
        for entryShortName, xmlprincipal in self._entriesForRecordType(recordType):
            yield entryShortName

    def recordWithShortName(self, recordType, shortName):
        for entryShortName, xmlprincipal in self._entriesForRecordType(recordType):
            if entryShortName == shortName:
                return XMLFileRecord(
                    service       = self,
                    recordType    = recordType,
                    shortName     = entryShortName,
                    xmlPrincipal  = xmlprincipal,
                )

        raise NotImplementedError()

    def recordWithGUID(self, guid):
        raise NotImplementedError()

    def _entriesForRecordType(self, recordType):
        for entry in self.xmlAccounts.items.itervalues():
            if entry.recordType == recordType:
                 yield entry.uid, entry

class XMLFileRecord(DirectoryRecord):
    """
    XML based implementation implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, shortName, xmlPrincipal):

        self.service        = service
        self.recordType     = recordType
        self.guid           = None
        self.shortName      = shortName
        self.fullName       = xmlPrincipal.name
        self.clearPassword  = xmlPrincipal.pswd
        self._members       = xmlPrincipal.members
        self._groups        = xmlPrincipal.groups

    def members(self):
        for shortName in self._members:
            yield self.service.recordWithShortName("user", shortName)

    def groups(self):
        for shortName in self._groups:
            yield self.service.recordWithShortName("group", shortName)

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            return credentials.password == self.clearPassword

        return super(XMLFileRecord, self).verifyCredentials(credentials)
