##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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

import itertools
import sys
import os
from random import random

import opendirectory
import dsattributes
import dsquery

from twisted.internet.reactor import callLater
from twisted.internet.threads import deferToThread
from twisted.cred.credentials import UsernamePassword
from twisted.web2.auth.digest import DigestedCredentials

from twistedcaldav import logging
from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError

from plistlib import readPlistFromString, readPlist

serverPreferences = '/Library/Preferences/com.apple.servermgr_info.plist'
saclGroup = 'com.apple.access_calendar'

class OpenDirectoryService(DirectoryService):
    """
    Open Directory implementation of L{IDirectoryService}.
    """
    baseGUID = "891F8321-ED02-424C-BA72-89C32F215C1E"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.node)

    def __init__(self, node="/Search", requireComputerRecord=True, dosetup=True, cacheTimeout=30):
        """
        @param node: an OpenDirectory node name to bind to.
        @param requireComputerRecord: C{True} if the directory schema is to be used to determine
            which calendar users are enabled.
        @param dosetup: if C{True} then the directory records are initialized,
                        if C{False} they are not.
                        This should only be set to C{False} when doing unit tests.
        """
        try:
            directory = opendirectory.odInit(node)
        except opendirectory.ODError, e:
            logging.err("Open Directory (node=%s) Initialization error: %s" % (node, e), system="OpenDirectoryService")
            raise

        self.realmName = node
        self.directory = directory
        self.node = node
        self.requireComputerRecord = requireComputerRecord
        self.computerRecords = {}
        self.servicetags = set()
        self.cacheTimeout = cacheTimeout
        self._records = {}
        self._delayedCalls = set()

        self.isWorkgroupServer = False

        if dosetup:
            if self.requireComputerRecord:
                try:
                    self._lookupVHostRecord()
                except Exception, e:
                    logging.err("Unable to locate virtual host record: %s" % (e,), system="OpenDirectoryService")
                    raise

                if os.path.exists(serverPreferences):
                    serverInfo = readPlist(serverPreferences)

                    self.isWorkgroupServer = serverInfo.get('ServiceConfig', {}).get('IsWorkgroupServer', False)

                    if self.isWorkgroupServer:
                        logging.info("Enabling Workgroup Server compatibility mode", system="OpenDirectoryService")

            for recordType in self.recordTypes():
                self.recordsForType(recordType)

    def _expandGroupMembership(self, members, nestedGroups, processedGUIDs=None):

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
                logging.err(
                    "Couldn't find group %s when trying to expand nested groups."
                    % (groupGUID,), system="OpenDirectoryService"
                )
                continue

            group = result[0][1]

            processedGUIDs.add(groupGUID)

            for GUID in self._expandGroupMembership(
                group.get(dsattributes.kDSNAttrGroupMembers, []),
                group.get(dsattributes.kDSNAttrNestedGroups, []),
                processedGUIDs
            ):
                yield GUID

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

    def _lookupVHostRecord(self):
        """
        Get the OD service record for this host.
        """

        # The server must have been configured with a virtual hostname.
        vhostname = config.ServerHostName
        if not vhostname:
            raise OpenDirectoryInitError(
                "There is no virtual hostname configured for the server for use with Open Directory (node=%s)"
                % (self.realmName,)
            )
         
        # Find a record in /Computers with an apple-serviceinfo attribute value equal to the virtual hostname
        # and return some useful attributes.
        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
            dsattributes.kDSNAttrRecordName,
            dsattributes.kDSNAttrMetaNodeLocation,
            "dsAttrTypeNative:apple-serviceinfo",
        ]

        records = opendirectory.queryRecordsWithAttributes_list(
            self.directory,
            dsquery.match(
                "dsAttrTypeNative:apple-serviceinfo",
                vhostname,
                dsattributes.eDSContains,
            ).generate(),
            True,    # case insentive for hostnames
            dsattributes.kDSStdRecordTypeComputers,
            attrs
        )
        self._parseComputersRecords(records, vhostname)

    def _parseComputersRecords(self, records, vhostname):
        # Must have some results
        if len(records) == 0:
            raise OpenDirectoryInitError(
                "Open Directory (node=%s) has no /Computers records with a virtual hostname: %s"
                % (self.realmName, vhostname)
            )

        # Now find all appropriate records and determine the enabled (only) service tags for each.
        for recordname, record in records:
            self._parseServiceInfo(vhostname, recordname, record)

        # Log all the matching records
        for key, value in self.computerRecords.iteritems():
            _ignore_recordname, enabled, servicetag = value
            logging.info("Matched Directory record: %s with ServicesLocator: %s, state: %s" % (
                key,
                servicetag,
                {True:"enabled", False:"disabled"}[enabled]
            ), system="OpenDirectoryService")

        # Log all the enabled service tags - or generate an error if there are none
        if self.servicetags:
            for tag in self.servicetags:
                logging.info("Enabled ServicesLocator: %s" % (tag,), system="OpenDirectoryService")
        else:
            raise OpenDirectoryInitError(
                "Open Directory (node=%s) no /Computers records with an enabled and valid "
                "calendar service were found matching virtual hostname: %s"
                % (self.realmName, vhostname)
            )

    def _parseServiceInfo(self, vhostname, recordname, record):

        # Extract some useful attributes
        recordguid = record[dsattributes.kDS1AttrGeneratedUID]
        recordlocation = "%s/Computers/%s" % (record[dsattributes.kDSNAttrMetaNodeLocation], recordname)

        # First check for apple-serviceinfo attribute
        plist = record.get("dsAttrTypeNative:apple-serviceinfo", None)
        if not plist:
            return False

        # Parse the plist and look for our special entry
        plist = readPlistFromString(plist)
        vhosts = plist.get("com.apple.macosxserver.virtualhosts", None)
        if not vhosts:
            logging.err(
                "Open Directory (node=%s) %s record does not have a "
                "com.apple.macosxserver.virtualhosts in its apple-serviceinfo attribute value"
                % (self.realmName, recordlocation), system="OpenDirectoryService"
            )
            return False
        
        # Iterate over each vhost and find one that is a calendar service
        hostguid = None
        for key, value in vhosts.iteritems():
            serviceTypes = value.get("serviceType", None)
            if serviceTypes:
                for type in serviceTypes:
                    if type == "calendar":
                        hostguid = key
                        break
                    
        if not hostguid:
            # We can get false positives from the query - we ignore those.
            return False
            
        # Get host name
        hostname = vhosts[hostguid].get("hostname", None)
        if not hostname:
            logging.err(
                "Open Directory (node=%s) %s record does not have "
                "any host name in its apple-serviceinfo attribute value"
                % (self.realmName, recordlocation, ), system="OpenDirectoryService"
            )
            return False
        if hostname != vhostname:
            # We can get false positives from the query - we ignore those.
            return False
        
        # Get host details. At this point we only check that it is present. We actually
        # ignore the details themselves (scheme/port) as we use our own config for that.
        hostdetails = vhosts[hostguid].get("hostDetails", None)
        if not hostdetails:
            logging.err(
                "Open Directory (node=%s) %s record does not have "
                "any host details in its apple-serviceinfo attribute value"
                % (self.realmName, recordlocation, ), system="OpenDirectoryService"
            )
            return False
        
        # Look at the service data
        serviceInfos = vhosts[hostguid].get("serviceInfo", None)
        if not serviceInfos or not serviceInfos.has_key("calendar"):
            logging.err(
                "Open Directory (node=%s) %s record does not have a "
                "calendar service in its apple-serviceinfo attribute value"
                % (self.realmName, recordlocation), system="OpenDirectoryService"
            )
            return False
        serviceInfo = serviceInfos["calendar"]
        
        # Check that this service is enabled
        enabled = serviceInfo.get("enabled", True)

        # Create the string we will use to match users with accounts on this server
        servicetag = "%s:%s:calendar" % (recordguid, hostguid)
        
        self.computerRecords[recordlocation] = (recordname, enabled, servicetag)
        
        if enabled:
            self.servicetags.add(servicetag)
        
        return True
    
    def _calendarUserAddresses(self, recordType, recordName, record):
        """
        Extract specific attributes from the directory record for use as calendar user address.
        
        @param recordName: a C{str} containing the record name being operated on.
        @param record: a C{dict} containing the attributes retrieved from the directory.
        @return: a C{set} of C{str} for each expanded calendar user address.
        """
        # Now get the addresses
        result = set()
        
        # Add each email address as a mailto URI
        emails = record.get(dsattributes.kDSNAttrEMailAddress)
        if emails is not None:
            if isinstance(emails, str):
                emails = [emails]
            for email in emails:
                result.add("mailto:%s" % (email,))
                
        return result

    def _parseResourceInfo(self, plist, guid, shortname):
        """
        Parse OD ResourceInfo attribute and extract information that the server needs.

        @param plist: the plist that is the attribute value.
        @type plist: str
        @param guid: the directory GUID of the record being parsed.
        @type guid: str
        @param shortname: the record shortname of the record being parsed.
        @type shortname: str
        @return: a C{tuple} of C{bool} for auto-accept and C{str} for proxy GUID.
        """
        try:
            plist = readPlistFromString(plist)
            wpframework = plist.get("com.apple.WhitePagesFramework", {})
            autoaccept = wpframework.get("AutoAcceptsInvitation", False)
            proxy = wpframework.get("CalendaringDelegate")
        except AttributeError:
            logging.err(
                "Failed to parse ResourceInfo attribute of record %s (%s): %s" %
                (shortname, guid, plist,)
            )
            autoaccept = False
            proxy = None

        return (autoaccept, proxy)

    def recordTypes(self):
        return (
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources,
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
                    logging.err(
                        "Unable to load records of type %s from OpenDirectory due to unexpected error: %s"
                        % (recordType, f), system="OpenDirectoryService"
                    )

                d = deferToThread(self.reloadCache, recordType)
                d.addErrback(onError)

        return storage

    def recordsForType(self, recordType):
        """
        @param recordType: a record type
        @return: a dictionary containing all records for the given record
        type.  Keys are short names and values are the cooresponding
        OpenDirectoryRecord for the given record type.
        """
        return self._storage(recordType)["records"]

    def listRecords(self, recordType):
        return self.recordsForType(recordType).itervalues()

    def recordWithShortName(self, recordType, shortName):
        try:
            return self.recordsForType(recordType)[shortName]
        except KeyError:
            # Cache miss; try looking the record up, in case it is new
            # FIXME: This is a blocking call (hopefully it's a fast one)
            self.reloadCache(recordType, shortName=shortName)
            return self.recordsForType(recordType).get(shortName, None)

    def recordWithGUID(self, guid):
        def lookup():
            for recordType in self.recordTypes():
                record = self._storage(recordType)["guids"].get(guid, None)
                if record:
                    return record
            else:
                return None

        record = lookup()

        if record is None:
            # Cache miss; try looking the record up, in case it is new
            for recordType in self.recordTypes():
                self.reloadCache(recordType, guid=guid)
                record = lookup()
                if record is not None:
                    logging.info("Faulted record with GUID %s into %s record cache" % (guid, recordType), system="OpenDirectoryService")
                    break
            else:
                logging.info("Unable to find any record with GUID %s" % (guid,), system="OpenDirectoryService")

        return record

    def reloadCache(self, recordType, shortName=None, guid=None):
        if shortName:
            logging.info("Faulting record %s into %s record cache" % (shortName, recordType), system="OpenDirectoryService")
        elif guid is None:
            logging.info("Reloading %s record cache" % (recordType,), system="OpenDirectoryService")

        results = self._queryDirectory(recordType, shortName=shortName, guid=guid)
        
        if shortName is None and guid is None:
            records = {}
            guids   = {}

            disabledNames = set()
            disabledGUIDs = set()
        else:
            storage = self._records[recordType]

            records = storage["records"]
            guids   = storage["guids"]

            disabledNames = storage["disabled names"]
            disabledGUIDs = storage["disabled guids"]

        for (recordShortName, value) in results:
            enabledForCalendaring = True

            if self.requireComputerRecord:
                servicesLocators = value.get(dsattributes.kDSNAttrServicesLocator)

                def allowForACLs():
                    return recordType in (
                        DirectoryService.recordType_users,
                        DirectoryService.recordType_groups,
                    )

                def disableForCalendaring():
                    logging.debug(
                        "Record (%s) %s is not enabled for calendaring but may be used in ACLs"
                        % (recordType, recordShortName), system="OpenDirectoryService"
                    )

                def invalidRecord():
                    logging.err(
                        "Directory (incorrectly) returned a record with no applicable "
                        "ServicesLocator attribute: (%s) %s"
                        % (recordType, recordShortName), system="OpenDirectoryService"
                    )

                if servicesLocators:
                    if type(servicesLocators) is str:
                        servicesLocators = (servicesLocators,)

                    for locator in servicesLocators:
                        if locator in self.servicetags:
                            break
                    else:
                        if allowForACLs():
                            disableForCalendaring()
                            enabledForCalendaring = False
                        else:
                            invalidRecord()
                            continue
                else:
                    if allowForACLs():
                        disableForCalendaring()
                        enabledForCalendaring = False
                    else:
                        invalidRecord()
                        continue

            # Now get useful record info.
            recordGUID     = value.get(dsattributes.kDS1AttrGeneratedUID)
            recordFullName = value.get(dsattributes.kDS1AttrDistinguishedName)
            recordNodeName = value.get(dsattributes.kDSNAttrMetaNodeLocation)

            if not recordGUID:
                logging.debug("Record (%s)%s in node %s has no GUID; ignoring." % (recordType, recordShortName, recordNodeName),
                              system="OpenDirectoryService")
                continue

            # Get calendar user addresses from directory record.
            if enabledForCalendaring:
                calendarUserAddresses = self._calendarUserAddresses(recordType, recordShortName, value)
            else:
                calendarUserAddresses = ()

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
            if recordType in (DirectoryService.recordType_resources, DirectoryService.recordType_locations):
                resourceInfo = value.get(dsattributes.kDSNAttrResourceInfo)
                if resourceInfo is not None:
                    autoSchedule, proxy = self._parseResourceInfo(resourceInfo, recordGUID, recordShortName)
                    if proxy:
                        proxyGUIDs = (proxy,)

            record = OpenDirectoryRecord(
                service               = self,
                recordType            = recordType,
                guid                  = recordGUID,
                nodeName              = recordNodeName,
                shortName             = recordShortName,
                fullName              = recordFullName,
                calendarUserAddresses = calendarUserAddresses,
                autoSchedule          = autoSchedule,
                enabledForCalendaring = enabledForCalendaring,
                memberGUIDs           = memberGUIDs,
                proxyGUIDs            = proxyGUIDs,
            )

            def disableRecord(record):
                logging.warn("Record disabled due to conflict: %s" % (record,), system="OpenDirectoryService")

                shortName = record.shortName
                guid      = record.guid

                disabledNames.add(shortName)
                disabledGUIDs.add(guid)

                if shortName in records:
                    del records[shortName]
                if guid in guids:
                    del guids[guid]

            # Check for disabled items
            if record.shortName in disabledNames or record.guid in disabledGUIDs:
                disableRecord(record)
            else:
                # Check for duplicate items and disable all names/guids for mismatched duplicates.
                if record.shortName in records:
                    existing_record = records[record.shortName]
                elif record.guid in guids:
                    existing_record = guids[record.guid]
                else:
                    existing_record = None

                if existing_record is not None:
                    if record.guid != existing_record.guid or record.shortName != existing_record.shortName:
                        disableRecord(existing_record)
                        disableRecord(record)

                if record.shortName not in disabledNames:
                    records[record.shortName] = guids[record.guid] = record
                    logging.debug("Added record %s to OD record cache" % (record,), system="OpenDirectoryService")

        if shortName is None and guid is None:
            #
            # Replace the entire cache
            #
            storage = {
                "status"        : "new",
                "records"       : records,
                "guids"         : guids,
                "disabled names": disabledNames,
                "disabled guids": disabledGUIDs,
            }

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

            logging.info(
                "Added %d records to %s OD record cache; expires in %d seconds"
                % (len(self._records[recordType]["guids"]), recordType, cacheTimeout),
                system="OpenDirectoryService"
            )

    def _queryDirectory(self, recordType, shortName=None, guid=None):
        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
            dsattributes.kDS1AttrDistinguishedName,
            dsattributes.kDSNAttrEMailAddress,
            dsattributes.kDSNAttrServicesLocator,
            dsattributes.kDSNAttrMetaNodeLocation,
        ]

        query = None
        if recordType == DirectoryService.recordType_users:
            listRecordType = dsattributes.kDSStdRecordTypeUsers

        elif recordType == DirectoryService.recordType_groups:
            listRecordType = dsattributes.kDSStdRecordTypeGroups
            attrs.append(dsattributes.kDSNAttrGroupMembers)
            attrs.append(dsattributes.kDSNAttrNestedGroups)

        elif recordType == DirectoryService.recordType_locations:
            listRecordType = dsattributes.kDSStdRecordTypePlaces
            attrs.append(dsattributes.kDSNAttrResourceInfo)
        
        elif recordType == DirectoryService.recordType_resources:
            listRecordType = dsattributes.kDSStdRecordTypeResources
            attrs.append(dsattributes.kDSNAttrResourceInfo)
        
        else:
            raise UnknownRecordTypeError("Unknown Open Directory record type: %s" % (recordType))

        if self.requireComputerRecord:
            if self.isWorkgroupServer and recordType == DirectoryService.recordType_users:
                if shortName is None and guid is None:
                    results = opendirectory.queryRecordsWithAttribute_list(
                        self.directory,
                        dsattributes.kDSNAttrRecordName,
                        saclGroup,
                        dsattributes.eDSExact,
                        False,
                        dsattributes.kDSStdRecordTypeGroups,
                        [dsattributes.kDSNAttrGroupMembers, dsattributes.kDSNAttrNestedGroups]
                    )

                    if len(results) == 1:
                        members      = results[0][1].get(dsattributes.kDSNAttrGroupMembers, [])
                        nestedGroups = results[0][1].get(dsattributes.kDSNAttrNestedGroups, [])
                    else:
                        members = []
                        nestedGroups = []

                    guidQueries = []

                    for GUID in self._expandGroupMembership(members, nestedGroups):
                        guidQueries.append(
                            dsquery.match(dsattributes.kDS1AttrGeneratedUID, GUID, dsattributes.eDSExact)
                        )

                    if not guidQueries:
                        logging.warn("No SACL enabled users found.", system="OpenDirectoryService")
                        return ()

                    query = dsquery.expression(dsquery.expression.OR, guidQueries)

            #
            # For users and groups, we'll load all entries, even if
            # they don't have a services locator for this server.
            #
            elif (
                recordType != DirectoryService.recordType_users and
                recordType != DirectoryService.recordType_groups
            ):
                tag_queries = []

                for tag in self.servicetags:
                    tag_queries.append(dsquery.match(dsattributes.kDSNAttrServicesLocator, tag, dsattributes.eDSExact))

                if len(tag_queries) == 1:
                    subquery = tag_queries[0]
                else:
                    subquery = dsquery.expression(dsquery.expression.OR, tag_queries)

                if query is None:
                    query = subquery
                else:
                    query = dsquery.expression(dsquery.expression.AND, (subquery, query))

        if shortName is not None:
            subquery = dsquery.match(dsattributes.kDSNAttrRecordName, shortName, dsattributes.eDSExact)
        elif guid is not None:
            subquery = dsquery.match(dsattributes.kDS1AttrGeneratedUID, guid, dsattributes.eDSExact)
        else:
            subquery = None

        if subquery is not None:
            if query is None:
                query = subquery
            else:
                query = dsquery.expression(dsquery.expression.AND, (subquery, query))

        try:
            if query:
                if isinstance(query, dsquery.match):
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
                    results = opendirectory.queryRecordsWithAttributes_list(
                        self.directory,
                        query.generate(),
                        False,
                        listRecordType,
                        attrs,
                    )
            else:
                results = opendirectory.listAllRecordsWithAttributes_list(
                    self.directory,
                    listRecordType,
                    attrs,
                )
        except opendirectory.ODError, ex:
            logging.err("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)), system="OpenDirectoryService")
            raise

        return results

class OpenDirectoryRecord(DirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def __init__(
        self, service, recordType, guid, nodeName, shortName, fullName,
        calendarUserAddresses, autoSchedule, enabledForCalendaring,
        memberGUIDs, proxyGUIDs,
    ):
        super(OpenDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = guid,
            shortName             = shortName,
            fullName              = fullName,
            calendarUserAddresses = calendarUserAddresses,
            autoSchedule          = autoSchedule,
            enabledForCalendaring = enabledForCalendaring,
        )
        self.nodeName = nodeName
        self._memberGUIDs = tuple(memberGUIDs)
        self._proxyGUIDs = tuple(proxyGUIDs)

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
            self.shortName,
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
        for groupRecord in self.service.recordsForType(DirectoryService.recordType_groups).itervalues():
            if self.guid in groupRecord._memberGUIDs:
                yield groupRecord

    def proxies(self):
        if self.recordType not in (DirectoryService.recordType_resources, DirectoryService.recordType_locations):
            return

        for guid in self._proxyGUIDs:
            proxyRecord = self.service.recordWithGUID(guid)
            if proxyRecord is None:
                logging.err("No record for proxy in %s with GUID %s" % (self.shortName, guid), system="OpenDirectoryService")
            else:
                yield proxyRecord

    def proxyFor(self):
        for proxyRecord in itertools.chain(
            self.service.recordsForType(DirectoryService.recordType_resources).itervalues(),
            self.service.recordsForType(DirectoryService.recordType_locations).itervalues(),
        ):
            if self.guid in proxyRecord._proxyGUIDs:
                yield proxyRecord

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
                if opendirectory.authenticateUserBasic(self.service.directory, self.nodeName, self.shortName, credentials.password):
                    # Cache the password to avoid future DS queries
                    self.password = credentials.password
                    return True
            except opendirectory.ODError, e:
                logging.err("Open Directory (node=%s) error while performing basic authentication for user %s: %s"
                            % (self.service.realmName, self.shortName, e), system="OpenDirectoryService")

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
                logging.err(
                    "Open Directory (node=%s) error while performing digest authentication for user %s: "
                    "missing digest response field: %s in: %s"
                    % (self.service.realmName, self.shortName, e, credentials.fields),
                    system="OpenDirectoryService"
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
                    self.shortName,
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
            except opendirectory.ODError, e:
                logging.err(
                    "Open Directory (node=%s) error while performing digest authentication for user %s: %s"
                    % (self.service.realmName, self.shortName, e), system="OpenDirectoryService"
                )
                return False

            return False

        return super(OpenDirectoryRecord, self).verifyCredentials(credentials)

class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
