# -*- test-case-name: twistedcaldav.directory.test -*-
##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
    "GroupMembershipCacheUpdater",
]

from plistlib import readPlistFromString

from twext.enterprise.dal.record import fromTable
from twext.enterprise.dal.syntax import Delete
from twext.enterprise.queue import WorkItem
from twext.python.log import Logger, LoggingMixIn
from twext.web2.dav.auth import IPrincipalCredentials
from twext.web2.dav.util import joinURL

from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.error import UnauthorizedLogin
from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twisted.python.filepath import FilePath

from twistedcaldav.config import config
from twistedcaldav.directory.idirectory import IDirectoryService, IDirectoryRecord
from twistedcaldav.directory.util import uuidFromName, normalizeUUID
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.scheduling.ischedule.localservers import Servers

from txdav.caldav.icalendardirectoryservice import ICalendarStoreDirectoryService, \
    ICalendarStoreDirectoryRecord
from txdav.common.datastore.sql_tables import schema

from xml.parsers.expat import ExpatError

from zope.interface import implements

import cPickle as pickle
import datetime
import grp
import itertools
import os
import pwd
import sys
import types

log = Logger()


class DirectoryService(LoggingMixIn):
    implements(IDirectoryService, ICalendarStoreDirectoryService, ICredentialsChecker)

    ##
    # IDirectoryService
    ##

    realmName = None

    recordType_users = "users"
    recordType_people = "people"
    recordType_groups = "groups"
    recordType_locations = "locations"
    recordType_resources = "resources"

    searchContext_location = "location"
    searchContext_attendee = "attendee"

    aggregateService = None

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
            NegotiateCredentials = None

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
        uid = normalizeUUID(uid)
        for record in self.allRecords():
            if record.uid == uid:
                return record
        return None


    def recordWithGUID(self, guid):
        guid = normalizeUUID(guid)
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
        elif address.startswith("/principals/"):
            parts = address.split("/")
            if len(parts) == 3:
                if parts[1] == "__uids__":
                    guid = parts[2]
                    record = self.recordWithGUID(guid)
                else:
                    record = self.recordWithShortName(parts[1], parts[2])

        return record if record and record.enabledForCalendaring else None


    def recordWithCachedGroupsAlias(self, recordType, alias):
        """
        @param recordType: the type of the record to look up.
        @param alias: the cached-groups alias of the record to look up.
        @type alias: C{str}

        @return: a deferred L{IDirectoryRecord} with the given cached-groups
            alias, or C{None} if no such record is found.
        """
        # The default implementation uses guid
        return succeed(self.recordWithGUID(alias))


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


    def recordTypesForSearchContext(self, context):
        """
        Map calendarserver-principal-search REPORT context value to applicable record types

        @param context: The context value to map (either "location" or "attendee")
        @type context: C{str}
        @returns: The list of record types the context maps to
        @rtype: C{list} of C{str}
        """
        if context == self.searchContext_location:
            recordTypes = [self.recordType_locations]
        elif context == self.searchContext_attendee:
            recordTypes = [self.recordType_users, self.recordType_groups,
                self.recordType_resources]
        else:
            recordTypes = list(self.recordTypes())
        return recordTypes


    def recordsMatchingTokens(self, tokens, context=None):
        """
        @param tokens: The tokens to search on
        @type tokens: C{list} of C{str} (utf-8 bytes)
        @param context: An indication of what the end user is searching
            for; "attendee", "location", or None
        @type context: C{str}
        @return: a deferred sequence of L{IDirectoryRecord}s which
            match the given tokens and optional context.

        Each token is searched for within each record's full name and
        email address; if each token is found within a record that
        record is returned in the results.

        If context is None, all record types are considered.  If
        context is "location", only locations are considered.  If
        context is "attendee", only users, groups, and resources
        are considered.
        """

        # Default, bruteforce method; override with one optimized for each
        # service

        def fieldMatches(fieldValue, value):
            if fieldValue is None:
                return False
            elif type(fieldValue) in types.StringTypes:
                fieldValue = (fieldValue,)

            for testValue in fieldValue:
                testValue = testValue.lower()
                value = value.lower()

                try:
                    testValue.index(value)
                    return True
                except ValueError:
                    pass

            return False

        def recordMatches(record):
            for token in tokens:
                for fieldName in ["fullName", "emailAddresses"]:
                    try:
                        fieldValue = getattr(record, fieldName)
                        if fieldMatches(fieldValue, token):
                            break
                    except AttributeError:
                        # No value
                        pass
                else:
                    return False
            return True


        def yieldMatches(recordTypes):
            try:
                for recordType in [r for r in recordTypes if r in self.recordTypes()]:
                    for record in self.listRecords(recordType):
                        if recordMatches(record):
                            yield record

            except UnknownRecordTypeError:
                # Skip this service since it doesn't understand this record type
                pass

        recordTypes = self.recordTypesForSearchContext(context)
        return succeed(yieldMatches(recordTypes))


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


    def getGroups(self, guids):
        """
        This implementation returns all groups, not just the ones specified
        by guids
        """
        return succeed(self.listRecords(self.recordType_groups))


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


    def parseResourceInfo(self, plist, guid, recordType, shortname):
        """
        Parse ResourceInfo plist and extract information that the server needs.

        @param plist: the plist that is the attribute value.
        @type plist: str
        @param guid: the directory GUID of the record being parsed.
        @type guid: str
        @param shortname: the record shortname of the record being parsed.
        @type shortname: str
        @return: a C{tuple} of C{bool} for auto-accept, C{str} for proxy GUID, C{str} for read-only proxy GUID.
        """
        try:
            plist = readPlistFromString(plist)
            wpframework = plist.get("com.apple.WhitePagesFramework", {})
            autoaccept = wpframework.get("AutoAcceptsInvitation", False)
            proxy = wpframework.get("CalendaringDelegate", None)
            read_only_proxy = wpframework.get("ReadOnlyCalendaringDelegate", None)
            autoAcceptGroup = wpframework.get("AutoAcceptGroup", "")
        except (ExpatError, AttributeError), e:
            self.log_error(
                "Failed to parse ResourceInfo attribute of record (%s)%s (guid=%s): %s\n%s" %
                (recordType, shortname, guid, e, plist,)
            )
            raise ValueError("Invalid ResourceInfo")

        return (autoaccept, proxy, read_only_proxy, autoAcceptGroup)


    def getExternalProxyAssignments(self):
        """
        Retrieve proxy assignments for locations and resources from the
        directory and return a list of (principalUID, ([memberUIDs)) tuples,
        suitable for passing to proxyDB.setGroupMembers( )

        This generic implementation fetches all locations and resources.
        More specialized implementations can perform whatever operation is
        most efficient for their particular directory service.
        """
        assignments = []

        resources = itertools.chain(
            self.listRecords(self.recordType_locations),
            self.listRecords(self.recordType_resources)
        )
        for record in resources:
            guid = record.guid
            assignments.append(("%s#calendar-proxy-write" % (guid,),
                               record.externalProxies()))
            assignments.append(("%s#calendar-proxy-read" % (guid,),
                               record.externalReadOnlyProxies()))

        return assignments


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


    def setPrincipalCollection(self, principalCollection):
        """
        Set the principal service that the directory relies on for doing proxy tests.

        @param principalService: the principal service.
        @type principalService: L{DirectoryProvisioningResource}
        """
        self.principalCollection = principalCollection


    def isProxyFor(self, test, other):
        """
        Test whether one record is a calendar user proxy for the specified record.

        @param test: record to test
        @type test: L{DirectoryRecord}
        @param other: record to check against
        @type other: L{DirectoryRecord}

        @return: C{True} if test is a proxy of other.
        @rtype: C{bool}
        """
        return self.principalCollection.isProxyFor(test, other)



class GroupMembershipCache(Memcacher, LoggingMixIn):
    """
    Caches group membership information

    This cache is periodically updated by a side car so that worker processes
    never have to ask the directory service directly for group membership
    information.

    Keys in this cache are:

    "groups-for:<GUID>" : comma-separated list of groups that GUID is a member
    of.  Note that when using LDAP, the key for this is an LDAP DN.

    "group-cacher-populated" : contains a datestamp indicating the most recent
    population.
    """

    def __init__(self, namespace, pickle=True, no_invalidation=False,
        key_normalization=True, expireSeconds=0):

        super(GroupMembershipCache, self).__init__(namespace, pickle=pickle,
            no_invalidation=no_invalidation,
            key_normalization=key_normalization)

        self.expireSeconds = expireSeconds


    def setGroupsFor(self, guid, memberships):
        self.log_debug("set groups-for %s : %s" % (guid, memberships))
        return self.set("groups-for:%s" %
            (str(guid)), memberships,
            expireTime=self.expireSeconds)


    def getGroupsFor(self, guid):
        self.log_debug("get groups-for %s" % (guid,))
        def _value(value):
            if value:
                return value
            else:
                return set()
        d = self.get("groups-for:%s" % (str(guid),))
        d.addCallback(_value)
        return d


    def deleteGroupsFor(self, guid):
        self.log_debug("delete groups-for %s" % (guid,))
        return self.delete("groups-for:%s" % (str(guid),))


    def setPopulatedMarker(self):
        self.log_debug("set group-cacher-populated")
        return self.set("group-cacher-populated", str(datetime.datetime.now()))


    @inlineCallbacks
    def isPopulated(self):
        self.log_debug("is group-cacher-populated")
        value = (yield self.get("group-cacher-populated"))
        returnValue(value is not None)



class GroupMembershipCacheUpdater(LoggingMixIn):
    """
    Responsible for updating memcached with group memberships.  This will run
    in a sidecar.  There are two sources of proxy data to pull from: the local
    proxy database, and the location/resource info in the directory system.
    """

    def __init__(self, proxyDB, directory, updateSeconds, expireSeconds,
        cache=None, namespace=None, useExternalProxies=False,
        externalProxiesSource=None):
        self.proxyDB = proxyDB
        self.directory = directory
        self.updateSeconds = updateSeconds
        self.useExternalProxies = useExternalProxies
        if useExternalProxies and externalProxiesSource is None:
            externalProxiesSource = self.directory.getExternalProxyAssignments
        self.externalProxiesSource = externalProxiesSource

        if cache is None:
            assert namespace is not None, "namespace must be specified if GroupMembershipCache is not provided"
            cache = GroupMembershipCache(namespace, expireSeconds=expireSeconds)
        self.cache = cache


    @inlineCallbacks
    def getGroups(self, guids=None):
        """
        Retrieve all groups and their member info (but don't actually fault in
        the records of the members), and return two dictionaries.  The first
        contains group records; the keys for this dictionary are the identifiers
        used by the directory service to specify members.  In OpenDirectory
        these would be guids, but in LDAP these could be DNs, or some other
        attribute.  This attribute can be retrieved from a record using
        record.cachedGroupsAlias().
        The second dictionary returned maps that member attribute back to the
        corresponding guid.  These dictionaries are used to reverse-index the
        groups that users are in by expandedMembers().

        @param guids: if provided, retrieve only the groups corresponding to
            these guids (including their sub groups)
        @type guids: list of guid strings
        """
        groups = {}
        aliases = {}

        if guids is None: # get all group guids
            records = self.directory.listRecords(self.directory.recordType_groups)
        else: # get only the ones we know have been delegated to
            records = (yield self.directory.getGroups(guids))

        for record in records:
            alias = record.cachedGroupsAlias()
            groups[alias] = record.memberGUIDs()
            aliases[record.guid] = alias

        returnValue((groups, aliases))


    def expandedMembers(self, groups, guid, members=None, seen=None):
        """
        Return the complete, flattened set of members of a group, including
        all sub-groups, based on the group hierarchy described in the
        groups dictionary.
        """
        if members is None:
            members = set()
        if seen is None:
            seen = set()

        if guid not in seen:
            seen.add(guid)
            for member in groups[guid]:
                members.add(member)
                if member in groups: # it's a group then
                    self.expandedMembers(groups, member, members=members,
                                         seen=seen)
        return members


    @inlineCallbacks
    def updateCache(self, fast=False):
        """
        Iterate the proxy database to retrieve all the principals who have been
        delegated to.  Fault these principals in.  For any of these principals
        that are groups, expand the members of that group and store those in
        the cache

        If fast=True, we're in quick-start mode, used only by the master process
        to start servicing requests as soon as possible.  In this mode we look
        for DataRoot/memberships_cache which is a pickle of a dictionary whose
        keys are guids (except when using LDAP where the keys will be DNs), and
        the values are lists of group guids.  If the cache file does not exist
        we switch to fast=False.

        The return value is mainly used for unit tests; it's a tuple containing
        the (possibly modified) value for fast, and the number of members loaded
        into the cache (which can be zero if fast=True and isPopulated(), or
        fast=False and the cache is locked by someone else).

        The pickled snapshot file is a dict whose keys represent a record and
        the values are the guids of the groups that record is a member of.  The
        keys are normally guids except in the case of a directory system like LDAP
        where there can be a different attribute used for referring to members,
        such as a DN.
        """

        # TODO: add memcached eviction protection

        # See if anyone has completely populated the group membership cache
        isPopulated = (yield self.cache.isPopulated())

        if fast:
            # We're in quick-start mode.  Check first to see if someone has
            # populated the membership cache, and if so, return immediately
            if isPopulated:
                self.log_info("Group membership cache is already populated")
                returnValue((fast, 0))

        self.log_info("Updating group membership cache")

        dataRoot = FilePath(config.DataRoot)
        membershipsCacheFile = dataRoot.child("memberships_cache")
        extProxyCacheFile = dataRoot.child("external_proxy_cache")

        if not membershipsCacheFile.exists():
            self.log_info("Group membership snapshot file does not yet exist")
            fast = False
            previousMembers = {}
            callGroupsChanged = False
        else:
            self.log_info("Group membership snapshot file exists: %s" %
                (membershipsCacheFile.path,))
            previousMembers = pickle.loads(membershipsCacheFile.getContent())
            callGroupsChanged = True

        if not fast and self.useExternalProxies:

            # Load in cached copy of external proxies so we can diff against them
            previousAssignments = []
            if extProxyCacheFile.exists():
                self.log_info("External proxies snapshot file exists: %s" %
                    (extProxyCacheFile.path,))
                previousAssignments = pickle.loads(extProxyCacheFile.getContent())

            self.log_info("Retrieving proxy assignments from directory")
            assignments = self.externalProxiesSource()
            self.log_info("%d proxy assignments retrieved from directory" %
                (len(assignments),))

            changed, removed = diffAssignments(previousAssignments, assignments)
            # changed is the list of proxy assignments (either new or updates).
            # removed is the list of principals who used to have an external
            #   delegate but don't anymore.

            # populate proxy DB from external resource info
            if changed:
                self.log_info("Updating proxy assignments")
                assignmentCount = 0
                totalNumAssignments = len(changed)
                currentAssignmentNum = 0
                for principalUID, members in changed:
                    currentAssignmentNum += 1
                    if currentAssignmentNum % 1000 == 0:
                        self.log_info("...proxy assignment %d of %d" % (currentAssignmentNum,
                            totalNumAssignments))
                    try:
                        current = (yield self.proxyDB.getMembers(principalUID))
                        if members != current:
                            assignmentCount += 1
                            yield self.proxyDB.setGroupMembers(principalUID, members)
                    except Exception, e:
                        self.log_error("Unable to update proxy assignment: principal=%s, members=%s, error=%s" % (principalUID, members, e))
                self.log_info("Updated %d assignment%s in proxy database" %
                    (assignmentCount, "" if assignmentCount == 1 else "s"))

            if removed:
                self.log_info("Deleting proxy assignments")
                assignmentCount = 0
                totalNumAssignments = len(removed)
                currentAssignmentNum = 0
                for principalUID in removed:
                    currentAssignmentNum += 1
                    if currentAssignmentNum % 1000 == 0:
                        self.log_info("...proxy assignment %d of %d" % (currentAssignmentNum,
                            totalNumAssignments))
                    try:
                        assignmentCount += 1
                        yield self.proxyDB.setGroupMembers(principalUID, [])
                    except Exception, e:
                        self.log_error("Unable to remove proxy assignment: principal=%s, members=%s, error=%s" % (principalUID, members, e))
                self.log_info("Removed %d assignment%s from proxy database" %
                    (assignmentCount, "" if assignmentCount == 1 else "s"))

            # Store external proxy snapshot
            self.log_info("Taking snapshot of external proxies to %s" %
                (extProxyCacheFile.path,))
            extProxyCacheFile.setContent(pickle.dumps(assignments))

        if fast:
            # If there is an on-disk snapshot of the membership information,
            # load that and put into memcached, bypassing the faulting in of
            # any records, so that the server can start up quickly.

            self.log_info("Loading group memberships from snapshot")
            members = pickle.loads(membershipsCacheFile.getContent())

        else:
            # Fetch the group hierarchy from the directory, fetch the list
            # of delegated-to guids, intersect those and build a dictionary
            # containing which delegated-to groups a user is a member of

            self.log_info("Retrieving list of all proxies")
            # This is always a set of guids:
            delegatedGUIDs = set((yield self.proxyDB.getAllMembers()))
            self.log_info("There are %d proxies" % (len(delegatedGUIDs),))
            self.log_info("Retrieving group hierarchy from directory")

            # "groups" maps a group to its members; the keys and values consist
            # of whatever directory attribute is used to refer to members.  The
            # attribute value comes from record.cachedGroupsAlias().
            # "aliases" maps the record.cachedGroupsAlias() value for a group
            # back to the group's guid.
            groups, aliases = (yield self.getGroups(guids=delegatedGUIDs))
            groupGUIDs = set(aliases.keys())
            self.log_info("%d groups retrieved from the directory" %
                (len(groupGUIDs),))

            delegatedGUIDs = delegatedGUIDs.intersection(groupGUIDs)
            self.log_info("%d groups are proxies" % (len(delegatedGUIDs),))

            # Reverse index the group membership from cache
            members = {}
            for groupGUID in delegatedGUIDs:
                groupMembers = self.expandedMembers(groups, aliases[groupGUID])
                # groupMembers is in cachedGroupsAlias() format
                for member in groupMembers:
                    memberships = members.setdefault(member, set())
                    memberships.add(groupGUID)

            self.log_info("There are %d users delegated-to via groups" %
                (len(members),))

            # Store snapshot
            self.log_info("Taking snapshot of group memberships to %s" %
                (membershipsCacheFile.path,))
            membershipsCacheFile.setContent(pickle.dumps(members))

            # Update ownership
            uid = gid = -1
            if config.UserName:
                uid = pwd.getpwnam(config.UserName).pw_uid
            if config.GroupName:
                gid = grp.getgrnam(config.GroupName).gr_gid
            os.chown(membershipsCacheFile.path, uid, gid)
            if extProxyCacheFile.exists():
                os.chown(extProxyCacheFile.path, uid, gid)

        self.log_info("Storing %d group memberships in memcached" %
                       (len(members),))
        changedMembers = set()
        totalNumMembers = len(members)
        currentMemberNum = 0
        for member, groups in members.iteritems():
            currentMemberNum += 1
            if currentMemberNum % 1000 == 0:
                self.log_info("...membership %d of %d" % (currentMemberNum,
                    totalNumMembers))
            # self.log_debug("%s is in %s" % (member, groups))
            yield self.cache.setGroupsFor(member, groups)
            if groups != previousMembers.get(member, None):
                # This principal has had a change in group membership
                # so invalidate the PROPFIND response cache
                changedMembers.add(member)
            try:
                # Remove from previousMembers; anything still left in
                # previousMembers when this loop is done will be
                # deleted from cache (since only members that were
                # previously in delegated-to groups but are no longer
                # would still be in previousMembers)
                del previousMembers[member]
            except KeyError:
                pass

        # Remove entries for principals that no longer are in delegated-to
        # groups
        for member, groups in previousMembers.iteritems():
            yield self.cache.deleteGroupsFor(member)
            changedMembers.add(member)

        # For principals whose group membership has changed, call groupsChanged()
        if callGroupsChanged and not fast and hasattr(self.directory, "principalCollection"):
            for member in changedMembers:
                record = yield self.directory.recordWithCachedGroupsAlias(
                    self.directory.recordType_users, member)
                if record is not None:
                    principal = self.directory.principalCollection.principalForRecord(record)
                    if principal is not None:
                        self.log_debug("Group membership changed for %s (%s)" %
                            (record.shortNames[0], record.guid,))
                        if hasattr(principal, "groupsChanged"):
                            yield principal.groupsChanged()

        yield self.cache.setPopulatedMarker()

        self.log_info("Group memberships cache updated")

        returnValue((fast, len(members), len(changedMembers)))



class GroupCacherPollingWork(WorkItem, fromTable(schema.GROUP_CACHER_POLLING_WORK)):

    group = "group_cacher_polling"

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items
        yield Delete(From=self.table, Where=None).on(self.transaction)

        groupCacher = getattr(self.transaction, "_groupCacher", None)
        if groupCacher is not None:
            try:
                yield groupCacher.updateCache()
            except Exception, e:
                log.error("Failed to update group membership cache (%s)" % (e,))
            finally:
                notBefore = (datetime.datetime.utcnow() +
                    datetime.timedelta(seconds=groupCacher.updateSeconds))
                log.debug("Scheduling next group cacher update: %s" % (notBefore,))
                yield self.transaction.enqueue(GroupCacherPollingWork,
                    notBefore=notBefore)
        else:
            notBefore = (datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10))
            log.debug("Rescheduling group cacher update: %s" % (notBefore,))
            yield self.transaction.enqueue(GroupCacherPollingWork,
                notBefore=notBefore)



@inlineCallbacks
def scheduleNextGroupCachingUpdate(store, seconds):
    txn = store.newTransaction()
    notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    log.debug("Scheduling next group cacher update: %s" % (notBefore,))
    yield txn.enqueue(GroupCacherPollingWork, notBefore=notBefore)
    yield txn.commit()



def diffAssignments(old, new):
    """
    Compare two proxy assignment lists and return their differences in the form of
    two lists -- one for added/updated assignments, and one for removed assignments.
    @param old: list of (group, set(members)) tuples
    @type old: C{list}
    @param new: list of (group, set(members)) tuples
    @type new: C{list}
    @return: Tuple of two lists; the first list contains tuples of (proxy-principal,
        set(members)), and represents all the new or updated assignments.  The
        second list contains all the proxy-principals which used to have a delegate
        but don't anymore.
    """
    old = dict(old)
    new = dict(new)
    changed = []
    removed = []
    for key in old.iterkeys():
        if key not in new:
            removed.append(key)
        else:
            if old[key] != new[key]:
                changed.append((key, new[key]))
    for key in new.iterkeys():
        if key not in old:
            changed.append((key, new[key]))
    return changed, removed



class DirectoryRecord(LoggingMixIn):
    implements(IDirectoryRecord, ICalendarStoreDirectoryRecord)

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
        self, service, recordType, guid=None,
        shortNames=(), authIDs=set(), fullName=None,
        firstName=None, lastName=None, emailAddresses=set(),
        calendarUserAddresses=set(),
        autoSchedule=False, autoScheduleMode=None,
        autoAcceptGroup="",
        enabledForCalendaring=None,
        enabledForAddressBooks=None,
        uid=None,
        enabledForLogin=True,
        extProxies=(), extReadOnlyProxies=(),
        **kwargs
    ):
        assert service.realmName is not None
        assert recordType
        assert shortNames and isinstance(shortNames, tuple)

        guid = normalizeUUID(guid)

        if uid is None:
            uid = guid

        if fullName is None:
            fullName = ""

        self.service = service
        self.recordType = recordType
        self.guid = guid
        self.uid = uid
        self.enabled = False
        self.serverID = ""
        self.partitionID = ""
        self.shortNames = shortNames
        self.authIDs = authIDs
        self.fullName = fullName
        self.firstName = firstName
        self.lastName = lastName
        self.emailAddresses = emailAddresses
        self.enabledForCalendaring = enabledForCalendaring
        self.autoSchedule = autoSchedule
        self.autoScheduleMode = autoScheduleMode
        self.autoAcceptGroup = autoAcceptGroup
        self.enabledForAddressBooks = enabledForAddressBooks
        self.enabledForLogin = enabledForLogin
        self.extProxies = extProxies
        self.extReadOnlyProxies = extReadOnlyProxies
        self.extras = kwargs


    def get_calendarUserAddresses(self):
        """
        Dynamically construct a calendarUserAddresses attribute which describes
        this L{DirectoryRecord}.

        @see: L{IDirectoryRecord.calendarUserAddresses}.
        """
        if not self.enabledForCalendaring:
            return frozenset()
        cuas = set(
            ["mailto:%s" % (emailAddress,)
             for emailAddress in self.emailAddresses]
        )
        if self.guid:
            cuas.add("urn:uuid:%s" % (self.guid,))
            cuas.add(joinURL("/principals", "__uids__", self.guid) + "/")
        for shortName in self.shortNames:
            cuas.add(joinURL("/principals", self.recordType, shortName,) + "/")

        return frozenset(cuas)

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


    def cacheToken(self):
        """
        Generate a token that can be uniquely used to identify the state of this record for use
        in a cache.
        """
        return hash((
            self.__class__.__name__,
            self.service.realmName,
            self.recordType,
            self.shortNames,
            self.guid,
            self.enabled,
            self.enabledForCalendaring,
        ))


    def addAugmentInformation(self, augment):

        if augment:
            self.enabled = augment.enabled
            self.serverID = augment.serverID
            self.partitionID = augment.partitionID
            self.enabledForCalendaring = augment.enabledForCalendaring
            self.enabledForAddressBooks = augment.enabledForAddressBooks
            self.autoSchedule = augment.autoSchedule
            self.autoScheduleMode = augment.autoScheduleMode
            self.autoAcceptGroup = augment.autoAcceptGroup
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


    def displayName(self):
        return self.fullName if self.fullName else self.shortNames[0]


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
        return self.service.groupMembershipCache.getGroupsFor(self.cachedGroupsAlias())


    def cachedGroupsAlias(self):
        """
        The GroupMembershipCache uses keys based on this value.  Normally it's
        a record's guid but in a directory system like LDAP which can use a
        different attribute to refer to group members, we need to be able to
        look up an entry in the GroupMembershipCache by that attribute.
        Subclasses which don't use record.guid to look up group membership
        should override this method.
        """
        return self.guid


    def externalProxies(self):
        """
        Return the set of proxies defined in the directory service, as opposed
        to assignments in the proxy DB itself.
        """
        return set(self.extProxies)


    def externalReadOnlyProxies(self):
        """
        Return the set of read-only proxies defined in the directory service,
        as opposed to assignments in the proxy DB itself.
        """
        return set(self.extReadOnlyProxies)


    def memberGUIDs(self):
        """
        Return the set of GUIDs that are members of this group
        """
        return set()


    def verifyCredentials(self, credentials):
        return False


    def calendarsEnabled(self):
        return config.EnableCalDAV and self.enabledForCalendaring


    def canonicalCalendarUserAddress(self):
        """
            Return a CUA for this principal, preferring in this order:
            urn:uuid: form
            mailto: form
            first in calendarUserAddresses list
        """

        cua = ""
        for candidate in self.calendarUserAddresses:
            # Pick the first one, but urn:uuid: and mailto: can override
            if not cua:
                cua = candidate
            # But always immediately choose the urn:uuid: form
            if candidate.startswith("urn:uuid:"):
                cua = candidate
                break
            # Prefer mailto: if no urn:uuid:
            elif candidate.startswith("mailto:"):
                cua = candidate
        return cua


    def enabledAsOrganizer(self):
        if self.recordType == DirectoryService.recordType_users:
            return True
        elif self.recordType == DirectoryService.recordType_groups:
            return config.Scheduling.Options.AllowGroupAsOrganizer
        elif self.recordType == DirectoryService.recordType_locations:
            return config.Scheduling.Options.AllowLocationAsOrganizer
        elif self.recordType == DirectoryService.recordType_resources:
            return config.Scheduling.Options.AllowResourceAsOrganizer
        else:
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


    def canAutoSchedule(self, organizer):
        if config.Scheduling.Options.AutoSchedule.Enabled:
            if (config.Scheduling.Options.AutoSchedule.Always or
                self.autoSchedule or
                self.autoAcceptFromOrganizer(organizer)):
                if (self.getCUType() != "INDIVIDUAL" or
                    config.Scheduling.Options.AutoSchedule.AllowUsers):
                    return True
        return False


    def getAutoScheduleMode(self, organizer):
        autoScheduleMode = self.autoScheduleMode
        if self.autoAcceptFromOrganizer(organizer):
            autoScheduleMode = "automatic"
        return autoScheduleMode


    def autoAcceptFromOrganizer(self, organizer):
        if organizer is not None and self.autoAcceptGroup is not None:
            service = self.service.aggregateService or self.service
            organizerRecord = service.recordWithCalendarUserAddress(organizer)
            if organizerRecord is not None:
                if organizerRecord.guid in self.autoAcceptMembers():
                    return True
        return False


    def serverURI(self):
        """
        URL of the server hosting this record. Return None if hosted on this server.
        """
        if config.Servers.Enabled and self.serverID:
            return Servers.getServerURIById(self.serverID)
        else:
            return None


    def server(self):
        """
        Server hosting this record. Return None if hosted on this server.
        """
        if config.Servers.Enabled and self.serverID:
            return Servers.getServerById(self.serverID)
        else:
            return None


    def partitionURI(self):
        """
        URL of the server hosting this record. Return None if hosted on this server.
        """
        if config.Servers.Enabled and self.serverID:
            s = Servers.getServerById(self.serverID)
            if s:
                return s.getPartitionURIForId(self.partitionID)
        return None


    def locallyHosted(self):
        """
        Hosted on this server/partition instance.
        """

        if config.Servers.Enabled and self.serverID:
            s = Servers.getServerById(self.serverID)
            if s:
                return s.thisServer and (not s.isPartitioned() or not self.partitionID or self.partitionID == config.ServerPartitionID)
        return True


    def effectivePartitionID(self):
        """
        Record partition ID taking into account whether the server is partitioned.
        """
        if config.Servers.Enabled and self.serverID:
            s = Servers.getServerById(self.serverID)
            if s and s.isPartitioned():
                return self.partitionID
        return ""


    def thisServer(self):
        if config.Servers.Enabled and self.serverID:
            s = Servers.getServerById(self.serverID)
            if s:
                return s.thisServer
        return True


    def autoAcceptMembers(self):
        """
        Return the list of GUIDs for which this record will automatically accept
        invites from (assuming no conflicts).  This list is based on the group
        assigned to record.autoAcceptGroup.  Cache the expanded group membership
        within the record.

        @return: the list of members of the autoAcceptGroup, or an empty list if
            not assigned
        @rtype: C{list} of GUID C{str}
        """
        if not hasattr(self, "_cachedAutoAcceptMembers"):
            self._cachedAutoAcceptMembers = []
            if self.autoAcceptGroup:
                service = self.service.aggregateService or self.service
                groupRecord = service.recordWithGUID(self.autoAcceptGroup)
                if groupRecord is not None:
                    self._cachedAutoAcceptMembers = [m.guid for m in groupRecord.expandedMembers()]

        return self._cachedAutoAcceptMembers


    def isProxyFor(self, other):
        """
        Test whether the record is a calendar user proxy for the specified record.

        @param other: record to test
        @type other: L{DirectoryRecord}

        @return: C{True} if it is a proxy.
        @rtype: C{bool}
        """
        return self.service.isProxyFor(self, other)



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
