##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""

from twext.enterprise.ienterprise import ORACLE_DIALECT, POSTGRES_DIALECT
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.modules import getModule
from twisted.trial.unittest import TestCase
from txdav.common.datastore.test.util import theStoreBuilder, StubNotifierFactory
from txdav.common.datastore.upgrade.sql.upgrade import UpgradeDatabaseSchemaService,\
    UpgradeDatabaseDataService
import re

class SchemaUpgradeTests(TestCase):
    """
    Tests for L{UpgradeDatabaseSchemaService}.
    """

    def _getSchemaVersion(self, fp, versionKey):
        schema = fp.getContent()
        found = re.search("insert into CALENDARSERVER (\(NAME, VALUE\) )?values \('%s', '(\d+)'\);" % (versionKey,), schema)
        if found is None:
            if versionKey == "VERSION":
                self.fail("Could not determine schema version for: %s" % (fp,))
            else:
                return 1
        return int(found.group(2))

    def test_scanUpgradeFiles(self):
        
        upgrader = UpgradeDatabaseSchemaService(None, None)

        upgrader.schemaLocation = getModule(__name__).filePath.sibling("fake_schema1")
        files = upgrader.scanForUpgradeFiles("fake_dialect")
        self.assertEqual(files, 
            [(3, 4, upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_3_to_4.sql"))],
        )

        upgrader.schemaLocation = getModule(__name__).filePath.sibling("fake_schema2")
        files = upgrader.scanForUpgradeFiles("fake_dialect")
        self.assertEqual(files, 
            [
                (3, 4, upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_3_to_4.sql")),
                (3, 5, upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_3_to_5.sql")),
                (4, 5, upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_4_to_5.sql")),
            ]
        )

    def test_determineUpgradeSequence(self):
        
        upgrader = UpgradeDatabaseSchemaService(None, None)

        upgrader.schemaLocation = getModule(__name__).filePath.sibling("fake_schema1")
        files = upgrader.scanForUpgradeFiles("fake_dialect")
        upgrades = upgrader.determineUpgradeSequence(3, 4, files, "fake_dialect")
        self.assertEqual(upgrades, 
            [upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_3_to_4.sql")],
        )
        self.assertRaises(RuntimeError, upgrader.determineUpgradeSequence, 3, 5, files, "fake_dialect")

        upgrader.schemaLocation = getModule(__name__).filePath.sibling("fake_schema2")
        files = upgrader.scanForUpgradeFiles("fake_dialect")
        upgrades = upgrader.determineUpgradeSequence(3, 5, files, "fake_dialect")
        self.assertEqual(upgrades, 
            [upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_3_to_5.sql")]
        )
        upgrades = upgrader.determineUpgradeSequence(4, 5, files, "fake_dialect")
        self.assertEqual(upgrades, 
            [upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_4_to_5.sql")]
        )

        upgrader.schemaLocation = getModule(__name__).filePath.sibling("fake_schema3")
        files = upgrader.scanForUpgradeFiles("fake_dialect")
        upgrades = upgrader.determineUpgradeSequence(3, 5, files, "fake_dialect")
        self.assertEqual(upgrades, 
            [
                upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_3_to_4.sql"),
                upgrader.schemaLocation.child("upgrades").child("fake_dialect").child("upgrade_from_4_to_5.sql"),
            ]
        )

    def test_upgradeAvailability(self):
        """
        Make sure that each old schema has a valid upgrade path to the current one.
        """
        
        for dialect in (POSTGRES_DIALECT, ORACLE_DIALECT,):
            upgrader = UpgradeDatabaseSchemaService(None, None)
            files = upgrader.scanForUpgradeFiles(dialect)

            current_version = self._getSchemaVersion(upgrader.schemaLocation.child("current.sql"), "VERSION")
            
            for child in upgrader.schemaLocation.child("old").child(dialect).globChildren("*.sql"):
                old_version = self._getSchemaVersion(child, "VERSION")
                upgrades = upgrader.determineUpgradeSequence(old_version, current_version, files, dialect)
                self.assertNotEqual(len(upgrades), 0)

#    def test_upgradeDataAvailability(self):
#        """
#        Make sure that each upgrade file has a valid data upgrade file or None.
#        """
#        
#        for dialect in (POSTGRES_DIALECT, ORACLE_DIALECT,):
#            upgrader = UpgradeDatabaseSchemaService(None, None)
#            files = upgrader.scanForUpgradeFiles(dialect)
#            for _ignore_from, _ignore_to, fp in files:
#                result = upgrader.getDataUpgrade(fp)
#                if result is not None:
#                    self.assertIsInstance(result, types.FunctionType)

    @inlineCallbacks
    def test_dbSchemaUpgrades(self):
        """
        This does a full DB test of all possible upgrade paths. For each old schema, it loads it into the DB
        then runs the upgrade service. This ensures all the upgrade.sql files work correctly - at least for
        postgres.
        """

        store = yield theStoreBuilder.buildStore(
            self, StubNotifierFactory()
        )

        @inlineCallbacks
        def _loadOldSchema(path):
            """
            Use the postgres schema mechanism to do tests under a separate "namespace"
            in postgres that we can quickly wipe clean afterwards.
            """
            startTxn = store.newTransaction("test_dbUpgrades")        
            yield startTxn.execSQL("create schema test_dbUpgrades;")
            yield startTxn.execSQL("set search_path to test_dbUpgrades;")
            yield startTxn.execSQL(path.getContent())
            yield startTxn.commit()

        @inlineCallbacks
        def _loadVersion():
            startTxn = store.newTransaction("test_dbUpgrades")        
            new_version = yield startTxn.execSQL("select value from calendarserver where name = 'VERSION';")
            yield startTxn.commit()
            returnValue(int(new_version[0][0]))

        @inlineCallbacks
        def _unloadOldSchema():
            startTxn = store.newTransaction("test_dbUpgrades")        
            yield startTxn.execSQL("set search_path to public;")
            yield startTxn.execSQL("drop schema test_dbUpgrades cascade;")
            yield startTxn.commit()

        @inlineCallbacks
        def _cleanupOldSchema():
            startTxn = store.newTransaction("test_dbUpgrades")        
            yield startTxn.execSQL("set search_path to public;")
            yield startTxn.execSQL("drop schema if exists test_dbUpgrades cascade;")
            yield startTxn.commit()

        self.addCleanup(_cleanupOldSchema)

        test_upgrader = UpgradeDatabaseSchemaService(None, None)
        expected_version = self._getSchemaVersion(test_upgrader.schemaLocation.child("current.sql"), "VERSION")
        for child in test_upgrader.schemaLocation.child("old").child(POSTGRES_DIALECT).globChildren("*.sql"):
            upgrader = UpgradeDatabaseSchemaService(store, None)
            yield _loadOldSchema(child)
            yield upgrader.databaseUpgrade()
            new_version = yield _loadVersion()
            yield _unloadOldSchema()

            self.assertEqual(new_version, expected_version)

    @inlineCallbacks
    def test_dbDataUpgrades(self):
        """
        This does a full DB test of all possible data upgrade paths. For each old schema, it loads it into the DB
        then runs the data upgrade service. This ensures all the upgrade_XX.py files work correctly - at least for
        postgres.
        
        TODO: this currently does not create any calendar data to test with. It simply runs the upgrade on an empty
        store.
        """

        store = yield theStoreBuilder.buildStore(
            self, StubNotifierFactory()
        )

        @inlineCallbacks
        def _loadOldData(path, oldVersion):
            """
            Use the postgres schema mechanism to do tests under a separate "namespace"
            in postgres that we can quickly wipe clean afterwards.
            """
            startTxn = store.newTransaction("test_dbUpgrades")        
            yield startTxn.execSQL("create schema test_dbUpgrades;")
            yield startTxn.execSQL("set search_path to test_dbUpgrades;")
            yield startTxn.execSQL(path.getContent())
            yield startTxn.execSQL("update CALENDARSERVER set VALUE = '%s' where NAME = 'CALENDAR-DATAVERSION';" % (oldVersion,))
            yield startTxn.commit()

        @inlineCallbacks
        def _loadVersion():
            startTxn = store.newTransaction("test_dbUpgrades")        
            new_version = yield startTxn.execSQL("select value from calendarserver where name = 'CALENDAR-DATAVERSION';")
            yield startTxn.commit()
            returnValue(int(new_version[0][0]))

        @inlineCallbacks
        def _unloadOldData():
            startTxn = store.newTransaction("test_dbUpgrades")        
            yield startTxn.execSQL("set search_path to public;")
            yield startTxn.execSQL("drop schema test_dbUpgrades cascade;")
            yield startTxn.commit()

        @inlineCallbacks
        def _cleanupOldData():
            startTxn = store.newTransaction("test_dbUpgrades")        
            yield startTxn.execSQL("set search_path to public;")
            yield startTxn.execSQL("drop schema if exists test_dbUpgrades cascade;")
            yield startTxn.commit()

        self.addCleanup(_cleanupOldData)

        test_upgrader = UpgradeDatabaseSchemaService(None, None)
        expected_version = self._getSchemaVersion(test_upgrader.schemaLocation.child("current.sql"), "CALENDAR-DATAVERSION")
        versions = set()
        for child in test_upgrader.schemaLocation.child("old").child(POSTGRES_DIALECT).globChildren("*.sql"):
            versions.add(self._getSchemaVersion(child, "CALENDAR-DATAVERSION"))

        for oldVersion in sorted(versions):
            upgrader = UpgradeDatabaseDataService(store, None)
            yield _loadOldData(test_upgrader.schemaLocation.child("current.sql"), oldVersion)
            yield upgrader.databaseUpgrade()
            new_version = yield _loadVersion()
            yield _unloadOldData()

            self.assertEqual(new_version, expected_version)
