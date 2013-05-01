##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twext.web2.test.test_server import SimpleRequest

from twisted.internet.defer import inlineCallbacks

from twistedcaldav import caldavxml, customxml
from twistedcaldav.test.util import StoreTestCase, SimpleStoreRequest

from txdav.xml import element as davxml
from twext.web2.http import HTTPError

class Properties (StoreTestCase):
    """
    CalDAV properties
    """

    @inlineCallbacks
    def test_free_busy_set_same(self):
        """
        Test that calendar-free-busy-set has the correct value and can be reset to the same.
        """

        request = SimpleRequest(self.site, "GET", "/calendars/users/user01/inbox/")
        inbox = yield request.locateResource("/calendars/users/user01/inbox/")
        self.assertTrue((yield inbox.hasProperty(caldavxml.CalendarFreeBusySet, request)))
        prop = (yield inbox.readProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertEqual(prop.children[0], davxml.HRef("/calendars/__uids__/user01/calendar/"))

        newfbset = set()
        newfbset.add("/calendars/users/user01/calendar/")
        newset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in newfbset])

        yield inbox.writeProperty(newset, request)
        yield request._newStoreTransaction.commit()

        request = SimpleRequest(self.site, "GET", "/calendars/users/user01/inbox/")
        inbox = yield request.locateResource("/calendars/users/user01/inbox/")
        prop = (yield inbox.readProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertEqual(prop.children[0], davxml.HRef("/calendars/__uids__/user01/calendar/"))
        yield request._newStoreTransaction.commit()
        calendar = yield request.locateResource("/calendars/__uids__/user01/calendar/")
        self.assertTrue(calendar._newStoreObject.isUsedForFreeBusy())


    @inlineCallbacks
    def test_free_busy_set_different(self):
        """
        Test that calendar-free-busy-set has the correct value and can be reset to the same.
        """

        txn = self.transactionUnderTest()
        home = (yield txn.calendarHomeWithUID("user01", create=True))
        yield home.createCalendarWithName("calendar_new")
        yield self.commit()

        request = SimpleRequest(self.site, "GET", "/calendars/users/user01/inbox/")
        inbox = yield request.locateResource("/calendars/users/user01/inbox/")
        self.assertTrue((yield inbox.hasProperty(caldavxml.CalendarFreeBusySet, request)))
        prop = (yield inbox.readProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertEqual(
            set([str(child) for child in prop.children]),
            set((
                "/calendars/__uids__/user01/calendar/",
                "/calendars/__uids__/user01/calendar_new/",
            ))
        )
        calendar = yield request.locateResource("/calendars/__uids__/user01/calendar_new/")
        self.assertTrue(calendar._newStoreObject.isUsedForFreeBusy())
        calendar = yield request.locateResource("/calendars/__uids__/user01/calendar/")
        self.assertTrue(calendar._newStoreObject.isUsedForFreeBusy())

        newfbset = set()
        newfbset.add("/calendars/users/user01/calendar_new/")
        newset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in newfbset])

        yield inbox.writeProperty(newset, request)
        yield request._newStoreTransaction.commit()

        request = SimpleRequest(self.site, "GET", "/calendars/users/user01/inbox/")
        inbox = yield request.locateResource("/calendars/users/user01/inbox/")
        prop = (yield inbox.readProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertEqual(prop.children[0], davxml.HRef("/calendars/__uids__/user01/calendar_new/"))
        yield request._newStoreTransaction.commit()
        calendar = yield request.locateResource("/calendars/__uids__/user01/calendar_new/")
        self.assertTrue(calendar._newStoreObject.isUsedForFreeBusy())
        calendar = yield request.locateResource("/calendars/__uids__/user01/calendar/")
        self.assertFalse(calendar._newStoreObject.isUsedForFreeBusy())


    @inlineCallbacks
    def test_free_busy_set_invalid_url(self):
        """
        Test that calendar-free-busy-set will generate an error if an invalid value is used.
        """

        request = SimpleRequest(self.site, "GET", "/calendars/users/user01/inbox/")
        inbox = yield request.locateResource("/calendars/users/user01/inbox/")
        self.assertTrue((yield inbox.hasProperty(caldavxml.CalendarFreeBusySet, request)))
        oldfbset = set(("/calendar",))

        newfbset = set()
        newfbset.update(oldfbset)
        newfbset.add("/calendar-broken")
        newset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in newfbset])

        self.failUnlessFailure(inbox.writeProperty(newset, request), HTTPError)



class DefaultCalendar (StoreTestCase):

    @inlineCallbacks
    def test_pick_default_vevent_calendar(self):
        """
        Test that pickNewDefaultCalendar will choose the correct calendar.
        """

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property initially present
        prop = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        self.assertEqual(str(prop.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar")

        yield self.abort()


    @inlineCallbacks
    def test_pick_default_vtodo_calendar(self):
        """
        Test that pickNewDefaultCalendar will choose the correct tasks calendar.
        """

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        default = yield inbox.readProperty(customxml.ScheduleDefaultTasksURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/tasks")

        yield self.abort()


    @inlineCallbacks
    def test_missing_default_vevent_calendar(self):
        """
        Test that pickNewDefaultCalendar will create a missing default calendar.
        """

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        home = yield request.locateResource("/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property initially not present
        default = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar")

        # Forcibly remove the one we need
        yield home._newStoreHome.removeChildWithName("calendar")
        names = [calendarName for calendarName in (yield home._newStoreHome.listCalendars())]
        self.assertTrue("calendar" not in names)

        default = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar")

        yield self.abort()


    @inlineCallbacks
    def test_missing_default_vtodo_calendar(self):
        """
        Test that pickNewDefaultCalendar will create a missing default tasks calendar.
        """

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        home = yield request.locateResource("/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property present
        default = yield inbox.readProperty(customxml.ScheduleDefaultTasksURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/tasks")

        # Forcibly remove the one we need
        yield home._newStoreHome.removeChildWithName("tasks")
        names = [calendarName for calendarName in (yield home._newStoreHome.listCalendars())]
        self.assertTrue("tasks" not in names)

        default = yield inbox.readProperty(customxml.ScheduleDefaultTasksURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/tasks")

        yield self.abort()


    @inlineCallbacks
    def test_pick_default_other(self):
        """
        Make calendar
        """

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property present
        default = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar")

        # Create a new default calendar
        newcalendar = yield request.locateResource("/calendars/users/wsanchez/newcalendar")
        yield newcalendar.createCalendarCollection()
        yield inbox.writeProperty(caldavxml.ScheduleDefaultCalendarURL(davxml.HRef("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")), request)

        # Delete the normal calendar
        calendar = yield request.locateResource("/calendars/users/wsanchez/calendar")
        yield calendar.storeRemove(request)
        yield self.commit()

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        default = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")

        yield self.abort()


    @inlineCallbacks
    def test_set_default_vevent_other(self):
        """
        Test that the default URL can be set to another VEVENT calendar
        """

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property is present
        default = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar")

        # Create a new default calendar
        newcalendar = yield request.locateResource("/calendars/users/wsanchez/newcalendar")
        yield newcalendar.createCalendarCollection()
        yield newcalendar.setSupportedComponents(("VEVENT",))
        yield self.commit()

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")
        yield inbox.writeProperty(caldavxml.ScheduleDefaultCalendarURL(davxml.HRef("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")), request)

        default = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")

        yield self.commit()


    @inlineCallbacks
    def test_is_default_calendar(self):
        """
        Test .isDefaultCalendar() returns the proper class or None.
        """

        # Create a new non-default calendar
        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        newcalendar = yield request.locateResource("/calendars/users/wsanchez/newcalendar")
        yield newcalendar.createCalendarCollection()
        yield newcalendar.setSupportedComponents(("VEVENT",))
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")
        yield inbox.defaultCalendar(request, "VEVENT")
        yield inbox.defaultCalendar(request, "VTODO")
        yield self.commit()

        request = SimpleStoreRequest(self, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")
        calendar = yield request.locateResource("/calendars/users/wsanchez/calendar")
        newcalendar = yield request.locateResource("/calendars/users/wsanchez/newcalendar")
        tasks = yield request.locateResource("/calendars/users/wsanchez/tasks")

        result = yield calendar.isDefaultCalendar(request)
        self.assertTrue(result)

        result = yield newcalendar.isDefaultCalendar(request)
        self.assertFalse(result)

        result = yield tasks.isDefaultCalendar(request)
        self.assertTrue(result)

        yield self.commit()
