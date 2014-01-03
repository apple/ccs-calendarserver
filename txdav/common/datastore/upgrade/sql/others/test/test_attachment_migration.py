##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Delete, Insert, Select, Count

from twisted.internet.defer import inlineCallbacks, succeed, returnValue

from twistedcaldav.config import config

from txdav.caldav.datastore.sql import CalendarStoreFeatures
from txdav.caldav.datastore.test.util import CommonStoreTests
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.test.util import theStoreBuilder, \
    StubNotifierFactory
from txdav.common.datastore.upgrade.sql.others import attachment_migration
from txdav.common.datastore.upgrade.sql.upgrade import UpgradeDatabaseOtherStep

import hashlib
import os

"""
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""


class AttachmentMigrationModeTests(CommonStoreTests):
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
            self, {"push": StubNotifierFactory()}
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



class AttachmentMigrationTests(CommonStoreTests):
    """
    Tests for L{UpgradeDatabaseSchemaStep}.
    """

    @inlineCallbacks
    def setUp(self):
        self.patch(config, "EnableManagedAttachments", True)

        yield super(AttachmentMigrationTests, self).setUp()

        self._sqlCalendarStore.enableManagedAttachments = True

        txn = self.transactionUnderTest()
        cs = schema.CALENDARSERVER
        yield Delete(
            From=cs,
            Where=cs.NAME == "MANAGED-ATTACHMENTS"
        ).on(txn)
        yield self.commit()


    @inlineCallbacks
    def test_upgradeOrphanedAttachment(self):
        """
        Test L{attachment_migration.doUpgrade} when an orphaned attachment is present.
        """

        def _hasDropboxAttachments(_self, txn):
            return succeed(True)
        self.patch(CalendarStoreFeatures, "hasDropboxAttachments", _hasDropboxAttachments)

        # Create orphaned attachment
        dropboxID = "ABCD.dropbox"
        attachmentName = "test.txt"
        home = yield self.homeUnderTest(name="user01")
        at = schema.ATTACHMENT
        yield Insert(
            {
                at.CALENDAR_HOME_RESOURCE_ID: home._resourceID,
                at.DROPBOX_ID: dropboxID,
                at.CONTENT_TYPE: "text/plain",
                at.SIZE: 10,
                at.MD5: "abcd",
                at.PATH: attachmentName,
            }
        ).on(self.transactionUnderTest())
        yield self.commit()

        hasheduid = hashlib.md5(dropboxID).hexdigest()
        fp = self._sqlCalendarStore.attachmentsPath.child(hasheduid[0:2]).child(hasheduid[2:4]).child(hasheduid)
        fp.makedirs()
        fp = fp.child(attachmentName)
        fp.setContent("1234567890")

        self.assertTrue(os.path.exists(fp.path))

        upgrader = UpgradeDatabaseOtherStep(self._sqlCalendarStore)
        yield attachment_migration.doUpgrade(upgrader)

        txn = upgrader.sqlStore.newTransaction()
        managed = (yield txn.calendarserverValue("MANAGED-ATTACHMENTS", raiseIfMissing=False))
        count = (yield Select(
            [Count(at.DROPBOX_ID), ],
            From=at,
        ).on(txn))[0][0]
        yield txn.commit()
        self.assertEqual(count, 0)
        self.assertNotEqual(managed, None)

        self.assertFalse(os.path.exists(fp.path))
