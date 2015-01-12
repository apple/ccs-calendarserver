##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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
Tests for txdav.caldav.datastore.utils
"""

from pycalendar.datetime import DateTime

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from txdav.caldav.datastore.scheduling.utils import getCalendarObjectForRecord, \
    extractEmailDomain, uidFromCalendarUserAddress
from txdav.common.datastore.test.util import populateCalendarsFrom, CommonCommonTests


now = DateTime.getToday().getYear()

ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:685BC3A1-195A-49B3-926D-388DDACA78A6
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
ORGANIZER:urn:uuid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:user02
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now + 1}

ATTENDEE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:685BC3A1-195A-49B3-926D-388DDACA78A6
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART:%(year)s0307T111500Z
DURATION:PT1H
DTSTAMP:20100303T181220Z
ORGANIZER:urn:uuid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:user01
ATTENDEE;PARTSTAT=ACCEPTED:urn:uuid:user02
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {"year": now + 1}



class RecipientCopy(CommonCommonTests, unittest.TestCase):
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
        "user01" : {
            "calendar1" : {
                "1.ics" : (ORGANIZER_ICS, metadata,),
            }
        },
        "user02" : {
            "calendar2" : {
                "2.ics" : (ATTENDEE_ICS, metadata,),
            },
            "calendar3" : {
                "3.ics" : (ATTENDEE_ICS, metadata,),
            }
        }
    }

    @inlineCallbacks
    def setUp(self):

        yield super(RecipientCopy, self).setUp()
        yield self.buildStoreAndDirectory()
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
    def test_getCalendarObjectForRecord(self):
        """
        Test that L{txdav.caldav.datastore.scheduling.utils.getCalendarObjectForRecord} detects and removes
        resources with duplicate UIDs in the same calendar home.
        """

        # Check that expected resources are present
        txn = self.transactionUnderTest()
        for home_uid, calendar_name, resource_name in (
            ("user01", "calendar1", "1.ics",),
            ("user02", "calendar2", "2.ics",),
            ("user02", "calendar3", "3.ics",),
        ):
            resource = (yield self.calendarObjectUnderTest(txn, name=resource_name, calendar_name=calendar_name, home=home_uid))
            self.assertNotEqual(resource, None)
        yield self.commit()

        # Look up resource by UID in home where only one exists
        principal = yield self.directory.recordWithUID(u"user01")
        txn = self.transactionUnderTest()
        resource = (yield getCalendarObjectForRecord(txn, principal, "685BC3A1-195A-49B3-926D-388DDACA78A6"))
        self.assertEqual(resource.name(), "1.ics")
        self.assertEqual(resource._parentCollection.name(), "calendar1")
        self.assertEqual(resource._parentCollection.viewerHome().uid(), "user01")
        yield self.commit()

        # Check that expected resources are still present
        txn = self.transactionUnderTest()
        for home_uid, calendar_name, resource_name in (
            ("user01", "calendar1", "1.ics",),
            ("user02", "calendar2", "2.ics",),
            ("user02", "calendar3", "3.ics",),
        ):
            resource = (yield self.calendarObjectUnderTest(txn, name=resource_name, calendar_name=calendar_name, home=home_uid))
            self.assertNotEqual(resource, None)
        yield self.commit()

        # Look up resource by UID in home where two exists
        principal = yield self.directory.recordWithUID("user02")
        txn = self.transactionUnderTest()
        resource = (yield getCalendarObjectForRecord(txn, principal, "685BC3A1-195A-49B3-926D-388DDACA78A6"))
        self.assertTrue(resource.name() in ("2.ics", "3.ics",))
        self.assertTrue(resource._parentCollection.name() in ("calendar2", "calendar3",))
        self.assertEqual(resource._parentCollection.viewerHome().uid(), "user02")
        yield self.commit()

        # Check that expected resources are still present, but the duplicate missing
        txn = self.transactionUnderTest()
        resource = (yield self.calendarObjectUnderTest(txn, name="1.ics", calendar_name="calendar1", home="user01"))
        self.assertNotEqual(resource, None)
        resource2 = (yield self.calendarObjectUnderTest(txn, name="2.ics", calendar_name="calendar2", home="user02"))
        resource3 = (yield self.calendarObjectUnderTest(txn, name="3.ics", calendar_name="calendar3", home="user02"))
        self.assertTrue((resource2 is not None) ^ (resource3 is not None))
        yield self.commit()

        # Look up resource where principal exists but home does not
        principal = yield self.directory.recordWithUID("user102")  # ASKCYRUS: but user102 doesn't exist
        txn = self.transactionUnderTest()
        resource = (yield getCalendarObjectForRecord(txn, principal, "685BC3A1-195A-49B3-926D-388DDACA78A6"))
        self.assertTrue(resource is None)
        yield self.commit()


    def test_uidFromCalendarUserAddress(self):
        """
        Test that L{uidFromCalendarUserAddress} returns the expected results.
        """

        data = (
            ("urn:x-uid:foobar", "foobar"),
            ("urn:uuid:foobar", "foobar"),
            ("urn:uuid:49DE7436-F01C-4AD8-B685-A94303F40301", "49DE7436-F01C-4AD8-B685-A94303F40301"),
            ("/principals/__uids__/foobar", "foobar"),
            ("/principals/users/foobar", None),
            ("/principals/groups/foobar", None),
            ("mailto:foo@example.com", None),
        )

        for cuaddr, uid in data:
            self.assertEqual(uidFromCalendarUserAddress(cuaddr), uid)


    def test_extractEmailDomain(self):
        """
        Test that L{extractEmailDomain} returns the expected results.
        """

        data = (
            ("mailto:foo@example.com", "example.com"),
            ("mailto:foo@example.com?subject=bar", "example.com"),
            ("mailto:foo", ""),
            ("mailto:foo@", ""),
            ("http://foobar.com", ""),
        )

        for mailto, domain in data:
            self.assertEqual(extractEmailDomain(mailto), domain)
