##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

from txdav.caldav.datastore.scheduling.ischedule.localservers import (
    ServersDB, Server
)
from txdav.common.datastore.podding.resource import ConduitResource
from txdav.common.datastore.sql_tables import _HOME_STATUS_NORMAL, \
    _HOME_STATUS_EXTERNAL
from txdav.common.datastore.test.util import CommonCommonTests
from txdav.common.idirectoryservice import DirectoryRecordNotFoundError

import txweb2.dav.test.util


class ExternalHome(CommonCommonTests, txweb2.dav.test.util.TestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(ExternalHome, self).setUp()

        serversDB = ServersDB()
        serversDB.addServer(Server("A", "http://127.0.0.1", "A", True))
        serversDB.addServer(Server("B", "http://127.0.0.2", "B", False))

        yield self.buildStoreAndDirectory(serversDB=serversDB)

        self.site.resource.putChild("conduit", ConduitResource(self.site.resource, self.storeUnderTest()))


    @inlineCallbacks
    def test_validNormalHome(self):
        """
        Locally hosted homes are valid.
        """

        for i in range(1, 100):
            home = yield self.transactionUnderTest().calendarHomeWithUID("user{:02d}".format(i), create=True)
            self.assertTrue(home is not None)
            self.assertEqual(home._status, _HOME_STATUS_NORMAL)
            calendar = yield home.childWithName("calendar")
            self.assertTrue(calendar is not None)


    @inlineCallbacks
    def test_validExternalHome(self):
        """
        Externally hosted homes are valid.
        """

        for i in range(1, 100):
            home = yield self.transactionUnderTest().calendarHomeWithUID("puser{:02d}".format(i), create=True)
            self.assertTrue(home is not None)
            self.assertEqual(home._status, _HOME_STATUS_EXTERNAL)
            calendar = yield home.childWithName("calendar")
            self.assertTrue(calendar is None)


    @inlineCallbacks
    def test_invalidHome(self):
        """
        Homes are invalid.
        """

        yield self.assertFailure(self.transactionUnderTest().calendarHomeWithUID("buser01", create=True), DirectoryRecordNotFoundError)
