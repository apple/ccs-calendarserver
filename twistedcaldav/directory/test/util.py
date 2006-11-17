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

import twisted.trial.unittest
from twisted.cred.credentials import UsernamePassword

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class DirectoryTestCase (twisted.trial.unittest.TestCase):
    """
    Tests a directory implementation.
    """
    # Subclass should init this to a set of recordtypes.
    recordTypes = set()

    # Subclass should init this to a dict of username keys and password values.
    users = {}

    # Subclass should init this to a dict of groupname keys and
    # sequence-of-members values.
    groups = {}

    # Subclass should init this to a set of resourcenames.
    resources = set()

    # Subclass should init this to an IDirectoryService implementation class.
    def service(self):
        """
        Returns an IDirectoryService.
        """
        raise NotImplementedError("Subclass needs to implement service()")

    def test_recordTypes(self):
        """
        IDirectoryService.recordTypes()
        """
        self.assertEquals(set(self.service().recordTypes()), self.recordTypes)

    def test_listRecords_user(self):
        """
        IDirectoryService.listRecords("user")
        """
        self.assertEquals(set(self.service().listRecords("user")), set(self.users.keys()))

    def test_listRecords_group(self):
        """
        IDirectoryService.listRecords("group")
        """
        self.assertEquals(set(self.service().listRecords("group")), set(self.groups.keys()))

    def test_listRecords_resources(self):
        """
        IDirectoryService.listRecords("resources")
        """
        if len(self.resources):
            self.assertEquals(set(self.service().listRecords("resource")), self.resources)

    def test_recordWithShortName_user(self):
        """
        IDirectoryService.recordWithShortName("user")
        """
        service = self.service()
        for user in self.users:
            record = service.recordWithShortName("user", user)
            self.assertEquals(record.shortName, user)
        self.assertEquals(service.recordWithShortName("user", "IDunnoWhoThisIsIReallyDont"), None)

    def test_recordWithShortName_group(self):
        """
        IDirectoryService.recordWithShortName("group")
        """
        service = self.service()
        for group in self.groups:
            groupRecord = service.recordWithShortName("group", group)
            self.assertEquals(groupRecord.shortName, group)
        self.assertEquals(service.recordWithShortName("group", "IDunnoWhoThisIsIReallyDont"), None)

    def test_recordWithShortName_resource(self):
        """
        XMLDirectoryService.recordWithShortName("resource")
        """
        service = self.service()
        for resource in self.resources:
            resourceRecord = service.recordWithShortName("resource", resource)
            self.assertEquals(resourceRecord.shortName, resource)

    def test_groupMembers(self):
        """
        IDirectoryRecord.members()
        """
        service = self.service()
        for group in self.groups:
            groupRecord = service.recordWithShortName("group", group)
            self.assertEquals(set(m.shortName for m in groupRecord.members()), set(self.groups[group]))

    def test_groupMemberships(self):
        """
        IDirectoryRecord.groups()
        """
        service = self.service()
        for user in self.users:
            userRecord = service.recordWithShortName("user", user)
            self.assertEquals(set(g.shortName for g in userRecord.groups()), set(g for g in self.groups if user in self.groups[g]))

class BasicTestCase (DirectoryTestCase):
    """
    Tests a directory implementation with basic auth.
    """
    def test_verifyCredentials(self):
        """
        IDirectoryRecord.verifyCredentials()
        """
        service = self.service()
        for user in self.users:
            userRecord = service.recordWithShortName("user", user)
            self.failUnless(userRecord.verifyCredentials(UsernamePassword(user, self.users[user])))
