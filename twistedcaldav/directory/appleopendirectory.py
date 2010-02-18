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
Apple OpenDirectory directory service implementation.
"""

__all__ = [
    "OpenDirectoryService",
    "OpenDirectoryInitError",
]

import sys

import opendirectory
import dsattributes
import dsquery

from twisted.internet.threads import deferToThread
from twisted.cred.credentials import UsernamePassword
from twext.web2.auth.digest import DigestedCredentials

from twistedcaldav.config import config
from twistedcaldav.directory import augment
from twistedcaldav.directory.cachingdirectory import CachingDirectoryService,\
    CachingDirectoryRecord
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError
from twistedcaldav.directory.principal import cuAddressConverter

class OpenDirectoryService(CachingDirectoryService):
    """
    OpenDirectory implementation of L{IDirectoryService}.
    """
    baseGUID = "891F8321-ED02-424C-BA72-89C32F215C1E"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.node)


    def __init__(self, params, dosetup=True):
        """
        @param params: a dictionary containing the following keys:
            node: an OpenDirectory node name to bind to.
            cacheTimeout: C{int} number of minutes before cache is invalidated.
        @param dosetup: if C{True} then the directory records are initialized,
                        if C{False} they are not.
                        This should only be set to C{False} when doing unit tests.
        """

        defaults = {
            'node' : '/Search',
            'cacheTimeout' : 30,
            'recordTypes' : (
                self.recordType_users,
                self.recordType_groups,
                self.recordType_locations,
                self.recordType_resources,
            ),
        }
        ignored = (
            'requireComputerRecord',
            'restrictEnabledRecords',
            'restrictToGroup'
        )
        params = self.getParams(params, defaults, ignored)

        self._recordTypes = params['recordTypes']

        super(OpenDirectoryService, self).__init__(params['cacheTimeout'])

        try:
            directory = opendirectory.odInit(params['node'])
        except opendirectory.ODError, e:
            self.log_error("OpenDirectory (node=%s) Initialization error: %s" % (params['node'], e))
            raise

        self.realmName = params['node']
        self.directory = directory
        self.node = params['node']
        self._records = {}
        self._delayedCalls = set()

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

            self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                self.directory,
                dsattributes.kDS1AttrGeneratedUID,
                groupGUID,
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups]
            ))
            result = opendirectory.queryRecordsWithAttribute_list(
                self.directory,
                dsattributes.kDS1AttrGeneratedUID,
                groupGUID,
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups]
            )

            if not result:
                self.log_error("Couldn't find group %s when trying to expand nested groups."
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

    def groupsForGUID(self, guid):
        
        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
        ]

        recordType = dsattributes.kDSStdRecordTypeGroups

        guids = set()

        query = dsquery.match(dsattributes.kDSNAttrGroupMembers, guid, dsattributes.eDSExact)
        try:
            self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                self.directory,
                query.attribute,
                query.value,
                query.matchType,
                False,
                recordType,
                attrs,
            ))
            results = opendirectory.queryRecordsWithAttribute_list(
                self.directory,
                query.attribute,
                query.value,
                query.matchType,
                False,
                recordType,
                attrs,
            )
        except opendirectory.ODError, ex:
            self.log_error("OpenDirectory (node=%s) error: %s" % (self.realmName, str(ex)))
            raise

        for (_ignore_recordShortName, value) in results:

            # Now get useful record info.
            recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
            if recordGUID:
                guids.add(recordGUID)

        query = dsquery.match(dsattributes.kDSNAttrNestedGroups, guid, dsattributes.eDSExact)
        try:
            self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                self.directory,
                query.attribute,
                query.value,
                query.matchType,
                False,
                recordType,
                attrs,
            ))
            results = opendirectory.queryRecordsWithAttribute_list(
                self.directory,
                query.attribute,
                query.value,
                query.matchType,
                False,
                recordType,
                attrs,
            )
        except opendirectory.ODError, ex:
            self.log_error("OpenDirectory (node=%s) error: %s" % (self.realmName, str(ex)))
            raise

        for (_ignore_recordShortName, value) in results:

            # Now get useful record info.
            recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
            if recordGUID:
                guids.add(recordGUID)

        return guids

    def proxiesForGUID(self, recordType, guid):
        
        # Lookup in index
        try:
            # TODO:
            return ()
        except KeyError:
            return ()

    def readOnlyProxiesForGUID(self, recordType, guid):
        
        # Lookup in index
        try:
            # TODO:
            return ()
        except KeyError:
            return ()

    _ODFields = {
        'fullName' : {
            'odField' : dsattributes.kDS1AttrDistinguishedName,
            'appliesTo' : set([
                dsattributes.kDSStdRecordTypeUsers,
                dsattributes.kDSStdRecordTypeGroups,
                dsattributes.kDSStdRecordTypePlaces,
                dsattributes.kDSStdRecordTypeResources,
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
                dsattributes.kDSStdRecordTypePlaces,
                dsattributes.kDSStdRecordTypeResources,
            ]),
        },
        'guid' : {
            'odField' : dsattributes.kDS1AttrGeneratedUID,
            'appliesTo' : set([
                dsattributes.kDSStdRecordTypeUsers,
                dsattributes.kDSStdRecordTypeGroups,
                dsattributes.kDSStdRecordTypePlaces,
                dsattributes.kDSStdRecordTypeResources,
            ]),
        },
    }

    _toODRecordTypes = {
        DirectoryService.recordType_users :
            dsattributes.kDSStdRecordTypeUsers,
        DirectoryService.recordType_locations :
            dsattributes.kDSStdRecordTypePlaces,
        DirectoryService.recordType_groups :
            dsattributes.kDSStdRecordTypeGroups,
        DirectoryService.recordType_resources :
            dsattributes.kDSStdRecordTypeResources,
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

    def recordsMatchingFields(self, fields, operand="or", recordType=None,
        lookupMethod=opendirectory.queryRecordsWithAttributes_list):

        # Note that OD applies case-sensitivity globally across the entire
        # query, not per expression, so the current code uses whatever is
        # specified in the last field in the fields list

        def collectResults(results):
            self.log_debug("Got back %d records from OD" % (len(results),))
            for key, value in results:
                self.log_debug("OD result: %s %s" % (key, value))
                try:
                    recordNodeName = value.get(
                        dsattributes.kDSNAttrMetaNodeLocation)
                    recordShortNames = self._uniqueTupleFromAttribute(
                        value.get(dsattributes.kDSNAttrRecordName))
                    if (recordNodeName == "/Local/Default" and not
                        (config.Scheduling.iMIP.Username in recordShortNames)):
                        continue

                    recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
                    recordType = value.get(dsattributes.kDSNAttrRecordType)
                    if isinstance(recordType, list):
                        recordType = recordType[0]
                    if not recordType:
                        continue
                    recordType = self._fromODRecordTypes[recordType]

                    recordAuthIDs = self._setFromAttribute(
                        value.get(dsattributes.kDSNAttrAltSecurityIdentities))
                    recordFullName = value.get(
                        dsattributes.kDS1AttrDistinguishedName)
                    recordFirstName = value.get(dsattributes.kDS1AttrFirstName)
                    recordLastName = value.get(dsattributes.kDS1AttrLastName)
                    recordEmailAddresses = self._setFromAttribute(
                        value.get(dsattributes.kDSNAttrEMailAddress),
                        lower=True)

                    # Create records but don't store them in our index or
                    # send them to memcached, because these are transient,
                    # existing only so we can create principal resource
                    # objects that are used to generate the REPORT result.

                    record = OpenDirectoryRecord(
                        service               = self,
                        recordType            = recordType,
                        guid                  = recordGUID,
                        nodeName              = recordNodeName,
                        shortNames            = recordShortNames,
                        authIDs               = recordAuthIDs,
                        fullName              = recordFullName,
                        firstName             = recordFirstName,
                        lastName              = recordLastName,
                        emailAddresses        = recordEmailAddresses,
                        memberGUIDs           = (),
                    )
                    yield record

                except KeyError:
                    pass

        def multiQuery(directory, queries, attrs, operand):
            results = []

            for query, recordTypes in queries.iteritems():
                if not query:
                    continue

                expressions = []
                for ODField, value, caseless, matchType in query:
                    if matchType == "starts-with":
                        comparison = dsattributes.eDSStartsWith
                    elif matchType == "contains":
                        comparison = dsattributes.eDSContains
                    else:
                        comparison = dsattributes.eDSExact
                    expressions.append(dsquery.match(ODField, value, comparison))

                complexExpression = dsquery.expression(operand, expressions).generate()

                self.log_debug("Calling OD: Types %s, Operand %s, Caseless %s, %s" %
                    (recordTypes, operand, caseless, complexExpression))

                results.extend(
                    lookupMethod(
                        directory,
                        complexExpression,
                        caseless,
                        recordTypes,
                        attrs,
                    )
                )

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

        deferred = deferToThread(
            multiQuery,
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
            ],
            operand
        )
        deferred.addCallback(collectResults)
        return deferred


    def queryDirectory(self, recordTypes, indexType, indexKey,
        lookupMethod=opendirectory.queryRecordsWithAttribute_list):
        
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

        query = dsquery.match(queryattr, indexKey, dsattributes.eDSExact)


        listRecordTypes = []
        for recordType in recordTypes:
            if recordType == DirectoryService.recordType_users:
                listRecordTypes.append(dsattributes.kDSStdRecordTypeUsers)
    
            elif recordType == DirectoryService.recordType_groups:
                if queryattr != dsattributes.kDSNAttrEMailAddress:
                    listRecordTypes.append(dsattributes.kDSStdRecordTypeGroups)
                    attrs.append(dsattributes.kDSNAttrGroupMembers)
                    attrs.append(dsattributes.kDSNAttrNestedGroups)
    
            elif recordType == DirectoryService.recordType_locations:
                if queryattr != dsattributes.kDSNAttrEMailAddress:
                    listRecordTypes.append(dsattributes.kDSStdRecordTypePlaces)
                # MOR: possibly can be removed
                attrs.append(dsattributes.kDSNAttrResourceInfo)
            
            elif recordType == DirectoryService.recordType_resources:
                if queryattr != dsattributes.kDSNAttrEMailAddress:
                    listRecordTypes.append(dsattributes.kDSStdRecordTypeResources)
                # MOR: possibly can be removed
                attrs.append(dsattributes.kDSNAttrResourceInfo)
            
            else:
                raise UnknownRecordTypeError("Unknown OpenDirectory record type: %s" % (recordType))


        try:
            self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                self.directory,
                query.attribute,
                query.value,
                query.matchType,
                False,
                listRecordTypes,
                attrs,
            ))
            results = lookupMethod(
                self.directory,
                query.attribute,
                query.value,
                query.matchType,
                False,
                listRecordTypes,
                attrs,
            )
            self.log_debug("opendirectory.queryRecordsWithAttribute_list matched records: %s" % (len(results),))

        except opendirectory.ODError, ex:
            if ex.message[1] == -14140 or ex.message[1] == -14200:
                # Unsupported attribute on record - don't fail
                return
            else:
                self.log_error("OpenDirectory (node=%s) error: %s" % (self.realmName, str(ex)))
                raise


        enabledRecords = []
        disabledRecords = []

        for (recordShortName, value) in results:

            # Now get useful record info.
            recordGUID           = value.get(dsattributes.kDS1AttrGeneratedUID)
            recordShortNames     = self._uniqueTupleFromAttribute(value.get(dsattributes.kDSNAttrRecordName))
            recordType           = value.get(dsattributes.kDSNAttrRecordType)
            if isinstance(recordType, list):
                recordType = recordType[0]
            recordAuthIDs        = self._setFromAttribute(value.get(dsattributes.kDSNAttrAltSecurityIdentities))
            recordFullName       = value.get(dsattributes.kDS1AttrDistinguishedName)
            recordFirstName      = value.get(dsattributes.kDS1AttrFirstName)
            recordLastName       = value.get(dsattributes.kDS1AttrLastName)
            recordEmailAddresses = self._setFromAttribute(value.get(dsattributes.kDSNAttrEMailAddress), lower=True)
            recordNodeName       = value.get(dsattributes.kDSNAttrMetaNodeLocation)

            if recordNodeName == "/Local/Default" and not (config.Scheduling.iMIP.Username in recordShortNames):
                self.log_info("Local record (%s)%s is not eligible for calendaring."
                              % (recordType, recordShortName))
                continue

            if not recordType:
                self.log_debug("Record (unknown)%s in node %s has no recordType; ignoring."
                               % (recordShortName, recordNodeName))
                continue

            recordType = self._fromODRecordTypes[recordType]

            if not recordGUID:
                self.log_debug("Record (%s)%s in node %s has no GUID; ignoring."
                               % (recordType, recordShortName, recordNodeName))
                continue

            if recordGUID.lower().startswith("ffffeeee-dddd-cccc-bbbb-aaaa"):
                self.log_debug("Ignoring system record (%s)%s in node %s."
                               % (recordType, recordShortName, recordNodeName))
                continue

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
                memberGUIDs = ()

            record = OpenDirectoryRecord(
                service               = self,
                recordType            = recordType,
                guid                  = recordGUID,
                nodeName              = recordNodeName,
                shortNames            = recordShortNames,
                authIDs               = recordAuthIDs,
                fullName              = recordFullName,
                firstName             = recordFirstName,
                lastName              = recordLastName,
                emailAddresses        = recordEmailAddresses,
                memberGUIDs           = memberGUIDs,
            )

            # Look up augment information
            # TODO: this needs to be deferred but for now we hard code the deferred result because
            # we know it is completing immediately.
            d = augment.AugmentService.getAugmentRecord(record.guid)
            d.addCallback(lambda x:record.addAugmentInformation(x))

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
            self.log_error("Duplicate records found for GUID %s:" % (indexKey,))
            for duplicateRecord in enabledRecords:
                self.log_error("Duplicate: %s" % (", ".join(duplicateRecord.shortNames)))

        if record:
            if isinstance(origIndexKey, unicode):
                origIndexKey = origIndexKey.encode("utf-8")
            self.log_debug("Storing (%s %s) %s in internal cache" % (indexType, origIndexKey, record))

            # Fetch the set of groups this record is a member of so we can
            # cache it, rather than have each process make the same group
            # lookup
            record._groupMembershipGUIDs = self.groupsForGUID(record.guid)

            self.recordCacheForType(recordType).addRecord(record, indexType, origIndexKey)

    def isAvailable(self):
        """
        Returns True if all configured directory nodes are accessible, False otherwise
        """

        if self.node == "/Search":
            result = opendirectory.getNodeAttributes(self.directory, "/Search",
                (dsattributes.kDS1AttrSearchPath,))
            nodes = result[dsattributes.kDS1AttrSearchPath]
        else:
            nodes = [self.node]

        try:
            for node in nodes:
                opendirectory.getNodeAttributes(self.directory, node, [dsattributes.kDSNAttrNodePath])
        except opendirectory.ODError:
            self.log_warn("OpenDirectory Node %s not available" % (node,))
            return False

        return True



def buildQueries(recordTypes, fields, mapping):
    """
    Determine how many queries need to be performed in order to work around opendirectory
    quirks, where searching on fields that don't apply to a given recordType returns incorrect
    results (either none, or all records).
    """

    fieldLists = {}
    for recordType in recordTypes:
        fieldLists[recordType] = []
        for field, value, caseless, matchType in fields:
            if field in mapping:
                if recordType in mapping[field]['appliesTo']:
                    ODField = mapping[field]['odField']
                    fieldLists[recordType].append((ODField, value, caseless, matchType))

    queries = {}
    for recordType, fieldList in fieldLists.iteritems():
        key = tuple(fieldList)
        queries.setdefault(key, []).append(recordType)
    return queries


class OpenDirectoryRecord(CachingDirectoryRecord):
    """
    OpenDirectory implementation of L{IDirectoryRecord}.
    """
    def __init__(
        self, service, recordType, guid, nodeName, shortNames, authIDs,
        fullName, firstName, lastName, emailAddresses, memberGUIDs,
    ):
        super(OpenDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = guid,
            shortNames            = shortNames,
            authIDs               = authIDs,
            fullName              = fullName,
            firstName             = firstName,
            lastName              = lastName,
            emailAddresses        = emailAddresses,
        )
        self.nodeName = nodeName
        self._memberGUIDs = tuple(memberGUIDs)
        
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
                if opendirectory.authenticateUserBasic(self.service.directory, self.nodeName, self.shortNames[0], credentials.password):
                    # Cache the password to avoid future DS queries
                    self.password = credentials.password
                    return True
            except opendirectory.ODError, e:
                self.log_error("OpenDirectory (node=%s) error while performing basic authentication for user %s: %s"
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
                self.log_error(
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
                if opendirectory.authenticateUserDigest(
                    self.service.directory,
                    self.nodeName,
                    self.shortNames[0],
                    challenge,
                    response,
                    credentials.originalMethod if credentials.originalMethod else credentials.method
                ):
                    try:
                        cache = self.digestcache
                    except AttributeError:
                        cache = self.digestcache = {}

                    cache[credentials.fields["uri"]] = response

                    return True
                else:
                    self.log_debug(
"""OpenDirectory digest authentication failed with:
    Nodename:  %s
    Username:  %s
    Challenge: %s
    Response:  %s
    Method:    %s
""" % (self.nodeName, self.shortNames[0], challenge, response, credentials.originalMethod if credentials.originalMethod else credentials.method))

            except opendirectory.ODError, e:
                self.log_error(
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
