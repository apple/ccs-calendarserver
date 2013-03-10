##
# Copyright (c) 2008-2013 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import TestCase
from twistedcaldav.test.util import xmlFile
from txdav.common.datastore.test.util import buildStore
from calendarserver.tap.util import getRootResource
from twistedcaldav.config import config
from twistedcaldav.scheduling.imip.mailgateway import MailGatewayTokensDatabase
from twistedcaldav.scheduling.imip.mailgateway import migrateTokensToStore


class MailGatewayTokenDBTests(TestCase):

    @inlineCallbacks
    def setUp(self):
        super(MailGatewayTokenDBTests, self).setUp()

        self.store = yield buildStore(self, None)
        self.patch(config.DirectoryService.params, "xmlFile", xmlFile)
        self.root = getRootResource(config, self.store)
        self.directory = self.root.getDirectory()

    @inlineCallbacks
    def test_migrate(self):
        self.path = self.mktemp()
        os.mkdir(self.path)
        oldDB = MailGatewayTokensDatabase(self.path)
        oldDB.createToken("urn:uuid:user01", "mailto:attendee@example.com",
            "icaluid1", token="token1")
        yield migrateTokensToStore(self.path, self.store)
        txn = self.store.newTransaction()
        results = yield (txn.imipLookupByToken("token1"))
        organizer, attendee, icaluid = results[0]
        yield txn.commit()
        self.assertEquals(organizer, "urn:uuid:user01")
        self.assertEquals(attendee, "mailto:attendee@example.com")
        self.assertEquals(icaluid, "icaluid1")

