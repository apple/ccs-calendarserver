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

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from txdav.caldav.datastore.scheduling.imip.mailgateway import MailGatewayTokensDatabase
from txdav.caldav.datastore.scheduling.imip.mailgateway import migrateTokensToStore
from txdav.common.datastore.test.util import buildStore

import os


class MailGatewayTokenDBTests(unittest.TestCase):

    @inlineCallbacks
    def setUp(self):
        super(MailGatewayTokenDBTests, self).setUp()

        self.store = yield buildStore(self, None)
        self.directory = self.store.directoryService()


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
