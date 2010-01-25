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

from twext.python.plistlib import writePlist

from twistedcaldav.log import logLevelForNamespace
from twistedcaldav.config import config, ConfigDict
from twistedcaldav.static import CalDAVFile
from twistedcaldav.stdconfig import DEFAULT_CONFIG, PListConfigProvider
from twistedcaldav.test.util import TestCase

testConfig = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

  <key>ResponseCompression</key>
  <false/>

  <key>HTTPPort</key>
  <integer>8008</integer>

  <key>DefaultLogLevel</key>
  <string>info</string>
  <key>LogLevels</key>
  <dict>
    <key>some.namespace</key>
    <string>debug</string>
  </dict>

</dict>
</plist>
"""

def _testResponseCompression(testCase):
    testCase.assertEquals(config.ResponseCompression, False)


class ConfigTests(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        config.setProvider(PListConfigProvider(DEFAULT_CONFIG))
        self.testConfig = self.mktemp()
        open(self.testConfig, "w").write(testConfig)

    def tearDown(self):
        config.setDefaults(DEFAULT_CONFIG)
        config.reset()
        config.update(None) # Make sure the update hooks get called

    def testDefaults(self):
        for key, value in DEFAULT_CONFIG.iteritems():
            self.assertEquals(getattr(config, key), value)

    def testLoadConfig(self):
        self.assertEquals(config.ResponseCompression, True)

        config.load(self.testConfig)

        self.assertEquals(config.ResponseCompression, False)

    def testScoping(self):
        self.assertEquals(config.ResponseCompression, True)

        config.load(self.testConfig)

        self.assertEquals(config.ResponseCompression, False)

        _testResponseCompression(self)

    def testReloading(self):
        self.assertEquals(config.HTTPPort, 0)

        config.load(self.testConfig)

        self.assertEquals(config.HTTPPort, 8008)

        writePlist({}, self.testConfig)

        config.reload()

        self.assertEquals(config.HTTPPort, 0)

    def testUpdateAndReload(self):
        self.assertEquals(config.HTTPPort, 0)

        config.load(self.testConfig)

        self.assertEquals(config.HTTPPort, 8008)

        config.update({"HTTPPort": 80})

        self.assertEquals(config.HTTPPort, 80)

        config.reload()

        self.assertEquals(config.HTTPPort, 8008)

    def testSetAttr(self):
        self.assertNotIn("BindAddresses", config.__dict__)

        config.BindAddresses = ["127.0.0.1"]

        self.assertNotIn("BindAddresses", config.__dict__)

        self.assertEquals(config.BindAddresses, ["127.0.0.1"])

    def testUpdating(self):
        self.assertEquals(config.SSLPort, 0)

        config.update({"SSLPort": 8443})

        self.assertEquals(config.SSLPort, 8443)

    def testMerge(self):
        self.assertEquals(config.MultiProcess.StaggeredStartup.Enabled, False)

        config.update({"MultiProcess": {}})

        self.assertEquals(config.MultiProcess.StaggeredStartup.Enabled, False)

    def testDirectoryService_noChange(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {}})

        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "/etc/caldavd/accounts.xml")

    def testDirectoryService_sameType(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.xmlfile.XMLDirectoryService"}})

        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "/etc/caldavd/accounts.xml")

    def testDirectoryService_newType(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.appleopendirectory.OpenDirectoryService"}})

        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.appleopendirectory.OpenDirectoryService")
        self.assertNotIn("xmlFile", config.DirectoryService.params)
        self.assertEquals(config.DirectoryService.params.node, "/Search")

    def testDirectoryService_newParam(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.appleopendirectory.OpenDirectoryService"}})

        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.appleopendirectory.OpenDirectoryService")
        self.assertEquals(config.DirectoryService.params.node, "/Search")

    def testDirectoryService_unknownType(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "/etc/caldavd/accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.test.test_config.SuperDuperAwesomeService"}})

        #self.assertEquals(
        #    config.DirectoryService.params,
        #    SuperDuperAwesomeService.defaultParameters
        #)

    testDirectoryService_unknownType.todo = "unimplemented"

    def testUpdateDefaults(self):
        self.assertEquals(config.SSLPort, 0)

        config.load(self.testConfig)

        config.updateDefaults({"SSLPort": 8009})

        self.assertEquals(config.SSLPort, 8009)

        config.reload()

        self.assertEquals(config.SSLPort, 8009)

        config.updateDefaults({"SSLPort": 0})

    def testMergeDefaults(self):
        config.updateDefaults({"MultiProcess": {}})

        self.assertEquals(config._provider.getDefaults().MultiProcess.StaggeredStartup.Enabled, False)

    def testSetDefaults(self):
        config.updateDefaults({"SSLPort": 8443})

        config.setDefaults(DEFAULT_CONFIG)

        config.reload()

        self.assertEquals(config.SSLPort, 0)

    def testCopiesDefaults(self):
        config.updateDefaults({"Foo": "bar"})

        self.assertNotIn("Foo", DEFAULT_CONFIG)

    def testComplianceClasses(self):
        resource = CalDAVFile("/")
        
        config.EnableProxyPrincipals = True
        self.assertTrue("calendar-proxy" in resource.davComplianceClasses())
        
        config.EnableProxyPrincipals = False
        self.assertTrue("calendar-proxy" not in resource.davComplianceClasses())

    def test_logging(self):
        """
        Logging module configures properly.
        """
        config.setDefaults(DEFAULT_CONFIG)
        config.reload()

        self.assertEquals(logLevelForNamespace(None), "warn")
        self.assertEquals(logLevelForNamespace("some.namespace"), "warn")

        config.load(self.testConfig)

        self.assertEquals(logLevelForNamespace(None), "info")
        self.assertEquals(logLevelForNamespace("some.namespace"), "debug")

        writePlist({}, self.testConfig)
        config.reload()

        self.assertEquals(logLevelForNamespace(None), "warn")
        self.assertEquals(logLevelForNamespace("some.namespace"), "warn")

    def test_ConfigDict(self):
        configDict = ConfigDict({
            "a": "A",
            "b": "B",
            "c": "C",
        })

        # Test either syntax inbound
        configDict["d"] = "D"
        configDict.e = "E"

        # Test either syntax outbound
        for key in "abcde":
            value = key.upper()

            self.assertEquals(configDict[key], value)
            self.assertEquals(configDict.get(key), value)
            self.assertEquals(getattr(configDict, key), value)

            self.assertIn(key, configDict)
            self.assertTrue(hasattr(configDict, key))

        self.assertEquals(configDict.a, "A")
        self.assertEquals(configDict.d, "D")
        self.assertEquals(configDict.e, "E")

        # Test either syntax for delete
        del configDict["d"]
        delattr(configDict, "e")

        # Test either syntax for absence
        for key in "de":
            self.assertNotIn(key, configDict)
            self.assertFalse(hasattr(configDict, key))
            self.assertRaises(KeyError, lambda: configDict[key])
            self.assertRaises(AttributeError, getattr, configDict, key)

        self.assertRaises(AttributeError, lambda: configDict.e)
        self.assertRaises(AttributeError, lambda: configDict.f)

        # Keys may not begin with "_" in dict syntax
        def set():
            configDict["_x"] = "X"
        self.assertRaises(KeyError, set)

        # But attr syntax is OK
        configDict._x = "X"
        self.assertEquals(configDict._x, "X")
