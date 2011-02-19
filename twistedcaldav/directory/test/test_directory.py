##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

from twistedcaldav.test.util import TestCase
from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord

def StubCheckSACL(cls, username, service):
    services = {
        "calendar" : ["amanda", "betty"],
        "addressbook" : ["amanda", "carlene"],
    }
    if username in services[service]:
        return 0
    return 1

class SALCTests(TestCase):

    def setUp(self):
        self.patch(DirectoryRecord, "CheckSACL", StubCheckSACL)
        self.patch(config, "EnableSACLs", True)
        self.service = DirectoryService()
        self.service.setRealm("test")
        self.service.baseGUID = "0E8E6EC2-8E52-4FF3-8F62-6F398B08A498"


    def test_applySACLs(self):
        """
        Users not in calendar SACL will have enabledForCalendaring set to
        False.
        Users not in addressbook SACL will have enabledForAddressBooks set to
        False.
        """

        data = [
            ("amanda",  True,  True,),
            ("betty",   True,  False,),
            ("carlene", False, True,),
            ("daniel",  False, False,),
        ]
        for username, cal, ab in data:
            record = DirectoryRecord(self.service, "users", None, (username,),
                enabledForCalendaring=True, enabledForAddressBooks=True)
            record.applySACLs()
            self.assertEquals(record.enabledForCalendaring, cal)
            self.assertEquals(record.enabledForAddressBooks, ab)
