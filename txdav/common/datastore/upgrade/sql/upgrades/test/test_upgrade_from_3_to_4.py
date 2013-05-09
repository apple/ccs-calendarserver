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
from twistedcaldav.caldavxml import ScheduleDefaultCalendarURL, \
    CalendarFreeBusySet, Opaque, ScheduleCalendarTransp
from txdav.base.propertystore.base import PropertyName
from txdav.caldav.datastore.test.util import CommonStoreTests
from txdav.xml.element import HRef
from twext.enterprise.dal.syntax import Update
from txdav.common.datastore.upgrade.sql.upgrades.upgrade_from_3_to_4 import moveDefaultCalendarProperties, \
    moveCalendarTranspProperties, removeResourceType, moveDefaultAlarmProperties
from txdav.xml import element
from twistedcaldav import caldavxml
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE

"""
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""

from twisted.internet.defer import inlineCallbacks

class Upgrade_from_3_to_4(CommonStoreTests):
    """
    Tests for L{DefaultCalendarPropertyUpgrade}.
    """

    @inlineCallbacks
    def test_defaultCalendarUpgrade(self):

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

        # Trigger upgrade
        yield moveDefaultCalendarProperties(self._sqlCalendarStore)

        # Test results
        for user in ("user01", "user02",):
            home = (yield self.homeUnderTest(name=user))
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertTrue(home.isDefaultCalendar(calendar))
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(ScheduleDefaultCalendarURL) not in inbox.properties())


    @inlineCallbacks
    def test_calendarTranspUpgrade(self):

        # Set dead property on inbox
        for user in ("user01", "user02",):
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            inbox.properties()[PropertyName.fromElement(CalendarFreeBusySet)] = CalendarFreeBusySet(HRef.fromString("/calendars/__uids__/%s/calendar_1" % (user,)))

            # Force current to transparent
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            yield calendar.setUsedForFreeBusy(False)
            calendar.properties()[PropertyName.fromElement(ScheduleCalendarTransp)] = ScheduleCalendarTransp(Opaque())

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

        # Trigger upgrade
        yield moveCalendarTranspProperties(self._sqlCalendarStore)

        # Test results
        for user in ("user01", "user02",):
            home = (yield self.homeUnderTest(name=user))
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertTrue(calendar.isUsedForFreeBusy())
            inbox = (yield self.calendarUnderTest(name="inbox", home=user))
            self.assertTrue(PropertyName.fromElement(CalendarFreeBusySet) not in inbox.properties())


    @inlineCallbacks
    def test_defaultAlarmUpgrade(self):

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
        yield self.commit()

        # Trigger upgrade
        yield moveDefaultAlarmProperties(self._sqlCalendarStore)

        # Check each type of collection
        home = yield self.homeUnderTest(name="user01")
        for vevent, timed, alarm, prop in detailshome:
            alarm_result = (yield home.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)
            self.assertTrue(PropertyName.fromElement(prop) not in home.properties())

        calendar = yield self.calendarUnderTest(name="calendar_1", home="user01")
        for vevent, timed, alarm, prop in detailscalendar:
            alarm_result = (yield calendar.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)
            self.assertTrue(PropertyName.fromElement(prop) not in home.properties())

        shared = yield self.calendarUnderTest(name=shared_name, home="user02")
        for vevent, timed, alarm, prop in detailsshared:
            alarm_result = (yield shared.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)
            self.assertTrue(PropertyName.fromElement(prop) not in home.properties())


    @inlineCallbacks
    def test_resourceTypeUpgrade(self):

        # Set dead property on calendar
        for user in ("user01", "user02",):
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            calendar.properties()[PropertyName.fromElement(element.ResourceType)] = element.ResourceType(element.Collection())
        yield self.commit()

        for user in ("user01", "user02",):
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertTrue(PropertyName.fromElement(element.ResourceType) in calendar.properties())
        yield self.commit()

        # Trigger upgrade
        yield removeResourceType(self._sqlCalendarStore)

        # Test results
        for user in ("user01", "user02",):
            calendar = (yield self.calendarUnderTest(name="calendar_1", home=user))
            self.assertTrue(PropertyName.fromElement(element.ResourceType) not in calendar.properties())
