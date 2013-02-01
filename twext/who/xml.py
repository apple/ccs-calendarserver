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

from xml.etree.ElementTree import parse as parseXML
from xml.etree.ElementTree import ParseError as XMLParseError

from twisted.python.constants import Values, ValueConstant, NamedConstant
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twext.who.idirectory import DirectoryServiceError
from twext.who.idirectory import RecordType, FieldName as BaseFieldName
from twext.who.idirectory import MatchType
from twext.who.idirectory import DirectoryQueryMatchExpression
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.directory import DirectoryRecord as BaseDirectoryRecord



##
# Data type extentions
##

class FieldName (BaseFieldName):
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
    uid.fieldName = FieldName.uid

    guid = ValueConstant("guid")
    guid.fieldName = FieldName.guid

    shortName = ValueConstant("short-name")
    shortName.fieldName = FieldName.shortNames

    fullName = ValueConstant("full-name")
    fullName.fieldName = FieldName.fullNames

    emailAddress = ValueConstant("email")
    emailAddress.fieldName = FieldName.emailAddresses

    password = ValueConstant("password")
    password.fieldName = FieldName.password

    memberUID = ValueConstant("member-uid")
    memberUID.fieldName = FieldName.memberUIDs



class Attribute(Values):
    realm      = ValueConstant("realm")
    recordType = ValueConstant("type")



class Value(Values):
    # Booleans
    true  = ValueConstant("true")
    false = ValueConstant("false")

    # Record types
    user  = ValueConstant("user")
    group = ValueConstant("group")

    user.recordType  = RecordType.user
    group.recordType = RecordType.group



##
# Directory Service
##

class DirectoryService(BaseDirectoryService):
    """
    XML directory service.
    """

    FieldNameClass  = FieldName

    ElementClass   = Element
    AttributeClass = Attribute
    ValueClass     = Value

    indexedFields = (
        FieldName.recordType,
        FieldName.uid,
        FieldName.guid,
        FieldName.shortNames,
        FieldName.emailAddresses,
    )


    def __init__(self, filePath, refreshInterval=4):
        BaseDirectoryService.__init__(self, realmName=None)

        self.filePath = filePath
        self.refreshInterval = refreshInterval


    def __repr__(self):
        return "<%s %s>" % (
            self.__class__.__name__,
            self._realmName,
        )


    @property
    def realmName(self):
        if not hasattr(self, "_realmName"):
            self.loadRecords()
        return self._realmName

    @realmName.setter
    def realmName(self, value):
        if value is not None:
            raise AssertionError("realmName may not be set directly")

    @property
    def unknownRecordTypes(self):
        if not hasattr(self, "_unknownRecordTypes"):
            self.loadRecords()
        return self._unknownRecordTypes

    @property
    def unknownFieldNames(self):
        if not hasattr(self, "_unknownFieldNames"):
            self.loadRecords()
        return self._unknownFieldNames

    @property
    def index(self):
        if not hasattr(self, "_index"):
            self.loadRecords()
        return self._index


    def loadRecords(self):
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
        if directoryNode.tag != self.ElementClass.directory.value:
            raise DirectoryServiceError("Incorrect root element: %s" % (directoryNode.tag,))

        def getAttribute(node, name):
            return node.get(name, "").encode("utf-8")

        realmName = getAttribute(directoryNode, self.AttributeClass.realm.value)

        if not realmName:
            raise DirectoryServiceError("No realm name.")

        unknownRecordTypes = set()
        unknownFieldNames  = set()

        records = set()

        for recordNode in directoryNode.getchildren():
            recordTypeAttribute = getAttribute(recordNode, self.AttributeClass.recordType.value)
            if not recordTypeAttribute:
                recordTypeAttribute = "user"

            try:
                recordType = self.ValueClass.lookupByValue(recordTypeAttribute).recordType
            except (ValueError, AttributeError):
                unknownRecordTypes.add(recordTypeAttribute)
                continue

            fields = {}
            fields[FieldName.recordType] = recordType

            for fieldNode in recordNode.getchildren():
                try:
                    fieldName = self.ElementClass.lookupByValue(fieldNode.tag).fieldName
                except (ValueError, AttributeError):
                    unknownFieldNames.add(fieldNode.tag)
                    continue

                value = fieldNode.text.encode("utf-8")

                if self.FieldNameClass.isMultiValue(fieldName):
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
                    if not self.FieldNameClass.isMultiValue(fieldName):
                        values = (values,)

                    for value in values:
                        index[fieldName].setdefault(value, set()).add(record)

        self._realmName = realmName

        self._unknownRecordTypes = unknownRecordTypes
        self._unknownFieldNames  = unknownFieldNames

        self._index = index


    def indexedRecordsFromMatchExpression(self, expression):
        if expression.matchType != MatchType.equals:
            raise NotImplementedError("Handle MatchType != equals")

        if expression.flags:
            raise NotImplementedError("Handle QueryFlags")

        return succeed(self.index[expression.fieldName].get(expression.fieldValue, ()))


    @inlineCallbacks
    def recordsFromExpression(self, expression):
        if isinstance(expression, DirectoryQueryMatchExpression):
            if expression.fieldName in self.indexedFields:
                returnValue((yield self.indexedRecordsFromMatchExpression(expression)))

            raise NotImplementedError("Handle unindexed field")

        else:
            returnValue((yield BaseDirectoryService.recordsFromExpression(self, expression)))



class DirectoryRecord(BaseDirectoryRecord):
    """
    XML directory record
    """
    def members(self):
        if self.recordType != RecordType.group:
            return succeed(())

        return succeed((
            self.service.recordForUID(uid)
            for uid in self.memberUIDs
        ))
