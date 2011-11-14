##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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

class ResourcesTestCase(TestCase):

    def setUp(self):
        super(ResourcesTestCase, self).setUp()

        testRoot = os.path.join(".", os.path.dirname(__file__), "resources")

        xmlFile = os.path.join(testRoot, "users-groups.xml")
        config.DirectoryService.params.xmlFile = xmlFile

        xmlFile = os.path.join(testRoot, "resources-locations.xml")
        config.ResourceService.params.xmlFile = xmlFile
        config.ResourceService.Enabled = True

        xmlFile = os.path.join(testRoot, "augments.xml")
        config.AugmentService.type = "twistedcaldav.directory.augment.AugmentXMLDB"
        config.AugmentService.params.xmlFiles = (xmlFile,)

# Uh, what's this testing?
#    def test_loadConfig(self):
#        directory = getDirectory()

    def test_recordInPrimaryDirectory(self):
        directory = getDirectory()

        # Look up a user, which comes out of primary directory service
        record = directory.recordWithUID("user01")
        self.assertNotEquals(record, None)

    def test_recordInSupplementalDirectory(self):
        directory = getDirectory()

        # Look up a resource, which comes out of locations/resources service
        record = directory.recordWithUID("resource01")
        self.assertNotEquals(record, None)

    def test_augments(self):
        directory = getDirectory()

        # Primary directory
        record = directory.recordWithUID("user01")
        self.assertEquals(record.enabled, True)
        self.assertEquals(record.enabledForCalendaring, True)
        record = directory.recordWithUID("user02")
        self.assertEquals(record.enabled, False)
        self.assertEquals(record.enabledForCalendaring, False)

        # Supplemental directory
        record = directory.recordWithUID("resource01")
        self.assertEquals(record.enabled, True)
        self.assertEquals(record.enabledForCalendaring, True)
        self.assertEquals(record.autoSchedule, True)
        record = directory.recordWithUID("resource02")
        self.assertEquals(record.enabled, False)
        self.assertEquals(record.enabledForCalendaring, False)
        self.assertEquals(record.autoSchedule, False)
