##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
Tests for calendarserver.tools.purge
"""

from twisted.trial import unittest
from twisted.internet.defer import inlineCallbacks

from txdav.common.datastore.test.util import buildStore, populateCalendarsFrom, CommonCommonTests

from calendarserver.tap.util import getRootResource
from calendarserver.tools.purge import purgeOldEvents, purgeGUID
from twistedcaldav.config import config
from vobject.icalendar import utc

import datetime
import os



OLD_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYMONTH=10;BYDAY=-1SU
DTSTART:19621028T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYMONTH=4;BYDAY=1SU
DTSTART:19870405T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:685BC3A1-195A-49B3-926D-388DDACA78A6
DTEND;TZID=US/Pacific:20000307T151500
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART;TZID=US/Pacific:20000307T111500
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

ENDLESS_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYMONTH=10;BYDAY=-1SU
DTSTART:19621028T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYMONTH=4;BYDAY=1SU
DTSTART:19870405T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T194654Z
UID:9FDE0E4C-1495-4CAF-863B-F7F0FB15FE8C
DTEND;TZID=US/Pacific:20000308T151500
RRULE:FREQ=YEARLY;INTERVAL=1
TRANSP:OPAQUE
SUMMARY:Ancient Repeating Endless
DTSTART;TZID=US/Pacific:20000308T111500
DTSTAMP:20100303T194710Z
SEQUENCE:4
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

REPEATING_AWHILE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYMONTH=10;BYDAY=-1SU
DTSTART:19621028T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYMONTH=4;BYDAY=1SU
DTSTART:19870405T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T194716Z
UID:76236B32-2BC4-4D78-956B-8D42D4086200
DTEND;TZID=US/Pacific:20000309T151500
RRULE:FREQ=YEARLY;INTERVAL=1;COUNT=3
TRANSP:OPAQUE
SUMMARY:Ancient Repeat Awhile
DTSTART;TZID=US/Pacific:20000309T111500
DTSTAMP:20100303T194747Z
SEQUENCE:6
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

STRADDLING_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T213643Z
UID:1C219DAD-D374-4822-8C98-ADBA85E253AB
DTEND;TZID=US/Pacific:20090508T121500
RRULE:FREQ=MONTHLY;INTERVAL=1;UNTIL=20100509T065959Z
TRANSP:OPAQUE
SUMMARY:Straddling cut-off
DTSTART;TZID=US/Pacific:20090508T111500
DTSTAMP:20100303T213704Z
SEQUENCE:5
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

RECENT_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T195159Z
UID:F2F14D94-B944-43D9-8F6F-97F95B2764CA
DTEND;TZID=US/Pacific:20100304T141500
TRANSP:OPAQUE
SUMMARY:Recent
DTSTART;TZID=US/Pacific:20100304T120000
DTSTAMP:20100303T195203Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")



class PurgeOldEventsTests(CommonCommonTests, unittest.TestCase):
    """
    Tests for deleting events older than a given date
    """

    requirements = {
        "home1" : {
            "calendar1" : {
                "old.ics" : OLD_ICS,
                "endless.ics" : ENDLESS_ICS,
            }
        },
        "home2" : {
            "calendar2" : {
                "straddling.ics" : STRADDLING_ICS,
                "recent.ics" : RECENT_ICS,
            },
            "calendar3" : {
                "repeating_awhile.ics" : REPEATING_AWHILE_ICS,
            }
        }
    }

    @inlineCallbacks
    def setUp(self):
        yield super(PurgeOldEventsTests, self).setUp()
        self._sqlCalendarStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()


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
    def test_eventsOlderThan(self):
        cutoff = datetime.datetime(2010, 4, 1)
        txn = self._sqlCalendarStore.newTransaction()

        # Query for all old events
        results = (yield txn.eventsOlderThan(cutoff))
        self.assertEquals(results,
            [
                ['home1', 'calendar1', 'old.ics', '2000-03-07 23:15:00'],
                ['home2', 'calendar3', 'repeating_awhile.ics', '2002-03-09 23:15:00'],
                ['home2', 'calendar2', 'recent.ics', '2010-03-04 22:15:00'],
            ]
        )

        # Query for oldest event
        results = (yield txn.eventsOlderThan(cutoff, batchSize=1))
        self.assertEquals(results,
            [
                ['home1', 'calendar1', 'old.ics', '2000-03-07 23:15:00'],
            ]
        )

    @inlineCallbacks
    def test_removeOldEvents(self):
        cutoff = datetime.datetime(2010, 4, 1)
        txn = self._sqlCalendarStore.newTransaction()

        # Remove oldest event
        count = (yield txn.removeOldEvents(cutoff, batchSize=1))
        self.assertEquals(count, 1)
        results = (yield txn.eventsOlderThan(cutoff))
        self.assertEquals(results,
            [
                ['home2', 'calendar3', 'repeating_awhile.ics', '2002-03-09 23:15:00'],
                ['home2', 'calendar2', 'recent.ics', '2010-03-04 22:15:00'],
            ]
        )

        # Remove remaining oldest events
        count = (yield txn.removeOldEvents(cutoff))
        self.assertEquals(count, 2)
        results = (yield txn.eventsOlderThan(cutoff))
        self.assertEquals(results, [ ])

        # Remove oldest events (none left)
        count = (yield txn.removeOldEvents(cutoff))
        self.assertEquals(count, 0)

    @inlineCallbacks
    def test_purgeOldEvents(self):
        self.patch(config.DirectoryService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "purge", "accounts.xml"
            )
        )
        self.patch(config.ResourceService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "purge", "resources.xml"
            )
        )
        self.patch(config.Memcached.Pools.Default, "ClientEnabled", False)
        rootResource = getRootResource(config, self._sqlCalendarStore)
        directory = rootResource.getDirectory()

        # Dry run
        total = (yield purgeOldEvents(self._sqlCalendarStore, directory,
            rootResource, datetime.datetime(2010, 4, 1), 2, dryrun=True,
            verbose=False))
        self.assertEquals(total, 3)

        # Actually remove
        total = (yield purgeOldEvents(self._sqlCalendarStore, directory,
            rootResource, datetime.datetime(2010, 4, 1), 2, verbose=False))
        self.assertEquals(total, 3)

        # There should be no more left
        total = (yield purgeOldEvents(self._sqlCalendarStore, directory,
            rootResource, datetime.datetime(2010, 4, 1), 2, verbose=False))
        self.assertEquals(total, 0)

    @inlineCallbacks
    def test_purgeGUID(self):
        self.patch(config.DirectoryService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "purge", "accounts.xml"
            )
        )
        self.patch(config.ResourceService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "purge", "resources.xml"
            )
        )
        self.patch(config.Memcached.Pools.Default, "ClientEnabled", False)
        rootResource = getRootResource(config, self._sqlCalendarStore)
        directory = rootResource.getDirectory()
        total, ignored = (yield purgeGUID("home2", directory, rootResource,
            verbose=False, proxies=False,
            when=datetime.datetime(2010, 4, 1, 12, 0, 0, 0, utc)))
        self.assertEquals(total, 1)
