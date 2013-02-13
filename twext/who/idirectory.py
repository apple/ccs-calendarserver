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
    "UnknownRecordTypeError",
    "QueryNotSupportedError",
    "NoSuchRecordError",
    "NotAllowedError",

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

class DirectoryServiceError(Exception):
    """
    Directory service generic error.
    """

class DirectoryAvailabilityError(DirectoryServiceError):
    """
    Directory not available.
    """

class UnknownRecordTypeError(DirectoryServiceError):
    """
    Unknown record type.
    """
    def __init__(self, token):
        DirectoryServiceError.__init__(self, token)
        self.token = token

class QueryNotSupportedError(DirectoryServiceError):
    """
    Query not supported.
    """

class NoSuchRecordError(DirectoryServiceError):
    """
    Record does not exist.
    """

class NotAllowedError(DirectoryServiceError):
    """
    Apparently, you can't do that.
    """



##
# Data Types
##

class RecordType(Names):
    user  = NamedConstant()
    group = NamedConstant()

    user.description  = "user"
    group.description = "group"



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

    @staticmethod
    def isMultiValue(name):
        return getattr(name, "multiValue", False)



class MatchType(Names):
    """
    Query match types.
    """
    equals     = NamedConstant()
    startsWith = NamedConstant()
    contains   = NamedConstant()

    equals.description     = "equals"
    startsWith.description = "starts with"
    contains.description   = "contains"



class Operand(Names):
    OR  = NamedConstant()
    AND = NamedConstant()

    OR.description  = "or"
    AND.description = "and"



class QueryFlags(Flags):
    """
    Query flags.
    """
    NOT = FlagConstant()
    NOT.description = "not"

    caseInsensitive = FlagConstant()
    caseInsensitive.description = "case insensitive"



class DirectoryQueryMatchExpression(object):
    """
    Query for a matching value in a given field.

    @ivar fieldName: a L{NamedConstant} specifying the field
    @ivar fieldValue: a text value to match
    @ivar matchType: a L{NamedConstant} specifying the match algorythm
    @ivar flags: L{NamedConstant} specifying additional options
    """

    def __init__(self, fieldName, fieldValue, matchType=MatchType.equals, flags=None):
        self.fieldName  = fieldName
        self.fieldValue = fieldValue
        self.matchType  = matchType
        self.flags      = flags

    def __repr__(self):
        def describe(constant):
            if hasattr(constant, "description"):
                return constant.description
            else:
                return str(constant)

        if self.flags is None:
            flags = ""
        else:
            flags = " (%s)" % (self.flags,)

        return "<%s: %r %s %r%s>" % (
            self.__class__.__name__,
            describe(self.fieldName),
            describe(self.matchType),
            describe(self.fieldValue),
            flags
        )



##
# Interfaces
##

class IDirectoryService(Interface):
    """
    Directory service.

    A directory service is a service that vends information about
    principals such as users, locations, printers, and other
    resources.  This information is provided in the form of directory
    records.

    A directory service can be queried for the types of records it
    supports, and for specific records matching certain criteria.

    A directory service may allow support the editing, removal and
    addition of records.
    """
    realmName = Attribute("The name of the authentication realm this service represents.")

    def recordTypes():
        """
        @return: a deferred iterable of L{NamedConstant}s denoting the
            record types that are kept in this directory.
        """

    def recordsFromQuery(expressions, operand=Operand.AND):
        """
        Find records matching a query consisting of an iterable of
        expressions and an operand.
        @param expressions: an iterable of expressions
        @type expressions: L{object}
        @param operand: an operand
        @type operand: a L{NamedConstant}
        @return: a deferred iterable of matching L{IDirectoryRecord}s.
        @raises: L{QueryNotSupportedError} if the query is not
            supported by this directory service.
        """

    def recordsWithFieldValue(fieldName, value):
        """
        Find records that have the given field name with the given
        value.
        @param fieldName: a field name
        @type fieldName: L{NamedConstant}
        @param value: a value to match
        @type value: L{bytes}
        @return: a deferred iterable of L{IDirectoryRecord}s.
        """

    def recordWithUID(uid):
        """
        Find the record that has the given UID.
        @param uid: a UID
        @type uid: L{bytes}
        @return: a deferred iterable of L{IDirectoryRecord}s, or
            C{None} if there is no such record.
        """
               
    def recordWithGUID(guid):
        """
        Find the record that has the given GUID.
        @param guid: a GUID
        @type guid: L{bytes}
        @return: a deferred iterable of L{IDirectoryRecord}s, or
            C{None} if there is no such record.
        """

    def recordsWithRecordType(recordType):
        """
        Find the records that have the given record type.
        @param recordType: a record type
        @type recordType: L{NamedConstant}
        @return: a deferred iterable of L{IDirectoryRecord}s.
        """

    def recordWithShortName(recordType, shortName):
        """
        Find the record that has the given record type and short name.
        @param recordType: a record type
        @type recordType: L{NamedConstant}
        @param shortName: a short name
        @type shortName: L{bytes}
        @return: a deferred iterable of L{IDirectoryRecord}s, or
            C{None} if there is no such record.
        """

    def recordsWithEmailAddress(emailAddress):
        """
        Find the records that have the given email address.
        @param emailAddress: an email address
        @type emailAddress: L{bytes}
        @return: a deferred iterable of L{IDirectoryRecord}s, or
            C{None} if there is no such record.
        """

    def updateRecords(records, create=False):
        """
        Updates existing directory records.
        @param records: the records to update
        @type records: iterable of L{IDirectoryRecord}s
        @param create: if true, create records if necessary
        @type create: boolean
        """

    def removeRecords(uids):
        """
        Removes the records with the given UIDs.
        @param uids: the UIDs of the records to remove
        @type uids: iterable of L{bytes}
        """



class IDirectoryRecord(Interface):
    """
    Directory record.

    A directory record corresponds to a principal, and contains
    information about the principal such as idenfiers, names and
    passwords.

    This information is stored in a set of fields (a mapping of field
    names and values).

    Some fields allow for multiple values while others allow only one
    value.  This is discoverable by calling L{FieldName.isMultiValue}
    on the field name.

    The field L{FieldName.recordType} will be present in all directory
    records, as all records must have a type.  Which other fields are
    required is implementation-specific.

    Principals (called group principals) may have references to other
    principals as members.  Records representing group principals will
    typically be records with the record type L{RecordType.group}, but
    it is not prohibited for other record types to have members.

    Fields may also be accessed as attributes.  For example:
    C{record.recordType} is equivalent to
    C{record.fields[FieldName.recordType]}.
    """
    service = Attribute("The L{IDirectoryService} this record exists in.")
    fields  = Attribute("A mapping with L{NamedConstant} keys.")

    def members():
        """
        Find the records that are members of this group.  Only direct
        members are included; members of members are not expanded.
        @return: a deferred iterable of L{IDirectoryRecord}s which are
            direct members of this group.
        """

    def groups():
        """
        Find the group records that this record is a member of.  Only
        groups for which this record is a direct member is are
        included; membership is not expanded.
        @return: a deferred iterable of L{IDirectoryRecord}s which are
            groups that this record is a member of.
        """
