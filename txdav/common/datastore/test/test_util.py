##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

"""
Tests for L{txdav.common.datastore.util}.
"""

from twisted.trial.unittest import TestCase
from twext.python.filepath import CachingFilePath

from twisted.application.service import Service, MultiService
from txdav.common.datastore.util import UpgradeToDatabaseService
from txdav.common.datastore.file import CommonDataStore
from txdav.common.datastore.test.util import theStoreBuilder, \
    populateCalendarsFrom
from txdav.caldav.datastore.test.common import StubNotifierFactory, CommonTests
from twisted.internet.defer import inlineCallbacks


class HomeMigrationTests(TestCase):
    """
    Tests for L{UpgradeToDatabaseService}.
    """

    @inlineCallbacks
    def setUp(self):
        """
        Set up two stores to migrate between.
        """
        # Add some files to the file store.
        self.filesPath = CachingFilePath(self.mktemp())
        self.filesPath.createDirectory()
        fileStore = CommonDataStore(
            self.filesPath, StubNotifierFactory(), True, True
        )
        self.sqlStore = yield theStoreBuilder.buildStore(
            self, StubNotifierFactory()
        )
        self.stubService = Service()
        self.topService = MultiService()
        self.upgrader = UpgradeToDatabaseService(
            fileStore, self.sqlStore, self.stubService
        )
        self.upgrader.setServiceParent(self.topService)
        requirements = CommonTests.requirements
        populateCalendarsFrom(requirements, fileStore)
        self.filesPath.child("calendars").child(
            "__uids__").child("ho").child("me").child("home1").child(
            ".some-extra-data").setContent("some extra data")


    def test_upgradeCalendarHomes(self):
        """
        L{UpgradeToDatabaseService.startService} will do the upgrade, then
        start its dependent service by adding it to its service hierarchy.
        """
        self.topService.startService()
        # XXX asyncify for attachment migration
        self.assertEquals(self.stubService.running, True)
        txn = self.sqlStore.newTransaction()
        self.addCleanup(txn.commit)
        for uid in CommonTests.requirements:
            if CommonTests.requirements[uid] is not None:
                self.assertNotIdentical(None, txn.calendarHomeWithUID(uid))
        # Un-migrated data should be preserved.
        self.assertEquals(self.filesPath.child("calendars-migrated").child(
            "__uids__").child("ho").child("me").child("home1").child(
                ".some-extra-data").getContent(),
                "some extra data"
        )

