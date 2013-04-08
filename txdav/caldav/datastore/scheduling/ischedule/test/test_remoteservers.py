##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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

from twisted.python.filepath import FilePath
from txdav.caldav.datastore.scheduling.ischedule.remoteservers import IScheduleServersParser
import twistedcaldav.test.util

class Test_IScheduleServersParser(twistedcaldav.test.util.TestCase):
    """
    Test L{IScheduleServersParser} implementation.
    """

    def test_readXML(self):

        fp = FilePath(self.mktemp())
        fp.open("w").write(
"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE servers SYSTEM "servertoserver.dtd">
<servers>
  <server>
    <uri>https://localhost:8543/inbox</uri>
    <allow-requests-from/>
    <allow-requests-to/>
    <domains>
        <domain>example.org</domain>
    </domains>
    <hosts>
        <host>127.0.0.1</host>
    </hosts>
  </server>
</servers>
"""
)

        parser = IScheduleServersParser(fp)
        self.assertEqual(len(parser.servers), 1)
