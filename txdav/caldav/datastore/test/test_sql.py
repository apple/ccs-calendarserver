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

"""
Tests for txdav.caldav.datastore.postgres, mostly based on
L{txdav.caldav.datastore.test.common}.
"""

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone

from twext.enterprise.dal.syntax import Select, Parameter, Insert, Delete
from twext.python.vcomponent import VComponent

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import deferLater
from twisted.trial import unittest

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import CalendarDescription
from twistedcaldav.config import config
from twistedcaldav.dateops import datetimeMktime
from twistedcaldav.ical import Component
from twistedcaldav.query import calendarqueryfilter

from txdav.base.propertystore.base import PropertyName
from txdav.caldav.datastore.test.common import CommonTests as CalendarCommonTests, \
    test_event_text
from txdav.caldav.datastore.test.test_file import setUpCalendarStore
from txdav.caldav.datastore.test.util import buildCalendarStore
from txdav.caldav.datastore.util import _migrateCalendar, migrateHome
from txdav.caldav.icalendarstore import ComponentUpdateState, InvalidDefaultCalendar
from txdav.common.datastore.sql import ECALENDARTYPE, CommonObjectResource
from txdav.common.datastore.sql_legacy import PostgresLegacyIndexEmulator
from txdav.common.datastore.sql_tables import schema, _BIND_MODE_DIRECT, \
    _BIND_STATUS_ACCEPTED
from txdav.common.datastore.test.util import populateCalendarsFrom
from txdav.common.icommondatastore import NoSuchObjectResourceError
from txdav.xml.rfc2518 import GETContentLanguage, ResourceType

import datetime

class CalendarSQLStorageTests(CalendarCommonTests, unittest.TestCase):
    """
    Calendar SQL storage tests.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(CalendarSQLStorageTests, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        yield self.populate()

        self.nowYear = {"now": PyCalendarDateTime.getToday().getYear()}


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def assertCalendarsSimilar(self, a, b, bCalendarFilter=None):
        """
        Assert that two calendars have a similar structure (contain the same
        events).
        """
        @inlineCallbacks
        def namesAndComponents(x, filter=lambda x: x.component()):
            result = {}
            for fromObj in (yield x.calendarObjects()):
                result[fromObj.name()] = yield filter(fromObj)
            returnValue(result)
        if bCalendarFilter is not None:
            extra = [bCalendarFilter]
        else:
            extra = []
        self.assertEquals((yield namesAndComponents(a)),
                          (yield namesAndComponents(b, *extra)))


    def assertPropertiesSimilar(self, a, b, disregard=[]):
        """
        Assert that two objects with C{properties} methods have similar
        properties.

        @param disregard: a list of L{PropertyName} keys to discard from both
            input and output.
        """
        def sanitize(x):
            result = dict(x.properties().items())
            for key in disregard:
                result.pop(key, None)
            return result
        self.assertEquals(sanitize(a), sanitize(b))


    def fileTransaction(self):
        """
        Create a file-backed calendar transaction, for migration testing.
        """
        setUpCalendarStore(self)
        fileStore = self.calendarStore
        txn = fileStore.newTransaction()
        self.addCleanup(txn.commit)
        return txn


    @inlineCallbacks
    def test_migrateCalendarFromFile(self):
        """
        C{_migrateCalendar()} can migrate a file-backed calendar to a database-
        backed calendar.
        """
        fromCalendar = yield (yield self.fileTransaction().calendarHomeWithUID(
            "home1")).calendarWithName("calendar_1")
        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "new-home", create=True)
        toCalendar = yield toHome.calendarWithName("calendar")
        yield _migrateCalendar(fromCalendar, toCalendar,
                               lambda x: x.component())
        yield self.assertCalendarsSimilar(fromCalendar, toCalendar)


    @inlineCallbacks
    def test_migrateBadCalendarFromFile(self):
        """
        C{_migrateCalendar()} can migrate a file-backed calendar to a database-
        backed calendar. We need to test what happens when there is "bad" calendar data
        present in the file-backed calendar.
        """
        fromCalendar = yield (yield self.fileTransaction().calendarHomeWithUID(
            "home_bad")).calendarWithName("calendar_bad")
        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "new-home", create=True)
        toCalendar = yield toHome.calendarWithName("calendar")
        ok, bad = (yield _migrateCalendar(fromCalendar, toCalendar,
                               lambda x: x.component()))
        self.assertEqual(ok, 1)
        self.assertEqual(bad, 2)


    @inlineCallbacks
    def test_migrateRecurrenceFixCalendarFromFile(self):
        """
        C{_migrateCalendar()} can migrate a file-backed calendar to a database-
        backed calendar. We need to test what happens when there is "bad" calendar data
        present in the file-backed calendar with a broken recurrence-id that we can fix.
        """

        self.storeUnderTest().setMigrating(True)
        fromCalendar = yield (yield self.fileTransaction().calendarHomeWithUID(
            "home_bad")).calendarWithName("calendar_fix_recurrence")
        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "new-home", create=True)
        toCalendar = yield toHome.calendarWithName("calendar")
        ok, bad = (yield _migrateCalendar(fromCalendar, toCalendar,
                               lambda x: x.component()))
        self.assertEqual(ok, 3)
        self.assertEqual(bad, 0)

        self.transactionUnderTest().commit()
        self.storeUnderTest().setMigrating(False)

        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "new-home", create=True)
        toCalendar = yield toHome.calendarWithName("calendar")
        toResource = yield toCalendar.calendarObjectWithName("1.ics")
        caldata = yield toResource.componentForUser()
        self.assertEqual(str(caldata), """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Eastern
LAST-MODIFIED:20040110T032845Z
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:uid2
DTSTART;TZID=US/Eastern:%(now)s0102T140000
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RDATE;TZID=US/Eastern:%(now)s0104T160000
RRULE:FREQ=DAILY;COUNT=5
SUMMARY:event 6-ctr
END:VEVENT
BEGIN:VEVENT
UID:uid2
RECURRENCE-ID;TZID=US/Eastern:%(now)s0104T160000
DTSTART;TZID=US/Eastern:%(now)s0104T160000
DURATION:PT1H
CREATED:20060102T190000Z
DESCRIPTION:Some notes
DTSTAMP:20051222T210507Z
SUMMARY:event 6-ctr changed again
BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % self.nowYear)

        toResource = yield toCalendar.calendarObjectWithName("2.ics")
        caldata = yield toResource.componentForUser()
        self.assertEqual(str(caldata), """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Eastern
LAST-MODIFIED:20040110T032845Z
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:uid3
DTSTART;TZID=US/Eastern:%(now)s0102T140000
DURATION:PT1H
ATTENDEE:urn:uuid:home_bad
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
ORGANIZER:urn:uuid:home_bad
RRULE:FREQ=DAILY;COUNT=5
SUMMARY:event 6-ctr
END:VEVENT
BEGIN:VEVENT
UID:uid3
RECURRENCE-ID;TZID=US/Eastern:%(now)s0104T140000
DTSTART;TZID=US/Eastern:%(now)s0104T160000
DURATION:PT1H
CREATED:20060102T190000Z
DESCRIPTION:Some notes
DTSTAMP:20051222T210507Z
ORGANIZER:urn:uuid:home_bad
SUMMARY:event 6-ctr changed again
BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % self.nowYear)

        toResource = yield toCalendar.calendarObjectWithName("3.ics")
        caldata = yield toResource.componentForUser()
        self.assertEqual(str(caldata), """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Eastern
LAST-MODIFIED:20040110T032845Z
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:uid4
DTSTART;TZID=US/Eastern:%(now)s0104T160000
DURATION:PT1H
CREATED:20060102T190000Z
DESCRIPTION:Some notes
DTSTAMP:20051222T210507Z
RDATE;TZID=US/Eastern:%(now)s0104T160000
SUMMARY:event 6-ctr changed again
END:VEVENT
BEGIN:VEVENT
UID:uid4
RECURRENCE-ID;TZID=US/Eastern:%(now)s0104T160000
DTSTART;TZID=US/Eastern:%(now)s0104T160000
DURATION:PT1H
CREATED:20060102T190000Z
DESCRIPTION:Some notes
DTSTAMP:20051222T210507Z
SUMMARY:event 6-ctr changed again
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % self.nowYear)


    @inlineCallbacks
    def test_migrateDuplicateAttachmentsCalendarFromFile(self):
        """
        C{_migrateCalendar()} can migrate a file-backed calendar to a database-
        backed calendar. Test that migrating a calendar containing duplicate attachments
        will de-duplicate those attachments and proceed without error.
        """
        # Need to tweak config and settings to setup dropbox to work
        self.patch(config, "EnableDropBox", True)
        self.patch(config, "EnableManagedAttachments", False)
        self._sqlCalendarStore.enableManagedAttachments = False

        txn = self._sqlCalendarStore.newTransaction()
        cs = schema.CALENDARSERVER
        yield Delete(
            From=cs,
            Where=cs.NAME == "MANAGED-ATTACHMENTS"
        ).on(txn)
        yield txn.commit()

        fromCalendar = yield (yield self.fileTransaction().calendarHomeWithUID(
            "home_attachments")).calendarWithName("calendar_1")
        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "home_attachments", create=True)
        toCalendar = yield toHome.calendarWithName("calendar")
        ok, bad = (yield _migrateCalendar(fromCalendar, toCalendar,
                               lambda x: x.component()))
        self.assertEqual(ok, 3)
        self.assertEqual(bad, 0)


    @inlineCallbacks
    def test_migrateCalendarFromFile_Transparency(self):
        """
        C{_migrateCalendar()} can migrate a file-backed calendar to a database-
        backed calendar.
        """
        fromCalendar = yield (yield self.fileTransaction().calendarHomeWithUID(
            "home1")).calendarWithName("calendar_1")
        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "new-home", create=True)
        toCalendar = yield toHome.calendarWithName("calendar")
        yield _migrateCalendar(fromCalendar, toCalendar,
                               lambda x: x.component())

        filter = caldavxml.Filter(
                      caldavxml.ComponentFilter(
                          caldavxml.ComponentFilter(
                              caldavxml.TimeRange(start="%(now)s0201T000000Z" % self.nowYear, end="%(now)s0202T000000Z" % self.nowYear),
                              name=("VEVENT", "VFREEBUSY", "VAVAILABILITY"),
                          ),
                          name="VCALENDAR",
                       )
                  )
        filter = calendarqueryfilter.Filter(filter)
        filter.settimezone(None)

        results = yield toCalendar._index.indexedSearch(filter, 'user01', True)
        self.assertEquals(len(results), 1)
        _ignore_name, uid, _ignore_type, _ignore_organizer, _ignore_float, _ignore_start, _ignore_end, _ignore_fbtype, transp = results[0]
        self.assertEquals(uid, "uid4")
        self.assertEquals(transp, 'T')


    @inlineCallbacks
    def test_migrateHomeFromFile(self):
        """
        L{migrateHome} will migrate an L{ICalendarHome} provider from one
        backend to another; in this specific case, from the file-based backend
        to the SQL-based backend.
        """

        # Need to turn of split calendar behavior just for this test
        self.patch(config, "RestrictCalendarsToOneComponentType", False)

        fromHome = yield self.fileTransaction().calendarHomeWithUID("home1")

        builtinProperties = [PropertyName.fromElement(ResourceType)]

        # Populate an arbitrary / unused dead properties so there's something
        # to verify against.

        key = PropertyName.fromElement(GETContentLanguage)
        fromHome.properties()[key] = GETContentLanguage("C")
        (yield fromHome.calendarWithName("calendar_1")).properties()[key] = (
            GETContentLanguage("pig-latin")
        )
        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "new-home", create=True
        )
        yield migrateHome(fromHome, toHome, lambda x: x.component())
        toCalendars = yield toHome.calendars()
        self.assertEquals(set([c.name() for c in toCalendars]),
                          set([k for k in self.requirements['home1'].keys()
                               if self.requirements['home1'][k] is not None]))
        fromCalendars = yield fromHome.calendars()
        for c in fromCalendars:
            self.assertPropertiesSimilar(
                c, (yield toHome.calendarWithName(c.name())),
                builtinProperties
            )
        self.assertPropertiesSimilar(fromHome, toHome, builtinProperties)


    @inlineCallbacks
    def test_migrateHomeSplits(self):
        """
        Make sure L{migrateHome} also splits calendars by component type.
        """
        fromHome = yield self.fileTransaction().calendarHomeWithUID("home_splits")
        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "new-home", create=True
        )
        yield migrateHome(fromHome, toHome, lambda x: x.component())
        toCalendars = yield toHome.calendars()
        fromCalendars = yield fromHome.calendars()
        for c in fromCalendars:
            self.assertTrue(
                (yield toHome.calendarWithName(c.name())) is not None
            )

        supported_components = set()
        self.assertEqual(len(toCalendars), 3)
        for calendar in toCalendars:
            if calendar.name() == "inbox":
                continue
            result = yield calendar.getSupportedComponents()
            supported_components.add(result)

        self.assertEqual(supported_components, set(("VEVENT", "VTODO",)))


    @inlineCallbacks
    def test_migrateHomeNoSplits(self):
        """
        Make sure L{migrateHome} also splits calendars by component type.
        """
        fromHome = yield self.fileTransaction().calendarHomeWithUID("home_no_splits")
        toHome = yield self.transactionUnderTest().calendarHomeWithUID(
            "new-home", create=True
        )
        yield migrateHome(fromHome, toHome, lambda x: x.component())
        toCalendars = yield toHome.calendars()
        fromCalendars = yield fromHome.calendars()
        for c in fromCalendars:
            self.assertTrue(
                (yield toHome.calendarWithName(c.name())) is not None
            )

        supported_components = set()
        self.assertEqual(len(toCalendars), 2)
        for calendar in toCalendars:
            if calendar.name() == "inbox":
                continue
            result = yield calendar.getSupportedComponents()
            supported_components.add(result)

        self.assertEqual(supported_components, set(("VEVENT", "VTODO",)))


    def test_calendarHomeVersion(self):
        """
        The DATAVERSION column for new calendar homes must match the
        CALENDAR-DATAVERSION value.
        """

        home = yield self.transactionUnderTest().calendarHomeWithUID("home_version")
        self.assertTrue(home is not None)
        yield self.transactionUnderTest().commit

        txn = yield self.transactionUnderTest()
        version = yield txn.calendarserverValue("CALENDAR-DATAVERSION")[0][0]
        ch = schema.CALENDAR_HOME
        homeVersion = yield Select(
            [ch.DATAVERSION, ],
            From=ch,
            Where=ch.OWNER_UID == "home_version",
        ).on(txn)[0][0]
        self.assertEqual(int(homeVersion, version))


    @inlineCallbacks
    def test_homeProvisioningConcurrency(self):
        """
        Test that two concurrent attempts to provision a calendar home do not
        cause a race-condition whereby the second commit results in a second
        C{INSERT} that violates a unique constraint. Also verify that, while
        the two provisioning attempts are happening and doing various lock
        operations, that we do not block other reads of the table.
        """

        calendarStore = self._sqlCalendarStore

        txn1 = calendarStore.newTransaction()
        txn2 = calendarStore.newTransaction()
        txn3 = calendarStore.newTransaction()

        # Provision one home now - we will use this to later verify we can do
        # reads of existing data in the table
        home_uid2 = yield txn3.homeWithUID(ECALENDARTYPE, "uid2", create=True)
        self.assertNotEqual(home_uid2, None)
        yield txn3.commit()

        home_uid1_1 = yield txn1.homeWithUID(
            ECALENDARTYPE, "uid1", create=True
        )

        @inlineCallbacks
        def _defer_home_uid1_2():
            home_uid1_2 = yield txn2.homeWithUID(
                ECALENDARTYPE, "uid1", create=True
            )
            yield txn2.commit()
            returnValue(home_uid1_2)
        d1 = _defer_home_uid1_2()

        @inlineCallbacks
        def _pause_home_uid1_1():
            yield deferLater(reactor, 1.0, lambda : None)
            yield txn1.commit()
        d2 = _pause_home_uid1_1()

        # Verify that we can still get to the existing home - i.e. the lock
        # on the table allows concurrent reads
        txn4 = calendarStore.newTransaction()
        home_uid2 = yield txn4.homeWithUID(ECALENDARTYPE, "uid2", create=True)
        self.assertNotEqual(home_uid2, None)
        yield txn4.commit()

        # Now do the concurrent provision attempt
        yield d2
        home_uid1_2 = yield d1

        self.assertNotEqual(home_uid1_1, None)
        self.assertNotEqual(home_uid1_2, None)


    @inlineCallbacks
    def test_putConcurrency(self):
        """
        Test that two concurrent attempts to PUT different calendar object
        resources to the same calendar home does not cause a deadlock.
        """

        calendarStore = self._sqlCalendarStore

        # Provision the home and calendar now
        txn = calendarStore.newTransaction()
        home = yield txn.homeWithUID(ECALENDARTYPE, "user01", create=True)
        self.assertNotEqual(home, None)
        cal = yield home.calendarWithName("calendar")
        self.assertNotEqual(cal, None)
        yield txn.commit()

        txn1 = calendarStore.newTransaction()
        txn2 = calendarStore.newTransaction()

        home1 = yield txn1.homeWithUID(ECALENDARTYPE, "user01", create=True)
        home2 = yield txn2.homeWithUID(ECALENDARTYPE, "user01", create=True)

        cal1 = yield home1.calendarWithName("calendar")
        cal2 = yield home2.calendarWithName("calendar")

        @inlineCallbacks
        def _defer1():
            yield cal1.createObjectResourceWithName("1.ics", VComponent.fromString(
"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100203T013849Z
UID:uid1
DTEND;TZID=US/Pacific:%(now)s0207T173000
TRANSP:OPAQUE
SUMMARY:New Event
DTSTART;TZID=US/Pacific:%(now)s0207T170000
DTSTAMP:20100203T013909Z
SEQUENCE:3
BEGIN:VALARM
X-WR-ALARMUID:1377CCC7-F85C-4610-8583-9513D4B364E1
TRIGGER:-PT20M
ATTACH;VALUE=URI:Basso
ACTION:AUDIO
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % self.nowYear
            ))
            yield txn1.commit()
        d1 = _defer1()

        @inlineCallbacks
        def _defer2():
            yield cal2.createObjectResourceWithName("2.ics", VComponent.fromString(
"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100203T013849Z
UID:uid2
DTEND;TZID=US/Pacific:%(now)s0207T173000
TRANSP:OPAQUE
SUMMARY:New Event
DTSTART;TZID=US/Pacific:%(now)s0207T170000
DTSTAMP:20100203T013909Z
SEQUENCE:3
BEGIN:VALARM
X-WR-ALARMUID:1377CCC7-F85C-4610-8583-9513D4B364E1
TRIGGER:-PT20M
ATTACH;VALUE=URI:Basso
ACTION:AUDIO
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % self.nowYear
            ))
            yield txn2.commit()
        d2 = _defer2()

        yield d1
        yield d2


    @inlineCallbacks
    def test_datetimes(self):
        calendarStore = self._sqlCalendarStore

        # Provision the home and calendar now
        txn = calendarStore.newTransaction()
        home = yield txn.homeWithUID(ECALENDARTYPE, "uid1", create=True)
        cal = yield home.calendarWithName("calendar")
        cal._created = "2011-02-05 11:22:47"
        cal._modified = "2011-02-06 11:22:47"
        self.assertEqual(cal.created(), datetimeMktime(datetime.datetime(2011, 2, 5, 11, 22, 47)))
        self.assertEqual(cal.modified(), datetimeMktime(datetime.datetime(2011, 2, 6, 11, 22, 47)))

        obj = yield self.calendarObjectUnderTest()
        obj._created = "2011-02-07 11:22:47"
        obj._modified = "2011-02-08 11:22:47"
        self.assertEqual(obj.created(), datetimeMktime(datetime.datetime(2011, 2, 7, 11, 22, 47)))
        self.assertEqual(obj.modified(), datetimeMktime(datetime.datetime(2011, 2, 8, 11, 22, 47)))


    @inlineCallbacks
    def test_notificationsProvisioningConcurrency(self):
        """
        Test that two concurrent attempts to provision a notifications collection do not
        cause a race-condition whereby the second commit results in a second
        C{INSERT} that violates a unique constraint.
        """

        calendarStore = self._sqlCalendarStore

        txn1 = calendarStore.newTransaction()
        txn2 = calendarStore.newTransaction()

        notification_uid1_1 = yield txn1.notificationsWithUID(
           "uid1",
        )

        @inlineCallbacks
        def _defer_notification_uid1_2():
            notification_uid1_2 = yield txn2.notificationsWithUID(
                "uid1",
            )
            yield txn2.commit()
            returnValue(notification_uid1_2)
        d1 = _defer_notification_uid1_2()

        @inlineCallbacks
        def _pause_notification_uid1_1():
            yield deferLater(reactor, 1.0, lambda : None)
            yield txn1.commit()
        d2 = _pause_notification_uid1_1()

        # Now do the concurrent provision attempt
        yield d2
        notification_uid1_2 = yield d1

        self.assertNotEqual(notification_uid1_1, None)
        self.assertNotEqual(notification_uid1_2, None)


    @inlineCallbacks
    def test_removeCalendarPropertiesOnDelete(self):
        """
        L{ICalendarHome.removeCalendarWithName} removes a calendar that already
        exists and makes sure properties are also removed.
        """

        # Create calendar and add a property
        home = yield self.homeUnderTest()
        name = "remove-me"
        calendar = yield home.createCalendarWithName(name)
        resourceID = calendar._resourceID
        calendarProperties = calendar.properties()

        prop = caldavxml.CalendarDescription.fromString("Calendar to be removed")
        calendarProperties[PropertyName.fromElement(prop)] = prop
        yield self.commit()

        prop = schema.RESOURCE_PROPERTY
        _allWithID = Select([prop.NAME, prop.VIEWER_UID, prop.VALUE],
                        From=prop,
                        Where=prop.RESOURCE_ID == Parameter("resourceID"))

        # Check that one property is present
        home = yield self.homeUnderTest()
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 1)
        yield self.commit()

        # Remove calendar and check for no properties
        home = yield self.homeUnderTest()
        yield home.removeCalendarWithName(name)
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()

        # Recheck it
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()


    @inlineCallbacks
    def test_removeCalendarObjectPropertiesOnDelete(self):
        """
        L{ICalendarHome.removeCalendarWithName} removes a calendar object that already
        exists and makes sure properties are also removed (which is always the case as right
        now calendar objects never have properties).
        """

        # Create calendar object
        calendar1 = yield self.calendarUnderTest()
        name = "test.ics"
        component = VComponent.fromString(test_event_text)
        metadata = {
            "accessMode": "PUBLIC",
            "isScheduleObject": True,
            "scheduleTag": "abc",
            "scheduleEtags": (),
            "hasPrivateComment": False,
        }
        calobject = yield calendar1.createCalendarObjectWithName(name, component, options=metadata)
        resourceID = calobject._resourceID

        prop = schema.RESOURCE_PROPERTY
        _allWithID = Select([prop.NAME, prop.VIEWER_UID, prop.VALUE],
                        From=prop,
                        Where=prop.RESOURCE_ID == Parameter("resourceID"))

        # No properties on existing calendar object
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)

        yield self.commit()

        # Remove calendar and check for no properties
        calendar1 = yield self.calendarUnderTest()
        obj1 = yield calendar1.calendarObjectWithName(name)
        yield obj1.remove()
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()

        # Recheck it
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()


    @inlineCallbacks
    def test_removeInboxObjectPropertiesOnDelete(self):
        """
        L{ICalendarHome.removeCalendarWithName} removes an inbox calendar object that already
        exists and makes sure properties are also removed. Inbox calendar objects can have properties.
        """

        # Create calendar object and add a property
        home = yield self.homeUnderTest()
        inbox = yield home.createCalendarWithName("inbox")

        name = "test.ics"
        component = VComponent.fromString(test_event_text)
        metadata = {
            "accessMode": "PUBLIC",
            "isScheduleObject": True,
            "scheduleTag": "abc",
            "scheduleEtags": (),
            "hasPrivateComment": False,
        }
        calobject = yield inbox.createCalendarObjectWithName(name, component, options=metadata)
        resourceID = calobject._resourceID
        calobjectProperties = calobject.properties()

        prop = caldavxml.CalendarDescription.fromString("Calendar object to be removed")
        calobjectProperties[PropertyName.fromElement(prop)] = prop
        yield self.commit()

        prop = schema.RESOURCE_PROPERTY
        _allWithID = Select([prop.NAME, prop.VIEWER_UID, prop.VALUE],
                        From=prop,
                        Where=prop.RESOURCE_ID == Parameter("resourceID"))

        # One property exists calendar object
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 1)

        yield self.commit()

        # Remove calendar object and check for no properties
        home = yield self.homeUnderTest()
        inbox = yield home.calendarWithName("inbox")
        obj1 = yield inbox.calendarObjectWithName(name)
        yield obj1.remove()
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()

        # Recheck it
        rows = yield _allWithID.on(self.transactionUnderTest(), resourceID=resourceID)
        self.assertEqual(len(tuple(rows)), 0)
        yield self.commit()


    @inlineCallbacks
    def test_directShareCreateConcurrency(self):
        """
        Test that two concurrent attempts to create a direct shared calendar
        work concurrently without an exception.
        """

        calendarStore = self._sqlCalendarStore

        # Provision the home and calendar now
        txn = calendarStore.newTransaction()
        sharerHome = yield txn.homeWithUID(ECALENDARTYPE, "uid1", create=True)
        self.assertNotEqual(sharerHome, None)
        cal = yield sharerHome.calendarWithName("calendar")
        self.assertNotEqual(cal, None)
        shareeHome = yield txn.homeWithUID(ECALENDARTYPE, "uid2", create=True)
        self.assertNotEqual(shareeHome, None)
        yield txn.commit()

        txn1 = calendarStore.newTransaction()
        txn2 = calendarStore.newTransaction()

        sharerHome1 = yield txn1.homeWithUID(ECALENDARTYPE, "uid1", create=True)
        self.assertNotEqual(sharerHome1, None)
        cal1 = yield sharerHome1.calendarWithName("calendar")
        self.assertNotEqual(cal1, None)
        shareeHome1 = yield txn1.homeWithUID(ECALENDARTYPE, "uid2", create=True)
        self.assertNotEqual(shareeHome1, None)

        sharerHome2 = yield txn2.homeWithUID(ECALENDARTYPE, "uid1", create=True)
        self.assertNotEqual(sharerHome2, None)
        cal2 = yield sharerHome2.calendarWithName("calendar")
        self.assertNotEqual(cal2, None)
        shareeHome2 = yield txn1.homeWithUID(ECALENDARTYPE, "uid2", create=True)
        self.assertNotEqual(shareeHome2, None)

        @inlineCallbacks
        def _defer1():
            yield cal1.shareWith(shareeHome=sharerHome1, mode=_BIND_MODE_DIRECT, status=_BIND_STATUS_ACCEPTED, message="Shared Wiki Calendar")
            yield txn1.commit()
        d1 = _defer1()

        @inlineCallbacks
        def _defer2():
            yield cal2.shareWith(shareeHome=sharerHome2, mode=_BIND_MODE_DIRECT, status=_BIND_STATUS_ACCEPTED, message="Shared Wiki Calendar")
            yield txn2.commit()
        d2 = _defer2()

        yield d1
        yield d2


    @inlineCallbacks
    def test_transferSharingDetails(self):
        """
        Test Calendar._transferSharingDetails to make sure sharing details are transferred.
        """

        shareeHome = yield self.transactionUnderTest().calendarHomeWithUID("home_splits_shared")

        calendar = yield (yield self.transactionUnderTest().calendarHomeWithUID(
            "home_splits")).calendarWithName("calendar_1")

        # Fake a shared binding on the original calendar
        bind = calendar._bindSchema
        _bindCreate = Insert({
            bind.HOME_RESOURCE_ID: shareeHome._resourceID,
            bind.RESOURCE_ID: calendar._resourceID,
            bind.RESOURCE_NAME: "shared_1",
            bind.MESSAGE: "Shared to you",
            bind.BIND_MODE: _BIND_MODE_DIRECT,
            bind.BIND_STATUS: _BIND_STATUS_ACCEPTED,
        })
        yield _bindCreate.on(self.transactionUnderTest())
        sharedCalendar = yield shareeHome.childWithName("shared_1")
        self.assertTrue(sharedCalendar is not None)
        sharedCalendar = yield shareeHome.childWithName("shared_1_vtodo")
        self.assertTrue(sharedCalendar is None)

        # Now do the transfer and see if a new binding exists
        newcalendar = yield (yield self.transactionUnderTest().calendarHomeWithUID(
            "home_splits")).createCalendarWithName("calendar_new")
        yield calendar._transferSharingDetails(newcalendar, "VTODO")

        sharedCalendar = yield shareeHome.childWithName("shared_1")
        self.assertTrue(sharedCalendar is not None)
        self.assertEqual(sharedCalendar._resourceID, calendar._resourceID)

        sharedCalendar = yield shareeHome.childWithName("shared_1-vtodo")
        self.assertTrue(sharedCalendar is not None)
        self.assertEqual(sharedCalendar._resourceID, newcalendar._resourceID)


    @inlineCallbacks
    def test_moveCalendarObjectResource(self):
        """
        Test Calendar._transferSharingDetails to make sure sharing details are transferred.
        """

        calendar1 = yield (yield self.transactionUnderTest().calendarHomeWithUID(
            "home_splits")).calendarWithName("calendar_1")
        calendar2 = yield (yield self.transactionUnderTest().calendarHomeWithUID(
            "home_splits")).calendarWithName("calendar_2")

        child = yield calendar2.calendarObjectWithName("5.ics")

        yield child.moveTo(calendar1, child.name())

        child = yield calendar2.calendarObjectWithName("5.ics")
        self.assertTrue(child is None)

        child = yield calendar1.calendarObjectWithName("5.ics")
        self.assertTrue(child is not None)


    @inlineCallbacks
    def test_splitCalendars(self):
        """
        Test Calendar.splitCollectionByComponentTypes to make sure components are split out,
        sync information is updated.
        """

        # calendar_2 add a dead property to make sure it gets copied over
        home = yield self.transactionUnderTest().calendarHomeWithUID("home_splits")
        calendar2 = yield home.calendarWithName("calendar_2")
        pkey = PropertyName.fromElement(CalendarDescription)
        calendar2.properties()[pkey] = CalendarDescription.fromString("A birthday calendar")
        yield self.commit()

        # calendar_1 no change
        home = yield self.transactionUnderTest().calendarHomeWithUID("home_splits")
        calendar1 = yield home.calendarWithName("calendar_1")
        original_sync_token1 = yield calendar1.syncToken()
        yield calendar1.splitCollectionByComponentTypes()
        yield self.commit()

        home = yield self.transactionUnderTest().calendarHomeWithUID("home_splits")

        child = yield home.calendarWithName("calendar_1-vtodo")
        self.assertTrue(child is None)

        calendar1 = yield home.calendarWithName("calendar_1")
        children = yield calendar1.listCalendarObjects()
        self.assertEqual(len(children), 3)
        new_sync_token1 = yield calendar1.syncToken()
        self.assertEqual(new_sync_token1, original_sync_token1)
        result = yield calendar1.getSupportedComponents()
        self.assertEquals(result, "VEVENT")

        yield self.commit()

        # calendar_2 does split
        home = yield self.transactionUnderTest().calendarHomeWithUID("home_splits")
        calendar2 = yield home.calendarWithName("calendar_2")
        original_sync_token2 = yield calendar2.syncToken()
        yield calendar2.splitCollectionByComponentTypes()
        yield self.commit()

        home = yield self.transactionUnderTest().calendarHomeWithUID("home_splits")

        calendar2_vtodo = yield home.calendarWithName("calendar_2-vtodo")
        self.assertTrue(calendar2_vtodo is not None)
        children = yield calendar2_vtodo.listCalendarObjects()
        self.assertEqual(len(children), 2)
        changed, deleted = yield calendar2_vtodo.resourceNamesSinceToken(None)
        self.assertEqual(sorted(changed), ["3.ics", "5.ics"])
        self.assertEqual(len(deleted), 0)
        result = yield calendar2_vtodo.getSupportedComponents()
        self.assertEquals(result, "VTODO")
        self.assertTrue(pkey in calendar2_vtodo.properties())
        self.assertEqual(str(calendar2_vtodo.properties()[pkey]), "A birthday calendar")

        calendar2 = yield home.calendarWithName("calendar_2")
        children = yield calendar2.listCalendarObjects()
        self.assertEqual(len(children), 3)
        new_sync_token2 = yield calendar2.syncToken()
        self.assertNotEqual(new_sync_token2, original_sync_token2)
        changed, deleted = yield calendar2.resourceNamesSinceToken(original_sync_token2)
        self.assertEqual(len(changed), 0)
        self.assertEqual(sorted(deleted), ["3.ics", "5.ics"])
        result = yield calendar2.getSupportedComponents()
        self.assertEquals(result, "VEVENT")
        self.assertTrue(pkey in calendar2.properties())
        self.assertEqual(str(calendar2.properties()[pkey]), "A birthday calendar")


    @inlineCallbacks
    def test_noSplitCalendars(self):
        """
        Test CalendarHome.splitCalendars to make sure we end up with at least two collections
        with different supported components.
        """

        # Do split
        home = yield self.transactionUnderTest().calendarHomeWithUID("home_no_splits")
        calendars = yield home.calendars()
        self.assertEqual(len(calendars), 1)
        yield home.splitCalendars()
        yield self.commit()

        # Make sure we have calendars supporting both VEVENT and VTODO
        home = yield self.transactionUnderTest().calendarHomeWithUID("home_no_splits")
        supported_components = set()
        calendars = yield home.calendars()
        for calendar in calendars:
            if calendar.name() == "inbox":
                continue
            result = yield calendar.getSupportedComponents()
            supported_components.add(result)

        self.assertEqual(supported_components, set(("VEVENT", "VTODO",)))


    @inlineCallbacks
    def test_defaultCalendar(self):
        """
        Make sure a default_events calendar is assigned.
        """

        home = yield self.transactionUnderTest().calendarHomeWithUID("home_defaults")
        calendar1 = yield home.calendarWithName("calendar_1")
        yield calendar1.splitCollectionByComponentTypes()
        yield self.commit()

        home = yield self.transactionUnderTest().calendarHomeWithUID("home_defaults")
        self.assertEqual(home._default_events, None)
        self.assertEqual(home._default_tasks, None)

        default_events = yield home.defaultCalendar("VEVENT")
        self.assertTrue(default_events is not None)
        self.assertEqual(home._default_events, default_events._resourceID)
        self.assertEqual(home._default_tasks, None)
        yield self.commit()

        home = yield self.transactionUnderTest().calendarHomeWithUID("home_defaults")
        self.assertEqual(home._default_events, default_events._resourceID)
        self.assertEqual(home._default_tasks, None)

        default_tasks = yield home.defaultCalendar("VTODO")
        self.assertTrue(default_tasks is not None)
        self.assertEqual(home._default_events, default_events._resourceID)
        self.assertEqual(home._default_tasks, default_tasks._resourceID)
        yield self.commit()

        home = yield self.transactionUnderTest().calendarHomeWithUID("home_defaults")
        self.assertEqual(home._default_events, default_events._resourceID)
        self.assertEqual(home._default_tasks, default_tasks._resourceID)
        yield home.removeCalendarWithName("calendar_1-vtodo")
        yield self.commit()

        home = yield self.transactionUnderTest().calendarHomeWithUID("home_defaults")
        self.assertEqual(home._default_events, default_events._resourceID)
        self.assertEqual(home._default_tasks, None)

        default_tasks2 = yield home.defaultCalendar("VTODO")
        self.assertTrue(default_tasks2 is not None)
        self.assertEqual(home._default_events, default_events._resourceID)
        self.assertEqual(home._default_tasks, default_tasks2._resourceID)
        yield self.commit()


    @inlineCallbacks
    def test_setDefaultCalendar(self):
        """
        Make sure a default_events calendar is assigned.
        """

        home = yield self.homeUnderTest(name="home_defaults")
        calendar1 = yield home.calendarWithName("calendar_1")
        yield calendar1.splitCollectionByComponentTypes()
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        self.assertEqual(home._default_events, None)
        self.assertEqual(home._default_tasks, None)
        calendar1 = yield home.calendarWithName("calendar_1")
        yield home.setDefaultCalendar(calendar1, False)
        self.assertEqual(home._default_events, calendar1._resourceID)
        self.assertEqual(home._default_tasks, None)
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        calendar1 = yield home.calendarWithName("calendar_1")
        calendar2 = yield home.calendarWithName("calendar_1-vtodo")
        yield self.failUnlessFailure(home.setDefaultCalendar(calendar2, False), InvalidDefaultCalendar)
        self.assertEqual(home._default_events, calendar1._resourceID)
        self.assertEqual(home._default_tasks, None)
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        calendar1 = yield home.calendarWithName("calendar_1")
        calendar2 = yield home.calendarWithName("calendar_1-vtodo")
        yield home.setDefaultCalendar(calendar2, True)
        self.assertEqual(home._default_events, calendar1._resourceID)
        self.assertEqual(home._default_tasks, calendar2._resourceID)
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        calendar1 = yield home.calendarWithName("inbox")
        yield self.failUnlessFailure(home.setDefaultCalendar(calendar1, False), InvalidDefaultCalendar)
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        home_other = yield self.homeUnderTest(name="home_splits")
        calendar1 = yield home_other.calendarWithName("calendar_1")
        yield self.failUnlessFailure(home.setDefaultCalendar(calendar1, False), InvalidDefaultCalendar)
        yield self.commit()


    @inlineCallbacks
    def test_defaultCalendar_delete(self):
        """
        Make sure a default_events calendar is assigned after existing one is deleted.
        """

        home = yield self.homeUnderTest(name="home_defaults")
        calendar1 = yield home.calendarWithName("calendar_1")
        default_events = yield home.defaultCalendar("VEVENT")
        self.assertTrue(default_events is not None)
        self.assertEqual(home._default_events, calendar1._resourceID)
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        calendar1 = yield home.calendarWithName("calendar_1")
        yield calendar1.remove()
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        self.assertEqual(home._default_events, None)
        self.assertEqual(home._default_tasks, None)
        calendars = yield home.listCalendars()
        self.assertEqual(calendars, ["inbox", ])
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        default_events = yield home.defaultCalendar("VEVENT")
        self.assertTrue(default_events is not None)
        yield self.commit()

        home = yield self.homeUnderTest(name="home_defaults")
        calendar1 = yield home.calendarWithName(default_events.name())
        default_events = yield home.defaultCalendar("VEVENT")
        self.assertTrue(default_events is not None)
        self.assertEqual(home._default_events, calendar1._resourceID)
        yield self.commit()


    @inlineCallbacks
    def test_resourceLock(self):
        """
        Test CommonObjectResource.lock to make sure it locks, raises on missing resource,
        and raises when locked and wait=False used.
        """

        # Valid object
        resource = yield self.calendarObjectUnderTest()

        # Valid lock
        yield resource.lock()
        self.assertTrue(resource._locked)

        # Setup a new transaction to verify the lock and also verify wait behavior
        newTxn = self._sqlCalendarStore.newTransaction()
        newResource = yield self.calendarObjectUnderTest(txn=newTxn)
        try:
            yield newResource.lock(wait=False)
        except:
            pass # OK
        else:
            self.fail("Expected an exception")
        self.assertFalse(newResource._locked)
        yield newTxn.abort()

        # Commit existing transaction and verify we can get the lock using
        yield self.commit()

        resource = yield self.calendarObjectUnderTest()
        yield resource.lock()
        self.assertTrue(resource._locked)

        # Setup a new transaction to verify the lock but pass in an alternative txn directly
        newTxn = self._sqlCalendarStore.newTransaction()

        # FIXME: not sure why, but without this statement here, this portion of the test fails in a funny way.
        # Basically the query in the try block seems to execute twice, failing each time, one of which is caught,
        # and the other not - causing the test to fail. Seems like some state on newTxn is not being initialized?
        yield self.calendarObjectUnderTest(txn=newTxn, name="2.ics")

        try:
            yield resource.lock(wait=False, useTxn=newTxn)
        except:
            pass # OK
        else:
            self.fail("Expected an exception")
        self.assertTrue(resource._locked)

        # Test missing resource
        resource2 = yield self.calendarObjectUnderTest(name="2.ics")
        resource2._resourceID = 123456789
        try:
            yield resource2.lock()
        except NoSuchObjectResourceError:
            pass # OK
        except:
            self.fail("Expected a NoSuchObjectResourceError exception")
        else:
            self.fail("Expected an exception")
        self.assertFalse(resource2._locked)


    @inlineCallbacks
    def test_recurrenceMinMax(self):
        """
        Test CalendarObjectResource.recurrenceMinMax to make sure it handles a None value.
        """

        # Valid object
        resource = yield self.calendarObjectUnderTest()

        # Valid lock
        rMin, rMax = yield resource.recurrenceMinMax()
        self.assertEqual(rMin, None)
        self.assertEqual(rMax, None)


    @inlineCallbacks
    def test_notExpandedWithin(self):
        """
        Test PostgresLegacyIndexEmulator.notExpandedWithin to make sure it returns the correct
        result based on the ranges passed in.
        """

        self.patch(config, "FreeBusyIndexDelayedExpand", False)

        # Create the index on a new calendar
        home = yield self.homeUnderTest()
        newcalendar = yield home.createCalendarWithName("index_testing")
        index = PostgresLegacyIndexEmulator(newcalendar)

        # Create the calendar object to use for testing
        nowYear = self.nowYear["now"]
        caldata = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:instance
DTSTART:%04d0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (nowYear - 3,)
        component = Component.fromString(caldata)
        calendarObject = yield newcalendar.createCalendarObjectWithName("indexing.ics", component)
        rmin, rmax = yield calendarObject.recurrenceMinMax()
        self.assertEqual(rmin.getYear(), nowYear - 1)
        self.assertEqual(rmax.getYear(), nowYear + 1)

        # Fully within range
        testMin = PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        testMax = PyCalendarDateTime(nowYear + 1, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        result = yield index.notExpandedWithin(testMin, testMax)
        self.assertEqual(result, [])

        # Upper bound exceeded
        testMin = PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        testMax = PyCalendarDateTime(nowYear + 5, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        result = yield index.notExpandedWithin(testMin, testMax)
        self.assertEqual(result, ["indexing.ics"])

        # Lower bound exceeded
        testMin = PyCalendarDateTime(nowYear - 5, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        testMax = PyCalendarDateTime(nowYear + 1, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        result = yield index.notExpandedWithin(testMin, testMax)
        self.assertEqual(result, ["indexing.ics"])

        # Lower and upper bounds exceeded
        testMin = PyCalendarDateTime(nowYear - 5, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        testMax = PyCalendarDateTime(nowYear + 5, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        result = yield index.notExpandedWithin(testMin, testMax)
        self.assertEqual(result, ["indexing.ics"])

        # Lower none within range
        testMin = None
        testMax = PyCalendarDateTime(nowYear + 1, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        result = yield index.notExpandedWithin(testMin, testMax)
        self.assertEqual(result, [])

        # Lower none and upper bounds exceeded
        testMin = None
        testMax = PyCalendarDateTime(nowYear + 5, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        result = yield index.notExpandedWithin(testMin, testMax)
        self.assertEqual(result, ["indexing.ics"])


    @inlineCallbacks
    def test_setComponent_no_instance_indexing(self):
        """
        L{ICalendarObject.setComponent} raises L{InvalidCalendarComponentError}
        when given a L{VComponent} whose UID does not match its existing UID.
        """

        caldata = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:instance
DTSTART:%(now)s0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=DAILY
SUMMARY:instance
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % self.nowYear

        self.patch(config, "FreeBusyIndexDelayedExpand", False)

        # Add event to store
        calendar = yield self.calendarUnderTest()
        component = Component.fromString(caldata)
        calendarObject = yield calendar.createCalendarObjectWithName("indexing.ics", component)
        rmin, rmax = yield calendarObject.recurrenceMinMax()
        self.assertEqual(rmin, None)
        self.assertNotEqual(rmax.getYear(), 1900)
        instances = yield calendarObject.instances()
        self.assertNotEqual(len(instances), 0)
        yield self.commit()

        # Re-add event with re-indexing
        calendar = yield self.calendarUnderTest()
        calendarObject = yield self.calendarObjectUnderTest(name="indexing.ics")
        yield calendarObject.setComponent(component)
        instances2 = yield calendarObject.instances()
        self.assertNotEqual(
            sorted(instances, key=lambda x: x[0])[0],
            sorted(instances2, key=lambda x: x[0])[0],
        )
        yield self.commit()

        # Re-add event without re-indexing
        calendar = yield self.calendarUnderTest()
        calendarObject = yield self.calendarObjectUnderTest(name="indexing.ics")
        component.noInstanceIndexing = True
        yield calendarObject.setComponent(component)
        instances3 = yield calendarObject.instances()
        self.assertEqual(
            sorted(instances2, key=lambda x: x[0])[0],
            sorted(instances3, key=lambda x: x[0])[0],
        )

        obj1 = yield calendar.calendarObjectWithName("indexing.ics")
        yield obj1.remove()
        yield self.commit()


    @inlineCallbacks
    def test_loadObjectResourcesWithName(self):
        """
        L{CommonHomeChild.objectResourcesWithNames} returns the correct set of object resources
        properly configured with a loaded property store. make sure batching works.
        """

        @inlineCallbacks
        def _tests(cal):
            resources = yield cal.objectResourcesWithNames(("1.ics",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("1.ics",)))

            resources = yield cal.objectResourcesWithNames(("1.ics", "2.ics",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("1.ics", "2.ics",)))

            resources = yield cal.objectResourcesWithNames(("1.ics", "2.ics", "3.ics",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("1.ics", "2.ics", "3.ics",)))

            resources = yield cal.objectResourcesWithNames(("1.ics", "2.ics", "3.ics", "4.ics",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("1.ics", "2.ics", "3.ics", "4.ics",)))

            resources = yield cal.objectResourcesWithNames(("bogus1.ics",))
            self.assertEqual(set([resource.name() for resource in resources]), set())

            resources = yield cal.objectResourcesWithNames(("bogus1.ics", "2.ics",))
            self.assertEqual(set([resource.name() for resource in resources]), set(("2.ics",)))

        # Basic load tests
        cal = yield self.calendarUnderTest()
        yield _tests(cal)

        # Adjust batch size and try again
        self.patch(CommonObjectResource, "BATCH_LOAD_SIZE", 2)
        yield _tests(cal)

        yield self.commit()

        # Tests on inbox - resources with properties
        txn = self.transactionUnderTest()
        yield txn.homeWithUID(ECALENDARTYPE, "byNameTest", create=True)
        inbox = yield self.calendarUnderTest(txn=txn, name="inbox", home="byNameTest")
        caldata = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:instance
DTSTART:%(now)s0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=DAILY
SUMMARY:instance
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % self.nowYear
        component = Component.fromString(caldata)

        @inlineCallbacks
        def _createInboxItem(rname, pvalue):
            obj = yield inbox._createCalendarObjectWithNameInternal(rname, component, internal_state=ComponentUpdateState.ATTENDEE_ITIP_UPDATE)
            prop = caldavxml.CalendarDescription.fromString(pvalue)
            obj.properties()[PropertyName.fromElement(prop)] = prop

        yield _createInboxItem("1.ics", "p1")
        yield _createInboxItem("2.ics", "p2")
        yield _createInboxItem("3.ics", "p3")
        yield _createInboxItem("4.ics", "p4")
        yield self.commit()

        inbox = yield self.calendarUnderTest(name="inbox", home="byNameTest")
        yield _tests(inbox)

        resources = yield inbox.objectResourcesWithNames(("1.ics",))
        prop = caldavxml.CalendarDescription.fromString("p1")
        self.assertEqual(resources[0].properties()[PropertyName.fromElement(prop)], prop)

        resources = yield inbox.objectResourcesWithNames(("1.ics", "2.ics",))
        resources.sort(key=lambda x: x._name)
        prop = caldavxml.CalendarDescription.fromString("p1")
        self.assertEqual(resources[0].properties()[PropertyName.fromElement(prop)], prop)
        prop = caldavxml.CalendarDescription.fromString("p2")
        self.assertEqual(resources[1].properties()[PropertyName.fromElement(prop)], prop)

        resources = yield inbox.objectResourcesWithNames(("bogus1.ics", "2.ics",))
        resources.sort(key=lambda x: x._name)
        prop = caldavxml.CalendarDescription.fromString("p2")
        self.assertEqual(resources[0].properties()[PropertyName.fromElement(prop)], prop)


    @inlineCallbacks
    def test_objectResourceWithID(self):
        """
        L{ICalendarHome.objectResourceWithID} will return the calendar object..
        """
        home = yield self.homeUnderTest()
        calendarObject = (yield home.objectResourceWithID(9999))
        self.assertEquals(calendarObject, None)

        obj = (yield self.calendarObjectUnderTest())
        calendarObject = (yield home.objectResourceWithID(obj._resourceID))
        self.assertNotEquals(calendarObject, None)


    @inlineCallbacks
    def test_defaultAlarms(self):
        """
        L{ICalendarHome.objectResourceWithID} will return the calendar object..
        """

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

        detailshome = (
            (True, True, alarmhome1,),
            (True, False, alarmhome2,),
            (False, True, alarmhome3,),
            (False, False, alarmhome4,),
        )

        home = yield self.homeUnderTest()
        for vevent, timed, _ignore_alarm in detailshome:
            alarm_result = (yield home.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, None)

        for vevent, timed, alarm in detailshome:
            yield home.setDefaultAlarm(alarm, vevent, timed)

        yield self.commit()

        home = yield self.homeUnderTest()
        for vevent, timed, alarm in detailshome:
            alarm_result = (yield home.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)

        for vevent, timed, alarm in detailshome:
            yield home.setDefaultAlarm(None, vevent, timed)

        yield self.commit()

        home = yield self.homeUnderTest()
        for vevent, timed, _ignore_alarm in detailshome:
            alarm_result = (yield home.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, None)

        yield self.commit()

        detailscalendar = (
            (True, True, alarmcalendar1,),
            (True, False, alarmcalendar2,),
            (False, True, alarmcalendar3,),
            (False, False, alarmcalendar4,),
        )

        calendar = yield self.calendarUnderTest()
        for vevent, timed, _ignore_alarm in detailscalendar:
            alarm_result = (yield calendar.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, None)

        for vevent, timed, alarm in detailscalendar:
            yield calendar.setDefaultAlarm(alarm, vevent, timed)

        yield self.commit()

        calendar = yield self.calendarUnderTest()
        for vevent, timed, alarm in detailscalendar:
            alarm_result = (yield calendar.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, alarm)

        yield self.commit()

        calendar = yield self.calendarUnderTest()
        for vevent, timed, alarm in detailscalendar:
            yield calendar.setDefaultAlarm(None, vevent, timed)

        yield self.commit()

        calendar = yield self.calendarUnderTest()
        for vevent, timed, _ignore_alarm in detailscalendar:
            alarm_result = (yield calendar.getDefaultAlarm(vevent, timed))
            self.assertEquals(alarm_result, None)

        yield self.commit()
