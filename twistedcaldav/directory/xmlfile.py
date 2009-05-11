##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
##

"""
XML based user/group/resource directory service implementation.
"""

__all__ = [
    "XMLDirectoryService",
]

from time import time
import types

from twisted.cred.credentials import UsernamePassword
from twisted.web2.auth.digest import DigestedCredentials
from twisted.python.filepath import FilePath

from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.cachingdirectory import CachingDirectoryService,\
    CachingDirectoryRecord
from twistedcaldav.directory.xmlaccountsparser import XMLAccountsParser

class XMLDirectoryService(CachingDirectoryService):
    """
    XML based implementation of L{IDirectoryService}.
    """
    baseGUID = "9CA8DEC5-5A17-43A9-84A8-BE77C1FB9172"

    realmName = None

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.xmlFile)

    def __init__(self, xmlFile, alwaysStat=False):
        super(XMLDirectoryService, self).__init__()

        if type(xmlFile) is str:
            xmlFile = FilePath(xmlFile)

        self.xmlFile = xmlFile
        self._fileInfo = None
        self._lastCheck = 0
        self._alwaysStat = alwaysStat
        self._accounts()

    def recordTypes(self):
        recordTypes = (
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources
        )
        return recordTypes

    def queryDirectory(self, recordTypes, indexType, indexKey):
        
        for recordType in recordTypes:
            for xmlPrincipal in self._accounts()[recordType].itervalues():
                
                matched = False
                if indexType == self.INDEX_TYPE_GUID:
                    matched = indexKey == xmlPrincipal.guid
                elif indexType == self.INDEX_TYPE_SHORTNAME:
                    matched = indexKey in xmlPrincipal.shortNames
                elif indexType == self.INDEX_TYPE_CUA:
                    matched = indexKey in xmlPrincipal.calendarUserAddresses
                
                if matched:
                    record = XMLDirectoryRecord(
                        service       = self,
                        recordType    = recordType,
                        shortNames    = tuple(xmlPrincipal.shortNames),
                        xmlPrincipal  = xmlPrincipal,
                    )
                    self.recordCacheForType(recordType).addRecord(record,
                        indexType, indexKey)
            
    def recordsMatchingFields(self, fields, operand="or", recordType=None):
        # Default, brute force method search of underlying XML data

        def fieldMatches(fieldValue, value, caseless, matchType):
            if fieldValue is None:
                return False
            elif type(fieldValue) in types.StringTypes:
                fieldValue = (fieldValue,)
            
            for testValue in fieldValue:
                if caseless:
                    testValue = testValue.lower()
                    value = value.lower()
    
                if matchType == 'starts-with':
                    if testValue.startswith(value):
                        return True
                elif matchType == 'contains':
                    try:
                        _ignore_discard = testValue.index(value)
                        return True
                    except ValueError:
                        pass
                else: # exact
                    if testValue == value:
                        return True
                    
            return False

        def xmlPrincipalMatches(xmlPrincipal):
            if operand == "and":
                for fieldName, value, caseless, matchType in fields:
                    try:
                        fieldValue = getattr(xmlPrincipal, fieldName)
                        if not fieldMatches(fieldValue, value, caseless, matchType):
                            return False
                    except AttributeError:
                        # No property => no match
                        return False
                # we hit on every property
                return True
            else: # "or"
                for fieldName, value, caseless, matchType in fields:
                    try:
                        fieldValue = getattr(xmlPrincipal, fieldName)
                        if fieldMatches(fieldValue, value, caseless, matchType):
                            return True
                    except AttributeError:
                        # No value
                        pass
                # we didn't hit any
                return False

        if recordType is None:
            recordTypes = list(self.recordTypes())
        else:
            recordTypes = (recordType,)

        for recordType in recordTypes:
            for xmlPrincipal in self._accounts()[recordType].itervalues():
                if xmlPrincipalMatches(xmlPrincipal):
                    
                    # Load/cache record from its GUID
                    record = self.recordWithGUID(xmlPrincipal.guid)
                    if record:
                        yield record

    def _accounts(self):
        currentTime = time()
        if self._alwaysStat or currentTime - self._lastCheck > 60:
            self.xmlFile.restat()
            self._lastCheck = currentTime
            fileInfo = (self.xmlFile.getmtime(), self.xmlFile.getsize())
            if fileInfo != self._fileInfo:
                parser = XMLAccountsParser(self.xmlFile)
                self._parsedAccounts = parser.items
                self.realmName = parser.realm
                self._fileInfo = fileInfo
        return self._parsedAccounts

class XMLDirectoryRecord(CachingDirectoryRecord):
    """
    XML based implementation implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, shortNames, xmlPrincipal):
        super(XMLDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = xmlPrincipal.guid,
            shortNames            = shortNames,
            fullName              = xmlPrincipal.fullName,
            firstName             = xmlPrincipal.firstName,
            lastName              = xmlPrincipal.lastName,
            emailAddresses        = xmlPrincipal.emailAddresses,
            calendarUserAddresses = xmlPrincipal.calendarUserAddresses,
            enabledForCalendaring = xmlPrincipal.enabledForCalendaring,
        )

        self.password          = xmlPrincipal.password
        self._members          = xmlPrincipal.members
        self._groups           = xmlPrincipal.groups

    def members(self):
        for recordType, shortName in self._members:
            yield self.service.recordWithShortName(recordType, shortName)

    def groups(self):
        for shortName in self._groups:
            yield self.service.recordWithShortName(DirectoryService.recordType_groups, shortName)

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            return credentials.password == self.password
        if isinstance(credentials, DigestedCredentials):
            return credentials.checkPassword(self.password)

        return super(XMLDirectoryRecord, self).verifyCredentials(credentials)
