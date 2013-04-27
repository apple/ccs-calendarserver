##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Delete

from twisted.internet.defer import inlineCallbacks, succeed, returnValue
from twisted.trial.unittest import TestCase

from twistedcaldav.config import config

from txdav.caldav.datastore.sql import CalendarStoreFeatures
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.test.util import theStoreBuilder, \
    StubNotifierFactory
from txdav.common.datastore.upgrade.sql.others import attachment_migration
from txdav.common.datastore.upgrade.sql.upgrade import UpgradeDatabaseOtherStep

"""
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""


class AttachmentMigrationTests(TestCase):
    """
    Tests for L{UpgradeDatabaseSchemaStep}.
    """

    @inlineCallbacks
    def _initStore(self, enableManagedAttachments=True):
        """
        Build a store with certain bits cleaned out.
        """

        self.patch(config, "EnableManagedAttachments", enableManagedAttachments)

        store = yield theStoreBuilder.buildStore(
            self, StubNotifierFactory()
        )
        store.enableManagedAttachments = enableManagedAttachments

        txn = store.newTransaction()
        cs = schema.CALENDARSERVER
        yield Delete(
            From=cs,
            Where=cs.NAME == "MANAGED-ATTACHMENTS"
        ).on(txn)
        yield txn.commit()

        returnValue(store)


    @inlineCallbacks
    def test_upgradeFromEmptyDropbox(self):
        """
        Test L{attachment_migration.doUpgrade} when managed attachments is enabled and dropbox items do not exist.
        """

        didUpgrade = [False, ]
        def _hasDropboxAttachments(_self, txn):
            return succeed(False)
        self.patch(CalendarStoreFeatures, "hasDropboxAttachments", _hasDropboxAttachments)

        def _upgradeToManagedAttachments(_self, batchSize=10):
            didUpgrade[0] = True
            return succeed(None)
        self.patch(CalendarStoreFeatures, "upgradeToManagedAttachments", _upgradeToManagedAttachments)

        store = (yield self._initStore())

        upgrader = UpgradeDatabaseOtherStep(store)
        yield attachment_migration.doUpgrade(upgrader)
        self.assertFalse(didUpgrade[0])

        txn = upgrader.sqlStore.newTransaction()
        managed = (yield txn.calendarserverValue("MANAGED-ATTACHMENTS", raiseIfMissing=False))
        yield txn.commit()
        self.assertNotEqual(managed, None)


    @inlineCallbacks
    def test_upgradeFromDropboxOK(self):
        """
        Test L{attachment_migration.doUpgrade} when managed attachments is enabled and dropbox items exist.
        """

        didUpgrade = [False, ]
        def _hasDropboxAttachments(_self, txn):
            return succeed(True)
        self.patch(CalendarStoreFeatures, "hasDropboxAttachments", _hasDropboxAttachments)

        def _upgradeToManagedAttachments(_self, batchSize=10):
            didUpgrade[0] = True
            return succeed(None)
        self.patch(CalendarStoreFeatures, "upgradeToManagedAttachments", _upgradeToManagedAttachments)

        store = (yield self._initStore())

        upgrader = UpgradeDatabaseOtherStep(store)
        yield attachment_migration.doUpgrade(upgrader)
        self.assertTrue(didUpgrade[0])

        txn = upgrader.sqlStore.newTransaction()
        managed = (yield txn.calendarserverValue("MANAGED-ATTACHMENTS", raiseIfMissing=False))
        yield txn.commit()
        self.assertNotEqual(managed, None)


    @inlineCallbacks
    def test_upgradeAlreadyDone(self):
        """
        Test L{attachment_migration.doUpgrade} when managed attachments is enabled and migration already done.
        """

        didUpgrade = [False, ]
        def _hasDropboxAttachments(_self, txn):
            return succeed(True)
        self.patch(CalendarStoreFeatures, "hasDropboxAttachments", _hasDropboxAttachments)

        def _upgradeToManagedAttachments(_self, batchSize=10):
            didUpgrade[0] = True
            return succeed(None)
        self.patch(CalendarStoreFeatures, "upgradeToManagedAttachments", _upgradeToManagedAttachments)

        store = (yield self._initStore())
        txn = store.newTransaction()
        yield txn.setCalendarserverValue("MANAGED-ATTACHMENTS", "1")
        yield txn.commit()

        upgrader = UpgradeDatabaseOtherStep(store)
        yield attachment_migration.doUpgrade(upgrader)
        self.assertFalse(didUpgrade[0])

        txn = upgrader.sqlStore.newTransaction()
        managed = (yield txn.calendarserverValue("MANAGED-ATTACHMENTS", raiseIfMissing=False))
        yield txn.commit()
        self.assertNotEqual(managed, None)


    @inlineCallbacks
    def test_upgradeNotEnabled(self):
        """
        Test L{attachment_migration.doUpgrade} when managed attachments is disabled.
        """

        didUpgrade = [False, ]
        def _hasDropboxAttachments(_self, txn):
            return succeed(True)
        self.patch(CalendarStoreFeatures, "hasDropboxAttachments", _hasDropboxAttachments)

        def _upgradeToManagedAttachments(_self, batchSize=10):
            didUpgrade[0] = True
            return succeed(None)
        self.patch(CalendarStoreFeatures, "upgradeToManagedAttachments", _upgradeToManagedAttachments)

        store = (yield self._initStore(False))

        upgrader = UpgradeDatabaseOtherStep(store)
        yield attachment_migration.doUpgrade(upgrader)
        self.assertFalse(didUpgrade[0])

        txn = upgrader.sqlStore.newTransaction()
        managed = (yield txn.calendarserverValue("MANAGED-ATTACHMENTS", raiseIfMissing=False))
        yield txn.commit()
        self.assertEqual(managed, None)
