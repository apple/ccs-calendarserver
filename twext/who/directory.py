# -*- test-case-name: twext.who.test.test_directory -*-
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
Generic directory service base implementation
"""

__all__ = [
    "DirectoryService",
    "DirectoryRecord",
]

from uuid import UUID

from zope.interface import implements

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import succeed, fail

from twext.who.idirectory import QueryNotSupportedError, NotAllowedError
from twext.who.idirectory import FieldName, RecordType
from twext.who.idirectory import Operand
from twext.who.idirectory import IDirectoryService, IDirectoryRecord
from twext.who.expression import MatchExpression
from twext.who.util import uniqueResult, describe



class DirectoryService(object):
    implements(IDirectoryService)

    recordType = RecordType
    fieldName  = FieldName

    normalizedFields = {
        FieldName.guid: lambda g: UUID(g).hex,
        FieldName.emailAddresses: lambda e: e.lower(),
    }


    def __init__(self, realmName):
        self.realmName = realmName


    def __repr__(self):
        return "<%s %r>" % (
            self.__class__.__name__,
            self.realmName,
        )


    def recordTypes(self):
        return self.recordType.iterconstants()


    def recordsFromExpression(self, expression, records=None):
        """
        Finds records matching a single expression.
        @param expression: an expression
        @type expression: L{object}
        @param records: a set of records to search within. C{None} if
            the whole directory should be searched.
        @type records: L{set} or L{frozenset}
        """
        return fail(QueryNotSupportedError(
            "Unknown expression: %s" % (expression,)
        ))


    @inlineCallbacks
    def recordsFromQuery(self, expressions, operand=Operand.AND):
        expressionIterator = iter(expressions)

        try:
            expression = expressionIterator.next()
        except StopIteration:
            returnValue(())

        results = set((yield self.recordsFromExpression(expression)))

        for expression in expressions:
            if operand == Operand.AND:
                if not results:
                    # No need to bother continuing here
                    returnValue(())

                records = results
            else:
                records = None

            recordsMatchingExpression = frozenset((
                yield self.recordsFromExpression(expression, records=records)
            ))

            if operand == Operand.AND:
                results &= recordsMatchingExpression
            elif operand == Operand.OR:
                results |= recordsMatchingExpression
            else:
                raise QueryNotSupportedError(
                    "Unknown operand: %s" % (operand,)
                )

        returnValue(results)


    def recordsWithFieldValue(self, fieldName, value):
        return self.recordsFromExpression(MatchExpression(fieldName, value))


    @inlineCallbacks
    def recordWithUID(self, uid):
        returnValue(uniqueResult(
            (yield self.recordsWithFieldValue(FieldName.uid, uid))
        ))


    @inlineCallbacks
    def recordWithGUID(self, guid):
        returnValue(uniqueResult(
            (yield self.recordsWithFieldValue(FieldName.guid, guid))
        ))


    def recordsWithRecordType(self, recordType):
        return self.recordsWithFieldValue(FieldName.recordType, recordType)


    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName):
        returnValue(uniqueResult((yield self.recordsFromQuery((
            MatchExpression(FieldName.recordType, recordType),
            MatchExpression(FieldName.shortNames, shortName),
        )))))


    def recordsWithEmailAddress(self, emailAddress):
        return self.recordsWithFieldValue(
            FieldName.emailAddresses,
            emailAddress,
        )


    def updateRecords(self, records, create=False):
        for record in records:
            return fail(NotAllowedError("Record updates not allowed."))


    def removeRecords(self, uids):
        for uid in uids:
            return fail(NotAllowedError("Record removal not allowed."))



class DirectoryRecord(object):
    implements(IDirectoryRecord)

    requiredFields = (
        FieldName.uid,
        FieldName.recordType,
        FieldName.shortNames,
    )


    def __init__(self, service, fields):
        for fieldName in self.requiredFields:
            if fieldName not in fields or not fields[fieldName]:
                raise ValueError("%s field is required." % (fieldName,))

            if FieldName.isMultiValue(fieldName):
                values = fields[fieldName]
                if len(values) == 0:
                    raise ValueError(
                        "%s field must have at least one value." % (fieldName,)
                    )
                for value in values:
                    if not value:
                        raise ValueError(
                            "%s field must not be empty." % (fieldName,)
                        )

        if (
            fields[FieldName.recordType] not in
            service.recordType.iterconstants()
        ):
            raise ValueError("Record type must be one of %r, not %r." % (
                tuple(service.recordType.iterconstants()),
                fields[FieldName.recordType]
            ))

        # Normalize fields
        normalizedFields = {}
        for name, value in fields.items():
            normalize = service.normalizedFields.get(name, None)

            if normalize is None:
                normalizedFields[name] = value
                continue

            if FieldName.isMultiValue(name):
                normalizedFields[name] = tuple((normalize(v) for v in value))
            else:
                normalizedFields[name] = normalize(value)

        self.service = service
        self.fields  = normalizedFields


    def __repr__(self):
        return "<%s (%s)%s>" % (
            self.__class__.__name__,
            describe(self.recordType),
            self.shortNames[0],
        )


    def __eq__(self, other):
        if IDirectoryRecord.implementedBy(other.__class__):
            return (
                self.service == other.service and
                self.fields == other.fields
            )
        return NotImplemented


    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq is NotImplemented:
            return NotImplemented
        return not eq


    def __getattr__(self, name):
        try:
            fieldName = self.service.fieldName.lookupByName(name)
        except ValueError:
            raise AttributeError(name)

        try:
            return self.fields[fieldName]
        except KeyError:
            raise AttributeError(name)


    def description(self):
        description = [self.__class__.__name__, ":"]

        for name, value in self.fields.items():
            if hasattr(name, "description"):
                name = name.description
            else:
                name = str(name)

            if hasattr(value, "description"):
                value = value.description
            else:
                value = str(value)

            description.append("\n  ")
            description.append(name)
            description.append(" = ")
            description.append(value)

        return "".join(description)


    def members(self):
        if self.recordType == RecordType.group:
            raise NotImplementedError("Subclasses must implement members()")
        return succeed(())


    def groups(self):
        raise NotImplementedError("Subclasses must implement groups()")
