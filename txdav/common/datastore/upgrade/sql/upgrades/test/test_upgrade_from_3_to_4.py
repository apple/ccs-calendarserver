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
from txdav.common.datastore.upgrade.sql.upgrades.calendar_upgrade_from_3_to_4 import moveDefaultCalendarProperties, \
    moveCalendarTranspProperties, removeResourceType
from txdav.xml import element

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
        inbox = (yield self.calendarUnderTest(name="inbox", home="user01"))
        inbox.properties()[PropertyName.fromElement(ScheduleDefaultCalendarURL)] = ScheduleDefaultCalendarURL(HRef.fromString("/calendars/__uids__/user01/calendar_1"))

        # Force current default to null
        home = (yield self.homeUnderTest(name="user01"))
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
        home = (yield self.homeUnderTest(name="user01"))
        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        self.assertTrue(home.isDefaultCalendar(calendar))
        inbox = (yield self.calendarUnderTest(name="inbox", home="user01"))
        self.assertTrue(PropertyName.fromElement(ScheduleDefaultCalendarURL) not in inbox.properties())


    @inlineCallbacks
    def test_calendarTranspUpgrade(self):

        # Set dead property on inbox
        inbox = (yield self.calendarUnderTest(name="inbox", home="user01"))
        inbox.properties()[PropertyName.fromElement(CalendarFreeBusySet)] = CalendarFreeBusySet(HRef.fromString("/calendars/__uids__/user01/calendar_1"))

        # Force current to transparent
        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        yield calendar.setUsedForFreeBusy(False)
        calendar.properties()[PropertyName.fromElement(ScheduleCalendarTransp)] = ScheduleCalendarTransp(Opaque())

        # Force data version to previous
        home = (yield self.homeUnderTest(name="user01"))
        ch = home._homeSchema
        yield Update(
            {ch.DATAVERSION: 3},
            Where=ch.RESOURCE_ID == home._resourceID,
        ).on(self.transactionUnderTest())

        yield self.commit()

        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        self.assertFalse(calendar.isUsedForFreeBusy())
        self.assertTrue(PropertyName.fromElement(ScheduleCalendarTransp) in calendar.properties())
        inbox = (yield self.calendarUnderTest(name="inbox", home="user01"))
        self.assertTrue(PropertyName.fromElement(CalendarFreeBusySet) in inbox.properties())
        yield self.commit()

        # Trigger upgrade
        yield moveCalendarTranspProperties(self._sqlCalendarStore)

        # Test results
        home = (yield self.homeUnderTest(name="user01"))
        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        self.assertTrue(calendar.isUsedForFreeBusy())
        inbox = (yield self.calendarUnderTest(name="inbox", home="user01"))
        self.assertTrue(PropertyName.fromElement(CalendarFreeBusySet) not in inbox.properties())


    @inlineCallbacks
    def test_resourceTypeUpgrade(self):

        # Set dead property on calendar
        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        calendar.properties()[PropertyName.fromElement(element.ResourceType)] = element.ResourceType(element.Collection())
        yield self.commit()

        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        self.assertTrue(PropertyName.fromElement(element.ResourceType) in calendar.properties())
        yield self.commit()

        # Trigger upgrade
        yield removeResourceType(self._sqlCalendarStore)

        # Test results
        calendar = (yield self.calendarUnderTest(name="calendar_1", home="user01"))
        self.assertTrue(PropertyName.fromElement(element.ResourceType) not in calendar.properties())
