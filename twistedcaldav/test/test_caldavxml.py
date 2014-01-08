##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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

from twistedcaldav import caldavxml
import twistedcaldav.test.util

class CustomXML (twistedcaldav.test.util.TestCase):


    def test_TimeRange(self):

        self.assertRaises(ValueError, caldavxml.CalDAVTimeRangeElement)

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000Z")
        self.assertTrue(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(end="20110201T120000Z")
        self.assertTrue(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(end="20110201T120000")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(end="20110201")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000Z", end="20110202T120000Z")
        self.assertTrue(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000Z", end="20110202T120000")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000Z", end="20110202")
        self.assertFalse(tr.valid())
