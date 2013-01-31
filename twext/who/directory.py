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

from zope.interface import implements

from twisted.python.util import FancyEqMixin

from twext.who.idirectory import QueryNotSupportedError
from twext.who.idirectory import FieldName, RecordType
from twext.who.idirectory import Operand
from twext.who.idirectory import IDirectoryService, IDirectoryRecord



class DirectoryService(FancyEqMixin, object):
    implements(IDirectoryService)

    compareAttributes = (
        "realmName",
    )

    RecordTypeClass = RecordType
    FieldNameClass  = FieldName


    def __init__(self, realmName):
        self.realmName = realmName


    def __repr__(self):
        return "<%s %s>" % (
            self.__class__.__name__,
            self.realmName,
        )


    def recordTypes(self):
        return self.RecordTypeClass.iterconstants()


    def recordFromQuery(self, expressions, operand=Operand.AND):
        raise QueryNotSupportedError("")



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

        if fields[FieldName.recordType] not in service.RecordTypeClass.iterconstants():
            raise ValueError("Record type must be one of %r, not %r." % (
                tuple(service.RecordTypeClass.iterconstants()),
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
            fieldName = self.service.FieldNameClass.lookupByName(name)
        except ValueError:
            raise AttributeError(name)

        try:
            return self.fields[fieldName]
        except KeyError:
            raise AttributeError(name)
