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

import sys

import opendirectory
import dsattributes

from twisted.python import log
from twisted.internet.threads import deferToThread
from twisted.internet.reactor import callLater
from twisted.cred.credentials import UsernamePassword

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

    def __init__(self, node="/Search", allUsers=False, dosetup=True):
        """
        @param node: an OpenDirectory node name to bind to.
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
        self.allUsers = allUsers
        self.computerRecordName = ""
        self._records = {}
        self._delayedCalls = set()

        if dosetup:
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
        ]

        records = opendirectory.queryRecordsWithAttributes(
            self.directory,
            { dsattributes.kDS1AttrXMLPlist: vhostname },
            dsattributes.eDSContains,
            True,    # case insentive for hostnames
            False,
            dsattributes.kDSStdRecordTypeComputers,
            attrs
        )
        self._parseComputersRecords(records, vhostname)

    def _parseComputersRecords(self, records, vhostname):
        
        # Must have some results
        if len(records) == 0:
            raise OpenDirectoryInitError(
                "Open Directory (node=%s) has no /Computers records with a virtual hostname: %s"
                % (self.realmName, vhostname,)
            )

        # Now find a single record that actually matches the hostname
        found = False
        for recordname, record in records.iteritems():
            
            # Must have XMLPlist value
            plist = record.get(dsattributes.kDS1AttrXMLPlist, None)
            if not plist:
                continue
            
            if not self._parseXMLPlist(vhostname, recordname, plist, record[dsattributes.kDS1AttrGeneratedUID]):
                continue
            elif found:
                raise OpenDirectoryInitError(
                    "Open Directory (node=%s) multiple /Computers records found matching virtual hostname: %s"
                    % (self.realmName, vhostname,)
                )
            else:
                found = True
                
        if not found:
            raise OpenDirectoryInitError(
                "Open Directory (node=%s) no /Computers records with an enabled and valid calendar service were found matching virtual hostname: %s"
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
        self.hostvariants = []
        for key, value in hostdetails.iteritems():
            if key in ("http", "https"):
                self.hostvariants.append((key, hostname, value["port"]))
        self.hostvariants = tuple(self.hostvariants)
        
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
        
        # Get useful templates
        templates = serviceInfo.get("templates", None)
        if not templates or not templates.has_key("calendarUserAddresses"):
            log.msg(
                "Open Directory (node=%s) /Computers/%s record does not have a "
                "template for calendar user addresses in its XMLPlist attribute value"
                % (self.realmName, recordname)
            )
            return False
        
        self.computerRecordName = recordname

        # Grab the templates we need for calendar user addresses
        self.cuaddrtemplates = tuple(templates["calendarUserAddresses"])
        
        # Create the string we will use to match users with accounts on this server
        self.servicetag = "%s:%s:calendar" % (recordguid, hostguid)
        
        return True
    
    def _templateExpandCalendarUserAddresses(self, recordType, recordName, record):
        """
        Expand this services calendar user address templates for the specified record.
        
        @param recordName: a C{str} containing the record name being operated on.
        @param record: a C{dict} containing the attributes retrieved from the directory.
        @return: a C{set} of C{str} for each expanded calendar user address.
        """
        
        # Make a dict of the substitutions we can do for this record. The only record parameters
        # we substitute are name, guid and email. Note that email is multi-valued so we have to
        # create a list of dicts for each one of those.
        name = recordName
        type = recordType
        guid = record.get(dsattributes.kDS1AttrGeneratedUID)
        emails = record.get(dsattributes.kDSNAttrEMailAddress)
        if emails is not None and isinstance(emails, str):
            emails = [emails]
            
        subslist = []
        if emails:
            for email in emails:
                subslist.append({
                    "name"  : name,
                    "type"  : type,
                    "guid"  : guid,
                    "email" : email,
                })
        else:
            subslist.append({
                "name"  : name,
                "type"  : type,
                "guid"  : guid,
            })
        
        # Now do substitutions    
        result = set()
        for template in self.cuaddrtemplates:
            
            # Ignore %(principaluri)s templates as we already default to adding those
            if template.find("%(principaluri)s") != -1:
                continue

            # Loop over each host variant
            for scheme, hostname, port in self.hostvariants:
                for subs in subslist:
                    # Add in host substitution values
                    subs.update({
                        "scheme"   : scheme,
                        "hostname" : hostname,
                        "port"     : port,
                    })
                    
                    # Special check for no email address for this record
                    if (template.find("%(email)s") != -1) and not emails:
                        continue

                    result.add(template % subs)
                
        return result

    def recordTypes(self):
        return (
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources,
        )

    def recordsForType(self, recordType):
        """
        @param recordType: a record type
        @return: a dictionary containing all records for the given record
        type.  Keys are short names and values are the cooresponding
        OpenDirectoryRecord for the given record type.
        """
        def reloadCache():
            log.msg("Reloading %s record cache" % (recordType,))

            query = {
                dsattributes.kDSNAttrServicesLocator: self.servicetag,
            }
    
            attrs = [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDS1AttrDistinguishedName,
                dsattributes.kDSNAttrEMailAddress,
                dsattributes.kDSNAttrServicesLocator,
            ]

            if recordType == DirectoryService.recordType_users:
                listRecordType = dsattributes.kDSStdRecordTypeUsers
            elif recordType == DirectoryService.recordType_groups:
                listRecordType = dsattributes.kDSStdRecordTypeGroups
                attrs.append(dsattributes.kDSNAttrGroupMembers)
            elif recordType == DirectoryService.recordType_locations:
                listRecordType = dsattributes.kDSStdRecordTypeLocations
            elif recordType == DirectoryService.recordType_resources:
                listRecordType = dsattributes.kDSStdRecordTypeResources
            else:
                raise UnknownRecordTypeError("Unknown Open Directory record type: %s"
                                             % (recordType,))

            records = {}

            try:
                if self.allUsers:
                    results = opendirectory.listAllRecordsWithAttributes(
                        self.directory,
                        listRecordType,
                        attrs)
                else:
                    results = opendirectory.queryRecordsWithAttributes(
                        self.directory,
                        query,
                        dsattributes.eDSStartsWith,
                        False,
                        False,
                        listRecordType,
                        attrs)
            except opendirectory.ODError, ex:
                log.msg("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
                raise

            for (key, value) in results.iteritems():
                if not self.allUsers:
	                # Make sure this user has service enabled.
                    enabled = True
                    service = value.get(dsattributes.kDSNAttrServicesLocator)
                    if isinstance(service, str):
                        service = [service]
                    for item in service:
                        if item.startswith(self.servicetag):
                            if item.endswith(":disabled"):
                                enabled = False
                            break
                    if not enabled:
                        continue

                # Now get useful record info.
                shortName = key
                guid = value.get(dsattributes.kDS1AttrGeneratedUID)
                if not guid:
                    continue
                realName = value.get(dsattributes.kDS1AttrDistinguishedName)

                # Get calendar user addresses expanded from service record templates.
                cuaddrset = self._templateExpandCalendarUserAddresses(recordType, key, value)

                # Special case for groups.
                if recordType == DirectoryService.recordType_groups:
                    memberGUIDs = value.get(dsattributes.kDSNAttrGroupMembers)
                    if memberGUIDs is None:
                        memberGUIDs = ()
                    elif type(memberGUIDs) is str:
                        memberGUIDs = (memberGUIDs,)
                else:
                    memberGUIDs = ()

                records[shortName] = OpenDirectoryRecord(
                    service               = self,
                    recordType            = recordType,
                    guid                  = guid,
                    shortName             = shortName,
                    fullName              = realName,
                    calendarUserAddresses = cuaddrset,
                    memberGUIDs           = memberGUIDs,
                )

            storage = {
                "status": "new",
                "records": records,
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

        try:
            storage = self._records[recordType]
        except KeyError:
            reloadCache()
        else:
            if storage["status"] == "stale":
                storage["status"] = "loading"

                def onError(f):
                    storage["status"] = "stale" # Keep trying
                    log.err("Unable to load records of type %s from OpenDirectory due to unexpected error: %s"
                            % (recordType, f))

                d = deferToThread(reloadCache)
                d.addErrback(onError)

        return self._records[recordType]["records"]

    def listRecords(self, recordType):
        return self.recordsForType(recordType).itervalues()

    def recordWithShortName(self, recordType, shortName):
        return self.recordsForType(recordType).get(shortName, None)

class OpenDirectoryRecord(DirectoryRecord):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, guid, shortName, fullName, calendarUserAddresses, memberGUIDs):
        super(OpenDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = guid,
            shortName             = shortName,
            fullName              = fullName,
            calendarUserAddresses = calendarUserAddresses,
        )
        self._memberGUIDs = tuple(memberGUIDs)

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

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            try:
                return opendirectory.authenticateUserBasic(self.service.directory, self.guid, self.shortName, credentials.password)
            except opendirectory.ODError, e:
                log.err("Open Directory (node=%s) error while performing basic authentication for user %s: %r"
                        % (self.service.realmName, self.shortName, e))
                return False

        return super(OpenDirectoryRecord, self).verifyCredentials(credentials)

class OpenDirectoryInitError(DirectoryError):
    """
    OpenDirectory initialization error.
    """
