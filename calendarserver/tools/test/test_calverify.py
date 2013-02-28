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

from StringIO import StringIO
from calendarserver.tap.util import getRootResource
from calendarserver.tools.calverify import BadDataService, \
    SchedulingMismatchService, DoubleBookingService
from pycalendar.datetime import PyCalendarDateTime
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial import unittest
from twistedcaldav import caldavxml
from twistedcaldav.config import config
from txdav.base.propertystore.base import PropertyName
from txdav.caldav.datastore import util
from txdav.common.datastore.test.util import buildStore, populateCalendarsFrom, CommonCommonTests
from txdav.xml import element as davxml
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



class CalVerifyDataTests(CommonCommonTests, unittest.TestCase):
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
            "calendar1" : {
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
            }
        },
    }

    @inlineCallbacks
    def setUp(self):
        yield super(CalVerifyDataTests, self).setUp()
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


    @inlineCallbacks
    def homeUnderTest(self, txn=None):
        """
        Get the calendar home detailed by C{requirements['home1']}.
        """
        if txn is None:
            txn = self.transactionUnderTest()
        returnValue((yield txn.calendarHomeWithUID("home1")))


    @inlineCallbacks
    def calendarUnderTest(self, txn=None):
        """
        Get the calendar detailed by C{requirements['home1']['calendar1']}.
        """
        returnValue((yield
            (yield self.homeUnderTest(txn)).calendarWithName("calendar1"))
        )


    @inlineCallbacks
    def calendarObjectUnderTest(self, name, txn=None):
        """
        Get the calendar object detailed by C{requirements[home_name][calendar_name][name]}.
        """
        returnValue((yield
            (yield self.calendarUnderTest(txn)).calendarObjectWithName(name))
        )


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

        self.assertEqual(calverify.results["Number of events to process"], 13)
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

        self.assertEqual(calverify.results["Number of events to process"], 13)
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
        )))

        # Do scan
        options["fix"] = False
        calverify = BadDataService(self._sqlCalendarStore, options, output, reactor, config)
        calverify.emailDomain = "example.com"
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], 13)
        self.verifyResultsByUID(calverify.results["Bad iCalendar data"], set((
            ("home1", "BAD1",),
        )))

        sync_token_new = (yield (yield self.calendarUnderTest()).syncToken())
        self.assertNotEqual(sync_token_old, sync_token_new)

        # Make sure mailto: fix results in urn:uuid value without SCHEDULE-AGENT
        obj = yield self.calendarObjectUnderTest("bad10.ics")
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

        self.assertEqual(calverify.results["Number of events to process"], 13)
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

        self.assertEqual(calverify.results["Number of events to process"], 13)
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

        self.assertEqual(calverify.results["Number of events to process"], 13)
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



class CalVerifyMismatchTestsBase(CommonCommonTests, unittest.TestCase):
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

    @inlineCallbacks
    def setUp(self):
        yield super(CalVerifyMismatchTestsBase, self).setUp()
        self._sqlCalendarStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()

        inbox = (yield self.calendarUnderTest(self.uuid3, "inbox"))
        inbox.properties()[PropertyName.fromElement(caldavxml.ScheduleDefaultCalendarURL)] = caldavxml.ScheduleDefaultCalendarURL(
            davxml.HRef.fromString("/calendars/__uids__/%s/calendar2/" % (self.uuid3,))
        )
        yield self.commit()

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


    @inlineCallbacks
    def homeUnderTest(self, name=None, txn=None):
        """
        Get the calendar home detailed by C{requirements[name]}.
        """
        if txn is None:
            txn = self.transactionUnderTest()
        returnValue((yield txn.calendarHomeWithUID(name)))


    @inlineCallbacks
    def calendarUnderTest(self, home_name, name="calendar", txn=None):
        """
        Get the calendar detailed by C{requirements[home_name][name]}.
        """
        returnValue((yield
            (yield self.homeUnderTest(home_name, txn)).calendarWithName(name))
        )


    @inlineCallbacks
    def calendarObjectUnderTest(self, home_name, calendar_name, name, txn=None):
        """
        Get the calendar object detailed by C{requirements[home_name][calendar_name][name]}.
        """
        returnValue((yield
            (yield self.calendarUnderTest(home_name, calendar_name, txn)).calendarObjectWithName(name))
        )

now = PyCalendarDateTime.getToday().getYear()

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
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    # Attendees have event, organizer does not
    MISSING_ORGANIZER_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISSING_ORGANIZER_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISSING_ORGANIZER_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISSING_ORGANIZER_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    # Attendee partstat mismatch
    MISMATCH_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH_ATTENDEE_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH_ATTENDEE_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    # Attendee events outside time range
    MISMATCH2_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH2_ATTENDEE_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH2_ATTENDEE_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    # Organizer event outside time range
    MISMATCH_ORGANIZER_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ORGANIZER_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now - 2}

    MISMATCH_ORGANIZER_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ORGANIZER_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    # Attendee uuid3 has event with different organizer
    MISMATCH3_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH3_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH3_ATTENDEE_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH3_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH3_ATTENDEE_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH3_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH_ORGANIZER_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ORGANIZER_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    # Attendee uuid3 has event they are not invited to
    MISMATCH2_ORGANIZER_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ORGANIZER_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH2_ORGANIZER_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ORGANIZER_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH2_ORGANIZER_3_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH2_ORGANIZER_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=DECLINED:urn:uuid:47B16BB4-DB5F-4BF6-85FE-A7DA54230F92
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:AC478592-7783-44D1-B2AE-52359B4E8415
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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
    def test_scanMismatchOnly(self):
        """
        CalVerifyService.doScan without fix for mismatches. Make sure it detects
        as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_old2 = (yield (yield self.calendarUnderTest(self.uuid2)).syncToken())
        sync_token_old3 = (yield (yield self.calendarUnderTest(self.uuid3)).syncToken())
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
            "start": PyCalendarDateTime(now, 1, 1, 0, 0, 0),
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

        sync_token_new1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_new2 = (yield (yield self.calendarUnderTest(self.uuid2)).syncToken())
        sync_token_new3 = (yield (yield self.calendarUnderTest(self.uuid3)).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertEqual(sync_token_old2, sync_token_new2)
        self.assertEqual(sync_token_old3, sync_token_new3)


    @inlineCallbacks
    def test_fixMismatch(self):
        """
        CalVerifyService.doScan with fix for mismatches. Make sure it detects
        and fixes as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_old2 = (yield (yield self.calendarUnderTest(self.uuid2)).syncToken())
        sync_token_old3 = (yield (yield self.calendarUnderTest(self.uuid3)).syncToken())
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
            "start": PyCalendarDateTime(now, 1, 1, 0, 0, 0),
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
        obj = yield self.calendarObjectUnderTest(self.uuid2, "calendar", "missing_organizer.ics")
        self.assertEqual(obj, None)
        obj = yield self.calendarObjectUnderTest(self.uuid3, "calendar", "missing_organizer.ics")
        self.assertEqual(obj, None)
        obj = yield self.calendarObjectUnderTest(self.uuid3, "calendar", "mismatched2_organizer.ics")
        self.assertEqual(obj, None)

        self.assertEqual(calverify.results["Fix failures"], 0)
        self.assertEqual(calverify.results["Auto-Accepts"], [])

        sync_token_new1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_new2 = (yield (yield self.calendarUnderTest(self.uuid2)).syncToken())
        sync_token_new3 = (yield (yield self.calendarUnderTest(self.uuid3)).syncToken())
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
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    # Attendee partstat mismatch
    MISMATCH_ATTENDEE_1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=NEEDS-ACTION:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    MISMATCH_ATTENDEE_L1_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:MISMATCH_ATTENDEE_ICS
DTEND:%(year)s0307T151500Z
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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

        sync_token_old1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_oldl1 = (yield (yield self.calendarUnderTest(self.uuidl1)).syncToken())
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
            "start": PyCalendarDateTime(now, 1, 1, 0, 0, 0),
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

        sync_token_new1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_newl1 = (yield (yield self.calendarUnderTest(self.uuidl1)).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertEqual(sync_token_oldl1, sync_token_newl1)


    @inlineCallbacks
    def test_fixMismatch(self):
        """
        CalVerifyService.doScan with fix for mismatches. Make sure it detects
        and fixes as much as it can. Make sure sync-token is not changed.
        """

        sync_token_old1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_oldl1 = (yield (yield self.calendarUnderTest(self.uuidl1)).syncToken())
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
            "start": PyCalendarDateTime(now, 1, 1, 0, 0, 0),
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
        self.assertEqual(testResults[0]["start"].getText(), "%s0307T031500" % (now,))
        self.assertEqual(testResults[1]["uid"], "MISSING_ATTENDEE_ICS")
        self.assertEqual(testResults[1]["start"].getText(), "%s0307T031500" % (now,))

        sync_token_new1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_newl1 = (yield (yield self.calendarUnderTest(self.uuidl1)).syncToken())
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
DTSTART:%(year)s0307T100000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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
DTSTART:%(year)s0307T110000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    INVITE_NO_OVERLAP1_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP1_2_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP1_2_ICS
DTSTART:%(year)s0307T120000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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
DTSTART:%(year)s0307T140000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    INVITE_NO_OVERLAP2_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP2_2_ICS
SUMMARY:INVITE_NO_OVERLAP2_2_ICS
DTSTART:%(year)s0307T150000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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
DTSTART:%(year)s0307T170000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    INVITE_NO_OVERLAP3_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP3_2_ICS
SUMMARY:INVITE_NO_OVERLAP3_2_ICS
DTSTART:%(year)s0307T180000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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
DTSTART:%(year)s0308T120000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    INVITE_NO_OVERLAP4_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP4_2_ICS
SUMMARY:INVITE_NO_OVERLAP4_2_ICS
DTSTART:%(year)s0309T120000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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
DTSTART:%(year)s0312T120000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
RRULE:FREQ=DAILY;COUNT=3
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    INVITE_NO_OVERLAP5_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP5_2_ICS
SUMMARY:INVITE_NO_OVERLAP5_2_ICS
DTSTART:%(year)s0313T140000Z
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
RECURRENCE-ID:%(year)s0314T140000Z
DTSTART:%(year)s0314T130000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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
DTSTART;TZID=America/Los_Angeles:%(year)s0320T200000
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    INVITE_NO_OVERLAP6_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP6_2_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP6_2_ICS
DTSTART;VALUE=DATE:%(year)s0321
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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
DTSTART:%(year)s0323T110000Z
DURATION:PT2H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

    INVITE_NO_OVERLAP7_2_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:INVITE_NO_OVERLAP7_2_ICS
TRANSP:OPAQUE
SUMMARY:INVITE_NO_OVERLAP7_1_ICS
DTSTART:%(year)s0323T120000Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
SEQUENCE:2
ORGANIZER:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:D46F3D71-04B7-43C2-A7B6-6F92F92E61D0
ATTENDEE:urn:uuid:75EA36BE-F71B-40F9-81F9-CF59BF40CA8F
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now}

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

        sync_token_old1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_oldl1 = (yield (yield self.calendarUnderTest(self.uuidl1)).syncToken())
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
            "start": PyCalendarDateTime(now, 1, 1, 0, 0, 0),
        }
        output = StringIO()
        calverify = DoubleBookingService(self._sqlCalendarStore, options, output, reactor, config)
        yield calverify.doAction()

        self.assertEqual(calverify.results["Number of events to process"], len(self.requirements[CalVerifyMismatchTestsBase.uuidl1]["calendar"]))
        self.assertEqual(
            [(sorted((i.uid1, i.uid2,)), str(i.start),) for i in calverify.results["Double-bookings"]],
            [
                (["INVITE_NO_OVERLAP1_1_ICS", "INVITE_NO_OVERLAP1_2_ICS"], "%(year)s0307T120000Z" % {"year": now}),
                (["INVITE_NO_OVERLAP4_1_ICS", "INVITE_NO_OVERLAP4_2_ICS"], "%(year)s0309T120000Z" % {"year": now}),
                (["INVITE_NO_OVERLAP4_1_ICS", "INVITE_NO_OVERLAP4_2_ICS"], "%(year)s0310T120000Z" % {"year": now}),
                (["INVITE_NO_OVERLAP5_1_ICS", "INVITE_NO_OVERLAP5_2_ICS"], "%(year)s0314T130000Z" % {"year": now}),
            ],
        )
        self.assertEqual(calverify.results["Number of double-bookings"], 4)
        self.assertEqual(calverify.results["Number of unique double-bookings"], 3)

        sync_token_new1 = (yield (yield self.calendarUnderTest(self.uuid1)).syncToken())
        sync_token_newl1 = (yield (yield self.calendarUnderTest(self.uuidl1)).syncToken())
        self.assertEqual(sync_token_old1, sync_token_new1)
        self.assertEqual(sync_token_oldl1, sync_token_newl1)


    def test_instance(self):
        """
        CalVerifyService.doScan without fix for mismatches. Make sure it detects
        as much as it can. Make sure sync-token is not changed.
        """

        s = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
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
UID:4760FF93-C7F8-4EB0-B3E8-0B22A96DB1BC
DTSTART;TZID=America/Los_Angeles:20130221T170000
DTEND;TZID=America/Los_Angeles:20130221T180000
ATTENDEE;CN=Casa Blanca APPLE EMP ONLY (12) DA03 4th;CUTYPE=ROOM;PARTSTAT=
 ACCEPTED;ROLE=REQ-PARTICIPANT:urn:uuid:366CC7BE-FEF7-4FFF-B713-6B883538A24
 9
ATTENDEE;CN=Mark Chu;CUTYPE=INDIVIDUAL;EMAIL=markchu@apple.com;PARTSTAT=AC
 CEPTED;ROLE=REQ-PARTICIPANT:urn:uuid:46F9D5D9-08E8-4987-9636-CC796F4093C6
ATTENDEE;CN=Kristie Phan;CUTYPE=INDIVIDUAL;EMAIL=kristie_phan@apple.com;PA
 RTSTAT=ACCEPTED:urn:uuid:97E8720F-4364-DBEC-6721-123E9A92B980
CREATED:20130220T200530Z
DTSTAMP:20130222T002246Z
EXDATE:20130228T010000Z
EXDATE:20130314T000000Z
EXDATE:20130321T000000Z
EXDATE:20130327T000000Z
EXDATE:20130328T000000Z
EXDATE:20130403T000000Z
LOCATION:Casa Blanca APPLE EMP ONLY (12) DA03 4th
ORGANIZER;CN=Kristie Phan;EMAIL=kristie_phan@apple.com;SCHEDULE-STATUS=1.2
 :urn:uuid:97E8720F-4364-DBEC-6721-123E9A92B980
RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;WKST=SU
SEQUENCE:13
SUMMARY:ESD Daily Meeting
END:VEVENT
END:VCALENDAR
"""
        from twistedcaldav.ical import Component
        c = Component.fromString(s)
        start = PyCalendarDateTime.getToday()
        start.setDateOnly(False)
        end = start.duplicate()
        end.offsetDay(30)
        config.MaxAllowedInstances = 3000
        i = c.expandTimeRanges(end, start, ignoreInvalidInstances=True)
        print(i)
