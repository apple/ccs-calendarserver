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

from twistedcaldav.directory.xmlfile import XMLFileService

users = set(
     ("admin"   ,
      "proxy"   ,
      "wsanchez",
      "cdaboo"  ,
      "lecroy"  ,
      "dreid"   ,
      "user01"  ,
      "user02"  ,)
)

groups = {
    "managers"   : ("lecroy",),
    "grunts"     : ("wsanchez", "cdaboo", "dreid"),
    "right_coast": ("cdaboo",),
    "left_coast" : ("wsanchez", "dreid", "lecroy"),
}

resources = set(
    ("mercury",
     "gemini" ,
     "apollo" ,)
)

xmlFile  = os.path.join(os.path.dirname(__file__), "accounts.xml")

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class Basic (twisted.trial.unittest.TestCase):
    """
    Test XML file based directory implementation.
    """
    def test_recordTypes(self):
        """
        XMLFileService.recordTypes(xmlFile)
        """
        service = XMLFileService(xmlFile)
        self.assertEquals(set(service.recordTypes()), set(("user", "group", "resource")))

    def test_listRecords_user(self):
        """
        XMLFileService.listRecords("user")
        """
        service = XMLFileService(xmlFile)
        self.assertEquals(set(service.listRecords("user")), users)

    def test_listRecords_group(self):
        """
        XMLFileService.listRecords("group")
        """
        service = XMLFileService(xmlFile)
        self.assertEquals(set(service.listRecords("group")), set(groups.keys()))

    def test_listRecords_resources(self):
        """
        XMLFileService.listRecords("resource")
        """
        service = XMLFileService(xmlFile)
        self.assertEquals(set(service.listRecords("resource")), resources)

    def test_recordWithShortName_user(self):
        """
        XMLFileService.recordWithShortName("user")
        """
        service = XMLFileService(xmlFile)
        for user in users:
            record = service.recordWithShortName("user", user)
            self.assertEquals(record.shortName, user)

    def test_recordWithShortName_group(self):
        """
        XMLFileService.recordWithShortName("group")
        """
        service = XMLFileService(xmlFile)
        for group in groups:
            groupRecord = service.recordWithShortName("group", group)
            self.assertEquals(groupRecord.shortName, group)

    def test_recordWithShortName_resource(self):
        """
        XMLFileService.recordWithShortName("resource")
        """
        service = XMLFileService(xmlFile)
        for resource in resources:
            resourceRecord = service.recordWithShortName("resource", resource)
            self.assertEquals(resourceRecord.shortName, resource)

    def test_groupMembers(self):
        """
        FileDirectoryRecord.members()
        """
        service = XMLFileService(xmlFile)
        for group in groups:
            groupRecord = service.recordWithShortName("group", group)
            self.assertEquals(set(m.shortName for m in groupRecord.members()), set(groups[group]))

    def test_groupMemberships(self):
        """
        FileDirectoryRecord.groups()
        """
        service = XMLFileService(xmlFile)
        for user in users:
            userRecord = service.recordWithShortName("user", user)
            self.assertEquals(set(g.shortName for g in userRecord.groups()), set(g for g in groups if user in groups[g]))

    def test_verifyCredentials(self):
        """
        FileDirectoryRecord.verifyCredentials()
        """
        service = XMLFileService(xmlFile)
        for user in users:
            userRecord = service.recordWithShortName("user", user)
            self.failUnless(userRecord.verifyCredentials(UsernamePassword(user, user)))
