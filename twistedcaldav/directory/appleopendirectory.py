# -*- test-case-name: twistedcaldav.directory.test.test_opendirectory -*-
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
Apple OpenDirectory directory service implementation.
"""

__all__ = [
    "OpenDirectoryService",
    "OpenDirectoryInitError",
]

import sys
import time
from uuid import UUID

from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twisted.cred.credentials import UsernamePassword
from twext.web2.auth.digest import DigestedCredentials
from twext.python.log import Logger

from twistedcaldav.directory.cachingdirectory import CachingDirectoryService, \
    CachingDirectoryRecord
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError
from twistedcaldav.directory.util import splitIntoBatches
from twistedcaldav.directory.principal import cuAddressConverter

from calendarserver.platform.darwin.od import opendirectory, dsattributes, dsquery



class OpenDirectoryService(CachingDirectoryService):
    """
    OpenDirectory implementation of L{IDirectoryService}.
    """
    log = Logger()

    baseGUID = "891F8321-ED02-424C-BA72-89C32F215C1E"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.node)


    def __init__(self, params, odModule=None):
        """
        @param params: a dictionary containing the following keys:

            - node: an OpenDirectory node name to bind to.

            - restrictEnabledRecords: C{True} if a group in the directory is to
              be used to determine which calendar users are enabled.

            - restrictToGroup: C{str} guid or name of group used to restrict
              enabled users.

            - cacheTimeout: C{int} number of minutes before cache is
              invalidated.

            - negativeCache: C{False} cache the fact that a record wasn't found
        """
        defaults = {
            'node' : '/Search',
            'restrictEnabledRecords' : False,
            'restrictToGroup' : '',
            'cacheTimeout' : 1, # Minutes
            'batchSize' : 100, # for splitting up large queries
            'negativeCaching' : False,
            'recordTypes' : (
                self.recordType_users,
                self.recordType_groups,
            ),
            'augmentService' : None,
            'groupMembershipCache' : None,
        }
        ignored = ('requireComputerRecord',)
        params = self.getParams(params, defaults, ignored)

        self._recordTypes = params['recordTypes']

        super(OpenDirectoryService, self).__init__(params['cacheTimeout'],
                                                   params['negativeCaching'])

        if odModule is None:
            odModule = opendirectory
        self.odModule = odModule

        try:
            directory = self.odModule.odInit(params['node'])
        except self.odModule.ODError, e:
            self.log.error("OpenDirectory (node=%s) Initialization error: %s" % (params['node'], e))
            raise

        self.augmentService = params['augmentService']
        self.groupMembershipCache = params['groupMembershipCache']
        self.realmName = params['node']
        self.directory = directory
        self.node = params['node']
        self.restrictEnabledRecords = params['restrictEnabledRecords']
        self.restrictToGroup = params['restrictToGroup']
        self.batchSize = params['batchSize']
        try:
            UUID(self.restrictToGroup)
        except:
            self.restrictToGUID = False
        else:
            self.restrictToGUID = True
        self.restrictedTimestamp = 0


    @property
    def restrictedGUIDs(self):
        """
        Look up (and cache) the set of guids that are members of the
        restrictToGroup.  If restrictToGroup is not set, return None to
        indicate there are no group restrictions.
        """
        if self.restrictEnabledRecords:
            if time.time() - self.restrictedTimestamp > self.cacheTimeout:
                attributeToMatch = dsattributes.kDS1AttrGeneratedUID if self.restrictToGUID else dsattributes.kDSNAttrRecordName
                valueToMatch = self.restrictToGroup
                self.log.debug("Doing restricted group membership check")
                self.log.debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                    self.directory,
                    attributeToMatch,
                    valueToMatch,
                    dsattributes.eDSExact,
                    False,
                    dsattributes.kDSStdRecordTypeGroups,
                    [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups, ],
                ))
                results = self.odModule.queryRecordsWithAttribute_list(
                    self.directory,
                    attributeToMatch,
                    valueToMatch,
                    dsattributes.eDSExact,
                    False,
                    dsattributes.kDSStdRecordTypeGroups,
                    [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups, ],
                )

                if len(results) == 1:
                    members = results[0][1].get(dsattributes.kDSNAttrGroupMembers, [])
                    nestedGroups = results[0][1].get(dsattributes.kDSNAttrNestedGroups, [])
                else:
                    members = []
                    nestedGroups = []
                self._cachedRestrictedGUIDs = set(self._expandGroupMembership(members, nestedGroups, returnGroups=True))
                self.log.debug("Got %d restricted group members" % (len(self._cachedRestrictedGUIDs),))
                self.restrictedTimestamp = time.time()
            return self._cachedRestrictedGUIDs
        else:
            # No restrictions
            return None


    def __cmp__(self, other):
        if not isinstance(other, DirectoryRecord):
            return super(DirectoryRecord, self).__eq__(other)

        for attr in ("directory", "node"):
            diff = cmp(getattr(self, attr), getattr(other, attr))
            if diff != 0:
                return diff
        return 0


    def __hash__(self):
        h = hash(self.__class__.__name__)
        for attr in ("node",):
            h = (h + hash(getattr(self, attr))) & sys.maxint
        return h


    def _expandGroupMembership(self, members, nestedGroups, processedGUIDs=None, returnGroups=False):

        if processedGUIDs is None:
            processedGUIDs = set()

        if isinstance(members, str):
            members = [members]

        if isinstance(nestedGroups, str):
            nestedGroups = [nestedGroups]

        for memberGUID in members:
            if memberGUID not in processedGUIDs:
                processedGUIDs.add(memberGUID)
                yield memberGUID

        for groupGUID in nestedGroups:
            if groupGUID in processedGUIDs:
                continue

            self.log.debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                self.directory,
                dsattributes.kDS1AttrGeneratedUID,
                groupGUID,
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups]
            ))
            result = self.odModule.queryRecordsWithAttribute_list(
                self.directory,
                dsattributes.kDS1AttrGeneratedUID,
                groupGUID,
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups]
            )

            if not result:
                self.log.error("Couldn't find group %s when trying to expand nested groups."
                             % (groupGUID,))
                continue

            group = result[0][1]

            processedGUIDs.add(groupGUID)
            if returnGroups:
                yield groupGUID

            for GUID in self._expandGroupMembership(
                group.get(dsattributes.kDSNAttrGroupMembers, []),
                group.get(dsattributes.kDSNAttrNestedGroups, []),
                processedGUIDs,
                returnGroups,
            ):
                yield GUID


    def recordTypes(self):
        return self._recordTypes


    def listRecords(self, recordType):
        """
        Retrieve all the records of recordType from the directory, but for
        expediency don't index them or cache them locally, nor in memcached.
        """

        records = []

        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
            dsattributes.kDSNAttrRecordName,
            dsattributes.kDS1AttrDistinguishedName,
        ]

        if recordType == DirectoryService.recordType_users:
            ODRecordType = self._toODRecordTypes[recordType]

        elif recordType in (
            DirectoryService.recordType_resources,
            DirectoryService.recordType_locations,
        ):
            attrs.append(dsattributes.kDSNAttrResourceInfo)
            ODRecordType = self._toODRecordTypes[recordType]

        elif recordType == DirectoryService.recordType_groups:
            attrs.append(dsattributes.kDSNAttrGroupMembers)
            attrs.append(dsattributes.kDSNAttrNestedGroups)
            ODRecordType = dsattributes.kDSStdRecordTypeGroups

        self.log.debug("Querying OD for all %s records" % (recordType,))
        results = self.odModule.listAllRecordsWithAttributes_list(
            self.directory, ODRecordType, attrs)
        self.log.debug("Retrieved %d %s records" % (len(results), recordType,))

        for key, value in results:
            recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
            if not recordGUID:
                self.log.warn("Ignoring record missing GUID: %s %s" %
                    (key, value,))
                continue

            # Skip if group restriction is in place and guid is not
            # a member (but don't skip any groups)
            if (recordType != self.recordType_groups and
                self.restrictedGUIDs is not None):
                if str(recordGUID) not in self.restrictedGUIDs:
                    continue

            recordShortNames = self._uniqueTupleFromAttribute(
                value.get(dsattributes.kDSNAttrRecordName))
            recordFullName = value.get(
                dsattributes.kDS1AttrDistinguishedName)

            proxyGUIDs = ()
            readOnlyProxyGUIDs = ()

            if recordType in (
                DirectoryService.recordType_resources,
                DirectoryService.recordType_locations,
            ):
                resourceInfo = value.get(dsattributes.kDSNAttrResourceInfo)
                if resourceInfo is not None:
                    if type(resourceInfo) is not str:
                        resourceInfo = resourceInfo[0]
                    try:
                        (
                            _ignore_autoSchedule,
                            proxy,
                            readOnlyProxy
                        ) = self.parseResourceInfo(
                            resourceInfo,
                            recordGUID,
                            recordType,
                            recordShortNames[0]
                        )
                    except ValueError:
                        continue
                    if proxy:
                        proxyGUIDs = (proxy,)
                    if readOnlyProxy:
                        readOnlyProxyGUIDs = (readOnlyProxy,)

            # Special case for groups, which have members.
            if recordType == self.recordType_groups:
                memberGUIDs = value.get(dsattributes.kDSNAttrGroupMembers)
                if memberGUIDs is None:
                    memberGUIDs = ()
                elif type(memberGUIDs) is str:
                    memberGUIDs = (memberGUIDs,)
                nestedGUIDs = value.get(dsattributes.kDSNAttrNestedGroups)
                if nestedGUIDs:
                    if type(nestedGUIDs) is str:
                        nestedGUIDs = (nestedGUIDs,)
                    memberGUIDs += tuple(nestedGUIDs)
                else:
                    nestedGUIDs = ()
            else:
                memberGUIDs = ()
                nestedGUIDs = ()

            record = OpenDirectoryRecord(
                service=self,
                recordType=recordType,
                guid=recordGUID,
                nodeName="",
                shortNames=recordShortNames,
                authIDs=(),
                fullName=recordFullName,
                firstName="",
                lastName="",
                emailAddresses="",
                memberGUIDs=memberGUIDs,
                nestedGUIDs=nestedGUIDs,
                extProxies=proxyGUIDs,
                extReadOnlyProxies=readOnlyProxyGUIDs,
            )

            # (Copied from below)
            # Look up augment information
            # TODO: this needs to be deferred but for now we hard code
            # the deferred result because we know it is completing
            # immediately.
            if self.augmentService is not None:
                d = self.augmentService.getAugmentRecord(record.guid,
                    recordType)
                d.addCallback(lambda x: record.addAugmentInformation(x))
            records.append(record)

        self.log.debug("ListRecords returning %d %s records" % (len(records),
            recordType))

        return records


    def groupsForGUID(self, guid):

        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
        ]

        recordType = dsattributes.kDSStdRecordTypeGroups

        guids = set()

        self.log.debug("Looking up which groups %s is a member of" % (guid,))
        try:
            self.log.debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                self.directory,
                dsattributes.kDSNAttrGroupMembers,
                guid,
                dsattributes.eDSExact,
                False,
                recordType,
                attrs,
            ))
            results = self.odModule.queryRecordsWithAttribute_list(
                self.directory,
                dsattributes.kDSNAttrGroupMembers,
                guid,
                dsattributes.eDSExact,
                False,
                recordType,
                attrs,
            )
        except self.odModule.ODError, ex:
            self.log.error("OpenDirectory (node=%s) error: %s" % (self.realmName, str(ex)))
            raise

        for (_ignore_recordShortName, value) in results:

            # Now get useful record info.
            recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
            if recordGUID:
                guids.add(recordGUID)

        try:
            self.log.debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                self.directory,
                dsattributes.kDSNAttrNestedGroups,
                guid,
                dsattributes.eDSExact,
                False,
                recordType,
                attrs,
            ))
            results = self.odModule.queryRecordsWithAttribute_list(
                self.directory,
                dsattributes.kDSNAttrNestedGroups,
                guid,
                dsattributes.eDSExact,
                False,
                recordType,
                attrs,
            )
        except self.odModule.ODError, ex:
            self.log.error("OpenDirectory (node=%s) error: %s" % (self.realmName, str(ex)))
            raise

        for (_ignore_recordShortName, value) in results:

            # Now get useful record info.
            recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
            if recordGUID:
                guids.add(recordGUID)

        self.log.debug("%s is a member of %d groups" % (guid, len(guids)))

        return guids

    _ODFields = {
        'fullName' : {
            'odField' : dsattributes.kDS1AttrDistinguishedName,
            'appliesTo' : set([
                dsattributes.kDSStdRecordTypeUsers,
                dsattributes.kDSStdRecordTypeGroups,
                dsattributes.kDSStdRecordTypeResources,
                dsattributes.kDSStdRecordTypePlaces,
            ]),
        },
        'firstName' : {
            'odField' : dsattributes.kDS1AttrFirstName,
            'appliesTo' : set([
                dsattributes.kDSStdRecordTypeUsers,
            ]),
        },
        'lastName' : {
            'odField' : dsattributes.kDS1AttrLastName,
            'appliesTo' : set([
                dsattributes.kDSStdRecordTypeUsers,
            ]),
        },
        'emailAddresses' : {
            'odField' : dsattributes.kDSNAttrEMailAddress,
            'appliesTo' : set([
                dsattributes.kDSStdRecordTypeUsers,
                dsattributes.kDSStdRecordTypeGroups,
            ]),
        },
        'recordName' : {
            'odField' : dsattributes.kDSNAttrRecordName,
            'appliesTo' : set([
                dsattributes.kDSStdRecordTypeUsers,
                dsattributes.kDSStdRecordTypeGroups,
                dsattributes.kDSStdRecordTypeResources,
                dsattributes.kDSStdRecordTypePlaces,
            ]),
        },
        'guid' : {
            'odField' : dsattributes.kDS1AttrGeneratedUID,
            'appliesTo' : set([
                dsattributes.kDSStdRecordTypeUsers,
                dsattributes.kDSStdRecordTypeGroups,
                dsattributes.kDSStdRecordTypeResources,
                dsattributes.kDSStdRecordTypePlaces,
            ]),
        },
    }

    _toODRecordTypes = {
        DirectoryService.recordType_users :
            dsattributes.kDSStdRecordTypeUsers,
        DirectoryService.recordType_groups :
            dsattributes.kDSStdRecordTypeGroups,
        DirectoryService.recordType_resources :
            dsattributes.kDSStdRecordTypeResources,
        DirectoryService.recordType_locations :
            dsattributes.kDSStdRecordTypePlaces,
    }

    _fromODRecordTypes = dict([(b, a) for a, b in _toODRecordTypes.iteritems()])

    def _uniqueTupleFromAttribute(self, attribute):
        if attribute:
            if isinstance(attribute, str):
                return (attribute,)
            else:
                s = set()
                return tuple([(s.add(x), x)[1] for x in attribute if x not in s])
        else:
            return ()


    def _setFromAttribute(self, attribute, lower=False):
        if attribute:
            if isinstance(attribute, str):
                return set((attribute.lower() if lower else attribute,))
            else:
                return set([item.lower() if lower else item for item in attribute])
        else:
            return ()


    def recordsMatchingTokens(self, tokens, context=None, lookupMethod=None):
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

        if lookupMethod is None:
            lookupMethod = self.odModule.queryRecordsWithAttributes_list

        def collectResults(results):
            self.log.debug("Got back %d records from OD" % (len(results),))
            for key, value in results:
                self.log.debug("OD result: %s %s" % (key, value))
                try:
                    recordNodeName = value.get(
                        dsattributes.kDSNAttrMetaNodeLocation)
                    recordShortNames = self._uniqueTupleFromAttribute(
                        value.get(dsattributes.kDSNAttrRecordName))

                    recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)

                    recordType = value.get(dsattributes.kDSNAttrRecordType)
                    if isinstance(recordType, list):
                        recordType = recordType[0]
                    if not recordType:
                        continue
                    recordType = self._fromODRecordTypes[recordType]

                    # Skip if group restriction is in place and guid is not
                    # a member (but don't skip any groups)
                    if (recordType != self.recordType_groups and
                        self.restrictedGUIDs is not None):
                        if str(recordGUID) not in self.restrictedGUIDs:
                            continue

                    recordAuthIDs = self._setFromAttribute(
                        value.get(dsattributes.kDSNAttrAltSecurityIdentities))
                    recordFullName = value.get(
                        dsattributes.kDS1AttrDistinguishedName)
                    recordFirstName = value.get(dsattributes.kDS1AttrFirstName)
                    recordLastName = value.get(dsattributes.kDS1AttrLastName)
                    recordEmailAddresses = self._setFromAttribute(
                        value.get(dsattributes.kDSNAttrEMailAddress),
                        lower=True)

                    # Special case for groups, which have members.
                    if recordType == self.recordType_groups:
                        memberGUIDs = value.get(dsattributes.kDSNAttrGroupMembers)
                        if memberGUIDs is None:
                            memberGUIDs = ()
                        elif type(memberGUIDs) is str:
                            memberGUIDs = (memberGUIDs,)
                        nestedGUIDs = value.get(dsattributes.kDSNAttrNestedGroups)
                        if nestedGUIDs:
                            if type(nestedGUIDs) is str:
                                nestedGUIDs = (nestedGUIDs,)
                            memberGUIDs += tuple(nestedGUIDs)
                        else:
                            nestedGUIDs = ()
                    else:
                        nestedGUIDs = ()
                        memberGUIDs = ()

                    # Create records but don't store them in our index or
                    # send them to memcached, because these are transient,
                    # existing only so we can create principal resource
                    # objects that are used to generate the REPORT result.

                    record = OpenDirectoryRecord(
                        service=self,
                        recordType=recordType,
                        guid=recordGUID,
                        nodeName=recordNodeName,
                        shortNames=recordShortNames,
                        authIDs=recordAuthIDs,
                        fullName=recordFullName,
                        firstName=recordFirstName,
                        lastName=recordLastName,
                        emailAddresses=recordEmailAddresses,
                        memberGUIDs=memberGUIDs,
                        nestedGUIDs=nestedGUIDs,
                        extProxies=(),
                        extReadOnlyProxies=(),
                    )

                    # (Copied from below)
                    # Look up augment information
                    # TODO: this needs to be deferred but for now we hard code
                    # the deferred result because we know it is completing
                    # immediately.
                    if self.augmentService is not None:
                        d = self.augmentService.getAugmentRecord(record.guid,
                            recordType)
                        d.addCallback(lambda x: record.addAugmentInformation(x))

                    yield record

                except KeyError:
                    pass


        def multiQuery(directory, queries, recordTypes, attrs):
            byGUID = {}
            sets = []

            caseInsensitive = True
            for compound in queries:
                compound = compound.generate()

                self.log.debug("Calling OD: Types %s, Query %s" %
                    (recordTypes, compound))

                try:
                    queryResults = lookupMethod(
                        directory,
                        compound,
                        caseInsensitive,
                        recordTypes,
                        attrs,
                    )

                    newSet = set()
                    for recordName, data in queryResults:
                        guid = data.get(dsattributes.kDS1AttrGeneratedUID, None)
                        if guid:
                            byGUID[guid] = (recordName, data)
                            newSet.add(guid)

                    sets.append(newSet)

                except self.odModule.ODError, e:
                    self.log.error("Ignoring OD Error: %d %s" %
                        (e.message[1], e.message[0]))
                    continue

            results = []
            for guid in set.intersection(*sets):
                recordName, data = byGUID.get(guid, None)
                if data is not None:
                    results.append((data[dsattributes.kDSNAttrRecordName], data))
            return results

        queries = buildQueriesFromTokens(tokens, self._ODFields)

        # Starting with the record types corresponding to the context...
        recordTypes = self.recordTypesForSearchContext(context)
        # ...limit to the types this service supports...
        recordTypes = [r for r in recordTypes if r in self.recordTypes()]
        # ...and map those to OD representations...
        recordTypes = [self._toODRecordTypes[r] for r in recordTypes]

        if recordTypes:
            results = multiQuery(
                self.directory,
                queries,
                recordTypes,
                [
                    dsattributes.kDS1AttrGeneratedUID,
                    dsattributes.kDSNAttrRecordName,
                    dsattributes.kDSNAttrAltSecurityIdentities,
                    dsattributes.kDSNAttrRecordType,
                    dsattributes.kDS1AttrDistinguishedName,
                    dsattributes.kDS1AttrFirstName,
                    dsattributes.kDS1AttrLastName,
                    dsattributes.kDSNAttrEMailAddress,
                    dsattributes.kDSNAttrMetaNodeLocation,
                    dsattributes.kDSNAttrGroupMembers,
                    dsattributes.kDSNAttrNestedGroups,
                ]
            )
            return succeed(collectResults(results))
        else:
            return succeed([])


    def recordsMatchingFields(self, fields, operand="or", recordType=None,
        lookupMethod=None):

        if lookupMethod is None:
            lookupMethod = self.odModule.queryRecordsWithAttribute_list

        # Note that OD applies case-sensitivity globally across the entire
        # query, not per expression, so the current code uses whatever is
        # specified in the last field in the fields list

        def collectResults(results):
            self.log.debug("Got back %d records from OD" % (len(results),))
            for key, value in results:
                self.log.debug("OD result: %s %s" % (key, value))
                try:
                    recordNodeName = value.get(
                        dsattributes.kDSNAttrMetaNodeLocation)
                    recordShortNames = self._uniqueTupleFromAttribute(
                        value.get(dsattributes.kDSNAttrRecordName))

                    recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)

                    recordType = value.get(dsattributes.kDSNAttrRecordType)
                    if isinstance(recordType, list):
                        recordType = recordType[0]
                    if not recordType:
                        continue
                    recordType = self._fromODRecordTypes[recordType]

                    # Skip if group restriction is in place and guid is not
                    # a member (but don't skip any groups)
                    if (recordType != self.recordType_groups and
                        self.restrictedGUIDs is not None):
                        if str(recordGUID) not in self.restrictedGUIDs:
                            continue

                    recordAuthIDs = self._setFromAttribute(
                        value.get(dsattributes.kDSNAttrAltSecurityIdentities))
                    recordFullName = value.get(
                        dsattributes.kDS1AttrDistinguishedName)
                    recordFirstName = value.get(dsattributes.kDS1AttrFirstName)
                    recordLastName = value.get(dsattributes.kDS1AttrLastName)
                    recordEmailAddresses = self._setFromAttribute(
                        value.get(dsattributes.kDSNAttrEMailAddress),
                        lower=True)

                    # Special case for groups, which have members.
                    if recordType == self.recordType_groups:
                        memberGUIDs = value.get(dsattributes.kDSNAttrGroupMembers)
                        if memberGUIDs is None:
                            memberGUIDs = ()
                        elif type(memberGUIDs) is str:
                            memberGUIDs = (memberGUIDs,)
                        nestedGUIDs = value.get(dsattributes.kDSNAttrNestedGroups)
                        if nestedGUIDs:
                            if type(nestedGUIDs) is str:
                                nestedGUIDs = (nestedGUIDs,)
                            memberGUIDs += tuple(nestedGUIDs)
                        else:
                            nestedGUIDs = ()
                    else:
                        nestedGUIDs = ()
                        memberGUIDs = ()

                    # Create records but don't store them in our index or
                    # send them to memcached, because these are transient,
                    # existing only so we can create principal resource
                    # objects that are used to generate the REPORT result.

                    record = OpenDirectoryRecord(
                        service=self,
                        recordType=recordType,
                        guid=recordGUID,
                        nodeName=recordNodeName,
                        shortNames=recordShortNames,
                        authIDs=recordAuthIDs,
                        fullName=recordFullName,
                        firstName=recordFirstName,
                        lastName=recordLastName,
                        emailAddresses=recordEmailAddresses,
                        memberGUIDs=memberGUIDs,
                        nestedGUIDs=nestedGUIDs,
                        extProxies=(),
                        extReadOnlyProxies=(),
                    )

                    # (Copied from below)
                    # Look up augment information
                    # TODO: this needs to be deferred but for now we hard code
                    # the deferred result because we know it is completing
                    # immediately.
                    if self.augmentService is not None:
                        d = self.augmentService.getAugmentRecord(record.guid,
                            recordType)
                        d.addCallback(lambda x: record.addAugmentInformation(x))

                    yield record

                except KeyError:
                    pass


        def multiQuery(directory, queries, attrs, operand):
            byGUID = {}
            sets = []

            for query, recordTypes in queries.iteritems():
                ODField, value, caseless, matchType = query
                if matchType == "starts-with":
                    comparison = dsattributes.eDSStartsWith
                elif matchType == "contains":
                    comparison = dsattributes.eDSContains
                else:
                    comparison = dsattributes.eDSExact

                self.log.debug("Calling OD: Types %s, Field %s, Value %s, Match %s, Caseless %s" %
                    (recordTypes, ODField, value, matchType, caseless))

                try:
                    queryResults = lookupMethod(
                        directory,
                        ODField,
                        value,
                        comparison,
                        caseless,
                        recordTypes,
                        attrs,
                    )

                    if operand == dsquery.expression.OR:
                        for recordName, data in queryResults:
                            guid = data.get(dsattributes.kDS1AttrGeneratedUID, None)
                            if guid:
                                byGUID[guid] = (recordName, data)
                    else: # AND
                        newSet = set()
                        for recordName, data in queryResults:
                            guid = data.get(dsattributes.kDS1AttrGeneratedUID, None)
                            if guid:
                                byGUID[guid] = (recordName, data)
                                newSet.add(guid)

                        sets.append(newSet)

                except self.odModule.ODError, e:
                    self.log.error("Ignoring OD Error: %d %s" %
                        (e.message[1], e.message[0]))
                    continue

            if operand == dsquery.expression.OR:
                return byGUID.values()

            else:
                results = []
                for guid in set.intersection(*sets):
                    recordName, data = byGUID.get(guid, None)
                    if data is not None:
                        results.append((data[dsattributes.kDSNAttrRecordName], data))
                return results

        operand = (dsquery.expression.OR if operand == "or"
            else dsquery.expression.AND)

        if recordType is None:
            # The client is looking for records in any of the four types
            recordTypes = set(self._toODRecordTypes.values())
        else:
            # The client is after only one recordType
            recordTypes = [self._toODRecordTypes[recordType]]

        queries = buildQueries(recordTypes, fields, self._ODFields)

        results = multiQuery(
            self.directory,
            queries,
            [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDSNAttrRecordName,
                dsattributes.kDSNAttrAltSecurityIdentities,
                dsattributes.kDSNAttrRecordType,
                dsattributes.kDS1AttrDistinguishedName,
                dsattributes.kDS1AttrFirstName,
                dsattributes.kDS1AttrLastName,
                dsattributes.kDSNAttrEMailAddress,
                dsattributes.kDSNAttrMetaNodeLocation,
                dsattributes.kDSNAttrGroupMembers,
                dsattributes.kDSNAttrNestedGroups,
            ],
            operand
        )
        return succeed(collectResults(results))


    def queryDirectory(self, recordTypes, indexType, indexKey,
        lookupMethod=None):

        if lookupMethod is None:
            lookupMethod = self.odModule.queryRecordsWithAttribute_list

        origIndexKey = indexKey
        if indexType == self.INDEX_TYPE_CUA:
            # The directory doesn't contain CUAs, so we need to convert
            # the CUA to the appropriate field name and value:
            queryattr, indexKey = cuAddressConverter(indexKey)
            # queryattr will be one of:
            # guid, emailAddresses, or recordName
            # ...which will need to be mapped to DS
            queryattr = self._ODFields[queryattr]['odField']

        else:
            queryattr = {
                self.INDEX_TYPE_SHORTNAME : dsattributes.kDSNAttrRecordName,
                self.INDEX_TYPE_GUID      : dsattributes.kDS1AttrGeneratedUID,
                self.INDEX_TYPE_AUTHID    : dsattributes.kDSNAttrAltSecurityIdentities,
            }.get(indexType)
            assert queryattr is not None, "Invalid type for record faulting query"
        # Make all OD queries case insensitive
        caseInsensitive = True

        results = []
        for recordType in recordTypes:

            attrs = [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDSNAttrRecordName,
                dsattributes.kDSNAttrAltSecurityIdentities,
                dsattributes.kDSNAttrRecordType,
                dsattributes.kDS1AttrDistinguishedName,
                dsattributes.kDS1AttrFirstName,
                dsattributes.kDS1AttrLastName,
                dsattributes.kDSNAttrEMailAddress,
                dsattributes.kDSNAttrMetaNodeLocation,
            ]

            if recordType == DirectoryService.recordType_users:
                listRecordTypes = [self._toODRecordTypes[recordType]]

            elif recordType in (
                DirectoryService.recordType_resources,
                DirectoryService.recordType_locations,
            ):
                if queryattr == dsattributes.kDSNAttrEMailAddress:
                    continue

                listRecordTypes = [self._toODRecordTypes[recordType]]

            elif recordType == DirectoryService.recordType_groups:

                if queryattr == dsattributes.kDSNAttrEMailAddress:
                    continue

                listRecordTypes = [dsattributes.kDSStdRecordTypeGroups]
                attrs.append(dsattributes.kDSNAttrGroupMembers)
                attrs.append(dsattributes.kDSNAttrNestedGroups)

            else:
                raise UnknownRecordTypeError("Unknown OpenDirectory record type: %s" % (recordType))

            # Because we're getting transient OD error -14987, try 3 times:
            for _ignore in xrange(3):
                try:
                    self.log.debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                        self.directory,
                        queryattr,
                        indexKey,
                        dsattributes.eDSExact,
                        caseInsensitive,
                        listRecordTypes,
                        attrs,
                    ))
                    lookedUp = lookupMethod(
                            self.directory,
                            queryattr,
                            indexKey,
                            dsattributes.eDSExact,
                            caseInsensitive,
                            listRecordTypes,
                            attrs,
                        )
                    results.extend(lookedUp)

                except self.odModule.ODError, ex:
                    if ex.message[1] == -14987:
                        # Fall through and retry
                        self.log.error("OpenDirectory (node=%s) error: %s" % (self.realmName, str(ex)))
                    elif ex.message[1] == -14140 or ex.message[1] == -14200:
                        # Unsupported attribute on record - don't fail
                        return
                    else:
                        self.log.error("OpenDirectory (node=%s) error: %s" % (self.realmName, str(ex)))
                        raise
                else:
                    # Success, so break the retry loop
                    break

        self.log.debug("opendirectory.queryRecordsWithAttribute_list matched records: %s" % (len(results),))

        enabledRecords = []
        disabledRecords = []

        for (recordShortName, value) in results:

            # Now get useful record info.
            recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
            recordShortNames = self._uniqueTupleFromAttribute(value.get(dsattributes.kDSNAttrRecordName))
            recordType = value.get(dsattributes.kDSNAttrRecordType)
            if isinstance(recordType, list):
                recordType = recordType[0]
            recordAuthIDs = self._setFromAttribute(value.get(dsattributes.kDSNAttrAltSecurityIdentities))
            recordFullName = value.get(dsattributes.kDS1AttrDistinguishedName)
            recordFirstName = value.get(dsattributes.kDS1AttrFirstName)
            recordLastName = value.get(dsattributes.kDS1AttrLastName)
            recordEmailAddresses = self._setFromAttribute(value.get(dsattributes.kDSNAttrEMailAddress), lower=True)
            recordNodeName = value.get(dsattributes.kDSNAttrMetaNodeLocation)

            if not recordType:
                self.log.debug("Record (unknown)%s in node %s has no recordType; ignoring."
                               % (recordShortName, recordNodeName))
                continue

            recordType = self._fromODRecordTypes[recordType]

            if not recordGUID:
                self.log.debug("Record (%s)%s in node %s has no GUID; ignoring."
                               % (recordType, recordShortName, recordNodeName))
                continue

            if recordGUID.lower().startswith("ffffeeee-dddd-cccc-bbbb-aaaa"):
                self.log.debug("Ignoring system record (%s)%s in node %s."
                               % (recordType, recordShortName, recordNodeName))
                continue

            # If restrictToGroup is in effect, all guids which are not a member
            # of that group are disabled (overriding the augments db).
            if (self.restrictedGUIDs is not None):
                unrestricted = recordGUID in self.restrictedGUIDs
            else:
                unrestricted = True

            # Special case for groups, which have members.
            if recordType == self.recordType_groups:
                memberGUIDs = value.get(dsattributes.kDSNAttrGroupMembers)
                if memberGUIDs is None:
                    memberGUIDs = ()
                elif type(memberGUIDs) is str:
                    memberGUIDs = (memberGUIDs,)
                nestedGUIDs = value.get(dsattributes.kDSNAttrNestedGroups)
                if nestedGUIDs:
                    if type(nestedGUIDs) is str:
                        nestedGUIDs = (nestedGUIDs,)
                    memberGUIDs += tuple(nestedGUIDs)
                else:
                    nestedGUIDs = ()
            else:
                memberGUIDs = ()
                nestedGUIDs = ()

            # Special case for resources and locations
            autoSchedule = False
            proxyGUIDs = ()
            readOnlyProxyGUIDs = ()
            if recordType in (DirectoryService.recordType_resources, DirectoryService.recordType_locations):
                resourceInfo = value.get(dsattributes.kDSNAttrResourceInfo)
                if resourceInfo is not None:
                    if type(resourceInfo) is not str:
                        resourceInfo = resourceInfo[0]
                    try:
                        autoSchedule, proxy, read_only_proxy = self.parseResourceInfo(resourceInfo, recordGUID, recordType, recordShortName)
                    except ValueError:
                        continue
                    if proxy:
                        proxyGUIDs = (proxy,)
                    if read_only_proxy:
                        readOnlyProxyGUIDs = (read_only_proxy,)

            record = OpenDirectoryRecord(
                service=self,
                recordType=recordType,
                guid=recordGUID,
                nodeName=recordNodeName,
                shortNames=recordShortNames,
                authIDs=recordAuthIDs,
                fullName=recordFullName,
                firstName=recordFirstName,
                lastName=recordLastName,
                emailAddresses=recordEmailAddresses,
                memberGUIDs=memberGUIDs,
                nestedGUIDs=nestedGUIDs,
                extProxies=proxyGUIDs,
                extReadOnlyProxies=readOnlyProxyGUIDs,
            )

            # Look up augment information
            # TODO: this needs to be deferred but for now we hard code the deferred result because
            # we know it is completing immediately.
            if self.augmentService is not None:
                d = self.augmentService.getAugmentRecord(record.guid,
                    recordType)
                d.addCallback(lambda x: record.addAugmentInformation(x))

            # Override based on ResourceInfo
            if autoSchedule:
                record.autoSchedule = True

            if not unrestricted:
                self.log.debug("%s is not enabled because it's not a member of group: %s" % (recordGUID, self.restrictToGroup))
                record.enabledForCalendaring = False
                record.enabledForAddressBooks = False

            record.applySACLs()

            if record.enabledForCalendaring:
                enabledRecords.append(record)
            else:
                disabledRecords.append(record)

        record = None
        if len(enabledRecords) == 1:
            record = enabledRecords[0]
        elif len(enabledRecords) == 0 and len(disabledRecords) == 1:
            record = disabledRecords[0]
        elif indexType == self.INDEX_TYPE_GUID and len(enabledRecords) > 1:
            self.log.error("Duplicate records found for GUID %s:" % (indexKey,))
            for duplicateRecord in enabledRecords:
                self.log.error("Duplicate: %s" % (", ".join(duplicateRecord.shortNames)))

        if record:
            if isinstance(origIndexKey, unicode):
                origIndexKey = origIndexKey.encode("utf-8")
            self.log.debug("Storing (%s %s) %s in internal cache" % (indexType, origIndexKey, record))

            self.recordCacheForType(recordType).addRecord(record, indexType, origIndexKey)


    def getResourceInfo(self):
        """
        Resource information including proxy assignments for resource and
        locations, as well as auto-schedule settings, used to live in the
        directory.  This method fetches old resource info for migration
        purposes.
        """
        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
            dsattributes.kDSNAttrResourceInfo,
        ]

        for recordType in (dsattributes.kDSStdRecordTypePlaces, dsattributes.kDSStdRecordTypeResources):
            try:
                self.log.debug("opendirectory.listAllRecordsWithAttributes_list(%r,%r,%r)" % (
                    self.directory,
                    recordType,
                    attrs,
                ))
                results = self.odModule.listAllRecordsWithAttributes_list(
                    self.directory,
                    recordType,
                    attrs,
                )
            except self.odModule.ODError, ex:
                self.log.error("OpenDirectory (node=%s) error: %s" % (self.realmName, str(ex)))
                raise

            for (recordShortName, value) in results:
                recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
                resourceInfo = value.get(dsattributes.kDSNAttrResourceInfo)
                if resourceInfo is not None:
                    if type(resourceInfo) is not str:
                        resourceInfo = resourceInfo[0]
                    try:
                        autoSchedule, proxy, readOnlyProxy = self.parseResourceInfo(resourceInfo,
                            recordGUID, recordType, recordShortName)
                    except ValueError:
                        continue
                    yield recordGUID, autoSchedule, proxy, readOnlyProxy


    def isAvailable(self):
        """
        Returns True if all configured directory nodes are accessible, False otherwise
        """

        if self.node == "/Search":
            result = self.odModule.getNodeAttributes(self.directory, "/Search",
                (dsattributes.kDS1AttrSearchPath,))
            nodes = result[dsattributes.kDS1AttrSearchPath]
        else:
            nodes = [self.node]

        try:
            for node in nodes:
                self.odModule.getNodeAttributes(self.directory, node, [dsattributes.kDSNAttrNodePath])
        except self.odModule.ODError:
            self.log.warn("OpenDirectory Node %s not available" % (node,))
            return False

        return True


    @inlineCallbacks
    def getGroups(self, guids):
        """
        Returns a set of group records for the list of guids passed in.  For
        any group that also contains subgroups, those subgroups' records are
        also returned, and so on.
        """

        recordsByGUID = {}
        valuesToFetch = guids

        loop = 1
        while valuesToFetch:
            self.log.debug("getGroups loop %d" % (loop,))

            results = []

            for batch in splitIntoBatches(valuesToFetch, self.batchSize):
                fields = []
                for value in batch:
                    fields.append(["guid", value, False, "equals"])
                self.log.debug("getGroups fetching batch of %d" %
                    (len(fields),))
                result = list((yield self.recordsMatchingFields(fields,
                    recordType=self.recordType_groups)))
                results.extend(result)
                self.log.debug("getGroups got back batch of %d for subtotal of %d" %
                    (len(result), len(results)))

            # Reset values for next iteration
            valuesToFetch = set()

            for record in results:
                guid = record.guid
                if guid not in recordsByGUID:
                    recordsByGUID[guid] = record

                # record.nestedGUIDs() contains the sub groups of this group
                for memberGUID in record.nestedGUIDs():
                    if memberGUID not in recordsByGUID:
                        self.log.debug("getGroups group %s contains group %s" %
                            (record.guid, memberGUID))
                        valuesToFetch.add(memberGUID)

            loop += 1

        returnValue(recordsByGUID.values())



def buildQueries(recordTypes, fields, mapping):
    """
    Determine how many queries need to be performed in order to work around opendirectory
    quirks, where searching on fields that don't apply to a given recordType returns incorrect
    results (either none, or all records).
    """

    queries = {}
    for recordType in recordTypes:
        for field, value, caseless, matchType in fields:
            if field in mapping:
                if recordType in mapping[field]['appliesTo']:
                    ODField = mapping[field]['odField']
                    key = (ODField, value, caseless, matchType)
                    queries.setdefault(key, []).append(recordType)

    return queries



def buildQueriesFromTokens(tokens, mapping):
    """
    OD /Local doesn't support nested complex queries, so create a list of
    complex queries that will be ANDed together in recordsMatchingTokens()

    @param tokens: The tokens to search on
    @type tokens: C{list} of C{str}
    @param mapping: The mapping of DirectoryRecord attributes to OD attributes
    @type mapping: C{dict}
    @return: A list of expression objects
    @type: C{list}
    """

    if len(tokens) == 0:
        return None

    fields = ["fullName", "emailAddresses"]

    results = []
    for token in tokens:
        queries = []
        for field in fields:
            ODField = mapping[field]['odField']
            query = dsquery.match(ODField, token, "contains")
            queries.append(query)
        results.append(dsquery.expression(dsquery.expression.OR, queries))
    return results



class OpenDirectoryRecord(CachingDirectoryRecord):
    """
    OpenDirectory implementation of L{IDirectoryRecord}.
    """
    def __init__(
        self, service, recordType, guid, nodeName, shortNames, authIDs,
        fullName, firstName, lastName, emailAddresses, memberGUIDs, nestedGUIDs,
        extProxies, extReadOnlyProxies,
    ):
        super(OpenDirectoryRecord, self).__init__(
            service=service,
            recordType=recordType,
            guid=guid,
            shortNames=shortNames,
            authIDs=authIDs,
            fullName=fullName,
            firstName=firstName,
            lastName=lastName,
            emailAddresses=emailAddresses,
            extProxies=extProxies,
            extReadOnlyProxies=extReadOnlyProxies,
        )
        self.nodeName = nodeName

        self._memberGUIDs = tuple(memberGUIDs)
        self._nestedGUIDs = tuple(nestedGUIDs)
        self._groupMembershipGUIDs = None


    def __repr__(self):
        if self.service.realmName == self.nodeName:
            location = self.nodeName
        else:
            location = "%s->%s" % (self.service.realmName, self.nodeName)

        return "<%s[%s@%s(%s)] %s(%s) %r>" % (
            self.__class__.__name__,
            self.recordType,
            self.service.guid,
            location,
            self.guid,
            ",".join(self.shortNames),
            self.fullName
        )


    def members(self):
        if self.recordType != self.service.recordType_groups:
            return

        for guid in self._memberGUIDs:
            userRecord = self.service.recordWithGUID(guid)
            if userRecord is not None:
                yield userRecord


    def groups(self):
        if self._groupMembershipGUIDs is None:
            self._groupMembershipGUIDs = self.service.groupsForGUID(self.guid)

        for guid in self._groupMembershipGUIDs:
            record = self.service.recordWithGUID(guid)
            if record:
                yield record


    def memberGUIDs(self):
        return set(self._memberGUIDs)


    def nestedGUIDs(self):
        return set(self._nestedGUIDs)


    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            # Check cached password
            try:
                if credentials.password == self.password:
                    return True
            except AttributeError:
                pass

            # Check with directory services
            try:
                if self.service.odModule.authenticateUserBasic(self.service.directory, self.nodeName, self.shortNames[0], credentials.password):
                    # Cache the password to avoid future DS queries
                    self.password = credentials.password
                    return True
            except self.service.odModule.ODError, e:
                self.log.error("OpenDirectory (node=%s) error while performing basic authentication for user %s: %s"
                            % (self.service.realmName, self.shortNames[0], e))

            return False

        elif isinstance(credentials, DigestedCredentials):
            #
            # We need a special format for the "challenge" and "response" strings passed into OpenDirectory, as it is
            # picky about exactly what it receives.
            #
            try:
                if "algorithm" not in credentials.fields:
                    credentials.fields["algorithm"] = "md5"
                challenge = 'Digest realm="%(realm)s", nonce="%(nonce)s", algorithm=%(algorithm)s' % credentials.fields
                response = (
                    'Digest username="%(username)s", '
                    'realm="%(realm)s", '
                    'nonce="%(nonce)s", '
                    'uri="%(uri)s", '
                    'response="%(response)s",'
                    'algorithm=%(algorithm)s'
                ) % credentials.fields
            except KeyError, e:
                self.log.error(
                    "OpenDirectory (node=%s) error while performing digest authentication for user %s: "
                    "missing digest response field: %s in: %s"
                    % (self.service.realmName, self.shortNames[0], e, credentials.fields)
                )
                return False

            try:
                if self.digestcache[credentials.fields["uri"]] == response:
                    return True
            except (AttributeError, KeyError):
                pass

            try:
                if self.service.odModule.authenticateUserDigest(
                    self.service.directory,
                    self.nodeName,
                    self.shortNames[0],
                    challenge,
                    response,
                    credentials.method
                ):
                    try:
                        cache = self.digestcache
                    except AttributeError:
                        cache = self.digestcache = {}

                    cache[credentials.fields["uri"]] = response

                    return True
                else:
                    self.log.debug(
"""OpenDirectory digest authentication failed with:
    Nodename:  %s
    Username:  %s
    Challenge: %s
    Response:  %s
    Method:    %s
""" % (self.nodeName, self.shortNames[0], challenge, response,
       credentials.method))

            except self.service.odModule.ODError, e:
                self.log.error(
                    "OpenDirectory (node=%s) error while performing digest authentication for user %s: %s"
                    % (self.service.realmName, self.shortNames[0], e)
                )
                return False

            return False

        return super(OpenDirectoryRecord, self).verifyCredentials(credentials)



class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
