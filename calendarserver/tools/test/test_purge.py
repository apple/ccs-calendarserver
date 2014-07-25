##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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


from calendarserver.tools.purge import PurgePrincipalService, \
    PrincipalPurgeHomeWork, PrincipalPurgePollingWork, PrincipalPurgeCheckWork, \
    PrincipalPurgeWork

from pycalendar.datetime import DateTime

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred

from twistedcaldav.config import config
from twistedcaldav.test.util import StoreTestCase

from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE
from txdav.common.datastore.test.util import populateCalendarsFrom

from txweb2.http_headers import MimeType

import datetime



future = DateTime.getNowUTC()
future.offsetDay(1)
future = future.getText()

past = DateTime.getNowUTC()
past.offsetDay(-1)
past = past.getText()

# For test_purgeExistingGUID

# No organizer/attendee
NON_INVITE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:151AFC76-6036-40EF-952B-97D1840760BF
SUMMARY:Non Invitation
DTSTART:%s
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)

# Purging existing organizer; has existing attendee
ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:7ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Organizer
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:10000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000002
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging existing attendee; has existing organizer
ATTENDEE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1974603C-B2C0-4623-92A0-2436DEAB07EF
SUMMARY:Attendee
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:10000000-0000-0000-0000-000000000002
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000002
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)


# For test_purgeNonExistentGUID

# No organizer/attendee, in the past
NON_INVITE_PAST_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:151AFC76-6036-40EF-952B-97D1840760BF
SUMMARY:Non Invitation
DTSTART:%s
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)

# No organizer/attendee, in the future
NON_INVITE_FUTURE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:251AFC76-6036-40EF-952B-97D1840760BF
SUMMARY:Non Invitation
DTSTART:%s
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)


# Purging non-existent organizer; has existing attendee
ORGANIZER_ICS_2 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:7ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Organizer
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:F0000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000002
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging non-existent attendee; has existing organizer
ATTENDEE_ICS_2 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1974603C-B2C0-4623-92A0-2436DEAB07EF
SUMMARY:Attendee
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:10000000-0000-0000-0000-000000000002
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000002
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging non-existent organizer; has existing attendee; repeating
REPEATING_ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:8ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Repeating Organizer
DTSTART:%s
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=400
ORGANIZER:urn:uuid:F0000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000002
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)


# For test_purgeMultipleNonExistentGUIDs

# No organizer/attendee
NON_INVITE_ICS_3 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:151AFC76-6036-40EF-952B-97D1840760BF
SUMMARY:Non Invitation
DTSTART:%s
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)

# Purging non-existent organizer; has non-existent and existent attendees
ORGANIZER_ICS_3 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:7ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Organizer
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:F0000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000002
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000002
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging non-existent attendee; has non-existent organizer and existent attendee
# (Note: Implicit scheduling doesn't update this at all for the existing attendee)
ATTENDEE_ICS_3 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1974603C-B2C0-4623-92A0-2436DEAB07EF
SUMMARY:Attendee
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:F0000000-0000-0000-0000-000000000002
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000002
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000001
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging non-existent attendee; has non-existent attendee and existent organizer
ATTENDEE_ICS_4 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:79F26B10-6ECE-465E-9478-53F2A9FCAFEE
SUMMARY:2 non-existent attendees
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:10000000-0000-0000-0000-000000000002
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:10000000-0000-0000-0000-000000000002
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:F0000000-0000-0000-0000-000000000002
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)



ATTACHMENT_ICS = """BEGIN:VCALENDAR
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
SUMMARY:Attachment
DTSTART;TZID=US/Pacific:20100304T120000
DTSTAMP:20100303T195203Z
SEQUENCE:2
X-APPLE-DROPBOX:/calendars/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/dropbox/F2F14D94-B944-43D9-8F6F-97F95B2764CA.dropbox
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")


# Purging non-existent organizer; has existing attendee; repeating
REPEATING_PUBLIC_EVENT_ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
X-CALENDARSERVER-ACCESS:PRIVATE
BEGIN:VEVENT
UID:8ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Repeating Organizer
DTSTART:%s
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=400
ORGANIZER:urn:x-uid:user01
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:x-uid:user02
DTSTAMP:20100303T195203Z
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)



class PurgePrincipalTests(StoreTestCase):
    """
    Tests for purging the data belonging to a given principal
    """
    uid = "user01"
    uid2 = "user02"

    metadata = {
        "accessMode": "PUBLIC",
        "isScheduleObject": True,
        "scheduleTag": "abc",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }

    requirements = {
        uid : {
            "calendar1" : {
                "attachment.ics" : (ATTACHMENT_ICS, metadata,),
                "organizer.ics" : (REPEATING_PUBLIC_EVENT_ORGANIZER_ICS, metadata,),
            },
            "inbox": {},
        },
        uid2 : {
            "calendar2" : {
                "attendee.ics" : (REPEATING_PUBLIC_EVENT_ORGANIZER_ICS, metadata,),
            },
            "inbox": {},
        },
    }

    @inlineCallbacks
    def setUp(self):
        yield super(PurgePrincipalTests, self).setUp()

        txn = self._sqlCalendarStore.newTransaction()

        # Add attachment to attachment.ics
        self._sqlCalendarStore._dropbox_ok = True
        home = yield txn.calendarHomeWithUID(self.uid)
        calendar = yield home.calendarWithName("calendar1")
        event = yield calendar.calendarObjectWithName("attachment.ics")
        attachment = yield event.createAttachmentWithName("attachment.txt")
        t = attachment.store(MimeType("text", "x-fixture"))
        t.write("attachment")
        t.write(" text")
        yield t.loseConnection()
        self._sqlCalendarStore._dropbox_ok = False

        # Share calendars each way
        home2 = yield txn.calendarHomeWithUID(self.uid2)
        calendar2 = yield home2.calendarWithName("calendar2")
        self.sharedName = yield calendar2.shareWith(home, _BIND_MODE_WRITE)
        self.sharedName2 = yield calendar.shareWith(home2, _BIND_MODE_WRITE)

        yield txn.commit()

        txn = self._sqlCalendarStore.newTransaction()
        home = yield txn.calendarHomeWithUID(self.uid)
        calendar2 = yield home.childWithName(self.sharedName)
        self.assertNotEquals(calendar2, None)
        home2 = yield txn.calendarHomeWithUID(self.uid2)
        calendar1 = yield home2.childWithName(self.sharedName2)
        self.assertNotEquals(calendar1, None)
        yield txn.commit()

        # Now remove user01
        yield self.directory.removeRecords((self.uid,))
        self.patch(config.Scheduling.Options.WorkQueues, "Enabled", False)
        self.patch(config.AutomaticPurging, "Enabled", True)
        self.patch(config.AutomaticPurging, "PollingIntervalSeconds", -1)
        self.patch(config.AutomaticPurging, "CheckStaggerSeconds", 1)
        self.patch(config.AutomaticPurging, "PurgeIntervalSeconds", 3)
        self.patch(config.AutomaticPurging, "HomePurgeDelaySeconds", 1)


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @inlineCallbacks
    def test_purgeUIDs(self):
        """
        Verify purgeUIDs removes homes, and doesn't provision homes that don't exist
        """

        # Now you see it
        home = yield self.homeUnderTest(name=self.uid)
        self.assertNotEquals(home, None)

        calobj2 = yield self.calendarObjectUnderTest(name="attendee.ics", calendar_name="calendar2", home=self.uid2)
        comp = yield calobj2.componentForUser()
        self.assertTrue("STATUS:CANCELLED" not in str(comp))
        self.assertTrue(";UNTIL=" not in str(comp))
        yield self.commit()

        count = (yield PurgePrincipalService.purgeUIDs(
            self.storeUnderTest(), self.directory,
            (self.uid,), verbose=False, proxies=False))
        self.assertEquals(count, 2) # 2 events

        # Wait for queue to process
        while(True):
            txn = self.transactionUnderTest()
            work = yield PrincipalPurgeHomeWork.all(txn)
            yield self.commit()
            if len(work) == 0:
                break
            d = Deferred()
            reactor.callLater(1, lambda : d.callback(None))
            yield d

        # Now you don't
        home = yield self.homeUnderTest(name=self.uid)
        self.assertEquals(home, None)
        # Verify calendar1 was unshared to uid2
        home2 = yield self.homeUnderTest(name=self.uid2)
        self.assertEquals((yield home2.childWithName(self.sharedName)), None)
        yield self.commit()

        count = yield PurgePrincipalService.purgeUIDs(
            self.storeUnderTest(),
            self.directory,
            (self.uid,),
            verbose=False,
            proxies=False,
        )
        self.assertEquals(count, 0)

        # And you still don't (making sure it's not provisioned)
        home = yield self.homeUnderTest(name=self.uid)
        self.assertEquals(home, None)
        yield self.commit()

        calobj2 = yield self.calendarObjectUnderTest(name="attendee.ics", calendar_name="calendar2", home=self.uid2)
        comp = yield calobj2.componentForUser()
        self.assertTrue("STATUS:CANCELLED" in str(comp))
        self.assertTrue(";UNTIL=" not in str(comp))
        yield self.commit()



class PurgePrincipalTestsWithWorkQueue(PurgePrincipalTests):
    """
    Same as L{PurgePrincipalTests} but with the work queue enabled.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(PurgePrincipalTestsWithWorkQueue, self).setUp()
        self.patch(config.Scheduling.Options.WorkQueues, "Enabled", True)
        self.patch(config.AutomaticPurging, "Enabled", True)
        self.patch(config.AutomaticPurging, "PollingIntervalSeconds", -1)
        self.patch(config.AutomaticPurging, "CheckStaggerSeconds", 1)
        self.patch(config.AutomaticPurging, "PurgeIntervalSeconds", 3)
        self.patch(config.AutomaticPurging, "HomePurgeDelaySeconds", 1)


    @inlineCallbacks
    def test_purgeUIDService(self):
        """
        Test that the full sequence of work items are processed via automatic polling.
        """

        # Now you see it
        home = yield self.homeUnderTest(name=self.uid)
        self.assertNotEquals(home, None)

        calobj2 = yield self.calendarObjectUnderTest(name="attendee.ics", calendar_name="calendar2", home=self.uid2)
        comp = yield calobj2.componentForUser()
        self.assertTrue("STATUS:CANCELLED" not in str(comp))
        self.assertTrue(";UNTIL=" not in str(comp))
        yield self.commit()

        txn = self.transactionUnderTest()
        notBefore = (
            datetime.datetime.utcnow() +
            datetime.timedelta(seconds=3)
        )
        yield txn.enqueue(PrincipalPurgePollingWork, notBefore=notBefore)
        yield self.commit()

        while True:
            txn = self.transactionUnderTest()
            work1 = yield PrincipalPurgePollingWork.all(txn)
            work2 = yield PrincipalPurgeCheckWork.all(txn)
            work3 = yield PrincipalPurgeWork.all(txn)
            work4 = yield PrincipalPurgeHomeWork.all(txn)

            if len(work4) != 0:
                home = yield txn.calendarHomeWithUID(self.uid)
                self.assertTrue(home.purging())

            yield self.commit()
            # print len(work1), len(work2), len(work3), len(work4)
            if len(work1) + len(work2) + len(work3) + len(work4) == 0:
                break
            d = Deferred()
            reactor.callLater(1, lambda : d.callback(None))
            yield d

        # Now you don't
        home = yield self.homeUnderTest(name=self.uid)
        self.assertEquals(home, None)
        # Verify calendar1 was unshared to uid2
        home2 = yield self.homeUnderTest(name=self.uid2)
        self.assertEquals((yield home2.childWithName(self.sharedName)), None)

        calobj2 = yield self.calendarObjectUnderTest(name="attendee.ics", calendar_name="calendar2", home=self.uid2)
        comp = yield calobj2.componentForUser()
        self.assertTrue("STATUS:CANCELLED" in str(comp))
        self.assertTrue(";UNTIL=" not in str(comp))
        yield self.commit()
