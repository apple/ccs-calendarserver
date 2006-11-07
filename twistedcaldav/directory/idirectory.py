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
Directory service interfaces.
"""

__all__ = [
    "IDirectoryService",
    "IDirectoryRecord",
]

from zope.interface import Attribute, Interface

class IDirectoryService(Interface):
    """
    Directory Service
    """
    def recordTypes():
        """
        @return: a sequence of strings denoting the record types that are kept
            in the directory.  For example: C{["users", "groups", "resources"]}.
        """

    def listRecords(recordType):
        """
        @param type: the type of records to retrieve.
        @return: an iterable of records of the given type.
        """

    def recordWithShortName(recordType, shortName):
        """
        @param recordType: the type of the record to look up.
        @param shortName: the short name of the record to look up.
        @return: an L{IDirectoryRecord} provider with the given short name, or
            C{None} of no such record exists.
        """

class IDirectoryRecord(Interface):
    """
    Directory Record
    """
    directory  = Attribute("The L{IDirectoryService} this record exists in.")
    recordType = Attribute("The type of this record.")
    guid       = Attribute("The GUID of this record.")
    shortName  = Attribute("The name of this record.")
    fullName   = Attribute("The full name of this record.")

    def authenticate(credentials):
        """
        Verify that the given credentials can authenticate the principal
        represented by this record.
        @param credentials: the credentials to authenticate with.
        @return: C{True} if the given credentials match this record,
            C{False} otherwise.
        """
