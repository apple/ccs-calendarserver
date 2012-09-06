##
# Copyright (c) 2011-2012 Apple Inc. All rights reserved.
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

from twistedcaldav import customxml
import time
import twistedcaldav.test.util

class CustomXML (twistedcaldav.test.util.TestCase):


    def test_DTStamp(self):
        
        dtstamp = customxml.DTStamp()
        now = time.time()
        now_tm = time.gmtime( now )
        self.assertEqual(str(dtstamp)[:4], "%s" % (now_tm.tm_year,))
