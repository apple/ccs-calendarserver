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

class RecordType(Names):
    user  = NamedConstant()
    group = NamedConstant()

class FieldName(Names):
    """
    Constants for common field names.
    """
    uid            = NamedConstant()
    guid           = NamedConstant()
    recordType     = NamedConstant()
    shortNames     = NamedConstant()
    fullNames      = NamedConstant()
    emailAddresses = NamedConstant()

    shortNames.multiValue     = True
    fullNames.multiValue      = True
    emailAddresses.multiValue = True

    @classmethod
    def isMultiValue(cls, name):
        return getattr(name, "multiValue", False)

class MatchType(Names):
    """
    Query match types.
    """
    equals     = NamedConstant()
    startsWith = NamedConstant()
    contains   = NamedConstant()

class Operand(Names):
    OR  = NamedConstant()
    AND = NamedConstant()

class QueryFlags(Flags):
    """
    Query flags.
    """
    caseInsensitive = FlagConstant()

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

    def recordFromQuery(expressions, operand=Operand.AND):
        """
        @return: a deferred iterable of matching L{IDirectoryRecord}s.
        @raises: L{QueryNotSupportedError} is the query is not
            supported by this directory service.
        """



class IDirectoryRecord(Interface):
    """
    Directory record.

    Fields may also be accessed as attributes of L{IDirectoryRecord} objects.
    """
    service = Attribute("The L{IDirectoryService} this record exists in.")
    fields  = Attribute("A dictionary with L{FieldName} keys and text values.")
