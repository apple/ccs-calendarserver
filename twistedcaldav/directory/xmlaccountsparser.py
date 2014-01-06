##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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

from twext.python.filepath import CachingFilePath as FilePath

from twext.python.log import Logger

from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.util import normalizeUUID
from twistedcaldav.xmlutil import readXML

import re
import hashlib

log = Logger()

ELEMENT_ACCOUNTS          = "accounts"
ELEMENT_USER              = "user"
ELEMENT_GROUP             = "group"
ELEMENT_LOCATION          = "location"
ELEMENT_RESOURCE          = "resource"
ELEMENT_ADDRESS           = "address"

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
    ELEMENT_ADDRESS  : DirectoryService.recordType_addresses,
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
        try:
            _ignore_tree, accounts_node = readXML(self.xmlFile.path, ELEMENT_ACCOUNTS)
        except ValueError, e:
            raise RuntimeError("XML parse error for '%s' because: %s" % (self.xmlFile, e,))
        self._parseXML(accounts_node)

    def _parseXML(self, node):
        """
        Parse the XML root node from the accounts configuration document.
        @param node: the L{Node} to parse.
        """
        self.realm = node.get(ATTRIBUTE_REALM, "").encode("utf-8")

        def updateMembership(group):
            # Update group membership
            for recordType, shortName in group.members:
                item = self.items[recordType].get(shortName)
                if item is not None:
                    item.groups.add(group.shortNames[0])

        for child in node:
            try:
                recordType = RECORD_TYPES[child.tag]
            except KeyError:
                raise RuntimeError("Unknown account type: %s" % (child.tag,))

            repeat = int(child.get(ATTRIBUTE_REPEAT, 0))

            principal = XMLAccountRecord(recordType)
            principal.parseXML(child)
            if repeat > 0:
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
            characters from the md5 hexdigest of str(ctr), e.g.::

                expand("~9 foo", 1)

            returns::

                "c4ca4238a foo"

            ...since "c4ca4238a" is the first 9 characters of::

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
        for child in node:
            if child.tag == ELEMENT_SHORTNAME:
                self.shortNames.append(child.text.encode("utf-8"))
            elif child.tag == ELEMENT_GUID:
                self.guid = normalizeUUID(child.text.encode("utf-8"))
                if len(self.guid) < 4:
                    self.guid += "?" * (4 - len(self.guid))
            elif child.tag == ELEMENT_PASSWORD:
                self.password = child.text.encode("utf-8")
            elif child.tag == ELEMENT_NAME:
                self.fullName = child.text.encode("utf-8")
            elif child.tag == ELEMENT_FIRST_NAME:
                self.firstName = child.text.encode("utf-8")
            elif child.tag == ELEMENT_LAST_NAME:
                self.lastName = child.text.encode("utf-8")
            elif child.tag == ELEMENT_EMAIL_ADDRESS:
                self.emailAddresses.add(child.text.encode("utf-8").lower())
            elif child.tag == ELEMENT_MEMBERS:
                self._parseMembers(child, self.members)
            elif child.tag == ELEMENT_EXTRAS:
                self._parseExtras(child, self.extras)
            else:
                raise RuntimeError("Unknown account attribute: %s" % (child.tag,))

        if not self.shortNames:
            self.shortNames.append(self.guid)

    def _parseMembers(self, node, addto):
        for child in node:
            if child.tag == ELEMENT_MEMBER:
                recordType = child.get(ATTRIBUTE_RECORDTYPE, DirectoryService.recordType_users)
                addto.add((recordType, child.text.encode("utf-8")))

    def _parseExtras(self, node, addto):
        for child in node:
            addto[child.tag] = child.text.encode("utf-8")
