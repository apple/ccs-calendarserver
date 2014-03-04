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

"""
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""

from twisted.internet.defer import inlineCallbacks, returnValue

from twext.enterprise.dal.syntax import Update

from txdav.caldav.datastore.test.util import CommonStoreTests
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE, _BIND_MODE_READ
from txdav.common.datastore.upgrade.sql.upgrades.calendar_upgrade_from_5_to_6 import doUpgrade


class Upgrade_from_5_to_6(CommonStoreTests):
    """
    Tests for L{DefaultCalendarPropertyUpgrade}.
    """

    @inlineCallbacks
    def _upgrade_setup(self):

        # Setup old properties
        detailshome = (
            (True, True, "boo",),
            (True, False, "boo",),
            (False, True, "boo",),
            (False, False, "boo",),
        )
        detailscalendar = (
            (True, True, "boo",),
            (True, False, "boo",),
            (False, True, "boo",),
            (False, False, "boo",),
        )
        detailsshared = (
            (True, True, "",),
            (True, False, "boo",),
            (False, True, "boo",),
            (False, False, "",),
        )

        home = yield self.homeUnderTest(name="user01")
        for vevent, timed, alarm in detailshome:
            yield home.setDefaultAlarm(alarm, vevent, timed)

        calendar = yield self.calendarUnderTest(name="calendar_1", home="user01")
        for vevent, timed, alarm in detailscalendar:
            yield calendar.setDefaultAlarm(alarm, vevent, timed)

        inbox = yield self.calendarUnderTest(name="inbox", home="user01")
        yield inbox.setUsedForFreeBusy(True)

        home2 = yield self.homeUnderTest(name="user02")
        shared_name2 = yield calendar.shareWith(home2, _BIND_MODE_WRITE)
        shared = yield self.calendarUnderTest(name=shared_name2, home="user02")
        for vevent, timed, alarm in detailsshared:
            yield shared.setDefaultAlarm(alarm, vevent, timed)

        home3 = yield self.homeUnderTest(name="user03")
        shared_name3 = yield calendar.shareWith(home3, _BIND_MODE_READ)
        shared = yield self.calendarUnderTest(name=shared_name3, home="user03")
        for vevent, timed, alarm in detailsshared:
            yield shared.setDefaultAlarm(alarm, vevent, timed)

        for user in ("user01", "user02", "user03",):
            # Force data version to previous
            home = (yield self.homeUnderTest(name=user))
            ch = home._homeSchema
            yield Update(
                {ch.DATAVERSION: 5},
                Where=ch.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

        yield self.commit()

        # Re-adjust for empty changes
        detailsshared = (
            (True, True, "empty",),
            (True, False, "empty",),
            (False, True, "empty",),
            (False, False, "empty",),
        )

        returnValue((detailshome, detailscalendar, detailsshared, shared_name2, shared_name3,))


    @inlineCallbacks
    def _upgrade_alarms_check(self, detailshome, detailscalendar, detailsshared, shared_name2, shared_name3):

        # Check each type of collection
        home = yield self.homeUnderTest(name="user01")
        version = (yield home.dataVersion())
        self.assertEqual(version, 6)
        for vevent, timed, alarm in detailshome:
            alarm_result = (yield home.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)

        calendar = yield self.calendarUnderTest(name="calendar_1", home="user01")
        for vevent, timed, alarm in detailscalendar:
            alarm_result = (yield calendar.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)

        home2 = (yield self.homeUnderTest(name="user02"))
        version = (yield home2.dataVersion())
        self.assertEqual(version, 6)
        shared = yield self.calendarUnderTest(name=shared_name2, home="user02")
        for vevent, timed, alarm in detailsshared:
            alarm_result = (yield shared.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)

        home3 = (yield self.homeUnderTest(name="user02"))
        version = (yield home3.dataVersion())
        self.assertEqual(version, 6)
        shared = yield self.calendarUnderTest(name=shared_name3, home="user03")
        for vevent, timed, alarm in detailsshared:
            alarm_result = (yield shared.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)

        version = yield self.transactionUnderTest().calendarserverValue("CALENDAR-DATAVERSION")
        self.assertEqual(int(version), 6)


    @inlineCallbacks
    def _upgrade_inbox_check(self, detailshome, detailscalendar, detailsshared, shared_name2, shared_name3):

        calendar = yield self.calendarUnderTest(name="calendar_1", home="user01")
        self.assertTrue(calendar.isUsedForFreeBusy())
        inbox = yield self.calendarUnderTest(name="inbox", home="user01")
        self.assertFalse(inbox.isUsedForFreeBusy())


    @inlineCallbacks
    def test_defaultAlarmUpgrade(self):
        detailshome, detailscalendar, detailsshared, shared_name2, shared_name3 = (yield self._upgrade_setup())
        yield doUpgrade(self._sqlCalendarStore)
        yield self._upgrade_alarms_check(detailshome, detailscalendar, detailsshared, shared_name2, shared_name3)


    @inlineCallbacks
    def test_inboxTranspUpgrade(self):
        detailshome, detailscalendar, detailsshared, shared_name2, shared_name3 = (yield self._upgrade_setup())
        yield doUpgrade(self._sqlCalendarStore)
        yield self._upgrade_inbox_check(detailshome, detailscalendar, detailsshared, shared_name2, shared_name3)
