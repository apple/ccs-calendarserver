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

"""
Apple Open Directory implementation.
"""

__all__ = [
    "OpenDirectoryService",
    "OpenDirectoryRecord",
    "OpenDirectoryInitError",
]

import opendirectory
import dsattributes

from twisted.cred.credentials import UsernamePassword

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError, UnknownRecordError

class OpenDirectoryService(DirectoryService):
    """
    Open Directory implementation of L{IDirectoryService}.
    """
    def __repr__(self):
        return "<%s %s>" % (self.__class__.__name__, self.node)

    def __init__(self, node="/Search"):
        directory = opendirectory.odInit(node)
        if directory is None:
            raise OpenDirectoryInitError("Failed to open Open Directory Node: %s" % (node,))

        self.directory = directory
        self.node = node

    def recordTypes(self):
        return ("user", "group", "resource")

    def listRecords(self, recordType):
        if recordType == "user":
            listRecords = opendirectory.listUsers
        elif recordType == "group":
            listRecords = opendirectory.listGroups
        elif recordType == "resource":
            listRecords = opendirectory.listResources
        else:
            raise UnknownRecordTypeError("Unknown Open Directory record type: %s" % (recordType,))

        for shortName, guid, lastModified, principalURI in opendirectory.listUsers(self.directory):
            if guid:
                yield OpenDirectoryRecord(
                    directory = self,
                    recordType = recordType,
                    guid = guid,
                    shortName = shortName,
                    fullName = None,
                )

    def recordWithShortName(self, recordType, shortName):
        if recordType == "user":
            result = opendirectory.listUsersWithAttributes(self.directory, [shortName])
            if result is None or shortName not in result:
                return None
            result = result[shortName]
        elif recordType == "group":
            result = opendirectory.groupAttributes(self.directory, shortName)
        elif recordType == "resource":
            result = opendirectory.resourceAttributes(self.directory, shortName)
        else:
            raise UnknownRecordError("Unknown record type: %s" % (recordType,))

        return OpenDirectoryRecord(
            service = self,
            recordType = recordType,
            guid = result[dsattributes.attrGUID],
            shortName = shortName,
            fullName = result[dsattributes.attrRealName],
        )

class OpenDirectoryRecord(DirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def members(self):
        if self.recordType != "group":
            return ()

        raise NotImplementedError("OpenDirectoryRecord.members() for groups")

    def groups(self):
        raise NotImplementedError("OpenDirectoryRecord.groups()")

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            return opendirectory.authenticateUser(self.service.directory, self.shortName, credentials.password)

        return super(OpenDirectoryInitError, self).verifyCredentials(credentials)

class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
