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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
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

import opendirectory
import dsattributes
import dsquery

from twisted.python import log
from twisted.internet.reactor import callLater
from twisted.internet.threads import deferToThread
from twisted.cred.credentials import UsernamePassword
from twisted.web2.auth.digest import DigestedCredentials

from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.directory import DirectoryError, UnknownRecordTypeError

from plistlib import readPlistFromString

recordListCacheTimeout = 60 * 30 # 30 minutes

class OpenDirectoryService(DirectoryService):
    """
    Open Directory implementation of L{IDirectoryService}.
    """
    baseGUID = "891F8321-ED02-424C-BA72-89C32F215C1E"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.node)

    def __init__(self, node="/Search", requireComputerRecord=True, dosetup=True):
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
            log.msg("Open Directory (node=%s) Initialization error: %s" % (node, e))
            raise

        self.realmName = node
        self.directory = directory
        self.node = node
        self.requireComputerRecord = requireComputerRecord
        self.computerRecordName = ""
        self._records = {}
        self._delayedCalls = set()

        if dosetup:
            if self.requireComputerRecord:
                try:
                    self._lookupVHostRecord()
                except Exception, e:
                    log.err("Unable to locate virtual host record: %s" % (e,))
                    raise

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
         
        # Find a record in /Computers with an ENetAddress attribute value equal to the MAC address
        # and return some useful attributes.
        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
            dsattributes.kDSNAttrRecordName,
            dsattributes.kDS1AttrXMLPlist,
            dsattributes.kDSNAttrMetaNodeLocation,
            'dsAttrTypeNative:apple-serviceinfo',
        ]

        from dsquery import expression, match

        records = opendirectory.queryRecordsWithAttributes(
            self.directory,
            expression(
                expression.OR,
                (
                    match(dsattributes.kDS1AttrXMLPlist,
                          vhostname,
                          dsattributes.eDSContains),
                    match('dsAttrTypeNative:apple-serviceinfo',
                          vhostname,
                          dsattributes.eDSContains))).generate(),
            True,    # case insentive for hostnames
            dsattributes.kDSStdRecordTypeComputers,
            attrs
        )
        self._parseComputersRecords(records, vhostname)

    def _parseComputersRecords(self, records, vhostname):
        localNodePath = '/Local/Default'
        localODNodePath = '/LDAPv3/127.0.0.1'

        # Must have some results
        if len(records) == 0:
            raise OpenDirectoryInitError(
                "Open Directory (node=%s) has no /Computers records with a virtual hostname: %s"
                % (self.realmName, vhostname,)
            )

        # Now find a single record that actually matches the hostname
        # Prefering the remote OD node to the local OD Node and
        # the local OD Node to the local node.

        _localNode = None
        _localODNode = None
        _remoteNode = None

        for recordname, record in records.iteritems():
            # May have an apple-serviceinfo
            plist = record.get('dsAttrTypeNative:apple-serviceinfo', None)

            if not plist:
                # May have XMLPlist value
                plist = record.get(dsattributes.kDS1AttrXMLPlist, None)

                # Must have one of the other
                if not plist:
                    continue

            # XXX: Parse the plist so we can find only calendar vhosts with our hostname.
            plistDict = readPlistFromString(plist)
            vhosts = plistDict.get("com.apple.macosxserver.virtualhosts", None)
            if not vhosts:
                continue

            hostguid = None
            for key, value in vhosts.iteritems():
                serviceTypes = value.get("serviceType", None)
                if serviceTypes:
                    for type in serviceTypes:
                        if type == "calendar":
                            hostguid = key
                            break

            if vhosts[hostguid].get("hostname", None) != vhostname:
                continue

            if record[dsattributes.kDSNAttrMetaNodeLocation] == localNodePath:
                _localNode = (recordname, plist, record[dsattributes.kDS1AttrGeneratedUID])

            elif record[dsattributes.kDSNAttrMetaNodeLocation] == localODNodePath:
                _localODNode = (recordname, plist, record[dsattributes.kDS1AttrGeneratedUID])

            else:
                _remoteNode = (recordname, plist, record[dsattributes.kDS1AttrGeneratedUID])

        # XXX: These calls to self._parseXMLPlist will cause the plsit to be parsed _again_
        #      refactor later so we only ever parse it once.

        for node in (_remoteNode, _localODNode, _localNode):
            if node and self._parseXMLPlist(vhostname, *node):
                break

        else:
            raise OpenDirectoryInitError(
                "Open Directory (node=%s) no /Computers records with an enabled and valid "
                "calendar service were found matching virtual hostname: %s"
                % (self.realmName, vhostname,)
            )

    def _parseXMLPlist(self, vhostname, recordname, plist, recordguid):
        # Parse the plist and look for our special entry
        plist = readPlistFromString(plist)
        vhosts = plist.get("com.apple.macosxserver.virtualhosts", None)
        if not vhosts:
            log.msg(
                "Open Directory (node=%s) /Computers/%s record does not have a "
                "com.apple.macosxserver.virtualhosts in its XMLPlist attribute value"
                % (self.realmName, recordname)
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
            log.msg(
                "Open Directory (node=%s) /Computers/%s record does not have a "
                "calendar service in its XMLPlist attribute value"
                % (self.realmName, recordname)
            )
            return False
            
        # Get host name
        hostname = vhosts[hostguid].get("hostname", None)
        if not hostname:
            log.msg(
                "Open Directory (node=%s) /Computers/%s record does not have "
                "any host name in its XMLPlist attribute value"
                % (self.realmName, recordname)
            )
            return False
        if hostname != vhostname:
            log.msg(
                "Open Directory (node=%s) /Computers/%s record hostname (%s) "
                "does not match this server (%s)"
                % (self.realmName, recordname, hostname, vhostname)
            )
            return False
        
        # Get host details and create host templates
        hostdetails = vhosts[hostguid].get("hostDetails", None)
        if not hostdetails:
            log.msg(
                "Open Directory (node=%s) /Computers/%s record does not have "
                "any host details in its XMLPlist attribute value"
                % (self.realmName, recordname)
            )
            return False
        hostvariants = []
        for key, value in hostdetails.iteritems():
            if key in ("http", "https"):
                hostvariants.append((key, hostname, value["port"]))
        
        # Look at the service data
        serviceInfos = vhosts[hostguid].get("serviceInfo", None)
        if not serviceInfos or not serviceInfos.has_key("calendar"):
            log.msg(
                "Open Directory (node=%s) /Computers/%s record does not have a "
                "calendar service in its XMLPlist attribute value"
                % (self.realmName, recordname)
            )
            return False
        serviceInfo = serviceInfos["calendar"]
        
        # Check that this service is enabled
        enabled = serviceInfo.get("enabled", True)
        if not enabled:
            log.msg(
                "Open Directory (node=%s) /Computers/%s record does not have an "
                "enabled calendar service in its XMLPlist attribute value"
                % (self.realmName, recordname)
            )
            return False

        # Create the string we will use to match users with accounts on this server
        self.servicetag = "%s:%s:calendar" % (recordguid, hostguid)
        
        self.computerRecordName = recordname
        
        return True
    
    def _getCalendarUserAddresses(self, recordType, recordName, record):
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

    def _parseResourceInfo(self, plist):
        """
        Parse OD ResourceInfo attribute and extract information that the server needs.

        @param plist: the plist that is the attribute value.
        @type plist: str
        @return: a C{tuple} of C{bool} for auto-accept and C{str} for proxy GUID.
        """
        plist = readPlistFromString(plist)
        wpframework = plist.get("com.apple.WhitePagesFramework", {})
        autoaccept = wpframework.get("AutoAcceptsInvitation", False)
        proxy= wpframework.get("CalendaringDelegate")
        
        return (autoaccept, proxy,)

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
        else:
            if storage["status"] == "stale":
                storage["status"] = "loading"

                def onError(f):
                    storage["status"] = "stale" # Keep trying
                    log.err("Unable to load records of type %s from OpenDirectory due to unexpected error: %s"
                            % (recordType, f))

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
        self._storage(recordType)["records"]

    def listRecords(self, recordType):
        return self.recordsForType(recordType).itervalues()

    def recordWithShortName(self, recordType, shortName):
        try:
            return self.recordsForType(recordType)[shortName]
        except KeyError:
            # Cache miss; try looking the record up, in case it is new
            # FIXME: This is a blocking call (hopefully it's a fast one)
            self.reloadCache(recordType, shortName)
            return self.recordsForType(recordType).get(shortName, None)

    def recordWithGUID(self, guid):
        # Override super's implementation with something faster.
        return self._storage(recordType)["guids"].get(guid, None)

    def reloadCache(self, recordType, shortName=None):
        log.msg("Reloading %s record cache" % (recordType,))

        attrs = [
            dsattributes.kDS1AttrGeneratedUID,
            dsattributes.kDS1AttrDistinguishedName,
            dsattributes.kDSNAttrEMailAddress,
            dsattributes.kDSNAttrServicesLocator,
        ]

        query = None
        if recordType == DirectoryService.recordType_users:
            listRecordType = dsattributes.kDSStdRecordTypeUsers

        elif recordType == DirectoryService.recordType_groups:
            listRecordType = dsattributes.kDSStdRecordTypeGroups
            attrs.append(dsattributes.kDSNAttrGroupMembers)

        elif recordType == DirectoryService.recordType_locations:
            listRecordType = dsattributes.kDSStdRecordTypePlaces
            attrs.append(dsattributes.kDSNAttrResourceInfo)
        
        elif recordType == DirectoryService.recordType_resources:
            listRecordType = dsattributes.kDSStdRecordTypeResources
            attrs.append(dsattributes.kDSNAttrResourceInfo)
        
        else:
            raise UnknownRecordTypeError("Unknown Open Directory record type: %s"
                                         % (recordType,))

        if self.requireComputerRecord:
            subquery = dsquery.match(dsattributes.kDSNAttrServicesLocator, self.servicetag, dsattributes.eDSExact)
            if query is None:
                query = subquery
            else:
                query = dsquery.expression(dsquery.expression.AND, (subquery, query))
            
        if shortName is not None:
            subquery = dsquery.match(dsattributes.kDSNAttrRecordName, shortName, dsattributes.eDSExact)
            if query is None:
                query = subquery
            else:
                query = dsquery.expression(dsquery.expression.AND, (subquery, query))

        try:
            if query:
                if isinstance(query, dsquery.match):
                    results = opendirectory.queryRecordsWithAttribute(
                        self.directory,
                        query.attribute,
                        query.value,
                        query.matchType,
                        False,
                        listRecordType,
                        attrs,
                    )
                else:
                    results = opendirectory.queryRecordsWithAttributes(
                        self.directory,
                        query.generate(),
                        False,
                        listRecordType,
                        attrs,
                    )
            else:
                results = opendirectory.listAllRecordsWithAttributes(
                    self.directory,
                    listRecordType,
                    attrs,
                )
        except opendirectory.ODError, ex:
            log.msg("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
            raise

        records = {}
        guids   = {}

        for (key, value) in results.iteritems():
            if self.requireComputerRecord:
                services = value.get(dsattributes.kDSNAttrServicesLocator)

                if not services:
                    log.err("Directory (incorrectly) returned a record with no ServicesLocator attribute: %s" % (key,))
                    continue

            # Now get useful record info.
            recordShortName = key
            guid = value.get(dsattributes.kDS1AttrGeneratedUID)
            if not guid:
                continue
            realName = value.get(dsattributes.kDS1AttrDistinguishedName)

            # Get calendar user addresses from directory record.
            cuaddrset = self._getCalendarUserAddresses(recordType, key, value)

            # Special case for groups.
            if recordType == DirectoryService.recordType_groups:
                memberGUIDs = value.get(dsattributes.kDSNAttrGroupMembers)
                if memberGUIDs is None:
                    memberGUIDs = ()
                elif type(memberGUIDs) is str:
                    memberGUIDs = (memberGUIDs,)
            else:
                memberGUIDs = ()

            # Special case for resources and locations
            autoSchedule = False
            proxyGUIDs = ()
            if recordType in (DirectoryService.recordType_resources, DirectoryService.recordType_locations):
                resourceInfo = value.get(dsattributes.kDSNAttrResourceInfo)
                if resourceInfo is not None:
                    autoSchedule, proxy = self._parseResourceInfo(resourceInfo)
                    if proxy:
                        proxyGUIDs = (proxy,)

            record = OpenDirectoryRecord(
                service               = self,
                recordType            = recordType,
                guid                  = guid,
                shortName             = recordShortName,
                fullName              = realName,
                calendarUserAddresses = cuaddrset,
                memberGUIDs           = memberGUIDs,
                autoSchedule          = autoSchedule,
                proxyGUIDs            = proxyGUIDs,
            )
            records[recordShortName] = guids[guid] record

            #log.debug("Populated record: %s" % (records[recordShortName],))

        if shortName is None:
            #
            # Replace the entire cache
            #
            storage = {
                "status" : "new",
                "records": records,
                "guids"  : guids,
            }

            def rot():
                storage["status"] = "stale"
                removals = set()
                for call in self._delayedCalls:
                    if not call.active():
                        removals.add(call)
                for item in removals:
                    self._delayedCalls.remove(item)

            self._delayedCalls.add(callLater(recordListCacheTimeout, rot))

            self._records[recordType] = storage

        elif records:
            #
            # Update one record, if found
            #
            assert len(records) == 1, "shortName = %r, records = %r" % (shortName, len(records))
            storage = self._records[recordType]
            storage["records"][shortName] = records[recordShortName]
            storage["guids"][record.guid] = records[recordShortName]

class OpenDirectoryRecord(DirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, guid, shortName, fullName, calendarUserAddresses, memberGUIDs, autoSchedule, proxyGUIDs):
        super(OpenDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = guid,
            shortName             = shortName,
            fullName              = fullName,
            calendarUserAddresses = calendarUserAddresses,
            autoSchedule          = autoSchedule,
        )
        self._memberGUIDs = tuple(memberGUIDs)
        self._proxyGUIDs = tuple(proxyGUIDs)

    def members(self):
        if self.recordType != DirectoryService.recordType_groups:
            return

        for guid in self._memberGUIDs:
            userRecord = self.service.recordWithGUID(guid)
            if userRecord is None:
                log.err("No record for member of group %s with GUID %s" % (self.shortName, guid))
            else:
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
                log.err("No record for proxy in %s with GUID %s" % (self.shortName, guid))
            else:
                yield proxyRecord

    def proxyFor(self):
        for proxyRecord in itertools.chain(
                                  self.service.recordsForType(DirectoryService.recordType_resources).itervalues(),
                                  self.service.recordsForType(DirectoryService.recordType_locations).itervalues()
                              ):
            if self.guid in proxyRecord._proxyGUIDs:
                yield proxyRecord

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            try:
                return opendirectory.authenticateUserBasic(self.service.directory, self.guid, self.shortName, credentials.password)
            except opendirectory.ODError, e:
                log.err("Open Directory (node=%s) error while performing basic authentication for user %s: %s"
                        % (self.service.realmName, self.shortName, e))
                return False
        elif isinstance(credentials, DigestedCredentials):
            try:
                # We need a special format for the "challenge" and "response" strings passed into open directory, as it is
                # picky about exactly what it receives.
                
                try:
                    challenge = 'Digest realm="%(realm)s", nonce="%(nonce)s", algorithm=%(algorithm)s' % credentials.fields
                    response = ('Digest username="%(username)s", '
                                'realm="%(realm)s", '
                                'nonce="%(nonce)s", '
                                'uri="%(uri)s", '
                                'response="%(response)s",'
                                'algorithm=%(algorithm)s') % credentials.fields
                except KeyError, e:
                    log.err("Open Directory (node=%s) error while performing digest authentication for user %s: missing digest response field: %s in: %s"
                            % (self.service.realmName, self.shortName, e, credentials.fields))
                    return False

                return opendirectory.authenticateUserDigest(
                    self.service.directory,
                    self.guid,
                    self.shortName,
                    challenge,
                    response,
                    credentials.method
                )
            except opendirectory.ODError, e:
                log.err("Open Directory (node=%s) error while performing digest authentication for user %s: %s"
                        % (self.service.realmName, self.shortName, e))
                return False

        return super(OpenDirectoryRecord, self).verifyCredentials(credentials)

class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
