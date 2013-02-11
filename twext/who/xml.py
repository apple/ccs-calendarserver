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
from xml.etree.ElementTree import tostring as etreeToString
from xml.etree.ElementTree import Element as XMLElement

from twisted.python.constants import Names, NamedConstant, Values, ValueConstant
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twext.who.idirectory import DirectoryServiceError
from twext.who.idirectory import RecordType, FieldName as BaseFieldName
from twext.who.idirectory import MatchType
from twext.who.idirectory import DirectoryQueryMatchExpression
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.directory import DirectoryRecord as BaseDirectoryRecord
from twext.who.directory import MergedConstants



##
# Exceptions
##

class ParseError(RuntimeError):
    """
    Parse error.
    """
    def __init__(self, token):
        RuntimeError.__init__(self, token)
        self.token = token

class UnknownRecordTypeParseError(ParseError):
    """
    Unknown record type.
    """

class UnknownFieldNameParseError(ParseError):
    """
    Unknown field name.
    """



##
# Data type extentions
##

class FieldName(Names):
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


    def loadRecords(self, loadNow=False):
        """
        Load records from L{self.filePath}.

        Does nothing if a successful refresh has happened within the
        last L{self.refreshInterval} seconds.

        @param loadNow: Load now (ignore L{self.refreshInterval})
        @type loadNow: boolean
        """
        #
        # Punt if we've read the file recently
        #
        now = time()
        if not loadNow and now - self._lastRefresh <= self.refreshInterval:
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

        realmName = directoryNode.get(self.attribute.realm.value, "").encode("utf-8")

        if not realmName:
            raise DirectoryServiceError("No realm name.")

        unknownRecordTypes   = set()
        unknownFieldElements = set()
        unknownFieldNames    = set()

        records = set()

        for recordNode in directoryNode.getchildren():
            try:
                records.add(self.parseRecordNode(recordNode))
            except UnknownRecordTypeParseError, e:
                unknownRecordTypes.add(e.token)
            except UnknownFieldNameParseError, e:
                unknownFieldNames.add(e.token)

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

        return etree


    def parseRecordNode(self, recordNode):
        recordTypeAttribute = recordNode.get(self.attribute.recordType.value, "").encode("utf-8")
        if recordTypeAttribute:
            try:
                recordType = self.value.lookupByValue(recordTypeAttribute).recordType
            except (ValueError, AttributeError):
                raise UnknownRecordTypeParseError(recordTypeAttribute)
        else:
            recordType = self.recordType.user

        fields = {}
        fields[self.fieldName.recordType] = recordType

        for fieldNode in recordNode.getchildren():
            try:
                fieldElement = self.element.lookupByValue(fieldNode.tag)
            except ValueError:
                raise UnknownFieldNameParseError(fieldNode.tag)

            try:
                fieldName = fieldElement.fieldName
            except AttributeError:
                raise UnknownFieldNameParseError(fieldNode.tag)

            value = fieldNode.text.encode("utf-8")

            if self.fieldName.isMultiValue(fieldName):
                values = fields.setdefault(fieldName, [])
                values.append(value)
            else:
                fields[fieldName] = value

        return DirectoryRecord(self, fields)


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
        fieldIndex = self.index[expression.fieldName]

        if expression.matchType != MatchType.equals:
            raise NotImplementedError("Handle MatchType != equals")

        if expression.flags:
            raise NotImplementedError("Handle QueryFlags")

        matchingRecords = fieldIndex.get(expression.fieldValue, ())

        return succeed(frozenset(matchingRecords))


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


    def updateRecords(self, records, create=False):
        self.flush()
        etree = self.loadRecords(loadNow=True)

        recordsByUID = dict(((record.uid, record) for record in records))

        directoryNode = etree.getroot()

        for recordNode in directoryNode.getchildren():
            uidNode = recordNode.find(self.element.uid.value)
            if uidNode is None:
                raise NotImplementedError("No UID node")

            record = recordsByUID.get(uidNode.text, None)

            if record:
                recordNode.clear()

                for (name, value) in record.fields.items():
                    if name == self.fieldName.recordType:
                        # FIXME: This lookup of the record type value is a bit much to do in a loop
                        for valueName in self.value.iterconstants():
                            if getattr(valueName, "recordType", None) == value:
                                recordNode.set(self.attribute.recordType.value, valueName.value)
                                break
                        else:
                            raise AssertionError("Unknown record type: %r" % (value,))
                    else:
                        # FIXME: This lookup of the field name element is a bit much to do in a loop
                        for elementName in self.element.iterconstants():
                            if getattr(elementName, "fieldName", None) == name:
                                if self.fieldName.isMultiValue(name):
                                    values = value
                                else:
                                    values = (value,)

                                for value in values:
                                    subNode = XMLElement(tag=elementName.value)
                                    subNode.text = value
                                    recordNode.append(subNode)

                                break
                        else:
                            raise AssertionError("Unknown field name: %r" % (name,))

                del recordsByUID[record.uid]

        if recordsByUID:
            if not create:
                raise NotImplementedError("Raise something.")

            raise NotImplementedError("Add new records.")

        self.filePath.setContent(etreeToString(directoryNode))
        self.flush()



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
