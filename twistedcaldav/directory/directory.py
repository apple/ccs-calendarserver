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
from twisted.internet.defer import succeed, inlineCallbacks

from twext.python.log import LoggingMixIn

from twistedcaldav.config import config
from twistedcaldav.directory.idirectory import IDirectoryService, IDirectoryRecord
from twistedcaldav.directory.util import uuidFromName
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav import servers
from twistedcaldav.memcacher import Memcacher
from twistedcaldav import memcachepool
from twisted.python.reflect import namedClass
from twisted.python.usage import Options, UsageError
from twistedcaldav.stdconfig import DEFAULT_CONFIG, DEFAULT_CONFIG_FILE
from twisted.application import service
from twisted.plugin import IPlugin
from zope.interface import implements

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

    @inlineCallbacks
    def cacheGroupMembership(self, guids):
        """
        Update the "which groups is each principal in" cache.  The only groups
        that the server needs to worry about are the ones which have been
        delegated to.  So instead of faulting in all groups a principal is in,
        we pre-fault in all the delgated-to groups and build an index to
        quickly look up principal membership.

        guids is the set of every guid that's been directly delegated to, and
        can be a mixture of users and groups.
        """
        groups = set()
        for guid in guids:
            record = self.recordWithGUID(guid)
            if record is not None and record.recordType == self.recordType_groups:
                groups.add(record)

        members = { }
        for group in groups:
            groupMembers = group.expandedMembers()
            for member in groupMembers:
                if member.recordType == self.recordType_users:
                    memberships = members.setdefault(member.guid, set())
                    memberships.add(group.guid)

        for member, groups in members.iteritems():
            yield self.groupMembershipCache.setGroupsFor(member, groups)

        self.groupMembershipCache.createMarker()


class GroupMembershipCache(Memcacher, LoggingMixIn):
    """
    Caches group membership information

    This cache is periodically updated by a side car so that worker processes
    never have to ask the directory service directly for group membership
    information.

    Keys in this cache are:

    "group-membership-cache-populated" : gets set to "true" after the cache
    is populated, so clients know they can now use it.  Note, this needs to
    be made robust in the face of memcached evictions.

    "groups-for:<GUID>" : comma-separated list of groups that GUID is a member
    of

    """

    def __init__(self, namespace, pickle=False, no_invalidation=False,
        key_normalization=True, expireSeconds=0):

        super(GroupMembershipCache, self).__init__(namespace, pickle=pickle,
            no_invalidation=no_invalidation,
            key_normalization=key_normalization)

        self.expireSeconds = expireSeconds

    def setGroupsFor(self, guid, memberships):
        self.log_debug("set groups-for %s : %s" % (guid, memberships))
        return self.set("groups-for:%s" %
            (str(guid)), str(",".join(memberships)),
            expire_time=self.expireSeconds)

    def getGroupsFor(self, guid):
        self.log_debug("get groups-for %s" % (guid,))
        def _value(value):
            if value:
                return set(value.split(","))
            else:
                return set()
        d = self.get("groups-for:%s" % (str(guid),))
        d.addCallback(_value)
        return d

    def deleteGroupsFor(self, guid, proxyType):
        return self.delete("groups-for:%s" % (str(guid),))

    def createMarker(self):
        return self.set("proxy-cache-populated", "true",
            expire_time=self.expireSeconds)

    def checkMarker(self):
        def _value(value):
            return value == "true"
        d = self.get("proxy-cache-populated")
        d.addCallback(_value)
        return d


class GroupMembershipCacheUpdater(LoggingMixIn):
    """
    Responsible for updating memcached with group memberships.  This will run
    in a sidecar.  There are two sources of proxy data to pull from: the local
    proxy database, and the location/resource info in the directory system.

    TODO: Implement location/resource
    """

    def __init__(self, proxyDB, directory, expireSeconds, cache=None,
        namespace=None):
        self.proxyDB = proxyDB
        self.directory = directory
        if cache is None:
            assert namespace is not None, "namespace must be specified if GroupMembershipCache is not provided"
            cache = GroupMembershipCache(namespace, expireSeconds=expireSeconds)
        self.cache = cache

    @inlineCallbacks
    def updateCache(self):
        """
        Iterate the proxy database to retrieve all the principals who have been
        delegated to.  Fault these principals in.  For any of these principals
        that are groups, expand the members of that group and store those in
        the cache
        """
        # TODO: add memcached eviction protection

        self.log_debug("Updating group membership cache")

        guids = set()

        proxyGroups = (yield self.proxyDB.getAllGroups())
        for proxyGroup in proxyGroups:

            # Protect against bogus entries in proxy db:
            if "#" not in proxyGroup:
                continue

            for guid in (yield self.proxyDB.getMembers(proxyGroup)):
                guids.add(guid)


        yield self.directory.cacheGroupMembership(guids)


class GroupMembershipCacherOptions(Options):
    optParameters = [[
        "config", "f", DEFAULT_CONFIG_FILE, "Path to configuration file."
    ]]

    def __init__(self, *args, **kwargs):
        super(GroupMembershipCacherOptions, self).__init__(*args, **kwargs)

        self.overrides = {}

    def _coerceOption(self, configDict, key, value):
        """
        Coerce the given C{val} to type of C{configDict[key]}
        """
        if key in configDict:
            if isinstance(configDict[key], bool):
                value = value == "True"

            elif isinstance(configDict[key], (int, float, long)):
                value = type(configDict[key])(value)

            elif isinstance(configDict[key], (list, tuple)):
                value = value.split(',')

            elif isinstance(configDict[key], dict):
                raise UsageError(
                    "Dict options not supported on the command line"
                )

            elif value == 'None':
                value = None

        return value

    def _setOverride(self, configDict, path, value, overrideDict):
        """
        Set the value at path in configDict
        """
        key = path[0]

        if len(path) == 1:
            overrideDict[key] = self._coerceOption(configDict, key, value)
            return

        if key in configDict:
            if not isinstance(configDict[key], dict):
                raise UsageError(
                    "Found intermediate path element that is not a dictionary"
                )

            if key not in overrideDict:
                overrideDict[key] = {}

            self._setOverride(
                configDict[key], path[1:],
                value, overrideDict[key]
            )


    def opt_option(self, option):
        """
        Set an option to override a value in the config file. True, False, int,
        and float options are supported, as well as comma seperated lists. Only
        one option may be given for each --option flag, however multiple
        --option flags may be specified.
        """

        if "=" in option:
            path, value = option.split('=')
            self._setOverride(
                DEFAULT_CONFIG,
                path.split('/'),
                value,
                self.overrides
            )
        else:
            self.opt_option('%s=True' % (option,))

    opt_o = opt_option

    def postOptions(self):
        config.load(self['config'])
        config.updateDefaults(self.overrides)
        self.parent['pidfile'] = None



class GroupMembershipCacherService(service.Service, LoggingMixIn):
    """
    Service to update the group membership cache at a configured interval
    """

    def __init__(self, proxyDB, directory, namespace, updateSeconds,
        expireSeconds, reactor=None, updateMethod=None):

        self.updater = GroupMembershipCacheUpdater(proxyDB, directory,
            expireSeconds, namespace=namespace)

        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        self.updateSeconds = updateSeconds
        self.nextUpdate = None
        if updateMethod:
            self.updateMethod = updateMethod
        else:
            self.updateMethod = self.updater.updateCache

    def startService(self):
        self.log_warn("Starting group membership cacher service")
        service.Service.startService(self)
        return self.update()

    @inlineCallbacks
    def update(self):
        self.nextUpdate = None
        try:
            yield self.updateMethod()
        finally:
            self.log_debug("Scheduling next group membership update")
            self.nextUpdate = self.reactor.callLater(self.updateSeconds,
                self.update)

    def stopService(self):
        self.log_warn("Stopping group membership cacher service")
        service.Service.stopService(self)
        if self.nextUpdate is not None:
            self.nextUpdate.cancel()


class GroupMembershipCacherServiceMaker(LoggingMixIn):
    """
    Configures and returns a GroupMembershipCacherService
    """
    implements(IPlugin, service.IServiceMaker)

    tapname = "caldav_groupcacher"
    description = "Group Membership Cacher"
    options = GroupMembershipCacherOptions

    def makeService(self, options):

        # Setup the directory
        from calendarserver.tap.util import directoryFromConfig
        directory = directoryFromConfig(config)

        # Setup the ProxyDB Service
        proxydbClass = namedClass(config.ProxyDBService.type)

        self.log_warn("Configuring proxydb service of type: %s" % (proxydbClass,))

        try:
            proxyDB = proxydbClass(**config.ProxyDBService.params)
        except IOError:
            self.log_error("Could not start proxydb service")
            raise

        # Setup memcached pools
        memcachepool.installPools(
            config.Memcached.Pools,
            config.Memcached.MaxClients,
        )

        cacherService = GroupMembershipCacherService(proxyDB, directory,
            config.GroupCaching.MemcachedPool,
            config.GroupCaching.UpdateSeconds,
            config.GroupCaching.ExpireSeconds
            )

        return cacherService



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


    def cachedGroups(self):
        """
        Return the set of groups (guids) this record is a member of, based on
        the data cached by cacheGroupMembership( )
        """
        return self.service.groupMembershipCache.getGroupsFor(self.guid)


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

