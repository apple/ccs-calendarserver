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
XML based user/group/resource directory service implementation.
"""

__all__ = [
    "XMLDirectoryService",
]

from time import time
import types
import os, pwd, grp

from twisted.cred.credentials import UsernamePassword
from twext.web2.auth.digest import DigestedCredentials
from twext.python.filepath import CachingFilePath as FilePath
from twistedcaldav.config import config

from twistedcaldav.config import fullServerPath
from twistedcaldav.directory import augment
from twistedcaldav.directory.directory import DirectoryService, DirectoryError
from twistedcaldav.directory.cachingdirectory import CachingDirectoryService,\
    CachingDirectoryRecord
from twistedcaldav.directory.xmlaccountsparser import XMLAccountsParser, XMLAccountRecord
import xml.etree.ElementTree as ET
from uuid import uuid4


class XMLDirectoryService(CachingDirectoryService):
    """
    XML based implementation of L{IDirectoryService}.
    """
    baseGUID = "9CA8DEC5-5A17-43A9-84A8-BE77C1FB9172"

    realmName = None

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.xmlFile)

    def __init__(self, params, alwaysStat=False):

        defaults = {
            'xmlFile' : None,
            'directoryBackedAddressBook': None,
            'recordTypes' : (
                self.recordType_users,
                self.recordType_groups,
                self.recordType_locations,
                self.recordType_resources,
            ),
            'cacheTimeout' : 30,
            'realmName' : '/Search',
        }
        ignored = None
        params = self.getParams(params, defaults, ignored)

        self._recordTypes = params['recordTypes']
        self.realmName = params['realmName']

        super(XMLDirectoryService, self).__init__(params['cacheTimeout'])

        xmlFile = fullServerPath(config.DataRoot, params.get("xmlFile"))
        if type(xmlFile) is str:
            xmlFile = FilePath(xmlFile)

        if not xmlFile.exists():
            xmlFile.setContent("""<?xml version="1.0" encoding="utf-8"?>

<accounts realm="%s">
</accounts>
""" % (self.realmName,))

        uid = -1
        if config.UserName:
            try:
                uid = pwd.getpwnam(config.UserName).pw_uid
            except KeyError:
                self.log_error("User not found: %s" % (config.UserName,))

        gid = -1
        if config.GroupName:
            try:
                gid = grp.getgrnam(config.GroupName).gr_gid
            except KeyError:
                self.log_error("Group not found: %s" % (config.GroupName,))

        if uid != -1 and gid != -1:
            os.chown(xmlFile.path, uid, gid)


        self.xmlFile = xmlFile
        self._fileInfo = None
        self._lastCheck = 0
        self._alwaysStat = alwaysStat
        self.directoryBackedAddressBook = params.get('directoryBackedAddressBook')

        self._accounts()


    def createCache(self):
        """
        No-op to pacify addressbook backing.
        """
        

    def recordTypes(self):
        return self._recordTypes

    def listRecords(self, recordType):
        self._lastCheck = 0
        for xmlPrincipal in self._accounts()[recordType].itervalues():
            record = self.recordWithGUID(xmlPrincipal.guid)
            if record is not None:
                yield record

    def queryDirectory(self, recordTypes, indexType, indexKey):
        """
        If the query is a miss, re-read from the XML file and try again
        """
        if not self._queryDirectory(recordTypes, indexType, indexKey):
            self._lastCheck = 0
            self._queryDirectory(recordTypes, indexType, indexKey)

    def _queryDirectory(self, recordTypes, indexType, indexKey):

        anyMatches = False

        for recordType in recordTypes:
            for xmlPrincipal in self._accounts()[recordType].itervalues():
                record = XMLDirectoryRecord(
                    service       = self,
                    recordType    = recordType,
                    shortNames    = tuple(xmlPrincipal.shortNames),
                    xmlPrincipal  = xmlPrincipal,
                )

                # Look up augment information
                # TODO: this needs to be deferred but for now we hard code the deferred result because
                # we know it is completing immediately.
                d = augment.AugmentService.getAugmentRecord(record.guid)
                d.addCallback(lambda x:record.addAugmentInformation(x))

                matched = False
                if indexType == self.INDEX_TYPE_GUID:
                    matched = indexKey == record.guid
                elif indexType == self.INDEX_TYPE_SHORTNAME:
                    matched = indexKey in record.shortNames
                elif indexType == self.INDEX_TYPE_CUA:
                    matched = indexKey in record.calendarUserAddresses
                
                if matched:
                    anyMatches = True
                    self.recordCacheForType(recordType).addRecord(record, indexType, indexKey)

        return anyMatches
            
    def recordsMatchingFields(self, fields, operand="or", recordType=None):
        # Default, brute force method search of underlying XML data

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

        def xmlPrincipalMatches(xmlPrincipal):
            if operand == "and":
                for fieldName, value, caseless, matchType in fields:
                    try:
                        fieldValue = getattr(xmlPrincipal, fieldName)
                        if not fieldMatches(fieldValue, value, caseless, matchType):
                            return False
                    except AttributeError:
                        # No property => no match
                        return False
                # we hit on every property
                return True
            else: # "or"
                for fieldName, value, caseless, matchType in fields:
                    try:
                        fieldValue = getattr(xmlPrincipal, fieldName)
                        if fieldMatches(fieldValue, value, caseless, matchType):
                            return True
                    except AttributeError:
                        # No value
                        pass
                # we didn't hit any
                return False

        if recordType is None:
            recordTypes = list(self.recordTypes())
        else:
            recordTypes = (recordType,)

        for recordType in recordTypes:
            for xmlPrincipal in self._accounts()[recordType].itervalues():
                if xmlPrincipalMatches(xmlPrincipal):
                    
                    # Load/cache record from its GUID
                    record = self.recordWithGUID(xmlPrincipal.guid)
                    if record:
                        yield record

    def _initCaches(self):
        super(XMLDirectoryService, self)._initCaches()
        self._lastCheck = 0

    def _accounts(self):
        currentTime = time()
        if self._alwaysStat or currentTime - self._lastCheck > 60:
            self.xmlFile.restat()
            self._lastCheck = currentTime
            fileInfo = (self.xmlFile.getmtime(), self.xmlFile.getsize())
            if fileInfo != self._fileInfo:
                parser = XMLAccountsParser(self.xmlFile)
                self._parsedAccounts = parser.items
                self.realmName = parser.realm
                self._fileInfo = fileInfo
        return self._parsedAccounts


    def _addElement(self, parent, principal):
        """
        Create an XML element from principal and add it as a child of parent
        """

        # TODO: derive this from xmlaccountsparser.py
        xmlTypes = {
            'users'     : 'user',
            'groups'    : 'group',
            'locations' : 'location',
            'resources' : 'resource',
        }
        xmlType = xmlTypes[principal.recordType]

        element = ET.SubElement(parent, xmlType)
        for value in principal.shortNames:
            ET.SubElement(element, "uid").text = value
        ET.SubElement(element, "guid").text = principal.guid
        ET.SubElement(element, "name").text = principal.fullName
        ET.SubElement(element, "first-name").text = principal.firstName
        ET.SubElement(element, "last-name").text = principal.lastName
        for value in principal.emailAddresses:
            ET.SubElement(element, "email-address").text = value
        if principal.extras:
            extrasElement = ET.SubElement(element, "extras")
            for key, value in principal.extras.iteritems():
                ET.SubElement(extrasElement, key).text = value

        return element


    def _persistRecords(self, element):

        def indent(elem, level=0):
            i = "\n" + level*"  "
            if len(elem):
                if not elem.text or not elem.text.strip():
                    elem.text = i + "  "
                if not elem.tail or not elem.tail.strip():
                    elem.tail = i
                for elem in elem:
                    indent(elem, level+1)
                if not elem.tail or not elem.tail.strip():
                    elem.tail = i
            else:
                if level and (not elem.tail or not elem.tail.strip()):
                    elem.tail = i

        indent(element)

        # TODO: make this robust:
        ET.ElementTree(element).write(self.xmlFile.path)

        # Reload
        self._initCaches() # nuke local cache
        self._lastCheck = 0
        self._accounts()
        # TODO: nuke memcache entries, or prepopulate them


    def createRecord(self, recordType, guid=None, shortNames=(), authIDs=set(),
        fullName=None, firstName=None, lastName=None, emailAddresses=set(),
        uid=None, password=None, **kwargs):
        """
        Create and persist a record using the provided information.  In this
        XML-based implementation, the xml accounts are read in and converted
        to elementtree elements, a new element is added for the new record,
        and the document is serialized to disk.
        """

        if guid is None:
            guid = str(uuid4())

        # Make sure latest XML records are read in
        self._lastCheck = 0
        accounts = self._accounts()

        accountsElement = ET.Element("accounts", realm=self.realmName)
        for recType in self.recordTypes():
            for xmlPrincipal in accounts[recType].itervalues():
                if xmlPrincipal.guid == guid:
                    raise DirectoryError("Duplicate guid: %s" % (guid,))
                self._addElement(accountsElement, xmlPrincipal)

        xmlPrincipal = XMLAccountRecord(recordType)
        xmlPrincipal.shortNames = shortNames
        xmlPrincipal.guid = guid
        xmlPrincipal.password = password
        xmlPrincipal.fullName = fullName
        xmlPrincipal.firstName = firstName
        xmlPrincipal.lastName = lastName
        xmlPrincipal.emailAddresses = emailAddresses
        xmlPrincipal.extras = kwargs
        self._addElement(accountsElement, xmlPrincipal)

        self._persistRecords(accountsElement)


    def destroyRecord(self, recordType, guid=None):
        """
        Remove the record matching guid.  In this XML-based implementation,
        the xml accounts are read in and those not matching the given guid are
        converted to elementtree elements, then the document is serialized to
        disk.
        """

        # Make sure latest XML records are read in
        self._lastCheck = 0
        accounts = self._accounts()

        accountsElement = ET.Element("accounts", realm=self.realmName)
        for recType in self.recordTypes():

            for xmlPrincipal in accounts[recType].itervalues():
                if xmlPrincipal.guid != guid:
                    self._addElement(accountsElement, xmlPrincipal)

        self._persistRecords(accountsElement)


    def updateRecord(self, recordType, guid=None, shortNames=(), authIDs=set(),
        fullName=None, firstName=None, lastName=None, emailAddresses=set(),
        uid=None, password=None, **kwargs):
        """
        Update the record matching guid.  In this XML-based implementation,
        the xml accounts are read in and converted to elementtree elements.
        The account matching the given guid is replaced, then the document
        is serialized to disk.
        """

        # Make sure latest XML records are read in
        self._lastCheck = 0
        accounts = self._accounts()

        accountsElement = ET.Element("accounts", realm=self.realmName)
        for recType in self.recordTypes():

            for xmlPrincipal in accounts[recType].itervalues():
                if xmlPrincipal.guid == guid:
                    # Replace this record
                    xmlPrincipal.shortNames = shortNames
                    xmlPrincipal.password = password
                    xmlPrincipal.fullName = fullName
                    xmlPrincipal.firstName = firstName
                    xmlPrincipal.lastName = lastName
                    xmlPrincipal.emailAddresses = emailAddresses
                    xmlPrincipal.extras = kwargs
                    self._addElement(accountsElement, xmlPrincipal)
                else:
                    self._addElement(accountsElement, xmlPrincipal)

        self._persistRecords(accountsElement)

        # Force a cache update - both local and memcached
        self.queryDirectory([recordType], self.INDEX_TYPE_GUID, guid)


class XMLDirectoryRecord(CachingDirectoryRecord):
    """
    XML based implementation implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, shortNames, xmlPrincipal):
        super(XMLDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = xmlPrincipal.guid,
            shortNames            = shortNames,
            fullName              = xmlPrincipal.fullName,
            firstName             = xmlPrincipal.firstName,
            lastName              = xmlPrincipal.lastName,
            emailAddresses        = xmlPrincipal.emailAddresses,
            **xmlPrincipal.extras
        )

        self.password          = xmlPrincipal.password
        self._members          = xmlPrincipal.members
        self._groups           = xmlPrincipal.groups

    def members(self):
        for recordType, shortName in self._members:
            yield self.service.recordWithShortName(recordType, shortName)

    def groups(self):
        for shortName in self._groups:
            yield self.service.recordWithShortName(DirectoryService.recordType_groups, shortName)

    def verifyCredentials(self, credentials):
        if self.enabled:
            if isinstance(credentials, UsernamePassword):
                return credentials.password == self.password
            if isinstance(credentials, DigestedCredentials):
                return credentials.checkPassword(self.password)

        return super(XMLDirectoryRecord, self).verifyCredentials(credentials)
