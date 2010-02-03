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
File calendar store tests.
"""

from zope.interface.verify import verifyObject, BrokenMethodImplementation

from twisted.python.filepath import FilePath
from twisted.trial import unittest

from twext.python.icalendar import Component as iComponent

from txdav.idav import IPropertyStore

from txcaldav.icalendarstore import ICalendarHome, ICalendar, ICalendarObject
from txcaldav.icalendarstore import CalendarNameNotAllowedError
from txcaldav.icalendarstore import CalendarAlreadyExistsError
from txcaldav.icalendarstore import NoSuchCalendarError

from txcaldav.calendarstore.file import CalendarStore, CalendarHome
from txcaldav.calendarstore.file import Calendar, CalendarObject

storePath = FilePath(__file__).parent().child("calendar_store")

home1_calendarNames = (
    "calendar_1",
    "calendar_2",
    "calendar_empty",
)

calendar1_objectNames = (
    "1.ics",
    "2.ics",
    "3.ics",
)

newEvent1_text = (
    "BEGIN:VCALENDAR\r\n"
      "VERSION:2.0\r\n"
      "PRODID:-//Apple Inc.//iCal 4.0.1//EN\r\n"
      "CALSCALE:GREGORIAN\r\n"
      "BEGIN:VTIMEZONE\r\n"
        "TZID:US/Pacific\r\n"
        "BEGIN:DAYLIGHT\r\n"
          "TZOFFSETFROM:-0800\r\n"
          "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\n"
          "DTSTART:20070311T020000\r\n"
          "TZNAME:PDT\r\n"
          "TZOFFSETTO:-0700\r\n"
        "END:DAYLIGHT\r\n"
        "BEGIN:STANDARD\r\n"
          "TZOFFSETFROM:-0700\r\n"
          "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\n"
          "DTSTART:20071104T020000\r\n"
          "TZNAME:PST\r\n"
          "TZOFFSETTO:-0800\r\n"
        "END:STANDARD\r\n"
      "END:VTIMEZONE\r\n"
      "BEGIN:VEVENT\r\n"
        "CREATED:20100203T013849Z\r\n"
        "UID:new-1\r\n"
        "DTEND;TZID=US/Pacific:20100207T173000\r\n"
        "TRANSP:OPAQUE\r\n"
        "SUMMARY:New Event\r\n"
        "DTSTART;TZID=US/Pacific:20100207T170000\r\n"
        "DTSTAMP:20100203T013909Z\r\n"
        "SEQUENCE:3\r\n"
        "BEGIN:VALARM\r\n"
          "X-WR-ALARMUID:1377CCC7-F85C-4610-8583-9513D4B364E1\r\n"
          "TRIGGER:-PT20M\r\n"
          "ATTACH;VALUE=URI:Basso\r\n"
          "ACTION:AUDIO\r\n"
        "END:VALARM\r\n"
      "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


class PropertiesTestMixin(object):
    def test_properties(self):
        properties = self.home1.properties()

        self.failUnless(
            IPropertyStore.providedBy(properties),
            properties
        )


def setUpCalendarStore(test):
    test.root = FilePath(test.mktemp())
    test.root.createDirectory()

    calendarPath = test.root.child("store")
    storePath.copyTo(calendarPath)

    test.calendarStore = CalendarStore(calendarPath)

def setUpHome1(test):
    setUpCalendarStore(test)
    test.home1 = test.calendarStore.calendarHomeWithUID("home1")

def setUpCalendar1(test):
    setUpHome1(test)
    test.calendar1 = test.home1.calendarWithName("calendar_1")


class CalendarStoreTest(unittest.TestCase):
    def setUp(self):
        setUpCalendarStore(self)

    # FIXME: If we define an interface
    #def test_interface(self):
    #    try:
    #        verifyObject(ICalendarStore, self.calendarstore)
    #    except BrokenMethodImplementation, e:
    #        self.fail(e)

    def test_init(self):
        self.failUnless(
            isinstance(self.calendarStore.path, FilePath),
            self.calendarStore.path
        )

    def test_calendarHomeWithUID(self):
        calendarHome = self.calendarStore.calendarHomeWithUID("home1")

        self.failUnless(isinstance(calendarHome, CalendarHome))


class CalendarHomeTest(unittest.TestCase, PropertiesTestMixin):
    def setUp(self):
        setUpHome1(self)

    def test_interface(self):
        try:
            verifyObject(ICalendarHome, self.home1)
        except BrokenMethodImplementation, e:
            self.fail(e)

    def test_init(self):
        self.failUnless(
            isinstance(self.home1.path, FilePath),
            self.home1.path
        )
        self.assertEquals(
            self.home1.calendarStore,
            self.calendarStore
        )

    def test_uid(self):
        self.assertEquals(self.home1.uid(), "home1")

    def test_calendars(self):
        # Add a dot directory to make sure we don't find it
        self.home1.path.child(".foo").createDirectory()

        calendars = tuple(self.home1.calendars())

        for calendar in calendars:
            self.failUnless(isinstance(calendar, Calendar), calendar)

        self.assertEquals(
            tuple(c.name() for c in calendars),
            home1_calendarNames
        )

    def test_calendarWithName_exists(self):
        for name in home1_calendarNames:
            calendar = self.home1.calendarWithName(name)
            self.failUnless(isinstance(calendar, Calendar), calendar)
            self.assertEquals(calendar.name(), name)

    def test_calendarWithName_absent(self):
        self.assertEquals(self.home1.calendarWithName("xyzzy"), None)

    def test_calendarWithName_dot(self):
        name = ".foo"
        self.home1.path.child(name).createDirectory()
        self.assertEquals(self.home1.calendarWithName(name), None)

    def test_createCalendarWithName_absent(self):
        name = "new"
        assert self.home1.calendarWithName(name) is None
        self.home1.createCalendarWithName(name)
        self.failUnless(self.home1.calendarWithName(name) is not None)

    def test_createCalendarWithName_exists(self):
        for name in home1_calendarNames:
            self.assertRaises(
                CalendarAlreadyExistsError,
                self.home1.createCalendarWithName,
                name
            )

    def test_createCalendarWithName_dot(self):
        self.assertRaises(
            CalendarNameNotAllowedError,
            self.home1.createCalendarWithName,
            ".foo"
        )

    def test_removeCalendarWithName_exists(self):
        for name in home1_calendarNames:
            self.home1.removeCalendarWithName(name)
            self.assertEquals(self.home1.calendarWithName(name), None)

    def test_removeCalendarWithName_absent(self):
        self.assertRaises(
            NoSuchCalendarError,
            self.home1.removeCalendarWithName,
            "xyzzy"
        )

    def test_removeCalendarWithName_dot(self):
        name = ".foo"
        self.home1.path.child(name).createDirectory()
        self.assertRaises(
            NoSuchCalendarError,
            self.home1.removeCalendarWithName,
            name
        )

class CalendarTest(unittest.TestCase, PropertiesTestMixin):
    def setUp(self):
        setUpCalendar1(self)

    def test_interface(self):
        try:
            verifyObject(ICalendar, self.calendar1)
        except BrokenMethodImplementation, e:
            self.fail(e)

    def test_init(self):
        self.failUnless(
            isinstance(self.calendar1.path, FilePath),
            self.calendar1
        )
        self.failUnless(
            isinstance(self.calendar1.calendarHome, CalendarHome),
            self.calendar1.calendarHome
        )

    def test_name(self):
        self.assertEquals(self.calendar1.name(), "calendar_1")

    def test_ownerCalendarHome(self):
        # Note that here we know that home1 owns calendar1
        self.assertEquals(
            self.calendar1.ownerCalendarHome().uid(),
            self.home1.uid()
        )

    def test_calendarObjects(self):
        # Add a dot file to make sure we don't find it
        self.home1.path.child(".foo").createDirectory()

        calendarObjects = tuple(self.calendar1.calendarObjects())

        for calendarObject in calendarObjects:
            self.failUnless(
                isinstance(calendarObject, CalendarObject),
                calendarObject
            )

        self.assertEquals(
            tuple(o.name() for o in calendarObjects),
            calendar1_objectNames
        )

    def test_calendarObjectWithName_exists(self):
        for name in calendar1_objectNames:
            calendarObject = self.calendar1.calendarObjectWithName(name)
            self.failUnless(
                isinstance(calendarObject, CalendarObject),
                calendarObject
            )
            self.assertEquals(calendarObject.name(), name)

    def test_calendarObjectWithName_absent(self):
        self.assertEquals(self.calendar1.calendarObjectWithName("xyzzy"), None)

    def test_calendarObjectWithName_dot(self):
        name = ".foo.ics"
        self.home1.path.child(name).touch()
        self.assertEquals(self.calendar1.calendarObjectWithName(name), None)

    def test_calendarObjectWithUID(self):
        raise NotImplementedError()
    test_calendarObjectWithUID.todo = "Unimplemented"

    def test_createCalendarObjectWithName_absent(self):
        name = "new1.ics"

        assert self.calendar1.calendarObjectWithName(name) is None

        component = iComponent.fromString(newEvent1_text)
        self.calendar1.createCalendarObjectWithName(name, component)

        calendarObject = self.calendar1.calendarObjectWithName(name)
        self.assertEquals(calendarObject.component(), component)


    def test_createCalendarObjectWithName_exists(self):
        raise NotImplementedError()
    test_createCalendarObjectWithName_exists.todo = "Unimplemented"

    def test_createCalendarObjectWithName_dot(self):
        raise NotImplementedError()
    test_createCalendarObjectWithName_dot.todo = "Unimplemented"

    def test_createCalendarObjectWithName_uidconflict(self):
        raise NotImplementedError()
    test_createCalendarObjectWithName_uidconflict.todo = "Unimplemented"

    def test_createCalendarObjectWithName_invalid(self):
        raise NotImplementedError()
    test_createCalendarObjectWithName_invalid.todo = "Unimplemented"

    def test_removeCalendarComponentWithName_exists(self):
        raise NotImplementedError()
    test_removeCalendarComponentWithName_exists.todo = "Unimplemented"

    def test_removeCalendarComponentWithName_absent(self):
        raise NotImplementedError()
    test_removeCalendarComponentWithName_absent.todo = "Unimplemented"

    def test_removeCalendarComponentWithName_dot(self):
        raise NotImplementedError()
    test_removeCalendarComponentWithName_dot.todo = "Unimplemented"

    def test_removeCalendarComponentWithUID(self):
        raise NotImplementedError()
    test_removeCalendarComponentWithUID.todo = "Unimplemented"

    def test_syncToken(self):
        raise NotImplementedError()
    test_syncToken.todo = "Unimplemented"

    def test_calendarObjectsInTimeRange(self):
        raise NotImplementedError()
    test_calendarObjectsInTimeRange.todo = "Unimplemented"

    def test_calendarObjectsSinceToken(self):
        raise NotImplementedError()
    test_calendarObjectsSinceToken.todo = "Unimplemented"


class CalendarObjectTest(unittest.TestCase, PropertiesTestMixin):
    def setUp(self):
        setUpCalendar1(self)
        self.object1 = self.calendar1.calendarObjectWithName("1.ics")

    def test_interface(self):
        try:
            verifyObject(ICalendarObject, self.object1)
        except BrokenMethodImplementation, e:
            self.fail(e)

    def test_init(self):
        self.failUnless(
            isinstance(self.object1.path, FilePath),
            self.object1.path
        )
        self.failUnless(
            isinstance(self.object1.calendar, Calendar),
            self.object1.calendar
        )

    def test_name(self):
        self.assertEquals(self.object1.name(), "1.ics")

    def test_setComponent(self):
        raise NotImplementedError()
    test_setComponent.todo = "Unimplemented"

    def test_component(self):
        component = self.object1.component()

        self.failUnless(
            isinstance(component, iComponent),
            component
        )

        self.assertEquals(component.name(), "VCALENDAR")
        self.assertEquals(component.mainType(), "VEVENT")
        self.assertEquals(component.resourceUID(), "uid1")

    def text_iCalendarText(self):
        text = self.object1.iCalendarText()

        self.failUnless(text.startswith("BEGIN:VCALENDAR\r\n"))
        self.failUnless("\r\nUID:uid-1\r\n" in text)
        self.failUnless(text.endswith("\r\nEND:VCALENDAR\r\n"))

    def test_uid(self):
        self.assertEquals(self.object1.uid(), "uid1")

    def test_componentType(self):
        self.assertEquals(self.object1.componentType(), "VEVENT")

    def test_organizer(self):
        self.assertEquals(self.object1.organizer(), "mailto:wsanchez@apple.com")
