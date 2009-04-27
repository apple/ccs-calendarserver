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
Apple Open Directory directory service implementation.
"""

__all__ = [
    "OpenDirectoryService",
    "OpenDirectoryInitError",
]

import sys
import time
from uuid import UUID

from twext.python.plistlib import readPlistFromString

from xml.parsers.expat import ExpatError

import opendirectory
import dsattributes
import dsquery

from twisted.internet.threads import deferToThread
from twisted.cred.credentials import UsernamePassword
from twisted.web2.auth.digest import DigestedCredentials
from twistedcaldav.config import config

from twistedcaldav.directory.cachingdirectory import CachingDirectoryService,\
    CachingDirectoryRecord
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError

class OpenDirectoryService(CachingDirectoryService):
    """
    Open Directory implementation of L{IDirectoryService}.
    """
    baseGUID = "891F8321-ED02-424C-BA72-89C32F215C1E"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.node)

    def __init__(
        self,
        node="/Search",
        restrictEnabledRecords=False,
        restrictToGroup="",
        dosetup=True,
        cacheTimeout=30
    ):
        """
        @param node: an OpenDirectory node name to bind to.
        @param restrictEnabledRecords: C{True} if a group in the directory is to be used to determine
            which calendar users are enabled.
        @param restrictToGroup: C{str} guid or name of group used to restrict enabled users.
        @param dosetup: if C{True} then the directory records are initialized,
                        if C{False} they are not.
                        This should only be set to C{False} when doing unit tests.
        @param cacheTimeout: C{int} number of minutes before cache is invalidated.
        """

        super(OpenDirectoryService, self).__init__(cacheTimeout)

        try:
            directory = opendirectory.odInit(node)
        except opendirectory.ODError, e:
            self.log_error("Open Directory (node=%s) Initialization error: %s" % (node, e))
            raise

        self.realmName = node
        self.directory = directory
        self.node = node
        self.restrictEnabledRecords = restrictEnabledRecords
        self.restrictToGroup = restrictToGroup
        try:
            UUID(self.restrictToGroup)
        except:
            self.restrictToGUID = False
        else:
            self.restrictToGUID = True
        self.restrictedGUIDs = None
        self.restrictedTimestamp = 0
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

    def _calendarUserAddresses(self, recordType, recordData):
        """
        Extract specific attributes from the directory record for use as calendar user address.
        
        @param recordData: a C{dict} containing the attributes retrieved from the directory.
        @return: a C{set} of C{str} for each expanded calendar user address.
        """
        # Now get the addresses
        result = set()
        
        # Add each email address as a mailto URI
        emails = recordData.get(dsattributes.kDSNAttrEMailAddress)
        if emails is not None:
            if isinstance(emails, str):
                emails = [emails]
            for email in emails:
                result.add("mailto:%s" % (email.lower(),))
                
        return result

    def recordTypes(self):
        return (
            self.recordType_users,
            self.recordType_groups,
            self.recordType_locations,
            self.recordType_resources,
        )

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
            self.log_error("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
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
            self.log_error("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
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
            'excludes' : set(),
        },
        'firstName' : {
            'odField' : dsattributes.kDS1AttrFirstName,
            'excludes' : set([
                dsattributes.kDSStdRecordTypePlaces,
                dsattributes.kDSStdRecordTypeResources,
            ]),
        },
        'lastName' : {
            'odField' : dsattributes.kDS1AttrLastName,
            'excludes' : set([
                dsattributes.kDSStdRecordTypePlaces,
                dsattributes.kDSStdRecordTypeResources,
            ]),
        },
        'emailAddresses' : {
            'odField' : dsattributes.kDSNAttrEMailAddress,
            'excludes' : set([
                dsattributes.kDSStdRecordTypePlaces,
                dsattributes.kDSStdRecordTypeResources,
            ]),
        },
        'recordName' : {
            'odField' : dsattributes.kDSNAttrRecordName,
            'excludes' : set(),
        },
        'guid' : {
            'odField' : dsattributes.kDS1AttrGeneratedUID,
            'excludes' : set(),
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

    def recordsMatchingFields(self, fields, operand="or", recordType=None):

        # Note that OD applies case-sensitivity globally across the entire
        # query, not per expression, so the current code uses whatever is
        # specified in the last field in the fields list

        def collectResults(results):
            self.log_info("Got back %d records from OD" % (len(results),))
            for key, val in results.iteritems():
                self.log_debug("OD result: %s %s" % (key, val))
                try:
                    guid = val[dsattributes.kDS1AttrGeneratedUID]
                    record = self.recordWithGUID(guid)
                    if record:
                        yield record
                except KeyError:
                    pass


        operand = (dsquery.expression.OR if operand == "or"
            else dsquery.expression.AND)

        excluded = set()
        for field, value, caseless, matchType in fields:
            if field in self._ODFields:
                ODField = self._ODFields[field]['odField']
                excluded = excluded | self._ODFields[field]['excludes']

        if recordType is None:
            # The client is looking for records in any of the four types
            recordTypes = set(self._toODRecordTypes.values())

            # Certain query combinations yield invalid results.  In particular,
            # any time you query on EMailAddress and are specifying Places
            # and/or Resources in the requested types, you will get all
            # Places/Resources returned.  So here we will filter out known
            # invalid combinations:
            excludeFields = False
            recordTypes = list(recordTypes - excluded)

        else:
            # The client is after only one recordType, so let's tailor the
            # query to not include any fields OD has trouble with:
            excludeFields = True
            recordTypes = [self._toODRecordTypes[recordType]]

        expressions = []
        for field, value, caseless, matchType in fields:
            if field in self._ODFields:

                if (excludeFields and
                    self._toODRecordTypes[recordType] in self._ODFields[field]['excludes']):
                    # This is a field we're excluding because it behaves badly
                    # for the record type result we're looking for.  Skip it.
                    continue

                ODField = self._ODFields[field]['odField']
                if matchType == "starts-with":
                    comparison = dsattributes.eDSStartsWith
                elif matchType == "contains":
                    comparison = dsattributes.eDSContains
                else:
                    comparison = dsattributes.eDSExact
                expressions.append(dsquery.match(ODField, value, comparison))

        if not recordTypes or not expressions:
            # If we've excluded all types or all expressions, short circuit.
            self.log_info("Empty query, skipping call to OD")
            return []

        self.log_info("Calling OD: Types %s, Operand %s, Caseless %s, %s" %
            (recordTypes, operand, caseless, fields))

        deferred = deferToThread(
            opendirectory.queryRecordsWithAttributes,
            self.directory,
            dsquery.expression(operand, expressions).generate(),
            caseless,
            recordTypes,
            [ dsattributes.kDS1AttrGeneratedUID ]
        )
        deferred.addCallback(collectResults)
        return deferred


    def queryDirectory(self, recordTypes, indexType, indexKey):
        
        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
            dsattributes.kDSNAttrRecordName,
            dsattributes.kDSNAttrRecordType,
            dsattributes.kDS1AttrDistinguishedName,
            dsattributes.kDS1AttrFirstName,
            dsattributes.kDS1AttrLastName,
            dsattributes.kDSNAttrEMailAddress,
            dsattributes.kDSNAttrMetaNodeLocation,
        ]

        listRecordTypes = []
        for recordType in recordTypes:
            if recordType == DirectoryService.recordType_users:
                listRecordTypes.append(dsattributes.kDSStdRecordTypeUsers)
    
            elif recordType == DirectoryService.recordType_groups:
                listRecordTypes.append(dsattributes.kDSStdRecordTypeGroups)
                attrs.append(dsattributes.kDSNAttrGroupMembers)
                attrs.append(dsattributes.kDSNAttrNestedGroups)
    
            elif recordType == DirectoryService.recordType_locations:
                # Email addresses and locations don't mix
                if indexType != self.INDEX_TYPE_EMAIL:
                    listRecordTypes.append(dsattributes.kDSStdRecordTypePlaces)
                # MOR: possibly can be removed
                attrs.append(dsattributes.kDSNAttrResourceInfo)
            
            elif recordType == DirectoryService.recordType_resources:
                # Email addresses and resources don't mix
                if indexType != self.INDEX_TYPE_EMAIL:
                    listRecordTypes.append(dsattributes.kDSStdRecordTypeResources)
                # MOR: possibly can be removed
                attrs.append(dsattributes.kDSNAttrResourceInfo)
            
            else:
                raise UnknownRecordTypeError("Unknown Open Directory record type: %s" % (recordType))

        queryattr = {
            self.INDEX_TYPE_SHORTNAME : dsattributes.kDSNAttrRecordName,
            self.INDEX_TYPE_GUID      : dsattributes.kDS1AttrGeneratedUID,
            self.INDEX_TYPE_EMAIL     : dsattributes.kDSNAttrEMailAddress,
        }.get(indexType)
        assert queryattr is not None, "Invalid type for record faulting query"
        query = dsquery.match(queryattr, indexKey, dsattributes.eDSExact)

        try:
            results = opendirectory.queryRecordsWithAttributes(
                self.directory,
                "(%s=%s)" % (queryattr, query.value),
                True, # caseless
                listRecordTypes,
                attrs,
            )
            self.log_debug("opendirectory.queryRecordsWithAttributes matched records: %s" % (len(results),))

            #  Commented out because this method is not working for email addresses...
            #  TODO: figure out why
            #
            # self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
            #     self.directory,
            #     query.attribute,
            #     query.value,
            #     query.matchType,
            #     False,
            #     listRecordTypes,
            #     attrs,
            # ))
            # results = opendirectory.queryRecordsWithAttribute_list(
            #     self.directory,
            #     query.attribute,
            #     query.value,
            #     query.matchType,
            #     False,
            #     listRecordTypes,
            #     attrs,
            #  )
            # self.log_debug("opendirectory.queryRecordsWithAttribute_list matched records: %s" % (len(results),))

        except opendirectory.ODError, ex:
            if ex.message[1] == -14140 or ex.message[1] == -14200:
                # Unsupported attribute on record - don't fail
                return
            else:
                self.log_error("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
                raise

        enabled_count = 0

        def _uniqueTupleFromAttribute(attribute):
            if attribute:
                if isinstance(attribute, str):
                    return (attribute,)
                else:
                    s = set()
                    return tuple([(s.add(x), x)[1] for x in attribute if x not in s])
            else:
                return ()

        def _setFromAttribute(attribute, lower=False):
            if attribute:
                if isinstance(attribute, str):
                    return set((attribute.lower() if lower else attribute,))
                else:
                    return set([item.lower() if lower else item for item in attribute])
            else:
                return ()
            
        for (recordShortName, value) in results.iteritems():

            # Now get useful record info.
            recordGUID           = value.get(dsattributes.kDS1AttrGeneratedUID)
            recordShortNames     = _uniqueTupleFromAttribute(value.get(dsattributes.kDSNAttrRecordName))
            recordType           = value.get(dsattributes.kDSNAttrRecordType)
            if isinstance(recordType, list):
                recordType = recordType[0]
            recordAuthIDs        = _setFromAttribute(value.get(dsattributes.kDSNAttrAltSecurityIdentities))
            recordFullName       = value.get(dsattributes.kDS1AttrDistinguishedName)
            recordFirstName      = value.get(dsattributes.kDS1AttrFirstName)
            recordLastName       = value.get(dsattributes.kDS1AttrLastName)
            recordEmailAddresses = _setFromAttribute(value.get(dsattributes.kDSNAttrEMailAddress), lower=True)
            recordNodeName       = value.get(dsattributes.kDSNAttrMetaNodeLocation)

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

            # Determine enabled state
            if recordType == self.recordType_groups:
                enabledForCalendaring = False
            else:
                if (
                    self.restrictEnabledRecords and
                    config.Scheduling.iMIP.Username != recordShortName
                ):
                    if time.time() - self.restrictedTimestamp > self.cacheTimeout:
                        attributeToMatch = dsattributes.kDS1AttrGeneratedUID if self.restrictToGUID else dsattributes.kDSNAttrRecordName
                        valueToMatch = self.restrictToGroup
                        self.log_debug("Doing restricted group membership check")
                        self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                            self.directory,
                            attributeToMatch,
                            valueToMatch,
                            dsattributes.eDSExact,
                            False,
                            dsattributes.kDSStdRecordTypeGroups,
                            [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups,],
                        ))
                        results = opendirectory.queryRecordsWithAttribute_list(
                            self.directory,
                            attributeToMatch,
                            valueToMatch,
                            dsattributes.eDSExact,
                            False,
                            dsattributes.kDSStdRecordTypeGroups,
                            [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups,],
                        )

                        if len(results) == 1:
                            members = results[0][1].get(dsattributes.kDSNAttrGroupMembers, [])
                            nestedGroups = results[0][1].get(dsattributes.kDSNAttrNestedGroups, [])
                        else:
                            members = []
                            nestedGroups = []
                        self.restrictedGUIDs = set(self._expandGroupMembership(members, nestedGroups, returnGroups=True))
                        self.log_debug("Got %d restricted group members" % (len(self.restrictedGUIDs),))
                        self.restrictedTimestamp = time.time()

                    enabledForCalendaring = recordGUID in self.restrictedGUIDs
                else:
                    enabledForCalendaring = True

            if enabledForCalendaring:
                enabled_count += 1
                calendarUserAddresses = self._calendarUserAddresses(recordType, value)
            else:
                # Some records we want to keep even though they are not enabled for calendaring.
                # Others we discard.
                if recordType not in (
                    self.recordType_users,
                    self.recordType_groups,
                ):
                    self.log_debug(
                        "Record (%s) %s is not enabled for calendaring"
                        % (recordType, recordShortName)
                    )
                    continue

                self.log_debug(
                    "Record (%s) %s is not enabled for calendaring but may be used in ACLs"
                    % (recordType, recordShortName)
                )
                calendarUserAddresses = ()

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
                calendarUserAddresses = calendarUserAddresses,
                enabledForCalendaring = enabledForCalendaring,
                memberGUIDs           = memberGUIDs,
            )
            self.recordCacheForType(recordType).addRecord(record)

    def _parseResourceInfo(self, plist, guid, recordType, shortname):
        """
        Parse OD ResourceInfo attribute and extract information that the server needs.

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
        except (ExpatError, AttributeError), e:
            self.log_error(
                "Failed to parse ResourceInfo attribute of record (%s)%s (guid=%s): %s\n%s" %
                (recordType, shortname, guid, e, plist,)
            )
            raise ValueError("Invalid ResourceInfo")

        return (autoaccept, proxy, read_only_proxy,)

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
                self.log_debug("opendirectory.listAllRecordsWithAttributes_list(%r,%r,%r)" % (
                    self.directory,
                    recordType,
                    attrs,
                ))
                results = opendirectory.listAllRecordsWithAttributes_list(
                    self.directory,
                    recordType,
                    attrs,
                )
            except opendirectory.ODError, ex:
                self.log_error("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
                raise

            for (recordShortName, value) in results:
                recordGUID = value.get(dsattributes.kDS1AttrGeneratedUID)
                resourceInfo = value.get(dsattributes.kDSNAttrResourceInfo)
                if resourceInfo is not None:
                    try:
                        autoSchedule, proxy, readOnlyProxy = self._parseResourceInfo(resourceInfo,
                            recordGUID, recordType, recordShortName)
                    except ValueError:
                        continue
                    yield recordGUID, autoSchedule, proxy, readOnlyProxy


class OpenDirectoryRecord(CachingDirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def __init__(
        self, service, recordType, guid, nodeName, shortNames, authIDs,
        fullName, firstName, lastName, emailAddresses,
        calendarUserAddresses,
        enabledForCalendaring,
        memberGUIDs,
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
            calendarUserAddresses = calendarUserAddresses,
            enabledForCalendaring = enabledForCalendaring,
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
                self.log_error("Open Directory (node=%s) error while performing basic authentication for user %s: %s"
                            % (self.service.realmName, self.shortNames[0], e))

            return False

        elif isinstance(credentials, DigestedCredentials):
            #
            # We need a special format for the "challenge" and "response" strings passed into open directory, as it is
            # picky about exactly what it receives.
            #
            try:
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
                    "Open Directory (node=%s) error while performing digest authentication for user %s: "
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
                    credentials.method
                ):
                    try:
                        cache = self.digestcache
                    except AttributeError:
                        cache = self.digestcache = {}

                    cache[credentials.fields["uri"]] = response

                    return True
                else:
                    self.log_debug(
"""Open Directory digest authentication failed with:
    Nodename:  %s
    Username:  %s
    Challenge: %s
    Response:  %s
    Method:    %s
""" % (self.nodeName, self.shortNames[0], challenge, response, credentials.method))

            except opendirectory.ODError, e:
                self.log_error(
                    "Open Directory (node=%s) error while performing digest authentication for user %s: %s"
                    % (self.service.realmName, self.shortNames[0], e)
                )
                return False

            return False

        return super(OpenDirectoryRecord, self).verifyCredentials(credentials)

class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
