##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
from txdav.caldav.datastore.test.util import buildCalendarStore

"""
Tests for txdav.caldav.datastore.util.
"""

import textwrap

from twisted.trial.unittest import TestCase as BaseTestCase
from twext.web2.http_headers import MimeType

from twisted.internet.defer import inlineCallbacks

from twistedcaldav.ical import Component
from twistedcaldav.test.util import TestCase

from txdav.common.datastore.test.util import populateCalendarsFrom, CommonCommonTests

from txdav.caldav.datastore.util import dropboxIDFromCalendarObject, \
    StorageTransportBase, migrateHome

from txdav.common.icommondatastore import HomeChildNameAlreadyExistsError

class DropboxIDTests(TestCase):
    """
    Test dropbox ID extraction from calendar data.
    """

    class FakeCalendarResource(object):
        """
        Fake object resource to work with tests.
        """

        def __init__(self, data):

            self.ical = Component.fromString(data)

        def component(self):
            return self.ical

        def uid(self):
            return self.ical.resourceUID()


    @inlineCallbacks
    def test_noAttachOrXdash(self):
        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890.dropbox"
        )


    @inlineCallbacks
    def test_okXdash(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
X-APPLE-DROPBOX:http://example.com/calendars/__uids__/1234/dropbox/12345-67890X.dropbox
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890X.dropbox"
        )


    @inlineCallbacks
    def test_emptyXdash(self):
        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
X-APPLE-DROPBOX:
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals((yield dropboxIDFromCalendarObject(resource)), "12345-67890.dropbox")


    @inlineCallbacks
    def test_okAttach(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH;VALUE=URI:http://example.com/calendars/__uids__/1234/dropbox/12345-67890Y.dropbox/text.txt
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890Y.dropbox"
        )


    @inlineCallbacks
    def test_badAttach(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH;VALUE=URI:tag:bogus
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890.dropbox"
        )


    @inlineCallbacks
    def test_inlineAttach(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH:bmFzZTY0
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890.dropbox"
        )


    @inlineCallbacks
    def test_multipleAttach(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH;VALUE=URI:tag:bogus
ATTACH:bmFzZTY0
ATTACH;VALUE=URI:http://example.com/calendars/__uids__/1234/dropbox/12345-67890Z.dropbox/text.txt
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890Z.dropbox"
        )


    @inlineCallbacks
    def test_okAttachRecurring(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH;VALUE=URI:http://example.com/calendars/__uids__/1234/dropbox/12345-67890Y.dropbox/text.txt
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890Y.dropbox"
        )


    @inlineCallbacks
    def test_okAttachAlarm(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
BEGIN:VALARM
ACTION:AUDIO
ATTACH;VALUE=URI:Ping
TRIGGER:-PT15M
X-WR-ALARMUID:5548D654-8FDA-49DB-8983-8FCAD1F322B1
END:VALARM
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890.dropbox"
        )


    @inlineCallbacks
    def test_UIDbadPath(self):
        test_UIDs = (
            ("12345/67890", "12345-67890"),
            ("http://12345,67890", "12345,67890"),
            ("https://12345,67890", "12345,67890"),
            ("12345:67890", "1234567890"),
            ("12345.67890", "1234567890"),
            ("12345/6:7.890", "12345-67890"),
        )

        for uid, result in test_UIDs:
            resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:%s
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""" % (uid,))

            self.assertEquals(
                (yield dropboxIDFromCalendarObject(resource)),
                "%s.dropbox" % (result,),
            )



class StorageTransportTests(TestCase):

    def test_MissingContentType(self):

        test_files = (
            ("plain.txt", MimeType.fromString("text/plain"),),
            ("word.doc", MimeType.fromString("application/msword"),),
            ("markup.html", MimeType.fromString("text/html"),),
            ("octet", MimeType.fromString("application/octet-stream"),),
            ("bogus.bog", MimeType.fromString("application/octet-stream"),),
        )

        class FakeAttachment(object):

            def __init__(self, name):
                self._name = name

            def name(self):
                return self._name

        for filename, result in test_files:
            item = StorageTransportBase(FakeAttachment(filename), None, None)
            self.assertEquals(item._contentType, result)
            self.assertEquals(item._dispositionName, None)
            item = StorageTransportBase(FakeAttachment(filename), result, filename)
            self.assertEquals(item._contentType, result)
            self.assertEquals(item._dispositionName, filename)



class HomeMigrationTests(CommonCommonTests, BaseTestCase):
    """
    Tests for L{migrateHome}.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(HomeMigrationTests, self).setUp()
        self.theStore = yield buildCalendarStore(self, self.notifierFactory, homes=("conflict1", "conflict2",))


    def storeUnderTest(self):
        return self.theStore


    @inlineCallbacks
    def test_migrateEmptyHome(self):
        """
        Migrating an empty home into an existing home should destroy all the
        existing home's calendars.
        """
        yield populateCalendarsFrom({
            "empty_home": {
                # Some of the upgrade logic will ensure that sufficient default
                # calendars exist for basic usage, so this home is actually only
                # *mostly* empty; the important thing is that the default
                # calendar is removed.
                "other-default-calendar": {}
            },
            "non_empty_home": {
                "calendar": {},
                "inbox": {},
                # XXX: implementation is configuration-sensitive regarding the
                # 'tasks' calendar and it shouldn't be.
                "tasks": {},
                "polls": {},
            }
        }, self.storeUnderTest())
        txn = self.transactionUnderTest()
        emptyHome = yield txn.calendarHomeWithUID("empty_home")
        self.assertIdentical((yield emptyHome.calendarWithName("calendar")), None)
        nonEmpty = yield txn.calendarHomeWithUID("non_empty_home")
        yield migrateHome(emptyHome, nonEmpty)
        yield self.commit()
        txn = self.transactionUnderTest()
        emptyHome = yield txn.calendarHomeWithUID("empty_home")
        nonEmpty = yield txn.calendarHomeWithUID("non_empty_home")

        self.assertIdentical((yield nonEmpty.calendarWithName("calendar")), None)
        self.assertNotIdentical((yield nonEmpty.calendarWithName("inbox")), None)
        self.assertNotIdentical((yield nonEmpty.calendarWithName("other-default-calendar")), None)


    @staticmethod
    def sampleEvent(uid, summary=None):
        """
        Create the iCalendar text for a sample event that has no organizer nor
        any attendees.
        """
        if summary is None:
            summary = "event " + uid
        return textwrap.dedent(
            """\
            BEGIN:VCALENDAR
            VERSION:2.0
            CALSCALE:GREGORIAN
            PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
            BEGIN:VEVENT
            UID:{uid}
            DTSTART;VALUE=DATE:20060201
            DURATION:P1D
            CREATED:20060101T210000Z
            DTSTAMP:20051222T210146Z
            LAST-MODIFIED:20051222T210203Z
            SEQUENCE:1
            SUMMARY:{summary}
            TRANSP:TRANSPARENT
            END:VEVENT
            END:VCALENDAR
            """.replace("\n", "\r\n").format(uid=uid, summary=summary)
        ), {}


    @inlineCallbacks
    def createConflicted(self, c1=None, c2=None):
        """
        Create two calendar homes with calendars with the same names within
        them.  Parameters are both a mapping of calendar object names to
        2-tuples of (iCalendar data, metadata).

        @param c1: the calendar data for conflict1/conflicted/*

        @param c2: the calendar data for conflict2/conflicted/*
        """
        if c1 is None:
            c1 = {"1.ics": self.sampleEvent("uid1")}
        if c2 is None:
            c2 = {"2.ics": self.sampleEvent("uid2")}
        defaults = {"calendar": {}, "inbox": {}, "tasks": {}, "polls": {}}
        def conflicted(caldata):
            d = defaults.copy()
            d.update(conflicted=caldata)
            return d
        yield populateCalendarsFrom({
            "conflict1": conflicted(c1),
            "conflict2": conflicted(c2),
        }, self.storeUnderTest())


    @inlineCallbacks
    def test_migrateConflict(self):
        """
        Migrating a home with conflicting (non-default) calendars will cause an
        error.
        """
        yield self.createConflicted()
        txn = self.transactionUnderTest()
        conflict1 = yield txn.calendarHomeWithUID("conflict1")
        conflict2 = yield txn.calendarHomeWithUID("conflict2")

        try:
            yield migrateHome(conflict1, conflict2)
        except HomeChildNameAlreadyExistsError:
            pass
        else:
            self.fail("No exception raised.")


    @inlineCallbacks
    def test_migrateMergeCalendars(self):
        """
        Migrating a home with a conflicting (non-default) calendar in merge
        mode will cause the properties on the conflicting calendar to be
        overridden by the new calendar of the same name, and calendar objects
        to be copied over.
        """
        yield self.createConflicted()
        from txdav.base.propertystore.base import PropertyName
        from txdav.xml import element as davxml
        class StubConflictingElement(davxml.WebDAVTextElement):
            namespace = "http://example.com/ns/stub-conflict"
            name = "conflict"
        beforeProp = StubConflictingElement.fromString("before")
        afterProp = StubConflictingElement.fromString("after")
        conflictPropName = PropertyName.fromElement(beforeProp)
        txn = self.transactionUnderTest()
        conflict1 = yield txn.calendarHomeWithUID("conflict1")
        conflict2 = yield txn.calendarHomeWithUID("conflict2")
        cal1 = yield conflict1.calendarWithName("conflicted")
        cal2 = yield conflict2.calendarWithName("conflicted")
        p1 = cal1.properties()
        p2 = cal2.properties()
        p1[conflictPropName] = afterProp
        p2[conflictPropName] = beforeProp
        yield migrateHome(conflict1, conflict2, merge=True)
        self.assertEquals(p2[conflictPropName].children[0].data, "after")
        obj1 = yield cal2.calendarObjectWithName("1.ics")
        obj2 = yield cal2.calendarObjectWithName("2.ics")
        # just a really cursory check to make sure they're really there.
        self.assertEquals(obj1.uid(), "uid1")
        self.assertEquals(obj2.uid(), "uid2")


    @inlineCallbacks
    def test_migrateMergeConflictingObjects(self):
        """
        When merging two homes together, calendar objects may conflict in the
        following ways:

        First, an object may have the same name and the same UID as an object
        in the target calendar.  We assume the target object is always be newer
        than the source object, so this type of conflict will leave the source
        object unmodified.  This type of conflict is expected, and may happen
        as a result of an implicitly scheduled event where the principal owning
        the merged calendars is an attendee of the conflicting object, and
        received a re-invitation.

        Second, an object may have a different name, but the same UID as an
        object in the target calendar.  While this type of conflict is not
        expected -- most clients will choose names for objects that correspond
        to the iCalendar UIDs of their main component -- it is treated the same
        way as the first conflict.

        Third, an object may have the same UID as an object on a different
        calendar in the target home.  This may also happen if a scheduled event
        was previously on a different (most likely non-default) calendar.
        Technically this is actually valid, and it is possible to have the same
        object in multiple calendars as long as the object is not scheduled;
        however, that type of conflict is extremely unlikely as the client
        would have to generate the same event twice.

        Basically, in all expected cases, conflicts will only occur because an
        update to a scheduled event was sent out and the target home accepted
        it.  Therefore, conflicts are always resolved in favor of ignoring the
        source data and trusting that the target data is more reliable.
        """
        # Note: these tests are all performed with un-scheduled data because it
        # is simpler.  Although the expected conflicts will involve scheduled
        # data the behavior will be exactly the same.
        yield self.createConflicted(
            {
                "same-name": self.sampleEvent("same-name", "source"),
                "other-name": self.sampleEvent("other-uid", "source other"),
                "other-calendar": self.sampleEvent("oc", "source calendar"),
                "no-conflict": self.sampleEvent("no-conflict", "okay"),
            },
            {
                "same-name": self.sampleEvent("same-name", "target"),
                "different-name": self.sampleEvent("other-uid", "tgt other"),
            },
        )
        txn = self.transactionUnderTest()
        c1 = yield txn.calendarHomeWithUID("conflict1")
        c2 = yield txn.calendarHomeWithUID("conflict2")
        otherCal = yield c2.createCalendarWithName("othercal")
        otherCal.createCalendarObjectWithName(
            "some-name", Component.fromString(
                self.sampleEvent("oc", "target calendar")[0]
            )
        )
        yield migrateHome(c1, c2, merge=True)
        targetCal = yield c2.calendarWithName("conflicted")
        yield self.checkSummary("same-name", "target", targetCal)
        yield self.checkSummary("different-name", "tgt other", targetCal)
        yield self.checkSummary("other-calendar", None, targetCal)
        yield self.checkSummary("other-name", None, targetCal)
        yield self.checkSummary("no-conflict", "okay", targetCal)
        yield self.checkSummary("oc", "target calendar", otherCal)


    @inlineCallbacks
    def checkSummary(self, name, summary, cal):
        """
        Verify that the summary of the calendar object for the given name in
        the given calendar matches.
        """
        obj = yield cal.calendarObjectWithName(name)
        if summary is None:
            self.assertIdentical(obj, None,
                                 name + " existed but shouldn't have")
        else:
            txt = ((yield obj.component()).mainComponent()
                   .getProperty("SUMMARY").value())
            self.assertEquals(txt, summary)


    @inlineCallbacks
    def test_migrateMergeDontDeleteDefault(self):
        """
        If we're doing a merge migration, it's quite possible that the user has
        scheduled events onto their default calendar already.  In fact the
        whole point of a merge migration is to preserve data that might have
        been created there.  So, let's make sure that we I{don't} delete any
        data from the default calendars in the case that we're merging.
        """
        yield populateCalendarsFrom({
            "empty_home": {
                # see test_migrateEmptyHome above.
                "other-default-calendar": {}
            },
            "non_empty_home": {
                "calendar": {
                    "some-name": self.sampleEvent("some-uid", "some summary"),
                }, "inbox": {}, "tasks": {}
            }
        }, self.storeUnderTest())
        txn = self.transactionUnderTest()
        emptyHome = yield txn.calendarHomeWithUID("empty_home")
        self.assertIdentical((yield emptyHome.calendarWithName("calendar")),
                             None)
        nonEmpty = yield txn.calendarHomeWithUID("non_empty_home")
        yield migrateHome(emptyHome, nonEmpty, merge=True)
        yield self.commit()
        txn = self.transactionUnderTest()
        emptyHome = yield txn.calendarHomeWithUID("empty_home")
        nonEmpty = yield txn.calendarHomeWithUID("non_empty_home")
        self.assertNotIdentical(
            (yield nonEmpty.calendarWithName("inbox")), None
        )
        defaultCal = (yield nonEmpty.calendarWithName("calendar"))
        self.assertNotIdentical(
            (yield defaultCal.calendarObjectWithName("some-name")), None
        )
