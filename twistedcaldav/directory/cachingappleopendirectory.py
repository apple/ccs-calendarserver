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
from uuid import UUID

from twext.python.plistlib import readPlistFromString

from xml.parsers.expat import ExpatError

import opendirectory
import dsattributes
import dsquery

from twisted.internet.threads import deferToThread
from twisted.cred.credentials import UsernamePassword
from twisted.web2.auth.digest import DigestedCredentials

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
        self.cacheTimeout = cacheTimeout
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

    def recordTypes(self):
        return (
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources,
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
        'fullName' : dsattributes.kDS1AttrDistinguishedName,
        'firstName' : dsattributes.kDS1AttrFirstName,
        'lastName' : dsattributes.kDS1AttrLastName,
        'emailAddresses' : dsattributes.kDSNAttrEMailAddress,
        'recordName' : dsattributes.kDSNAttrRecordName,
        'guid' : dsattributes.kDS1AttrGeneratedUID,
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

        expressions = []
        for field, value, caseless, matchType in fields:
            if field in self._ODFields:
                ODField = self._ODFields[field]
                if matchType == "starts-with":
                    comparison = dsattributes.eDSStartsWith
                elif matchType == "contains":
                    comparison = dsattributes.eDSContains
                else:
                    comparison = dsattributes.eDSExact
                expressions.append(dsquery.match(ODField, value, comparison))


        if recordType is None:
            recordTypes = self._toODRecordTypes.values()
        else:
            recordTypes = (self._toODRecordTypes[recordType],)

        self.log_info("Calling OD: Types %s, Operand %s, Caseless %s, %s" % (recordTypes, operand, caseless, fields))
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
                listRecordTypes.append(dsattributes.kDSStdRecordTypePlaces)
                attrs.append(dsattributes.kDSNAttrResourceInfo)
            
            elif recordType == DirectoryService.recordType_resources:
                listRecordTypes.append(dsattributes.kDSStdRecordTypeResources)
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
            self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                self.directory,
                query.attribute,
                query.value,
                query.matchType,
                False,
                listRecordTypes,
                attrs,
            ))
            results = opendirectory.queryRecordsWithAttribute_list(
                self.directory,
                query.attribute,
                query.value,
                query.matchType,
                False,
                listRecordTypes,
                attrs,
            )
        except opendirectory.ODError, ex:
            self.log_error("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
            raise

        for (recordShortName, value) in results:

            # Now get useful record info.
            recordGUID         = value.get(dsattributes.kDS1AttrGeneratedUID)
            recordShortNames   = value.get(dsattributes.kDSNAttrRecordName)
            recordType         = value.get(dsattributes.kDSNAttrRecordType)
            if isinstance(recordType, list):
                recordType = recordType[0]                
            if isinstance(recordShortNames, str):
                recordShortNames = (recordShortNames,)
            else:
                recordShortNames = tuple(recordShortNames) if recordShortNames else ()
            recordFullName     = value.get(dsattributes.kDS1AttrDistinguishedName)
            recordFirstName    = value.get(dsattributes.kDS1AttrFirstName)
            recordLastName     = value.get(dsattributes.kDS1AttrLastName)
            recordEmailAddress = value.get(dsattributes.kDSNAttrEMailAddress)
            recordNodeName     = value.get(dsattributes.kDSNAttrMetaNodeLocation)

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
            enabledForCalendaring = True

            if self.restrictEnabledRecords and self.restrictedGUIDs is not None:
                enabledForCalendaring = recordGUID in self.restrictedGUIDs

            if not enabledForCalendaring:
                # Some records we want to keep even though they are not enabled for calendaring.
                # Others we discard.
                if recordType in (
                    DirectoryService.recordType_users,
                    DirectoryService.recordType_groups,
                ):
                    self.log_debug(
                        "Record (%s) %s is not enabled for calendaring but may be used in ACLs"
                        % (recordType, recordShortName)
                    )
                else:
                    self.log_debug(
                        "Record (%s) %s is not enabled for calendaring"
                        % (recordType, recordShortName)
                    )
                    continue

            # Get calendar user addresses from directory record.
            if enabledForCalendaring:
                calendarUserAddresses = self._calendarUserAddresses(recordType, value)
            else:
                calendarUserAddresses = ()

            # Get email address from directory record
            recordEmailAddresses = set()
            if isinstance(recordEmailAddress, str):
                recordEmailAddresses.add(recordEmailAddress.lower())
            elif isinstance(recordEmailAddress, list):
                for addr in recordEmailAddresses:
                    recordEmailAddresses.add(addr.lower())

            # Special case for groups, which have members.
            if recordType == DirectoryService.recordType_groups:
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

            # Special case for resources and locations
            autoSchedule = False
            proxyGUIDs = ()
            readOnlyProxyGUIDs = ()
            if recordType in (DirectoryService.recordType_resources, DirectoryService.recordType_locations):
                resourceInfo = value.get(dsattributes.kDSNAttrResourceInfo)
                if resourceInfo is not None:
                    try:
                        autoSchedule, proxy, read_only_proxy = self._parseResourceInfo(resourceInfo, recordGUID, recordType, recordShortName)
                    except ValueError:
                        continue
                    if proxy:
                        proxyGUIDs = (proxy,)
                    if read_only_proxy:
                        readOnlyProxyGUIDs = (read_only_proxy,)

            record = OpenDirectoryRecord(
                service               = self,
                recordType            = recordType,
                guid                  = recordGUID,
                nodeName              = recordNodeName,
                shortNames            = recordShortNames,
                fullName              = recordFullName,
                firstName             = recordFirstName,
                lastName              = recordLastName,
                emailAddresses        = recordEmailAddresses,
                calendarUserAddresses = calendarUserAddresses,
                autoSchedule          = autoSchedule,
                enabledForCalendaring = enabledForCalendaring,
                memberGUIDs           = memberGUIDs,
                proxyGUIDs            = proxyGUIDs,
                readOnlyProxyGUIDs    = readOnlyProxyGUIDs,
            )
            self.recordCacheForType(recordType).addRecord(record)

class OpenDirectoryRecord(CachingDirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def __init__(
        self, service, recordType, guid, nodeName, shortNames, fullName,
        firstName, lastName, emailAddresses,
        calendarUserAddresses, autoSchedule, enabledForCalendaring,
        memberGUIDs, proxyGUIDs, readOnlyProxyGUIDs,
    ):
        super(OpenDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = guid,
            shortNames            = shortNames,
            fullName              = fullName,
            firstName             = firstName,
            lastName              = lastName,
            emailAddresses        = emailAddresses,
            calendarUserAddresses = calendarUserAddresses,
            autoSchedule          = autoSchedule,
            enabledForCalendaring = enabledForCalendaring,
        )
        self.nodeName = nodeName
        self._memberGUIDs = tuple(memberGUIDs)
        self._proxyGUIDs = tuple(proxyGUIDs)
        self._readOnlyProxyGUIDs = tuple(readOnlyProxyGUIDs)
        
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
        if self.recordType != DirectoryService.recordType_groups:
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

    def proxies(self):
        if self.recordType not in (DirectoryService.recordType_resources, DirectoryService.recordType_locations):
            return

        for guid in self._proxyGUIDs:
            proxyRecord = self.service.recordWithGUID(guid)
            if proxyRecord is None:
                self.log_error("No record for proxy in (%s)%s with GUID %s" % (
                    self.recordType,
                    self.shortNames[0],
                    guid,
                ))
            else:
                yield proxyRecord

    def proxyFor(self):
        result = set()
        result.update(self.service.proxiesForGUID(DirectoryService.recordType_resources, self.guid))
        result.update(self.service.proxiesForGUID(DirectoryService.recordType_locations, self.guid))
        return result

    def readOnlyProxies(self):
        if self.recordType not in (DirectoryService.recordType_resources, DirectoryService.recordType_locations):
            return

        for guid in self._readOnlyProxyGUIDs:
            proxyRecord = self.service.recordWithGUID(guid)
            if proxyRecord is None:
                self.log_error("No record for proxy in (%s)%s with GUID %s" % (
                    self.recordType,
                    self.shortNames[0],
                    guid,
                ))
            else:
                yield proxyRecord

    def readOnlyProxyFor(self):
        result = set()
        result.update(self.service.readOnlyProxiesForGUID(DirectoryService.recordType_resources, self.guid))
        result.update(self.service.readOnlyProxiesForGUID(DirectoryService.recordType_locations, self.guid))
        return result

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
