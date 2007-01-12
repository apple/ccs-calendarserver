##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
from twisted.internet.threads import deferToThread
from twisted.internet.reactor import callLater
from twisted.cred.credentials import UsernamePassword

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError

recordListCacheTimeout = 60 * 30 # 30 minutes

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
        self._delayedCalls = set()

        for recordType in self.recordTypes():
            self.recordsForType(recordType)

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
        return (
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources,
        )

    def recordsForType(self, recordType):
        """
        @param recordType: a record type
        @return: a dictionary containing all records for the given record
        type.  Keys are short names and values are the cooresponding
        OpenDirectoryRecord for the given record type.
        """
        def reloadCache():
            log.msg("Reloading %s record cache" % (recordType,))

            attrs = [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDS1AttrDistinguishedName,
                dsattributes.kDSNAttrCalendarPrincipalURI,
            ]

            if recordType == DirectoryService.recordType_users:
                listRecordType = dsattributes.kDSStdRecordTypeUsers
            elif recordType == DirectoryService.recordType_groups:
                listRecordType = dsattributes.kDSStdRecordTypeGroups
                attrs.append(dsattributes.kDSNAttrGroupMembers)
            elif recordType == DirectoryService.recordType_locations:
                listRecordType = dsattributes.kDSStdRecordTypeLocations
            elif recordType == DirectoryService.recordType_resources:
                listRecordType = dsattributes.kDSStdRecordTypeResources
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

                # FIXME: We get email address also
                # FIXME: In new schema, kDSNAttrCalendarPrincipalURI goes away
                cuaddrs = value.get(dsattributes.kDSNAttrCalendarPrincipalURI)
                cuaddrset = set()
                if cuaddrs is not None:
                    if isinstance(cuaddrs, str):
                        cuaddrset.add(cuaddrs)
                    else:
                        cuaddrset.update(cuaddrs)

                if recordType == DirectoryService.recordType_groups:
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
                    calendarUserAddresses = cuaddrset,
                    memberGUIDs           = memberGUIDs,
                )

            storage = {
                "status": "new",
                "records": records,
            }

            def rot():
                storage["status"] = "stale"
                removals = set()
                for call in self._delayedCalls:
                    if not call.active():
                        removals.add(call)
                for item in removals:
                    self._delayedCalls.remove(item)

            self._delayedCalls.add(callLater(recordListCacheTimeout, rot))

            self._records[recordType] = storage

        try:
            storage = self._records[recordType]
        except KeyError:
            reloadCache()
        else:
            if storage["status"] == "stale":
                storage["status"] = "loading"

                def onError(f):
                    storage["status"] = "stale" # Keep trying
                    log.err("Unable to load records of type %s from OpenDirectory due to unexpected error: %s"
                            % (recordType, f))

                d = deferToThread(reloadCache)
                d.addErrback(onError)

        return self._records[recordType]["records"]

    def listRecords(self, recordType):
        return self.recordsForType(recordType).itervalues()

    def recordWithShortName(self, recordType, shortName):
        return self.recordsForType(recordType).get(shortName, None)

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
        if self.recordType != DirectoryService.recordType_groups:
            return

        for guid in self._memberGUIDs:
            userRecord = self.service.recordWithGUID(guid)
            if userRecord is None:
                log.err("No record for member of group %s with GUID %s" % (self.shortName, guid))
            else:
                yield userRecord

    def groups(self):
        for groupRecord in self.service.recordsForType(DirectoryService.recordType_groups).itervalues():
            if self.guid in groupRecord._memberGUIDs:
                yield groupRecord

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            try:
                return opendirectory.authenticateUserBasic(self.service.directory, self.shortName, credentials.password)
            except opendirectory.ODError, e:
                log.err("OpenDirectory error while performing basic authentication for user %s: %r" % (self.shortName, e))
                return False

        return super(OpenDirectoryRecord, self).verifyCredentials(credentials)

class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
