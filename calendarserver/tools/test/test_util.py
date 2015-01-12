##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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
import tempfile
from twistedcaldav.test.util import TestCase
from twistedcaldav.config import ConfigurationError
from calendarserver.tools.util import loadConfig, checkDirectory

class UtilTestCase(TestCase):

    def test_loadConfig(self):
        testRoot = os.path.join(os.path.dirname(__file__), "util")
        configPath = os.path.join(testRoot, "caldavd.plist")
        config = loadConfig(configPath)
        self.assertEquals(config.EnableCalDAV, True)
        self.assertEquals(config.EnableCardDAV, True)


    def test_checkDirectory(self):
        tmpDir = tempfile.mkdtemp()
        tmpFile = os.path.join(tmpDir, "tmpFile")
        self.assertRaises(ConfigurationError, checkDirectory, tmpFile, "Test file")
        os.rmdir(tmpDir)
