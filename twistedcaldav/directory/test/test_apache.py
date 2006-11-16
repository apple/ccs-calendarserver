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

import os

import twisted.trial.unittest
from twisted.cred.credentials import UsernamePassword

from twistedcaldav.directory.apache import FileDirectoryService, FileDirectoryRecord

users = {
    "wsanchez": "foo" ,
    "cdaboo"  : "bar" ,
    "dreid"   : "baz" ,
    "lecroy"  : "quux",
}

groups = {
    "managers"   : ("lecroy",),
    "grunts"     : ("wsanchez", "cdaboo", "dreid"),
    "right_coast": ("cdaboo",),
    "left_coast" : ("wsanchez", "dreid", "lecroy"),
}

digestRealm = "Test"

basicUserFile  = os.path.join(os.path.dirname(__file__), "basic")
digestUserFile = os.path.join(os.path.dirname(__file__), "digest")
groupFile      = os.path.join(os.path.dirname(__file__), "groups")

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class Basic (twisted.trial.unittest.TestCase):
    """
    Test Apache-Compatible UserFile/GroupFile directory implementation.
    """
    def test_recordTypes_user(self):
        """
        FileDirectoryService.recordTypes(userFile)
        """
        service = FileDirectoryService(basicUserFile)
        self.assertEquals(set(service.recordTypes()), set(("user",)))

    def test_recordTypes_group(self):
        """
        FileDirectoryService.recordTypes(userFile, groupFile)
        """
        service = FileDirectoryService(basicUserFile, groupFile)
        self.assertEquals(set(service.recordTypes()), set(("user", "group")))

    def test_listRecords_user(self):
        """
        FileDirectoryService.listRecords("user")
        """
        service = FileDirectoryService(basicUserFile)
        self.assertEquals(set(service.listRecords("user")), set(users.keys()))

    def test_listRecords_group(self):
        """
        FileDirectoryService.listRecords("group")
        """
        service = FileDirectoryService(basicUserFile, groupFile)
        self.assertEquals(set(service.listRecords("group")), set(groups.keys()))

    def test_recordWithShortName_user(self):
        """
        FileDirectoryService.recordWithShortName("user")
        """
        service = FileDirectoryService(basicUserFile)
        for user in users:
            record = service.recordWithShortName("user", user)
            self.assertEquals(record.shortName, user)
        self.assertEquals(service.recordWithShortName("user", "IDunnoWhoThisIsIReallyDont"), None)

    def test_recordWithShortName_group(self):
        """
        FileDirectoryService.recordWithShortName("group")
        """
        service = FileDirectoryService(basicUserFile, groupFile)
        for group in groups:
            groupRecord = service.recordWithShortName("group", group)
            self.assertEquals(groupRecord.shortName, group)
        self.assertEquals(service.recordWithShortName("group", "IDunnoWhoThisIsIReallyDont"), None)

    def test_groupMembers(self):
        """
        FileDirectoryRecord.members()
        """
        service = FileDirectoryService(basicUserFile, groupFile)
        for group in groups:
            groupRecord = service.recordWithShortName("group", group)
            self.assertEquals(set(m.shortName for m in groupRecord.members()), set(groups[group]))

    def test_groupMemberships(self):
        """
        FileDirectoryRecord.groups()
        """
        service = FileDirectoryService(basicUserFile, groupFile)
        for user in users:
            userRecord = service.recordWithShortName("user", user)
            self.assertEquals(set(g.shortName for g in userRecord.groups()), set(g for g in groups if user in groups[g]))

    def test_verifyCredentials(self):
        """
        FileDirectoryRecord.verifyCredentials()
        """
        service = FileDirectoryService(basicUserFile)
        for user in users:
            userRecord = service.recordWithShortName("user", user)
            self.failUnless(userRecord.verifyCredentials(UsernamePassword(user, users[user])))
