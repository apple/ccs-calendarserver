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
    baseGUID = "891F8321-ED02-424C-BA72-89C32F215C1E"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.node)

    def __init__(self, node="/Search"):
        """
        @param node: an OpenDirectory node name to bind to.
        """
        directory = opendirectory.odInit(node)
        if directory is None:
            raise OpenDirectoryInitError("Failed to open Open Directory Node: %s" % (node,))

        self.realmName = node
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
        return ("user", "group", "resource", "location",)

    def _cacheRecords(self, recordType):
        if recordType not in self._records:
            log.msg("Reloading %s record cache" % (recordType,))

            attrs = [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDS1AttrDistinguishedName,
            ]
            if recordType == "user":
                listRecordType = dsattributes.kDSStdRecordTypeUsers
            elif recordType == "group":
                listRecordType = dsattributes.kDSStdRecordTypeGroups
                attrs += [dsattributes.kDSNAttrGroupMembers,]
            elif recordType == "resource":
                listRecordType = dsattributes.kDSStdRecordTypeResources
            elif recordType == "location":
                listRecordType = dsattributes.kDSStdRecordTypeLocations
            else:
                raise UnknownRecordTypeError("Unknown Open Directory record type: %s" % (recordType,))

            records = {}

            try:
                results = opendirectory.listAllRecordsWithAttributes(self.directory, listRecordType, attrs)
            except opendirectory.ODError, ex:
                log.msg("OpenDirectory error: %s", str(ex))
                raise

            for (key, value) in results.iteritems():
                shortName = key
                guid = value.get(dsattributes.kDS1AttrGeneratedUID)
                if not guid:
                    continue
                realName = value.get(dsattributes.kDS1AttrDistinguishedName)

                if recordType == "group":
                    memberGUIDs = value.get(dsattributes.kDSNAttrGroupMembers)
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
                    fullName              = realName,
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
            return opendirectory.authenticateUserBasic(self.service.directory, self.shortName, credentials.password)

        return super(OpenDirectoryRecord, self).verifyCredentials(credentials)

class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
