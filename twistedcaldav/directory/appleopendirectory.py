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
]

import opendirectory
import dsattributes

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord

class OpenDirectoryService(DirectoryService):
    """
    Open Directory implementation of L{IDirectoryService}.
    """
    def __init__(self, node="/Search"):
        directory = opendirectory.odInit(node)
        if directory is None:
            raise ValueError("Failed to open Open Directory Node: %s" % (node,))

        self._directory = directory

    def recordTypes(self):
        return ("user", "group", "resource")

    def listRecords(self, recordType):
        def makeRecord(shortName, guid, lastModified, principalURI):
            if not guid:
                return None

            ##
            # FIXME: Also verify that principalURI is on this server
            # Which probably means that the host information needs to be on
            # the site object, and that we need the site object passed to
            # __init__() here.
            ##

            return OpenDirectoryRecord(
                directory = self,
                recordType = recordType,
                guid = guid,
                shortName = shortName,
                fullName = None,
            )

        if recordType == "user":
            for data in opendirectory.listUsers(self._directory):
                yield makeRecord(*data)
            return

        if recordType == "group":
            for data in opendirectory.listGroups(self._directory):
                yield makeRecord(*data)
            return

        if recordType == "resource":
            for data in opendirectory.listResources(self._directory):
                yield makeRecord(*data)
            return

        raise AssertionError("Unknown Open Directory record type: %s" % (recordType,))

    def recordWithShortName(self, recordType, shortName):
        if recordType == "user":
            result = opendirectory.listUsersWithAttributes(self._directory, [shortName])
            if shortName not in result:
                return None
            result = result[shortName]
        elif recordType == "group":
            result = opendirectory.groupAttributes(self._directory, shortName)
        elif recordType == "resource":
            result = opendirectory.resourceAttributes(self._directory, shortName)
        else:
            raise ValueError("Unknown record type: %s" % (recordType,))

        return OpenDirectoryRecord(
            directory = self,
            recordType = recordType,
            guid = result[dsattributes.attrGUID],
            shortName = shortName,
            fullName = result[dsattributes.attrRealName],
        )

class OpenDirectoryRecord(DirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def authenticate(self, credentials):
        if isinstance(credentials, credentials.UsernamePassword):
            return opendirectory.authenticateUser(self.directory, self.shortName, credentials.password)

        return False
