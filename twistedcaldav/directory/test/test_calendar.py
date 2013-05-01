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

from twisted.internet.defer import inlineCallbacks
from txdav.xml import element as davxml

from twistedcaldav import caldavxml

from twistedcaldav.test.util import StoreTestCase, SimpleStoreRequest
from twistedcaldav.directory.util import NotFoundResource

class ProvisionedCalendars (StoreTestCase):
    """
    Directory service provisioned principals.
    """

    def oneRequest(self, uri):
        return SimpleStoreRequest(self, "GET", uri)


    def test_NonExistentCalendarHome(self):
        """
        Requests for missing homes and principals should return
        NotFoundResources so that we have the opportunity to
        turn 404s into 401s to protect against user-existence attacks.
        """

        def _response(resource):
            self.assertTrue(isinstance(resource, NotFoundResource))

        request = self.oneRequest("/calendars/users/12345/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)
        return d


    def test_ExistentCalendarHome(self):

        def _response(resource):
            if resource is None:
                self.fail("Incorrect response to GET on existent calendar home.")

        request = self.oneRequest("/calendars/users/wsanchez/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)
        return d


    def test_ExistentCalendar(self):

        def _response(resource):
            if resource is None:
                self.fail("Incorrect response to GET on existent calendar.")

        request = self.oneRequest("/calendars/users/wsanchez/calendar/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)
        return d


    def test_ExistentInbox(self):

        def _response(resource):
            if resource is None:
                self.fail("Incorrect response to GET on existent inbox.")

        request = self.oneRequest("/calendars/users/wsanchez/inbox/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)
        return d


    @inlineCallbacks
    def test_CalendarTranspProperty(self):

        request = self.oneRequest("/calendars/users/wsanchez/calendar/")

        # Get calendar first
        calendar = (yield request.locateResource("/calendars/users/wsanchez/calendar/"))
        if calendar is None:
            self.fail("Incorrect response to GET on existent calendar.")

        inbox = (yield request.locateResource("/calendars/users/wsanchez/inbox/"))
        if inbox is None:
            self.fail("Incorrect response to GET on existent inbox.")

        # Provisioned calendar has default opaque property
        transp = (yield calendar.hasProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertTrue(transp)

        transp = (yield calendar.readProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertEqual(transp, caldavxml.ScheduleCalendarTransp(caldavxml.Opaque()))

        # Inbox property lists the default calendar
        fbset = (yield inbox.hasProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertTrue(fbset)

        fbset = (yield inbox.readProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertEqual(fbset, caldavxml.CalendarFreeBusySet(
            davxml.HRef.fromString("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar/"),
        ))

        # Now remove the property to simulate the old calendar server state with
        # a calendar listed in the fbset
        yield calendar._newStoreObject.setUsedForFreeBusy(False)
        fbset = (yield inbox.readProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertEqual(fbset, caldavxml.CalendarFreeBusySet())

        # Calendar has opaque property derived from inbox
        transp = (yield calendar.hasProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertTrue(transp)

        transp = (yield calendar.readProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertEqual(transp, caldavxml.ScheduleCalendarTransp(caldavxml.Transparent()))

        # Force trailing slash on fbset
        yield inbox.writeProperty(caldavxml.CalendarFreeBusySet(
            davxml.HRef.fromString("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar/"),
        ), request)

        # Now remove the dead property to simulate the old calendar server state with
        # a calendar listed in the fbset
        fbset = (yield inbox.readProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertEqual(fbset, caldavxml.CalendarFreeBusySet(
            davxml.HRef.fromString("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar/"),
        ))

        # Calendar has opaque property derived from inbox
        transp = (yield calendar.hasProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertTrue(transp)

        transp = (yield calendar.readProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertEqual(transp, caldavxml.ScheduleCalendarTransp(caldavxml.Opaque()))
