##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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
import os

from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks

import twistedcaldav.directory.test.util
from twistedcaldav.directory.sudo import SudoDirectoryService

plistFile = FilePath(os.path.join(os.path.dirname(__file__), "sudoers.plist"))
plistFile2 = FilePath(os.path.join(os.path.dirname(__file__), "sudoers2.plist"))

class SudoTestCase(
    twistedcaldav.directory.test.util.BasicTestCase,
    twistedcaldav.directory.test.util.DigestTestCase
):
    """
    Test the Sudo Directory Service
    """

    recordTypes = set(('sudoers',))
    recordType = 'sudoers'

    sudoers = {
        'alice': {'password': 'alice',},
    }

    locations = {}

    def plistFile(self):
        if not hasattr(self, "_plistFile"):
            self._plistFile = FilePath(self.mktemp())
            plistFile.copyTo(self._plistFile)
        return self._plistFile

    def service(self):
        service = SudoDirectoryService(self.plistFile())
        service.realmName = "test realm"
        return service

    @inlineCallbacks
    def test_listRecords(self):
        for record in (yield self.service().listRecords(self.recordType)):
            self.failUnless(record.shortNames[0] in self.sudoers)
            self.assertEqual(self.sudoers[record.shortNames[0]]['password'],
                             record.password)

    @inlineCallbacks
    def test_recordWithShortName(self):
        service = self.service()

        record = (yield service.recordWithShortName(self.recordType, 'alice'))
        self.assertEquals(record.password, 'alice')

        record = (yield service.recordWithShortName(self.recordType, 'bob'))
        self.failIf(record)

    @inlineCallbacks
    def test_calendaringDisabled(self):
        service = self.service()

        record = (yield service.recordWithShortName(self.recordType, 'alice'))

        self.failIf(record.enabledForCalendaring,
                    "sudoers should have enabledForCalendaring=False")
