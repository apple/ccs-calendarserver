##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
from __future__ import print_function

"""
Tests for calendarserver.tools.calverify
"""

from calendarserver.tools.calverify import BadDataService, \
    SchedulingMismatchService, DoubleBookingService, DarkPurgeService

from pycalendar.datetime import PyCalendarDateTime

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

from twistedcaldav.config import config
from twistedcaldav.test.util import StoreTestCase

from txdav.common.datastore.test.util import populateCalendarsFrom

from StringIO import StringIO
import os


OK_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:OK
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
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
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
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
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
RRULE:FREQ=DAILY;COUNT=3
SEQUENCE:2
END:VEVENT
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD2
RECURRENCE-ID:20100307T120000Z
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
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
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
RRULE:FREQ=DAILY;COUNT=3
SEQUENCE:2
END:VEVENT
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD2
RECURRENCE-ID:20100307T120000Z
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
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
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
RRULE:FREQ=DAILY;COUNT=3
SEQUENCE:2
END:VEVENT
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD3
RECURRENCE-ID:20100307T111500Z
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
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
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER:http://demo.com:8008/principals/__uids__/D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
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
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:http://demo.com:8008/principals/__uids__/D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
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
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER:http://demo.com:8008/principals/__uids__/D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:http://demo.com:8008/principals/__uids__/D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")


# Non-base64 Organizer and Attendee parameter
BAD7_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD7
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER;CALENDARSERVER-OLD-CUA="http://demo.com:8008/principals/__uids__/
 D46F3D71-04B7-43C2-A7B6-6F92F92E61D0":urn:uuid:D46F3D71-04B7-43C2-A7B6-6F9
 2F92E61D0
ATTENDEE;CALENDARSERVER-OLD-CUA="http://demo.com:8008/principals/__uids__/D
 46F3D71-04B7-43C2-A7B6-6F92F92E61D0":urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92
 F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")


# Base64 Organizer and Attendee parameter
OK8_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:OK8
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER;CALENDARSERVER-OLD-CUA="base64-aHR0cDovL2RlbW8uY29tOjgwMDgvcHJpbm
 NpcGFscy9fX3VpZHNfXy9ENDZGM0Q3MS0wNEI3LTQzQzItQTdCNi02RjkyRjkyRTYxRDA=":
 urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;CALENDARSERVER-OLD-CUA="base64-aHR0cDovL2RlbW8uY29tOjgwMDgvcHJpbmN
 pcGFscy9fX3VpZHNfXy9ENDZGM0Q3MS0wNEI3LTQzQzItQTdCNi02RjkyRjkyRTYxRDA=":u
 rn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

BAD9_ICS = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:19621028T020000
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19870405T020000
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYDAY=1SU;BYMONTH=4
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:BAD9
DTSTART;TZID=US/Pacific:20111103T150000
DTEND;TZID=US/Pacific:20111103T160000
ATTENDEE;CALENDARSERVER-OLD-CUA="//example.com\\:8443/principals/users/cyrus
 /;CN=\\"Cyrus Daboo\\";CUTYPE=INDIVIDUAL;EMAIL=\\"cyrus@example.com\\";PARTSTAT=ACC
 EPTED:urn:uuid:7B2636C7-07F6-4475-924B-2854107F7A22";CN=Cyrus Daboo;EMAIL=c
 yrus@example.com;RSVP=TRUE:urn:uuid:7B2636C7-07F6-4475-924B-2854107F7A22
ATTENDEE;CN=John Smith;CUTYPE=INDIVIDUAL;EMAIL=smith@example.com;PARTSTAT=AC
 CEPTED;ROLE=REQ-PARTICIPANT:urn:uuid:E975EB3D-C412-411B-A655-C3BE4949788C
CREATED:20090730T214912Z
DTSTAMP:20120421T182823Z
ORGANIZER;CALENDARSERVER-OLD-CUA="//example.com\\:8443/principals/users/cyru
 s/;CN=\\"Cyrus Daboo\\";EMAIL=\\"cyrus@example.com\\":urn:uuid:7B2636C7-07F6-4475-9
 24B-2854107F7A22";CN=Cyrus Daboo;EMAIL=cyrus@example.com:urn:uuid:7B2636C7-
 07F6-4475-924B-2854107F7A22
RRULE:FREQ=WEEKLY;COUNT=400
SEQUENCE:18
SUMMARY:1-on-1
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

# Non-mailto: Organizer
BAD10_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD10
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER;CN=Example User1;SCHEDULE-AGENT=NONE:example1@example.com
ATTENDEE;CN=Example User1:example1@example.com
ATTENDEE;CN=Example User2:example2@example.com
ATTENDEE;CN=Example User3:/principals/users/example3
ATTENDEE;CN=Example User4:http://demo.com:8008/principals/users/example4
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

# Bad recurrence EXDATE
BAD11_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD11
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
EXDATE:20100314T111500Z
RRULE:FREQ=WEEKLY
SEQUENCE:2
END:VEVENT
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD11
RECURRENCE-ID:20100314T111500Z
DTEND:20100314T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100314T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

BAD12_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD12
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
ORGANIZER:mailto:example2@example.com
ATTENDEE:mailto:example1@example.com
ATTENDEE:mailto:example2@example.com
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

BAD13_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:BAD13
DTEND:20100307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:20100307T111500Z
DTSTAMP:20100303T181220Z
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")



class CalVerifyDataTests(StoreTestCase):
    """
    Tests calverify for iCalendar data problems.
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
            "calendar_1" : {
                "ok.ics"   : (OK_ICS, metadata,),
                "bad1.ics" : (BAD1_ICS, metadata,),
                "bad2.ics" : (BAD2_ICS, metadata,),
                "bad3.ics" : (BAD3_ICS, metadata,),
                "bad4.ics" : (BAD4_ICS, metadata,),
                "bad5.ics" : (BAD5_ICS, metadata,),
                "bad6.ics" : (BAD6_ICS, metadata,),
                "bad7.ics" : (BAD7_ICS, metadata,),
                "ok8.ics"  : (OK8_ICS, metadata,),
                "bad9.ics" : (BAD9_ICS, metadata,),
                "bad10.ics" : (BAD10_ICS, metadata,),
                "bad11.ics" : (BAD11_ICS, metadata,),
                "bad12.ics" : (BAD12_ICS, metadata,),
                "bad13.ics" : (BAD13_ICS, metadata,),
            }
        },
    }

    number_to_process = len(requirements["home1"]["calendar_1"])

    def configure(self):
        super(CalVerifyDataTests, self).configure()
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


    @inlineCallbacks
    def populate(self):

        # Need to bypass normal validation inside the store
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
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
        Make sure sync-token is not changed.
        """

        sync_token_old = (yield (yield self.calendarUnderTest()).syncToken())
        self.commit()

        options = {
            "ical": True,
            "fix": False,
            "nobase64": False,
            "verbose": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
        }
        output = StringIO()
        calverify = BadDataService(self._sqlCalendarStore, options, output, reactor, config)
        calverify.emailDomain = "example.com"
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], self.number_to_process)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD1",),
            ("home1", "BAD2",),
            ("home1", "BAD3",),
            ("home1", "BAD4",),
            ("home1", "BAD5",),
            ("home1", "BAD6",),
            ("home1", "BAD7",),
            ("home1", "BAD9",),
            ("home1", "BAD10",),
            ("home1", "BAD11",),
            ("home1", "BAD12",),
            ("home1", "BAD13",),
        )))

        sync_token_new = (yield (yield self.calendarUnderTest()).syncToken())
        self.assertEqual(sync_token_old, sync_token_new)


    @inlineCallbacks
    def test_fixBadData(self):
        """
        CalVerifyService.doScan with fix. Make sure it detects and fixes as much as it can.
        Make sure sync-token is changed.
        """

        sync_token_old = (yield (yield self.calendarUnderTest()).syncToken())
        self.commit()

        options = {
            "ical": True,
            "fix": True,
            "nobase64": False,
            "verbose": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
        }
        output = StringIO()

        # Do fix
        self.patch(config.Scheduling.Options, "PrincipalHostAliases", "demo.com")
        self.patch(config, "HTTPPort", 8008)
        calverify = BadDataService(self._sqlCalendarStore, options, output, reactor, config)
        calverify.emailDomain = "example.com"
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], self.number_to_process)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD1",),
            ("home1", "BAD2",),
            ("home1", "BAD3",),
            ("home1", "BAD4",),
            ("home1", "BAD5",),
            ("home1", "BAD6",),
            ("home1", "BAD7",),
            ("home1", "BAD9",),
            ("home1", "BAD10",),
            ("home1", "BAD11",),
            ("home1", "BAD12",),
            ("home1", "BAD13",),
        )))

        # Do scan
        options["fix"] = False
        calverify = BadDataService(self._sqlCalendarStore, options, output, reactor, config)
        calverify.emailDomain = "example.com"
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], self.number_to_process)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD1",),
            ("home1", "BAD13",),
        )))

        sync_token_new = (yield (yield self.calendarUnderTest()).syncToken())
        self.assertNotEqual(sync_token_old, sync_token_new)

        # Make sure mailto: fix results in urn:uuid value without SCHEDULE-AGENT
        obj = yield self.calendarObjectUnderTest(name="bad10.ics")
        ical = yield obj.component()
        org = ical.getOrganizerProperty()
        self.assertEqual(org.value(), "urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0")
        self.assertFalse(org.hasParameter("SCHEDULE-AGENT"))
        for attendee in ical.getAllAttendeeProperties():
            self.assertTrue(
                attendee.value().startswith("urn:uuid:") or
                attendee.value().startswith("/principals")
            )


    @inlineCallbacks
    def test_scanBadCuaOnly(self):
        """
        CalVerifyService.doScan without fix for CALENDARSERVER-OLD-CUA only. Make sure it detects
        and fixes as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old = (yield (yield self.calendarUnderTest()).syncToken())
        self.commit()

        options = {
            "ical": False,
            "fix": False,
            "badcua": True,
            "nobase64": False,
            "verbose": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
        }
        output = StringIO()
        calverify = BadDataService(self._sqlCalendarStore, options, output, reactor, config)
        calverify.emailDomain = "example.com"
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], self.number_to_process)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD4",),
            ("home1", "BAD5",),
            ("home1", "BAD6",),
            ("home1", "BAD7",),
            ("home1", "BAD9",),
            ("home1", "BAD10",),
            ("home1", "BAD12",),
        )))

        sync_token_new = (yield (yield self.calendarUnderTest()).syncToken())
        self.assertEqual(sync_token_old, sync_token_new)


    @inlineCallbacks
    def test_fixBadCuaOnly(self):
        """
        CalVerifyService.doScan with fix for CALENDARSERVER-OLD-CUA only. Make sure it detects
        and fixes as much as it can. Make sure sync-token is changed.
        """

        sync_token_old = (yield (yield self.calendarUnderTest()).syncToken())
        self.commit()

        options = {
            "ical": False,
            "fix": True,
            "badcua": True,
            "nobase64": False,
            "verbose": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
        }
        output = StringIO()

        # Do fix
        self.patch(config.Scheduling.Options, "PrincipalHostAliases", "demo.com")
        self.patch(config, "HTTPPort", 8008)
        calverify = BadDataService(self._sqlCalendarStore, options, output, reactor, config)
        calverify.emailDomain = "example.com"
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], self.number_to_process)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD4",),
            ("home1", "BAD5",),
            ("home1", "BAD6",),
            ("home1", "BAD7",),
            ("home1", "BAD9",),
            ("home1", "BAD10",),
            ("home1", "BAD12",),
        )))

        # Do scan
        options["fix"] = False
        calverify = BadDataService(self._sqlCalendarStore, options, output, reactor, config)
        calverify.emailDomain = "example.com"
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], self.number_to_process)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
        )))

        sync_token_new = (yield (yield self.calendarUnderTest()).syncToken())
        self.assertNotEqual(sync_token_old, sync_token_new)


    def test_fixBadCuaLines(self):
        """
        CalVerifyService.fixBadOldCuaLines. Make sure it applies correct fix.
        """

        data = (
            (
                """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:19621028T020000
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19870405T020000
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYDAY=1SU;BYMONTH=4
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:32956D5C-579F-46FD-BAE3-4A6C354B8CA3
DTSTART;TZID=US/Pacific:20111103T150000
DTEND;TZID=US/Pacific:20111103T160000
ATTENDEE;CALENDARSERVER-OLD-CUA="//example.com\\:8443/principals/users/cyrus
 /;CN="Cyrus Daboo";CUTYPE=INDIVIDUAL;EMAIL="cyrus@example.com";PARTSTAT=ACC
 EPTED:urn:uuid:7B2636C7-07F6-4475-924B-2854107F7A22";CN=Cyrus Daboo;EMAIL=c
 yrus@example.com;RSVP=TRUE:urn:uuid:7B2636C7-07F6-4475-924B-2854107F7A22
ATTENDEE;CN=John Smith;CUTYPE=INDIVIDUAL;EMAIL=smith@example.com;PARTSTAT=AC
 CEPTED;ROLE=REQ-PARTICIPANT:urn:uuid:E975EB3D-C412-411B-A655-C3BE4949788C
CREATED:20090730T214912Z
DTSTAMP:20120421T182823Z
ORGANIZER;CALENDARSERVER-OLD-CUA="//example.com\\:8443/principals/users/cyru
 s/;CN="Cyrus Daboo";EMAIL="cyrus@example.com":urn:uuid:7B2636C7-07F6-4475-9
 24B-2854107F7A22";CN=Cyrus Daboo;EMAIL=cyrus@example.com:urn:uuid:7B2636C7-
 07F6-4475-924B-2854107F7A22
RRULE:FREQ=WEEKLY;COUNT=400
SEQUENCE:18
SUMMARY:1-on-1
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"),
                """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:19621028T020000
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19870405T020000
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYDAY=1SU;BYMONTH=4
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:32956D5C-579F-46FD-BAE3-4A6C354B8CA3
DTSTART;TZID=US/Pacific:20111103T150000
DTEND;TZID=US/Pacific:20111103T160000
ATTENDEE;CALENDARSERVER-OLD-CUA="https://example.com:8443/principals/users/c
 yrus/";CN=Cyrus Daboo;EMAIL=cyrus@example.com;RSVP=TRUE:urn:uuid:7B2636C7-0
 7F6-4475-924B-2854107F7A22
ATTENDEE;CN=John Smith;CUTYPE=INDIVIDUAL;EMAIL=smith@example.com;PARTSTAT=AC
 CEPTED;ROLE=REQ-PARTICIPANT:urn:uuid:E975EB3D-C412-411B-A655-C3BE4949788C
CREATED:20090730T214912Z
DTSTAMP:20120421T182823Z
ORGANIZER;CALENDARSERVER-OLD-CUA="https://example.com:8443/principals/users/
 cyrus/";CN=Cyrus Daboo;EMAIL=cyrus@example.com:urn:uuid:7B2636C7-07F6-4475-
 924B-2854107F7A22
RRULE:FREQ=WEEKLY;COUNT=400
SEQUENCE:18
SUMMARY:1-on-1
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"),
                """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:19621028T020000
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19870405T020000
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYDAY=1SU;BYMONTH=4
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:32956D5C-579F-46FD-BAE3-4A6C354B8CA3
DTSTART;TZID=US/Pacific:20111103T150000
DTEND;TZID=US/Pacific:20111103T160000
ATTENDEE;CALENDARSERVER-OLD-CUA=base64-aHR0cHM6Ly9leGFtcGxlLmNvbTo4NDQzL3Bya
 W5jaXBhbHMvdXNlcnMvY3lydXMv;CN=Cyrus Daboo;EMAIL=cyrus@example.com;RSVP=TRU
 E:urn:uuid:7B2636C7-07F6-4475-924B-2854107F7A22
ATTENDEE;CN=John Smith;CUTYPE=INDIVIDUAL;EMAIL=smith@example.com;PARTSTAT=AC
 CEPTED;ROLE=REQ-PARTICIPANT:urn:uuid:E975EB3D-C412-411B-A655-C3BE4949788C
CREATED:20090730T214912Z
DTSTAMP:20120421T182823Z
ORGANIZER;CALENDARSERVER-OLD-CUA=base64-aHR0cHM6Ly9leGFtcGxlLmNvbTo4NDQzL3By
 aW5jaXBhbHMvdXNlcnMvY3lydXMv;CN=Cyrus Daboo;EMAIL=cyrus@example.com:urn:uui
 d:7B2636C7-07F6-4475-924B-2854107F7A22
RRULE:FREQ=WEEKLY;COUNT=400
SEQUENCE:18
SUMMARY:1-on-1
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"),
            ),
        )

        optionsNo64 = {
            "ical": True,
            "nobase64": True,
            "verbose": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
        }
        calverifyNo64 = BadDataService(self._sqlCalendarStore, optionsNo64, StringIO(), reactor, config)
        calverifyNo64.emailDomain = "example.com"

        options64 = {
            "ical": True,
            "nobase64": False,
            "verbose": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
        }
        calverify64 = BadDataService(self._sqlCalendarStore, options64, StringIO(), reactor, config)
        calverify64.emailDomain = "example.com"

        for bad, oknobase64, okbase64 in data:
            bad = bad.replace("\r\n ", "")
            oknobase64 = oknobase64.replace("\r\n ", "")
            okbase64 = okbase64.replace("\r\n ", "")
            self.assertEqual(calverifyNo64.fixBadOldCuaLines(bad), oknobase64)
            self.assertEqual(calverify64.fixBadOldCuaLines(bad), okbase64)



class CalVerifyMismatchTestsBase(StoreTestCase):
    """
    Tests calverify for iCalendar mismatch problems.
    """

    metadata = {
        "accessMode": "PUBLIC",
        "isScheduleObject": True,
        "scheduleTag": "abc",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }

    uuid1 = "D46F3D71-04B7-43C2-A7B6-6F92F92E61D0"
    uuid2 = "47B16BB4-DB5F-4BF6-85FE-A7DA54230F92"
    uuid3 = "AC478592-7783-44D1-B2AE-52359B4E8415"
    uuidl1 = "75EA36BE-F71B-40F9-81F9-CF59BF40CA8F"

    def configure(self):
        super(CalVerifyMismatchTestsBase, self).configure()
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
        self.patch(config.AugmentService.params, "xmlFiles",
            [os.path.join(
                os.path.dirname(__file__), "calverify", "augments.xml"
            ), ]
        )


    @inlineCallbacks
    def populate(self):

        # Need to bypass normal validation inside the store
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


now = PyCalendarDateTime.getToday()
now.setDay(1)
now.offsetMonth(2)
nowYear = now.getYear()
nowMonth = now.getMonth()

class CalVerifyMismatchTestsNonRecurring(CalVerifyMismatchTestsBase):
    """
    Tests calverify for iCalendar mismatch problems for non-recurring events.
    """

    # Organizer has event, attendees do not
    MISSING_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISSING_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Attendees have event, organizer does not
    MISSING_ORGANIZER_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISSING_ORGANIZER_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISSING_ORGANIZER_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISSING_ORGANIZER_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Attendee partstat mismatch
    MISMATCH_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH_ATTENDEE_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH_ATTENDEE_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Attendee events outside time range
    MISMATCH2_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH2_ATTENDEE_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH2_ATTENDEE_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Organizer event outside time range
    MISMATCH_ORGANIZER_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ORGANIZER_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear - 1, "month": nowMonth}

    MISMATCH_ORGANIZER_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ORGANIZER_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Attendee uuid3 has event with different organizer
    MISMATCH3_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH3_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH3_ATTENDEE_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH3_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH3_ATTENDEE_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH3_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH_ORGANIZER_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ORGANIZER_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Attendee uuid3 has event they are not invited to
    MISMATCH2_ORGANIZER_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ORGANIZER_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH2_ORGANIZER_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ORGANIZER_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH2_ORGANIZER_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ORGANIZER_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    requirements = {
        CalVerifyMismatchTestsBase.uuid1 : {
            "calendar" : {
                 "missing_attendee.ics"      : (MISSING_ATTENDEE_1_ICS, CalVerifyMismatchTestsBase.metadata,),
                 "mismatched_attendee.ics"   : (MISMATCH_ATTENDEE_1_ICS, CalVerifyMismatchTestsBase.metadata,),
                 "mismatched2_attendee.ics"  : (MISMATCH2_ATTENDEE_1_ICS, CalVerifyMismatchTestsBase.metadata,),
                 "mismatched3_attendee.ics"  : (MISMATCH3_ATTENDEE_1_ICS, CalVerifyMismatchTestsBase.metadata,),
                 "mismatched_organizer.ics"  : (MISMATCH_ORGANIZER_1_ICS, CalVerifyMismatchTestsBase.metadata,),
                 "mismatched2_organizer.ics" : (MISMATCH2_ORGANIZER_1_ICS, CalVerifyMismatchTestsBase.metadata,),
           },
           "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid2 : {
            "calendar" : {
                "mismatched_attendee.ics"   : (MISMATCH_ATTENDEE_2_ICS, CalVerifyMismatchTestsBase.metadata,),
                "mismatched2_attendee.ics"  : (MISMATCH2_ATTENDEE_2_ICS, CalVerifyMismatchTestsBase.metadata,),
                "mismatched3_attendee.ics"  : (MISMATCH3_ATTENDEE_2_ICS, CalVerifyMismatchTestsBase.metadata,),
                "missing_organizer.ics"     : (MISSING_ORGANIZER_2_ICS, CalVerifyMismatchTestsBase.metadata,),
                "mismatched_organizer.ics"  : (MISMATCH_ORGANIZER_2_ICS, CalVerifyMismatchTestsBase.metadata,),
                "mismatched2_organizer.ics" : (MISMATCH2_ORGANIZER_2_ICS, CalVerifyMismatchTestsBase.metadata,),
            },
           "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid3 : {
            "calendar" : {
                "mismatched_attendee.ics"   : (MISMATCH_ATTENDEE_3_ICS, CalVerifyMismatchTestsBase.metadata,),
                "mismatched3_attendee.ics"  : (MISMATCH3_ATTENDEE_3_ICS, CalVerifyMismatchTestsBase.metadata,),
                "missing_organizer.ics"     : (MISSING_ORGANIZER_3_ICS, CalVerifyMismatchTestsBase.metadata,),
                "mismatched2_organizer.ics" : (MISMATCH2_ORGANIZER_3_ICS, CalVerifyMismatchTestsBase.metadata,),
            },
            "calendar2" : {
                "mismatched_organizer.ics" : (MISMATCH_ORGANIZER_3_ICS, CalVerifyMismatchTestsBase.metadata,),
                "mismatched2_attendee.ics" : (MISMATCH2_ATTENDEE_3_ICS, CalVerifyMismatchTestsBase.metadata,),
            },
           "inbox" : {},
        },
    }

    @inlineCallbacks
    def setUp(self):
        yield super(CalVerifyMismatchTestsNonRecurring, self).setUp()

        home = (yield self.homeUnderTest(name=self.uuid3))
        calendar = (yield self.calendarUnderTest(name="calendar2", home=self.uuid3))
        yield home.setDefaultCalendar(calendar)
        yield self.commit()


    @inlineCallbacks
    def test_scanMismatchOnly(self):
        """
        CalVerifyService.doScan without fix for mismatches. Make sure it detects
        as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_old2 = (yield (yield self.calendarUnderTest(home=self.uuid2, name="calendar")).syncToken())
        sync_token_old3 = (yield (yield self.calendarUnderTest(home=self.uuid3, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": True,
            "nobase64": False,
            "fix": False,
            "verbose": False,
            "details": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
        }
        output = StringIO()
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 17)
        self.assertEqual(calverify.results["Missing Attendee"], set((
            ("MISSING_ATTENDEE_ICS", self.uuid1, self.uuid2,),
            ("MISSING_ATTENDEE_ICS", self.uuid1, self.uuid3,),
        )))
        self.assertEqual(calverify.results["Mismatch Attendee"], set((
            ("MISMATCH_ATTENDEE_ICS", self.uuid1, self.uuid2,),
            ("MISMATCH_ATTENDEE_ICS", self.uuid1, self.uuid3,),
            ("MISMATCH2_ATTENDEE_ICS", self.uuid1, self.uuid2,),
            ("MISMATCH2_ATTENDEE_ICS", self.uuid1, self.uuid3,),
            ("MISMATCH3_ATTENDEE_ICS", self.uuid1, self.uuid3,),
        )))
        self.assertEqual(calverify.results["Missing Organizer"], set((
            ("MISSING_ORGANIZER_ICS", self.uuid2, self.uuid1,),
            ("MISSING_ORGANIZER_ICS", self.uuid3, self.uuid1,),
        )))
        self.assertEqual(calverify.results["Mismatch Organizer"], set((
            ("MISMATCH_ORGANIZER_ICS", self.uuid2, self.uuid1,),
            ("MISMATCH_ORGANIZER_ICS", self.uuid3, self.uuid1,),
            ("MISMATCH2_ORGANIZER_ICS", self.uuid3, self.uuid1,),
        )))

        self.assertTrue("Fix change event" not in calverify.results)
        self.assertTrue("Fix add event" not in calverify.results)
        self.assertTrue("Fix add inbox" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)
        self.assertTrue("Fix failures" not in calverify.results)
        self.assertTrue("Auto-Accepts" not in calverify.results)

        sync_token_new1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_new2 = (yield (yield self.calendarUnderTest(home=self.uuid2, name="calendar")).syncToken())
        sync_token_new3 = (yield (yield self.calendarUnderTest(home=self.uuid3, name="calendar")).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertEqual(sync_token_old2, sync_token_new2)
        self.assertEqual(sync_token_old3, sync_token_new3)


    @inlineCallbacks
    def test_fixMismatch(self):
        """
        CalVerifyService.doScan with fix for mismatches. Make sure it detects
        and fixes as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_old2 = (yield (yield self.calendarUnderTest(home=self.uuid2, name="calendar")).syncToken())
        sync_token_old3 = (yield (yield self.calendarUnderTest(home=self.uuid3, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": True,
            "nobase64": False,
            "fix": True,
            "verbose": False,
            "details": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
        }
        output = StringIO()
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 17)
        self.assertEqual(calverify.results["Missing Attendee"], set((
            ("MISSING_ATTENDEE_ICS", self.uuid1, self.uuid2,),
            ("MISSING_ATTENDEE_ICS", self.uuid1, self.uuid3,),
        )))
        self.assertEqual(calverify.results["Mismatch Attendee"], set((
            ("MISMATCH_ATTENDEE_ICS", self.uuid1, self.uuid2,),
            ("MISMATCH_ATTENDEE_ICS", self.uuid1, self.uuid3,),
            ("MISMATCH2_ATTENDEE_ICS", self.uuid1, self.uuid2,),
            ("MISMATCH2_ATTENDEE_ICS", self.uuid1, self.uuid3,),
            ("MISMATCH3_ATTENDEE_ICS", self.uuid1, self.uuid3,),
        )))
        self.assertEqual(calverify.results["Missing Organizer"], set((
            ("MISSING_ORGANIZER_ICS", self.uuid2, self.uuid1,),
            ("MISSING_ORGANIZER_ICS", self.uuid3, self.uuid1,),
        )))
        self.assertEqual(calverify.results["Mismatch Organizer"], set((
            ("MISMATCH_ORGANIZER_ICS", self.uuid2, self.uuid1,),
            ("MISMATCH_ORGANIZER_ICS", self.uuid3, self.uuid1,),
            ("MISMATCH2_ORGANIZER_ICS", self.uuid3, self.uuid1,),
        )))

        self.assertEqual(calverify.results["Fix change event"], set((
            (self.uuid2, "calendar", "MISMATCH_ATTENDEE_ICS",),
            (self.uuid3, "calendar", "MISMATCH_ATTENDEE_ICS",),
            (self.uuid2, "calendar", "MISMATCH2_ATTENDEE_ICS",),
            (self.uuid3, "calendar2", "MISMATCH2_ATTENDEE_ICS",),
            (self.uuid3, "calendar", "MISMATCH3_ATTENDEE_ICS",),
            (self.uuid2, "calendar", "MISMATCH_ORGANIZER_ICS",),
            (self.uuid3, "calendar2", "MISMATCH_ORGANIZER_ICS",),
        )))

        self.assertEqual(calverify.results["Fix add event"], set((
            (self.uuid2, "calendar", "MISSING_ATTENDEE_ICS",),
            (self.uuid3, "calendar2", "MISSING_ATTENDEE_ICS",),
        )))

        self.assertEqual(calverify.results["Fix add inbox"], set((
            (self.uuid2, "MISSING_ATTENDEE_ICS",),
            (self.uuid3, "MISSING_ATTENDEE_ICS",),
            (self.uuid2, "MISMATCH_ATTENDEE_ICS",),
            (self.uuid3, "MISMATCH_ATTENDEE_ICS",),
            (self.uuid2, "MISMATCH2_ATTENDEE_ICS",),
            (self.uuid3, "MISMATCH2_ATTENDEE_ICS",),
            (self.uuid3, "MISMATCH3_ATTENDEE_ICS",),
            (self.uuid2, "MISMATCH_ORGANIZER_ICS",),
            (self.uuid3, "MISMATCH_ORGANIZER_ICS",),
        )))

        self.assertEqual(calverify.results["Fix remove"], set((
            (self.uuid2, "calendar", "missing_organizer.ics",),
            (self.uuid3, "calendar", "missing_organizer.ics",),
            (self.uuid3, "calendar", "mismatched2_organizer.ics",),
        )))
        obj = yield self.calendarObjectUnderTest(home=self.uuid2, calendar_name="calendar", name="missing_organizer.ics")
        self.assertEqual(obj, None)
        obj = yield self.calendarObjectUnderTest(home=self.uuid3, calendar_name="calendar", name="missing_organizer.ics")
        self.assertEqual(obj, None)
        obj = yield self.calendarObjectUnderTest(home=self.uuid3, calendar_name="calendar", name="mismatched2_organizer.ics")
        self.assertEqual(obj, None)

        self.assertEqual(calverify.results["Fix failures"], 0)
        self.assertEqual(calverify.results["Auto-Accepts"], [])

        sync_token_new1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_new2 = (yield (yield self.calendarUnderTest(home=self.uuid2, name="calendar")).syncToken())
        sync_token_new3 = (yield (yield self.calendarUnderTest(home=self.uuid3, name="calendar")).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertNotEqual(sync_token_old2, sync_token_new2)
        self.assertNotEqual(sync_token_old3, sync_token_new3)

        # Re-scan after changes to make sure there are no errors
        self.commit()
        options["fix"] = False
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 14)
        self.assertTrue("Missing Attendee" not in calverify.results)
        self.assertTrue("Mismatch Attendee" not in calverify.results)
        self.assertTrue("Missing Organizer" not in calverify.results)
        self.assertTrue("Mismatch Organizer" not in calverify.results)
        self.assertTrue("Fix add event" not in calverify.results)
        self.assertTrue("Fix add inbox" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)
        self.assertTrue("Fix failures" not in calverify.results)
        self.assertTrue("Auto-Accepts" not in calverify.results)



class CalVerifyMismatchTestsAutoAccept(CalVerifyMismatchTestsBase):
    """
    Tests calverify for iCalendar mismatch problems for auto-accept attendees.
    """

    # Organizer has event, attendee do not
    MISSING_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISSING_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Attendee partstat mismatch
    MISMATCH_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH_ATTENDEE_L1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    requirements = {
        CalVerifyMismatchTestsBase.uuid1 : {
            "calendar" : {
                 "missing_attendee.ics"      : (MISSING_ATTENDEE_1_ICS, CalVerifyMismatchTestsBase.metadata,),
                 "mismatched_attendee.ics"   : (MISMATCH_ATTENDEE_1_ICS, CalVerifyMismatchTestsBase.metadata,),
           },
           "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid2 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid3 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuidl1 : {
            "calendar" : {
                "mismatched_attendee.ics"   : (MISMATCH_ATTENDEE_L1_ICS, CalVerifyMismatchTestsBase.metadata,),
            },
            "inbox" : {},
        },
    }

    @inlineCallbacks
    def test_scanMismatchOnly(self):
        """
        CalVerifyService.doScan without fix for mismatches. Make sure it detects
        as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": True,
            "nobase64": False,
            "fix": False,
            "verbose": False,
            "details": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
        }
        output = StringIO()
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 3)
        self.assertEqual(calverify.results["Missing Attendee"], set((
            ("MISSING_ATTENDEE_ICS", self.uuid1, self.uuidl1,),
        )))
        self.assertEqual(calverify.results["Mismatch Attendee"], set((
            ("MISMATCH_ATTENDEE_ICS", self.uuid1, self.uuidl1,),
        )))
        self.assertTrue("Missing Organizer" not in calverify.results)
        self.assertTrue("Mismatch Organizer" not in calverify.results)

        self.assertTrue("Fix change event" not in calverify.results)
        self.assertTrue("Fix add event" not in calverify.results)
        self.assertTrue("Fix add inbox" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)
        self.assertTrue("Fix failures" not in calverify.results)
        self.assertTrue("Auto-Accepts" not in calverify.results)

        sync_token_new1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertEqual(sync_token_oldl1, sync_token_newl1)


    @inlineCallbacks
    def test_fixMismatch(self):
        """
        CalVerifyService.doScan with fix for mismatches. Make sure it detects
        and fixes as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": True,
            "nobase64": False,
            "fix": True,
            "verbose": False,
            "details": False,
            "uid": "",
            "uuid": "",
            "tzid": "",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
        }
        output = StringIO()
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 3)
        self.assertEqual(calverify.results["Missing Attendee"], set((
            ("MISSING_ATTENDEE_ICS", self.uuid1, self.uuidl1,),
        )))
        self.assertEqual(calverify.results["Mismatch Attendee"], set((
            ("MISMATCH_ATTENDEE_ICS", self.uuid1, self.uuidl1,),
        )))
        self.assertTrue("Missing Organizer" not in calverify.results)
        self.assertTrue("Mismatch Organizer" not in calverify.results)

        self.assertEqual(calverify.results["Fix change event"], set((
            (self.uuidl1, "calendar", "MISMATCH_ATTENDEE_ICS",),
        )))

        self.assertEqual(calverify.results["Fix add event"], set((
            (self.uuidl1, "calendar", "MISSING_ATTENDEE_ICS",),
        )))

        self.assertEqual(calverify.results["Fix add inbox"], set((
            (self.uuidl1, "MISSING_ATTENDEE_ICS",),
            (self.uuidl1, "MISMATCH_ATTENDEE_ICS",),
        )))

        self.assertTrue("Fix remove" not in calverify.results)

        self.assertEqual(calverify.results["Fix failures"], 0)
        testResults = sorted(calverify.results["Auto-Accepts"], key=lambda x: x["uid"])
        self.assertEqual(testResults[0]["path"], "/calendars/__uids__/%s/calendar/mismatched_attendee.ics" % self.uuidl1)
        self.assertEqual(testResults[0]["uid"], "MISMATCH_ATTENDEE_ICS")
        self.assertEqual(testResults[0]["start"].getText()[:8], "%(year)s%(month)02d07" % {"year": nowYear, "month": nowMonth})
        self.assertEqual(testResults[1]["uid"], "MISSING_ATTENDEE_ICS")
        self.assertEqual(testResults[1]["start"].getText()[:8], "%(year)s%(month)02d07" % {"year": nowYear, "month": nowMonth})

        sync_token_new1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertNotEqual(sync_token_oldl1, sync_token_newl1)

        # Re-scan after changes to make sure there are no errors
        self.commit()
        options["fix"] = False
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 4)
        self.assertTrue("Missing Attendee" not in calverify.results)
        self.assertTrue("Mismatch Attendee" not in calverify.results)
        self.assertTrue("Missing Organizer" not in calverify.results)
        self.assertTrue("Mismatch Organizer" not in calverify.results)
        self.assertTrue("Fix add event" not in calverify.results)
        self.assertTrue("Fix add inbox" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)
        self.assertTrue("Fix failures" not in calverify.results)
        self.assertTrue("Auto-Accepts" not in calverify.results)



class CalVerifyMismatchTestsUUID(CalVerifyMismatchTestsBase):
    """
    Tests calverify for iCalendar mismatch problems for auto-accept attendees.
    """

    # Organizer has event, attendee do not
    MISSING_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISSING_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Attendee partstat mismatch
    MISMATCH_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    MISMATCH_ATTENDEE_L1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s%(month)02d07T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    requirements = {
        CalVerifyMismatchTestsBase.uuid1 : {
            "calendar" : {
                 "missing_attendee.ics"      : (MISSING_ATTENDEE_1_ICS, CalVerifyMismatchTestsBase.metadata,),
                 "mismatched_attendee.ics"   : (MISMATCH_ATTENDEE_1_ICS, CalVerifyMismatchTestsBase.metadata,),
           },
           "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid2 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid3 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuidl1 : {
            "calendar" : {
                "mismatched_attendee.ics"   : (MISMATCH_ATTENDEE_L1_ICS, CalVerifyMismatchTestsBase.metadata,),
            },
            "inbox" : {},
        },
    }

    @inlineCallbacks
    def test_scanMismatchOnly(self):
        """
        CalVerifyService.doScan without fix for mismatches. Make sure it detects
        as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": True,
            "nobase64": False,
            "fix": False,
            "verbose": False,
            "details": False,
            "uid": "",
            "uuid": CalVerifyMismatchTestsBase.uuidl1,
            "tzid": "",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
        }
        output = StringIO()
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 2)
        self.assertTrue("Missing Attendee" not in calverify.results)
        self.assertEqual(calverify.results["Mismatch Attendee"], set((
            ("MISMATCH_ATTENDEE_ICS", self.uuid1, self.uuidl1,),
        )))
        self.assertTrue("Missing Organizer" not in calverify.results)
        self.assertTrue("Mismatch Organizer" not in calverify.results)

        self.assertTrue("Fix change event" not in calverify.results)
        self.assertTrue("Fix add event" not in calverify.results)
        self.assertTrue("Fix add inbox" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)
        self.assertTrue("Fix failures" not in calverify.results)
        self.assertTrue("Auto-Accepts" not in calverify.results)

        sync_token_new1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertEqual(sync_token_oldl1, sync_token_newl1)


    @inlineCallbacks
    def test_fixMismatch(self):
        """
        CalVerifyService.doScan with fix for mismatches. Make sure it detects
        and fixes as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": True,
            "nobase64": False,
            "fix": True,
            "verbose": False,
            "details": False,
            "uid": "",
            "uuid": CalVerifyMismatchTestsBase.uuidl1,
            "tzid": "",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
        }
        output = StringIO()
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 2)
        self.assertTrue("Missing Attendee" not in calverify.results)
        self.assertEqual(calverify.results["Mismatch Attendee"], set((
            ("MISMATCH_ATTENDEE_ICS", self.uuid1, self.uuidl1,),
        )))
        self.assertTrue("Missing Organizer" not in calverify.results)
        self.assertTrue("Mismatch Organizer" not in calverify.results)

        self.assertEqual(calverify.results["Fix change event"], set((
            (self.uuidl1, "calendar", "MISMATCH_ATTENDEE_ICS",),
        )))

        self.assertTrue("Fix add event" not in calverify.results)

        self.assertEqual(calverify.results["Fix add inbox"], set((
            (self.uuidl1, "MISMATCH_ATTENDEE_ICS",),
        )))

        self.assertTrue("Fix remove" not in calverify.results)

        self.assertEqual(calverify.results["Fix failures"], 0)
        testResults = sorted(calverify.results["Auto-Accepts"], key=lambda x: x["uid"])
        self.assertEqual(testResults[0]["path"], "/calendars/__uids__/%s/calendar/mismatched_attendee.ics" % self.uuidl1)
        self.assertEqual(testResults[0]["uid"], "MISMATCH_ATTENDEE_ICS")
        self.assertEqual(testResults[0]["start"].getText()[:8], "%(year)s%(month)02d07" % {"year": nowYear, "month": nowMonth})

        sync_token_new1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertNotEqual(sync_token_oldl1, sync_token_newl1)

        # Re-scan after changes to make sure there are no errors
        self.commit()
        options["fix"] = False
        options["uuid"] = CalVerifyMismatchTestsBase.uuidl1
        calverify = SchedulingMismatchService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 2)
        self.assertTrue("Missing Attendee" not in calverify.results)
        self.assertTrue("Mismatch Attendee" not in calverify.results)
        self.assertTrue("Missing Organizer" not in calverify.results)
        self.assertTrue("Mismatch Organizer" not in calverify.results)
        self.assertTrue("Fix add event" not in calverify.results)
        self.assertTrue("Fix add inbox" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)
        self.assertTrue("Fix failures" not in calverify.results)
        self.assertTrue("Auto-Accepts" not in calverify.results)



class CalVerifyDoubleBooked(CalVerifyMismatchTestsBase):
    """
    Tests calverify for double-bookings.
    """

    # No overlap
    INVITE_NO_OVERLAP_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP_ICS
DTSTART:%(year)s%(month)02d07T100000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Two overlapping
    INVITE_NO_OVERLAP1_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP1_1_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP1_1_ICS
DTSTART:%(year)s%(month)02d07T110000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    INVITE_NO_OVERLAP1_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP1_2_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP1_2_ICS
DTSTART:%(year)s%(month)02d07T120000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Two overlapping with one transparent
    INVITE_NO_OVERLAP2_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP2_1_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP2_1_ICS
DTSTART:%(year)s%(month)02d07T140000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    INVITE_NO_OVERLAP2_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP2_2_ICS
SUMMARY:INVITE_NO_OVERLAP2_2_ICS
DTSTART:%(year)s%(month)02d07T150000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Two overlapping with one cancelled
    INVITE_NO_OVERLAP3_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP3_1_ICS
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s%(month)02d07T170000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    INVITE_NO_OVERLAP3_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP3_2_ICS
SUMMARY:INVITE_NO_OVERLAP3_2_ICS
DTSTART:%(year)s%(month)02d07T180000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Two overlapping recurring
    INVITE_NO_OVERLAP4_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP4_1_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP4_1_ICS
DTSTART:%(year)s%(month)02d08T120000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    INVITE_NO_OVERLAP4_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP4_2_ICS
SUMMARY:INVITE_NO_OVERLAP4_2_ICS
DTSTART:%(year)s%(month)02d09T120000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Two overlapping on one recurrence instance
    INVITE_NO_OVERLAP5_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP5_1_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP5_1_ICS
DTSTART:%(year)s%(month)02d12T120000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    INVITE_NO_OVERLAP5_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP5_2_ICS
SUMMARY:INVITE_NO_OVERLAP5_2_ICS
DTSTART:%(year)s%(month)02d13T140000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP5_2_ICS
SUMMARY:INVITE_NO_OVERLAP5_2_ICS
RECURRENCE-ID:%(year)s%(month)02d14T140000Z
DTSTART:%(year)s%(month)02d14T130000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Two not overlapping - one all-day
    INVITE_NO_OVERLAP6_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP6_1_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP6_1_ICS
DTSTART;TZID=America/Los_Angeles:%(year)s%(month)02d20T200000
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    INVITE_NO_OVERLAP6_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP6_2_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP6_2_ICS
DTSTART;VALUE=DATE:%(year)s%(month)02d21
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Two overlapping - same organizer and summary
    INVITE_NO_OVERLAP7_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP7_1_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP7_1_ICS
DTSTART:%(year)s%(month)02d23T110000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    INVITE_NO_OVERLAP7_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP7_2_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP7_1_ICS
DTSTART:%(year)s%(month)02d23T120000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    allEvents = {
        "invite1.ics"      : (INVITE_NO_OVERLAP_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite2.ics"      : (INVITE_NO_OVERLAP1_1_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite3.ics"      : (INVITE_NO_OVERLAP1_2_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite4.ics"      : (INVITE_NO_OVERLAP2_1_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite5.ics"      : (INVITE_NO_OVERLAP2_2_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite6.ics"      : (INVITE_NO_OVERLAP3_1_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite7.ics"      : (INVITE_NO_OVERLAP3_2_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite8.ics"      : (INVITE_NO_OVERLAP4_1_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite9.ics"      : (INVITE_NO_OVERLAP4_2_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite10.ics"     : (INVITE_NO_OVERLAP5_1_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite11.ics"     : (INVITE_NO_OVERLAP5_2_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite12.ics"     : (INVITE_NO_OVERLAP6_1_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite13.ics"     : (INVITE_NO_OVERLAP6_2_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite14.ics"     : (INVITE_NO_OVERLAP7_1_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite15.ics"     : (INVITE_NO_OVERLAP7_2_ICS, CalVerifyMismatchTestsBase.metadata,),
    }

    requirements = {
        CalVerifyMismatchTestsBase.uuid1 : {
            "calendar" : allEvents,
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid2 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid3 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuidl1 : {
            "calendar" : allEvents,
            "inbox" : {},
        },
    }

    @inlineCallbacks
    def test_scanDoubleBookingOnly(self):
        """
        CalVerifyService.doScan without fix for mismatches. Make sure it detects
        as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": False,
            "nobase64": False,
            "double": True,
            "fix": False,
            "verbose": False,
            "details": False,
            "summary": False,
            "days": 365,
            "uid": "",
            "uuid": self.uuidl1,
            "tzid": "utc",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
        }
        output = StringIO()
        calverify = DoubleBookingService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], len(self.requirements[CalVerifyMismatchTestsBase.uuidl1]["calendar"]))
        self.assertEqual(
            [(sorted((i.uid1, i.uid2,)), str(i.start),) for i in calverify.results["Double-bookings"]],
            [
                (["INVITE_NO_OVERLAP1_1_ICS", "INVITE_NO_OVERLAP1_2_ICS"], "%(year)s%(month)02d07T120000Z" % {"year": nowYear, "month": nowMonth}),
                (["INVITE_NO_OVERLAP4_1_ICS", "INVITE_NO_OVERLAP4_2_ICS"], "%(year)s%(month)02d09T120000Z" % {"year": nowYear, "month": nowMonth}),
                (["INVITE_NO_OVERLAP4_1_ICS", "INVITE_NO_OVERLAP4_2_ICS"], "%(year)s%(month)02d10T120000Z" % {"year": nowYear, "month": nowMonth}),
                (["INVITE_NO_OVERLAP5_1_ICS", "INVITE_NO_OVERLAP5_2_ICS"], "%(year)s%(month)02d14T130000Z" % {"year": nowYear, "month": nowMonth}),
            ],
        )
        self.assertEqual(calverify.results["Number of double-bookings"], 4)
        self.assertEqual(calverify.results["Number of unique double-bookings"], 3)

        sync_token_new1 = (yield (yield self.calendarUnderTest(home=self.uuid1, name="calendar")).syncToken())
        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertEqual(sync_token_oldl1, sync_token_newl1)



class CalVerifyDarkPurge(CalVerifyMismatchTestsBase):
    """
    Tests calverify for events.
    """

    # No organizer
    INVITE_NO_ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_ORGANIZER_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_ORGANIZER_ICS
DTSTART:%(year)s%(month)02d07T100000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Valid organizer
    INVITE_VALID_ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_VALID_ORGANIZER_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_VALID_ORGANIZER_ICS
DTSTART:%(year)s%(month)02d08T100000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Invalid organizer #1
    INVITE_INVALID_ORGANIZER_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_INVALID_ORGANIZER_1_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_INVALID_ORGANIZER_1_ICS
DTSTART:%(year)s%(month)02d09T100000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0-1
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0-1
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    # Invalid organizer #2
    INVITE_INVALID_ORGANIZER_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_INVALID_ORGANIZER_2_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_INVALID_ORGANIZER_2_ICS
DTSTART:%(year)s%(month)02d10T100000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:mailto:foobar@example.com
ATTENDEE:mailto:foobar@example.com
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": nowYear, "month": nowMonth}

    allEvents = {
        "invite1.ics"      : (INVITE_NO_ORGANIZER_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite2.ics"      : (INVITE_VALID_ORGANIZER_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite3.ics"      : (INVITE_INVALID_ORGANIZER_1_ICS, CalVerifyMismatchTestsBase.metadata,),
        "invite4.ics"      : (INVITE_INVALID_ORGANIZER_2_ICS, CalVerifyMismatchTestsBase.metadata,),
    }

    requirements = {
        CalVerifyMismatchTestsBase.uuid1 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid2 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuid3 : {
            "calendar" : {},
            "inbox" : {},
        },
        CalVerifyMismatchTestsBase.uuidl1 : {
            "calendar" : allEvents,
            "inbox" : {},
        },
    }

    @inlineCallbacks
    def test_scanDarkEvents(self):
        """
        CalVerifyService.doScan without fix for dark events. Make sure it detects
        as much as it can. Make sure sync-token is not changed.
        """

        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": False,
            "nobase64": False,
            "double": True,
            "dark-purge": False,
            "fix": False,
            "verbose": False,
            "details": False,
            "summary": False,
            "days": 365,
            "uid": "",
            "uuid": self.uuidl1,
            "tzid": "utc",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
            "no-organizer": False,
            "invalid-organizer": False,
            "disabled-organizer": False,
        }
        output = StringIO()
        calverify = DarkPurgeService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], len(self.requirements[CalVerifyMismatchTestsBase.uuidl1]["calendar"]))
        self.assertEqual(
            sorted([i.uid for i in calverify.results["Dark Events"]]),
            ["INVITE_INVALID_ORGANIZER_1_ICS", "INVITE_INVALID_ORGANIZER_2_ICS", ]
        )
        self.assertEqual(calverify.results["Number of dark events"], 2)
        self.assertTrue("Fix dark events" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)

        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertEqual(sync_token_oldl1, sync_token_newl1)


    @inlineCallbacks
    def test_fixDarkEvents(self):
        """
        CalVerifyService.doScan with fix for dark events. Make sure it detects
        as much as it can. Make sure sync-token is changed.
        """

        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": False,
            "nobase64": False,
            "double": True,
            "dark-purge": False,
            "fix": True,
            "verbose": False,
            "details": False,
            "summary": False,
            "days": 365,
            "uid": "",
            "uuid": self.uuidl1,
            "tzid": "utc",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
            "no-organizer": False,
            "invalid-organizer": False,
            "disabled-organizer": False,
        }
        output = StringIO()
        calverify = DarkPurgeService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], len(self.requirements[CalVerifyMismatchTestsBase.uuidl1]["calendar"]))
        self.assertEqual(
            sorted([i.uid for i in calverify.results["Dark Events"]]),
            ["INVITE_INVALID_ORGANIZER_1_ICS", "INVITE_INVALID_ORGANIZER_2_ICS", ]
        )
        self.assertEqual(calverify.results["Number of dark events"], 2)
        self.assertEqual(calverify.results["Fix dark events"], 2)
        self.assertTrue("Fix remove" in calverify.results)

        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertNotEqual(sync_token_oldl1, sync_token_newl1)

        # Re-scan after changes to make sure there are no errors
        self.commit()
        options["fix"] = False
        options["uuid"] = self.uuidl1
        calverify = DarkPurgeService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 2)
        self.assertEqual(len(calverify.results["Dark Events"]), 0)
        self.assertTrue("Fix dark events" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)


    @inlineCallbacks
    def test_fixDarkEventsNoOrganizerOnly(self):
        """
        CalVerifyService.doScan with fix for dark events. Make sure it detects
        as much as it can. Make sure sync-token is changed.
        """

        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": False,
            "nobase64": False,
            "double": True,
            "dark-purge": False,
            "fix": True,
            "verbose": False,
            "details": False,
            "summary": False,
            "days": 365,
            "uid": "",
            "uuid": self.uuidl1,
            "tzid": "utc",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
            "no-organizer": True,
            "invalid-organizer": False,
            "disabled-organizer": False,
        }
        output = StringIO()
        calverify = DarkPurgeService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], len(self.requirements[CalVerifyMismatchTestsBase.uuidl1]["calendar"]))
        self.assertEqual(
            sorted([i.uid for i in calverify.results["Dark Events"]]),
            ["INVITE_NO_ORGANIZER_ICS", ]
        )
        self.assertEqual(calverify.results["Number of dark events"], 1)
        self.assertEqual(calverify.results["Fix dark events"], 1)
        self.assertTrue("Fix remove" in calverify.results)

        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertNotEqual(sync_token_oldl1, sync_token_newl1)

        # Re-scan after changes to make sure there are no errors
        self.commit()
        options["fix"] = False
        options["uuid"] = self.uuidl1
        calverify = DarkPurgeService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 3)
        self.assertEqual(len(calverify.results["Dark Events"]), 0)
        self.assertTrue("Fix dark events" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)


    @inlineCallbacks
    def test_fixDarkEventsAllTypes(self):
        """
        CalVerifyService.doScan with fix for dark events. Make sure it detects
        as much as it can. Make sure sync-token is changed.
        """

        sync_token_oldl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.commit()

        options = {
            "ical": False,
            "badcua": False,
            "mismatch": False,
            "nobase64": False,
            "double": True,
            "dark-purge": False,
            "fix": True,
            "verbose": False,
            "details": False,
            "summary": False,
            "days": 365,
            "uid": "",
            "uuid": self.uuidl1,
            "tzid": "utc",
            "start": PyCalendarDateTime(nowYear, 1, 1, 0, 0, 0),
            "no-organizer": True,
            "invalid-organizer": True,
            "disabled-organizer": True,
        }
        output = StringIO()
        calverify = DarkPurgeService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], len(self.requirements[CalVerifyMismatchTestsBase.uuidl1]["calendar"]))
        self.assertEqual(
            sorted([i.uid for i in calverify.results["Dark Events"]]),
            ["INVITE_INVALID_ORGANIZER_1_ICS", "INVITE_INVALID_ORGANIZER_2_ICS", "INVITE_NO_ORGANIZER_ICS", ]
        )
        self.assertEqual(calverify.results["Number of dark events"], 3)
        self.assertEqual(calverify.results["Fix dark events"], 3)
        self.assertTrue("Fix remove" in calverify.results)

        sync_token_newl1 = (yield (yield self.calendarUnderTest(home=self.uuidl1, name="calendar")).syncToken())
        self.assertNotEqual(sync_token_oldl1, sync_token_newl1)

        # Re-scan after changes to make sure there are no errors
        self.commit()
        options["fix"] = False
        options["uuid"] = self.uuidl1
        calverify = DarkPurgeService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 1)
        self.assertEqual(len(calverify.results["Dark Events"]), 0)
        self.assertTrue("Fix dark events" not in calverify.results)
        self.assertTrue("Fix remove" not in calverify.results)
