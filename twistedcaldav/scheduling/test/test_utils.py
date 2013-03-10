##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
from twistedcaldav.scheduling.utils import getCalendarObjectForPrincipals

"""
Tests for calendarserver.tools.purge
"""

from calendarserver.tap.util import getRootResource, FakeRequest

from pycalendar.datetime import PyCalendarDateTime

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from twistedcaldav.config import config

from txdav.common.datastore.test.util import buildStore, populateCalendarsFrom, CommonCommonTests

import os


now = PyCalendarDateTime.getToday().getYear()

ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:685BC3A1-195A-49B3-926D-388DDACA78A6
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
ORGANIZER:urn:uuid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:user02
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now + 1}

ATTENDEE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:685BC3A1-195A-49B3-926D-388DDACA78A6
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
ORGANIZER:urn:uuid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:user02
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now + 1}



class RecipientCopy(CommonCommonTests, unittest.TestCase):
    """
    Tests for deleting events older than a given date
    """

    metadata = {
        "accessMode": "PUBLIC",
        "isScheduleObject": True,
        "scheduleTag": "abc",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }

    requirements = {
        "user01" : {
            "calendar1" : {
                "1.ics" : (ORGANIZER_ICS, metadata,),
            }
        },
        "user02" : {
            "calendar2" : {
                "2.ics" : (ATTENDEE_ICS, metadata,),
            },
            "calendar3" : {
                "3.ics" : (ATTENDEE_ICS, metadata,),
            }
        }
    }

    @inlineCallbacks
    def setUp(self):

        yield super(RecipientCopy, self).setUp()
        self._sqlCalendarStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()

        self.patch(config.DirectoryService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "accounts.xml"
            )
        )
        self.patch(config.ResourceService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "resources.xml"
            )
        )
        self.rootResource = getRootResource(config, self._sqlCalendarStore)
        self.directory = self.rootResource.getDirectory()


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
    def test_getCalendarObjectForPrincipals(self):
        """
        Test that L{twistedcaldav.scheduling.utils.getCalendarObjectForPrincipals} detects and removes
        resources with duplicate UIDs in the same calendar home.
        """

        # Check that expected resources are present
        request = FakeRequest(self.rootResource, "PUT", path='/user01/outbox')
        for uri in (
            "/calendars/__uids__/user01/calendar1/1.ics",
            "/calendars/__uids__/user02/calendar2/2.ics",
            "/calendars/__uids__/user02/calendar3/3.ics",
        ):
            resource = (yield request.locateResource(uri))
            self.assertNotEqual(resource, None)
        yield request._newStoreTransaction.commit()

        # Look up resource by UID in home where only one exists
        request = FakeRequest(self.rootResource, "PUT", path='/user01/outbox')
        principalCollection = self.directory.principalCollection
        principal = principalCollection.principalForUID("user01")
        _ignore_resource, rname, _ignore_calendar, calendar_uri = (yield getCalendarObjectForPrincipals(request, principal, "685BC3A1-195A-49B3-926D-388DDACA78A6"))
        self.assertEqual(rname, "1.ics")
        self.assertEqual(calendar_uri, "/calendars/__uids__/user01/calendar1")
        yield request._newStoreTransaction.commit()

        # Check that expected resources are still present
        request = FakeRequest(self.rootResource, "PUT", path='/user01/outbox')
        for uri in (
            "/calendars/__uids__/user01/calendar1/1.ics",
            "/calendars/__uids__/user02/calendar2/2.ics",
            "/calendars/__uids__/user02/calendar3/3.ics",
        ):
            resource = (yield request.locateResource(uri))
            self.assertNotEqual(resource, None)

        # Look up resource by UID in home where two exists
        request = FakeRequest(self.rootResource, "PUT", path='/user01/outbox')
        principalCollection = self.directory.principalCollection
        principal = principalCollection.principalForUID("user02")
        _ignore_resource, rname, _ignore_calendar, calendar_uri = (yield getCalendarObjectForPrincipals(request, principal, "685BC3A1-195A-49B3-926D-388DDACA78A6"))
        self.assertTrue(
            (rname, calendar_uri) in
            (
                ("2.ics", "/calendars/__uids__/user02/calendar2"),
                ("3.ics", "/calendars/__uids__/user02/calendar3"),
            )
        )
        yield request._newStoreTransaction.commit()

        # Check that expected resources are still present, but the duplicate missing
        request = FakeRequest(self.rootResource, "PUT", path='/user01/outbox')
        resource = (yield request.locateResource("/calendars/__uids__/user01/calendar1/1.ics"))
        self.assertNotEqual(resource, None)
        resource2 = (yield request.locateResource("/calendars/__uids__/user02/calendar2/2.ics"))
        resource3 = (yield request.locateResource("/calendars/__uids__/user02/calendar3/3.ics"))
        self.assertTrue(resource2.exists() ^ resource3.exists())
