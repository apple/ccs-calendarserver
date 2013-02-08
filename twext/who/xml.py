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

from __future__ import absolute_import

"""
XML directory service implementation.
"""

__all__ = [
    "DirectoryService",
    "DirectoryRecord",
]

from time import time

from xml.etree.ElementTree import parse as parseXML
from xml.etree.ElementTree import ParseError as XMLParseError

from twisted.python.constants import Names, NamedConstant, Values, ValueConstant
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twext.who.idirectory import DirectoryServiceError
from twext.who.idirectory import RecordType, FieldName as BaseFieldName
from twext.who.idirectory import MatchType
from twext.who.idirectory import DirectoryQueryMatchExpression
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.directory import DirectoryRecord as BaseDirectoryRecord
from twext.who.directory import MergedConstants
from twext.who.idirectory import _DescriptionMixIn # FIXME



##
# Data type extentions
##

class FieldName(Names, _DescriptionMixIn):
    memberUIDs = NamedConstant()
    memberUIDs.description = "member UIDs"
    memberUIDs.multiValue = True



##
# XML constants
##

class Element(Values):
    directory = ValueConstant("directory")
    record    = ValueConstant("record")

    #
    # Field names
    #
    uid = ValueConstant("uid")
    uid.fieldName = BaseFieldName.uid

    guid = ValueConstant("guid")
    guid.fieldName = BaseFieldName.guid

    shortName = ValueConstant("short-name")
    shortName.fieldName = BaseFieldName.shortNames

    fullName = ValueConstant("full-name")
    fullName.fieldName = BaseFieldName.fullNames

    emailAddress = ValueConstant("email")
    emailAddress.fieldName = BaseFieldName.emailAddresses

    password = ValueConstant("password")
    password.fieldName = BaseFieldName.password

    memberUID = ValueConstant("member-uid")
    memberUID.fieldName = FieldName.memberUIDs



class Attribute(Values):
    realm      = ValueConstant("realm")
    recordType = ValueConstant("type")



class Value(Values):
    #
    # Booleans
    #
    true  = ValueConstant("true")
    false = ValueConstant("false")

    #
    # Record types
    #
    user = ValueConstant("user")
    user.recordType = RecordType.user

    group = ValueConstant("group")
    group.recordType = RecordType.group



##
# Directory Service
##

class DirectoryService(BaseDirectoryService):
    """
    XML directory service.
    """

    fieldName = MergedConstants(BaseFieldName, FieldName)

    element   = Element
    attribute = Attribute
    value     = Value

    indexedFields = (
        BaseFieldName.recordType,
        BaseFieldName.uid,
        BaseFieldName.guid,
        BaseFieldName.shortNames,
        BaseFieldName.emailAddresses,
        FieldName.memberUIDs,
    )


    def __init__(self, filePath, refreshInterval=4):
        BaseDirectoryService.__init__(self, realmName=None)

        self.filePath = filePath
        self.refreshInterval = refreshInterval

        self.flush()


    def __repr__(self):
        return "<%s %s>" % (
            self.__class__.__name__,
            self._realmName,
        )


    @property
    def realmName(self):
        self.loadRecords()
        return self._realmName

    @realmName.setter
    def realmName(self, value):
        if value is not None:
            raise AssertionError("realmName may not be set directly")

    @property
    def unknownRecordTypes(self):
        self.loadRecords()
        return self._unknownRecordTypes

    @property
    def unknownFieldElements(self):
        self.loadRecords()
        return self._unknownFieldElements

    @property
    def unknownFieldNames(self):
        self.loadRecords()
        return self._unknownFieldNames

    @property
    def index(self):
        self.loadRecords()
        return self._index


    def loadRecords(self):
        #
        # Punt if we've read the file recently
        #
        now = time()
        if now - self._lastRefresh < self.refreshInterval:
            return

        #
        # Punt if we've read the file and it's still the same.
        #
        cacheTag = (self.filePath.getmtime(), self.filePath.getsize())
        if cacheTag == self._cacheTag:
            return

        #
        # Open and parse the file
        #
        try:
            fh = self.filePath.open()

            try:
                etree = parseXML(fh)
            except XMLParseError, e:
                raise DirectoryServiceError(e.getMessage())
        finally:
            fh.close()

        #
        # Pull data from DOM
        #
        directoryNode = etree.getroot()
        if directoryNode.tag != self.element.directory.value:
            raise DirectoryServiceError("Incorrect root element: %s" % (directoryNode.tag,))

        def getAttribute(node, name):
            return node.get(name, "").encode("utf-8")

        realmName = getAttribute(directoryNode, self.attribute.realm.value)

        if not realmName:
            raise DirectoryServiceError("No realm name.")

        unknownRecordTypes   = set()
        unknownFieldElements = set()
        unknownFieldNames    = set()

        records = set()

        for recordNode in directoryNode.getchildren():
            recordTypeAttribute = getAttribute(recordNode, self.attribute.recordType.value)
            if recordTypeAttribute:
                try:
                    recordType = self.value.lookupByValue(recordTypeAttribute).recordType
                except (ValueError, AttributeError):
                    unknownRecordTypes.add(recordTypeAttribute)
                    continue
            else:
                recordType = self.recordType.user

            fields = {}
            fields[self.fieldName.recordType] = recordType

            for fieldNode in recordNode.getchildren():
                try:
                    fieldElement = self.element.lookupByValue(fieldNode.tag)
                except ValueError:
                    unknownFieldElements.add(fieldNode.tag)
                    continue

                try:
                    fieldName = fieldElement.fieldName
                except AttributeError:
                    unknownFieldNames.add(fieldNode.tag)
                    continue

                value = fieldNode.text.encode("utf-8")

                if self.fieldName.isMultiValue(fieldName):
                    values = fields.setdefault(fieldName, [])
                    values.append(value)
                else:
                    fields[fieldName] = value


            records.add(DirectoryRecord(self, fields))

        #
        # Store results
        #

        index = {}

        for fieldName in self.indexedFields:
            index[fieldName] = {}

        for record in records:
            for fieldName in self.indexedFields:
                values = record.fields.get(fieldName, None)

                if values is not None:
                    if not self.fieldName.isMultiValue(fieldName):
                        values = (values,)

                    for value in values:
                        index[fieldName].setdefault(value, set()).add(record)

        self._realmName = realmName

        self._unknownRecordTypes   = unknownRecordTypes
        self._unknownFieldElements = unknownFieldElements
        self._unknownFieldNames    = unknownFieldNames

        self._index = index

        self._cacheTag = cacheTag
        self._lastRefresh = now


    def flush(self):
        self._realmName            = None
        self._unknownRecordTypes   = None
        self._unknownFieldElements = None
        self._unknownFieldNames    = None
        self._index                = None
        self._cacheTag             = None
        self._lastRefresh          = 0


    def indexedRecordsFromMatchExpression(self, expression):
        """
        Finds records in the internal indexes matching a single
        expression.
        @param expression: an expression
        @type expression: L{object}
        """
        if expression.matchType != MatchType.equals:
            raise NotImplementedError("Handle MatchType != equals")

        if expression.flags:
            raise NotImplementedError("Handle QueryFlags")

        return succeed(self.index[expression.fieldName].get(expression.fieldValue, ()))


    def unIndexedRecordsFromMatchExpression(self, expression):
        """
        Finds records not in the internal indexes matching a single
        expression.
        @param expression: an expression
        @type expression: L{object}
        """
        raise NotImplementedError("Handle unindexed fields")

    def recordsFromExpression(self, expression):
        if isinstance(expression, DirectoryQueryMatchExpression):
            if expression.fieldName in self.indexedFields:
                records = self.indexedRecordsFromMatchExpression(expression)
            else:
                records = self.unIndexedRecordsFromMatchExpression(expression)
        else:
            records = BaseDirectoryService.recordsFromExpression(self, expression)

        return records


class DirectoryRecord(BaseDirectoryRecord):
    """
    XML directory record
    """
    @inlineCallbacks
    def members(self):
        members = set()
        for uid in getattr(self, "memberUIDs", ()):
            members.add((yield self.service.recordWithUID(uid)))
        returnValue(members)


    def groups(self):
        return self.service.recordsWithFieldValue(FieldName.memberUIDs, self.uid)
