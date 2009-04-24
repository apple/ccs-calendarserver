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
XML based user/group/resource configuration file handling.
"""

__all__ = [
    "XMLAccountsParser",
]

from uuid import UUID
import xml.dom.minidom

from twisted.python.filepath import FilePath

from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.log import Logger
from twistedcaldav.directory.resourceinfo import ResourceInfoDatabase
from twistedcaldav.directory.calendaruserproxy import CalendarUserProxyDatabase

log = Logger()

ELEMENT_ACCOUNTS          = "accounts"
ELEMENT_USER              = "user"
ELEMENT_GROUP             = "group"
ELEMENT_LOCATION          = "location"
ELEMENT_RESOURCE          = "resource"

ELEMENT_SHORTNAME         = "uid"
ELEMENT_GUID              = "guid"
ELEMENT_PASSWORD          = "password"
ELEMENT_NAME              = "name"
ELEMENT_FIRST_NAME        = "first-name"
ELEMENT_LAST_NAME         = "last-name"
ELEMENT_EMAIL_ADDRESS     = "email-address"
ELEMENT_MEMBERS           = "members"
ELEMENT_MEMBER            = "member"
ELEMENT_CUADDR            = "cuaddr"
ELEMENT_AUTOSCHEDULE      = "auto-schedule"
ELEMENT_DISABLECALENDAR   = "disable-calendar"
ELEMENT_PROXIES           = "proxies"
ELEMENT_READ_ONLY_PROXIES = "read-only-proxies"

ATTRIBUTE_REALM           = "realm"
ATTRIBUTE_REPEAT          = "repeat"
ATTRIBUTE_RECORDTYPE      = "type"

RECORD_TYPES = {
    ELEMENT_USER     : DirectoryService.recordType_users,
    ELEMENT_GROUP    : DirectoryService.recordType_groups,
    ELEMENT_LOCATION : DirectoryService.recordType_locations,
    ELEMENT_RESOURCE : DirectoryService.recordType_resources,
}

class XMLAccountsParser(object):
    """
    XML account configuration file parser.
    """
    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.xmlFile)

    def __init__(self, xmlFile):

        if type(xmlFile) is str:
            xmlFile = FilePath(xmlFile)

        self.xmlFile = xmlFile
        self.realm = None
        self.items = {}
        
        for recordType in RECORD_TYPES.values():
            self.items[recordType] = {}

        # Read in XML
        fd = open(self.xmlFile.path, "r")
        doc = xml.dom.minidom.parse(fd)
        fd.close()

        # Verify that top-level element is correct
        accounts_node = doc._get_documentElement()
        if accounts_node._get_localName() != ELEMENT_ACCOUNTS:
            self.log("Ignoring file %r because it is not a repository builder file" % (self.xmlFile,))
            return
        self._parseXML(accounts_node)
        self._updateExternalDatabases()

    def _updateExternalDatabases(self):
        resourceInfoDatabase = ResourceInfoDatabase(config.DataRoot)

        calendarUserProxyDatabase = CalendarUserProxyDatabase(config.DataRoot)

        for records in self.items.itervalues():
            for principal in records.itervalues():

                resourceInfoDatabase.setAutoScheduleInDatabase(principal.guid,
                    principal.autoSchedule)

                if principal.proxies:
                    proxies = []
                    for recordType, uid in principal.proxies:
                        record = self.items[recordType].get(uid)
                        if record is not None:
                            proxies.append(record.guid)

                    calendarUserProxyDatabase.setGroupMembersInDatabase(
                        "%s#calendar-proxy-write" % (principal.guid,),
                        proxies
                    )

                if principal.readOnlyProxies:
                    readOnlyProxies = []
                    for recordType, uid in principal.readOnlyProxies:
                        record = self.items[recordType].get(uid)
                        if record is not None:
                            readOnlyProxies.append(record.guid)

                    calendarUserProxyDatabase.setGroupMembersInDatabase(
                        "%s#calendar-proxy-read" % (principal.guid,),
                        readOnlyProxies
                    )

    def _parseXML(self, node):
        """
        Parse the XML root node from the accounts configuration document.
        @param node: the L{Node} to parse.
        """
        if node.hasAttribute(ATTRIBUTE_REALM):
            self.realm = node.getAttribute(ATTRIBUTE_REALM).encode("utf-8")

        def updateMembership(group):
            # Update group membership
            for recordType, shortName in group.members:
                item = self.items[recordType].get(shortName)
                if item is not None:
                    item.groups.add(group.shortNames[0])

        def updateProxyFor(proxier):
            # Update proxy membership
            for recordType, shortName in proxier.proxies:
                item = self.items[recordType].get(shortName)
                if item is not None:
                    item.proxyFor.add((proxier.recordType, proxier.shortNames[0]))

            # Update read-only proxy membership
            for recordType, shortName in proxier.readOnlyProxies:
                item = self.items[recordType].get(shortName)
                if item is not None:
                    item.readOnlyProxyFor.add((proxier.recordType, proxier.shortNames[0]))

        for child in node._get_childNodes():
            child_name = child._get_localName()
            if child_name is None:
                continue

            try:
                recordType = RECORD_TYPES[child_name]
            except KeyError:
                raise RuntimeError("Unknown account type: %s" % (child_name,))

            if child.hasAttribute(ATTRIBUTE_REPEAT):
                repeat = int(child.getAttribute(ATTRIBUTE_REPEAT))
            else:
                repeat = 1

            principal = XMLAccountRecord(recordType)
            principal.parseXML(child)
            if repeat > 1:
                for i in xrange(1, repeat+1):
                    newprincipal = principal.repeat(i)
                    self.items[recordType][newprincipal.shortNames[0]] = newprincipal
            else:
                self.items[recordType][principal.shortNames[0]] = principal

        # Do reverse membership mapping only after all records have been read in
        for records in self.items.itervalues():
            for principal in records.itervalues():
                updateMembership(principal)
                updateProxyFor(principal)
                
class XMLAccountRecord (object):
    """
    Contains provision information for one user.
    """
    def __init__(self, recordType):
        """
        @param recordType: record type for directory entry.
        """
        self.recordType = recordType
        self.shortNames = []
        self.guid = None
        self.password = None
        self.fullName = None
        self.firstName = None
        self.lastName = None
        self.emailAddresses = set()
        self.members = set()
        self.groups = set()
        self.calendarUserAddresses = set()
        self.autoSchedule = False
        if recordType == DirectoryService.recordType_groups:
            self.enabledForCalendaring = False
        else:
            self.enabledForCalendaring = True
        self.proxies = set()
        self.proxyFor = set()
        self.readOnlyProxies = set()
        self.readOnlyProxyFor = set()

    def repeat(self, ctr):
        """
        Create another object like this but with all text items having % substitution
        done on them with the numeric value provided.
        @param ctr: an integer to substitute into text.
        """
        shortNames = []
        for shortName in self.shortNames:
            if shortName.find("%") != -1:
                shortNames.append(shortName % ctr)
            else:
                shortNames.append(shortName)
        if self.guid and self.guid.find("%") != -1:
            guid = self.guid % ctr
        else:
            guid = self.guid
        if self.password.find("%") != -1:
            password = self.password % ctr
        else:
            password = self.password
        if self.fullName.find("%") != -1:
            fullName = self.fullName % ctr
        else:
            fullName = self.fullName
        if self.firstName and self.firstName.find("%") != -1:
            firstName = self.firstName % ctr
        else:
            firstName = self.firstName
        if self.lastName and self.lastName.find("%") != -1:
            lastName = self.lastName % ctr
        else:
            lastName = self.lastName
        emailAddresses = set()
        for emailAddr in self.emailAddresses:
            if emailAddr.find("%") != -1:
                emailAddresses.add(emailAddr % ctr)
            else:
                emailAddresses.add(emailAddr)
        calendarUserAddresses = set()
        for cuaddr in self.calendarUserAddresses:
            if cuaddr.find("%") != -1:
                calendarUserAddresses.add(cuaddr % ctr)
            else:
                calendarUserAddresses.add(cuaddr)
        
        result = XMLAccountRecord(self.recordType)
        result.shortNames = shortNames
        result.guid = guid
        result.password = password
        result.fullName = fullName
        result.firstName = firstName
        result.lastName = lastName
        result.emailAddresses = emailAddresses
        result.members = self.members
        result.calendarUserAddresses = calendarUserAddresses
        result.autoSchedule = self.autoSchedule
        result.enabledForCalendaring = self.enabledForCalendaring
        result.proxies = self.proxies
        result.readOnlyProxies = self.readOnlyProxies
        return result

    def parseXML(self, node):
        for child in node._get_childNodes():
            child_name = child._get_localName()
            if child_name is None:
                continue
            elif child_name == ELEMENT_SHORTNAME:
                if child.firstChild is not None:
                    self.shortNames.append(child.firstChild.data.encode("utf-8"))
            elif child_name == ELEMENT_GUID:
                if child.firstChild is not None:
                    guid = child.firstChild.data.encode("utf-8")
                    try:
                        UUID(guid)
                    except:
                        log.error("Invalid GUID in accounts XML: %r" % (guid,))
                    self.guid = guid
            elif child_name == ELEMENT_PASSWORD:
                if child.firstChild is not None:
                    self.password = child.firstChild.data.encode("utf-8")
            elif child_name == ELEMENT_NAME:
                if child.firstChild is not None:
                    self.fullName = child.firstChild.data.encode("utf-8")
            elif child_name == ELEMENT_FIRST_NAME:
                if child.firstChild is not None:
                    self.firstName = child.firstChild.data.encode("utf-8")
            elif child_name == ELEMENT_LAST_NAME:
                if child.firstChild is not None:
                    self.lastName = child.firstChild.data.encode("utf-8")
            elif child_name == ELEMENT_EMAIL_ADDRESS:
                if child.firstChild is not None:
                    self.emailAddresses.add(child.firstChild.data.encode("utf-8").lower())
            elif child_name == ELEMENT_MEMBERS:
                self._parseMembers(child, self.members)
            elif child_name == ELEMENT_CUADDR:
                if child.firstChild is not None:
                    self.calendarUserAddresses.add(child.firstChild.data.encode("utf-8"))
            elif child_name == ELEMENT_AUTOSCHEDULE:
                self.autoSchedule = True
            elif child_name == ELEMENT_DISABLECALENDAR:
                # FIXME: Not sure I see why this restriction is needed. --wsanchez
                ## Only Users or Groups
                #if self.recordType != DirectoryService.recordType_users:
                #    raise ValueError("<disable-calendar> element only allowed for Users: %s" % (child_name,))
                self.enabledForCalendaring = False
            elif child_name == ELEMENT_PROXIES:
                self._parseMembers(child, self.proxies)
            elif child_name == ELEMENT_READ_ONLY_PROXIES:
                self._parseMembers(child, self.readOnlyProxies)
            else:
                raise RuntimeError("Unknown account attribute: %s" % (child_name,))

        if self.enabledForCalendaring:
            for email in self.emailAddresses:
                self.calendarUserAddresses.add("mailto:%s" % (email,))

    def _parseMembers(self, node, addto):
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_MEMBER:
                if child.hasAttribute(ATTRIBUTE_RECORDTYPE):
                    recordType = child.getAttribute(ATTRIBUTE_RECORDTYPE).encode("utf-8")
                else:
                    recordType = DirectoryService.recordType_users
                if child.firstChild is not None:
                    addto.add((recordType, child.firstChild.data.encode("utf-8")))
