##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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

from urllib import quote

import twisted.trial.unittest
from twisted.trial.unittest import SkipTest
from twisted.cred.credentials import UsernamePassword
from twisted.web2.auth.digest import DigestedCredentials, calcResponse, calcHA1

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class DirectoryTestCase (twisted.trial.unittest.TestCase):
    """
    Tests a directory implementation.
    """
    # Subclass should init this to a set of recordtypes.
    recordTypes = set()

    # Subclass should init this to a dict of username keys and dict values.
    users = {}

    # Subclass should init this to a dict of groupname keys and dict values.
    groups = {}

    # Subclass should init this to a dict of resourcenames keys and dict values.
    resources = {}

    # Subclass should init this to an IDirectoryService implementation class.
    def service(self):
        """
        Returns an IDirectoryService.
        """
        raise NotImplementedError("Subclass needs to implement service()")

    def test_realm(self):
        """
        IDirectoryService.realm
        """
        self.failUnless(self.service().realmName)

    def test_recordTypes(self):
        """
        IDirectoryService.recordTypes()
        """
        if not self.recordTypes:
            raise SkipTest("No record types")

        self.assertEquals(set(self.service().recordTypes()), self.recordTypes)

    def test_listRecords_user(self):
        """
        IDirectoryService.listRecords("user")
        """
        if not self.users:
            raise SkipTest("No users")

        self.assertEquals(self.recordNames("user"), set(self.users.keys()))

    def test_listRecords_group(self):
        """
        IDirectoryService.listRecords("group")
        """
        if not self.groups:
            raise SkipTest("No groups")

        self.assertEquals(self.recordNames("group"), set(self.groups.keys()))

    def test_listRecords_resources(self):
        """
        IDirectoryService.listRecords("resources")
        """
        if not self.resources:
            raise SkipTest("No resources")

        self.assertEquals(self.recordNames("resource"), set(self.resources.keys()))

    def test_recordWithShortName_user(self):
        """
        IDirectoryService.recordWithShortName("user")
        """
        if not self.users:
            raise SkipTest("No users")

        service = self.service()
        for shortName in self.users:
            record = service.recordWithShortName("user", shortName)
            self.compare(record, shortName, self.users[shortName])
        self.assertEquals(service.recordWithShortName("user", "IDunnoWhoThisIsIReallyDont"), None)

    def test_recordWithShortName_group(self):
        """
        IDirectoryService.recordWithShortName("group")
        """
        if not self.groups:
            raise SkipTest("No groups")

        service = self.service()
        for shortName in self.groups:
            record = service.recordWithShortName("group", shortName)
            self.compare(record, shortName, self.groups[shortName])
        self.assertEquals(service.recordWithShortName("group", "IDunnoWhoThisIsIReallyDont"), None)

    def test_recordWithShortName_resource(self):
        """
        XMLDirectoryService.recordWithShortName("resource")
        """
        if not self.resources:
            raise SkipTest("No resources")

        service = self.service()
        for shortName in self.resources:
            record = service.recordWithShortName("resource", shortName)
            self.compare(record, shortName, self.resources[shortName])

    def test_recordWithGUID(self):
        service = self.service()
        record = None

        for shortName, what in self.allEntries():
            guid = what["guid"]
            if guid is not None:
                record = service.recordWithGUID(guid)
                self.compare(record, shortName, what)

        if record is None:
            raise SkipTest("No GUIDs provided to test")

    def test_recordWithCalendarUserAddress(self):
        service = self.service()
        record = None

        for shortName, what in self.allEntries():
            for address in what["addresses"]:
                record = service.recordWithCalendarUserAddress(address)
                self.compare(record, shortName, what)

        if record is None:
            raise SkipTest("No calendar user addresses provided to test")

    def test_groupMembers(self):
        """
        IDirectoryRecord.members()
        """
        if not self.groups:
            raise SkipTest("No groups")

        service = self.service()
        for group in self.groups:
            groupRecord = service.recordWithShortName("group", group)
            result = set((m.recordType, m.shortName) for m in groupRecord.members())
            expected = set(self.groups[group]["members"])
            self.assertEquals(
                result, expected,
                "Wrong membership for group %r: %s != %s" % (group, result, expected)
            )

    def test_groupMemberships(self):
        """
        IDirectoryRecord.groups()
        """
        if not self.users:
            raise SkipTest("No users")
        if not self.groups:
            raise SkipTest("No groups")

        for recordType, data in (
            ( "user" , self.users  ),
            ( "group", self.groups ),
        ):
            service = self.service()
            for shortName in data:
                record = service.recordWithShortName(recordType, shortName)
                result = set(g.shortName for g in record.groups())
                expected = set(g for g in self.groups if (record.recordType, shortName) in self.groups[g]["members"])
                self.assertEquals(
                    result, expected,
                    "Wrong groups for %s %r: %s != %s" % (record.recordType, shortName, result, expected)
                )

    def recordNames(self, recordType):
        return set(r.shortName for r in self.service().listRecords(recordType))

    def allEntries(self):
        for data, recordType in (
            (self.users,     "user"    ),
            (self.groups,    "group"   ),
            (self.resources, "resource"),
        ):
            for item in data.iteritems():
                yield item

    def compare(self, record, shortName, data):
        def value(key):
            if key in data:
                return data[key]
            else:
                return None

        guid = value("guid")
        if guid is not None:
            guid = record.guid

        addresses = set(value("addresses"))
        addresses.add("urn:uuid:%s" % (record.guid,))

        self.assertEquals(record.shortName, shortName)
        self.assertEquals(set(record.calendarUserAddresses), addresses)

        if value("guid"):
            self.assertEquals(record.guid, value("guid"))

        if value("name"):
            self.assertEquals(record.fullName, value("name"))

class BasicTestCase (DirectoryTestCase):
    """
    Tests a directory implementation with basic auth.
    """
    def test_verifyCredentials_basic(self):
        """
        IDirectoryRecord.verifyCredentials() with basic
        """
        if not self.users:
            raise SkipTest("No users")

        service = self.service()
        for user in self.users:
            userRecord = service.recordWithShortName("user", user)
            self.failUnless(userRecord.verifyCredentials(UsernamePassword(user, self.users[user]["password"])))

# authRequest = {
#    username="username",
#    realm="test realm",
#    nonce="178288758716122392881254770685",
#    uri="/write/",
#    response="62f388be1cf678fbdfce87910871bcc5",
#    opaque="1041524039",
#    algorithm="md5",
#    cnonce="29fc54aa1641c6fa0e151419361c8f23",
#    nc=00000001,
#    qop="auth",
# }

class DigestTestCase (DirectoryTestCase):
    """
    Tests a directory implementation with digest auth.
    """
    def test_verifyCredentials_digest(self):
        """
        IDirectoryRecord.verifyCredentials() with digest
        """
        if not self.users:
            raise SkipTest("No users")

        service = self.service()
        for user in self.users:
            userRecord = service.recordWithShortName("user", user)

            # I'm glad this is so simple...
            response = calcResponse(
                calcHA1(
                    "md5",
                    user,
                    service.realmName,
                    self.users[user]["password"],
                    "booger",
                    "phlegm",
                ),
                "md5",
                "booger",
                None,
                "phlegm",
                "auth",
                "GET",
                "/",
                None,
            )

            credentials = DigestedCredentials(
                user,
                "GET",
                service.realmName,
                {
                    "response": response,
                    "uri": "/",
                    "nonce": "booger",
                    "cnonce": "phlegm",
                    "nc": None,
                },
            )

            self.failUnless(userRecord.verifyCredentials(credentials))
