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
Directory service interface.
"""

__all__ = [
    "DirectoryServiceError",
    "DirectoryAvailabilityError",
    "QueryNotSupportedError",
    "RecordType",
    "FieldName",
    "MatchType",
    "Operand",
    "QueryFlags",
    "DirectoryQueryMatchExpression",
    "IDirectoryService",
    "IDirectoryRecord",
]

from zope.interface import Attribute, Interface

from twisted.python.constants import Names, NamedConstant
from twisted.python.constants import Flags, FlagConstant



##
# Exceptions
##

class DirectoryServiceError(RuntimeError):
    """
    Directory service generic error.
    """

class DirectoryAvailabilityError(DirectoryServiceError):
    """
    Directory not available.
    """

class QueryNotSupportedError(DirectoryServiceError):
    """
    Query not supported.
    """



##
# Data Types
##

class _DescriptionMixIn(object):
    def __str__(self):
        return getattr(self, "description", Names.__str__(self))

class RecordType(Names, _DescriptionMixIn):
    user  = NamedConstant()
    group = NamedConstant()

    user.description  = "user"
    group.description = "group"

class FieldName(Names, _DescriptionMixIn):
    """
    Constants for common field names.
    """
    uid            = NamedConstant()
    guid           = NamedConstant()
    recordType     = NamedConstant()
    shortNames     = NamedConstant()
    fullNames      = NamedConstant()
    emailAddresses = NamedConstant()
    password       = NamedConstant()

    uid.description            = "UID"
    guid.description           = "GUID"
    recordType.description     = "record type"
    shortNames.description     = "short names"
    fullNames.description      = "full names"
    emailAddresses.description = "email addresses"
    password.description       = "password"

    shortNames.multiValue     = True
    fullNames.multiValue      = True
    emailAddresses.multiValue = True

    @classmethod
    def isMultiValue(cls, name):
        return getattr(name, "multiValue", False)

class MatchType(Names, _DescriptionMixIn):
    """
    Query match types.
    """
    equals     = NamedConstant()
    startsWith = NamedConstant()
    contains   = NamedConstant()

    equals.description     = "equals"
    startsWith.description = "starts with"
    contains.description   = "contains"

class Operand(Names, _DescriptionMixIn):
    OR  = NamedConstant()
    AND = NamedConstant()

    OR.description  = "or"
    AND.description = "and"

class QueryFlags(Flags, _DescriptionMixIn):
    """
    Query flags.
    """
    caseInsensitive = FlagConstant()

    caseInsensitive.description = "case insensitive"

class DirectoryQueryMatchExpression(object):
    """
    Directory query.

    @ivar fieldName: a L{FieldName}
    @ivar fieldValue: a text value to match
    @ivar matchType: a L{MatchType}
    @ivar flags: l{QueryFlags}
    """

    def __init__(self, fieldName, fieldValue, matchType=MatchType.equals, flags=None):
        self.fieldName  = fieldName
        self.fieldValue = fieldValue
        self.matchType  = matchType
        self.flags      = flags



##
# Interfaces
##

class IDirectoryService(Interface):
    """
    Directory service.
    """
    realmName = Attribute("The name of the authentication realm this service represents.")

    def recordTypes():
        """
        @return: a deferred iterable of strings denoting the record
            types that are kept in the directory.  For example:
            C{("users", "groups", "resources")}.
        """

    def recordsFromQuery(expressions, operand=Operand.AND):
        """
        Find records matching a query consisting of an interable of
        expressions and an L{Operand}.
        @return: a deferred iterable of matching L{IDirectoryRecord}s.
        @raises: L{QueryNotSupportedError} if the query is not
            supported by this directory service.
        """

    def recordsWithFieldValue(fieldName, value):
        """
        Find records that have the given L{FieldName} with the given
        value.
        @return: a deferred iterable of L{IDirectoryRecord}s.
        """

    def recordWithUID(uid):
        """
        Find the record that has the given L{FieldName.uid}.
        @return: a deferred iterable of L{IDirectoryRecord}s, or
            C{None} if there is no such record.
        """
               
    def recordWithGUID(guid):
        """
        Find the record that has the given L{FieldName.guid}.
        @return: a deferred iterable of L{IDirectoryRecord}s, or
            C{None} if there is no such record.
        """

    def recordsWithRecordType(recordType):
        """
        Find the records that have the given L{RecordType}.
        @return: a deferred iterable of L{IDirectoryRecord}s.
        """

    def recordWithShortName(recordType, shortName):
        """
        Find the record that has the given L{RecordType} and
        L{FieldName.shortName}.
        @return: a deferred iterable of L{IDirectoryRecord}s, or
            C{None} if there is no such record.
        """

    def recordsWithEmailAddress(emailAddress):
        """
        Find the records that have the given L{FieldName.emailAddress}.
        @return: a deferred iterable of L{IDirectoryRecord}s, or
            C{None} if there is no such record.
        """



class IDirectoryRecord(Interface):
    """
    Directory record.

    Fields may also be accessed as attributes of L{IDirectoryRecord} objects.
    """
    service = Attribute("The L{IDirectoryService} this record exists in.")
    fields  = Attribute("A dictionary with L{FieldName} keys and text values.")

    def members():
        """
        Find the records that are members of this group.  Only direct
        members are included; members of members are not expanded.
        @return: an iterable of L{IDirectoryRecord}s which are direct
            members of this group.
        """
