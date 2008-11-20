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
##

try:
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryService
except ImportError:
    pass
else:
    from twistedcaldav.test.util import TestCase

    class ODResourceInfoParse (TestCase):

        plist_good_false = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <dict>
        <key>AutoAcceptsInvitation</key>
        <false/>
        <key>Label</key>
        <string>Location</string>
        <key>CalendaringDelegate</key>
        <string>1234-GUID-5678</string>
        <key>ReadOnlyCalendaringDelegate</key>
        <string>1234-GUID-5679</string>
    </dict>
</dict>
</plist>
"""

        plist_good_true = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <dict>
        <key>AutoAcceptsInvitation</key>
        <true/>
        <key>Label</key>
        <string>Location</string>
        <key>CalendaringDelegate</key>
        <string></string>
        <key>ReadOnlyCalendaringDelegate</key>
        <string></string>
    </dict>
</dict>
</plist>
"""

        plist_good_missing = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <dict>
        <key>Label</key>
        <string>Location</string>
    </dict>
</dict>
</plist>
"""

        plist_bad = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <string>bogus</string>
</dict>
</plist>
"""

        plist_wrong = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.YellowPagesFramework</key>
    <dict>
        <key>AutoAcceptsInvitation</key>
        <true/>
        <key>Label</key>
        <string>Location</string>
        <key>CalendaringDelegate</key>
        <string>1234-GUID-5678</string>
        <key>ReadOnlyCalendaringDelegate</key>
        <string>1234-GUID-5679</string>
    </dict>
</dict>
</plist>
"""

        plist_invalid = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <string>bogus</string>
    <string>another bogon</string>
</dict>
</plist>
"""

        test_bool = (
            (plist_good_false, False, "1234-GUID-5678", "1234-GUID-5679"),
            (plist_good_true, True, "", ""),
            (plist_good_missing, False, None, None),
            (plist_wrong, False, None, None),
            (plist_bad, False, None, None),
            (plist_invalid, False, None, None),
        )

        def test_plists(self):
            service = OpenDirectoryService(node="/Search", dosetup=False)
            
            for item in ODResourceInfoParse.test_bool:
                item1, item2, item3 = service._parseResourceInfo(item[0], "guid", "name")
                self.assertEqual(item1, item[1])
                self.assertEqual(item2, item[2])
                self.assertEqual(item3, item[3])
