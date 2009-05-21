##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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

try:
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryService
except ImportError:
    pass
else:
    import twisted.web2.auth.digest
    import twistedcaldav.directory.test.util
    from twistedcaldav.directory.directory import DirectoryService
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryRecord
    import dsattributes

    # Wonky hack to prevent unclean reactor shutdowns
    class DummyReactor(object):
        @staticmethod
        def callLater(*args):
            pass
    import twistedcaldav.directory.appleopendirectory
    twistedcaldav.directory.appleopendirectory.reactor = DummyReactor

    class OpenDirectory (
        twistedcaldav.directory.test.util.BasicTestCase,
        twistedcaldav.directory.test.util.DigestTestCase
    ):
        """
        Test Open Directory directory implementation.
        """
        recordTypes = set((
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources
        ))

        users = groups = locations = resources = {}

        def setUp(self):
            super(OpenDirectory, self).setUp()
            self._service = OpenDirectoryService({'node' : "/Search"}, dosetup=False)

        def tearDown(self):
            for call in self._service._delayedCalls:
                call.cancel()

        def service(self):
            return self._service

        def test_invalidODDigest(self):
            record = OpenDirectoryRecord(
                service               = self.service(),
                recordType            = DirectoryService.recordType_users,
                guid                  = "B1F93EB1-DA93-4772-9141-81C250DA35B3",
                nodeName              = "/LDAPv2/127.0.0.1",
                shortNames            = ("user",),
                authIDs               = set(),
                fullName              = "Some user",
                firstName             = "Some",
                lastName              = "User",
                emailAddresses        = set(("someuser@example.com",)),
                calendarUserAddresses = set(("mailtoguid@example.com",)),
                enabledForCalendaring = True,
                memberGUIDs           = [],
            )

            digestFields = {}
            digested = twisted.web2.auth.digest.DigestedCredentials("user", "GET", "example.com", digestFields, None)

            self.assertFalse(record.verifyCredentials(digested))


        def test_queryDirectorySingleGUID(self):
            """ Test for lookup on existing and non-existing GUIDs """

            def lookupMethod(obj, attr, value, matchType, casei, recordType, attributes, count=0):

                data = [
                    {
                        dsattributes.kDS1AttrGeneratedUID : "1234567890",
                        dsattributes.kDSNAttrRecordName : ["user1", "User 1"],
                        dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                    },
                ]
                results = []
                for entry in data:
                    if entry[attr] == value:
                        results.append(("", entry))
                return results

            recordTypes = [DirectoryService.recordType_users, DirectoryService.recordType_groups, DirectoryService.recordType_locations, DirectoryService.recordType_resources]
            self.service().queryDirectory(recordTypes, self.service().INDEX_TYPE_GUID, "1234567890", lookupMethod=lookupMethod)
            self.assertTrue(self.service().recordWithGUID("1234567890"))
            self.assertFalse(self.service().recordWithGUID("987654321"))


        def test_queryDirectoryDuplicateGUIDs(self):
            """ Test for lookup on duplicate GUIDs, ensuring they don't get
                faulted in """

            def lookupMethod(obj, attr, value, matchType, casei, recordType, attributes, count=0):

                data = [
                    {
                        dsattributes.kDS1AttrGeneratedUID : "1234567890",
                        dsattributes.kDSNAttrRecordName : ["user1", "User 1"],
                        dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                    },
                    {
                        dsattributes.kDS1AttrGeneratedUID : "1234567890",
                        dsattributes.kDSNAttrRecordName : ["user2", "User 2"],
                        dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                    },
                ]
                results = []
                for entry in data:
                    if entry[attr] == value:
                        results.append(("", entry))
                return results

            recordTypes = [DirectoryService.recordType_users, DirectoryService.recordType_groups, DirectoryService.recordType_locations, DirectoryService.recordType_resources]
            self.service().queryDirectory(recordTypes, self.service().INDEX_TYPE_GUID, "1234567890", lookupMethod=lookupMethod)
            self.assertFalse(self.service().recordWithGUID("1234567890"))
