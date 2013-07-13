# -*- coding: utf-8 -*-
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

from cStringIO import StringIO

from twext.python.filepath import CachingFilePath as FilePath
from twisted.trial.unittest import TestCase

from twistedcaldav.config import Config, ConfigDict
from twistedcaldav.stdconfig import NoUnicodePlistParser, PListConfigProvider,\
    _updateDataStore, _updateMultiProcess
import twistedcaldav.stdconfig

nonASCIIValue = "→←"
nonASCIIPlist = "<plist version='1.0'><string>%s</string></plist>" % (
    nonASCIIValue,
)

nonASCIIConfigPList = """
<plist version="1.0">
  <dict>
    <key>DataRoot</key>
    <string>%s</string>
  </dict>
</plist>
""" % (nonASCIIValue,)

class ConfigParsingTests(TestCase):
    """
    Tests to verify the behavior of the configuration parser.
    """

    def test_noUnicodePListParser(self):
        """
        L{NoUnicodePlistParser.parse} retrieves non-ASCII property list values
        as (UTF-8 encoded) 'str' objects, so that a single type is consistently
        used regardless of the input data.
        """
        parser = NoUnicodePlistParser()
        self.assertEquals(parser.parse(StringIO(nonASCIIPlist)),
                          nonASCIIValue)


    def test_parseNonASCIIConfig(self):
        """
        Non-ASCII <string>s found as part of a configuration file will be
        retrieved as UTF-8 encoded 'str' objects, as parsed by
        L{NoUnicodePlistParser}.
        """
        cfg = Config(PListConfigProvider({"DataRoot": ""}))
        tempfile = FilePath(self.mktemp())
        tempfile.setContent(nonASCIIConfigPList)
        cfg.load(tempfile.path)
        self.assertEquals(cfg.DataRoot, nonASCIIValue)


    def test_relativeDefaultPaths(self):
        """
        The paths specified in the default configuration should be interpreted
        as relative to the paths specified in the configuration file.
        """
        cfg = Config(PListConfigProvider(
            {"AccountingLogRoot": "some-path",
             "LogRoot": "should-be-ignored"}))
        cfg.addPostUpdateHooks([_updateDataStore])
        tempfile = FilePath(self.mktemp())
        tempfile.setContent("<plist version='1.0'><dict>"
                            "<key>LogRoot</key><string>/some/root</string>"
                            "</dict></plist>")
        cfg.load(tempfile.path)
        self.assertEquals(cfg.AccountingLogRoot, "/some/root/some-path")
        tempfile.setContent("<plist version='1.0'><dict>"
                            "<key>LogRoot</key><string>/other/root</string>"
                            "</dict></plist>")
        cfg.load(tempfile.path)
        self.assertEquals(cfg.AccountingLogRoot, "/other/root/some-path")


    def test_includes(self):

        plist1 = """
<plist version="1.0">
  <dict>
    <key>ServerRoot</key>
    <string>/root</string>
    <key>DocumentRoot</key>
    <string>defaultdoc</string>
    <key>DataRoot</key>
    <string>defaultdata</string>
    <key>ConfigRoot</key>
    <string>defaultconfig</string>
    <key>LogRoot</key>
    <string>defaultlog</string>
    <key>RunRoot</key>
    <string>defaultrun</string>
    <key>Includes</key>
    <array>
        <string>%s</string>
    </array>
  </dict>
</plist>
"""

        plist2 = """
<plist version="1.0">
  <dict>
    <key>DataRoot</key>
    <string>overridedata</string>
  </dict>
</plist>
"""

        tempfile2 = FilePath(self.mktemp())
        tempfile2.setContent(plist2)

        tempfile1 = FilePath(self.mktemp())
        tempfile1.setContent(plist1 % (tempfile2.path,))

        cfg = Config(PListConfigProvider({
            "ServerRoot": "",
            "DocumentRoot": "",
            "DataRoot": "",
            "ConfigRoot": "",
            "LogRoot": "",
            "RunRoot": "",
            "Includes": [],
        }))
        cfg.addPostUpdateHooks([_updateDataStore])
        cfg.load(tempfile1.path)
        self.assertEquals(cfg.DocumentRoot, "/root/overridedata/defaultdoc")
        self.assertEquals(cfg.DataRoot, "/root/overridedata")


    def test_updateDataStore(self):
        configDict = {
            "ServerRoot" : "/a/b/c/",
        }
        _updateDataStore(configDict)
        self.assertEquals(configDict["ServerRoot"], "/a/b/c")


    def test_updateMultiProcess(self):
        def stubProcessCount(*args):
            return 3
        self.patch(twistedcaldav.stdconfig, "computeProcessCount", stubProcessCount)
        configDict = ConfigDict({
            "MultiProcess" : {
                "ProcessCount" : 0,
                "MinProcessCount" : 2,
                "PerCPU" : 1,
                "PerGB" : 1,
            },
            "Postgres" : {
                "ExtraConnections" : 5,
                "BuffersToConnectionsRatio" : 1.5,
            },
            "SharedConnectionPool" : False,
            "MaxDBConnectionsPerPool" : 10,
        })
        _updateMultiProcess(configDict)
        self.assertEquals(45, configDict.Postgres.MaxConnections)
        self.assertEquals(67, configDict.Postgres.SharedBuffers)
