##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
from twext.enterprise.dal.syntax import Insert, Select
from txdav.common.datastore.sql_tables import _populateSchema
from datetime import datetime

"""
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""

from twext.enterprise.ienterprise import POSTGRES_DIALECT
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from txdav.common.datastore.test.util import theStoreBuilder, \
    StubNotifierFactory
from txdav.common.datastore.upgrade.sql.upgrade import UpgradeDatabaseSchemaStep
import re

class SchemaUpgradeWithDataTests(TestCase):
    """
    Tests for upgrading schema when data is present in the database to make sure data conversion
    is done correctly.
    """

    @staticmethod
    def _getRawSchemaVersion(fp, versionKey):
        schema = fp.getContent()
        found = re.search("insert into CALENDARSERVER (\(NAME, VALUE\) )?values \('%s', '(\d+)'\);" % (versionKey,), schema)
        return int(found.group(2)) if found else None


    def _getSchemaVersion(self, fp, versionKey):
        found = self._getRawSchemaVersion(fp, versionKey)
        if found is None:
            if versionKey == "VERSION":
                self.fail("Could not determine schema version for: %s" % (fp,))
            else:
                return 1
        return found


    @inlineCallbacks
    def setUp(self):
        TestCase.setUp(self)

        test_upgrader = UpgradeDatabaseSchemaStep(None)
        self.upgradePath = test_upgrader.schemaLocation.child("old").child(POSTGRES_DIALECT)
        self.currentVersion = self._getSchemaVersion(test_upgrader.schemaLocation.child("current.sql"), "VERSION")

        self.store = yield theStoreBuilder.buildStore(
            self, {"push": StubNotifierFactory()}, enableJobProcessing=False
        )


    @inlineCallbacks
    def cleanUp(self):
        startTxn = self.store.newTransaction("test_dbUpgrades")
        yield startTxn.execSQL("set search_path to public;")
        yield startTxn.execSQL("drop schema test_dbUpgrades cascade;")
        yield startTxn.commit()


    @inlineCallbacks
    def _loadOldSchema(self, path):
        """
        Use the postgres schema mechanism to do tests under a separate "namespace"
        in postgres that we can quickly wipe clean afterwards.
        """
        startTxn = self.store.newTransaction("test_dbUpgrades")
        yield startTxn.execSQL("create schema test_dbUpgrades;")
        yield startTxn.execSQL("set search_path to test_dbUpgrades;")
        yield startTxn.execSQL(path.getContent())
        yield startTxn.commit()

        self.addCleanup(self.cleanUp)

        returnValue(_populateSchema(path))


    @inlineCallbacks
    def _loadVersion(self):
        startTxn = self.store.newTransaction("test_dbUpgrades")
        new_version = yield startTxn.execSQL("select value from calendarserver where name = 'VERSION';")
        yield startTxn.commit()
        returnValue(int(new_version[0][0]))


    @inlineCallbacks
    def test_upgrade_SCHEDULE_REPLY_CANCEL(self):

        cal1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REPLY
BEGIN:VEVENT
UID:1234-5678
DTSTART:20071114T010000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
END:VEVENT
END:VCALENDAR
"""

        # Load old schema and populate with data
        schema = yield self._loadOldSchema(self.upgradePath.child("v49.sql"))

        txn = self.store.newTransaction("loadData")
        yield Insert(
            {
                schema.CALENDAR_HOME.RESOURCE_ID: 1,
                schema.CALENDAR_HOME.OWNER_UID: "abcdefg",
            }
        ).on(txn)
        yield Insert(
            {
                schema.JOB.JOB_ID: 1,
                schema.JOB.WORK_TYPE: "SCHEDULE_REPLY_CANCEL_WORK",
                schema.JOB.NOT_BEFORE: datetime.utcnow(),
            }
        ).on(txn)
        yield Insert(
            {
                schema.SCHEDULE_WORK.WORK_ID: 1,
                schema.SCHEDULE_WORK.JOB_ID: 1,
                schema.SCHEDULE_WORK.ICALENDAR_UID: "1234-5678",
                schema.SCHEDULE_WORK.WORK_TYPE: "SCHEDULE_REPLY_CANCEL_WORK",
            }
        ).on(txn)
        yield Insert(
            {
                schema.SCHEDULE_REPLY_CANCEL_WORK.WORK_ID: 1,
                schema.SCHEDULE_REPLY_CANCEL_WORK.HOME_RESOURCE_ID: 1,
                schema.SCHEDULE_REPLY_CANCEL_WORK.ICALENDAR_TEXT: cal1,
            }
        ).on(txn)
        yield txn.commit()

        # Try to upgrade and verify new version afterwards
        upgrader = UpgradeDatabaseSchemaStep(self.store)
        yield upgrader.databaseUpgrade()

        new_version = yield self._loadVersion()
        self.assertEqual(new_version, self.currentVersion)

        txn = self.store.newTransaction("loadData")
        jobs = yield Select(
            From=schema.JOB,
        ).on(txn)
        schedules = yield Select(
            From=schema.SCHEDULE_WORK,
        ).on(txn)
        replies = yield Select(
            From=schema.SCHEDULE_REPLY_WORK,
        ).on(txn)
        yield txn.commit()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(schedules), 1)
        self.assertEqual(len(replies), 1)

        self.assertEqual(replies[0], [1, 1, None, cal1, ])


    @inlineCallbacks
    def test_upgrade_SCHEDULE_REPLY(self):

        cal1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:1234-5678
DTSTART:20071114T010000Z
DURATION:PT1H
DTSTAMP:20071114T000000Z
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ORGANIZER:mailto:user01@example.com
SUMMARY:Test
END:VEVENT
END:VCALENDAR
"""

        # Load old schema and populate with data
        schema = yield self._loadOldSchema(self.upgradePath.child("v49.sql"))

        txn = self.store.newTransaction("loadData")
        yield Insert(
            {
                schema.CALENDAR_HOME.RESOURCE_ID: 1,
                schema.CALENDAR_HOME.OWNER_UID: "abcdefg",
            }
        ).on(txn)
        yield Insert(
            {
                schema.CALENDAR.RESOURCE_ID: 2,
            }
        ).on(txn)
        yield Insert(
            {
                schema.CALENDAR_OBJECT.RESOURCE_ID: 3,
                schema.CALENDAR_OBJECT.CALENDAR_RESOURCE_ID: 2,
                schema.CALENDAR_OBJECT.RESOURCE_NAME: "1.ics",
                schema.CALENDAR_OBJECT.ICALENDAR_TEXT: cal1,
                schema.CALENDAR_OBJECT.ICALENDAR_UID: "1234-5678",
                schema.CALENDAR_OBJECT.ICALENDAR_TYPE: "VEVENT",
                schema.CALENDAR_OBJECT.MD5: "md5-1234567890",
            }
        ).on(txn)
        yield Insert(
            {
                schema.JOB.JOB_ID: 1,
                schema.JOB.WORK_TYPE: "SCHEDULE_REPLY_WORK",
                schema.JOB.NOT_BEFORE: datetime.utcnow(),
            }
        ).on(txn)
        yield Insert(
            {
                schema.SCHEDULE_WORK.WORK_ID: 1,
                schema.SCHEDULE_WORK.JOB_ID: 1,
                schema.SCHEDULE_WORK.ICALENDAR_UID: "1234-5678",
                schema.SCHEDULE_WORK.WORK_TYPE: "SCHEDULE_REPLY_WORK",
            }
        ).on(txn)
        yield Insert(
            {
                schema.SCHEDULE_REPLY_WORK.WORK_ID: 1,
                schema.SCHEDULE_REPLY_WORK.HOME_RESOURCE_ID: 1,
                schema.SCHEDULE_REPLY_WORK.RESOURCE_ID: 3,
                schema.SCHEDULE_REPLY_WORK.CHANGED_RIDS: None,
            }
        ).on(txn)
        yield txn.commit()

        # Try to upgrade and verify new version afterwards
        upgrader = UpgradeDatabaseSchemaStep(self.store)
        yield upgrader.databaseUpgrade()

        new_version = yield self._loadVersion()
        self.assertEqual(new_version, self.currentVersion)

        txn = self.store.newTransaction("loadData")
        jobs = yield Select(
            From=schema.JOB,
        ).on(txn)
        schedules = yield Select(
            From=schema.SCHEDULE_WORK,
        ).on(txn)
        replies = yield Select(
            From=schema.SCHEDULE_REPLY_WORK,
        ).on(txn)
        yield txn.commit()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(schedules), 1)
        self.assertEqual(len(replies), 1)

        self.assertEqual(replies[0], [1, 1, 3, None, ])
