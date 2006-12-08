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
Apple Open Directory directory service implementation.
"""

__all__ = [
    "OpenDirectoryService",
    "OpenDirectoryInitError",
]

import sys

import opendirectory
import dsattributes

from twisted.python import log
from twisted.internet import reactor
from twisted.cred.credentials import UsernamePassword

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError

recordListCacheTimeout = 60 * 5 # 5 minutes

class OpenDirectoryService(DirectoryService):
    """
    Open Directory implementation of L{IDirectoryService}.
    """
    def __repr__(self):
        return "<%s %s>" % (self.__class__.__name__, self.node)

    def __init__(self, node="/Search"):
        """
        @param node: an OpenDirectory node name to bind to.
        """
        directory = opendirectory.odInit(node)
        if directory is None:
            raise OpenDirectoryInitError("Failed to open Open Directory Node: %s" % (node,))

        self.directory = directory
        self.node = node
        self._records = {}

    def __cmp__(self, other):
        if not isinstance(other, DirectoryRecord):
            return super(DirectoryRecord, self).__eq__(other)

        for attr in ("directory", "node"):
            diff = cmp(getattr(self, attr), getattr(other, attr))
            if diff != 0:
                return diff
        return 0

    def __hash__(self):
        h = hash(self.__class__)
        for attr in ("directory", "node"):
            h = (h + hash(getattr(self, attr))) & sys.maxint
        return h

    def recordTypes(self):
        return ("user", "group", "resource")

    def _cacheRecords(self, recordType):
        if recordType not in self._records:
            log.msg("Reloading %s record cache" % (recordType,))

            if recordType == "user":
                listRecords = opendirectory.listUsers
            elif recordType == "group":
                listRecords = opendirectory.listGroups
            elif recordType == "resource":
                listRecords = opendirectory.listResources
            else:
                raise UnknownRecordTypeError("Unknown Open Directory record type: %s" % (recordType,))

            records = {}

            for shortName, guid, lastModified, principalURI in listRecords(self.directory):
                if not guid:
                    continue

                # FIXME: This is a second directory lookup; we should have gotten everything in one pass...
                if recordType == "group":
                    result = opendirectory.listGroupsWithAttributes(self.directory, [shortName])
                    if result is None or shortName not in result:
                        log.err("Group %s exists and then doesn't." % (shortName,))
                        continue
                    result = result[shortName]

                    memberGUIDs = result.get(dsattributes.attrGroupMembers, None)
                    if memberGUIDs is None:
                        memberGUIDs = ()
                    elif type(memberGUIDs) is str:
                        memberGUIDs = (memberGUIDs,)
                else:
                    memberGUIDs = ()

                records[shortName] = OpenDirectoryRecord(
                    service               = self,
                    recordType            = recordType,
                    guid                  = guid,
                    shortName             = shortName,
                    fullName              = None, # FIXME: Need to get this attribute
                    calendarUserAddresses = set(), # FIXME: Should be able to look up email, etc.
                    memberGUIDs           = memberGUIDs,
                )

            if records:
                self._records[recordType] = records

                def flush():
                    log.msg("Flushing %s record cache" % (recordType,))
                    del self._records[recordType]
                reactor.callLater(recordListCacheTimeout, flush)
            else:
                # records is empty.  This may mean the directory went down.
                # Don't cache this result, so that we keep checking the directory.
                return records

        return self._records[recordType]

    def listRecords(self, recordType):
        return self._cacheRecords(recordType).itervalues()

    def recordWithShortName(self, recordType, shortName):
        return self._cacheRecords(recordType).get(shortName, None)

#    def recordWithShortName(self, recordType, shortName):
#        if recordType == "user":
#            listRecords = opendirectory.listUsersWithAttributes
#        elif recordType == "group":
#            listRecords = opendirectory.listGroupsWithAttributes
#        elif recordType == "resource":
#            listRecords = opendirectory.listResourcesWithAttributes
#        else:
#            raise UnknownRecordTypeError("Unknown record type: %s" % (recordType,))
#
#        result = listRecords(self.directory, [shortName])
#        if result is None or shortName not in result:
#            return None
#        else:
#            result = result[shortName]
#
#        if dsattributes.attrGUID in result:
#            guid = result[dsattributes.attrGUID]
#        else:
#            raise DirectoryError("Found OpenDirectory record %s of type %s with no GUID attribute"
#                                 % (shortName, recordType))
#
#        if dsattributes.attrRealName in result:
#            fullName = result[dsattributes.attrRealName]
#        else:
#            fullName = None
#
#        return OpenDirectoryRecord(
#            service = self,
#            recordType = recordType,
#            guid = guid,
#            shortName = shortName,
#            fullName = fullName,
#        )

class OpenDirectoryRecord(DirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, guid, shortName, fullName, calendarUserAddresses, memberGUIDs):
        super(OpenDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = guid,
            shortName             = shortName,
            fullName              = fullName,
            calendarUserAddresses = calendarUserAddresses,
        )
        self._memberGUIDs = tuple(memberGUIDs)

    def members(self):
        if self.recordType != "group":
            return

        for guid in self._memberGUIDs:
            userRecord = self.service.recordWithGUID(guid)
            if userRecord is None:
                log.err("No record for member of group %s with GUID %s" % (self.shortName, guid))
            else:
                yield userRecord

    def groups(self):
        for groupRecord in self.service._cacheRecords("group").itervalues():
            if self.guid in groupRecord._memberGUIDs:
                yield groupRecord

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            return opendirectory.authenticateUser(self.service.directory, self.shortName, credentials.password)

        return super(OpenDirectoryRecord, self).verifyCredentials(credentials)

class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
