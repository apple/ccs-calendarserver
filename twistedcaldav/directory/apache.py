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
Apache UserFile/GroupFile compatible directory service implementation.
"""

__all__ = [
    "FileDirectoryService",
    "FileDirectoryRecord",
]

from twisted.python.filepath import FilePath

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import UnknownRecordTypeError

class FileDirectoryService(DirectoryService):
    """
    Apache UserFile/GroupFile implementation of L{IDirectoryService}.
    """
    def __repr__(self):
        return "<%s %r %r>" % (self.__class__.__name__, self.userFile, self.groupFile)

    def __init__(self, userFile, groupFile=None):
        if type(userFile) is str:
            userFile = FilePath(userFile)
        if type(groupFile) is str:
            groupFile = FilePath(groupFile)

        self.userFile = userFile
        self.groupFile = groupFile

    def recordTypes(self):
        recordTypes = ("user",)
        if self.groupFile is not None:
            recordTypes += ("group",)
        return recordTypes

    def listRecords(self, recordType):
        if recordType == "user":
            for entry in self.userFile.open():
                if entry and entry[0] != "#":
                    user, password = entry.split(":")
                    yield user
        elif recordType == "group":
            raise NotImplementedError()
        else:
            raise UnknownRecordTypeError("Unknown record type: %s" % (recordType,))

    def recordWithShortName(self, recordType, shortName):
        raise NotImplementedError()

    def recordWithGUID(self, guid):
        raise NotImplementedError()

class FileDirectoryRecord(DirectoryRecord):
    """
    Apache UserFile/GroupFile implementation of L{IDirectoryRecord}.
    """
    def __init__(self):
        service    = None
        recordType = None
        guid       = None
        shortName  = None
        fullName   = None

    def members(self):
        raise NotImplementedError()

    def group(self):
        raise NotImplementedError()

    def verifyCredentials(self, credentials):
        raise NotImplementedError()
