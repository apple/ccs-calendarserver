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

from calendarserver.tap.util import directoryFromConfig

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.value import PyCalendarValue

from twext.enterprise.dal.syntax import Delete
from twext.python.clsprop import classproperty
from twext.web2.http_headers import MimeType
from twext.web2.stream import MemoryStream

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.filepath import FilePath
from twisted.trial import unittest

from twistedcaldav.config import config
from twistedcaldav.ical import Property, Component

from txdav.caldav.datastore.sql import CalendarStoreFeatures, DropBoxAttachment, \
    ManagedAttachment
from txdav.caldav.datastore.test.common import CaptureProtocol
from txdav.caldav.datastore.test.util import buildCalendarStore
from txdav.caldav.icalendarstore import IAttachmentStorageTransport, IAttachment, \
    QuotaExceeded
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.test.util import CommonCommonTests, \
    populateCalendarsFrom, deriveQuota, withSpecialQuota

import hashlib
import os

"""
Tests for txdav.caldav.datastore.sql attachment handling.
"""

storePath = FilePath(__file__).parent().child("calendar_store")
homeRoot = storePath.child("ho").child("me").child("home1")
cal1Root = homeRoot.child("calendar_1")

calendar1_objectNames = [
    "1.ics",
    "2.ics",
    "3.ics",
    "4.ics",
]

home1_calendarNames = [
    "calendar_1",
]


class AttachmentTests(CommonCommonTests, unittest.TestCase):

    metadata1 = {
        "accessMode": "PUBLIC",
        "isScheduleObject": True,
        "scheduleTag": "abc",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }
    metadata2 = {
        "accessMode": "PRIVATE",
        "isScheduleObject": False,
        "scheduleTag": "",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }
    metadata3 = {
        "accessMode": "PUBLIC",
        "isScheduleObject": None,
        "scheduleTag": "abc",
        "scheduleEtags": (),
        "hasPrivateComment": True,
    }
    metadata4 = {
        "accessMode": "PUBLIC",
        "isScheduleObject": True,
        "scheduleTag": "abc4",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }


    @inlineCallbacks
    def setUp(self):
        yield super(AttachmentTests, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        metadata1 = cls.metadata1.copy()
        metadata2 = cls.metadata2.copy()
        metadata3 = cls.metadata3.copy()
        metadata4 = cls.metadata4.copy()
        return {
        "home1": {
            "calendar_1": {
                "1.ics": (cal1Root.child("1.ics").getContent(), metadata1),
                "2.ics": (cal1Root.child("2.ics").getContent(), metadata2),
                "3.ics": (cal1Root.child("3.ics").getContent(), metadata3),
                "4.ics": (cal1Root.child("4.ics").getContent(), metadata4),
            },
        },
    }


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore



class DropBoxAttachmentTests(AttachmentTests):

    eventWithDropbox = "\r\n".join("""
BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VTIMEZONE
LAST-MODIFIED:20040110T032845Z
TZID:US/Eastern
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20060101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:user01
ATTENDEE;PARTSTAT=ACCEPTED:user01
ATTACH;VALUE=URI:/calendars/users/home1/some-dropbox-id/some-dropbox-id/caldavd.plist
X-APPLE-DROPBOX:/calendars/users/home1/dropbox/some-dropbox-id
END:VEVENT
END:VCALENDAR
    """.strip().split("\n"))


    @inlineCallbacks
    def setUp(self):
        yield super(DropBoxAttachmentTests, self).setUp()

        # Need to tweak config and settings to setup dropbox to work
        self.patch(config, "EnableDropBox", True)
        self.patch(config, "EnableManagedAttachments", False)
        self._sqlCalendarStore.enableManagedAttachments = False

        txn = self._sqlCalendarStore.newTransaction()
        cs = schema.CALENDARSERVER
        yield Delete(
            From=cs,
            Where=cs.NAME == "MANAGED-ATTACHMENTS"
        ).on(txn)
        yield txn.commit()


    @inlineCallbacks
    def createAttachmentTest(self, refresh):
        """
        Common logic for attachment-creation tests.
        """
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createAttachmentWithName(
            "new.attachment",
        )
        t = attachment.store(MimeType("text", "x-fixture"), "")
        self.assertProvides(IAttachmentStorageTransport, t)
        t.write("new attachment")
        t.write(" text")
        yield t.loseConnection()
        obj = yield refresh(obj)
        attachment = yield obj.attachmentWithName("new.attachment")
        self.assertProvides(IAttachment, attachment)
        data = yield self.attachmentToString(attachment)
        self.assertEquals(data, "new attachment text")
        contentType = attachment.contentType()
        self.assertIsInstance(contentType, MimeType)
        self.assertEquals(contentType, MimeType("text", "x-fixture"))
        self.assertEquals(attachment.md5(), '50a9f27aeed9247a0833f30a631f1858')
        self.assertEquals(
            [_attachment.name() for _attachment in (yield obj.attachments())],
            ['new.attachment']
        )


    @inlineCallbacks
    def stringToAttachment(self, obj, name, contents,
                           mimeType=MimeType("text", "x-fixture")):
        """
        Convenience for producing an attachment from a calendar object.

        @param obj: the calendar object which owns the dropbox associated with
            the to-be-created attachment.

        @param name: the (utf-8 encoded) name to create the attachment with.

        @type name: C{bytes}

        @param contents: the desired contents of the new attachment.

        @type contents: C{bytes}

        @param mimeType: the mime type of the incoming bytes.

        @return: a L{Deferred} that fires with the L{IAttachment} that is
            created, once all the bytes have been stored.
        """
        att = yield obj.createAttachmentWithName(name)
        t = att.store(mimeType, "")
        t.write(contents)
        yield t.loseConnection()
        returnValue(att)


    def attachmentToString(self, attachment):
        """
        Convenience to convert an L{IAttachment} to a string.

        @param attachment: an L{IAttachment} provider to convert into a string.

        @return: a L{Deferred} that fires with the contents of the attachment.

        @rtype: L{Deferred} firing C{bytes}
        """
        capture = CaptureProtocol()
        attachment.retrieve(capture)
        return capture.deferred


    @inlineCallbacks
    def test_attachmentPath(self):
        """
        L{ICalendarObject.createAttachmentWithName} will store an
        L{IAttachment} object that can be retrieved by
        L{ICalendarObject.attachmentWithName}.
        """
        yield self.createAttachmentTest(lambda x: x)
        attachmentRoot = (
            yield self.calendarObjectUnderTest()
        )._txn._store.attachmentsPath
        obj = yield self.calendarObjectUnderTest()
        hasheduid = hashlib.md5(obj._dropboxID).hexdigest()
        attachmentPath = attachmentRoot.child(
            hasheduid[0:2]).child(hasheduid[2:4]).child(hasheduid).child(
                "new.attachment")
        self.assertTrue(attachmentPath.isfile())


    @inlineCallbacks
    def test_dropboxID(self):
        """
        L{ICalendarObject.dropboxID} should synthesize its dropbox from the X
        -APPLE-DROPBOX property, if available.
        """
        cal = yield self.calendarUnderTest()
        yield cal.createCalendarObjectWithName("drop.ics", Component.fromString(
                self.eventWithDropbox
            )
        )
        obj = yield cal.calendarObjectWithName("drop.ics")
        self.assertEquals((yield obj.dropboxID()), "some-dropbox-id")


    @inlineCallbacks
    def test_dropboxIDs(self):
        """
        L{ICalendarObject.getAllDropboxIDs} returns a L{Deferred} that fires
        with a C{list} of all Dropbox IDs.
        """
        home = yield self.homeUnderTest()
        # The only item in the home which has an ATTACH or X-APPLE-DROPBOX
        # property.
        allDropboxIDs = set([
            u'FE5CDC6F-7776-4607-83A9-B90FF7ACC8D0.dropbox',
        ])
        self.assertEquals(set((yield home.getAllDropboxIDs())),
                          allDropboxIDs)


    @inlineCallbacks
    def test_indexByDropboxProperty(self):
        """
        L{ICalendarHome.calendarObjectWithDropboxID} will return a calendar
        object in the calendar home with the given final segment in its C{X
        -APPLE-DROPBOX} property URI.
        """
        objName = "with-dropbox.ics"
        cal = yield self.calendarUnderTest()
        yield cal.createCalendarObjectWithName(
            objName, Component.fromString(
                self.eventWithDropbox
            )
        )
        yield self.commit()
        home = yield self.homeUnderTest()
        cal = yield self.calendarUnderTest()
        fromName = yield cal.calendarObjectWithName(objName)
        fromDropbox = yield home.calendarObjectWithDropboxID("some-dropbox-id")
        self.assertEquals(fromName, fromDropbox)


    @inlineCallbacks
    def test_twoAttachmentsWithTheSameName(self):
        """
        Attachments are uniquely identified by their associated object and path;
        two attachments with the same name won't overwrite each other.
        """
        obj = yield self.calendarObjectUnderTest()
        obj2 = yield self.calendarObjectUnderTest(name="2.ics")
        att1 = yield self.stringToAttachment(obj, "sample.attachment",
                                             "test data 1")
        att2 = yield self.stringToAttachment(obj2, "sample.attachment",
                                             "test data 2")
        data1 = yield self.attachmentToString(att1)
        data2 = yield self.attachmentToString(att2)
        self.assertEquals(data1, "test data 1")
        self.assertEquals(data2, "test data 2")


    def test_createAttachment(self):
        """
        L{ICalendarObject.createAttachmentWithName} will store an
        L{IAttachment} object that can be retrieved by
        L{ICalendarObject.attachmentWithName}.
        """
        return self.createAttachmentTest(lambda x: x)


    def test_createAttachmentCommit(self):
        """
        L{ICalendarObject.createAttachmentWithName} will store an
        L{IAttachment} object that can be retrieved by
        L{ICalendarObject.attachmentWithName} in subsequent transactions.
        """
        @inlineCallbacks
        def refresh(obj):
            yield self.commit()
            result = yield self.calendarObjectUnderTest()
            returnValue(result)
        return self.createAttachmentTest(refresh)


    @inlineCallbacks
    def test_attachmentTemporaryFileCleanup(self):
        """
        L{IAttachmentStream} object cleans-up its temporary file on txn abort.
        """
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createAttachmentWithName(
            "new.attachment",
        )
        t = attachment.store(MimeType("text", "x-fixture"))

        temp = t._path.path

        yield self.abort()

        self.assertFalse(os.path.exists(temp))

        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createAttachmentWithName(
            "new.attachment",
        )
        t = attachment.store(MimeType("text", "x-fixture"))

        temp = t._path.path
        os.remove(temp)

        yield self.abort()

        self.assertFalse(os.path.exists(temp))


    @inlineCallbacks
    def test_quotaAllowedBytes(self):
        """
        L{ICalendarHome.quotaAllowedBytes} should return the configuration value
        passed to the calendar store's constructor.
        """
        expected = deriveQuota(self)
        home = yield self.homeUnderTest()
        actual = home.quotaAllowedBytes()
        self.assertEquals(expected, actual)


    @withSpecialQuota(None)
    @inlineCallbacks
    def test_quotaUnlimited(self):
        """
        When L{ICalendarHome.quotaAllowedBytes} returns C{None}, quota is
        unlimited; any sized attachment can be stored.
        """
        home = yield self.homeUnderTest()
        allowed = home.quotaAllowedBytes()
        self.assertIdentical(allowed, None)
        yield self.test_createAttachment()


    @inlineCallbacks
    def test_quotaTransportAddress(self):
        """
        Since L{IAttachmentStorageTransport} is a subinterface of L{ITransport},
        it must provide peer and host addresses.
        """
        obj = yield self.calendarObjectUnderTest()
        name = 'a-fun-attachment'
        attachment = yield obj.createAttachmentWithName(name)
        transport = attachment.store(MimeType("test", "x-something"), "")
        peer = transport.getPeer()
        host = transport.getHost()
        self.assertIdentical(peer.attachment, attachment)
        self.assertIdentical(host.attachment, attachment)
        self.assertIn(name, repr(peer))
        self.assertIn(name, repr(host))


    @inlineCallbacks
    def exceedQuotaTest(self, getit):
        """
        If too many bytes are passed to the transport returned by
        L{ICalendarObject.createAttachmentWithName},
        L{IAttachmentStorageTransport.loseConnection} will return a L{Deferred}
        that fails with L{QuotaExceeded}.
        """
        home = yield self.homeUnderTest()
        attachment = yield getit()
        t = attachment.store(MimeType("text", "x-fixture"), "")
        sample = "all work and no play makes jack a dull boy"
        chunk = (sample * (home.quotaAllowedBytes() / len(sample)))

        t.write(chunk)
        t.writeSequence([chunk, chunk])

        d = t.loseConnection()
        yield self.failUnlessFailure(d, QuotaExceeded)


    @inlineCallbacks
    def test_exceedQuotaNew(self):
        """
        When quota is exceeded on a new attachment, that attachment will no
        longer exist.
        """
        obj = yield self.calendarObjectUnderTest()
        yield self.exceedQuotaTest(
            lambda: obj.createAttachmentWithName("too-big.attachment")
        )
        self.assertEquals((yield obj.attachments()), [])
        yield self.commit()
        obj = yield self.calendarObjectUnderTest()
        self.assertEquals((yield obj.attachments()), [])


    @inlineCallbacks
    def test_exceedQuotaReplace(self):
        """
        When quota is exceeded while replacing an attachment, that attachment's
        contents will not be replaced.
        """
        obj = yield self.calendarObjectUnderTest()
        create = lambda: obj.createAttachmentWithName("exists.attachment")
        get = lambda: obj.attachmentWithName("exists.attachment")
        attachment = yield create()
        t = attachment.store(MimeType("text", "x-fixture"), "")
        sampleData = "a reasonably sized attachment"
        t.write(sampleData)
        yield t.loseConnection()
        yield self.exceedQuotaTest(get)
        @inlineCallbacks
        def checkOriginal():
            actual = yield self.attachmentToString(attachment)
            expected = sampleData
            # note: 60 is less than len(expected); trimming is just to make
            # the error message look sane when the test fails.
            actual = actual[:60]
            self.assertEquals(actual, expected)
        yield checkOriginal()
        yield self.commit()
        # Make sure that things go back to normal after a commit of that
        # transaction.
        obj = yield self.calendarObjectUnderTest()
        attachment = yield get()
        yield checkOriginal()


    def test_removeAttachmentWithName(self, refresh=lambda x: x):
        """
        L{ICalendarObject.removeAttachmentWithName} will remove the calendar
        object with the given name.
        """
        @inlineCallbacks
        def deleteIt(ignored):
            obj = yield self.calendarObjectUnderTest()
            yield obj.removeAttachmentWithName("new.attachment")
            obj = yield refresh(obj)
            self.assertIdentical(
                None, (yield obj.attachmentWithName("new.attachment"))
            )
            self.assertEquals(list((yield obj.attachments())), [])
        return self.test_createAttachmentCommit().addCallback(deleteIt)


    def test_removeAttachmentWithNameCommit(self):
        """
        L{ICalendarObject.removeAttachmentWithName} will remove the calendar
        object with the given name.  (After commit, it will still be gone.)
        """
        @inlineCallbacks
        def refresh(obj):
            yield self.commit()
            result = yield self.calendarObjectUnderTest()
            returnValue(result)
        return self.test_removeAttachmentWithName(refresh)


    @inlineCallbacks
    def test_noDropboxCalendar(self):
        """
        L{ICalendarObject.createAttachmentWithName} may create a directory
        named 'dropbox', but this should not be seen as a calendar by
        L{ICalendarHome.calendarWithName} or L{ICalendarHome.calendars}.
        """
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createAttachmentWithName(
            "new.attachment",
        )
        t = attachment.store(MimeType("text", "plain"), "")
        t.write("new attachment text")
        yield t.loseConnection()
        yield self.commit()
        home = (yield self.homeUnderTest())
        calendars = (yield home.calendars())
        self.assertEquals((yield home.calendarWithName("dropbox")), None)
        self.assertEquals(
            set([n.name() for n in calendars]),
            set(home1_calendarNames))


    @inlineCallbacks
    def test_cleanupAttachments(self):
        """
        L{ICalendarObject.remove} will remove an associated calendar
        attachment.
        """

        # Create attachment
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createAttachmentWithName(
            "new.attachment",
        )
        t = attachment.store(MimeType("text", "x-fixture"))
        t.write("new attachment")
        t.write(" text")
        yield t.loseConnection()
        apath = attachment._path.path
        yield self.commit()

        self.assertTrue(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertNotEqual(quota, 0)

        # Remove resource
        obj = yield self.calendarObjectUnderTest()
        yield obj.remove()
        yield self.commit()

        self.assertFalse(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertEqual(quota, 0)


    @inlineCallbacks
    def test_cleanupMultipleAttachments(self):
        """
        L{ICalendarObject.remove} will remove all associated calendar
        attachments.
        """

        # Create attachment
        obj = yield self.calendarObjectUnderTest()

        attachment = yield obj.createAttachmentWithName(
            "new.attachment",
        )
        t = attachment.store(MimeType("text", "x-fixture"))
        t.write("new attachment")
        t.write(" text")
        yield t.loseConnection()
        apath1 = attachment._path.path

        attachment = yield obj.createAttachmentWithName(
            "new.attachment2",
        )
        t = attachment.store(MimeType("text", "x-fixture"))
        t.write("new attachment 2")
        t.write(" text")
        yield t.loseConnection()
        apath2 = attachment._path.path

        yield self.commit()

        self.assertTrue(os.path.exists(apath1))
        self.assertTrue(os.path.exists(apath2))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertNotEqual(quota, 0)

        # Remove resource
        obj = yield self.calendarObjectUnderTest()
        yield obj.remove()
        yield self.commit()

        self.assertFalse(os.path.exists(apath1))
        self.assertFalse(os.path.exists(apath2))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertEqual(quota, 0)


    @inlineCallbacks
    def test_cleanupAttachmentsOnMultipleResources(self):
        """
        L{ICalendarObject.remove} will remove all associated calendar
        attachments unless used in another resource.
        """

        # Create attachment
        obj = yield self.calendarObjectUnderTest()

        attachment = yield obj.createAttachmentWithName(
            "new.attachment",
        )
        t = attachment.store(MimeType("text", "x-fixture"))
        t.write("new attachment")
        t.write(" text")
        yield t.loseConnection()
        apath = attachment._path.path

        new_component = """BEGIN:VCALENDAR
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
ATTENDEE;CN="Wilfredo Sanchez";CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailt
 o:wsanchez@example.com
ATTENDEE;CN="Cyrus Daboo";CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:cda
 boo@example.com
DTEND;TZID=US/Pacific:%(now)s0324T124500
TRANSP:OPAQUE
ORGANIZER;CN="Wilfredo Sanchez":mailto:wsanchez@example.com
UID:uid1-attachmenttest
DTSTAMP:20090326T145447Z
LOCATION:Wilfredo's Office
SEQUENCE:2
X-APPLE-EWS-BUSYSTATUS:BUSY
X-APPLE-DROPBOX:/calendars/__uids__/user01/dropbox/FE5CDC6F-7776-4607-83
 A9-B90FF7ACC8D0.dropbox
SUMMARY:CalDAV protocol updates
DTSTART;TZID=US/Pacific:%(now)s0324T121500
CREATED:20090326T145440Z
BEGIN:VALARM
X-WR-ALARMUID:DB39AB67-449C-441C-89D2-D740B5F41A73
TRIGGER;VALUE=DATE-TIME:%(now)s0324T180009Z
ACTION:AUDIO
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"now": 2012}

        calendar = yield self.calendarUnderTest()
        yield calendar.createCalendarObjectWithName(
            "test.ics", Component.fromString(new_component)
        )

        yield self.commit()

        self.assertTrue(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertNotEqual(quota, 0)

        # Remove resource
        obj = yield self.calendarObjectUnderTest()
        yield obj.remove()
        yield self.commit()

        self.assertTrue(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertNotEqual(quota, 0)

        # Remove resource
        obj = yield self.calendarObjectUnderTest(name="test.ics")
        yield obj.remove()
        yield self.commit()

        self.assertFalse(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertEqual(quota, 0)



class ManagedAttachmentTests(AttachmentTests):

    @inlineCallbacks
    def setUp(self):
        yield super(ManagedAttachmentTests, self).setUp()

        # Need to tweak config and settings to setup dropbox to work
        self.patch(config, "EnableDropBox", False)
        self.patch(config, "EnableManagedAttachments", True)
        self._sqlCalendarStore.enableManagedAttachments = True


    @inlineCallbacks
    def createAttachmentTest(self, refresh):
        """
        Common logic for attachment-creation tests.
        """
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createManagedAttachment()
        mid = attachment.managedID()
        t = attachment.store(MimeType("text", "x-fixture"), "new.attachment")
        self.assertProvides(IAttachmentStorageTransport, t)
        t.write("new attachment")
        t.write(" text")
        yield t.loseConnection()
        obj = yield refresh(obj)
        attachment = yield obj.attachmentWithManagedID(mid)
        self.assertProvides(IAttachment, attachment)
        data = yield self.attachmentToString(attachment)
        self.assertEquals(data, "new attachment text")
        contentType = attachment.contentType()
        self.assertIsInstance(contentType, MimeType)
        self.assertEquals(contentType, MimeType("text", "x-fixture"))
        self.assertEquals(attachment.md5(), '50a9f27aeed9247a0833f30a631f1858')
        self.assertEquals(
            (yield obj.managedAttachmentList()),
            ['new-%s.attachment' % (mid[:8],)]
        )

        returnValue(mid)


    @inlineCallbacks
    def stringToAttachment(self, obj, name, contents,
                           mimeType=MimeType("text", "x-fixture")):
        """
        Convenience for producing an attachment from a calendar object.

        @param obj: the calendar object which owns the dropbox associated with
            the to-be-created attachment.

        @param name: the (utf-8 encoded) name to create the attachment with.

        @type name: C{bytes}

        @param contents: the desired contents of the new attachment.

        @type contents: C{bytes}

        @param mimeType: the mime type of the incoming bytes.

        @return: a L{Deferred} that fires with the L{IAttachment} that is
            created, once all the bytes have been stored.
        """
        att = yield obj.createManagedAttachment()
        t = att.store(mimeType, name)
        t.write(contents)
        yield t.loseConnection()
        returnValue(att)


    def attachmentToString(self, attachment):
        """
        Convenience to convert an L{IAttachment} to a string.

        @param attachment: an L{IAttachment} provider to convert into a string.

        @return: a L{Deferred} that fires with the contents of the attachment.

        @rtype: L{Deferred} firing C{bytes}
        """
        capture = CaptureProtocol()
        attachment.retrieve(capture)
        return capture.deferred


    @inlineCallbacks
    def test_attachmentPath(self):
        """
        L{ICalendarObject.createManagedAttachment} will store an
        L{IAttachment} object that can be retrieved by
        L{ICalendarObject.attachmentWithManagedID}.
        """

        mid = yield self.createAttachmentTest(lambda x: x)
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.attachmentWithManagedID(mid)
        hasheduid = hashlib.md5(str(attachment._attachmentID)).hexdigest()

        attachmentRoot = (
            yield self.calendarObjectUnderTest()
        )._txn._store.attachmentsPath
        attachmentPath = attachmentRoot.child(
            hasheduid[0:2]).child(hasheduid[2:4]).child(hasheduid)
        self.assertTrue(attachmentPath.isfile())


    @inlineCallbacks
    def test_twoAttachmentsWithTheSameName(self):
        """
        Attachments are uniquely identified by their associated object and path;
        two attachments with the same name won't overwrite each other.
        """
        obj = yield self.calendarObjectUnderTest()
        obj2 = yield self.calendarObjectUnderTest(name="2.ics")
        att1 = yield self.stringToAttachment(obj, "sample.attachment",
                                             "test data 1")
        att2 = yield self.stringToAttachment(obj2, "sample.attachment",
                                             "test data 2")
        data1 = yield self.attachmentToString(att1)
        data2 = yield self.attachmentToString(att2)
        self.assertEquals(data1, "test data 1")
        self.assertEquals(data2, "test data 2")


    def test_createAttachment(self):
        """
        L{ICalendarObject.createManagedAttachment} will store an
        L{IAttachment} object that can be retrieved by
        L{ICalendarObject.attachmentWithManagedID}.
        """
        return self.createAttachmentTest(lambda x: x)


    def test_createAttachmentCommit(self):
        """
        L{ICalendarObject.createManagedAttachment} will store an
        L{IAttachment} object that can be retrieved by
        L{ICalendarObject.attachmentWithManagedID} in subsequent transactions.
        """
        @inlineCallbacks
        def refresh(obj):
            yield self.commit()
            result = yield self.calendarObjectUnderTest()
            returnValue(result)
        return self.createAttachmentTest(refresh)


    @inlineCallbacks
    def test_attachmentTemporaryFileCleanup(self):
        """
        L{IAttachmentStream} object cleans-up its temporary file on txn abort.
        """
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createManagedAttachment()
        t = attachment.store(MimeType("text", "x-fixture"), "new.attachment")

        temp = t._path.path

        yield self.abort()

        self.assertFalse(os.path.exists(temp))

        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createManagedAttachment()
        t = attachment.store(MimeType("text", "x-fixture"), "new.attachment")

        temp = t._path.path
        os.remove(temp)

        yield self.abort()

        self.assertFalse(os.path.exists(temp))


    @inlineCallbacks
    def test_quotaAllowedBytes(self):
        """
        L{ICalendarHome.quotaAllowedBytes} should return the configuration value
        passed to the calendar store's constructor.
        """
        expected = deriveQuota(self)
        home = yield self.homeUnderTest()
        actual = home.quotaAllowedBytes()
        self.assertEquals(expected, actual)


    @withSpecialQuota(None)
    @inlineCallbacks
    def test_quotaUnlimited(self):
        """
        When L{ICalendarHome.quotaAllowedBytes} returns C{None}, quota is
        unlimited; any sized attachment can be stored.
        """
        home = yield self.homeUnderTest()
        allowed = home.quotaAllowedBytes()
        self.assertIdentical(allowed, None)
        yield self.test_createAttachment()


    @inlineCallbacks
    def test_quotaTransportAddress(self):
        """
        Since L{IAttachmentStorageTransport} is a subinterface of L{ITransport},
        it must provide peer and host addresses.
        """
        obj = yield self.calendarObjectUnderTest()
        name = 'a-fun-attachment'
        attachment = yield obj.createManagedAttachment()
        transport = attachment.store(MimeType("test", "x-something"), name)
        peer = transport.getPeer()
        host = transport.getHost()
        self.assertIdentical(peer.attachment, attachment)
        self.assertIdentical(host.attachment, attachment)
        self.assertIn(name, repr(peer))
        self.assertIn(name, repr(host))


    @inlineCallbacks
    def exceedQuotaTest(self, getit, name):
        """
        If too many bytes are passed to the transport returned by
        L{ICalendarObject.createManagedAttachment},
        L{IAttachmentStorageTransport.loseConnection} will return a L{Deferred}
        that fails with L{QuotaExceeded}.
        """
        home = yield self.homeUnderTest()
        attachment = yield getit()
        t = attachment.store(MimeType("text", "x-fixture"), name)
        sample = "all work and no play makes jack a dull boy"
        chunk = (sample * (home.quotaAllowedBytes() / len(sample)))

        t.write(chunk)
        t.writeSequence([chunk, chunk])

        d = t.loseConnection()
        yield self.failUnlessFailure(d, QuotaExceeded)


    @inlineCallbacks
    def test_exceedQuotaNew(self):
        """
        When quota is exceeded on a new attachment, that attachment will no
        longer exist.
        """
        obj = yield self.calendarObjectUnderTest()
        yield self.exceedQuotaTest(
            lambda: obj.createManagedAttachment(), "too-big.attachment"
        )
        self.assertEquals((yield obj.managedAttachmentList()), [])
        yield self.commit()
        obj = yield self.calendarObjectUnderTest()
        self.assertEquals((yield obj.managedAttachmentList()), [])


    @inlineCallbacks
    def test_exceedQuotaReplace(self):
        """
        When quota is exceeded while replacing an attachment, that attachment's
        contents will not be replaced.
        """
        obj = yield self.calendarObjectUnderTest()
        create = lambda: obj.createManagedAttachment()
        attachment = yield create()
        get = lambda: obj.attachmentWithManagedID(attachment.managedID())
        t = attachment.store(MimeType("text", "x-fixture"), "new.attachment")
        sampleData = "a reasonably sized attachment"
        t.write(sampleData)
        yield t.loseConnection()
        yield self.exceedQuotaTest(get, "exists.attachment")
        @inlineCallbacks
        def checkOriginal():
            actual = yield self.attachmentToString(attachment)
            expected = sampleData
            # note: 60 is less than len(expected); trimming is just to make
            # the error message look sane when the test fails.
            actual = actual[:60]
            self.assertEquals(actual, expected)
        yield checkOriginal()
        yield self.commit()
        # Make sure that things go back to normal after a commit of that
        # transaction.
        obj = yield self.calendarObjectUnderTest()
        attachment = yield get()
        yield checkOriginal()


    def test_removeManagedAttachmentWithID(self, refresh=lambda x: x):
        """
        L{ICalendarObject.removeManagedAttachmentWithID} will remove the calendar
        object with the given managed-id.
        """
        @inlineCallbacks
        def deleteIt(mid):
            obj = yield self.calendarObjectUnderTest()
            yield obj.removeManagedAttachmentWithID(mid)
            obj = yield refresh(obj)
            self.assertIdentical(
                None, (yield obj.attachmentWithManagedID(mid))
            )
            self.assertEquals(list((yield obj.managedAttachmentList())), [])
        return self.test_createAttachmentCommit().addCallback(deleteIt)


    def test_removeManagedAttachmentWithIDCommit(self):
        """
        L{ICalendarObject.removeManagedAttachmentWithID} will remove the calendar
        object with the given managed-id.  (After commit, it will still be gone.)
        """
        @inlineCallbacks
        def refresh(obj):
            yield self.commit()
            result = yield self.calendarObjectUnderTest()
            returnValue(result)
        return self.test_removeManagedAttachmentWithID(refresh)


    @inlineCallbacks
    def test_noDropboxCalendar(self):
        """
        L{ICalendarObject.createManagedAttachment} may create a directory
        named 'dropbox', but this should not be seen as a calendar by
        L{ICalendarHome.calendarWithName} or L{ICalendarHome.calendars}.
        """
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createManagedAttachment()
        t = attachment.store(MimeType("text", "plain"), "new.attachment")
        t.write("new attachment text")
        yield t.loseConnection()
        yield self.commit()
        home = (yield self.homeUnderTest())
        calendars = (yield home.calendars())
        self.assertEquals((yield home.calendarWithName("dropbox")), None)
        self.assertEquals(
            set([n.name() for n in calendars]),
            set(home1_calendarNames))


    @inlineCallbacks
    def test_cleanupAttachments(self):
        """
        L{ICalendarObject.remove} will remove an associated calendar
        attachment.
        """

        # Create attachment
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createManagedAttachment()
        t = attachment.store(MimeType("text", "x-fixture"), "new.attachment")
        t.write("new attachment")
        t.write(" text")
        yield t.loseConnection()
        apath = attachment._path.path
        yield self.commit()

        self.assertTrue(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertNotEqual(quota, 0)

        # Remove resource
        obj = yield self.calendarObjectUnderTest()
        yield obj.remove()
        yield self.commit()

        self.assertFalse(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertEqual(quota, 0)


    @inlineCallbacks
    def test_cleanupMultipleAttachments(self):
        """
        L{ICalendarObject.remove} will remove all associated calendar
        attachments.
        """

        # Create attachment
        obj = yield self.calendarObjectUnderTest()

        attachment = yield obj.createManagedAttachment()
        t = attachment.store(MimeType("text", "x-fixture"), "new.attachment")
        t.write("new attachment")
        t.write(" text")
        yield t.loseConnection()
        apath1 = attachment._path.path

        attachment = yield obj.createManagedAttachment()
        t = attachment.store(MimeType("text", "x-fixture"), "new.attachment2")
        t.write("new attachment 2")
        t.write(" text")
        yield t.loseConnection()
        apath2 = attachment._path.path

        yield self.commit()

        self.assertTrue(os.path.exists(apath1))
        self.assertTrue(os.path.exists(apath2))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertNotEqual(quota, 0)

        # Remove resource
        obj = yield self.calendarObjectUnderTest()
        yield obj.remove()
        yield self.commit()

        self.assertFalse(os.path.exists(apath1))
        self.assertFalse(os.path.exists(apath2))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertEqual(quota, 0)


    @inlineCallbacks
    def test_cleanupAttachmentsOnMultipleResources(self):
        """
        L{ICalendarObject.remove} will remove all associated calendar
        attachments unless used in another resource.
        """

        # Create attachment
        obj = yield self.calendarObjectUnderTest()

        attachment, _ignore_location = yield obj.addAttachment(None, MimeType("text", "x-fixture"), "new.attachment", MemoryStream("new attachment text"))
        apath = attachment._path.path

        cdata = yield obj.componentForUser()
        newcdata = Component.fromString(str(cdata).replace("uid1", "uid1-attached"))
        calendar = yield self.calendarUnderTest()
        yield calendar.createCalendarObjectWithName("test.ics", newcdata)
        yield self.commit()

        self.assertTrue(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertNotEqual(quota, 0)

        # Remove resource
        obj = yield self.calendarObjectUnderTest()
        yield obj.remove()
        yield self.commit()

        self.assertTrue(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertNotEqual(quota, 0)

        # Remove resource
        obj = yield self.calendarObjectUnderTest(name="test.ics")
        yield obj.remove()
        yield self.commit()

        self.assertFalse(os.path.exists(apath))

        home = (yield self.transactionUnderTest().calendarHomeWithUID("home1"))
        quota = (yield home.quotaUsedBytes())
        yield self.commit()
        self.assertEqual(quota, 0)



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

        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory, directoryFromConfig(config))
        yield self.populate()

        self.paths = {}


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()

        txn = self._sqlCalendarStore.newTransaction()
        yield Delete(
            From=schema.ATTACHMENT,
            Where=None
        ).on(txn)
        yield Delete(
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

        self._sqlCalendarStore._dropbox_ok = True
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

        self.paths[name] = attachment._path

        cal = (yield event.componentForUser())
        cal.mainComponent().addProperty(Property(
            "ATTACH",
            "http://localhost/calendars/users/%s/dropbox/%s.dropbox/%s" % (home.name(), dropboxid, name,),
            valuetype=PyCalendarValue.VALUETYPE_URI
        ))
        yield event.setComponent(cal)
        yield txn.commit()
        self._sqlCalendarStore._dropbox_ok = False

        returnValue(attachment)


    @inlineCallbacks
    def _addAttachmentProperty(self, home, calendar, event, dropboxid, owner_home, name):

        txn = self._sqlCalendarStore.newTransaction()

        # Create an event with an attachment
        home = (yield txn.calendarHomeWithUID(home))
        calendar = (yield home.calendarWithName(calendar))
        event = (yield calendar.calendarObjectWithName(event))

        cal = (yield event.componentForUser())
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
        component = (yield event.componentForUser()).mainComponent()

        # No more X-APPLE-DROPBOX
        self.assertFalse(component.hasProperty("X-APPLE-DROPBOX"))

        # Check only managed attachments exist
        attachments = (yield event.componentForUser()).mainComponent().properties("ATTACH")
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
        component = (yield event.componentForUser()).mainComponent()

        # X-APPLE-DROPBOX present
        self.assertTrue(component.hasProperty("X-APPLE-DROPBOX"))

        # Check only managed attachments exist
        attachments = (yield event.componentForUser()).mainComponent().properties("ATTACH")
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
        mattachment2 = (yield ManagedAttachment.load(txn, None, None, attachmentID=dattachment._attachmentID))
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
        self.assertNotEqual(mattachment.managedID(), None)

        mnew4 = (yield mattachment.newReference(event4._resourceID))
        self.assertNotEqual(mnew4, None)
        self.assertEqual(mnew4.managedID(), mattachment.managedID())

        mnew5 = (yield mattachment.newReference(event5._resourceID))
        self.assertNotEqual(mnew5, None)
        self.assertEqual(mnew5.managedID(), mattachment.managedID())

        yield txn.commit()

        # Managed attachment present
        txn = self._sqlCalendarStore.newTransaction()
        mtest4 = (yield ManagedAttachment.load(txn, event4._resourceID, mnew4.managedID()))
        self.assertNotEqual(mtest4, None)
        self.assertTrue(mtest4.isManaged())
        self.assertEqual(mtest4._objectResourceID, event4._resourceID)
        yield txn.commit()

        # Managed attachment present
        txn = self._sqlCalendarStore.newTransaction()
        mtest5 = (yield ManagedAttachment.load(txn, event5._resourceID, mnew5.managedID()))
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
        attachments = (yield event.componentForUser()).mainComponent().properties("ATTACH")
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

        # Check that one managed-id and one dropbox ATTACH exist
        attachments = (yield event.componentForUser()).mainComponent().properties("ATTACH")
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
        component = (yield event.componentForUser()).mainComponent()

        # No more X-APPLE-DROPBOX
        self.assertFalse(component.hasProperty("X-APPLE-DROPBOX"))

        # Check that one managed-id and one dropbox ATTACH exist
        attachments = (yield event.componentForUser()).mainComponent().properties("ATTACH")
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

        calstore = CalendarStoreFeatures(self._sqlCalendarStore)
        yield calstore.upgradeToManagedAttachments(2)

        yield self._verifyConversion("home1", "calendar1", "1.2.ics", ("attach_1_2_1.txt", "attach_1_2_2.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.3.ics", ("attach_1_3.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.4.ics", ("attach_1_4.txt",))
        yield self._verifyConversion("home1", "calendar1", "1.5.ics", ("attach_1_4.txt",))
        yield self._verifyConversion("home2", "calendar2", "2-2.2.ics", ("attach_2_2.txt",))
        yield self._verifyConversion("home2", "calendar2", "2-2.3.ics", ("attach_1_3.txt",))
        yield self._verifyConversion("home2", "calendar3", "2-3.2.ics", ("attach_1_4.txt",))
        yield self._verifyConversion("home2", "calendar3", "2-3.3.ics", ("attach_1_4.txt",))

        # Paths do not exist
        for path in self.paths.values():
            for _ignore in range(4):
                self.assertFalse(path.exists(), msg="Still exists: %s" % (path,))
                path = path.parent()
