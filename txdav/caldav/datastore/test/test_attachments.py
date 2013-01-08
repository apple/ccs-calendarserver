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

from twisted.trial import unittest
from txdav.common.datastore.test.util import CommonCommonTests, buildStore, \
    populateCalendarsFrom
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav.config import config
import os
from calendarserver.tap.util import getRootResource
from twext.enterprise.dal.syntax import Delete
from txdav.common.datastore.sql_tables import schema
from pycalendar.datetime import PyCalendarDateTime
from txdav.caldav.datastore.sql import CalendarStoreFeatures, DropBoxAttachment, \
    ManagedAttachment
from twext.web2.http_headers import MimeType
from twistedcaldav.ical import Property
from pycalendar.value import PyCalendarValue

"""
Tests for txdav.caldav.datastore.sql attachment handling.
"""

now = PyCalendarDateTime.getToday().getYear()

PLAIN_ICS = """BEGIN:VCALENDAR
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
UID:685BC3A1-195A-49B3-926D-388DDACA78A6-%(uid)s
DTEND;TZID=US/Pacific:%(year)s0307T151500
TRANSP:OPAQUE
SUMMARY:Event without attachment
DTSTART;TZID=US/Pacific:%(year)s0307T111500
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

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
SUMMARY:Event with attachment
DTSTART;TZID=US/Pacific:%(year)s0308T111500
DTEND;TZID=US/Pacific:%(year)s0308T151500
DTSTAMP:20100303T181220Z
X-APPLE-DROPBOX:/calendars/__uids__/%(userid)s/dropbox/%(dropboxid)s.dropbox
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")


class AttachmentMigrationTests(CommonCommonTests, unittest.TestCase):
    """
    Test migrating dropbox to managed attachments.
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
                "1.1.ics" : (PLAIN_ICS % {"year": now, "uid": "1.1", }, metadata,),
                "1.2.ics" : (ATTACHMENT_ICS % {"year": now, "uid": "1.2", "userid": "user01", "dropboxid": "1.2"}, metadata,),
                "1.3.ics" : (ATTACHMENT_ICS % {"year": now, "uid": "1.3", "userid": "user01", "dropboxid": "1.3"}, metadata,),
                "1.4.ics" : (ATTACHMENT_ICS % {"year": now, "uid": "1.4", "userid": "user01", "dropboxid": "1.4"}, metadata,),
                "1.5.ics" : (ATTACHMENT_ICS % {"year": now, "uid": "1.5", "userid": "user01", "dropboxid": "1.4"}, metadata,),
            }
        },
        "home2" : {
            "calendar2" : {
                "2-2.1.ics" : (PLAIN_ICS % {"year": now, "uid": "2-2.1", }, metadata,),
                "2-2.2.ics" : (ATTACHMENT_ICS % {"year": now, "uid": "2-2.2", "userid": "user02", "dropboxid": "2.2"}, metadata,),
                "2-2.3.ics" : (ATTACHMENT_ICS % {"year": now, "uid": "1.3", "userid": "user01", "dropboxid": "1.3"}, metadata,),
            },
            "calendar3" : {
                "2-3.1.ics" : (PLAIN_ICS % {"year": now, "uid": "2-3.1", }, metadata,),
                "2-3.2.ics" : (ATTACHMENT_ICS % {"year": now, "uid": "1.4", "userid": "user01", "dropboxid": "1.4"}, metadata,),
                "2-3.3.ics" : (ATTACHMENT_ICS % {"year": now, "uid": "1.5", "userid": "user01", "dropboxid": "1.4"}, metadata,),
            }
        }
    }

    @inlineCallbacks
    def setUp(self):
        yield super(AttachmentMigrationTests, self).setUp()
        self._sqlCalendarStore = yield buildStore(self, self.notifierFactory)
        yield self.populate()

        self.patch(config.DirectoryService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "attachments", "accounts.xml"
            )
        )
        self.patch(config.ResourceService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "attachments", "resources.xml"
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
        Delete(
            From=schema.ATTACHMENT_CALENDAR_OBJECT,
            Where=None
        ).on(txn)

        yield txn.commit()


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def _addAttachment(self, home, calendar, event, dropboxid, name):

        txn = self._sqlCalendarStore.newTransaction()

        # Create an event with an attachment
        home = (yield txn.calendarHomeWithUID(home))
        calendar = (yield home.calendarWithName(calendar))
        event = (yield calendar.calendarObjectWithName(event))
        attachment = (yield event.createAttachmentWithName(name))
        t = attachment.store(MimeType("text", "x-fixture"))
        t.write("%s/%s/%s/%s" % (home, calendar, event, name,))
        t.write(" attachment")
        yield t.loseConnection()

        cal = (yield event.component())
        cal.mainComponent().addProperty(Property(
            "ATTACH",
            "http://localhost/calendars/users/%s/dropbox/%s.dropbox/%s" % (home.name(), dropboxid, name,),
            valuetype=PyCalendarValue.VALUETYPE_URI
        ))
        yield event.setComponent(cal)
        yield txn.commit()

        returnValue(attachment)


    @inlineCallbacks
    def _addAttachmentProperty(self, home, calendar, event, dropboxid, owner_home, name):

        txn = self._sqlCalendarStore.newTransaction()

        # Create an event with an attachment
        home = (yield txn.calendarHomeWithUID(home))
        calendar = (yield home.calendarWithName(calendar))
        event = (yield calendar.calendarObjectWithName(event))

        cal = (yield event.component())
        cal.mainComponent().addProperty(Property(
            "ATTACH",
            "http://localhost/calendars/users/%s/dropbox/%s.dropbox/%s" % (owner_home, dropboxid, name,),
            valuetype=PyCalendarValue.VALUETYPE_URI
        ))
        yield event.setComponent(cal)
        yield txn.commit()


    @inlineCallbacks
    def _addAllAttachments(self):
        """
        Add the full set of attachments to be used for testing.
        """
        yield self._addAttachment("home1", "calendar1", "1.2.ics", "1.2", "attach_1_2_1.txt")
        yield self._addAttachment("home1", "calendar1", "1.2.ics", "1.2", "attach_1_2_2.txt")
        yield self._addAttachment("home1", "calendar1", "1.3.ics", "1.3", "attach_1_3.txt")
        yield self._addAttachment("home1", "calendar1", "1.4.ics", "1.4", "attach_1_4.txt")
        yield self._addAttachmentProperty("home1", "calendar1", "1.5.ics", "1.4", "home1", "attach_1_4.txt")

        yield self._addAttachment("home2", "calendar2", "2-2.2.ics", "2.2", "attach_2_2.txt")
        yield self._addAttachmentProperty("home2", "calendar2", "2-2.3.ics", "1.3", "home1", "attach_1_3.txt")
        yield self._addAttachmentProperty("home2", "calendar3", "2-3.2.ics", "1.4", "home1", "attach_1_4.txt")
        yield self._addAttachmentProperty("home2", "calendar3", "2-3.3.ics", "1.4", "home1", "attach_1_4.txt")


    @inlineCallbacks
    def _verifyConversion(self, home, calendar, event, filenames):
        """
        Verify that the specified event contains managed attachments only.
        """
        txn = self._sqlCalendarStore.newTransaction()
        home = (yield txn.calendarHomeWithUID(home))
        calendar = (yield home.calendarWithName(calendar))
        event = (yield calendar.calendarObjectWithName(event))
        component = (yield event.component()).mainComponent()

        # No more X-APPLE-DROPBOX
        self.assertFalse(component.hasProperty("X-APPLE-DROPBOX"))

        # Check only managed attachments exist
        attachments = (yield event.component()).mainComponent().properties("ATTACH")
        dropbox_count = 0
        managed_count = 0
        for attach in attachments:
            if attach.hasParameter("MANAGED-ID"):
                managed_count += 1
                self.assertTrue(attach.value().find("/dropbox/") == -1)
                self.assertTrue(attach.parameterValue("FILENAME") in filenames)
            else:
                dropbox_count += 1
        self.assertEqual(managed_count, len(filenames))
        self.assertEqual(dropbox_count, 0)
        yield txn.commit()


    @inlineCallbacks
    def _verifyNoConversion(self, home, calendar, event, filenames):
        """
        Verify that the specified event does not contain managed attachments.
        """
        txn = self._sqlCalendarStore.newTransaction()
        home = (yield txn.calendarHomeWithUID(home))
        calendar = (yield home.calendarWithName(calendar))
        event = (yield calendar.calendarObjectWithName(event))
        component = (yield event.component()).mainComponent()

        # X-APPLE-DROPBOX present
        self.assertTrue(component.hasProperty("X-APPLE-DROPBOX"))

        # Check only managed attachments exist
        attachments = (yield event.component()).mainComponent().properties("ATTACH")
        dropbox_count = 0
        managed_count = 0
        for attach in attachments:
            if attach.hasParameter("MANAGED-ID"):
                managed_count += 1
            else:
                dropbox_count += 1
                self.assertTrue(attach.value().find("/dropbox/") != -1)
                self.assertTrue(any([attach.value().endswith(filename) for filename in filenames]))
        self.assertEqual(managed_count, 0)
        self.assertEqual(dropbox_count, len(filenames))
        yield txn.commit()


    @inlineCallbacks
    def test_loadCalendarObjectsForDropboxID(self):
        """
        Test L{txdav.caldav.datastore.sql.CalendarStore._loadCalendarObjectsForDropboxID} returns the right set of
        calendar objects.
        """
        txn = self._sqlCalendarStore.newTransaction()
        calstore = CalendarStoreFeatures(self._sqlCalendarStore)

        for dropbox_id, result_count, result_names  in (
            ("1.2", 1, ("1.2.ics",)),
            ("1.3", 2, ("1.3.ics", "2-2.3.ics",)),
            ("1.4", 4, ("1.4.ics", "1.5.ics", "2-3.2.ics", "2-3.3.ics",)),
            ("2.2", 1, ("2-2.2.ics",)),
        ):
            cobjs = (yield calstore._loadCalendarObjectsForDropboxID(txn, "%s.dropbox" % (dropbox_id,)))
            self.assertEqual(len(cobjs), result_count, "Failed count with dropbox id: %s" % (dropbox_id,))
            names = set([cobj.name() for cobj in cobjs])
            self.assertEqual(names, set(result_names), "Failed names with dropbox id: %s" % (dropbox_id,))


    @inlineCallbacks
    def test_convertToManaged(self):
        """
        Test L{txdav.caldav.datastore.sql.DropboxAttachment.convertToManaged} converts properly to a ManagedAttachment.
        """
        yield self._addAttachment("home1", "calendar1", "1.2.ics", "1.2", "attach_1_2.txt")

        txn = self._sqlCalendarStore.newTransaction()

        dattachment = (yield DropBoxAttachment.load(txn, "1.2.dropbox", "attach_1_2.txt"))
        self.assertNotEqual(dattachment, None)
        self.assertTrue(dattachment._path.exists())
        mattachment = (yield dattachment.convertToManaged())
        self.assertNotEqual(mattachment, None)
        yield txn.commit()
        self.assertFalse(dattachment._path.exists())
        self.assertTrue(mattachment._path.exists())

        # Dropbox attachment gone
        txn = self._sqlCalendarStore.newTransaction()
        dattachment2 = (yield DropBoxAttachment.load(txn, "1.2", "attach_1_2.txt"))
        self.assertEqual(dattachment2, None)

        # Managed attachment present
        txn = self._sqlCalendarStore.newTransaction()
        mattachment2 = (yield ManagedAttachment.load(txn, None, attachmentID=dattachment._attachmentID))
        self.assertNotEqual(mattachment2, None)
        self.assertTrue(mattachment2.isManaged())


    @inlineCallbacks
    def test_newReference(self):
        """
        Test L{txdav.caldav.datastore.sql.ManagedAttachment.newReference} creates a new managed attachment reference.
        """
        yield self._addAttachment("home1", "calendar1", "1.4.ics", "1.4", "attach_1_4.txt")

        txn = self._sqlCalendarStore.newTransaction()

        home = (yield txn.calendarHomeWithUID("home1"))
        calendar = (yield home.calendarWithName("calendar1"))
        event4 = (yield calendar.calendarObjectWithName("1.4.ics"))
        event5 = (yield calendar.calendarObjectWithName("1.5.ics"))

        dattachment = (yield DropBoxAttachment.load(txn, "1.4.dropbox", "attach_1_4.txt"))
        self.assertNotEqual(dattachment, None)
        self.assertTrue(dattachment._path.exists())
        mattachment = (yield dattachment.convertToManaged())
        self.assertNotEqual(mattachment, None)
        self.assertEqual(mattachment.managedID(), None)

        mnew4 = (yield mattachment.newReference(event4._resourceID))
        self.assertNotEqual(mnew4, None)
        self.assertNotEqual(mnew4.managedID(), None)

        mnew5 = (yield mattachment.newReference(event5._resourceID))
        self.assertNotEqual(mnew5, None)
        self.assertNotEqual(mnew5.managedID(), None)

        yield txn.commit()

        # Managed attachment present
        txn = self._sqlCalendarStore.newTransaction()
        mtest4 = (yield ManagedAttachment.load(txn, mnew4.managedID()))
        self.assertNotEqual(mtest4, None)
        self.assertTrue(mtest4.isManaged())
        self.assertEqual(mtest4._objectResourceID, event4._resourceID)
        yield txn.commit()

        # Managed attachment present
        txn = self._sqlCalendarStore.newTransaction()
        mtest5 = (yield ManagedAttachment.load(txn, mnew5.managedID()))
        self.assertNotEqual(mtest5, None)
        self.assertTrue(mtest5.isManaged())
        self.assertEqual(mtest5._objectResourceID, event5._resourceID)
        yield txn.commit()


    @inlineCallbacks
    def test_convertAttachments(self):
        """
        Test L{txdav.caldav.datastore.sql.CalendarObject.convertAttachments} re-writes calendar data.
        """
        yield self._addAttachment("home1", "calendar1", "1.2.ics", "1.2", "attach_1_2_1.txt")
        yield self._addAttachment("home1", "calendar1", "1.2.ics", "1.2", "attach_1_2_2.txt")

        txn = self._sqlCalendarStore.newTransaction()

        home = (yield txn.calendarHomeWithUID("home1"))
        calendar = (yield home.calendarWithName("calendar1"))
        event = (yield calendar.calendarObjectWithName("1.2.ics"))

        # Check that dropbox ATTACH exists
        attachments = (yield event.component()).mainComponent().properties("ATTACH")
        for attach in attachments:
            self.assertTrue(attach.value().find("1.2.dropbox") != -1)
            self.assertTrue(attach.value().endswith("attach_1_2_1.txt") or attach.value().endswith("attach_1_2_2.txt"))
            self.assertFalse(attach.value().find("MANAGED-ID") != -1)

        dattachment = (yield DropBoxAttachment.load(txn, "1.2.dropbox", "attach_1_2_1.txt"))
        mattachment = (yield dattachment.convertToManaged())
        mnew = (yield mattachment.newReference(event._resourceID))
        yield event.convertAttachments(dattachment, mnew)
        yield txn.commit()

        txn = self._sqlCalendarStore.newTransaction()

        home = (yield txn.calendarHomeWithUID("home1"))
        calendar = (yield home.calendarWithName("calendar1"))
        event = (yield calendar.calendarObjectWithName("1.2.ics"))
        component = (yield event.component()).mainComponent()

        # Still has X-APPLE-DROPBOX
        self.assertTrue(component.hasProperty("X-APPLE-DROPBOX"))

        # Check that one managed-id and one dropbox ATTACH exist
        attachments = (yield event.component()).mainComponent().properties("ATTACH")
        dropbox_count = 0
        managed_count = 0
        for attach in attachments:
            if attach.hasParameter("MANAGED-ID"):
                managed_count += 1
                self.assertTrue(attach.value().find("1.2.dropbox") == -1)
                self.assertEqual(attach.parameterValue("MANAGED-ID"), mnew.managedID())
                self.assertEqual(attach.parameterValue("FILENAME"), mnew.name())
            else:
                dropbox_count += 1
                self.assertTrue(attach.value().find("1.2.dropbox") != -1)
                self.assertTrue(attach.value().endswith("attach_1_2_2.txt"))
        self.assertEqual(managed_count, 1)
        self.assertEqual(dropbox_count, 1)
        yield txn.commit()

        # Convert the second dropbox attachment
        txn = self._sqlCalendarStore.newTransaction()
        home = (yield txn.calendarHomeWithUID("home1"))
        calendar = (yield home.calendarWithName("calendar1"))
        event = (yield calendar.calendarObjectWithName("1.2.ics"))
        dattachment = (yield DropBoxAttachment.load(txn, "1.2.dropbox", "attach_1_2_2.txt"))
        mattachment = (yield dattachment.convertToManaged())
        mnew = (yield mattachment.newReference(event._resourceID))
        yield event.convertAttachments(dattachment, mnew)
        yield txn.commit()

        txn = self._sqlCalendarStore.newTransaction()
        home = (yield txn.calendarHomeWithUID("home1"))
        calendar = (yield home.calendarWithName("calendar1"))
        event = (yield calendar.calendarObjectWithName("1.2.ics"))
        component = (yield event.component()).mainComponent()

        # No more X-APPLE-DROPBOX
        self.assertFalse(component.hasProperty("X-APPLE-DROPBOX"))

        # Check that one managed-id and one dropbox ATTACH exist
        attachments = (yield event.component()).mainComponent().properties("ATTACH")
        dropbox_count = 0
        managed_count = 0
        for attach in attachments:
            if attach.hasParameter("MANAGED-ID"):
                managed_count += 1
                self.assertTrue(attach.value().find("1.2.dropbox") == -1)
                self.assertTrue(attach.parameterValue("FILENAME") in ("attach_1_2_1.txt", "attach_1_2_2.txt"))
            else:
                dropbox_count += 1
        self.assertEqual(managed_count, 2)
        self.assertEqual(dropbox_count, 0)
        yield txn.commit()


    @inlineCallbacks
    def test_upgradeDropbox_oneEvent(self):
        """
        Test L{txdav.caldav.datastore.sql.CalendarStoreFeatures._upgradeDropbox} re-writes calendar data
        for one event with an attachment.
        """

        yield self._addAllAttachments()

        txn = self._sqlCalendarStore.newTransaction()
        calstore = CalendarStoreFeatures(self._sqlCalendarStore)
        yield calstore._upgradeDropbox(txn, "1.2.dropbox")
        yield txn.commit()

        yield self._verifyConversion("home1", "calendar1", "1.2.ics", ("attach_1_2_1.txt", "attach_1_2_2.txt",))
        yield self._verifyNoConversion("home1", "calendar1", "1.3.ics", ("attach_1_3.txt",))
        yield self._verifyNoConversion("home1", "calendar1", "1.4.ics", ("attach_1_4.txt",))
        yield self._verifyNoConversion("home1", "calendar1", "1.5.ics", ("attach_1_4.txt",))
        yield self._verifyNoConversion("home2", "calendar2", "2-2.2.ics", ("attach_2_2.txt",))
        yield self._verifyNoConversion("home2", "calendar2", "2-2.3.ics", ("attach_1_3.txt",))
        yield self._verifyNoConversion("home2", "calendar3", "2-3.2.ics", ("attach_1_4.txt",))
        yield self._verifyNoConversion("home2", "calendar3", "2-3.3.ics", ("attach_1_4.txt",))


    @inlineCallbacks
    def test_upgradeDropbox_oneEventTwoHomes(self):
        """
        Test L{txdav.caldav.datastore.sql.CalendarStoreFeatures._upgradeDropbox} re-writes calendar data
        for multiple events across different homes with the same attachment.
        """

        yield self._addAllAttachments()

        txn = self._sqlCalendarStore.newTransaction()
        calstore = CalendarStoreFeatures(self._sqlCalendarStore)
        yield calstore._upgradeDropbox(txn, "1.3.dropbox")
        yield txn.commit()

        yield self._verifyNoConversion("home1", "calendar1", "1.2.ics", ("attach_1_2_1.txt", "attach_1_2_2.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.3.ics", ("attach_1_3.txt",))
        yield self._verifyNoConversion("home1", "calendar1", "1.4.ics", ("attach_1_4.txt",))
        yield self._verifyNoConversion("home1", "calendar1", "1.5.ics", ("attach_1_4.txt",))
        yield self._verifyNoConversion("home2", "calendar2", "2-2.2.ics", ("attach_2_2.txt",))
        yield self._verifyConversion("home2", "calendar2", "2-2.3.ics", ("attach_1_3.txt",))
        yield self._verifyNoConversion("home2", "calendar3", "2-3.2.ics", ("attach_1_4.txt",))
        yield self._verifyNoConversion("home2", "calendar3", "2-3.3.ics", ("attach_1_4.txt",))


    @inlineCallbacks
    def test_upgradeDropbox_twoEventsTwoHomes(self):
        """
        Test L{txdav.caldav.datastore.sql.CalendarStoreFeatures._upgradeDropbox} re-writes calendar data
        for multiple events across different homes with the same attachment.
        """

        yield self._addAllAttachments()

        txn = self._sqlCalendarStore.newTransaction()
        calstore = CalendarStoreFeatures(self._sqlCalendarStore)
        yield calstore._upgradeDropbox(txn, "1.4.dropbox")
        yield txn.commit()

        yield self._verifyNoConversion("home1", "calendar1", "1.2.ics", ("attach_1_2_1.txt", "attach_1_2_2.txt",))
        yield self._verifyNoConversion("home1", "calendar1", "1.3.ics", ("attach_1_3.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.4.ics", ("attach_1_4.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.5.ics", ("attach_1_4.txt",))
        yield self._verifyNoConversion("home2", "calendar2", "2-2.2.ics", ("attach_2_2.txt",))
        yield self._verifyNoConversion("home2", "calendar2", "2-2.3.ics", ("attach_1_3.txt",))
        yield self._verifyConversion("home2", "calendar3", "2-3.2.ics", ("attach_1_4.txt",))
        yield self._verifyConversion("home2", "calendar3", "2-3.3.ics", ("attach_1_4.txt",))


    @inlineCallbacks
    def test_upgradeToManagedAttachments(self):
        """
        Test L{txdav.caldav.datastore.sql.CalendarStoreFeatures.upgradeToManagedAttachments} re-writes calendar data
        for all events with an attachment.
        """

        yield self._addAllAttachments()

        txn = self._sqlCalendarStore.newTransaction()
        calstore = CalendarStoreFeatures(self._sqlCalendarStore)
        yield calstore.upgradeToManagedAttachments(txn, 2)
        yield txn.commit()

        yield self._verifyConversion("home1", "calendar1", "1.2.ics", ("attach_1_2_1.txt", "attach_1_2_2.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.3.ics", ("attach_1_3.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.4.ics", ("attach_1_4.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.5.ics", ("attach_1_4.txt",))
        yield self._verifyConversion("home2", "calendar2", "2-2.2.ics", ("attach_2_2.txt",))
        yield self._verifyConversion("home2", "calendar2", "2-2.3.ics", ("attach_1_3.txt",))
        yield self._verifyConversion("home2", "calendar3", "2-3.2.ics", ("attach_1_4.txt",))
        yield self._verifyConversion("home2", "calendar3", "2-3.3.ics", ("attach_1_4.txt",))
