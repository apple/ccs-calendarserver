##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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
Tests for calendarserver.tools.calverify
"""

from StringIO import StringIO
from calendarserver.tap.util import getRootResource
from calendarserver.tools.calverify import CalVerifyService
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest
from twistedcaldav.config import config
from txdav.caldav.datastore import util
from txdav.common.datastore.test.util import buildStore, populateCalendarsFrom, CommonCommonTests
import os


OK_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:OK
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

# Missing DTSTAMP
BAD1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD1
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

# Bad recurrence
BAD2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD2
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
RRULE:FREQ=DAILY;COUNT=3
SEQUENCE:2
END:VEVENT
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD2
RECURRENCE-ID:20000307T120000Z
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

# Bad recurrence
BAD3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD2
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
RRULE:FREQ=DAILY;COUNT=3
SEQUENCE:2
END:VEVENT
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD2
RECURRENCE-ID:20000307T120000Z
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

# Missing Organizer
BAD3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD3
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
RRULE:FREQ=DAILY;COUNT=3
SEQUENCE:2
END:VEVENT
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD3
RECURRENCE-ID:20000307T111500Z
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:mailto:example2@example.com
ATTENDEE:mailto:example1@example.com
ATTENDEE:mailto:example2@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

# https Organizer
BAD4_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD4
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER:http://demo.com:8008/principals/__uids__/D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:mailto:example1@example.com
ATTENDEE:mailto:example2@example.com
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")


# https Attendee
BAD5_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD5
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER:mailto:example1@example.com
ATTENDEE:http://demo.com:8008/principals/__uids__/D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:mailto:example2@example.com
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")


# https Organizer and Attendee
BAD6_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD6
DTEND:20000307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20000307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER:http://demo.com:8008/principals/__uids__/D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:http://demo.com:8008/principals/__uids__/D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:mailto:example2@example.com
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")


class CalVerifyTests(CommonCommonTests, unittest.TestCase):
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
        "home1" : {
            "calendar1" : {
                "ok.ics" : (OK_ICS, metadata,),
                "bad1.ics" : (BAD1_ICS, metadata,),
                "bad2.ics" : (BAD2_ICS, metadata,),
                "bad3.ics" : (BAD3_ICS, metadata,),
                "bad4.ics" : (BAD4_ICS, metadata,),
                "bad5.ics" : (BAD5_ICS, metadata,),
                "bad6.ics" : (BAD6_ICS, metadata,),
            }
        },
    }

    @inlineCallbacks
    def setUp(self):
        yield super(CalVerifyTests, self).setUp()
        self._sqlCalendarStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()

        self.patch(config.DirectoryService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "calverify", "accounts.xml"
            )
        )
        self.patch(config.ResourceService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "calverify", "resources.xml"
            )
        )
        self.rootResource = getRootResource(config, self._sqlCalendarStore)
        self.directory = self.rootResource.getDirectory()


    @inlineCallbacks
    def populate(self):
        
        # Need to bypass normal validation inside the store
        util.validationBypass = True
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest(), migrating=True)
        util.validationBypass = False
        self.notifierFactory.reset()


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    def verifyResultsByUID(self, results, expected):
        reported = set([(home, uid) for home, uid, _ignore_resid, _ignore_reason in results])
        self.assertEqual(reported, expected)


    @inlineCallbacks
    def test_scanBadData(self):
        """
        CalVerifyService.doScan without fix. Make sure it detects common errors.
        """

        options = {
            "ical":None,
            "verbose":False,
            "uuid":"",
        }
        output = StringIO()
        calverify = CalVerifyService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doScan(True, False, False)

        self.assertEqual(calverify.results["Number of events to process"], 7)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD1",),
            ("home1", "BAD2",),
            ("home1", "BAD3",),
            ("home1", "BAD4",),
            ("home1", "BAD5",),
            ("home1", "BAD6",),
        )))


    @inlineCallbacks
    def test_fixBadData(self):
        """
        CalVerifyService.doScan without fix. Make sure it detects and fixes as much as it can.
        """

        options = {
            "ical":None,
            "verbose":False,
            "uuid":"",
        }
        output = StringIO()
        
        # Do fix
        self.patch(config.Scheduling.Options, "PrincipalHostAliases", "demo.com")
        self.patch(config, "HTTPPort", 8008)
        calverify = CalVerifyService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doScan(True, False, True)

        self.assertEqual(calverify.results["Number of events to process"], 7)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD1",),
            ("home1", "BAD2",),
            ("home1", "BAD3",),
            ("home1", "BAD4",),
            ("home1", "BAD5",),
            ("home1", "BAD6",),
        )))

        # Do scan
        calverify = CalVerifyService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doScan(True, False, False)

        self.assertEqual(calverify.results["Number of events to process"], 7)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD1",),
        )))
