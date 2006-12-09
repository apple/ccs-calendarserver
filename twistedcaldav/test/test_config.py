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
# DRI: David Reid, dreid@apple.com
##

from twisted.trial import unittest

from twistedcaldav.config import config, defaultConfig, parseConfig

testConfig = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Verbose</key>
  <true/>
</dict>
</plist>
"""

class ConfigTests(unittest.TestCase):
    def setUp(self):
        config.update(defaultConfig)
        self.testConfig = self.mktemp()
        open(self.testConfig, 'w').write(testConfig)

    def testDefaults(self):
        for key, value in defaultConfig.iteritems():
            self.failUnless(key in config.__dict__)
            self.assertEquals(config.__dict__[key], value)

    def testParseConfig(self):
        self.assertEquals(config.Verbose, False)

        parseConfig(self.testConfig)

        self.assertEquals(config.Verbose, True)
    
    def testScoping(self):
        def getVerbose():
            self.assertEquals(config.Verbose, True)

        self.assertEquals(config.Verbose, False)

        parseConfig(self.testConfig)

        self.assertEquals(config.Verbose, True)

        getVerbose()
