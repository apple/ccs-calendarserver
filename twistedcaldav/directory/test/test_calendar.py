##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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

import os

from twisted.internet.defer import inlineCallbacks
from twisted.web2.dav import davxml
from twisted.web2.test.test_server import SimpleRequest

from twistedcaldav import caldavxml
from twistedcaldav.directory import augment
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.test.test_xmlfile import xmlFile, augmentsFile
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.static import CalendarHomeProvisioningFile

import twistedcaldav.test.util

class ProvisionedCalendars (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """
    def setUp(self):
        super(ProvisionedCalendars, self).setUp()
        
        # Setup the initial directory
        self.xmlFile = self.mktemp()
        fd = open(self.xmlFile, "w")
        fd.write(open(xmlFile.path, "r").read())
        fd.close()
        self.directoryService = XMLDirectoryService({'xmlFile' : self.xmlFile})
        augment.AugmentService = augment.AugmentXMLDB(xmlFiles=(augmentsFile.path,))
        
        # Set up a principals hierarchy for each service we're testing with
        name = "principals"
        url = "/" + name + "/"

        provisioningResource = DirectoryPrincipalProvisioningResource(url, self.directoryService)

        self.site.resource.putChild("principals", provisioningResource)

        self.setupCalendars()

        self.site.resource.setAccessControlList(davxml.ACL())

    def setupCalendars(self):
        calendarCollection = CalendarHomeProvisioningFile(
            os.path.join(self.docroot, "calendars"),
            self.directoryService,
            "/calendars/"
        )
        self.site.resource.putChild("calendars", calendarCollection)

    def test_NonExistentCalendarHome(self):

        def _response(resource):
            if resource is not None:
                self.fail("Incorrect response to GET on non-existent calendar home.")

        request = SimpleRequest(self.site, "GET", "/calendars/users/12345/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)

    def test_ExistentCalendarHome(self):

        def _response(resource):
            if resource is None:
                self.fail("Incorrect response to GET on existent calendar home.")

        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)

    def test_ExistentCalendar(self):

        def _response(resource):
            if resource is None:
                self.fail("Incorrect response to GET on existent calendar.")

        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/calendar/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)

    def test_ExistentInbox(self):

        def _response(resource):
            if resource is None:
                self.fail("Incorrect response to GET on existent inbox.")

        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/inbox/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)

    @inlineCallbacks
    def test_CalendarTranspProperty(self):

        request = SimpleRequest(self.site, "GET", "/calendars/users/wsanchez/calendar/")

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
            davxml.HRef.fromString("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar"),
        ))

        # Now remove the dead property to simulate the old calendar server state with
        # a calendar listed in the fbset
        yield calendar.removeDeadProperty(caldavxml.ScheduleCalendarTransp)
        fbset = (yield inbox.readProperty(caldavxml.CalendarFreeBusySet, request))
        self.assertEqual(fbset, caldavxml.CalendarFreeBusySet(
            davxml.HRef.fromString("/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/calendar"),
        ))

        # Calendar has opaque property derived from inbox
        transp = (yield calendar.hasProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertTrue(transp)

        transp = (yield calendar.readProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertEqual(transp, caldavxml.ScheduleCalendarTransp(caldavxml.Opaque()))

        # Now remove the dead property and the inbox fbset item to simulate the old calendar server state
        yield calendar.removeDeadProperty(caldavxml.ScheduleCalendarTransp)
        yield inbox.removeDeadProperty(caldavxml.CalendarFreeBusySet)

        # Calendar has transp property derived from inbox
        transp = (yield calendar.hasProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertTrue(transp)

        transp = (yield calendar.readProperty(caldavxml.ScheduleCalendarTransp, request))
        self.assertEqual(transp, caldavxml.ScheduleCalendarTransp(caldavxml.Transparent()))

