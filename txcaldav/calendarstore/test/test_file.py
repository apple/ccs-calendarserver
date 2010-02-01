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

from txcaldav.icalendarstore import ICalendarHome
from txcaldav.icalendarstore import ICalendar
from txcaldav.icalendarstore import ICalendarObject

from txcaldav.calendarstore.file import CalendarStore
from txcaldav.calendarstore.file import CalendarHome
from txcaldav.calendarstore.file import Calendar
from txcaldav.calendarstore.file import CalendarObject

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

class CalendarStoreTest(unittest.TestCase):
    def setUp(self):
        self.calendarStore = CalendarStore(storePath)

    # FIXME: If we define an interface
    #def test_interface(self):
    #    try:
    #        verifyObject(ICalendarStore, self.calendarstore)
    #    except BrokenMethodImplementation, e:
    #        self.fail(e)

    def test_init(self):
        assert isinstance(self.calendarStore.path, FilePath), self.calendarStore.path

    def test_calendarHomeWithUID(self):
        calendarHome = self.calendarStore.calendarHomeWithUID("home1")

        assert isinstance(calendarHome, CalendarHome)


class CalendarHomeTest(unittest.TestCase):
    def setUp(self):
        self.calendarStore = CalendarStore(storePath)
        self.home1 = self.calendarStore.calendarHomeWithUID("home1")

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
        calendars = tuple(self.home1.calendars())

        for calendar in calendars:
            self.failUnless(isinstance(calendar, Calendar))

        self.assertEquals(
            tuple(c.name() for c in calendars),
            home1_calendarNames
        )

    def test_calendarWithName(self):
        for name in home1_calendarNames:
            calendar = self.home1.calendarWithName(name)
            self.failUnless(isinstance(calendar, Calendar))
            self.assertEquals(calendar.name(), name)

    def test_createCalendarWithName(self):
        raise NotImplementedError()
    test_createCalendarWithName.todo = "Unimplemented"

    def test_removeCalendarWithName(self):
        raise NotImplementedError()
    test_removeCalendarWithName.todo = "Unimplemented"

    def test_properties(self):
        properties = self.home1.properties()

        # FIXME: check specific class later?
        self.failUnless(IPropertyStore.providedBy(properties))
    test_properties.todo = "Unimplemented"


class CalendarTest(unittest.TestCase):
    def setUp(self):
        self.calendarStore = CalendarStore(storePath)
        self.home1 = self.calendarStore.calendarHomeWithUID("home1")
        self.calendar1 = self.home1.calendarWithName("calendar_1")

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
        calendarObjects = tuple(self.calendar1.calendarObjects())

        for calendarObject in calendarObjects:
            self.failUnless(isinstance(calendarObject, CalendarObject))

        self.assertEquals(
            tuple(o.name() for o in calendarObjects),
            calendar1_objectNames
        )

    def test_calendarObjectWithName(self):
        for name in calendar1_objectNames:
            calendarObject = self.calendar1.calendarObjectWithName(name)
            self.failUnless(isinstance(calendarObject, CalendarObject))
            self.assertEquals(calendarObject.name(), name)

    def test_calendarObjectWithUID(self):
        raise NotImplementedError()
    test_calendarObjectWithUID.todo = "Unimplemented"

    def test_createCalendarObjectWithName(self):
        raise NotImplementedError()
    test_createCalendarObjectWithName.todo = "Unimplemented"

    def test_removeCalendarComponentWithName(self):
        raise NotImplementedError()
    test_removeCalendarComponentWithName.todo = "Unimplemented"

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

    def test_properties(self):
        raise NotImplementedError()
    test_properties.todo = "Unimplemented"


class CalendarObjectTest(unittest.TestCase):
    def setUp(self):
        self.calendarStore = CalendarStore(storePath)
        self.home1 = self.calendarStore.calendarHomeWithUID("home1")
        self.calendar1 = self.home1.calendarWithName("calendar_1")
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

    def test_properties(self):
        raise NotImplementedError()
    test_properties.todo = "Unimplemented"
