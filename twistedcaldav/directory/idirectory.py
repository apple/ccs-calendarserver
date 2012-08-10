##
# Copyright (c) 2006-2011 Apple Inc. All rights reserved.
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
    realmName = Attribute("The name of the authentication realm this service represents.")
    guid = Attribute("A GUID for this service.")

    def recordTypes():
        """
        @return: a sequence of strings denoting the record types that
            are kept in the directory.  For example: C{["users",
            "groups", "resources"]}.
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
        @return: an L{IDirectoryRecord} with the given short name, or
            C{None} if no such record exists.
        """

    def recordWithUID(uid):
        """
        @param uid: the UID of the record to look up.
        @return: an L{IDirectoryRecord} with the given UID, or C{None}
            if no such record exists.
        """

    def recordWithGUID(guid):
        """
        @param guid: the GUID of the record to look up.
        @return: an L{IDirectoryRecord} with the given GUID, or
            C{None} if no such record exists.
        """

    def recordWithCalendarUserAddress(address):
        """
        @param address: the calendar user address of the record to look up.
        @type address: C{str}

        @return: an L{IDirectoryRecord} with the given calendar user
            address, or C{None} if no such record is found.  Note that
            some directory services may not be able to locate records
            by calendar user address, or may return partial results.
            Note also that the calendar server may add to the list of
            valid calendar user addresses for a user, and the
            directory service may not be aware of these addresses.
        """

    def recordsMatchingFields(fields):
        """
        @return: a deferred sequence of L{IDirectoryRecord}s which
            match the given fields.
        """

    def recordsMatchingTokens(tokens, context=None):
        """
        @param tokens: The tokens to search on
        @type tokens: C{list} of C{str} (utf-8 bytes)
        @param context: An indication of what the end user is searching
            for; "attendee", "location", or None
        @type context: C{str}
        @return: a deferred sequence of L{IDirectoryRecord}s which
            match the given tokens and optional context.

        Each token is searched for within each record's full name and
        email address; if each token is found within a record that
        record is returned in the results.

        If context is None, all record types are considered.  If
        context is "location", only locations are considered.  If
        context is "attendee", only users, groups, and resources
        are considered.
        """


    def setRealm(realmName):
        """
        Set a new realm name for this (and nested services if any)

        @param realmName: the realm name this service should use.
        """

class IDirectoryRecord(Interface):
    """
    Directory Record
    """
    service               = Attribute("The L{IDirectoryService} this record exists in.")
    recordType            = Attribute("The type of this record.")
    guid                  = Attribute("The GUID of this record.")
    uid                   = Attribute("The UID of this record.")
    enabled               = Attribute("Determines whether this record should allow a principal to be created.")
    serverID              = Attribute("Identifies the server that actually hosts data for the record.")
    partitionID           = Attribute("Identifies the partition node that actually hosts data for the record.")
    shortNames            = Attribute("The names for this record.")
    authIDs               = Attribute("Alternative security identities for this record.")
    fullName              = Attribute("The full name of this record.")
    firstName             = Attribute("The first name of this record.")
    lastName              = Attribute("The last name of this record.")
    emailAddresses        = Attribute("The email addresses of this record.")
    enabledForCalendaring = Attribute("Determines whether this record creates a principal with a calendar home.")
    enabledForAddressBooks = Attribute("Determines whether this record creates a principal with an address book home.")
    calendarUserAddresses = Attribute(
        """
        An iterable of C{str}s representing calendar user addresses for this
        L{IDirectoryRecord}.

        A "calendar user address", as defined by U{RFC 2445 section
        4.3.3<http://xml.resource.org/public/rfc/html/rfc2445.html#anchor50>},
        is simply an URI which identifies this user.  Some of these URIs are
        relative references to URLs from the root of the calendar server's HTTP
        hierarchy.
        """
    )

    def members():
        """
        @return: an iterable of L{IDirectoryRecord}s for the members of this
            (group) record.
        """

    def groups():
        """
        @return: an iterable of L{IDirectoryRecord}s for the groups this
            record is a member of.
        """

    def verifyCredentials(credentials):
        """
        Verify that the given credentials can authenticate the principal
        represented by this record.
        @param credentials: the credentials to authenticate with.
        @return: C{True} if the given credentials match this record,
            C{False} otherwise.
        """
