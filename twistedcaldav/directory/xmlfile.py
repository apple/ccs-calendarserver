##
# Copyright (c) 2006-2012 Apple Inc. All rights reserved.
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
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord, DirectoryError
from twistedcaldav.directory.xmlaccountsparser import XMLAccountsParser, XMLAccountRecord
from twistedcaldav.directory.util import normalizeUUID
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.xmlutil import addSubElement, createElement, elementToXML
from uuid import uuid4


class XMLDirectoryService(DirectoryService):
    """
    XML based implementation of L{IDirectoryService}.
    """
    baseGUID = "9CA8DEC5-5A17-43A9-84A8-BE77C1FB9172"

    realmName = None

    INDEX_TYPE_GUID      = "guid"
    INDEX_TYPE_SHORTNAME = "shortname"
    INDEX_TYPE_CUA       = "cua"
    INDEX_TYPE_AUTHID    = "authid"


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
            'realmName' : '/Search',
            'statSeconds' : 15,
            'augmentService' : None,
            'groupMembershipCache' : None,
        }
        ignored = None
        params = self.getParams(params, defaults, ignored)

        self._recordTypes = params['recordTypes']
        self.realmName = params['realmName']
        self.statSeconds = params['statSeconds']
        self.augmentService = params['augmentService']
        self.groupMembershipCache = params['groupMembershipCache']

        super(XMLDirectoryService, self).__init__()

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
        self._initIndexes()
        self._accounts()

    def _initIndexes(self):
        """
        Create empty indexes
        """
        self.records = {}
        self.recordIndexes = {}

        for recordType in self.recordTypes():
            self.records[recordType] = set()
            self.recordIndexes[recordType] = {
                self.INDEX_TYPE_GUID     : {},
                self.INDEX_TYPE_SHORTNAME: {},
                self.INDEX_TYPE_CUA      : {},
                self.INDEX_TYPE_AUTHID   : {},
            }

    def _accounts(self):
        """
        Parses XML file, creates XMLDirectoryRecords and indexes them, and
        because some other code in this module still works directly with
        XMLAccountRecords as returned by XMLAccountsParser, returns a list
        of XMLAccountRecords.

        The XML file is only stat'ed at most every self.statSeconds, and is
        only reparsed if it's been modified.

        FIXME: don't return XMLAccountRecords, and have any code in this module
        which currently does work with XMLAccountRecords, modify such code to
        use XMLDirectoryRecords instead.
        """
        currentTime = time()
        if self._alwaysStat or currentTime - self._lastCheck > self.statSeconds:
            self.xmlFile.restat()
            self._lastCheck = currentTime
            fileInfo = (self.xmlFile.getmtime(), self.xmlFile.getsize())
            if fileInfo != self._fileInfo:
                self._initIndexes()
                parser = XMLAccountsParser(self.xmlFile)
                self._parsedAccounts = parser.items
                self.realmName = parser.realm
                self._fileInfo = fileInfo

                for accountDict in self._parsedAccounts.itervalues():
                    for xmlAccountRecord in accountDict.itervalues():
                        if xmlAccountRecord.recordType not in self.recordTypes():
                            continue
                        record = XMLDirectoryRecord(
                            service       = self,
                            recordType    = xmlAccountRecord.recordType,
                            shortNames    = tuple(xmlAccountRecord.shortNames),
                            xmlPrincipal  = xmlAccountRecord,
                        )
                        if self.augmentService is not None:
                            d = self.augmentService.getAugmentRecord(record.guid,
                                record.recordType)
                            d.addCallback(lambda x:record.addAugmentInformation(x))

                        self._addToIndex(record)

        return self._parsedAccounts

    def _addToIndex(self, record):
        """
        Index the record by GUID, shortName(s), authID(s) and CUA(s)
        """

        self.recordIndexes[record.recordType][self.INDEX_TYPE_GUID][record.guid] = record
        for shortName in record.shortNames:
            self.recordIndexes[record.recordType][self.INDEX_TYPE_SHORTNAME][shortName] = record
        for authID in record.authIDs:
            self.recordIndexes[record.recordType][self.INDEX_TYPE_AUTHID][authID] = record
        for cua in record.calendarUserAddresses:
            cua = normalizeCUAddr(cua)
            self.recordIndexes[record.recordType][self.INDEX_TYPE_CUA][cua] = record
        self.records[record.recordType].add(record)

    def _removeFromIndex(self, record):
        """
        Removes a record from all indexes.  Note this is only used for unit
        testing, to simulate a user being removed from the directory.
        """
        del self.recordIndexes[record.recordType][self.INDEX_TYPE_GUID][record.guid]
        for shortName in record.shortNames:
            del self.recordIndexes[record.recordType][self.INDEX_TYPE_SHORTNAME][shortName]
        for authID in record.authIDs:
            del self.recordIndexes[record.recordType][self.INDEX_TYPE_AUTHID][authID]
        for cua in record.calendarUserAddresses:
            cua = normalizeCUAddr(cua)
            del self.recordIndexes[record.recordType][self.INDEX_TYPE_CUA][cua] 
        if record in self.records[record.recordType]:
            self.records[record.recordType].remove(record)


    def _lookupInIndex(self, recordType, indexType, key):
        """
        Look for an existing record of the given recordType with the key for
        the given index type.  Returns None if no match.
        """
        self._accounts()
        return self.recordIndexes.get(recordType, {}).get(indexType, {}).get(key, None)

    def _initCaches(self):
        """
        Invalidates the indexes
        """
        self._lastCheck = 0
        self._initIndexes()

    def _forceReload(self):
        """
        Invalidates the indexes, re-reads the XML file and re-indexes
        """
        self._initCaches()
        self._fileInfo = None
        return self._accounts()


    def recordWithCalendarUserAddress(self, cua):
        cua = normalizeCUAddr(cua)
        for recordType in self.recordTypes():
            record = self._lookupInIndex(recordType, self.INDEX_TYPE_CUA, cua)
            if record and record.enabledForCalendaring:
                return record
        return None

    def recordWithShortName(self, recordType, shortName):
        return self._lookupInIndex(recordType, self.INDEX_TYPE_SHORTNAME, shortName)

    def recordWithAuthID(self, authID):
        for recordType in self.recordTypes():
            record = self._lookupInIndex(recordType, self.INDEX_TYPE_AUTHID, authID)
            if record is not None:
                return record
        return None

    def recordWithGUID(self, guid):
        guid = normalizeUUID(guid)
        for recordType in self.recordTypes():
            record = self._lookupInIndex(recordType, self.INDEX_TYPE_GUID, guid)
            if record is not None:
                return record
        return None

    recordWithUID = recordWithGUID

    def createCache(self):
        """
        No-op to pacify addressbook backing.
        """


    def recordTypes(self):
        return self._recordTypes

    def listRecords(self, recordType):
        self._accounts()
        return self.records[recordType]


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

        element = addSubElement(parent, xmlType)
        for value in principal.shortNames:
            addSubElement(element, "uid", text=value.decode("utf-8"))
        addSubElement(element, "guid", text=principal.guid)
        if principal.fullName is not None:
            addSubElement(element, "name", text=principal.fullName.decode("utf-8"))
        if principal.firstName is not None:
            addSubElement(element, "first-name", text=principal.firstName.decode("utf-8"))
        if principal.lastName is not None:
            addSubElement(element, "last-name", text=principal.lastName.decode("utf-8"))
        for value in principal.emailAddresses:
            addSubElement(element, "email-address", text=value.decode("utf-8"))
        if principal.extras:
            extrasElement = addSubElement(element, "extras")
            for key, value in principal.extras.iteritems():
                addSubElement(extrasElement, key, text=value.decode("utf-8"))

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

        self.xmlFile.setContent(elementToXML(element))

        # Fix up the file ownership because setContent doesn't maintain it
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
            os.chown(self.xmlFile.path, uid, gid)


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
        guid = normalizeUUID(guid)

        if not shortNames:
            shortNames = (guid,)

        # Make sure latest XML records are read in
        accounts = self._forceReload()

        accountsElement = createElement("accounts", realm=self.realmName)
        for recType in self.recordTypes():
            for xmlPrincipal in accounts[recType].itervalues():
                if xmlPrincipal.guid == guid:
                    raise DirectoryError("Duplicate guid: %s" % (guid,))
                for shortName in shortNames:
                    if shortName in xmlPrincipal.shortNames:
                        raise DirectoryError("Duplicate shortName: %s" %
                            (shortName,))
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
        self._forceReload()
        return self.recordWithGUID(guid)


    def destroyRecord(self, recordType, guid=None):
        """
        Remove the record matching guid.  In this XML-based implementation,
        the xml accounts are read in and those not matching the given guid are
        converted to elementtree elements, then the document is serialized to
        disk.
        """

        guid = normalizeUUID(guid)

        # Make sure latest XML records are read in
        accounts = self._forceReload()

        accountsElement = createElement("accounts", realm=self.realmName)
        for recType in self.recordTypes():

            for xmlPrincipal in accounts[recType].itervalues():
                if xmlPrincipal.guid != guid:
                    self._addElement(accountsElement, xmlPrincipal)

        self._persistRecords(accountsElement)
        self._forceReload()


    def updateRecord(self, recordType, guid=None, shortNames=(), authIDs=set(),
        fullName=None, firstName=None, lastName=None, emailAddresses=set(),
        uid=None, password=None, **kwargs):
        """
        Update the record matching guid.  In this XML-based implementation,
        the xml accounts are read in and converted to elementtree elements.
        The account matching the given guid is replaced, then the document
        is serialized to disk.
        """

        guid = normalizeUUID(guid)

        # Make sure latest XML records are read in
        accounts = self._forceReload()

        accountsElement = createElement("accounts", realm=self.realmName)
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
        self._forceReload()
        return self.recordWithGUID(guid)

    def createRecords(self, data):
        """
        Create records in bulk
        """

        # Make sure latest XML records are read in
        accounts = self._forceReload()

        knownGUIDs = { }
        knownShortNames = { }

        accountsElement = createElement("accounts", realm=self.realmName)
        for recType in self.recordTypes():
            for xmlPrincipal in accounts[recType].itervalues():
                self._addElement(accountsElement, xmlPrincipal)
                knownGUIDs[xmlPrincipal.guid] = 1
                for shortName in xmlPrincipal.shortNames:
                    knownShortNames[shortName] = 1

        for recordType, recordData in data:
            guid = recordData["guid"]
            if guid is None:
                guid = str(uuid4())

            shortNames = recordData["shortNames"]
            if not shortNames:
                shortNames = (guid,)

            if guid in knownGUIDs:
                raise DirectoryError("Duplicate guid: %s" % (guid,))

            for shortName in shortNames:
                if shortName in knownShortNames:
                    raise DirectoryError("Duplicate shortName: %s" %
                        (shortName,))

            xmlPrincipal = XMLAccountRecord(recordType)
            xmlPrincipal.shortNames = shortNames
            xmlPrincipal.guid = guid
            xmlPrincipal.fullName = recordData["fullName"]
            self._addElement(accountsElement, xmlPrincipal)

        self._persistRecords(accountsElement)
        self._forceReload()


class XMLDirectoryRecord(DirectoryRecord):
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

    def memberGUIDs(self):
        results = set()
        for recordType, shortName in self._members:
            record = self.service.recordWithShortName(recordType, shortName)
            results.add(record.guid)
        return results

    def verifyCredentials(self, credentials):
        if self.enabled:
            if isinstance(credentials, UsernamePassword):
                return credentials.password == self.password
            if isinstance(credentials, DigestedCredentials):
                return credentials.checkPassword(self.password)

        return super(XMLDirectoryRecord, self).verifyCredentials(credentials)
