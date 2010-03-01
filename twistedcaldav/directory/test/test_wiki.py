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

from twistedcaldav.test.util import TestCase
from twistedcaldav.directory.wiki import WikiDirectoryService, WikiDirectoryRecord

class WikiTestCase(TestCase):
    """
    Test the Wiki Directory Service
    """

    def test_enabled(self):
        service = WikiDirectoryService()
        service.realmName = "Test"
        record = WikiDirectoryRecord(service,
            WikiDirectoryService.recordType_wikis,
            "test",
            None
        )
        self.assertTrue(record.enabled)
        self.assertTrue(record.enabledForCalendaring)
