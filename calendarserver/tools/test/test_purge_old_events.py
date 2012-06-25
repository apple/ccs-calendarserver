##
# Copyright (c) 2011-2012 Apple Inc. All rights reserved.
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
from calendarserver.tap.util import getRootResource
from calendarserver.tools.purge import purgeOldEvents, purgeUID, purgeOrphanedAttachments

from twext.web2.http_headers import MimeType

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial import unittest

from twistedcaldav.config import config
from twistedcaldav.vcard import Component as VCardComponent

from txdav.common.datastore.test.util import buildStore, populateCalendarsFrom, CommonCommonTests

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone

import os


now = PyCalendarDateTime.getToday().getYear()

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
DTEND;TZID=US/Pacific:%(year)s0307T151500
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART;TZID=US/Pacific:%(year)s0307T111500
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year":now-5}

OLD_ATTACHMENT_ICS = """BEGIN:VCALENDAR
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
UID:57A5D1F6-9A57-4F74-9520-25C617F54B88
TRANSP:OPAQUE
SUMMARY:Ancient event with attachment
DTSTART;TZID=US/Pacific:%(year)s0308T111500
DTEND;TZID=US/Pacific:%(year)s0308T151500
DTSTAMP:20100303T181220Z
X-APPLE-DROPBOX:/calendars/__uids__/user01/dropbox/57A5D1F6-9A57-4F74-95
 20-25C617F54B88.dropbox
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year":now-5}

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
DTEND;TZID=US/Pacific:%(year)s0308T151500
RRULE:FREQ=YEARLY;INTERVAL=1
TRANSP:OPAQUE
SUMMARY:Ancient Repeating Endless
DTSTART;TZID=US/Pacific:%(year)s0308T111500
DTSTAMP:20100303T194710Z
SEQUENCE:4
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year":now-5}

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
DTEND;TZID=US/Pacific:%(year)s0309T151500
RRULE:FREQ=YEARLY;INTERVAL=1;COUNT=3
TRANSP:OPAQUE
SUMMARY:Ancient Repeat Awhile
DTSTART;TZID=US/Pacific:%(year)s0309T111500
DTSTAMP:20100303T194747Z
SEQUENCE:6
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year":now-5}

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
DTEND;TZID=US/Pacific:%(year)s0508T121500
RRULE:FREQ=MONTHLY;INTERVAL=1;UNTIL=%(until)s0509T065959Z
TRANSP:OPAQUE
SUMMARY:Straddling cut-off
DTSTART;TZID=US/Pacific:%(year)s0508T111500
DTSTAMP:20100303T213704Z
SEQUENCE:5
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year":now-2, "until":now+1}

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
DTEND;TZID=US/Pacific:%(year)s0304T141500
TRANSP:OPAQUE
SUMMARY:Recent
DTSTART;TZID=US/Pacific:%(year)s0304T120000
DTSTAMP:20100303T195203Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year":now}


VCARD_1 = """BEGIN:VCARD
VERSION:3.0
N:User;Test
FN:Test User
EMAIL;type=INTERNET;PREF:testuser@example.com
UID:12345-67890-1.1
END:VCARD
""".replace("\n", "\r\n")


class PurgeOldEventsTests(CommonCommonTests, unittest.TestCase):
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
                "old.ics" : (OLD_ICS, metadata,),
                "endless.ics" : (ENDLESS_ICS, metadata,),
                "oldattachment.ics" : (OLD_ATTACHMENT_ICS, metadata,),
            }
        },
        "home2" : {
            "calendar2" : {
                "straddling.ics" : (STRADDLING_ICS, metadata,),
                "recent.ics" : (RECENT_ICS, metadata,),
            },
            "calendar3" : {
                "repeating_awhile.ics" : (REPEATING_AWHILE_ICS, metadata,),
            }
        }
    }

    @inlineCallbacks
    def setUp(self):
        # Turn off delayed indexing option so we can have some useful tests
        self.patch(config, "FreeBusyIndexDelayedExpand", False)

        yield super(PurgeOldEventsTests, self).setUp()
        self._sqlCalendarStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()

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
    def test_eventsOlderThan(self):
        cutoff = PyCalendarDateTime(now, 4, 1, 0, 0, 0)
        txn = self._sqlCalendarStore.newTransaction()

        # Query for all old events
        results = (yield txn.eventsOlderThan(cutoff))
        self.assertEquals(sorted(results),
            sorted([
                ['home1', 'calendar1', 'old.ics', '1901-01-01 01:00:00'],
                ['home1', 'calendar1', 'oldattachment.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar3', 'repeating_awhile.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar2', 'recent.ics', '%s-03-04 22:15:00' % (now,)],
            ])
        )

        # Query for oldest event
        results = (yield txn.eventsOlderThan(cutoff, batchSize=1))
        self.assertEquals(results,
            [
                ['home1', 'calendar1', 'old.ics', '1901-01-01 01:00:00'],
            ]
        )


    @inlineCallbacks
    def test_removeOldEvents(self):
        cutoff = PyCalendarDateTime(now, 4, 1, 0, 0, 0)
        txn = self._sqlCalendarStore.newTransaction()

        # Remove oldest event
        count = (yield txn.removeOldEvents(cutoff, batchSize=1))
        self.assertEquals(count, 1)
        results = (yield txn.eventsOlderThan(cutoff))
        self.assertEquals(sorted(results),
            sorted([
                ['home1', 'calendar1', 'oldattachment.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar3', 'repeating_awhile.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar2', 'recent.ics', '%s-03-04 22:15:00' % (now,)],
            ])
        )

        # Remove remaining oldest events
        count = (yield txn.removeOldEvents(cutoff))
        self.assertEquals(count, 3)
        results = (yield txn.eventsOlderThan(cutoff))
        self.assertEquals(results, [ ])

        # Remove oldest events (none left)
        count = (yield txn.removeOldEvents(cutoff))
        self.assertEquals(count, 0)


    @inlineCallbacks
    def _addAttachment(self):

        txn = self._sqlCalendarStore.newTransaction()

        # Create an event with an attachment
        home = (yield txn.calendarHomeWithUID("home1"))
        calendar = (yield home.calendarWithName("calendar1"))
        event = (yield calendar.calendarObjectWithName("oldattachment.ics"))
        attachment = (yield event.createAttachmentWithName("oldattachment.ics"))
        t = attachment.store(MimeType("text", "x-fixture"))
        t.write("old attachment")
        t.write(" text")
        (yield t.loseConnection())
        (yield txn.commit())

        returnValue(attachment)


    @inlineCallbacks
    def test_removeOrphanedAttachments(self):
        attachment = (yield self._addAttachment())
        txn = self._sqlCalendarStore.newTransaction()
        attachmentPath = attachment._path.path
        self.assertTrue(os.path.exists(attachmentPath))

        orphans = (yield txn.orphanedAttachments())
        self.assertEquals(len(orphans), 0)

        count = (yield txn.removeOrphanedAttachments(batchSize=100))
        self.assertEquals(count, 0)

        # File still exists
        self.assertTrue(os.path.exists(attachmentPath))

        # Delete all old events (including the event containing the attachment)
        cutoff = PyCalendarDateTime(now, 4, 1, 0, 0, 0)
        count = (yield txn.removeOldEvents(cutoff))

        # Just look for orphaned attachments but don't delete
        orphans = (yield txn.orphanedAttachments())
        self.assertEquals(len(orphans), 1)

        # Remove orphaned attachments, should be 1
        count = (yield txn.removeOrphanedAttachments(batchSize=100))
        self.assertEquals(count, 1)

        # Remove orphaned attachments, shouldn't be any
        count = (yield txn.removeOrphanedAttachments())
        self.assertEquals(count, 0)

        # File isn't actually removed until after commit
        (yield txn.commit())

        # Verify the file itself is gone
        self.assertFalse(os.path.exists(attachmentPath))


    @inlineCallbacks
    def test_purgeOldEvents(self):

        # Dry run
        total = (yield purgeOldEvents(self._sqlCalendarStore, self.directory,
            self.rootResource, PyCalendarDateTime(now, 4, 1, 0, 0, 0), 2, dryrun=True,
            verbose=False))
        self.assertEquals(total, 4)

        # Actually remove
        total = (yield purgeOldEvents(self._sqlCalendarStore, self.directory,
            self.rootResource, PyCalendarDateTime(now, 4, 1, 0, 0, 0), 2, verbose=False))
        self.assertEquals(total, 4)

        # There should be no more left
        total = (yield purgeOldEvents(self._sqlCalendarStore, self.directory,
            self.rootResource, PyCalendarDateTime(now, 4, 1, 0, 0, 0), 2, verbose=False))
        self.assertEquals(total, 0)


    @inlineCallbacks
    def test_purgeUID(self):
        txn = self._sqlCalendarStore.newTransaction()

        # Create an addressbook and one CardDAV resource
        abHome = (yield txn.addressbookHomeWithUID("home1", create=True))
        abColl = (yield abHome.addressbookWithName("addressbook"))
        (yield abColl.createAddressBookObjectWithName("card1",
            VCardComponent.fromString(VCARD_1)))
        self.assertEquals(len( (yield abColl.addressbookObjects()) ), 1)

        # Verify there are 3 events in calendar1
        calHome = (yield txn.calendarHomeWithUID("home1"))
        calColl = (yield calHome.calendarWithName("calendar1"))
        self.assertEquals(len( (yield calColl.calendarObjects()) ), 3)

        # Make the newly created objects available to the purgeUID transaction
        (yield txn.commit())

        # Purge home1
        total, ignored = (yield purgeUID(self._sqlCalendarStore, "home1", self.directory,
            self.rootResource, verbose=False, proxies=False,
            when=PyCalendarDateTime(now, 4, 1, 12, 0, 0, 0, PyCalendarTimezone(utc=True))))

        # 2 items deleted: 1 event and 1 vcard
        self.assertEquals(total, 2)

        txn = self._sqlCalendarStore.newTransaction()
        # adressbook home is deleted since it's now empty
        abHome = (yield txn.addressbookHomeWithUID("home1"))
        self.assertEquals(abHome, None)

        calHome = (yield txn.calendarHomeWithUID("home1"))
        calColl = (yield calHome.calendarWithName("calendar1"))
        self.assertEquals(len( (yield calColl.calendarObjects()) ), 2)


    @inlineCallbacks
    def test_purgeUIDCompletely(self):
        txn = self._sqlCalendarStore.newTransaction()

        # Create an addressbook and one CardDAV resource
        abHome = (yield txn.addressbookHomeWithUID("home1", create=True))
        abColl = (yield abHome.addressbookWithName("addressbook"))
        (yield abColl.createAddressBookObjectWithName("card1",
            VCardComponent.fromString(VCARD_1)))
        self.assertEquals(len( (yield abColl.addressbookObjects()) ), 1)

        # Verify there are 3 events in calendar1
        calHome = (yield txn.calendarHomeWithUID("home1"))
        calColl = (yield calHome.calendarWithName("calendar1"))
        self.assertEquals(len( (yield calColl.calendarObjects()) ), 3)

        # Make the newly created objects available to the purgeUID transaction
        (yield txn.commit())

        # Purge home1 completely
        total, ignored = (yield purgeUID(self._sqlCalendarStore, "home1", self.directory,
            self.rootResource, verbose=False, proxies=False, completely=True))

        # 4 items deleted: 3 events and 1 vcard
        self.assertEquals(total, 4)

        # Homes have been deleted as well
        txn = self._sqlCalendarStore.newTransaction()
        abHome = (yield txn.addressbookHomeWithUID("home1"))
        self.assertEquals(abHome, None)
        calHome = (yield txn.calendarHomeWithUID("home1"))
        self.assertEquals(calHome, None)


    @inlineCallbacks
    def test_purgeOrphanedAttachments(self):

        (yield self._addAttachment())

        # Remove old events first
        total = (yield purgeOldEvents(self._sqlCalendarStore, self.directory,
            self.rootResource, PyCalendarDateTime(now, 4, 1, 0, 0, 0), 2, verbose=False))
        self.assertEquals(total, 4)

        # Dry run
        total = (yield purgeOrphanedAttachments(self._sqlCalendarStore, 2,
            dryrun=True, verbose=False))
        self.assertEquals(total, 1)

        # Actually remove
        total = (yield purgeOrphanedAttachments(self._sqlCalendarStore, 2,
            dryrun=False, verbose=False))
        self.assertEquals(total, 1)

        # There should be no more left
        total = (yield purgeOrphanedAttachments(self._sqlCalendarStore, 2,
            dryrun=False, verbose=False))
        self.assertEquals(total, 0)

