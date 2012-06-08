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
XML based user/group/resource configuration file handling.
"""

__all__ = [
    "XMLAccountsParser",
]

import xml.dom.minidom

from twext.python.filepath import CachingFilePath as FilePath

from twext.python.log import Logger

from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.util import normalizeUUID

import re
import hashlib

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
ELEMENT_EXTRAS            = "extras"

ATTRIBUTE_REALM           = "realm"
ATTRIBUTE_REPEAT          = "repeat"
ATTRIBUTE_RECORDTYPE      = "type"

VALUE_TRUE                = "true"
VALUE_FALSE               = "false"

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

    def __init__(self, xmlFile, externalUpdate=True):

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
            log.error("Ignoring file %r because it is not a repository builder file" % (self.xmlFile,))
            return
        self._parseXML(accounts_node)

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
        self.extras = {}

    def repeat(self, ctr):
        """
        Create another object like this but with all text items having % substitution
        done on them with the numeric value provided.
        @param ctr: an integer to substitute into text.
        """

        # Regular expression which matches ~ followed by a number
        matchNumber = re.compile(r"(~\d+)")

        def expand(text, ctr):
            """
            Returns a string where ~<number> is replaced by the first <number>
            characters from the md5 hexdigest of str(ctr), e.g.:

                expand("~9 foo", 1)

            returns:

                "c4ca4238a foo"

            ...since "c4ca4238a" is the first 9 characters of:

                hashlib.md5(str(1)).hexdigest()

            If <number> is larger than 32, the hash will repeat as needed.
            """
            if text:
                m = matchNumber.search(text)
                if m:
                    length = int(m.group(0)[1:])
                    hash = hashlib.md5(str(ctr)).hexdigest()
                    string = (hash*((length/32)+1))[:-(32-(length%32))]
                    return text.replace(m.group(0), string)
            return text

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
        fullName = expand(fullName, ctr)
        if self.firstName and self.firstName.find("%") != -1:
            firstName = self.firstName % ctr
        else:
            firstName = self.firstName
        firstName = expand(firstName, ctr)
        if self.lastName and self.lastName.find("%") != -1:
            lastName = self.lastName % ctr
        else:
            lastName = self.lastName
        lastName = expand(lastName, ctr)
        emailAddresses = set()
        for emailAddr in self.emailAddresses:
            emailAddr = expand(emailAddr, ctr)
            if emailAddr.find("%") != -1:
                emailAddresses.add(emailAddr % ctr)
            else:
                emailAddresses.add(emailAddr)
        
        result = XMLAccountRecord(self.recordType)
        result.shortNames = shortNames
        result.guid = normalizeUUID(guid)
        result.password = password
        result.fullName = fullName
        result.firstName = firstName
        result.lastName = lastName
        result.emailAddresses = emailAddresses
        result.members = self.members
        result.extras = self.extras
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
                    self.guid = child.firstChild.data.encode("utf-8")
                    if len(self.guid) < 4:
                        self.guid += "?" * (4 - len(self.guid))
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
            elif child_name == ELEMENT_EXTRAS:
                self._parseExtras(child, self.extras)
            else:
                raise RuntimeError("Unknown account attribute: %s" % (child_name,))

        if not self.shortNames:
            self.shortNames.append(self.guid)

    def _parseMembers(self, node, addto):
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_MEMBER:
                if child.hasAttribute(ATTRIBUTE_RECORDTYPE):
                    recordType = child.getAttribute(ATTRIBUTE_RECORDTYPE).encode("utf-8")
                else:
                    recordType = DirectoryService.recordType_users
                if child.firstChild is not None:
                    addto.add((recordType, child.firstChild.data.encode("utf-8")))

    def _parseExtras(self, node, addto):
        for child in node._get_childNodes():
            key = child._get_localName()
            if key:
                value = child.firstChild.data.encode("utf-8")
                addto[key.encode("utf-8")] = value
