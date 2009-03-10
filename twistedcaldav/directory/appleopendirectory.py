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
from random import random
from uuid import UUID

from twext.python.plistlib import readPlistFromString

from xml.parsers.expat import ExpatError

import opendirectory
import dsattributes
import dsquery

from twisted.internet.reactor import callLater
from twisted.internet.threads import deferToThread
from twisted.cred.credentials import UsernamePassword
from twisted.web2.auth.digest import DigestedCredentials

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError

class OpenDirectoryService(DirectoryService):
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

        if dosetup:
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
            self.recordType_users,
            self.recordType_groups,
            self.recordType_locations,
            self.recordType_resources,
        )

    def _storage(self, recordType):
        try:
            storage = self._records[recordType]
        except KeyError:
            self.reloadCache(recordType)
            storage = self._records[recordType]
        else:
            if storage["status"] == "stale":
                storage["status"] = "loading"

                def onError(f):
                    storage["status"] = "stale" # Keep trying
                    self.log_error(
                        "Unable to load records of type %s from OpenDirectory due to unexpected error: %s"
                        % (recordType, f)
                    )

                # Reload the restricted access group details if reloading user records
                if recordType == self.recordType_users:
                    self.restrictedGUIDs = None

                d = deferToThread(self.reloadCache, recordType)
                d.addErrback(onError)

        return storage

    def recordsForType(self, recordType):
        """
        @param recordType: a record type
        @return: a dictionary containing all records for the given record
        type.  Keys are short names and values are the corresponding
        OpenDirectoryRecord for the given record type.
        """
        return self._storage(recordType)["records"]

    def listRecords(self, recordType):
        return self.recordsForType(recordType).itervalues()

    def recordWithShortName(self, recordType, shortName):
        try:
            return self.recordsForType(recordType)[shortName]
        except KeyError:
            # Check negative cache
            if shortName in self._storage(recordType)["disabled names"]:
                return None

            # Cache miss; try looking the record up, in case it is new
            # FIXME: This is a blocking call (hopefully it's a fast one)
            self.reloadCache(recordType, lookup=("shortName", shortName,))
            record = self.recordsForType(recordType).get(shortName, None)
            if record is None:
                # Add to negative cache
                self._storage(recordType)["disabled names"].add(shortName)
            return record

    def recordWithEmailAddress(self, emailAddress):
        return self._recordWithAttribute("emails", "disabled emails", "email", emailAddress)

    def recordWithGUID(self, guid):
        return self._recordWithAttribute("guids", "disabled guids", "guid", guid)

    recordWithUID = recordWithGUID

    def recordWithAuthID(self, authID):
        return self._recordWithAttribute("authIDs", "disabled authIDs", "authID", authID)

    def _recordWithAttribute(self, cacheKey, disabledKey, lookupKey, value):
        def lookup():
            for recordType in self.recordTypes():
                record = self._storage(recordType)[cacheKey].get(value, None)
                if record:
                    return record
            else:
                return None

        record = lookup()

        if record is None:
            # Cache miss; try looking the record up, in case it is new
            for recordType in self.recordTypes():
                # Check negative cache
                if value in self._storage(recordType)[disabledKey]:
                    continue

                try:
                    self.reloadCache(recordType, lookup=(lookupKey, value,))
                    record = lookup()
                except opendirectory.ODError, e:
                    if e.message[1] == -14140 or e.message[1] == -14200:
                        # Unsupported attribute on record - don't fail
                        record = None
                    else:
                        raise

                if record is None:
                    self._storage(recordType)[disabledKey].add(value)
                else:
                    self.log_info("Faulted record with %s %s into %s record cache"
                                  % (lookupKey, value, recordType))
                    break
            else:
                # Nothing found; add to negative cache
                self.log_info("Unable to find any record with %s %s" % (lookupKey, value,))

        return record

    def groupsForGUID(self, guid):
        
        # Lookup in index
        try:
            return self._storage(self.recordType_groups)["groupsForGUID"][guid]
        except KeyError:
            return ()

    def proxiesForGUID(self, recordType, guid):
        
        # Lookup in index
        try:
            return self._storage(recordType)["proxiesForGUID"][guid]
        except KeyError:
            return ()

    def readOnlyProxiesForGUID(self, recordType, guid):
        
        # Lookup in index
        try:
            return self._storage(recordType)["readOnlyProxiesForGUID"][guid]
        except KeyError:
            return ()

    def _indexGroup(self, group, guids, index):
        for guid in guids:
            index.setdefault(guid, set()).add(group)

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

        _ODTypes = {
            self.recordType_users:     dsattributes.kDSStdRecordTypeUsers,
            self.recordType_locations: dsattributes.kDSStdRecordTypePlaces,
            self.recordType_groups:    dsattributes.kDSStdRecordTypeGroups,
            self.recordType_resources: dsattributes.kDSStdRecordTypeResources,
        }

        if recordType is None:
            # The client is looking for records in any of the four types
            recordTypes = set(_ODTypes.values())

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
            recordTypes = [_ODTypes[recordType]]

        expressions = []
        for field, value, caseless, matchType in fields:
            if field in self._ODFields:

                if (excludeFields and
                    _ODTypes[recordType] in self._ODFields[field]['excludes']):
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


    def reloadCache(self, recordType, lookup=None):
        if lookup is not None:
            self.log_info("Faulting record with %s %s into %s record cache" % (lookup[0], lookup[1], recordType))
        else:
            self.log_info("Reloading %s record cache" % (recordType,))

        results = self._queryDirectory(recordType, lookup=lookup)

        if lookup is None:
            records = {}
            guids   = {}
            authIDs = {}
            emails  = {}

            disabledNames   = set()
            disabledGUIDs   = set()
            disabledAuthIDs = set()
            disabledEmails  = set()
            
            if recordType == self.recordType_groups:
                groupsForGUID = {}
            elif recordType in (self.recordType_resources, self.recordType_locations):
                proxiesForGUID = {}
                readOnlyProxiesForGUID = {}
        else:
            storage = self._records[recordType]

            records = storage["records"]
            guids   = storage["guids"]
            authIDs = storage["authIDs"]
            emails  = storage["emails"]

            disabledNames   = storage["disabled names"]
            disabledGUIDs   = storage["disabled guids"]
            disabledAuthIDs = storage["disabled authIDs"]
            disabledEmails  = storage["disabled emails"]
            
            if recordType == self.recordType_groups:
                groupsForGUID = storage["groupsForGUID"]
            elif recordType in (self.recordType_resources, self.recordType_locations):
                proxiesForGUID = storage["proxiesForGUID"]
                readOnlyProxiesForGUID = storage["readOnlyProxiesForGUID"]

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
            
        for (recordShortName, value) in results:

            # Now get useful record info.
            recordGUID           = value.get(dsattributes.kDS1AttrGeneratedUID)
            recordShortNames     = _uniqueTupleFromAttribute(value.get(dsattributes.kDSNAttrRecordName))
            recordAuthIDs        = _setFromAttribute(value.get(dsattributes.kDSNAttrAltSecurityIdentities))
            recordFullName       = value.get(dsattributes.kDS1AttrDistinguishedName)
            recordFirstName      = value.get(dsattributes.kDS1AttrFirstName)
            recordLastName       = value.get(dsattributes.kDS1AttrLastName)
            recordEmailAddresses = _setFromAttribute(value.get(dsattributes.kDSNAttrEMailAddress), lower=True)
            recordNodeName       = value.get(dsattributes.kDSNAttrMetaNodeLocation)

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
                if self.restrictEnabledRecords and self.restrictedGUIDs is not None:
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

            # Special case for resources and locations
            autoSchedule = False
            proxyGUIDs = ()
            readOnlyProxyGUIDs = ()
            if recordType in (self.recordType_resources, self.recordType_locations):
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
                authIDs               = recordAuthIDs,
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

            def disableGUID(guid, record):
                """
                Disable the record by removing it from all indexes.
                """

                self.log_warn("GUID %s disabled due to conflict for record: %s"
                              % (guid, record))

                disabledGUIDs.add(guid)
                disabledNames.update(record.shortNames)
                disabledAuthIDs.update(record.authIDs)
                disabledEmails.update(record.emailAddresses)

                if guid in guids:
                    try:
                        del guids[guid]
                    except KeyError:
                        pass
                for shortName in record.shortNames:
                    try:
                        del records[shortName]
                    except KeyError:
                        pass
                for authID in record.authIDs:
                    try:
                        del authIDs[authID]
                    except KeyError:
                        pass
                for email in record.emailAddresses:
                    try:
                        del emails[email]
                    except KeyError:
                        pass

            if record.guid in disabledGUIDs:
                disableGUID(record.guid, record)
            else:
                # Check for duplicates
                existing_record = guids.get(record.guid)
                if existing_record is not None:
                    if existing_record.shortNames != record.shortNames:
                        disableGUID(record.guid, record)
                        disableGUID(record.guid, existing_record)
                        if existing_record.enabledForCalendaring:
                            enabled_count -= 1
                else:
                    guids[record.guid] = record
                    self.log_debug("Added record %s to OD record cache" % (record,))
                    if record.enabledForCalendaring:
                        enabled_count += 1
        
                    # Do group indexing if needed
                    if recordType == self.recordType_groups:
                        self._indexGroup(record, record._memberGUIDs, groupsForGUID)

                    # Do proxy indexing if needed
                    elif recordType in (self.recordType_resources, self.recordType_locations):
                        self._indexGroup(record, record._proxyGUIDs, proxiesForGUID)
                        self._indexGroup(record, record._readOnlyProxyGUIDs, readOnlyProxiesForGUID)

                    # Index non-duplicate shortNames
                    def disableName(shortName, record):
                        self.log_warn("Short name %s disabled due to conflict for record: %s"
                                      % (shortName, record))
        
                        record.shortNames = tuple([item for item in record.shortNames if item != shortName])
                        disabledNames.add(shortName)
        
                        if shortName in records:
                            del records[shortName]
        
                    for shortName in tuple(record.shortNames):
                        if shortName in disabledNames:
                            disableName(shortName, record)
                        else:
                            # Check for duplicates
                            existing_record = records.get(shortName)
                            if existing_record is not None and existing_record != record:
                                disableName(shortName, record)
                                disableName(shortName, existing_record)
                            else:
                                records[shortName] = record
        
                    # Index non-duplicate authIDs
                    def disableAuthIDs(authID, record):
                        self.log_warn("Auth ID %s disabled due to conflict for record: %s"
                                      % (authID, record))
        
                        record.authIDs.remove(authID)
                        disabledAuthIDs.add(authID)
        
                        if authID in authIDs:
                            del authIDs[authID]
        
                    for authID in frozenset(recordAuthIDs):
                        if authID in disabledAuthIDs:
                            disableAuthIDs(authID, record)
                        else:
                            # Check for duplicates
                            existing_record = authIDs.get(authID)
                            if existing_record is not None:
                                disableAuthIDs(authID, record)
                                disableAuthIDs(authID, existing_record)
                            else:
                                authIDs[authID] = record
        
                    # Index non-duplicate emails
                    def disableEmail(emailAddress, record):
                        self.log_warn("Email address %s disabled due to conflict for record: %s"
                                      % (emailAddress, record))
        
                        record.emailAddresses.remove(emailAddress)
                        disabledEmails.add(emailAddress)
        
                        if emailAddress in emails:
                            del emails[emailAddress]
        
                    for email in frozenset(recordEmailAddresses):
                        if email in disabledEmails:
                            disableEmail(email, record)
                        else:
                            # Check for duplicates
                            existing_record = emails.get(email)
                            if existing_record is not None:
                                disableEmail(email, record)
                                disableEmail(email, existing_record)
                            else:
                                emails[email] = record

        if lookup is None:
            #
            # Replace the entire cache
            #
            storage = {
                "status"           : "new",
                "records"          : records,
                "guids"            : guids,
                "authIDs"          : authIDs,
                "emails"           : emails,
                "disabled names"   : disabledNames,
                "disabled guids"   : disabledGUIDs,
                "disabled authIDs" : disabledAuthIDs,
                "disabled emails"  : disabledEmails,
            }

            # Add group indexing if needed
            if recordType == self.recordType_groups:
                storage["groupsForGUID"] = groupsForGUID

            # Add proxy indexing if needed
            elif recordType in (self.recordType_resources, self.recordType_locations):
                storage["proxiesForGUID"] = proxiesForGUID
                storage["readOnlyProxiesForGUID"] = readOnlyProxiesForGUID

            def rot():
                storage["status"] = "stale"
                removals = set()
                for call in self._delayedCalls:
                    if not call.active():
                        removals.add(call)
                for item in removals:
                    self._delayedCalls.remove(item)

            #
            # Add jitter/fuzz factor to avoid stampede for large OD query
            # Max out the jitter at 60 minutes
            #
            cacheTimeout = min(self.cacheTimeout, 60) * 60
            cacheTimeout = (cacheTimeout * random()) - (cacheTimeout / 2)
            cacheTimeout += self.cacheTimeout * 60
            self._delayedCalls.add(callLater(cacheTimeout, rot))

            self._records[recordType] = storage

            self.log_info(
                "Added %d (%d enabled) records to %s OD record cache; expires in %d seconds"
                % (len(self._records[recordType]["guids"]), enabled_count, recordType, cacheTimeout)
            )

    def _queryDirectory(self, recordType, lookup=None):
        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
            dsattributes.kDSNAttrRecordName,
            dsattributes.kDSNAttrAltSecurityIdentities,
            dsattributes.kDS1AttrDistinguishedName,
            dsattributes.kDS1AttrFirstName,
            dsattributes.kDS1AttrLastName,
            dsattributes.kDSNAttrEMailAddress,
            dsattributes.kDSNAttrMetaNodeLocation,
        ]

        if recordType == self.recordType_users:
            listRecordType = dsattributes.kDSStdRecordTypeUsers

        elif recordType == self.recordType_groups:
            listRecordType = dsattributes.kDSStdRecordTypeGroups
            attrs.append(dsattributes.kDSNAttrGroupMembers)
            attrs.append(dsattributes.kDSNAttrNestedGroups)

        elif recordType == self.recordType_locations:
            listRecordType = dsattributes.kDSStdRecordTypePlaces
            attrs.append(dsattributes.kDSNAttrResourceInfo)
        
        elif recordType == self.recordType_resources:
            listRecordType = dsattributes.kDSStdRecordTypeResources
            attrs.append(dsattributes.kDSNAttrResourceInfo)
        
        else:
            raise UnknownRecordTypeError("Unknown Open Directory record type: %s" % (recordType))

        # If restricting enabled records, then make sure the restricted group member
        # details are loaded. Do nested group expansion and include the nested groups
        # as enabled records too.
        if self.restrictEnabledRecords and self.restrictedGUIDs is None:

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
                members      = results[0][1].get(dsattributes.kDSNAttrGroupMembers, [])
                nestedGroups = results[0][1].get(dsattributes.kDSNAttrNestedGroups, [])
            else:
                members = []
                nestedGroups = []

            self.restrictedGUIDs = set(self._expandGroupMembership(members, nestedGroups, returnGroups=True))
            self.log_debug("Got %d restricted group members" % (len(self.restrictedGUIDs),))

        query = None
        if lookup is not None:
            queryattr = {
                "shortName" : dsattributes.kDSNAttrRecordName,
                "guid"      : dsattributes.kDS1AttrGeneratedUID,
                "authID"    : dsattributes.kDSNAttrAltSecurityIdentities,
                "email"     : dsattributes.kDSNAttrEMailAddress,
            }.get(lookup[0])
            assert queryattr is not None, "Invalid type for record faulting query"
            query = dsquery.match(queryattr, lookup[1], dsattributes.eDSExact)

        try:
            if query:
                self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
                    self.directory,
                    query.attribute,
                    query.value,
                    query.matchType,
                    False,
                    listRecordType,
                    attrs,
                ))
                results = opendirectory.queryRecordsWithAttribute_list(
                    self.directory,
                    query.attribute,
                    query.value,
                    query.matchType,
                    False,
                    listRecordType,
                    attrs,
                )
            else:
                self.log_debug("opendirectory.listAllRecordsWithAttributes_list(%r,%r,%r)" % (
                    self.directory,
                    listRecordType,
                    attrs,
                ))
                results = opendirectory.listAllRecordsWithAttributes_list(
                    self.directory,
                    listRecordType,
                    attrs,
                )
        except opendirectory.ODError, ex:
            self.log_error("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
            raise

        return results

class OpenDirectoryRecord(DirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def __init__(
        self, service, recordType, guid, nodeName, shortNames, authIDs, fullName,
        firstName, lastName, emailAddresses,
        calendarUserAddresses, autoSchedule, enabledForCalendaring,
        memberGUIDs, proxyGUIDs, readOnlyProxyGUIDs,
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
            autoSchedule          = autoSchedule,
            enabledForCalendaring = enabledForCalendaring,
        )
        self.nodeName = nodeName
        self._memberGUIDs = tuple(memberGUIDs)
        self._proxyGUIDs = tuple(proxyGUIDs)
        self._readOnlyProxyGUIDs = tuple(readOnlyProxyGUIDs)

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
        return self.service.groupsForGUID(self.guid)

    def proxies(self):
        if self.recordType not in (self.service.recordType_resources, self.service.recordType_locations):
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
        result.update(self.service.proxiesForGUID(self.service.recordType_resources, self.guid))
        result.update(self.service.proxiesForGUID(self.service.recordType_locations, self.guid))
        return result

    def readOnlyProxies(self):
        if self.recordType not in (self.service.recordType_resources, self.service.recordType_locations):
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
        result.update(self.service.readOnlyProxiesForGUID(self.service.recordType_resources, self.guid))
        result.update(self.service.readOnlyProxiesForGUID(self.service.recordType_locations, self.guid))
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
