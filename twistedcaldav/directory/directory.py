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
Generic directory service classes.
"""

__all__ = [
    "DirectoryService",
    "DirectoryRecord",
    "DirectoryError",
    "UnknownRecordError",
    "UnknownRecordTypeError",
]

from zope.interface import implements

from twistedcaldav.directory.idirectory import IDirectoryService, IDirectoryRecord

class DirectoryService(object):
    implements(IDirectoryService)

class DirectoryRecord(object):
    implements(IDirectoryRecord)

    def __repr__(self):
        return "<%s[%s@%s] %s(%s) %r>" % (self.__class__.__name__, self.recordType, self.service, self.guid, self.shortName, self.fullName)

    def __init__(self, service, recordType, guid, shortName, fullName=None):
        self.service    = service
        self.recordType = recordType
        self.guid       = guid
        self.shortName  = shortName
        self.fullName   = fullName

    def members(self):
        return ()

    def groups(self):
        return ()

    def verifyCredentials(credentials):
        return False

class DirectoryError(RuntimeError):
    """
    Generic directory error.
    """

class UnknownRecordTypeError(DirectoryError):
    """
    Unknown directory record type.
    """
