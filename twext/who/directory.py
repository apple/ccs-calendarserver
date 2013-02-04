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

from types import FunctionType

from zope.interface import implements

from twisted.python.util import FancyEqMixin
from twisted.python.constants import NamedConstant
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import succeed, fail

from twext.who.idirectory import DirectoryServiceError
from twext.who.idirectory import QueryNotSupportedError
from twext.who.idirectory import FieldName, RecordType
from twext.who.idirectory import Operand
from twext.who.idirectory import DirectoryQueryMatchExpression
from twext.who.idirectory import IDirectoryService, IDirectoryRecord



class MergedConstants(object):
    """
    Work-around for the fact that Names is apparently not subclassable
    and doesn't provide a way to merge multiple Names classes.
    """
    def __init__(self, *containers):
        self._containers = containers

    def __getattr__(self, name):
        for container in self._containers:
            attr = getattr(container, name, None)
            if attr is not None:
                # Named constant or static method
                if isinstance(attr, (NamedConstant, FunctionType)):
                    return attr

        raise AttributeError(name)

    def iterconstants(self):
        for container in self._containers:
            for constant in container.iterconstants():
                yield constant

    def lookupByName(self, name):
        for container in self._containers:
            try:
                return container.lookupByName(name)
            except ValueError:
                pass

        raise ValueError(name)



class DirectoryService(FancyEqMixin, object):
    implements(IDirectoryService)

    compareAttributes = (
        "realmName",
    )

    recordType = MergedConstants(RecordType)
    fieldName  = MergedConstants(FieldName)


    def __init__(self, realmName):
        self.realmName = realmName


    def __repr__(self):
        return "<%s %s>" % (
            self.__class__.__name__,
            self.realmName,
        )


    def recordTypes(self):
        return succeed(self.recordType.iterconstants())


    def recordsFromExpression(self, expression):
        return fail(QueryNotSupportedError("Unknown expression: %s" % (expression,)))


    @inlineCallbacks
    def recordsFromQuery(self, expressions, operand=Operand.AND):
        expressionIterator = iter(expressions)

        try:
            expression = expressionIterator.next()
        except StopIteration:
            returnValue(set())

        results = (yield self.recordsFromExpression(expression))

        for expression in expressions:
            if (operand == Operand.AND and not results):
                # No need to bother continuing here
                returnValue(set())

            recordsMatchingExpression = (yield self.recordsFromExpression(expression))

            if operand == Operand.AND:
                results &= recordsMatchingExpression
            elif operand == Operand.OR:
                results |= recordsMatchingExpression
            else:
                raise QueryNotSupportedError("Unknown operand: %s" % (operand,))

        returnValue(results)


    @inlineCallbacks
    def recordsWithFieldValue(self, fieldName, value):
        returnValue((yield self.recordsFromExpression(DirectoryQueryMatchExpression(fieldName, value))))

    @inlineCallbacks
    def recordWithUID(self, uid):
        returnValue(uniqueResult((yield self.recordsWithFieldValue(FieldName.uid, uid))))
               
    @inlineCallbacks
    def recordWithGUID(self, guid):
        returnValue(uniqueResult((yield self.recordsWithFieldValue(FieldName.guid, guid))))

    def recordsWithRecordType(self, recordType):
        return self.recordsWithFieldValue(FieldName.recordType, recordType)

    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName):
        returnValue(uniqueResult((yield self.recordsFromQuery((
            DirectoryQueryMatchExpression(FieldName.recordType, recordType),
            DirectoryQueryMatchExpression(FieldName.shortNames, shortName ),
        )))))

    def recordsWithEmailAddress(self, emailAddress):
        return self.recordsWithFieldValue(FieldName.emailAddresses, emailAddress)
               


class DirectoryRecord(FancyEqMixin, object):
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
                    raise ValueError("%s field must have at least one value." % (fieldName,))
                for value in values:
                    if not value:
                        raise ValueError("%s field must not be empty." % (fieldName,))

        if fields[FieldName.recordType] not in service.recordType.iterconstants():
            raise ValueError("Record type must be one of %r, not %r." % (
                tuple(service.recordType.iterconstants()),
                fields[FieldName.recordType]
            ))

        self.service = service
        self.fields  = fields


    def __repr__(self):
        recordType = getattr(self.recordType, "description", self.recordType)

        return "<%s (%s)%s>" % (
            self.__class__.__name__,
            recordType,
            self.shortNames[0],
        )


    def __eq__(self, other):
        if isinstance(self, other.__class__):
            return (
                self.service == other.service and
                self.fields[FieldName.uid] == other.fields[FieldName.uid]
            )
        return NotImplemented


    def __getattr__(self, name):
        try:
            fieldName = self.service.fieldName.lookupByName(name)
        except ValueError:
            raise AttributeError(name)

        try:
            return self.fields[fieldName]
        except KeyError:
            raise AttributeError(name)


    def members(self):
        if self.recordType == RecordType.group:
            raise NotImplementedError()
        return succeed(())



def uniqueResult(values):
    result = None
    for value in values:
        if result is None:
            result = value
        else:
            raise DirectoryServiceError("Multiple values found where one expected.")
    return result
