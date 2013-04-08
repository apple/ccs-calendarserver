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

from txdav.common.datastore.test.util import CommonCommonTests, buildStore, \
    populateCalendarsFrom
from twisted.trial.unittest import TestCase
from twext.python.clsprop import classproperty
from twistedcaldav.config import config
from txdav.common.icommondatastore import ObjectResourceTooBigError, \
    InvalidObjectResourceError
from txdav.caldav.icalendarstore import InvalidComponentTypeError, \
    TooManyAttendeesError, InvalidCalendarAccessError, InvalidUIDError, \
    UIDExistsError
import sys

class ImplicitRequests (CommonCommonTests, TestCase):
    """
    Test twistedcaldav.scheduyling.implicit with a Request object.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(ImplicitRequests, self).setUp()
        self._sqlCalendarStore = yield buildStore(self, self.notifierFactory)
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
        self.assertTrue("urn:uuid:user01" in str(calendar1))
        self.assertTrue("urn:uuid:user02" in str(calendar1))
        self.assertTrue("CN=" in str(calendar1))
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
        try:
            yield calendar_collection.createCalendarObjectWithName("test.ics", calendar1)
        except ObjectResourceTooBigError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
        yield self.commit()

        self.patch(config, "MaxResourceSize", 10000)
        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar1 = Component.fromString(data1)
        yield calendar_collection.createCalendarObjectWithName("test.ics", calendar1)
        yield self.commit()

        self.patch(config, "MaxResourceSize", 100)
        calendar_resource = (yield self.calendarObjectUnderTest(name="test.ics", home="user01",))
        calendar2 = Component.fromString(data2)
        try:
            yield calendar_resource.setComponent(calendar2)
        except ObjectResourceTooBigError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
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
            try:
                yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
            except InvalidObjectResourceError:
                pass
            except:
                self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
            else:
                self.fail("Exception not raised")
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
        try:
            yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        except InvalidComponentTypeError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
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
        try:
            yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        except TooManyAttendeesError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
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

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        try:
            yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        except InvalidCalendarAccessError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
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

        calendar_collection = (yield self.calendarUnderTest(home="user01"))
        calendar = Component.fromString(data1)
        txn = self.transactionUnderTest()
        txn._authz_uid = "user02"
        try:
            yield calendar_collection.createCalendarObjectWithName("test.ics", calendar)
        except InvalidCalendarAccessError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
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
        self.assertTrue("X-CALENDARSERVER-ACCESS:PRIVATE" in str(calendar1))
        self.assertTrue("SUMMARY:Changed" in str(calendar1))
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
        try:
            yield calendar_resource.setComponent(calendar)
        except InvalidUIDError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
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
        try:
            yield calendar_collection.createCalendarObjectWithName("test2.ics", calendar)
        except UIDExistsError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
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
        try:
            yield calendar_collection_2.createCalendarObjectWithName("test2.ics", calendar)
        except UIDExistsError:
            pass
        except:
            self.fail("Wrong exception raised: %s" % (sys.exc_info()[0].__name__,))
        else:
            self.fail("Exception not raised")
        yield self.commit()
