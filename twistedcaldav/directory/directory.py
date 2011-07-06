# -*- test-case-name: twistedcaldav.directory.test -*-
##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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
    "UnknownRecordTypeError",
]

import sys
import types

from zope.interface import implements

from twisted.cred.error import UnauthorizedLogin
from twisted.cred.checkers import ICredentialsChecker
from twext.web2.dav.auth import IPrincipalCredentials
from twisted.internet.defer import succeed

from twext.python.log import LoggingMixIn

from twistedcaldav.config import config
from twistedcaldav.directory.idirectory import IDirectoryService, IDirectoryRecord
from twistedcaldav.directory.util import uuidFromName
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav import servers

class DirectoryService(LoggingMixIn):
    implements(IDirectoryService, ICredentialsChecker)

    ##
    # IDirectoryService
    ##

    realmName = None

    recordType_users = "users"
    recordType_people = "people"
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

    # Needed by twistedcaldav.directorybackedaddressbook
    liveQuery = False

    def setRealm(self, realmName):
        self.realmName = realmName

    def available(self):
        """
        By default, the directory is available.  This may return a boolean or a
        Deferred which fires a boolean.

        A return value of "False" means that the directory is currently
        unavailable due to the service starting up.
        """
        return True
    # end directorybackedaddressbook requirements

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

        # See if record is enabledForLogin
        if not credentials.authnPrincipal.record.isLoginEnabled():
            raise UnauthorizedLogin("User not allowed to log in: %s" %
                (credentials.credentials.username,))

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
                credentials.authnPrincipal,
                credentials.authzPrincipal,
            )
        else:
            if credentials.authnPrincipal.record.verifyCredentials(credentials.credentials):
                return (
                    credentials.authnPrincipal.principalURL(),
                    credentials.authzPrincipal.principalURL(),
                    credentials.authnPrincipal,
                    credentials.authzPrincipal,
                )
            else:
                raise UnauthorizedLogin("Incorrect credentials for %s" % (credentials.credentials.username,)) 

    def recordTypes(self):
        raise NotImplementedError("Subclass must implement recordTypes()")

    def listRecords(self, recordType):
        raise NotImplementedError("Subclass must implement listRecords()")

    def recordWithShortName(self, recordType, shortName):
        for record in self.listRecords(recordType):
            if shortName in record.shortNames:
                return record
        return None

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
                if address[7:] in record.emailAddresses:
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
                        testValue.index(value)
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

    def isAvailable(self):
        return True

    def getParams(self, params, defaults, ignore=None):
        """ Checks configuration parameters for unexpected/ignored keys, and
            applies default values. """

        keys = set(params.keys())

        result = {}
        for key in defaults.iterkeys():
            if key in params:
                result[key] = params[key]
                keys.remove(key)
            else:
                result[key] = defaults[key]

        if ignore:
            for key in ignore:
                if key in params:
                    self.log_warn("Ignoring obsolete directory service parameter: %s" % (key,))
                    keys.remove(key)

        if keys:
            raise DirectoryConfigurationError("Invalid directory service parameter(s): %s" % (", ".join(list(keys)),))
        return result


    def createRecord(self, recordType, guid=None, shortNames=(), authIDs=set(),
        fullName=None, firstName=None, lastName=None, emailAddresses=set(),
        uid=None, password=None, **kwargs):
        """
        Create/persist a directory record based on the given values
        """
        raise NotImplementedError("Subclass must implement createRecord")

    def updateRecord(self, recordType, guid=None, shortNames=(), authIDs=set(),
        fullName=None, firstName=None, lastName=None, emailAddresses=set(),
        uid=None, password=None, **kwargs):
        """
        Update/persist a directory record based on the given values
        """
        raise NotImplementedError("Subclass must implement updateRecord")

    def destroyRecord(self, recordType, guid=None):
        """
        Remove a directory record from the directory
        """
        raise NotImplementedError("Subclass must implement destroyRecord")

    def createRecords(self, data):
        """
        Create directory records in bulk
        """
        raise NotImplementedError("Subclass must implement createRecords")

class DirectoryRecord(LoggingMixIn):
    implements(IDirectoryRecord)

    def __repr__(self):
        return "<%s[%s@%s(%s)] %s(%s) %r @ %s/#%s>" % (
            self.__class__.__name__,
            self.recordType,
            self.service.guid,
            self.service.realmName,
            self.guid,
            ",".join(self.shortNames),
            self.fullName,
            self.serverURI(),
            self.partitionID,
        )

    def __init__(
        self, service, recordType, guid,
        shortNames=(), authIDs=set(), fullName=None,
        firstName=None, lastName=None, emailAddresses=set(),
        calendarUserAddresses=set(), autoSchedule=False, enabledForCalendaring=None,
        enabledForAddressBooks=None,
        uid=None,
        enabledForLogin=True,
        **kwargs
    ):
        assert service.realmName is not None
        assert recordType
        assert shortNames and isinstance(shortNames, tuple) 

        if not guid:
            guid = uuidFromName(service.guid, "%s:%s" % (recordType, ",".join(shortNames)))

        if uid is None:
            uid = guid

        if fullName is None:
            fullName = ""

        self.service                = service
        self.recordType             = recordType
        self.guid                   = guid
        self.uid                    = uid
        self.enabled                = False
        self.serverID               = ""
        self.partitionID            = ""
        self.shortNames             = shortNames
        self.authIDs                = authIDs
        self.fullName               = fullName
        self.firstName              = firstName
        self.lastName               = lastName
        self.emailAddresses         = emailAddresses
        self.enabledForCalendaring  = enabledForCalendaring
        self.autoSchedule           = autoSchedule
        self.enabledForAddressBooks = enabledForAddressBooks
        self.enabledForLogin        = enabledForLogin
        self.extras                 = kwargs



    def get_calendarUserAddresses(self):
        """
        Dynamically construct a calendarUserAddresses attribute which describes
        this L{DirectoryRecord}.

        @see: L{IDirectoryRecord.calendarUserAddresses}.
        """
        if not self.enabledForCalendaring:
            return frozenset()
        return frozenset(
            ["urn:uuid:%s" % (self.guid,)] +
            ["mailto:%s" % (emailAddress,)
             for emailAddress in self.emailAddresses]
        )

    calendarUserAddresses = property(get_calendarUserAddresses)

    def __cmp__(self, other):
        if not isinstance(other, DirectoryRecord):
            return NotImplemented

        for attr in ("service", "recordType", "shortNames", "guid"):
            diff = cmp(getattr(self, attr), getattr(other, attr))
            if diff != 0:
                return diff
        return 0

    def __hash__(self):
        h = hash(self.__class__.__name__)
        for attr in ("service", "recordType", "shortNames", "guid",
                     "enabled", "enabledForCalendaring"):
            h = (h + hash(getattr(self, attr))) & sys.maxint

        return h

    def addAugmentInformation(self, augment):
        
        if augment:
            self.enabled = augment.enabled
            self.serverID = augment.serverID
            self.partitionID = augment.partitionID
            self.enabledForCalendaring = augment.enabledForCalendaring
            self.enabledForAddressBooks = augment.enabledForAddressBooks
            self.autoSchedule = augment.autoSchedule
            self.enabledForLogin = augment.enabledForLogin

            if (self.enabledForCalendaring or self.enabledForAddressBooks) and self.recordType == self.service.recordType_groups:
                self.enabledForCalendaring = False
                self.enabledForAddressBooks = False

                # For augment records cloned from the Default augment record,
                # don't emit this message:
                if not augment.clonedFromDefault:
                    self.log_error("Group '%s(%s)' cannot be enabled for calendaring or address books" % (self.guid, self.shortNames[0],))

        else:
            # Groups are by default always enabled
            self.enabled = (self.recordType == self.service.recordType_groups)
            self.serverID = ""
            self.partitionID = ""
            self.enabledForCalendaring = False
            self.enabledForAddressBooks = False
            self.enabledForLogin = False


    def applySACLs(self):
        """
        Disable calendaring and addressbooks as dictated by SACLs
        """

        if config.EnableSACLs and self.CheckSACL:
            username = self.shortNames[0]
            if self.CheckSACL(username, "calendar") != 0:
                self.log_debug("%s is not enabled for calendaring due to SACL"
                               % (username,))
                self.enabledForCalendaring = False
            if self.CheckSACL(username, "addressbook") != 0:
                self.log_debug("%s is not enabled for addressbooks due to SACL"
                               % (username,))
                self.enabledForAddressBooks = False

    def isLoginEnabled(self):
        """
        Returns True if the user should be allowed to log in, based on the
        enabledForLogin attribute, which is currently controlled by the
        DirectoryService implementation.
        """
        return self.enabledForLogin

    def members(self):
        return ()

    def expandedMembers(self, members=None, seen=None):
        """
        Return the complete, flattened set of members of a group, including
        all sub-groups.
        """
        if members is None:
            members = set()
        if seen is None:
            seen = set()

        if self not in seen:
            seen.add(self)
            for member in self.members():
                members.add(member)
                if member.recordType == self.service.recordType_groups:
                    member.expandedMembers(members=members, seen=seen)

        return members


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

    def serverURI(self):
        """
        URL of the server hosting this record. Return None if hosted on this server.
        """
        if config.Servers.Enabled and self.serverID:
            return servers.Servers.getServerURIById(self.serverID)
        else:
            return None
    
    def server(self):
        """
        Server hosting this record. Return None if hosted on this server.
        """
        if config.Servers.Enabled and self.serverID:
            return servers.Servers.getServerById(self.serverID)
        else:
            return None
    
    def partitionURI(self):
        """
        URL of the server hosting this record. Return None if hosted on this server.
        """
        if config.Servers.Enabled and self.serverID:
            s = servers.Servers.getServerById(self.serverID)
            if s:
                return s.getPartitionURIForId(self.partitionID)
        return None
    
    def locallyHosted(self):
        """
        Hosted on this server/partition instance.
        """
        
        if config.Servers.Enabled and self.serverID:
            s = servers.Servers.getServerById(self.serverID)
            if s:
                return s.thisServer and (not self.partitionID or self.partitionID == config.ServerPartitionID)
        return True

    def thisServer(self):
        if config.Servers.Enabled and self.serverID:
            s = servers.Servers.getServerById(self.serverID)
            if s:
                return s.thisServer
        return True
        
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
    def __init__(self, recordType):
        DirectoryError.__init__(self, "Invalid record type: %s" % (recordType,))
        self.recordType = recordType


# So CheckSACL will be parameterized
# We do this after DirectoryRecord is defined
try:
    from calendarserver.platform.darwin._sacl import CheckSACL
    DirectoryRecord.CheckSACL = CheckSACL
except ImportError:
    DirectoryRecord.CheckSACL = None

