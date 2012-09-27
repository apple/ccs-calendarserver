##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

from twext.web2 import responsecode, http_headers
from txdav.xml import element as davxml
from twext.web2.dav.util import davXMLFromStream
from twext.web2.http import HTTPError
from twext.web2.iweb import IResponse
from twext.web2.stream import MemoryStream
from twext.web2.test.test_server import SimpleRequest

from twisted.internet.defer import inlineCallbacks

from twistedcaldav import caldavxml, customxml
from twistedcaldav.config import config
from twistedcaldav.memcachelock import MemcacheLock
from twistedcaldav.schedule import IScheduleInboxResource
from twistedcaldav.test.util import HomeTestCase, TestCase

class Properties (HomeTestCase):
    """
    CalDAV properties
    """
    def test_free_busy_set_prop(self):
        """
        Test for PROPFIND on Inbox with missing calendar-free-busy-set property.
        """

        inbox_uri  = "/inbox/"

        def propfind_cb(response):
            response = IResponse(response)

            if response.code != responsecode.MULTI_STATUS:
                self.fail("Incorrect response to PROPFIND: %s" % (response.code,))

            def got_xml(doc):
                if not isinstance(doc.root_element, davxml.MultiStatus):
                    self.fail("PROPFIND response XML root element is not multistatus: %r" % (doc.root_element,))

                response = doc.root_element.childOfType(davxml.Response)
                href = response.childOfType(davxml.HRef)
                self.failUnless(str(href) == inbox_uri)

                for propstat in response.childrenOfType(davxml.PropertyStatus):
                    status = propstat.childOfType(davxml.Status)
                    if status.code != responsecode.OK:
                        self.fail("Unable to read requested properties (%s): %r"
                                  % (status, propstat.childOfType(davxml.PropertyContainer).toxml()))

                container = propstat.childOfType(davxml.PropertyContainer)

                #
                # Check CalDAV:calendar-free-busy-set
                #

                free_busy_set = container.childOfType(caldavxml.CalendarFreeBusySet)
                if not free_busy_set:
                    self.fail("Expected CalDAV:calendar-free-busy-set element; but got none.")

                if not free_busy_set.children:
                    self.fail("Expected non-empty CalDAV:calendar-free-busy-set element.")

            return davXMLFromStream(response.stream).addCallback(got_xml)

        query = davxml.PropertyFind(
                    davxml.PropertyContainer(
                        caldavxml.CalendarFreeBusySet(),
                    ),
                )

        request = SimpleRequest(
            self.site,
            "PROPFIND",
            inbox_uri,
            headers=http_headers.Headers({"Depth":"0"}),
        )
        request.stream = MemoryStream(query.toxml())
        return self.send(request, propfind_cb)

    @inlineCallbacks
    def test_free_busy_set_remove_broken(self):
        """
        ???
        """

        request = SimpleRequest(self.site, "GET", "/inbox/")
        inbox = yield request.locateResource("/inbox/")
        self.assertTrue(inbox.hasDeadProperty(caldavxml.CalendarFreeBusySet))
        oldfbset = set(("/calendar",))
        oldset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in oldfbset])

        newfbset = set()
        newfbset.update(oldfbset)
        newfbset.add("/calendar-broken")
        newset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in newfbset])

        inbox.writeDeadProperty(newset)
        changedset = inbox.readDeadProperty(caldavxml.CalendarFreeBusySet)
        self.assertEqual(tuple(changedset.children), tuple(newset.children))
        
        yield inbox.writeProperty(newset, request)

        changedset = inbox.readDeadProperty(caldavxml.CalendarFreeBusySet)
        self.assertEqual(tuple(changedset.children), tuple(oldset.children))

    @inlineCallbacks
    def test_free_busy_set_strip_slash(self):
        """
        ???
        """

        request = SimpleRequest(self.site, "GET", "/inbox/")
        inbox = yield request.locateResource("/inbox/")
        self.assertTrue(inbox.hasDeadProperty(caldavxml.CalendarFreeBusySet))

        oldfbset = set(("/calendar/",))
        oldset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in oldfbset])
        inbox.writeDeadProperty(oldset)
        
        writefbset = set(("/calendar/",))
        writeset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in writefbset])
        yield inbox.writeProperty(writeset, request)

        correctfbset = set(("/calendar",))
        correctset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in correctfbset])
        changedset = inbox.readDeadProperty(caldavxml.CalendarFreeBusySet)
        self.assertEqual(tuple(changedset.children), tuple(correctset.children))

    @inlineCallbacks
    def test_free_busy_set_strip_slash_remove(self):
        """
        ???
        """

        request = SimpleRequest(self.site, "GET", "/inbox/")
        inbox = yield request.locateResource("/inbox/")
        self.assertTrue(inbox.hasDeadProperty(caldavxml.CalendarFreeBusySet))

        oldfbset = set(("/calendar/", "/broken/"))
        oldset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in oldfbset])
        inbox.writeDeadProperty(oldset)
        
        writefbset = set(("/calendar/", "/broken/"))
        writeset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in writefbset])
        yield inbox.writeProperty(writeset, request)

        correctfbset = set(("/calendar",))
        correctset = caldavxml.CalendarFreeBusySet(*[davxml.HRef(url) for url in correctfbset])
        changedset = inbox.readDeadProperty(caldavxml.CalendarFreeBusySet)
        self.assertEqual(tuple(changedset.children), tuple(correctset.children))

class DefaultCalendar (TestCase):

    def setUp(self):
        super(DefaultCalendar, self).setUp()
        self.createStockDirectoryService()
        self.setupCalendars()

    @inlineCallbacks
    def test_pick_default_vevent_calendar(self):
        """
        Test that pickNewDefaultCalendar will choose the correct calendar.
        """
        
        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property initially not present
        try:
            inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            pass
        else:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not empty")

        yield inbox.pickNewDefaultCalendar(request)

        try:
            default = inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar")

        request._newStoreTransaction.abort()

    @inlineCallbacks
    def test_pick_default_vtodo_calendar(self):
        """
        Test that pickNewDefaultCalendar will choose the correct tasks calendar.
        """
        
        
        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property initially not present
        try:
            inbox.readDeadProperty(customxml.ScheduleDefaultTasksURL)
        except HTTPError:
            pass
        else:
            self.fail("customxml.ScheduleDefaultTasksURL is not empty")

        yield inbox.pickNewDefaultCalendar(request, tasks=True)

        try:
            default = inbox.readDeadProperty(customxml.ScheduleDefaultTasksURL)
        except HTTPError:
            self.fail("customxml.ScheduleDefaultTasksURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/tasks")

        request._newStoreTransaction.abort()

    @inlineCallbacks
    def test_missing_default_vevent_calendar(self):
        """
        Test that pickNewDefaultCalendar will create a missing default calendar.
        """
        
        
        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        home = yield request.locateResource("/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property initially not present
        try:
            inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            pass
        else:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not empty")

        # Forcibly remove the one we need
        yield home._newStoreHome.removeChildWithName("calendar")
        names = [calendarName for calendarName in (yield home._newStoreHome.listCalendars())]
        self.assertTrue("calendar" not in names)

        yield inbox.pickNewDefaultCalendar(request)

        try:
            default = inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar")

        request._newStoreTransaction.abort()

    @inlineCallbacks
    def test_missing_default_vtodo_calendar(self):
        """
        Test that pickNewDefaultCalendar will create a missing default tasks calendar.
        """
        
        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        home = yield request.locateResource("/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property initially not present
        try:
            inbox.readDeadProperty(customxml.ScheduleDefaultTasksURL)
        except HTTPError:
            pass
        else:
            self.fail("caldavxml.ScheduleDefaultTasksURL is not empty")

        # Forcibly remove the one we need
        yield home._newStoreHome.removeChildWithName("tasks")
        names = [calendarName for calendarName in (yield home._newStoreHome.listCalendars())]
        self.assertTrue("tasks" not in names)

        yield inbox.pickNewDefaultCalendar(request, tasks=True)

        try:
            default = inbox.readDeadProperty(customxml.ScheduleDefaultTasksURL)
        except HTTPError:
            self.fail("caldavxml.ScheduleDefaultTasksURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/tasks")

        request._newStoreTransaction.abort()

    @inlineCallbacks
    def test_pick_default_other(self):
        """
        Make calendar
        """
        

        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property not present
        try:
            inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            pass
        else:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not empty")

        # Create a new default calendar
        newcalendar = yield request.locateResource("/calendars/users/wsanchez/newcalendar")
        yield newcalendar.createCalendarCollection()
        inbox.writeDeadProperty(caldavxml.ScheduleDefaultCalendarURL(
            davxml.HRef("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")
        ))
        
        # Delete the normal calendar
        calendar = yield request.locateResource("/calendars/users/wsanchez/calendar")
        yield calendar.storeRemove(request, False, "/calendars/users/wsanchez/calendar")

        inbox.removeDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        
        # default property not present
        try:
            inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            pass
        else:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not empty")
        request._newStoreTransaction.commit()

        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")
        yield inbox.pickNewDefaultCalendar(request)

        try:
            default = inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")

        request._newStoreTransaction.abort()

    @inlineCallbacks
    def test_fix_shared_default(self):
        """
        Make calendar
        """
        

        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # Create a new default calendar
        newcalendar = yield request.locateResource("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")
        yield newcalendar.createCalendarCollection()
        inbox.writeDeadProperty(caldavxml.ScheduleDefaultCalendarURL(
            davxml.HRef("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")
        ))
        try:
            default = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        except HTTPError:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")
        
        # Force the new calendar to think it is a sharee collection
        newcalendar._isShareeCollection = True
        
        try:
            default = yield inbox.readProperty(caldavxml.ScheduleDefaultCalendarURL, request)
        except HTTPError:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar")

        request._newStoreTransaction.abort()

    @inlineCallbacks
    def test_set_default_vevent_other(self):
        """
        Test that the default URL can be set to another VEVENT calendar
        """

        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")

        # default property not present
        try:
            inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            pass
        else:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not empty")

        # Create a new default calendar
        newcalendar = yield request.locateResource("/calendars/users/wsanchez/newcalendar")
        yield newcalendar.createCalendarCollection()
        yield newcalendar.setSupportedComponents(("VEVENT",))
        request._newStoreTransaction.commit()
        
        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")
        yield inbox.writeProperty(caldavxml.ScheduleDefaultCalendarURL(davxml.HRef("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")), request)

        try:
            default = inbox.readDeadProperty(caldavxml.ScheduleDefaultCalendarURL)
        except HTTPError:
            self.fail("caldavxml.ScheduleDefaultCalendarURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newcalendar")

        request._newStoreTransaction.commit()

    @inlineCallbacks
    def test_is_default_calendar(self):
        """
        Test .isDefaultCalendar() returns the proper class or None.
        """
        
        # Create a new non-default calendar
        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        newcalendar = yield request.locateResource("/calendars/users/wsanchez/newcalendar")
        yield newcalendar.createCalendarCollection()
        yield newcalendar.setSupportedComponents(("VEVENT",))
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")
        yield inbox.pickNewDefaultCalendar(request)
        request._newStoreTransaction.commit()
        
        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        inbox = yield request.locateResource("/calendars/users/wsanchez/inbox")
        calendar = yield request.locateResource("/calendars/users/wsanchez/calendar")
        newcalendar = yield request.locateResource("/calendars/users/wsanchez/newcalendar")
        tasks = yield request.locateResource("/calendars/users/wsanchez/tasks")

        result = yield inbox.isDefaultCalendar(request, calendar)
        self.assertEqual(result, caldavxml.ScheduleDefaultCalendarURL)
        
        result = yield inbox.isDefaultCalendar(request, newcalendar)
        self.assertEqual(result, None)
        
        result = yield inbox.isDefaultCalendar(request, tasks)
        self.assertEqual(result, customxml.ScheduleDefaultTasksURL)

        request._newStoreTransaction.commit()

class iSchedulePOST (TestCase):

    def setUp(self):
        super(iSchedulePOST, self).setUp()
        self.createStockDirectoryService()
        self.setupCalendars()
        self.site.resource.putChild("ischedule", IScheduleInboxResource(self.site.resource, self._newStore))

    @inlineCallbacks
    def test_deadlock(self):
        """
        Make calendar
        """
        
        request = SimpleRequest(
            self.site,
            "POST",
            "/ischedule",
            headers=http_headers.Headers(rawHeaders={
                "Originator": ("mailto:wsanchez@example.com",),
                "Recipient": ("mailto:cdaboo@example.com",),
            }),
            content="""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20060101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:deadlocked
ORGANIZER:mailto:wsanchez@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:wsanchez@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:cdaboo@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        )

        # Lock the UID here to force a deadlock - but adjust the timeout so the test does not wait too long
        self.patch(config.Scheduling.Options, "UIDLockTimeoutSeconds", 1)
        lock = MemcacheLock("ImplicitUIDLock", "deadlocked", timeout=60, expire_time=60)
        yield lock.acquire()
        
        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.CONFLICT)
