##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
from calendarserver.tools.purge import PurgeOldEventsService, PurgeAttachmentsService, \
    PurgePrincipalService

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone

from twext.enterprise.dal.syntax import Update, Delete
from twext.web2.http_headers import MimeType

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial import unittest

from twistedcaldav.config import config
from twistedcaldav.vcard import Component as VCardComponent

from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.test.util import buildStore, populateCalendarsFrom, CommonCommonTests

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
""".replace("\n", "\r\n") % {"year": now - 5}

ATTACHMENT_ICS = """BEGIN:VCALENDAR
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
UID:57A5D1F6-9A57-4F74-9520-25C617F54B88-%(uid)s
TRANSP:OPAQUE
SUMMARY:Ancient event with attachment
DTSTART;TZID=US/Pacific:%(year)s0308T111500
DTEND;TZID=US/Pacific:%(year)s0308T151500
DTSTAMP:20100303T181220Z
X-APPLE-DROPBOX:/calendars/__uids__/user01/dropbox/%(dropboxid)s.dropbox
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

MATTACHMENT_ICS = """BEGIN:VCALENDAR
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
UID:57A5D1F6-9A57-4F74-9520-25C617F54B88-%(uid)s
TRANSP:OPAQUE
SUMMARY:Ancient event with attachment
DTSTART;TZID=US/Pacific:%(year)s0308T111500
DTEND;TZID=US/Pacific:%(year)s0308T151500
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
DTEND;TZID=US/Pacific:%(year)s0308T151500
RRULE:FREQ=YEARLY;INTERVAL=1
TRANSP:OPAQUE
SUMMARY:Ancient Repeating Endless
DTSTART;TZID=US/Pacific:%(year)s0308T111500
DTSTAMP:20100303T194710Z
SEQUENCE:4
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now - 5}

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
""".replace("\n", "\r\n") % {"year": now - 5}

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
""".replace("\n", "\r\n") % {"year": now - 2, "until": now + 1}

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
""".replace("\n", "\r\n") % {"year": now}


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
                "oldattachment1.ics" : (ATTACHMENT_ICS % {"year": now - 5, "uid": "1.1", "dropboxid": "1.1"}, metadata,),
                "oldattachment2.ics" : (ATTACHMENT_ICS % {"year": now - 5, "uid": "1.2", "dropboxid": "1.2"}, metadata,),
                "currentattachment3.ics" : (ATTACHMENT_ICS % {"year": now + 1, "uid": "1.3", "dropboxid": "1.3"}, metadata,),
                "oldmattachment1.ics" : (MATTACHMENT_ICS % {"year": now - 5, "uid": "1.1m"}, metadata,),
                "oldmattachment2.ics" : (MATTACHMENT_ICS % {"year": now - 5, "uid": "1.2m"}, metadata,),
                "currentmattachment3.ics" : (MATTACHMENT_ICS % {"year": now + 1, "uid": "1.3m"}, metadata,),
            }
        },
        "home2" : {
            "calendar2" : {
                "straddling.ics" : (STRADDLING_ICS, metadata,),
                "recent.ics" : (RECENT_ICS, metadata,),
                "oldattachment1.ics" : (ATTACHMENT_ICS % {"year": now - 5, "uid": "2.1", "dropboxid": "2.1"}, metadata,),
                "currentattachment2.ics" : (ATTACHMENT_ICS % {"year": now + 1, "uid": "2.2", "dropboxid": "2.1"}, metadata,),
                "oldattachment3.ics" : (ATTACHMENT_ICS % {"year": now - 5, "uid": "2.3", "dropboxid": "2.2"}, metadata,),
                "oldattachment4.ics" : (ATTACHMENT_ICS % {"year": now - 5, "uid": "2.4", "dropboxid": "2.2"}, metadata,),
                "oldmattachment1.ics" : (MATTACHMENT_ICS % {"year": now - 5, "uid": "2.1"}, metadata,),
                "currentmattachment2.ics" : (MATTACHMENT_ICS % {"year": now + 1, "uid": "2.2"}, metadata,),
                "oldmattachment3.ics" : (MATTACHMENT_ICS % {"year": now - 5, "uid": "2.3"}, metadata,),
                "oldmattachment4.ics" : (MATTACHMENT_ICS % {"year": now - 5, "uid": "2.4"}, metadata,),
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

        txn = self._sqlCalendarStore.newTransaction()
        Delete(
            From=schema.ATTACHMENT,
            Where=None
        ).on(txn)

        (yield txn.commit())


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
                ['home1', 'calendar1', 'oldattachment1.ics', '1901-01-01 01:00:00'],
                ['home1', 'calendar1', 'oldattachment2.ics', '1901-01-01 01:00:00'],
                ['home1', 'calendar1', 'oldmattachment1.ics', '1901-01-01 01:00:00'],
                ['home1', 'calendar1', 'oldmattachment2.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar3', 'repeating_awhile.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar2', 'recent.ics', '%s-03-04 22:15:00' % (now,)],
                ['home2', 'calendar2', 'oldattachment1.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar2', 'oldattachment3.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar2', 'oldattachment4.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar2', 'oldmattachment1.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar2', 'oldmattachment3.ics', '1901-01-01 01:00:00'],
                ['home2', 'calendar2', 'oldmattachment4.ics', '1901-01-01 01:00:00'],
            ])
        )

        # Query for oldest event - actually with limited time caching, the oldest event
        # cannot be precisely known, all we get back is the first one in the sorted list
        # where each has the 1901 "dummy" time stamp to indicate a partial cache
        results = (yield txn.eventsOlderThan(cutoff, batchSize=1))
        self.assertEquals(len(results), 1)


    @inlineCallbacks
    def test_removeOldEvents(self):
        cutoff = PyCalendarDateTime(now, 4, 1, 0, 0, 0)
        txn = self._sqlCalendarStore.newTransaction()

        # Remove oldest event - except we don't know what that is because of the dummy timestamps
        # used with a partial index. So all we can check is that one event was removed.
        count = (yield txn.removeOldEvents(cutoff, batchSize=1))
        self.assertEquals(count, 1)
        results = (yield txn.eventsOlderThan(cutoff))
        self.assertEquals(len(results), 12)

        # Remove remaining oldest events
        count = (yield txn.removeOldEvents(cutoff))
        self.assertEquals(count, 12)
        results = (yield txn.eventsOlderThan(cutoff))
        self.assertEquals(results, [])

        # Remove oldest events (none left)
        count = (yield txn.removeOldEvents(cutoff))
        self.assertEquals(count, 0)


    @inlineCallbacks
    def _addAttachment(self, home, calendar, event, name):

        txn = self._sqlCalendarStore.newTransaction()

        # Create an event with an attachment
        home = (yield txn.calendarHomeWithUID(home))
        calendar = (yield home.calendarWithName(calendar))
        event = (yield calendar.calendarObjectWithName(event))
        attachment = (yield event.createAttachmentWithName(name))
        t = attachment.store(MimeType("text", "x-fixture"))
        t.write("%s/%s/%s/%s" % (home, calendar, event, name,))
        t.write(" attachment")
        (yield t.loseConnection())

        (yield txn.commit())

        returnValue(attachment)


    @inlineCallbacks
    def _orphanAttachment(self, home, calendar, event):

        txn = self._sqlCalendarStore.newTransaction()

        # Reset dropbox id in calendar_object
        home = (yield txn.calendarHomeWithUID(home))
        calendar = (yield home.calendarWithName(calendar))
        event = (yield calendar.calendarObjectWithName(event))
        co = schema.CALENDAR_OBJECT
        Update(
            {co.DROPBOX_ID: None, },
            Where=co.RESOURCE_ID == event._resourceID,
        ).on(txn)

        (yield txn.commit())


    @inlineCallbacks
    def _addManagedAttachment(self, home, calendar, event, name):

        txn = self._sqlCalendarStore.newTransaction()

        # Create an event with an attachment
        home = (yield txn.calendarHomeWithUID(home))
        calendar = (yield home.calendarWithName(calendar))
        event = (yield calendar.calendarObjectWithName(event))
        attachment = (yield event.createManagedAttachment())
        t = attachment.store(MimeType("text", "x-fixture"), name)
        t.write("%s/%s/%s/%s" % (home, calendar, event, name,))
        t.write(" managed attachment")
        (yield t.loseConnection())

        (yield txn.commit())

        returnValue(attachment)


    @inlineCallbacks
    def test_removeOrphanedAttachments(self):

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota1 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertEqual(quota1, 0)

        attachment = (yield self._addAttachment("home1", "calendar1", "oldattachment1.ics", "att1"))
        attachmentPath = attachment._path.path
        self.assertTrue(os.path.exists(attachmentPath))

        mattachment1 = (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment1.ics", "matt1"))
        mattachment2 = (yield self._addManagedAttachment("home1", "calendar1", "currentmattachment3.ics", "matt3"))

        mattachmentPath1 = mattachment1._path.path
        self.assertTrue(os.path.exists(mattachmentPath1))
        mattachmentPath2 = mattachment2._path.path
        self.assertTrue(os.path.exists(mattachmentPath2))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota2 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota2 > quota1)

        orphans = (yield self.transactionUnderTest().orphanedAttachments())
        self.assertEquals(len(orphans), 0)

        count = (yield self.transactionUnderTest().removeOrphanedAttachments(batchSize=100))
        self.assertEquals(count, 0)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertNotEqual(quota, 0)

        # Files still exist
        self.assertTrue(os.path.exists(attachmentPath))
        self.assertTrue(os.path.exists(mattachmentPath1))
        self.assertTrue(os.path.exists(mattachmentPath2))

        # Delete all old events (including the event containing the attachment)
        cutoff = PyCalendarDateTime(now, 4, 1, 0, 0, 0)
        count = (yield self.transactionUnderTest().removeOldEvents(cutoff))

        # See which events have gone and which exist
        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        calendar = (yield home.calendarWithName("calendar1"))
        self.assertNotEqual((yield calendar.calendarObjectWithName("endless.ics")), None)
        self.assertNotEqual((yield calendar.calendarObjectWithName("currentmattachment3.ics")), None)
        self.assertEqual((yield calendar.calendarObjectWithName("old.ics")), None)
        self.assertEqual((yield calendar.calendarObjectWithName("oldattachment1.ics")), None)
        self.assertEqual((yield calendar.calendarObjectWithName("oldmattachment1.ics")), None)
        (yield self.commit())

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota3 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota3 < quota2)
        self.assertNotEqual(quota3, 0)

        # Just look for orphaned attachments - none left
        orphans = (yield self.transactionUnderTest().orphanedAttachments())
        self.assertEquals(len(orphans), 0)

        # Files
        self.assertFalse(os.path.exists(attachmentPath))
        self.assertFalse(os.path.exists(mattachmentPath1))
        self.assertTrue(os.path.exists(mattachmentPath2))


    @inlineCallbacks
    def test_purgeOldEvents(self):

        # Dry run
        total = (yield PurgeOldEventsService.purgeOldEvents(
            self._sqlCalendarStore,
            PyCalendarDateTime(now, 4, 1, 0, 0, 0),
            2,
            dryrun=True,
            verbose=False
        ))
        self.assertEquals(total, 13)

        # Actually remove
        total = (yield PurgeOldEventsService.purgeOldEvents(
            self._sqlCalendarStore,
            PyCalendarDateTime(now, 4, 1, 0, 0, 0),
            2,
            verbose=False
        ))
        self.assertEquals(total, 13)

        # There should be no more left
        total = (yield PurgeOldEventsService.purgeOldEvents(
            self._sqlCalendarStore,
            PyCalendarDateTime(now, 4, 1, 0, 0, 0),
            2,
            verbose=False
        ))
        self.assertEquals(total, 0)


    @inlineCallbacks
    def test_purgeUID(self):
        txn = self._sqlCalendarStore.newTransaction()

        # Create an addressbook and one CardDAV resource
        abHome = (yield txn.addressbookHomeWithUID("home1", create=True))
        abColl = (yield abHome.addressbookWithName("addressbook"))
        (yield abColl.createAddressBookObjectWithName("card1",
            VCardComponent.fromString(VCARD_1)))
        self.assertEquals(len((yield abColl.addressbookObjects())), 1)

        # Verify there are 8 events in calendar1
        calHome = (yield txn.calendarHomeWithUID("home1"))
        calColl = (yield calHome.calendarWithName("calendar1"))
        self.assertEquals(len((yield calColl.calendarObjects())), 8)

        # Make the newly created objects available to the purgeUID transaction
        (yield txn.commit())

        # Purge home1
        total, ignored = (yield PurgePrincipalService.purgeUIDs(self._sqlCalendarStore, self.directory,
            self.rootResource, ("home1",), verbose=False, proxies=False,
            when=PyCalendarDateTime(now, 4, 1, 12, 0, 0, 0, PyCalendarTimezone(utc=True))))

        # 4 items deleted: 3 events and 1 vcard
        self.assertEquals(total, 4)

        txn = self._sqlCalendarStore.newTransaction()
        # adressbook home is deleted since it's now empty
        abHome = (yield txn.addressbookHomeWithUID("home1"))
        self.assertEquals(abHome, None)

        calHome = (yield txn.calendarHomeWithUID("home1"))
        calColl = (yield calHome.calendarWithName("calendar1"))
        self.assertEquals(len((yield calColl.calendarObjects())), 5)


    @inlineCallbacks
    def test_purgeUIDCompletely(self):
        txn = self._sqlCalendarStore.newTransaction()

        # Create an addressbook and one CardDAV resource
        abHome = (yield txn.addressbookHomeWithUID("home1", create=True))
        abColl = (yield abHome.addressbookWithName("addressbook"))
        (yield abColl.createAddressBookObjectWithName("card1",
            VCardComponent.fromString(VCARD_1)))
        self.assertEquals(len((yield abColl.addressbookObjects())), 1)

        # Verify there are 8 events in calendar1
        calHome = (yield txn.calendarHomeWithUID("home1"))
        calColl = (yield calHome.calendarWithName("calendar1"))
        self.assertEquals(len((yield calColl.calendarObjects())), 8)

        # Make the newly created objects available to the purgeUID transaction
        (yield txn.commit())

        # Purge home1 completely
        total, ignored = (yield PurgePrincipalService.purgeUIDs(self._sqlCalendarStore, self.directory,
            self.rootResource, ("home1",), verbose=False, proxies=False, completely=True))

        # 9 items deleted: 8 events and 1 vcard
        self.assertEquals(total, 9)

        # Homes have been deleted as well
        txn = self._sqlCalendarStore.newTransaction()
        abHome = (yield txn.addressbookHomeWithUID("home1"))
        self.assertEquals(abHome, None)
        calHome = (yield txn.calendarHomeWithUID("home1"))
        self.assertEquals(calHome, None)


    @inlineCallbacks
    def test_purgeAttachmentsWithoutCutoffWithPurgeOld(self):
        """
        L{PurgeAttachmentsService.purgeAttachments} purges only orphaned attachments, not current ones.
        """

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota1 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertEqual(quota1, 0)

        (yield self._addAttachment("home1", "calendar1", "oldattachment1.ics", "att1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.2"))
        (yield self._addAttachment("home1", "calendar1", "currentattachment3.ics", "att3"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment1.ics", "att4"))
        (yield self._addAttachment("home2", "calendar2", "currentattachment2.ics", "att5"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment3.ics", "att6"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment4.ics", "att7"))
        (yield self._orphanAttachment("home1", "calendar1", "oldattachment1.ics"))

        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment1.ics", "matt1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.2"))
        (yield self._addManagedAttachment("home1", "calendar1", "currentmattachment3.ics", "matt3"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment1.ics", "matt4"))
        (yield self._addManagedAttachment("home2", "calendar2", "currentmattachment2.ics", "matt5"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment3.ics", "matt6"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment4.ics", "matt7"))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota2 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota2 > quota1)

        # Remove old events first
        total = (yield PurgeOldEventsService.purgeOldEvents(
            self._sqlCalendarStore,
            PyCalendarDateTime(now, 4, 1, 0, 0, 0),
            2,
            verbose=False
        ))
        self.assertEquals(total, 13)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota3 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota3 < quota2)

        # Dry run
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 0, 2, dryrun=True, verbose=False))
        self.assertEquals(total, 1)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota4 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota4 == quota3)

        # Actually remove
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 0, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 1)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota5 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota5 < quota4)

        # There should be no more left
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 0, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 0)


    @inlineCallbacks
    def test_purgeAttachmentsWithoutCutoff(self):
        """
        L{PurgeAttachmentsService.purgeAttachments} purges only orphaned attachments, not current ones.
        """

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota1 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertEqual(quota1, 0)

        (yield self._addAttachment("home1", "calendar1", "oldattachment1.ics", "att1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.2"))
        (yield self._addAttachment("home1", "calendar1", "currentattachment3.ics", "att3"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment1.ics", "att4"))
        (yield self._addAttachment("home2", "calendar2", "currentattachment2.ics", "att5"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment3.ics", "att6"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment4.ics", "att7"))
        (yield self._orphanAttachment("home1", "calendar1", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "currentattachment2.ics"))

        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment1.ics", "matt1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.2"))
        (yield self._addManagedAttachment("home1", "calendar1", "currentmattachment3.ics", "matt3"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment1.ics", "matt4"))
        (yield self._addManagedAttachment("home2", "calendar2", "currentmattachment2.ics", "matt5"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment3.ics", "matt6"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment4.ics", "matt7"))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota2 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota2 > quota1)

        # Dry run
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 0, 2, dryrun=True, verbose=False))
        self.assertEquals(total, 3)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota3 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota3 == quota2)

        # Actually remove
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 0, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 3)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota4 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota4 < quota3)

        # There should be no more left
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 0, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 0)


    @inlineCallbacks
    def test_purgeAttachmentsWithoutCutoffWithMatchingUUID(self):
        """
        L{PurgeAttachmentsService.purgeAttachments} purges only orphaned attachments, not current ones.
        """

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota1 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertEqual(quota1, 0)

        (yield self._addAttachment("home1", "calendar1", "oldattachment1.ics", "att1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.2"))
        (yield self._addAttachment("home1", "calendar1", "currentattachment3.ics", "att3"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment1.ics", "att4"))
        (yield self._addAttachment("home2", "calendar2", "currentattachment2.ics", "att5"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment3.ics", "att6"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment4.ics", "att7"))
        (yield self._orphanAttachment("home1", "calendar1", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "currentattachment2.ics"))

        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment1.ics", "matt1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.2"))
        (yield self._addManagedAttachment("home1", "calendar1", "currentmattachment3.ics", "matt3"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment1.ics", "matt4"))
        (yield self._addManagedAttachment("home2", "calendar2", "currentmattachment2.ics", "matt5"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment3.ics", "matt6"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment4.ics", "matt7"))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota2 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota2 > quota1)

        # Dry run
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home1", 0, 2, dryrun=True, verbose=False))
        self.assertEquals(total, 1)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota3 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota3 == quota2)

        # Actually remove
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home1", 0, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 1)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota4 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota4 < quota3)

        # There should be no more left
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home1", 0, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 0)


    @inlineCallbacks
    def test_purgeAttachmentsWithoutCutoffWithoutMatchingUUID(self):
        """
        L{PurgeAttachmentsService.purgeAttachments} purges only orphaned attachments, not current ones.
        """

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota1 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertEqual(quota1, 0)

        (yield self._addAttachment("home1", "calendar1", "oldattachment1.ics", "att1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.2"))
        (yield self._addAttachment("home1", "calendar1", "currentattachment3.ics", "att3"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment1.ics", "att4"))
        (yield self._addAttachment("home2", "calendar2", "currentattachment2.ics", "att5"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment3.ics", "att6"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment4.ics", "att7"))
        (yield self._orphanAttachment("home1", "calendar1", "oldattachment1.ics"))

        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment1.ics", "matt1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.2"))
        (yield self._addManagedAttachment("home1", "calendar1", "currentmattachment3.ics", "matt3"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment1.ics", "matt4"))
        (yield self._addManagedAttachment("home2", "calendar2", "currentmattachment2.ics", "matt5"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment3.ics", "matt6"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment4.ics", "matt7"))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota2 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota2 > quota1)

        # Dry run
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home2", 0, 2, dryrun=True, verbose=False))
        self.assertEquals(total, 0)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota3 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota3 == quota2)

        # Actually remove
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home2", 0, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 0)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota4 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota4 == quota3)

        # There should be no more left
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home2", 0, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 0)


    @inlineCallbacks
    def test_purgeAttachmentsWithCutoffOld(self):
        """
        L{PurgeAttachmentsService.purgeAttachments} purges only orphaned attachments, not current ones.
        """

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota1 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertEqual(quota1, 0)

        (yield self._addAttachment("home1", "calendar1", "oldattachment1.ics", "att1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.2"))
        (yield self._addAttachment("home1", "calendar1", "currentattachment3.ics", "att3"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment1.ics", "att4"))
        (yield self._addAttachment("home2", "calendar2", "currentattachment2.ics", "att5"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment3.ics", "att6"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment4.ics", "att7"))
        (yield self._orphanAttachment("home1", "calendar1", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "currentattachment2.ics"))

        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment1.ics", "matt1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.2"))
        (yield self._addManagedAttachment("home1", "calendar1", "currentmattachment3.ics", "matt3"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment1.ics", "matt4"))
        (yield self._addManagedAttachment("home2", "calendar2", "currentmattachment2.ics", "matt5"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment3.ics", "matt6"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment4.ics", "matt7"))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota2 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota2 > quota1)

        # Dry run
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 14, 2, dryrun=True, verbose=False))
        self.assertEquals(total, 13)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota3 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota3 == quota2)

        # Actually remove
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 14, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 13)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota4 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota4 < quota3)

        # There should be no more left
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, None, 14, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 0)


    @inlineCallbacks
    def test_purgeAttachmentsWithCutoffOldWithMatchingUUID(self):
        """
        L{PurgeAttachmentsService.purgeAttachments} purges only orphaned attachments, not current ones.
        """

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota1 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertEqual(quota1, 0)

        (yield self._addAttachment("home1", "calendar1", "oldattachment1.ics", "att1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.2"))
        (yield self._addAttachment("home1", "calendar1", "currentattachment3.ics", "att3"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment1.ics", "att4"))
        (yield self._addAttachment("home2", "calendar2", "currentattachment2.ics", "att5"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment3.ics", "att6"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment4.ics", "att7"))
        (yield self._orphanAttachment("home1", "calendar1", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "currentattachment2.ics"))

        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment1.ics", "matt1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.2"))
        (yield self._addManagedAttachment("home1", "calendar1", "currentmattachment3.ics", "matt3"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment1.ics", "matt4"))
        (yield self._addManagedAttachment("home2", "calendar2", "currentmattachment2.ics", "matt5"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment3.ics", "matt6"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment4.ics", "matt7"))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota2 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota2 > quota1)

        # Dry run
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home1", 14, 2, dryrun=True, verbose=False))
        self.assertEquals(total, 6)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota3 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota3 == quota2)

        # Actually remove
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home1", 14, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 6)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota4 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota4 < quota3)

        # There should be no more left
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home1", 14, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 0)


    @inlineCallbacks
    def test_purgeAttachmentsWithCutoffOldWithoutMatchingUUID(self):
        """
        L{PurgeAttachmentsService.purgeAttachments} purges only orphaned attachments, not current ones.
        """

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota1 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertEqual(quota1, 0)

        (yield self._addAttachment("home1", "calendar1", "oldattachment1.ics", "att1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.1"))
        (yield self._addAttachment("home1", "calendar1", "oldattachment2.ics", "att2.2"))
        (yield self._addAttachment("home1", "calendar1", "currentattachment3.ics", "att3"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment1.ics", "att4"))
        (yield self._addAttachment("home2", "calendar2", "currentattachment2.ics", "att5"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment3.ics", "att6"))
        (yield self._addAttachment("home2", "calendar2", "oldattachment4.ics", "att7"))
        (yield self._orphanAttachment("home1", "calendar1", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "oldattachment1.ics"))
        (yield self._orphanAttachment("home2", "calendar2", "currentattachment2.ics"))

        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment1.ics", "matt1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.1"))
        (yield self._addManagedAttachment("home1", "calendar1", "oldmattachment2.ics", "matt2.2"))
        (yield self._addManagedAttachment("home1", "calendar1", "currentmattachment3.ics", "matt3"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment1.ics", "matt4"))
        (yield self._addManagedAttachment("home2", "calendar2", "currentmattachment2.ics", "matt5"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment3.ics", "matt6"))
        (yield self._addManagedAttachment("home2", "calendar2", "oldmattachment4.ics", "matt7"))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota2 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota2 > quota1)

        # Dry run
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home2", 14, 2, dryrun=True, verbose=False))
        self.assertEquals(total, 7)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota3 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota3 == quota2)

        # Actually remove
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home2", 14, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 7)

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota4 = (yield home.quotaUsedBytes())
        (yield self.commit())
        self.assertTrue(quota4 == quota3)

        # There should be no more left
        total = (yield PurgeAttachmentsService.purgeAttachments(self._sqlCalendarStore, "home2", 14, 2, dryrun=False, verbose=False))
        self.assertEquals(total, 0)
