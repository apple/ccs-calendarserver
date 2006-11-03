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
    "DirectoryRecord",
]

from zope.interface import implements

from twistedcaldav.directory.idirectory import IDirectoryService, IDirectoryRecord

class DirectoryService(object):
    implements(IDirectoryService)

class DirectoryRecord(object):
    implements(IDirectoryRecord)

    def __init__(self, directory, recordType, guid, shortName, fullName=None, calendarUserAddresses=()):
        self.directory             = directory
        self.recordType            = recordType
        self.guid                  = guid
        self.shortName             = shortName
        self.fullName              = fullName
        self.calendarUserAddresses = calendarUserAddresses

    def authenticate(credentials):
        return False
