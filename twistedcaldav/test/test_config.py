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

from twistedcaldav.config import config, defaultConfig, ConfigurationError
from twistedcaldav.static import CalDAVFile

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

def _testVerbose(testCase):
    from twistedcaldav.config import config
    testCase.assertEquals(config.Verbose, True)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        config.update(defaultConfig)
        self.testConfig = self.mktemp()
        open(self.testConfig, 'w').write(testConfig)

    def tearDown(self):
        config.setDefaults(defaultConfig)
        config.loadConfig(None)
        config.reload()

    def testDefaults(self):
        for key, value in defaultConfig.iteritems():
            self.assertEquals(getattr(config, key), value)

    def testLoadConfig(self):
        self.assertEquals(config.Verbose, False)

        config.loadConfig(self.testConfig)

        self.assertEquals(config.Verbose, True)

    def testScoping(self):
        self.assertEquals(config.Verbose, False)

        config.loadConfig(self.testConfig)

        self.assertEquals(config.Verbose, True)

        _testVerbose(self)

    def testReloading(self):
        self.assertEquals(config.HTTPPort, 0)

        config.loadConfig(self.testConfig)

        self.assertEquals(config.HTTPPort, 8008)

        writePlist({}, self.testConfig)

        config.reload()

        self.assertEquals(config.HTTPPort, 0)

    def testUpdateAndReload(self):
        self.assertEquals(config.HTTPPort, 0)

        config.loadConfig(self.testConfig)

        self.assertEquals(config.HTTPPort, 8008)

        config.update({'HTTPPort': 80})

        self.assertEquals(config.HTTPPort, 80)

        config.reload()

        self.assertEquals(config.HTTPPort, 8008)

    def testSetAttr(self):
        self.assertNotIn('BindAddresses', config.__dict__)

        config.BindAddresses = ['127.0.0.1']

        self.assertNotIn('BindAddresses', config.__dict__)

        self.assertEquals(config.BindAddresses, ['127.0.0.1'])

    def testUpdating(self):
        self.assertEquals(config.SSLPort, 0)

        config.update({'SSLPort': 8443})

        self.assertEquals(config.SSLPort, 8443)

    def testMerge(self):
        self.assertEquals(config.MultiProcess["LoadBalancer"]["Enabled"], True)

        config.update({'MultiProcess': {}})

        self.assertEquals(config.MultiProcess["LoadBalancer"]["Enabled"], True)

    def testDirectoryService_noChange(self):
        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["xmlFile"], "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {}})

        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["xmlFile"], "/etc/caldavd/accounts.xml")

    def testDirectoryService_sameType(self):
        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["xmlFile"], "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.xmlfile.XMLDirectoryService"}})

        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["xmlFile"], "/etc/caldavd/accounts.xml")

    def testDirectoryService_newType(self):
        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["xmlFile"], "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.appleopendirectory.OpenDirectoryService"}})

        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.appleopendirectory.OpenDirectoryService")
        self.assertNotIn("xmlFile", config.DirectoryService["params"])
        self.assertEquals(config.DirectoryService["params"]["node"], "/Search")
        self.assertEquals(config.DirectoryService["params"]["requireComputerRecord"], True)

    def testDirectoryService_newParam(self):
        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["xmlFile"], "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.appleopendirectory.OpenDirectoryService"}})
        config.update({"DirectoryService": {"params": {"requireComputerRecord": False}}})

        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.appleopendirectory.OpenDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["node"], "/Search")
        self.assertEquals(config.DirectoryService["params"]["requireComputerRecord"], False)

    def testDirectoryService_badParam(self):
        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["xmlFile"], "/etc/caldavd/accounts.xml")

        self.assertRaises(ConfigurationError, config.update, {"DirectoryService": {"params": {"requireComputerRecord": False}}})

    def testDirectoryService_unknownType(self):
        self.assertEquals(config.DirectoryService["type"], "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService["params"]["xmlFile"], "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.test.test_config.SuperDuperAwesomeService"}})

        self.assertEquals(
            config.DirectoryService["params"],
            SuperDuperAwesomeService.defaultParameters
        )

    testDirectoryService_unknownType.todo = "unimplemented"

    def testUpdateDefaults(self):
        self.assertEquals(config.SSLPort, 0)

        config.loadConfig(self.testConfig)

        config.updateDefaults({'SSLPort': 8009})

        self.assertEquals(config.SSLPort, 8009)

        config.reload()

        self.assertEquals(config.SSLPort, 8009)

        config.updateDefaults({'SSLPort': 0})

    def testMergeDefaults(self):
        config.updateDefaults({'MultiProcess': {}})

        self.assertEquals(config._defaults["MultiProcess"]["LoadBalancer"]["Enabled"], True)

    def testSetDefaults(self):
        config.updateDefaults({'SSLPort': 8443})

        config.setDefaults(defaultConfig)

        config.reload()

        self.assertEquals(config.SSLPort, 0)

    def testCopiesDefaults(self):
        config.updateDefaults({'Foo': 'bar'})

        self.assertNotIn('Foo', defaultConfig)

    def testComplianceClasses(self):
        
        resource = CalDAVFile("/")
        
        config.EnableProxyPrincipals = True
        self.assertTrue("calendar-proxy" in resource.davComplianceClasses())
        
        config.EnableProxyPrincipals = False
        self.assertTrue("calendar-proxy" not in resource.davComplianceClasses())
        