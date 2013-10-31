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

from twext.enterprise.dal.syntax import Update, Insert

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import ScheduleDefaultCalendarURL, \
    CalendarFreeBusySet, Opaque, ScheduleCalendarTransp, Transparent

from txdav.base.propertystore.base import PropertyName
from txdav.caldav.datastore.test.util import CommonStoreTests
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE, schema
from txdav.common.datastore.upgrade.sql.upgrades.calendar_upgrade_from_3_to_4 import updateCalendarHomes, \
    doUpgrade
from txdav.xml import element
from txdav.xml.element import HRef
from twistedcaldav.config import config

"""
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""

from twisted.internet.defer import inlineCallbacks, returnValue

class Upgrade_from_3_to_4(CommonStoreTests):
    """
    Tests for L{DefaultCalendarPropertyUpgrade}.
    """

    @inlineCallbacks
    def _defaultCalendarUpgrade_setup(self):

        # Set dead property on inbox
        for user in ("user01", "user02",):
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            inbox.properties()[PropertyName.fromElement(ScheduleDefaultCalendarURL)] = ScheduleDefaultCalendarURL(HRef.fromString("/calendars/__uids__/%s/calendar_1" % (user,)))

            # Force current default to null
            home = (yield self.homeUnderTest(name=user))
            chm = home._homeMetaDataSchema
            yield Update(
                {chm.DEFAULT_EVENTS: None},
                Where=chm.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

            # Force data version to previous
            ch = home._homeSchema
            yield Update(
                {ch.DATAVERSION: 3},
                Where=ch.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

        yield self.commit()


    @inlineCallbacks
    def _defaultCalendarUpgrade_check(self, changed_users, unchanged_users):

        # Test results
        for user in changed_users:
            home = (yield self.homeUnderTest(name=user))
            version = (yield home.dataVersion())
            self.assertEqual(version, 4)
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertTrue(home.isDefaultCalendar(calendar))
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(ScheduleDefaultCalendarURL) not in inbox.properties())

        for user in unchanged_users:
            home = (yield self.homeUnderTest(name=user))
            version = (yield home.dataVersion())
            self.assertEqual(version, 3)
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertFalse(home.isDefaultCalendar(calendar))
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(ScheduleDefaultCalendarURL) in inbox.properties())


    @inlineCallbacks
    def test_defaultCalendarUpgrade(self):
        yield self._defaultCalendarUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore)
        yield self._defaultCalendarUpgrade_check(("user01", "user02",), ())


    @inlineCallbacks
    def test_partialDefaultCalendarUpgrade(self):
        yield self._defaultCalendarUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore, "user01")
        yield self._defaultCalendarUpgrade_check(("user01",), ("user02",))


    @inlineCallbacks
    def _invalidDefaultCalendarUpgrade_setup(self):

        # Set dead property on inbox
        for user in ("user01", "user02",):
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            inbox.properties()[PropertyName.fromElement(ScheduleDefaultCalendarURL)] = ScheduleDefaultCalendarURL(HRef.fromString("/calendars/__uids__/%s/tasks_1" % (user,)))

            # Force current default to null
            home = (yield self.homeUnderTest(name=user))
            chm = home._homeMetaDataSchema
            yield Update(
                {chm.DEFAULT_EVENTS: None},
                Where=chm.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

            # Create tasks only calendar
            tasks = (yield home.createCalendarWithName("tasks_1"))
            yield tasks.setSupportedComponents("VTODO")

            # Force data version to previous
            ch = home._homeSchema
            yield Update(
                {ch.DATAVERSION: 3},
                Where=ch.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

        yield self.commit()


    @inlineCallbacks
    def _invalidDefaultCalendarUpgrade_check(self, changed_users, unchanged_users):

        # Test results
        for user in changed_users:
            home = (yield self.homeUnderTest(name=user))
            version = (yield home.dataVersion())
            self.assertEqual(version, 4)
            calendar = (yield self.calendarUnderTest(name="tasks_1", home=user))
            self.assertFalse(home.isDefaultCalendar(calendar))
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(ScheduleDefaultCalendarURL) not in inbox.properties())

        for user in unchanged_users:
            home = (yield self.homeUnderTest(name=user))
            version = (yield home.dataVersion())
            self.assertEqual(version, 3)
            calendar = (yield self.calendarUnderTest(name="tasks_1", home=user))
            self.assertFalse(home.isDefaultCalendar(calendar))
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(ScheduleDefaultCalendarURL) in inbox.properties())


    @inlineCallbacks
    def test_invalidDefaultCalendarUpgrade(self):
        yield self._invalidDefaultCalendarUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore)
        yield self._invalidDefaultCalendarUpgrade_check(("user01", "user02",), ())


    @inlineCallbacks
    def test_partialInvalidDefaultCalendarUpgrade(self):
        yield self._invalidDefaultCalendarUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore, "user01")
        yield self._invalidDefaultCalendarUpgrade_check(("user01",), ("user02",))


    @inlineCallbacks
    def _calendarTranspUpgrade_setup(self):

        # Set dead property on inbox
        for user in ("user01", "user02",):
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            inbox.properties()[PropertyName.fromElement(CalendarFreeBusySet)] = CalendarFreeBusySet(HRef.fromString("/calendars/__uids__/%s/calendar_1" % (user,)))

            # Force current to transparent
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            yield calendar.setUsedForFreeBusy(False)
            calendar.properties()[PropertyName.fromElement(ScheduleCalendarTransp)] = ScheduleCalendarTransp(Opaque() if user == "user01" else Transparent())

            # Force data version to previous
            home = (yield self.homeUnderTest(name=user))
            ch = home._homeSchema
            yield Update(
                {ch.DATAVERSION: 3},
                Where=ch.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

        yield self.commit()

        for user in ("user01", "user02",):
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertFalse(calendar.isUsedForFreeBusy())
            self.assertTrue(PropertyName.fromElement(ScheduleCalendarTransp) in calendar.properties())
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(CalendarFreeBusySet) in inbox.properties())
        yield self.commit()

        # Create "fake" entry for non-existent share
        txn = self.transactionUnderTest()
        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        rp = schema.RESOURCE_PROPERTY
        yield Insert(
            {
                rp.RESOURCE_ID: calendar._resourceID,
                rp.NAME: PropertyName.fromElement(ScheduleCalendarTransp).toString(),
                rp.VALUE: ScheduleCalendarTransp(Opaque()).toxml(),
                rp.VIEWER_UID: "user03",
            }
        ).on(txn)
        yield self.commit()


    @inlineCallbacks
    def _calendarTranspUpgrade_check(self, changed_users, unchanged_users):

        # Test results
        for user in changed_users:
            home = (yield self.homeUnderTest(name=user))
            version = (yield home.dataVersion())
            self.assertEqual(version, 4)
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            if user == "user01":
                self.assertTrue(calendar.isUsedForFreeBusy())
            else:
                self.assertFalse(calendar.isUsedForFreeBusy())
            self.assertTrue(PropertyName.fromElement(caldavxml.ScheduleCalendarTransp) not in calendar.properties())
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(CalendarFreeBusySet) not in inbox.properties())

        for user in unchanged_users:
            home = (yield self.homeUnderTest(name=user))
            version = (yield home.dataVersion())
            self.assertEqual(version, 3)
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            if user == "user01":
                self.assertFalse(calendar.isUsedForFreeBusy())
            else:
                self.assertFalse(calendar.isUsedForFreeBusy())
            self.assertTrue(PropertyName.fromElement(caldavxml.ScheduleCalendarTransp) in calendar.properties())
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(CalendarFreeBusySet) in inbox.properties())


    @inlineCallbacks
    def test_calendarTranspUpgrade(self):
        yield self._calendarTranspUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore)
        yield self._calendarTranspUpgrade_check(("user01", "user02",), ())


    @inlineCallbacks
    def test_partialCalendarTranspUpgrade(self):
        yield self._calendarTranspUpgrade_setup()
        yield updateCalendarHomes(self._sqlCalendarStore, "user01")
        yield self._calendarTranspUpgrade_check(("user01",), ("user02",))


    @inlineCallbacks
    def _defaultAlarmUpgrade_setup(self):

        alarmhome1 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT1M
END:VALARM
"""

        alarmhome2 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT2M
END:VALARM
"""

        alarmhome3 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT3M
END:VALARM
"""

        alarmhome4 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT4M
END:VALARM
"""

        alarmcalendar1 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT1M
END:VALARM
"""

        alarmcalendar2 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT2M
END:VALARM
"""

        alarmcalendar3 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT3M
END:VALARM
"""

        alarmcalendar4 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT4M
END:VALARM
"""

        alarmshared1 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT1M
END:VALARM
"""

        alarmshared2 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT2M
END:VALARM
"""

        alarmshared3 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT3M
END:VALARM
"""

        alarmshared4 = """BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT4M
END:VALARM
"""

        # Setup old properties
        detailshome = (
            (True, True, alarmhome1, caldavxml.DefaultAlarmVEventDateTime,),
            (True, False, alarmhome2, caldavxml.DefaultAlarmVEventDate,),
            (False, True, alarmhome3, caldavxml.DefaultAlarmVToDoDateTime,),
            (False, False, alarmhome4, caldavxml.DefaultAlarmVToDoDate,),
        )
        detailscalendar = (
            (True, True, alarmcalendar1, caldavxml.DefaultAlarmVEventDateTime,),
            (True, False, alarmcalendar2, caldavxml.DefaultAlarmVEventDate,),
            (False, True, alarmcalendar3, caldavxml.DefaultAlarmVToDoDateTime,),
            (False, False, alarmcalendar4, caldavxml.DefaultAlarmVToDoDate,),
        )
        detailsshared = (
            (True, True, alarmshared1, caldavxml.DefaultAlarmVEventDateTime,),
            (True, False, alarmshared2, caldavxml.DefaultAlarmVEventDate,),
            (False, True, alarmshared3, caldavxml.DefaultAlarmVToDoDateTime,),
            (False, False, alarmshared4, caldavxml.DefaultAlarmVToDoDate,),
        )

        home = yield self.homeUnderTest(name="user01")
        for _ignore_vevent, _ignore_timed, alarm, prop in detailshome:
            home.properties()[PropertyName.fromElement(prop)] = prop(alarm)
        calendar = yield self.calendarUnderTest(name="calendar_1", home="user01")
        for _ignore_vevent, _ignore_timed, alarm, prop in detailscalendar:
            calendar.properties()[PropertyName.fromElement(prop)] = prop(alarm)
        home2 = yield self.homeUnderTest(name="user02")
        shared_name = yield calendar.shareWith(home2, _BIND_MODE_WRITE)
        shared = yield self.calendarUnderTest(name=shared_name, home="user02")
        for _ignore_vevent, _ignore_timed, alarm, prop in detailsshared:
            shared.properties()[PropertyName.fromElement(prop)] = prop(alarm)

        for user in ("user01", "user02",):
            # Force data version to previous
            home = (yield self.homeUnderTest(name=user))
            ch = home._homeSchema
            yield Update(
                {ch.DATAVERSION: 3},
                Where=ch.RESOURCE_ID == home._resourceID,
            ).on(self.transactionUnderTest())

        yield self.commit()

        returnValue((detailshome, detailscalendar, detailsshared, shared_name,))


    @inlineCallbacks
    def _defaultAlarmUpgrade_check(self, changed_users, unchanged_users, detailshome, detailscalendar, detailsshared, shared_name):

        # Check each type of collection
        home = yield self.homeUnderTest(name="user01")
        version = (yield home.dataVersion())
        self.assertEqual(version, 4)
        for vevent, timed, alarm, prop in detailshome:
            alarm_result = (yield home.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)
            self.assertTrue(PropertyName.fromElement(prop) not in home.properties())

        calendar = yield self.calendarUnderTest(name="calendar_1", home="user01")
        for vevent, timed, alarm, prop in detailscalendar:
            alarm_result = (yield calendar.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)
            self.assertTrue(PropertyName.fromElement(prop) not in calendar.properties())

        if "user02" in changed_users:
            home = (yield self.homeUnderTest(name="user02"))
            version = (yield home.dataVersion())
            self.assertEqual(version, 4)
            shared = yield self.calendarUnderTest(name=shared_name, home="user02")
            for vevent, timed, alarm, prop in detailsshared:
                alarm_result = (yield shared.getDefaultAlarm(vevent, timed))
                self.assertEquals(alarm_result, alarm)
                self.assertTrue(PropertyName.fromElement(prop) not in shared.properties())
        else:
            home = (yield self.homeUnderTest(name="user02"))
            version = (yield home.dataVersion())
            self.assertEqual(version, 3)
            shared = yield self.calendarUnderTest(name=shared_name, home="user02")
            for vevent, timed, alarm, prop in detailsshared:
                alarm_result = (yield shared.getDefaultAlarm(vevent, timed))
                self.assertEquals(alarm_result, None)
                self.assertTrue(PropertyName.fromElement(prop) in shared.properties())


    @inlineCallbacks
    def test_defaultAlarmUpgrade(self):
        detailshome, detailscalendar, detailsshared, shared_name = (yield self._defaultAlarmUpgrade_setup())
        yield updateCalendarHomes(self._sqlCalendarStore)
        yield self._defaultAlarmUpgrade_check(("user01", "user02",), (), detailshome, detailscalendar, detailsshared, shared_name)


    @inlineCallbacks
    def test_partialDefaultAlarmUpgrade(self):
        detailshome, detailscalendar, detailsshared, shared_name = (yield self._defaultAlarmUpgrade_setup())
        yield updateCalendarHomes(self._sqlCalendarStore, "user01")
        yield self._defaultAlarmUpgrade_check(("user01",), ("user02",), detailshome, detailscalendar, detailsshared, shared_name)


    @inlineCallbacks
    def test_combinedUpgrade(self):
        yield self._defaultCalendarUpgrade_setup()
        yield self._calendarTranspUpgrade_setup()
        detailshome, detailscalendar, detailsshared, shared_name = (yield self._defaultAlarmUpgrade_setup())
        yield updateCalendarHomes(self._sqlCalendarStore)
        yield self._defaultCalendarUpgrade_check(("user01", "user02",), ())
        yield self._calendarTranspUpgrade_check(("user01", "user02",), ())
        yield self._defaultAlarmUpgrade_check(("user01", "user02",), (), detailshome, detailscalendar, detailsshared, shared_name)


    @inlineCallbacks
    def test_partialCombinedUpgrade(self):
        yield self._defaultCalendarUpgrade_setup()
        yield self._calendarTranspUpgrade_setup()
        detailshome, detailscalendar, detailsshared, shared_name = (yield self._defaultAlarmUpgrade_setup())
        yield updateCalendarHomes(self._sqlCalendarStore, "user01")
        yield self._defaultCalendarUpgrade_check(("user01",), ("user02",))
        yield self._calendarTranspUpgrade_check(("user01",), ("user02",))
        yield self._defaultAlarmUpgrade_check(("user01",), ("user02",), detailshome, detailscalendar, detailsshared, shared_name)


    @inlineCallbacks
    def _resourceTypeUpgrade_setup(self):

        # Set dead property on calendar
        for user in ("user01", "user02",):
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            calendar.properties()[PropertyName.fromElement(element.ResourceType)] = element.ResourceType(element.Collection())
        yield self.commit()

        for user in ("user01", "user02",):
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertTrue(PropertyName.fromElement(element.ResourceType) in calendar.properties())

        yield self.transactionUnderTest().updateCalendarserverValue("CALENDAR-DATAVERSION", "3")

        yield self.commit()


    @inlineCallbacks
    def _resourceTypeUpgrade_check(self, full=True):

        # Test results
        if full:
            for user in ("user01", "user02",):
                calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
                self.assertTrue(PropertyName.fromElement(element.ResourceType) not in calendar.properties())
            version = yield self.transactionUnderTest().calendarserverValue("CALENDAR-DATAVERSION")
            self.assertEqual(int(version), 4)
        else:
            for user in ("user01", "user02",):
                calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
                self.assertTrue(PropertyName.fromElement(element.ResourceType) in calendar.properties())
            version = yield self.transactionUnderTest().calendarserverValue("CALENDAR-DATAVERSION")
            self.assertEqual(int(version), 3)


    @inlineCallbacks
    def test_resourceTypeUpgrade(self):
        yield self._resourceTypeUpgrade_setup()
        yield doUpgrade(self._sqlCalendarStore)
        yield self._resourceTypeUpgrade_check()


    @inlineCallbacks
    def test_fullUpgrade(self):
        self.patch(config, "UpgradeHomePrefix", "")
        yield self._defaultCalendarUpgrade_setup()
        yield self._calendarTranspUpgrade_setup()
        detailshome, detailscalendar, detailsshared, shared_name = (yield self._defaultAlarmUpgrade_setup())
        yield self._resourceTypeUpgrade_setup()
        yield doUpgrade(self._sqlCalendarStore)
        yield self._defaultCalendarUpgrade_check(("user01", "user02",), ())
        yield self._calendarTranspUpgrade_check(("user01", "user02",), ())
        yield self._defaultAlarmUpgrade_check(("user01", "user02",), (), detailshome, detailscalendar, detailsshared, shared_name)
        yield self._resourceTypeUpgrade_check()


    @inlineCallbacks
    def test_partialFullUpgrade(self):
        self.patch(config, "UpgradeHomePrefix", "user01")
        yield self._defaultCalendarUpgrade_setup()
        yield self._calendarTranspUpgrade_setup()
        yield self._resourceTypeUpgrade_setup()
        detailshome, detailscalendar, detailsshared, shared_name = (yield self._defaultAlarmUpgrade_setup())
        yield doUpgrade(self._sqlCalendarStore)
        yield self._defaultCalendarUpgrade_check(("user01",), ("user02",))
        yield self._calendarTranspUpgrade_check(("user01",), ("user02",))
        yield self._defaultAlarmUpgrade_check(("user01",), ("user02",), detailshome, detailscalendar, detailsshared, shared_name)
        yield self._resourceTypeUpgrade_check(False)
