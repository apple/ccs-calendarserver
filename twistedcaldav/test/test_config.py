##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

from twistedcaldav.py.plistlib import writePlist

from twistedcaldav.config import config, defaultConfig, parseConfig

testConfig = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Verbose</key>
  <true/>
  <key>HTTPPort</key>
  <integer>8008</integer>
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
            self.assertEquals(getattr(config, key), value)

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

    def testReloading(self):
        self.assertEquals(config.HTTPPort, None)

        parseConfig(self.testConfig)

        self.assertEquals(config.HTTPPort, 8008)

        writePlist({}, self.testConfig)

        config.reload()

        self.assertEquals(config.HTTPPort, None)

    def testUpdateAndReload(self):
        self.assertEquals(config.HTTPPort, None)

        parseConfig(self.testConfig)

        self.assertEquals(config.HTTPPort, 8008)

        config.update({'HTTPPort': 80})

        self.assertEquals(config.HTTPPort, 80)

        config.reload()

        self.assertEquals(config.HTTPPort, 8008)

    def testUpdating(self):
        self.assertEquals(config.SSLPort, None)

        config.update({'SSLPort': 8443})

        self.assertEquals(config.SSLPort, 8443)

    def testUpdateDefaults(self):
        self.assertEquals(config.SSLPort, None)

        parseConfig(self.testConfig)

        config.updateDefaults({'SSLPort': 8009})

        self.assertEquals(config.SSLPort, 8009)

        config.reload()

        self.assertEquals(config.SSLPort, 8009)

        config.updateDefaults({'SSLPort': None})
