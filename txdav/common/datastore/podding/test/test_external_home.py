##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from txdav.caldav.datastore.scheduling.ischedule.localservers import Servers, \
    Server
from txdav.caldav.datastore.test.util import buildCalendarStore, \
    TestCalendarStoreDirectoryRecord
from txdav.common.datastore.podding.resource import ConduitResource
from txdav.common.datastore.sql_tables import _HOME_STATUS_NORMAL, \
    _HOME_STATUS_EXTERNAL
from txdav.common.datastore.test.util import CommonCommonTests
from txdav.common.idirectoryservice import DirectoryRecordNotFoundError

import twext.web2.dav.test.util


class ExternalHome(CommonCommonTests, twext.web2.dav.test.util.TestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(ExternalHome, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        self.directory = self._sqlCalendarStore.directoryService()

        for ctr in range(1, 100):
            self.directory.addRecord(TestCalendarStoreDirectoryRecord(
                "puser{:02d}".format(ctr),
                ("puser{:02d}".format(ctr),),
                "Puser {:02d}".format(ctr),
                frozenset((
                    "urn:uuid:puser{:02d}".format(ctr),
                    "mailto:puser{:02d}@example.com".format(ctr),
                )),
                thisServer=False,
            ))

        self.site.resource.putChild("conduit", ConduitResource(self.site.resource, self.storeUnderTest()))

        self.thisServer = Server("A", "http://127.0.0.1", "A", True)
        Servers.addServer(self.thisServer)


    def storeUnderTest(self):
        """
        Return a store for testing.
        """
        return self._sqlCalendarStore


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
