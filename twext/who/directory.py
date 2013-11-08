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

from zope.interface import implementer

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import succeed, fail

from twext.who.idirectory import QueryNotSupportedError, NotAllowedError
from twext.who.idirectory import FieldName, RecordType
from twext.who.idirectory import Operand
from twext.who.idirectory import IDirectoryService, IDirectoryRecord
from twext.who.expression import CompoundExpression, MatchExpression
from twext.who.util import uniqueResult, describe



@implementer(IDirectoryService)
class DirectoryService(object):
    """
    Generic implementation of L{IDirectoryService}.

    Most of the C{recordsWith*} methods call L{recordsWithFieldValue}, which in
    turn calls L{recordsFromExpression} with a corresponding
    L{MatchExpression}.

    L{recordsFromExpression} relies on L{recordsFromNonCompoundExpression} for
    all expression types other than L{CompoundExpression}, which it handles
    directly.

    L{recordsFromNonCompoundExpression} (and therefore most uses of the other
    methods) will always fail with a L{QueryNotSupportedError}.

    A subclass should therefore override L{recordsFromNonCompoundExpression}
    with an implementation that handles any queries that it can support (which
    should include L{MatchExpression}) and calls its superclass' implementation
    with any query it cannot support.

    A subclass may override L{recordsFromExpression} if it is to support
    L{CompoundExpression}s with operands other than L{Operand.AND} and
    L{Operand.OR}.

    A subclass may override L{recordsFromExpression} if it is built on top
    of a directory service that supports compound expressions, as that may be
    more effient than relying on L{DirectoryService}'s implementation.

    L{updateRecords} and L{removeRecords} will fail with L{NotAllowedError}
    when asked to modify data.
    A subclass should override these methods if is to allow editing of
    directory information.

    @cvar recordType: a L{Names} class or compatible object (eg.
        L{ConstantsContainer}) which contains the L{NamedConstant}s denoting
        the record types that are supported by this directory service.

    @cvar fieldName: a L{Names} class or compatible object (eg.
        L{ConstantsContainer}) which contains the L{NamedConstant}s denoting
        the record field names that are supported by this directory service.

    @cvar normalizedFields: a L{dict} mapping of (ie. L{NamedConstant}s
        contained in the C{fieldName} class variable) to callables that take
        a field value (a L{unicode}) and return a normalized field value (also
        a L{unicode}).
    """

    recordType = RecordType
    fieldName  = FieldName

    normalizedFields = {
        FieldName.emailAddresses: lambda e: bytes(e).lower(),
    }


    def __init__(self, realmName):
        """
        @param realmName: a realm name
        @type realmName: L{unicode}
        """
        self.realmName = realmName


    def __repr__(self):
        return (
            "<{self.__class__.__name__} {self.realmName!r}>"
            .format(self=self)
        )


    def recordTypes(self):
        return self.recordType.iterconstants()


    def recordsFromNonCompoundExpression(self, expression, records=None):
        """
        Finds records matching a expression.

        @note: This method is called by L{recordsFromExpression} to handle
            all expressions other than L{CompoundExpression}.
            This implementation always fails with L{QueryNotSupportedError}.
            Subclasses should override this in order to handle additional
            expression types, and call on the superclass' implementation
            for other expression types.

        @note: This interface is the same as L{recordsFromExpression}, except
            for the additional C{records} argument.

        @param expression: an expression to apply
        @type expression: L{object}

        @param records: a set of records to limit the search to. C{None} if
            the whole directory should be searched.
        @type records: L{set} or L{frozenset}

        @return: The matching records.
        @rtype: deferred iterable of L{IDirectoryRecord}s

        @raises: L{QueryNotSupportedError} if the expression is not
            supported by this directory service.
        """
        return fail(QueryNotSupportedError(
            "Unknown expression: {0}".format(expression)
        ))


    @inlineCallbacks
    def recordsFromExpression(self, expression):
        if isinstance(expression, CompoundExpression):
            operand = expression.operand
            subExpressions = iter(expression.expressions)

            try:
                subExpression = subExpressions.next()
            except StopIteration:
                returnValue(())

            results = set((
                yield self.recordsFromNonCompoundExpression(subExpression)
            ))

            for subExpression in subExpressions:
                if operand == Operand.AND:
                    if not results:
                        # No need to bother continuing here
                        returnValue(())

                    records = results
                else:
                    records = None

                recordsMatchingExpression = frozenset((
                    yield self.recordsFromNonCompoundExpression(
                        subExpression,
                        records=records
                    )
                ))

                if operand == Operand.AND:
                    results &= recordsMatchingExpression
                elif operand == Operand.OR:
                    results |= recordsMatchingExpression
                else:
                    raise QueryNotSupportedError(
                        "Unknown operand: {0}".format(operand)
                    )
        else:
            results = yield self.recordsFromNonCompoundExpression(expression)

        returnValue(results)


    def recordsWithFieldValue(self, fieldName, value):
        return self.recordsFromExpression(
            MatchExpression(fieldName, value)
        )


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
        returnValue(uniqueResult((
            yield self.recordsFromExpression(
                CompoundExpression(
                    (
                        MatchExpression(FieldName.recordType, recordType),
                        MatchExpression(FieldName.shortNames, shortName),
                    ),
                    operand=Operand.AND
                )
            )
        )))


    def recordsWithEmailAddress(self, emailAddress):
        return self.recordsWithFieldValue(
            FieldName.emailAddresses,
            emailAddress,
        )


    def updateRecords(self, records, create=False):
        for record in records:
            return fail(NotAllowedError("Record updates not allowed."))
        return succeed(None)


    def removeRecords(self, uids):
        for uid in uids:
            return fail(NotAllowedError("Record removal not allowed."))
        return succeed(None)



@implementer(IDirectoryRecord)
class DirectoryRecord(object):
    """
    Generic implementation of L{IDirectoryService}.

    This is an incomplete implementation of L{IDirectoryRecord}.

    L{groups} will always fail with L{NotImplementedError} and L{members} will
    do so if this is a group record.
    A subclass should override these methods to support group membership and
    complete this implementation.

    @cvar requiredFields: an iterable of field names that must be present in
        all directory records.
    """

    requiredFields = (
        FieldName.uid,
        FieldName.recordType,
        FieldName.shortNames,
    )


    def __init__(self, service, fields):
        for fieldName in self.requiredFields:
            if fieldName not in fields or not fields[fieldName]:
                raise ValueError("{0} field is required.".format(fieldName))

            if FieldName.isMultiValue(fieldName):
                values = fields[fieldName]
                if len(values) == 0:
                    raise ValueError(
                        "{0} field must have at least one value."
                        .format(fieldName)
                    )
                for value in values:
                    if not value:
                        raise ValueError(
                            "{0} field must not be empty.".format(fieldName)
                        )

        if (
            fields[FieldName.recordType] not in
            service.recordType.iterconstants()
        ):
            raise ValueError(
                "Record type must be one of {0!r}, not {1!r}.".format(
                    tuple(service.recordType.iterconstants()),
                    fields[FieldName.recordType],
                )
            )

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
        return (
            "<{self.__class__.__name__} ({recordType}){shortName}>".format(
                self=self,
                recordType=describe(self.recordType),
                shortName=self.shortNames[0],
            )
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
        """
        Generate a string description of this directory record.

        @return: A description.
        @rtype: L{unicode}
        """
        description = [self.__class__.__name__, u":"]

        for name, value in self.fields.items():
            if hasattr(name, "description"):
                name = name.description
            else:
                name = unicode(name)

            if hasattr(value, "description"):
                value = value.description
            else:
                value = unicode(value)

            description.append(u"\n  ")
            description.append(name)
            description.append(u" = ")
            description.append(value)

        return u"".join(description)


    def members(self):
        if self.recordType == RecordType.group:
            return fail(
                NotImplementedError("Subclasses must implement members()")
            )
        return succeed(())


    def groups(self):
        return fail(NotImplementedError("Subclasses must implement groups()"))
