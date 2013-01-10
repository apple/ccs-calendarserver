##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

import os
from twistedcaldav.config import config
from twistedcaldav.test.util import TestCase
from calendarserver.tools.util import getDirectory
from twext.python.filepath import CachingFilePath as FilePath
from twistedcaldav.directory.directory import DirectoryError


class ModificationTestCase(TestCase):

    def setUp(self):
        super(ModificationTestCase, self).setUp()

        testRoot = os.path.join(os.path.dirname(__file__), "modify")
        #configFileName = os.path.join(testRoot, "caldavd.plist")
        #config.load(configFileName)

        usersFile = os.path.join(testRoot, "users-groups.xml")
        config.DirectoryService.params.xmlFile = usersFile

        # Copy xml file containing locations/resources to a temp file because
        # we're going to be modifying it during testing

        origResourcesFile = FilePath(os.path.join(os.path.dirname(__file__),
            "modify", "resources-locations.xml"))
        copyResourcesFile = FilePath(self.mktemp())
        origResourcesFile.copyTo(copyResourcesFile)
        config.ResourceService.params.xmlFile = copyResourcesFile
        config.ResourceService.Enabled = True

        augmentsFile = os.path.join(testRoot, "augments.xml")
        config.AugmentService.params.xmlFiles = (augmentsFile,)

    def test_createRecord(self):
        directory = getDirectory()

        record = directory.recordWithUID("resource01")
        self.assertEquals(record, None)

        directory.createRecord("resources", guid="resource01",
            shortNames=("resource01",), uid="resource01",
            emailAddresses=("res1@example.com", "res2@example.com"),
            comment="Test Comment")

        record = directory.recordWithUID("resource01")
        self.assertNotEquals(record, None)

        self.assertEquals(len(record.emailAddresses), 2)
        self.assertEquals(record.extras['comment'], "Test Comment")

        directory.createRecord("resources", guid="resource02", shortNames=("resource02",), uid="resource02")

        record = directory.recordWithUID("resource02")
        self.assertNotEquals(record, None)

        # Make sure old records are still there:
        record = directory.recordWithUID("resource01")
        self.assertNotEquals(record, None)
        record = directory.recordWithUID("location01")
        self.assertNotEquals(record, None)

    def test_destroyRecord(self):
        directory = getDirectory()

        record = directory.recordWithUID("resource01")
        self.assertEquals(record, None)

        directory.createRecord("resources", guid="resource01", shortNames=("resource01",), uid="resource01")

        record = directory.recordWithUID("resource01")
        self.assertNotEquals(record, None)

        directory.destroyRecord("resources", guid="resource01")

        record = directory.recordWithUID("resource01")
        self.assertEquals(record, None)

        # Make sure old records are still there:
        record = directory.recordWithUID("location01")
        self.assertNotEquals(record, None)

    def test_updateRecord(self):
        directory = getDirectory()

        directory.createRecord("resources", guid="resource01",
            shortNames=("resource01",), uid="resource01",
            fullName="Resource number 1")

        record = directory.recordWithUID("resource01")
        self.assertEquals(record.fullName, "Resource number 1")

        directory.updateRecord("resources", guid="resource01",
            shortNames=("resource01", "r01"), uid="resource01",
            fullName="Resource #1", firstName="First", lastName="Last",
            emailAddresses=("resource01@example.com", "r01@example.com"),
            comment="Test Comment")

        record = directory.recordWithUID("resource01")
        self.assertEquals(record.fullName, "Resource #1")
        self.assertEquals(record.firstName, "First")
        self.assertEquals(record.lastName, "Last")
        self.assertEquals(set(record.shortNames), set(["resource01", "r01"]))
        self.assertEquals(record.emailAddresses,
            set(["resource01@example.com", "r01@example.com"]))
        self.assertEquals(record.extras['comment'], "Test Comment")

        # Make sure old records are still there:
        record = directory.recordWithUID("location01")
        self.assertNotEquals(record, None)

    def test_createDuplicateRecord(self):
        directory = getDirectory()

        directory.createRecord("resources", guid="resource01", shortNames=("resource01",), uid="resource01")
        self.assertRaises(DirectoryError, directory.createRecord, "resources", guid="resource01", shortNames=("resource01",), uid="resource01")

    def test_missingShortNames(self):
        directory = getDirectory()

        directory.createRecord("resources", guid="resource01")

        record = directory.recordWithUID("resource01")
        self.assertEquals(record.shortNames[0], "resource01")

        directory.updateRecord("resources", guid="resource01",
            fullName="Resource #1")

        record = directory.recordWithUID("resource01")
        self.assertEquals(record.shortNames[0], "resource01")
        self.assertEquals(record.fullName, "Resource #1")

    def test_missingGUID(self):
        directory = getDirectory()

        record = directory.createRecord("resources")

        self.assertEquals(record.shortNames[0], record.guid)
