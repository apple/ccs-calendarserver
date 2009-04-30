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
Generic directory service classes.
"""

__all__ = [
    "DirectoryService",
    "DirectoryRecord",
    "DirectoryError",
    "DirectoryConfigurationError",
    "UnknownRecordError",
    "UnknownRecordTypeError",
]

import sys
import types

from zope.interface import implements

from twisted.cred.error import UnauthorizedLogin
from twisted.cred.checkers import ICredentialsChecker
from twisted.web2.dav.auth import IPrincipalCredentials
from twisted.internet.defer import succeed

from twistedcaldav.log import LoggingMixIn
from twistedcaldav.directory.idirectory import IDirectoryService, IDirectoryRecord
from twistedcaldav.directory.util import uuidFromName
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr

class DirectoryService(LoggingMixIn):
    implements(IDirectoryService, ICredentialsChecker)

    ##
    # IDirectoryService
    ##

    realmName = None

    recordType_users = "users"
    recordType_groups = "groups"
    recordType_locations = "locations"
    recordType_resources = "resources"
    
    def _generatedGUID(self):
        if not hasattr(self, "_guid"):
            realmName = self.realmName

            assert self.baseGUID, "Class %s must provide a baseGUID attribute" % (self.__class__.__name__,)

            if realmName is None:
                self.log_error("Directory service %s has no realm name or GUID; generated service GUID will not be unique." % (self,))
                realmName = ""
            else:
                self.log_info("Directory service %s has no GUID; generating service GUID from realm name." % (self,))

            self._guid = uuidFromName(self.baseGUID, realmName)

        return self._guid

    baseGUID = None
    guid = property(_generatedGUID)

    ##
    # ICredentialsChecker
    ##

    # For ICredentialsChecker
    credentialInterfaces = (IPrincipalCredentials,)

    def requestAvatarId(self, credentials):
        credentials = IPrincipalCredentials(credentials)

        # FIXME: ?
        # We were checking if principal is enabled; seems unnecessary in current
        # implementation because you shouldn't have a principal object for a
        # disabled directory principal.

        if credentials.authnPrincipal is None:
            raise UnauthorizedLogin("No such user: %s" % (credentials.credentials.username,))

        # Handle Kerberos as a separate behavior
        try:
            from twistedcaldav.authkerb import NegotiateCredentials
        except ImportError:
            NegotiateCredentials=None
        
        if NegotiateCredentials and isinstance(credentials.credentials, 
                                               NegotiateCredentials):
            # If we get here with Kerberos, then authentication has already succeeded
            return (
                credentials.authnPrincipal.principalURL(),
                credentials.authzPrincipal.principalURL(),
            )
        else:
            if credentials.authnPrincipal.record.verifyCredentials(credentials.credentials):
                return (
                    credentials.authnPrincipal.principalURL(),
                    credentials.authzPrincipal.principalURL(),
                )
            else:
                raise UnauthorizedLogin("Incorrect credentials for %s" % (credentials.credentials.username,)) 

    def recordTypes(self):
        raise NotImplementedError("Subclass must implement recordTypes()")

    def listRecords(self, recordType):
        raise NotImplementedError("Subclass must implement listRecords()")

    def recordWithShortName(self, recordType, shortName):
        raise NotImplementedError("Subclass must implement recordWithShortName()")

    def recordWithUID(self, uid):
        for record in self.allRecords():
            if record.uid == uid:
                return record
        return None

    def recordWithGUID(self, guid):
        for record in self.allRecords():
            if record.guid == guid:
                return record
        return None

    def recordWithAuthID(self, authID):
        for record in self.allRecords():
            if authID in record.authIDs:
                return record
        return None

    def recordWithCalendarUserAddress(self, address):
        address = normalizeCUAddr(address)
        record = None
        if address.startswith("urn:uuid:"):
            guid = address[9:]
            record = self.recordWithGUID(guid)
        elif address.startswith("mailto:"):
            for record in self.allRecords():
                if address in record.calendarUserAddresses:
                    break
            else:
                return None

        return record if record and record.enabledForCalendaring else None

    def allRecords(self):
        for recordType in self.recordTypes():
            for record in self.listRecords(recordType):
                yield record

    def recordsMatchingFieldsWithCUType(self, fields, operand="or",
        cuType=None):
        if cuType:
            recordType = DirectoryRecord.fromCUType(cuType)
        else:
            recordType = None

        return self.recordsMatchingFields(fields, operand=operand,
            recordType=recordType)


    def recordsMatchingFields(self, fields, operand="or", recordType=None):
        # Default, bruteforce method; override with one optimized for each
        # service

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

        def recordMatches(record):
            if operand == "and":
                for fieldName, value, caseless, matchType in fields:
                    try:
                        fieldValue = getattr(record, fieldName)
                        if not fieldMatches(fieldValue, value, caseless,
                            matchType):
                            return False
                    except AttributeError:
                        # No property => no match
                        return False
                # we hit on every property
                return True
            else: # "or"
                for fieldName, value, caseless, matchType in fields:
                    try:
                        fieldValue = getattr(record, fieldName)
                        if fieldMatches(fieldValue, value, caseless,
                            matchType):
                            return True
                    except AttributeError:
                        # No value
                        pass
                # we didn't hit any
                return False

        def yieldMatches(recordType):
            try:
                if recordType is None:
                    recordTypes = list(self.recordTypes())
                else:
                    recordTypes = (recordType,)

                for recordType in recordTypes:
                    for record in self.listRecords(recordType):
                        if recordMatches(record):
                            yield record

            except UnknownRecordTypeError:
                # Skip this service since it doesn't understand this record type
                pass

        return succeed(yieldMatches(recordType))

    def getResourceInfo(self):
        return ()

class DirectoryRecord(LoggingMixIn):
    implements(IDirectoryRecord)

    def __repr__(self):
        return "<%s[%s@%s(%s)] %s(%s) %r>" % (
            self.__class__.__name__,
            self.recordType,
            self.service.guid,
            self.service.realmName,
            self.guid,
            ",".join(self.shortNames),
            self.fullName
        )

    def __init__(
        self, service, recordType, guid, shortNames=(), authIDs=set(), fullName=None,
        firstName=None, lastName=None, emailAddresses=set(),
        calendarUserAddresses=set(),
        enabledForCalendaring=None,
        uid=None,
    ):
        assert service.realmName is not None
        assert recordType
        assert shortNames and isinstance(shortNames, tuple) 

        if not guid:
            guid = uuidFromName(service.guid, "%s:%s" % (recordType, ",".join(shortNames)))

        if uid is None:
            uid = guid

        if enabledForCalendaring is None:
            if recordType == service.recordType_groups:
                enabledForCalendaring = False
            else:
                enabledForCalendaring = True

        if enabledForCalendaring and recordType == service.recordType_groups:
            raise AssertionError("Groups may not be enabled for calendaring")

        if enabledForCalendaring:
            calendarUserAddresses = set(calendarUserAddresses)
            calendarUserAddresses.add("urn:uuid:%s" % (guid,))
        else:
            assert len(calendarUserAddresses) == 0

        self.service               = service
        self.recordType            = recordType
        self.guid                  = guid
        self.uid                   = uid
        self.shortNames            = shortNames
        self.authIDs               = authIDs
        self.fullName              = fullName
        self.firstName             = firstName
        self.lastName              = lastName
        self.emailAddresses        = emailAddresses
        self.enabledForCalendaring = enabledForCalendaring
        self.calendarUserAddresses = calendarUserAddresses

    def __cmp__(self, other):
        if not isinstance(other, DirectoryRecord):
            return NotImplemented

        for attr in ("service", "recordType", "shortNames", "guid"):
            diff = cmp(getattr(self, attr), getattr(other, attr))
            if diff != 0:
                return diff
        return 0

    def __hash__(self):
        h = hash(self.__class__)
        for attr in ("service", "recordType", "shortNames", "guid",
                     "enabledForCalendaring"):
            h = (h + hash(getattr(self, attr))) & sys.maxint

        return h

    def members(self):
        return ()

    def groups(self):
        return ()

    def verifyCredentials(self, credentials):
        return False

    # Mapping from directory record.recordType to RFC2445 CUTYPE values
    _cuTypes = {
        'users' : 'INDIVIDUAL',
        'groups' : 'GROUP',
        'resources' : 'RESOURCE',
        'locations' : 'ROOM',
    }

    def getCUType(self):
        return self._cuTypes.get(self.recordType, "UNKNOWN")

    @classmethod
    def fromCUType(cls, cuType):
        for key, val in cls._cuTypes.iteritems():
            if val == cuType:
                return key
        return None

class DirectoryError(RuntimeError):
    """
    Generic directory error.
    """

class DirectoryConfigurationError(DirectoryError):
    """
    Invalid directory configuration.
    """

class UnknownRecordTypeError(DirectoryError):
    """
    Unknown directory record type.
    """
