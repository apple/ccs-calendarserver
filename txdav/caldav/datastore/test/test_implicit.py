##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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


from twisted.internet.defer import inlineCallbacks

from twistedcaldav.ical import Component

from txdav.common.datastore.test.util import CommonCommonTests, populateCalendarsFrom
from twisted.trial.unittest import TestCase
from twext.python.clsprop import classproperty
from twistedcaldav.config import config
from txdav.common.icommondatastore import ObjectResourceTooBigError, \
    InvalidObjectResourceError, InvalidComponentForStoreError, InvalidUIDError, \
    UIDExistsError, UIDExistsElsewhereError
from txdav.caldav.icalendarstore import InvalidComponentTypeError, \
    TooManyAttendeesError, InvalidCalendarAccessError, ComponentUpdateState
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE
from txdav.caldav.datastore.test.util import buildCalendarStore

class ImplicitRequests (CommonCommonTests, TestCase):
    """
    Test twistedcaldav.scheduyling.implicit with a Request object.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(ImplicitRequests, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user02": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
    }


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def test_doCreateResource(self):
        """
        Test that resource creation works.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar1 = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar1)
        yield self.commit()

        calendar_resource1 = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar1 = (yield calendar_resource1.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("urn:uuid:user01" in calendar1)
        self.assertTrue("urn:uuid:user02" in calendar1)
        self.assertTrue("CN=" in calendar1)
        yield self.commit()


    @inlineCallbacks
    def test_validation_maxResourceSize(self):
        """
        Test that various types of invalid calendar data are rejected when creating a resource.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:Changed
END:VEVENT
END:VCALENDAR
"""

        self.patch(config, "MaxResourceSize", 100)
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar1 = Component.fromString(data1)
        yield self.failUnlessFailure(calendar_collection.createCalendarObjectWithName("test.ics", calendar1), ObjectResourceTooBigError)
        yield self.commit()

        self.patch(config, "MaxResourceSize", 10000)
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar1 = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar1)
        yield self.commit()

        self.patch(config, "MaxResourceSize", 100)
        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar2 = Component.fromString(data2)
        yield self.failUnlessFailure(calendar_resource.setComponent(calendar2), ObjectResourceTooBigError)
        yield self.commit()


    @inlineCallbacks
    def test_validation_validCalendarDataCheck(self):
        """
        Test that various types of invalid calendar data are rejected when creating a resource.
        """

        data = (
            "xyz",
            Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:1
SUMMARY:2
END:VEVENT
END:VCALENDAR
"""),

        Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:PUBLISH
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""),
        )

        for item in data:
            calendar_collection = (yield self.calendarUnderTest(home="user01"))
            calendar = item
            yield self.failUnlessFailure(calendar_collection.createCalendarObjectWithName("test.ics", calendar), InvalidObjectResourceError, InvalidComponentForStoreError)
            yield self.commit()


    @inlineCallbacks
    def test_validation_validSupportedComponentType(self):
        """
        Test that resources are restricted by component type.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar_collection.setSupportedComponents("VTODO")
        calendar = Component.fromString(data1)
        yield self.failUnlessFailure(calendar_collection.createCalendarObjectWithName("test.ics", calendar), InvalidComponentTypeError)
        yield self.commit()


    @inlineCallbacks
    def test_validation_validAttendeeListSizeCheck(self):
        """
        Test that resource with too many attendees are rejected.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:user03@example.com
ATTENDEE:mailto:user04@example.com
ATTENDEE:mailto:user05@example.com
END:VEVENT
END:VCALENDAR
"""

        self.patch(config, "MaxAttendeesPerInstance", 2)
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield self.failUnlessFailure(calendar_collection.createCalendarObjectWithName("test.ics", calendar), TooManyAttendeesError)
        yield self.commit()


    @inlineCallbacks
    def test_validation_validAccess_invalidValue(self):
        """
        Test that resource access mode changes are rejected.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
X-CALENDARSERVER-ACCESS:BOGUS
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        self.patch(config, "EnablePrivateEvents", True)
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield self.failUnlessFailure(calendar_collection.createCalendarObjectWithName("test.ics", calendar), InvalidCalendarAccessError)
        yield self.commit()


    @inlineCallbacks
    def test_validation_validAccess_authzChangeNotAllowed(self):
        """
        Test that resource access mode changes are rejected.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
X-CALENDARSERVER-ACCESS:PRIVATE
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        self.patch(config, "EnablePrivateEvents", True)
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        txn = self.transactionUnderTest()
        txn._authz_uid = "user02"
        yield self.failUnlessFailure(calendar_collection.createCalendarObjectWithName("test.ics", calendar), InvalidCalendarAccessError)
        yield self.commit()

        # This one should be OK
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        txn = self.transactionUnderTest()
        txn._authz_uid = "user01"
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        # This one should re-insert access mode
        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:Changed
END:VEVENT
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data2)
        txn = self.transactionUnderTest()
        txn._authz_uid = "user01"
        yield calendar_resource.setComponent(calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("X-CALENDARSERVER-ACCESS:PRIVATE" in calendar1)
        self.assertTrue("SUMMARY:Changed" in calendar1)
        yield self.commit()


    @inlineCallbacks
    def test_validation_overwriteUID(self):
        """
        Test that a change to a resource UID is not allowed.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        # This one should fail
        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply-1
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data2)
        yield self.failUnlessFailure(calendar_resource.setComponent(calendar), InvalidUIDError)
        yield self.commit()


    @inlineCallbacks
    def test_validation_duplicateUIDSameCalendar(self):
        """
        Test that a resource with a duplicate UID in the same calendar is not allowed.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        # This one should fail
        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:Changed
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data2)
        yield self.failUnlessFailure(calendar_collection.createCalendarObjectWithName("test2.ics", calendar), UIDExistsError)
        yield self.commit()


    @inlineCallbacks
    def test_validation_duplicateUIDDifferentCalendar(self):
        """
        Test that a resource with a duplicate UID in a different calendar is not allowed.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        # This one should fail
        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:Changed
END:VEVENT
END:VCALENDAR
"""

        home_collection = (yield self.homeUnderTest(name="user01"))
        calendar_collection_2 = (yield home_collection.createCalendarWithName("calendar_2"))
        calendar = Component.fromString(data2)
        yield self.failUnlessFailure(calendar_collection_2.createCalendarObjectWithName("test2.ics", calendar), UIDExistsElsewhereError)
        yield self.commit()


    @inlineCallbacks
    def test_validation_preservePrivateComments(self):
        """
        Test that resource private comments are restored.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
X-CALENDARSERVER-PRIVATE-COMMENT:My Comment
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:Changed
END:VEVENT
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data2)
        txn = self.transactionUnderTest()
        txn._authz_uid = "user01"
        yield calendar_resource.setComponent(calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("X-CALENDARSERVER-PRIVATE-COMMENT:My Comment" in calendar1)
        self.assertTrue("SUMMARY:Changed" in calendar1)
        yield self.commit()


    @inlineCallbacks
    def test_validation_replaceMissingToDoProperties_OrganizerAttendee(self):
        """
        Test that missing scheduling properties in VTODOs are recovered.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTODO
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VTODO
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTODO
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:Changed
END:VTODO
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data2)
        txn = self.transactionUnderTest()
        txn._authz_uid = "user01"
        yield calendar_resource.setComponent(calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("ORGANIZER" in calendar1)
        self.assertTrue("ATTENDEE" in calendar1)
        self.assertTrue("SUMMARY:Changed" in calendar1)
        yield self.commit()


    @inlineCallbacks
    def test_validation_replaceMissingToDoProperties_Completed(self):
        """
        Test that VTODO completed status is fixed.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTODO
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VTODO
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTODO
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:Changed
COMPLETED:20080601T140000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VTODO
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data2)
        txn = self.transactionUnderTest()
        txn._authz_uid = "user01"
        yield calendar_resource.setComponent(calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("ORGANIZER" in calendar1)
        self.assertTrue("ATTENDEE" in calendar1)
        self.assertTrue("SUMMARY:Changed" in calendar1)
        self.assertTrue("PARTSTAT=COMPLETED" in calendar1)
        yield self.commit()


    @inlineCallbacks
    def test_validation_dropboxPathNormalization(self):
        """
        Test that dropbox paths are normalized.
        """

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        sharee_home = (yield self.homeUnderTest(name="user02"))
        shared_name = (yield calendar_collection.shareWith(sharee_home, _BIND_MODE_WRITE,))
        yield self.commit()

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTODO
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
X-APPLE-DROPBOX:https://example.com/calendars/users/user02/dropbox/123.dropbox
ATTACH;VALUE=URI:https://example.com/calendars/users/user02/dropbox/123.dropbox/1.txt
ATTACH;VALUE=URI:https://example.org/attachments/2.txt
END:VTODO
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(name=shared_name, home="user02"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", calendar_name=shared_name, home="user02",))
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("X-APPLE-DROPBOX:https://example.com/calendars/__uids__/user01/dropbox/123.dropbox" in calendar1)
        self.assertTrue("ATTACH:https://example.com/calendars/__uids__/user01/dropbox/123.dropbox/1.txt" in calendar1)
        self.assertTrue("ATTACH:https://example.org/attachments/2.txt" in calendar1)
        yield self.commit()


    @inlineCallbacks
    def test_validation_processAlarms_DuplicateRemoval(self):
        """
        Test that duplicate alarms are removed.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
SUMMARY:Changed
BEGIN:VALARM
X-WR-ALARMUID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
UID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
DESCRIPTION:Event reminder
TRIGGER:-PT8M
ACTION:DISPLAY
END:VALARM
BEGIN:VALARM
X-WR-ALARMUID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
UID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
DESCRIPTION:Event reminder
TRIGGER:-PT8M
ACTION:DISPLAY
END:VALARM
END:VEVENT
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data2)
        txn = self.transactionUnderTest()
        txn._authz_uid = "user01"
        result = (yield calendar_resource.setComponent(calendar))
        yield self.commit()
        self.assertTrue(result)

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 1)
        self.assertTrue("SUMMARY:Changed" in calendar1)
        yield self.commit()


    @inlineCallbacks
    def test_validation_processAlarms_AddDefault(self):
        """
        Test that default alarms are added.
        """

        alarm = """BEGIN:VALARM
X-WR-ALARMUID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
UID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
DESCRIPTION:Event reminder
TRIGGER:-PT8M
ACTION:DISPLAY
END:VALARM
"""

        home = (yield self.homeUnderTest(name="user01"))
        home.setDefaultAlarm(alarm, True, True)
        yield self.commit()

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 1)
        yield self.commit()


    @inlineCallbacks
    def test_validation_processAlarms_NoDefaultShared(self):
        """
        Test that default alarms are not added to shared resources.
        """

        # Set default alarm for user02
        alarm = """BEGIN:VALARM
X-WR-ALARMUID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
UID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
DESCRIPTION:Event reminder
TRIGGER:-PT8M
ACTION:DISPLAY
END:VALARM
"""

        home = (yield self.homeUnderTest(name="user02"))
        home.setDefaultAlarm(alarm, True, True)
        yield self.commit()

        # user01 shares calendar with user02
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        sharee_home = (yield self.homeUnderTest(name="user02"))
        shared_name = (yield calendar_collection.shareWith(sharee_home, _BIND_MODE_WRITE,))
        yield self.commit()

        # user02 writes event to shared calendar
        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(name=shared_name, home="user02"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", calendar_name=shared_name, home="user02",))
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 0)
        yield self.commit()


    @inlineCallbacks
    def test_validation_mergePerUserData(self):
        """
        Test that per-user data is correctly stored and retrieved.
        """

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        sharee_home = (yield self.homeUnderTest(name="user02"))
        shared_name = (yield calendar_collection.shareWith(sharee_home, _BIND_MODE_WRITE,))
        yield self.commit()

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
BEGIN:VALARM
X-WR-ALARMUID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
UID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
DESCRIPTION:Event reminder
TRIGGER:-PT5M
ACTION:DISPLAY
END:VALARM
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
BEGIN:VALARM
X-WR-ALARMUID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
UID:D9D1AC84-F629-4B9D-9B6B-4A6CA9A11FEF
DESCRIPTION:Event reminder
TRIGGER:-PT10M
ACTION:DISPLAY
END:VALARM
END:VEVENT
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", calendar_name=shared_name, home="user02",))
        calendar = Component.fromString(data2)
        yield calendar_resource.setComponent(calendar)
        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))

        # Unfiltered view of event
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("TRIGGER:-PT5M" in calendar1)
        self.assertTrue("TRIGGER:-PT10M" in calendar1)
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 2)

        # user01 view of event
        calendar1 = (yield calendar_resource.componentForUser("user01"))
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("TRIGGER:-PT5M" in calendar1)
        self.assertFalse("TRIGGER:-PT10M" in calendar1)
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 1)

        # user02 view of event
        calendar1 = (yield calendar_resource.componentForUser("user02"))
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertFalse("TRIGGER:-PT5M" in calendar1)
        self.assertTrue("TRIGGER:-PT10M" in calendar1)
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 1)

        yield self.commit()

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", calendar_name=shared_name, home="user02",))

        # Unfiltered view of event
        calendar1 = (yield calendar_resource.component())
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("TRIGGER:-PT5M" in calendar1)
        self.assertTrue("TRIGGER:-PT10M" in calendar1)
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 2)

        # user01 view of event
        calendar1 = (yield calendar_resource.componentForUser("user01"))
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertTrue("TRIGGER:-PT5M" in calendar1)
        self.assertFalse("TRIGGER:-PT10M" in calendar1)
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 1)

        # user02 view of event
        calendar1 = (yield calendar_resource.componentForUser("user02"))
        calendar1 = str(calendar1).replace("\r\n ", "")
        self.assertFalse("TRIGGER:-PT5M" in calendar1)
        self.assertTrue("TRIGGER:-PT10M" in calendar1)
        self.assertEqual(calendar1.count("BEGIN:VALARM"), 1)

        yield self.commit()


    @inlineCallbacks
    def test_validation_processScheduleTags(self):
        """
        Test that schedule tags are correctly updated.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
END:VEVENT
END:VCALENDAR
"""

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        yield self.commit()

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
SUMMARY:Changed #1
END:VEVENT
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data2)
        yield calendar_resource.setComponent(calendar)
        schedule_tag = calendar_resource.scheduleTag
        yield self.commit()

        data3 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
SUMMARY:Changed #2
END:VEVENT
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data3)
        yield calendar_resource.setComponent(calendar)
        self.assertNotEqual(calendar_resource.scheduleTag, schedule_tag)
        schedule_tag = calendar_resource.scheduleTag
        yield self.commit()

        data4 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTAMP:20080601T120000Z
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
SUMMARY:Changed #2
END:VEVENT
END:VCALENDAR
"""

        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar = Component.fromString(data4)
        yield calendar_resource._setComponentInternal(calendar, internal_state=ComponentUpdateState.ORGANIZER_ITIP_UPDATE)
        self.assertEqual(calendar_resource.scheduleTag, schedule_tag)
        yield self.commit()
