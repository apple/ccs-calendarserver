##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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

from unittest.case import TestCase
from twistedcaldav.dumpconfig import parseConfigItem, processConfig, \
    writeOrderedPlistToString
from collections import OrderedDict

class TestDumpConfig (TestCase):

    def test_parseConfigItem(self):
        """
        Make sure L{parseConfigItem} can parse the DEFAULT_* items
        """

        items = {
            "DEFAULT_SERVICE_PARAMS",
            "DEFAULT_RESOURCE_PARAMS",
            "DEFAULT_AUGMENT_PARAMS",
            "DEFAULT_DIRECTORY_ADDRESSBOOK_PARAMS",
            "DEFAULT_CONFIG",
        }

        for item in items:
            lines = parseConfigItem(item)
            self.assertNotEqual(len(lines), 0, msg="Failed {}".format(item))


    def test_writeOrderedPlistToString(self):
        """
        Make sure L{writeOrderedPlistToString} preserves key order
        """

        data = OrderedDict()
        data["KeyB"] = "1"
        data["KeyA"] = "2"
        data["KeyC"] = "3"
        data["KeyE"] = "4"
        data["KeyD"] = "5"

        plist = writeOrderedPlistToString(data)
        self.assertEqual(plist, """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>KeyB</key>
\t<string>1</string>

\t<key>KeyA</key>
\t<string>2</string>

\t<key>KeyC</key>
\t<string>3</string>

\t<key>KeyE</key>
\t<string>4</string>

\t<key>KeyD</key>
\t<string>5</string>
</dict>
</plist>
""")


    def test_plistWithComments(self):
        """
        Make sure L{writeOrderedPlistToString} preserves key order
        """

        data = OrderedDict()
        data["comment_1"] = "All about KeyB"
        data["KeyB"] = "1"
        data["section_2"] = "Details on KeyA & KeyC"
        data["comment_3"] = "All about KeyA"
        data["KeyA"] = "2"
        data["comment_4"] = "All about KeyC"
        data["KeyC"] = "3"

        plist = writeOrderedPlistToString(data)
        self.assertEqual(plist, """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<!-- All about KeyB -->
\t<key>KeyB</key>
\t<string>1</string>

\t<!-- Details on KeyA &amp; KeyC -->

\t<!-- All about KeyA -->
\t<key>KeyA</key>
\t<string>2</string>

\t<!-- All about KeyC -->
\t<key>KeyC</key>
\t<string>3</string>
</dict>
</plist>
""")


    def test_fullPlistDump(self):
        """
        Make sure a full dump of DEFAULT_CONFIG works
        """

        maps = {
            "DEFAULT_SERVICE_PARAMS": "",
            "DEFAULT_RESOURCE_PARAMS": "",
            "DEFAULT_AUGMENT_PARAMS": "",
            "DEFAULT_DIRECTORY_ADDRESSBOOK_PARAMS": "",
        }

        for item in maps.keys():
            lines = parseConfigItem(item)
            maps[item] = processConfig(lines, with_comments=True, verbose=False)

        # Generate the plist for the default config, substituting for the *_PARAMS items
        lines = parseConfigItem("DEFAULT_CONFIG")
        j = processConfig(lines, with_comments=True, verbose=False, substitutions=maps)
        result = writeOrderedPlistToString(j)
        self.assertIn('<plist version="1.0">', result)
