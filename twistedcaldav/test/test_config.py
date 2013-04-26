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

from twext.python.plistlib import writePlist #@UnresolvedImport
from twext.python.log import logLevelForNamespace

from twistedcaldav.config import config, ConfigDict, mergeData
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.stdconfig import DEFAULT_CONFIG, PListConfigProvider,\
    RELATIVE_PATHS
from twistedcaldav.test.util import TestCase
import socket

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

  <key>Scheduling</key>
  <dict>
    <key>iMIP</key>
    <dict>
      <key>Password</key>
      <string>imip</string>
      <key>Sending</key>
      <dict>
          <key>Password</key>
          <string>sending</string>
      </dict>
      <key>Receiving</key>
      <dict>
          <key>Password</key>
          <string>receiving</string>
      </dict>
    </dict>
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

    def testDefaults(self):
        for key, value in DEFAULT_CONFIG.iteritems():
            if key in ("ServerHostName", "Notifications", "MultiProcess",
                "Postgres"):
                # Value is calculated and may vary
                continue
            for item in RELATIVE_PATHS:
                item = item[1]
                if isinstance(item, str):
                    item = (item,)
                if key == item[0]:
                    if len(item) == 1:
                        value = getattr(config, key)
                    else:
                        value[item[1]] = getattr(config, key)[item[1]]

            self.assertEquals(
                getattr(config, key), value,
                "config[%r] == %r, expected %r"
                % (key, getattr(config, key), value)
            )

    def testLoadConfig(self):
        self.assertEquals(config.ResponseCompression, True)

        config.load(self.testConfig)

        self.assertEquals(config.ResponseCompression, False)

    def testScoping(self):
        self.assertEquals(config.ResponseCompression, True)

        config.load(self.testConfig)

        self.assertEquals(config.ResponseCompression, False)

        _testResponseCompression(self)

    def _myUpdateHook(self, data, reloading=False):
        # A stub hook to record the value of reloading=
        self._reloadingValue = reloading

    def testReloading(self):
        self.assertEquals(config.HTTPPort, 0)

        config.load(self.testConfig)

        self.assertEquals(config.HTTPPort, 8008)

        writePlist({}, self.testConfig)

        self._reloadingValue = None
        config.addPostUpdateHooks([self._myUpdateHook])
        config.reload()

        # Make sure reloading=True was passed to the update hooks
        self.assertTrue(self._reloadingValue)

        self.assertEquals(config.HTTPPort, 0)

    def testUpdateAndReload(self):
        self.assertEquals(config.HTTPPort, 0)

        config.load(self.testConfig)

        self.assertEquals(config.HTTPPort, 8008)

        config.update({"HTTPPort": 80})

        self.assertEquals(config.HTTPPort, 80)

        config.reload()

        self.assertEquals(config.HTTPPort, 8008)

    def testPreserveAcrossReload(self):
        self.assertEquals(config.Scheduling.iMIP.Sending.Password, "")
        self.assertEquals(config.Scheduling.iMIP.Receiving.Password, "")

        config.load(self.testConfig)

        self.assertEquals(config.Scheduling.iMIP.Sending.Password, "sending")
        self.assertEquals(config.Scheduling.iMIP.Receiving.Password, "receiving")

        writePlist({}, self.testConfig)

        config.reload()

        self.assertEquals(config.Scheduling.iMIP.Sending.Password, "sending")
        self.assertEquals(config.Scheduling.iMIP.Receiving.Password, "receiving")

    def testSetAttr(self):
        self.assertNotIn("BindAddresses", config.__dict__)

        config.BindAddresses = ["127.0.0.1"]

        self.assertNotIn("BindAddresses", config.__dict__)

        self.assertEquals(config.BindAddresses, ["127.0.0.1"])

    def testDirty(self):
        config.__dict__["_dirty"] = False
        self.assertEquals(config.__dict__["_dirty"], False)

        config.foo = "bar"
        self.assertEquals(config.__dict__["_dirty"], True)

        config.__dict__["_dirty"] = False
        self.assertEquals(config.__dict__["_dirty"], False)

        config._foo = "bar"
        self.assertEquals(config.__dict__["_dirty"], False)


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
        self.assertEquals(config.DirectoryService.params.xmlFile, "accounts.xml")

        config.update({"DirectoryService": {}})

        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "accounts.xml")

    def testDirectoryService_sameType(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.xmlfile.XMLDirectoryService"}})

        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "accounts.xml")

    def testDirectoryService_newType(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.appleopendirectory.OpenDirectoryService"}})

        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.appleopendirectory.OpenDirectoryService")
        self.assertNotIn("xmlFile", config.DirectoryService.params)
        self.assertEquals(config.DirectoryService.params.node, "/Search")

    def testDirectoryService_newParam(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "accounts.xml")

        config.update({"DirectoryService": {"type": "twistedcaldav.directory.appleopendirectory.OpenDirectoryService"}})

        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.appleopendirectory.OpenDirectoryService")
        self.assertEquals(config.DirectoryService.params.node, "/Search")

    def testDirectoryService_unknownType(self):
        self.assertEquals(config.DirectoryService.type, "twistedcaldav.directory.xmlfile.XMLDirectoryService")
        self.assertEquals(config.DirectoryService.params.xmlFile, "accounts.xml")

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
        resource = CalDAVResource()
        
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

    def test_mergeData(self):
        """
        Verify we don't lose keys which are present in the old but not
        replaced in the new.
        """
        old = ConfigDict({
            "Scheduling" : ConfigDict({
                "iMIP" : ConfigDict({
                    "Enabled" : True,
                    "Receiving" : ConfigDict({
                        "Username" : "xyzzy",
                        "Server" : "example.com",
                    }),
                    "Sending" : ConfigDict({
                        "Username" : "plugh",
                    }),
                    "AddressPatterns" : ["mailto:.*"],
                }),
            }),
        })
        new = ConfigDict({
            "Scheduling" : ConfigDict({
                "iMIP" : ConfigDict({
                    "Enabled" : False,
                    "Receiving" : ConfigDict({
                        "Username" : "changed",
                    }),
                }),
            }),
        })
        mergeData(old, new)
        self.assertEquals(old.Scheduling.iMIP.Receiving.Server, "example.com")
        self.assertEquals(old.Scheduling.iMIP.Sending.Username, "plugh")

    def test_SimpleInclude(self):

        testConfigMaster = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

  <key>ResponseCompression</key>
  <false/>

  <key>ServerRoot</key>
  <string></string>

  <key>ConfigRoot</key>
  <string></string>

  <key>HTTPPort</key>
  <integer>8008</integer>

  <key>SSLPort</key>
  <integer>8443</integer>

  <key>DefaultLogLevel</key>
  <string>info</string>
  <key>LogLevels</key>
  <dict>
    <key>some.namespace</key>
    <string>debug</string>
  </dict>
  
  <key>Includes</key>
  <array>
      <string>%s</string>
  </array>

</dict>
</plist>
"""

        testConfigInclude = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

  <key>HTTPPort</key>
  <integer>9008</integer>

</dict>
</plist>
"""

        config.setProvider(PListConfigProvider(DEFAULT_CONFIG))

        self.testInclude = self.mktemp()
        open(self.testInclude, "w").write(testConfigInclude)

        self.testMaster = self.mktemp()
        open(self.testMaster, "w").write(testConfigMaster % (self.testInclude,))

        config.load(self.testMaster)
        self.assertEquals(config.HTTPPort, 9008)
        self.assertEquals(config.SSLPort, 8443)

    def test_FQDNInclude(self):

        testConfigMaster = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

  <key>ResponseCompression</key>
  <false/>

  <key>ServerRoot</key>
  <string></string>

  <key>ConfigRoot</key>
  <string></string>

  <key>HTTPPort</key>
  <integer>8008</integer>

  <key>SSLPort</key>
  <integer>8443</integer>

  <key>DefaultLogLevel</key>
  <string>info</string>
  <key>LogLevels</key>
  <dict>
    <key>some.namespace</key>
    <string>debug</string>
  </dict>
  
  <key>Includes</key>
  <array>
      <string>%s.$</string>
  </array>

</dict>
</plist>
"""

        testConfigInclude = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

  <key>HTTPPort</key>
  <integer>9008</integer>

</dict>
</plist>
"""

        config.setProvider(PListConfigProvider(DEFAULT_CONFIG))

        self.testIncludeRoot = self.mktemp()
        self.testInclude = self.testIncludeRoot + "." + socket.getfqdn()
        open(self.testInclude, "w").write(testConfigInclude)

        self.testMaster = self.mktemp()
        open(self.testMaster, "w").write(testConfigMaster % (self.testIncludeRoot,))

        config.load(self.testMaster)
        self.assertEquals(config.HTTPPort, 9008)
        self.assertEquals(config.SSLPort, 8443)

    def test_HostnameInclude(self):

        testConfigMaster = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

  <key>ResponseCompression</key>
  <false/>

  <key>ServerRoot</key>
  <string></string>

  <key>ConfigRoot</key>
  <string></string>

  <key>HTTPPort</key>
  <integer>8008</integer>

  <key>SSLPort</key>
  <integer>8443</integer>

  <key>DefaultLogLevel</key>
  <string>info</string>
  <key>LogLevels</key>
  <dict>
    <key>some.namespace</key>
    <string>debug</string>
  </dict>
  
  <key>Includes</key>
  <array>
      <string>%s.#</string>
  </array>

</dict>
</plist>
"""

        testConfigInclude = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

  <key>HTTPPort</key>
  <integer>9008</integer>

</dict>
</plist>
"""

        config.setProvider(PListConfigProvider(DEFAULT_CONFIG))

        self.testIncludeRoot = self.mktemp()
        self.testInclude = self.testIncludeRoot + "." + socket.gethostbyname(socket.getfqdn())
        open(self.testInclude, "w").write(testConfigInclude)

        self.testMaster = self.mktemp()
        open(self.testMaster, "w").write(testConfigMaster % (self.testIncludeRoot,))

        config.load(self.testMaster)
        self.assertEquals(config.HTTPPort, 9008)
        self.assertEquals(config.SSLPort, 8443)
