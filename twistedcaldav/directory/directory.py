##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Generic directory service classes.
"""

__all__ = [
    "DirectoryService",
    "DirectoryRecord",
    "DirectoryError",
    "UnknownRecordError",
    "UnknownRecordTypeError",
]

import sys

from zope.interface import implements

from twisted.cred.error import UnauthorizedLogin
from twisted.cred.checkers import ICredentialsChecker
from twisted.web2.dav.auth import IPrincipalCredentials

from twistedcaldav.directory.idirectory import IDirectoryService, IDirectoryRecord

class DirectoryService(object):
    implements(IDirectoryService, ICredentialsChecker)

    ##
    # IDirectoryService
    ##

    realmName = None

    ##
    # ICredentialsChecker
    ##

    # For ICredentialsChecker
    credentialInterfaces = (IPrincipalCredentials,)

    def requestAvatarId(self, credentials):
        credentials = IPrincipalCredentials(credentials)

        # FIXME: ?
        # We were checking if principal is enabled; seems unnecessary in current
        # implementation because you shouldn't have a principal object for a
        # disabled directory principal.

        user = self.recordWithShortName("user", credentials.credentials.username)
        if user is None:
            raise UnauthorizedLogin("No such user: %s" % (user,))

        if user.verifyCredentials(credentials.credentials):
            return (credentials.authnPrincipal.principalURL(), credentials.authzPrincipal.principalURL())
        else:
            raise UnauthorizedLogin("Incorrect credentials for %s" % (user,)) 

    def recordTypes(self):
        raise NotImplementedError("Subclass must implement recordTypes()")

    def listRecords(self, recordType):
        raise NotImplementedError("Subclass must implement listRecords()")

    def recordWithShortName(self, recordType, shortName):
        raise NotImplementedError("Subclass must implement recordWithShortName()")

    def recordWithGUID(self, guid):
        for record in self.allRecords():
            if record.guid == guid:
                return record
        return None

    def recordWithCalendarUserAddress(self, address):
        for record in self.allRecords():
            if address in record.calendarUserAddresses:
                return record
        return None

    def allRecords(self):
        for recordType in self.recordTypes():
            for record in self.listRecords(recordType):
                yield record


class DirectoryRecord(object):
    implements(IDirectoryRecord)

    def __repr__(self):
        return "<%s[%s@%s] %s(%s) %r>" % (
            self.__class__.__name__,
            self.recordType,
            self.service,
            self.guid,
            self.shortName,
            self.fullName
        )

    def __init__(self, service, recordType, guid, shortName, fullName, calendarUserAddresses):
        self.service               = service
        self.recordType            = recordType
        self.guid                  = guid
        self.shortName             = shortName
        self.fullName              = fullName
        self.calendarUserAddresses = calendarUserAddresses

    def __cmp__(self, other):
        if not isinstance(other, DirectoryRecord):
            return NotImplemented

        for attr in ("service", "recordType", "shortName", "guid"):
            diff = cmp(getattr(self, attr), getattr(other, attr))
            if diff != 0:
                return diff
        return 0

    def __hash__(self):
        h = hash(self.__class__)
        for attr in ("service", "recordType", "shortName", "guid"):
            h = (h + hash(getattr(self, attr))) & sys.maxint
        return h

    def members(self):
        return ()

    def groups(self):
        return ()

    def verifyCredentials(self, credentials):
        return False

class DirectoryError(RuntimeError):
    """
    Generic directory error.
    """

class UnknownRecordTypeError(DirectoryError):
    """
    Unknown directory record type.
    """
