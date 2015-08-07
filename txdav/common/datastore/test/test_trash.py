##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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
Trash-specific tests for L{txdav.common.datastore.sql}.
"""

from calendarserver.tools.trash import emptyTrashForPrincipal
from pycalendar.datetime import DateTime
from twext.enterprise.jobs.jobitem import JobItem
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav.ical import Component
from twistedcaldav.test.util import StoreTestCase
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE


class TrashTests(StoreTestCase):


    def _homeForUser(self, txn, userName):
        return txn.calendarHomeWithUID(userName, create=True)


    @inlineCallbacks
    def _collectionForUser(self, txn, userName, collectionName, create=False, onlyInTrash=False):
        home = yield txn.calendarHomeWithUID(userName, create=True)
        collection = yield home.childWithName(collectionName, onlyInTrash=onlyInTrash)
        if collection is None:
            if create:
                collection = yield home.createCalendarWithName(collectionName)
        returnValue(collection)


    @inlineCallbacks
    def _createResource(self, txn, userName, collectionName, resourceName, data):
        collection = yield self._collectionForUser(txn, userName, collectionName)
        resource = yield collection.createObjectResourceWithName(
            resourceName, Component.allFromString(data)
        )
        returnValue(resource)


    @inlineCallbacks
    def _getResource(self, txn, userName, collectionName, resourceName):
        collection = yield self._collectionForUser(txn, userName, collectionName)
        if not resourceName:
            # Get the first one
            resourceNames = yield collection.listObjectResources()
            if len(resourceNames) == 0:
                returnValue(None)
            resourceName = resourceNames[0]
        resource = yield collection.calendarObjectWithName(resourceName)
        returnValue(resource)


    @inlineCallbacks
    def _getResourceNames(self, txn, userName, collectionName):
        collection = yield self._collectionForUser(txn, userName, collectionName)
        resourceNames = yield collection.listObjectResources()
        returnValue(resourceNames)


    @inlineCallbacks
    def _getTrashNames(self, txn, userName):
        home = yield txn.calendarHomeWithUID(userName)
        trash = yield home.getTrash()
        resourceNames = yield trash.listObjectResources()
        returnValue(resourceNames)


    @inlineCallbacks
    def _updateResource(self, txn, userName, collectionName, resourceName, data):
        resource = yield self._getResource(txn, userName, collectionName, resourceName)
        yield resource.setComponent(Component.fromString(data))
        returnValue(resource)


    @inlineCallbacks
    def _getResourceData(self, txn, userName, collectionName, resourceName):
        resource = yield self._getResource(txn, userName, collectionName, resourceName)
        if resource is None:
            returnValue(None)
        component = yield resource.component()
        returnValue(str(component).replace("\r\n ", ""))


    @inlineCallbacks
    def test_trashUnscheduled(self):
        """
        Verify the "resource is entirely in the trash" flag
        """

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)


        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
DTSTART;TZID=America/Los_Angeles:20141108T093000
DTEND;TZID=America/Los_Angeles:20141108T103000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
RRULE:FREQ=DAILY
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
RECURRENCE-ID;TZID=America/Los_Angeles:20141111T093000
DTSTART;TZID=America/Los_Angeles:20141111T110000
DTEND;TZID=America/Los_Angeles:20141111T120000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

        txn = self.store.newTransaction()

        #
        # First, use a calendar object
        #

        home = yield txn.calendarHomeWithUID("user01", create=True)
        collection = yield home.childWithName("calendar")
        trash = yield home.getTrash(create=True)

        # No objects
        objects = yield collection.listObjectResources()
        self.assertEquals(len(objects), 0)

        # Create an object
        resource = yield collection.createObjectResourceWithName(
            "test.ics",
            Component.allFromString(data1)
        )

        # One object in collection
        objects = yield collection.listObjectResources()
        self.assertEquals(len(objects), 1)

        # No objects in trash
        objects = yield trash.listObjectResources()
        self.assertEquals(len(objects), 0)

        # Verify it's not in the trash
        self.assertFalse(resource.isInTrash())
        trashed = resource.whenTrashed()
        self.assertTrue(trashed is None)

        # Move object to trash
        newName = yield resource.toTrash()

        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        # Verify it's in the trash
        resource = yield self._getResource(txn, "user01", trash.name(), newName)
        self.assertTrue(resource.isInTrash())
        trashed = resource.whenTrashed()
        self.assertFalse(trashed is None)

        # No objects in collection
        resourceNames = yield self._getResourceNames(txn, "user01", "calendar")
        self.assertEqual(len(resourceNames), 0)

        # One object in trash
        resourceNames = yield self._getResourceNames(txn, "user01", trash.name())
        self.assertEqual(len(resourceNames), 1)

        # Put back from trash
        yield resource.fromTrash()

        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        # Not in trash
        resource = yield self._getResource(txn, "user01", trash.name(), "")
        self.assertTrue(resource is None)


        # One object in collection
        resourceNames = yield self._getResourceNames(txn, "user01", "calendar")
        self.assertEqual(len(resourceNames), 1)
        resource = yield self._getResource(txn, "user01", "calendar", newName)
        self.assertFalse(resource.isInTrash())
        trashed = resource.whenTrashed()
        self.assertTrue(trashed is None)

        # No objects in trash
        resourceNames = yield self._getResourceNames(txn, "user01", trash.name())
        self.assertEqual(len(resourceNames), 0)

        yield txn.commit()


    @inlineCallbacks
    def test_trashScheduledFullyInFuture(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        # A month in the future
        start = DateTime.getNowUTC()
        start.setHHMMSS(0, 0, 0)
        start.offsetMonth(1)
        end = DateTime.getNowUTC()
        end.setHHMMSS(1, 0, 0)
        end.offsetMonth(1)
        subs = {
            "start": start,
            "end": end,
        }

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        # user01 invites user02
        txn = self.store.newTransaction()
        yield self._createResource(
            txn, "user01", "calendar", "test.ics", data1
        )
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy has SCHEDULE-STATUS update
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=1.2" in data)

        # user02 has an inbox item
        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user02 accepts
        yield self._updateResource(txn, "user02", "calendar", "", data2)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 has an inbox item
        txn = self.store.newTransaction()
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user01's copy has SCHEDULE-STATUS update
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=2.0" in data)
        self.assertTrue("PARTSTAT=ACCEPTED" in data)
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()

        # user01 trashes event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", "calendar", "test.ics")
        yield resource.remove()
        home1 = yield self._homeForUser(txn, "user01")
        trash1 = yield home1.getTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy is in the trash, still with user02 accepted
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", trash1.name(), "")
        self.assertTrue(resource.isInTrash())
        trashed = resource.whenTrashed()
        self.assertFalse(trashed is None)
        data = yield self._getResourceData(txn, "user01", trash1.name(), "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)
        yield txn.commit()

        # user02's copy is cancelled
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user02", "inbox", "")
        self.assertTrue("METHOD:CANCEL" in data)
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()
        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("STATUS:CANCELLED" in data)
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()
        self.assertEquals(trash2, None)
        yield txn.commit()

        # user01 restores event from the trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", trash1.name(), "")
        data = yield self._getResourceData(txn, "user01", trash1.name(), "")
        yield resource.fromTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        # user01's copy should be back on their calendar
        resource = yield self._getResource(txn, "user01", "calendar", "")
        self.assertFalse(resource.isInTrash())
        trashed = resource.whenTrashed()
        self.assertTrue(trashed is None)
        data = yield self._getResourceData(txn, "user01", "calendar", "")
        self.assertTrue("PARTSTAT=NEEDS-ACTION" in data)

        # user02's copy should be back on their calendar
        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=NEEDS-ACTION" in data)

        yield txn.commit()


    @inlineCallbacks
    def test_trashScheduledFullyInFutureAttendeeTrashedThenOrganizerChanged(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        # A month in the future
        start = DateTime.getNowUTC()
        start.setHHMMSS(0, 0, 0)
        start.offsetMonth(1)
        end = DateTime.getNowUTC()
        end.setHHMMSS(1, 0, 0)
        end.offsetMonth(1)
        subs = {
            "start": start,
            "end": end,
        }

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs


        start.offsetHours(1)
        end.offsetHours(1)

        data3 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data4 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:CHANGED!
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs


        # user01 invites user02
        txn = self.store.newTransaction()
        yield self._createResource(
            txn, "user01", "calendar", "test.ics", data1
        )
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy has SCHEDULE-STATUS update
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=1.2" in data)

        # user02 has an inbox item
        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user02 accepts
        yield self._updateResource(txn, "user02", "calendar", "", data2)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 has an inbox item
        txn = self.store.newTransaction()
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user01's copy has SCHEDULE-STATUS update
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=2.0" in data)
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()

        # user02 trashes event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()

        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's calendar copy shows user02 declined
        txn = self.store.newTransaction()

        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=DECLINED" in data)

        # user01's inbox copy also shows user02 declined
        data = yield self._getResourceData(txn, "user01", "inbox", "")
        self.assertTrue("PARTSTAT=DECLINED" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()


        # user02's copy is in the trash only, and still has ACCEPTED
        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", trash2.name(), "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        # result = yield txn.execSQL("select * from calendar_object", [])
        # for row in result:
        #     print("calendar object ROW", row)

        # result = yield txn.execSQL("select * from calendar_metadata", [])
        # for row in result:
        #     print("calendar ROW", row)


        yield txn.commit()

        # user01 makes a change to event while user02's copy is in the trash
        txn = self.store.newTransaction()

        yield self._updateResource(txn, "user01", "calendar", "test.ics", data3)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=NEEDS-ACTION" in data)

        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 0)

        yield txn.commit()

        # user02 trashes event again
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()

        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's calendar copy shows user02 declined
        txn = self.store.newTransaction()

        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=DECLINED" in data)

        # user01's inbox copy also shows user02 declined
        data = yield self._getResourceData(txn, "user01", "inbox", "")
        self.assertTrue("PARTSTAT=DECLINED" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 makes a SUMMARY change to event while user02's copy is in the trash
        txn = self.store.newTransaction()

        yield self._updateResource(txn, "user01", "calendar", "test.ics", data4)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)


        txn = self.store.newTransaction()

        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        yield txn.commit()


    @inlineCallbacks
    def test_trashScheduledFullyInFutureAttendeeRemovedThenOrganizerChanged(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        # A month in the future
        start = DateTime.getNowUTC()
        start.setHHMMSS(0, 0, 0)
        start.offsetMonth(1)
        end = DateTime.getNowUTC()
        end.setHHMMSS(1, 0, 0)
        end.offsetMonth(1)
        subs = {
            "start": start,
            "end": end,
        }

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs


        data3 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:CHANGED!
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs


        start.offsetHours(1)
        end.offsetHours(1)

        data4 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:CHANGED!
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=DECLINED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs


        # user01 invites user02
        txn = self.store.newTransaction()
        yield self._createResource(
            txn, "user01", "calendar", "test.ics", data1
        )
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy has SCHEDULE-STATUS update
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=1.2" in data)

        # user02 has an inbox item
        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user02 accepts
        yield self._updateResource(txn, "user02", "calendar", "", data2)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 has an inbox item
        txn = self.store.newTransaction()
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user01's copy has SCHEDULE-STATUS update
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=2.0" in data)
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()

        # user02 trashes event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()

        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's calendar copy shows user02 declined
        txn = self.store.newTransaction()

        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=DECLINED" in data)

        # user01's inbox copy also shows user02 declined
        data = yield self._getResourceData(txn, "user01", "inbox", "")
        self.assertTrue("PARTSTAT=DECLINED" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user02's copy is in the trash only, and still has ACCEPTED
        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", trash2.name(), "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)
        yield txn.commit()


        # user02 removes the event completely from the trash

        txn = self.store.newTransaction()

        resource = yield self._getResource(txn, "user02", trash2.name(), "")
        yield resource.purge()

        yield txn.commit()


        # user01 makes a SUMMARY change to event (user02 does not get notified because they are fully declined)
        txn = self.store.newTransaction()

        yield self._updateResource(txn, "user01", "calendar", "test.ics", data3)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        yield txn.commit()

        # user01 makes a time change to event (user02 gets notified)
        txn = self.store.newTransaction()

        yield self._updateResource(txn, "user01", "calendar", "test.ics", data4)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=NEEDS-ACTION" in data)

        yield txn.commit()


    @inlineCallbacks
    def test_trashScheduledFullyInFutureAttendeeTrashedThenPutBack(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        # A month in the future
        start = DateTime.getNowUTC()
        start.setHHMMSS(0, 0, 0)
        start.offsetMonth(1)
        end = DateTime.getNowUTC()
        end.setHHMMSS(1, 0, 0)
        end.offsetMonth(1)
        subs = {
            "start": start,
            "end": end,
        }

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs


        # user01 invites user02
        txn = self.store.newTransaction()
        yield self._createResource(
            txn, "user01", "calendar", "test.ics", data1
        )
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy has SCHEDULE-STATUS update
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=1.2" in data)

        # user02 has an inbox item
        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user02 accepts
        yield self._updateResource(txn, "user02", "calendar", "", data2)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 has an inbox item
        txn = self.store.newTransaction()
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user01's copy has SCHEDULE-STATUS update
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=2.0" in data)
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()

        # user02 trashes event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()

        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's calendar copy shows user02 declined
        txn = self.store.newTransaction()

        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=DECLINED" in data)

        # user01's inbox copy also shows user02 declined
        data = yield self._getResourceData(txn, "user01", "inbox", "")
        self.assertTrue("PARTSTAT=DECLINED" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # result = yield txn.execSQL("select * from calendar_object", [])
        # for row in result:
        #     print("ROW", row)

        # user02's copy is in the trash only, and still has ACCEPTED
        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", trash2.name(), "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        yield txn.commit()

        # user02 moves it from trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", trash2.name(), "")
        yield resource.fromTrash()
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's calendar copy shows user02 accepted
        txn = self.store.newTransaction()

        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        # user01's inbox copy also shows user02 accepted
        data = yield self._getResourceData(txn, "user01", "inbox", "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user02 has nothing in trash
        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        yield txn.commit()


    @inlineCallbacks
    def test_trashScheduledFullyInPast(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        # A month in the past
        start = DateTime.getNowUTC()
        start.setHHMMSS(0, 0, 0)
        start.offsetMonth(-1)
        end = DateTime.getNowUTC()
        end.setHHMMSS(1, 0, 0)
        end.offsetMonth(-1)
        subs = {
            "start": start,
            "end": end,
        }

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=TENTATIVE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        # user01 invites user02
        txn = self.store.newTransaction()
        yield self._createResource(
            txn, "user01", "calendar", "test.ics", data1
        )
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy has SCHEDULE-STATUS update
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=1.2" in data)

        # user02 has an inbox item
        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user02 accepts
        yield self._updateResource(txn, "user02", "calendar", "", data2)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 has an inbox item
        txn = self.store.newTransaction()
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user01's copy has SCHEDULE-STATUS update
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=2.0" in data)
        self.assertTrue("PARTSTAT=TENTATIVE" in data)
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()

        # user01 trashes event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", "calendar", "test.ics")
        yield resource.remove()
        home1 = yield self._homeForUser(txn, "user01")
        trash1 = yield home1.getTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy is in the trash, still with user02 partstat
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", trash1.name(), "")
        self.assertTrue("PARTSTAT=TENTATIVE" in data)
        yield txn.commit()

        # user02's copy is cancelled
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user02", "inbox", "")
        self.assertTrue("METHOD:CANCEL" in data)
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()
        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("STATUS:CANCELLED" in data)
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()
        self.assertEquals(trash2, None)
        yield txn.commit()

        # user01 restores event from the trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", trash1.name(), "")
        data = yield self._getResourceData(txn, "user01", trash1.name(), "")
        yield resource.fromTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        # user01's copy should be back on their calendar
        data = yield self._getResourceData(txn, "user01", "calendar", "")
        self.assertTrue("PARTSTAT=TENTATIVE" in data)

        # user02's copy should be back on their calendar
        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=TENTATIVE" in data)


        yield txn.commit()


    @inlineCallbacks
    def test_trashScheduledFullyInPastAttendeeTrashedThenPutBack(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        # A month in the past
        start = DateTime.getNowUTC()
        start.setHHMMSS(0, 0, 0)
        start.offsetMonth(-1)
        end = DateTime.getNowUTC()
        end.setHHMMSS(1, 0, 0)
        end.offsetMonth(-1)
        subs = {
            "start": start,
            "end": end,
        }

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=TENTATIVE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        # user01 invites user02
        txn = self.store.newTransaction()
        yield self._createResource(
            txn, "user01", "calendar", "test.ics", data1
        )
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy has SCHEDULE-STATUS update
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=1.2" in data)

        # user02 has an inbox item
        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user02 accepts
        yield self._updateResource(txn, "user02", "calendar", "", data2)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 has an inbox item
        txn = self.store.newTransaction()
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user01's copy has SCHEDULE-STATUS update
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=2.0" in data)
        self.assertTrue("PARTSTAT=TENTATIVE" in data)

        # clear the inbox items
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()

        # user02 trashes event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's calendar copy shows user02 declined
        txn = self.store.newTransaction()

        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=DECLINED" in data)

        # user01's inbox copy also shows user02 declined
        data = yield self._getResourceData(txn, "user01", "inbox", "")
        self.assertTrue("PARTSTAT=DECLINED" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user02's copy is in the trash only, and still has TENTATIVE
        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", trash2.name(), "")
        self.assertTrue("PARTSTAT=TENTATIVE" in data)

        yield txn.commit()

        # user02 moves it from trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", trash2.name(), "")
        yield resource.fromTrash()
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's calendar copy shows user02 tentative again
        txn = self.store.newTransaction()

        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=TENTATIVE" in data)

        # user01's inbox copy also shows user02 tentative
        data = yield self._getResourceData(txn, "user01", "inbox", "")
        self.assertTrue("PARTSTAT=TENTATIVE" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user02 has nothing in trash
        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=TENTATIVE" in data)

        yield txn.commit()


    @inlineCallbacks
    def test_trashScheduledSpanningNow(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        # A month in the past
        start = DateTime.getNowUTC()
        start.setHHMMSS(0, 0, 0)
        start.offsetMonth(-1)
        end = DateTime.getNowUTC()
        end.setHHMMSS(1, 0, 0)
        end.offsetMonth(-1)
        subs = {
            "start": start,
            "end": end,
        }

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
RRULE:FREQ=WEEKLY;COUNT=20
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
RRULE:FREQ=WEEKLY;COUNT=20
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        # user01 invites user02
        txn = self.store.newTransaction()
        yield self._createResource(
            txn, "user01", "calendar", "test.ics", data1
        )
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy has SCHEDULE-STATUS update
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=1.2" in data)

        # user02 has an inbox item
        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user02 accepts
        yield self._updateResource(txn, "user02", "calendar", "", data2)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 has an inbox item
        txn = self.store.newTransaction()
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user01's copy has SCHEDULE-STATUS update
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=2.0" in data)
        self.assertTrue("PARTSTAT=ACCEPTED" in data)
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()

        # user01 trashes event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", "calendar", "test.ics")
        yield resource.remove()
        home1 = yield self._homeForUser(txn, "user01")
        trash1 = yield home1.getTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy is in the trash, still with user02 accepted
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", trash1.name(), "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)
        yield txn.commit()

        # user02's copy is cancelled
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user02", "inbox", "")
        self.assertTrue("METHOD:CANCEL" in data)
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()
        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("STATUS:CANCELLED" in data)
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()
        self.assertEquals(trash2, None)
        yield txn.commit()

        # user01 restores event from the trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", trash1.name(), "")
        trashedName = yield resource.fromTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        # user01's trash should be empty
        resourceNames = yield self._getResourceNames(txn, "user01", trash1.name())
        self.assertEquals(len(resourceNames), 0)

        # user01 should have two .ics
        resourceNames = yield self._getResourceNames(txn, "user01", "calendar")
        self.assertEquals(len(resourceNames), 2)
        self.assertTrue(trashedName in resourceNames)
        resourceNames.remove(trashedName)
        newName = resourceNames[0]

        # user01's test.ics -- verify it got split correctly, by making sure
        # it's got a count other than 20 now
        data = yield self._getResourceData(txn, "user01", "calendar", trashedName)
        self.assertTrue("COUNT=" in data)
        self.assertFalse("COUNT=20" in data)

        # user01's new .ics -- verify it got split correctly
        data = yield self._getResourceData(txn, "user01", "calendar", newName)
        self.assertTrue("RRULE:FREQ=WEEKLY;UNTIL=" in data)

        # user02's copy should be back on their calendar, and not in trash

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEquals(len(resourceNames), 1)
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()
        self.assertEquals(trash2, None)

        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=NEEDS-ACTION" in data)

        yield txn.commit()


    @inlineCallbacks
    def test_trashScheduledSpanningNowAttendeeTrashedThenPutBack(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        # A month in the past
        start = DateTime.getNowUTC()
        start.setHHMMSS(0, 0, 0)
        start.offsetMonth(-1)
        end = DateTime.getNowUTC()
        end.setHHMMSS(1, 0, 0)
        end.offsetMonth(-1)
        subs = {
            "start": start,
            "end": end,
        }

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
RRULE:FREQ=WEEKLY;COUNT=20
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-attendee-reply
DTSTART;TZID=America/Los_Angeles:%(start)s
DTEND;TZID=America/Los_Angeles:%(end)s
DTSTAMP:20150204T192546Z
RRULE:FREQ=WEEKLY;COUNT=20
SUMMARY:Scheduled
ORGANIZER;CN="User 01":mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user02@example.com
END:VEVENT
END:VCALENDAR
""" % subs

        # user01 invites user02
        txn = self.store.newTransaction()
        yield self._createResource(
            txn, "user01", "calendar", "test.ics", data1
        )
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy has SCHEDULE-STATUS update
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=1.2" in data)

        # user02 has an inbox item
        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user02 accepts
        yield self._updateResource(txn, "user02", "calendar", "", data2)
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01 has an inbox item
        txn = self.store.newTransaction()
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)

        # user01's copy has SCHEDULE-STATUS update
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("SCHEDULE-STATUS=2.0" in data)
        self.assertTrue("PARTSTAT=ACCEPTED" in data)
        resource = yield self._getResource(txn, "user02", "inbox", "")
        yield resource.remove()

        yield txn.commit()

        # user02 trashes event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", "calendar", "")
        yield resource.remove()
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy shows user02 declined
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=DECLINED" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        resourceNames = yield self._getResourceNames(txn, "user01", "calendar")
        self.assertEqual(len(resourceNames), 1)
        resourceNames = yield self._getResourceNames(txn, "user01", "inbox")
        self.assertEqual(len(resourceNames), 1)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user02's copy is in the trash only, and still has ACCEPTED
        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", trash2.name(), "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        yield txn.commit()
        # user02 moves it from trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user02", trash2.name(), "")
        yield resource.fromTrash()
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's calendar copy shows user02 accepted
        txn = self.store.newTransaction()

        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        # user01's inbox copy also shows user02 accepted
        data = yield self._getResourceData(txn, "user01", "inbox", "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)
        resource = yield self._getResource(txn, "user01", "inbox", "")
        yield resource.remove()

        # user02 has nothing in trash
        resourceNames = yield self._getResourceNames(txn, "user02", trash2.name())
        self.assertEqual(len(resourceNames), 0)

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEqual(len(resourceNames), 1)

        resourceNames = yield self._getResourceNames(txn, "user02", "inbox")
        self.assertEqual(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=ACCEPTED" in data)

        yield txn.commit()


    @inlineCallbacks
    def test_trashCalendar(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        txn = self.store.newTransaction()

        collection = yield self._collectionForUser(txn, "user01", "test", create=True)
        isInTrash = collection.isInTrash()
        self.assertFalse(isInTrash)
        whenTrashed = collection.whenTrashed()
        self.assertEquals(whenTrashed, None)

        home = yield self._homeForUser(txn, "user01")
        names = yield home.listChildren()
        self.assertTrue("test" in names)
        names = yield home.listChildren(onlyInTrash=True)
        self.assertFalse("test" in names)

        yield collection.remove()
        isInTrash = collection.isInTrash()
        self.assertTrue(isInTrash)
        whenTrashed = collection.whenTrashed()
        self.assertNotEquals(whenTrashed, None)

        collection = yield self._collectionForUser(txn, "user01", "test")
        self.assertEquals(collection, None)

        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        collection = yield self._collectionForUser(txn, "user01", "test")
        self.assertEquals(collection, None)
        home = yield self._homeForUser(txn, "user01")
        names = yield home.listChildren(onlyInTrash=True)
        trashedName = names[0]
        collection = yield self._collectionForUser(txn, "user01", trashedName, onlyInTrash=True)
        self.assertNotEquals(collection, None)
        home = yield self._homeForUser(txn, "user01")
        names = yield home.listChildren()
        self.assertFalse("test" in names)
        names = yield home.listChildren(onlyInTrash=True)
        self.assertTrue(trashedName in names)

        yield collection.fromTrash()

        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()
        home = yield self._homeForUser(txn, "user01")
        names = yield home.listChildren()
        self.assertTrue(trashedName in names)
        names = yield home.listChildren(onlyInTrash=True)
        self.assertFalse("test" in names)
        yield txn.commit()


    @inlineCallbacks
    def test_trashCalendarWithUnscheduled(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        txn = self.store.newTransaction()

        collection = yield self._collectionForUser(txn, "user01", "test", create=True)

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
DTSTART;TZID=America/Los_Angeles:20141108T093000
DTEND;TZID=America/Los_Angeles:20141108T103000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
RRULE:FREQ=DAILY
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
RECURRENCE-ID;TZID=America/Los_Angeles:20141111T093000
DTSTART;TZID=America/Los_Angeles:20141111T110000
DTEND;TZID=America/Los_Angeles:20141111T120000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

        # Create an object
        resource = yield collection.createObjectResourceWithName(
            "test.ics",
            Component.allFromString(data1)
        )

        # One object in collection
        objects = yield collection.listObjectResources()
        self.assertEquals(len(objects), 1)

        # No objects in trash
        home1 = yield self._homeForUser(txn, "user01")
        trash1 = yield home1.getTrash(create=True)
        trash = yield self._collectionForUser(txn, "user01", trash1.name())
        objects = yield trash.listObjectResources()
        self.assertEquals(len(objects), 0)

        # Verify it's not in the trash
        self.assertFalse(resource.isInTrash())
        trashed = resource.whenTrashed()
        self.assertTrue(trashed is None)

        collection = yield self._collectionForUser(txn, "user01", "test")
        resources = yield trash.trashForCollection(collection._resourceID)
        self.assertEquals(len(resources), 0)

        yield txn.commit()

        txn = self.store.newTransaction()
        collection = yield self._collectionForUser(txn, "user01", "test")
        yield collection.remove()
        yield txn.commit()

        txn = self.store.newTransaction()
        # One object in trash
        trash = yield self._collectionForUser(txn, "user01", trash1.name())
        objects = yield trash.listObjectResources()
        self.assertEquals(len(objects), 1)

        resources = yield trash.trashForCollection(collection._resourceID)
        self.assertEquals(len(resources), 1)

        home = yield self._homeForUser(txn, "user01")
        names = yield home.listChildren(onlyInTrash=True)
        trashedName = names[0]
        collection = yield self._collectionForUser(txn, "user01", trashedName, onlyInTrash=True)
        yield collection.fromTrash()

        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()
        home = yield self._homeForUser(txn, "user01")
        names = yield home.listChildren()
        self.assertTrue(trashedName in names)
        names = yield home.listChildren(onlyInTrash=True)
        self.assertFalse(trashedName in names)
        resourceNames = yield self._getResourceNames(txn, "user01", trashedName)
        self.assertEqual(len(resourceNames), 1)

        yield txn.commit()


    @inlineCallbacks
    def test_shareeDelete(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
DTSTART;TZID=America/Los_Angeles:20141108T093000
DTEND;TZID=America/Los_Angeles:20141108T103000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
RRULE:FREQ=DAILY
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
RECURRENCE-ID;TZID=America/Los_Angeles:20141111T093000
DTSTART;TZID=America/Los_Angeles:20141111T110000
DTEND;TZID=America/Los_Angeles:20141111T120000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

        txn = self.store.newTransaction()
        calendar1 = yield self._collectionForUser(txn, "user01", "calendar")

        yield calendar1.createObjectResourceWithName(
            "test.ics",
            Component.allFromString(data1)
        )

        shareeView = yield calendar1.inviteUIDToShare("user02", _BIND_MODE_WRITE, "summary")
        inviteUID = shareeView.shareUID()
        home2 = yield self._homeForUser(txn, "user02")
        shareeView = yield home2.acceptShare(inviteUID)
        calendarName2 = shareeView.name()
        yield self._collectionForUser(txn, "user02", calendarName2)
        yield txn.commit()

        txn = self.store.newTransaction()
        resource2 = yield self._getResource(txn, "user02", calendarName2, "test.ics")
        yield resource2.remove()
        home1 = yield self._homeForUser(txn, "user01")
        trash1 = yield home1.getTrash()
        yield txn.commit()

        txn = self.store.newTransaction()
        names = yield self._getResourceNames(txn, "user01", trash1.name())
        self.assertEquals(len(names), 1)
        names = yield self._getResourceNames(txn, "user01", "calendar")
        self.assertEquals(len(names), 0)
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()
        self.assertEquals(trash2, None)
        names = yield self._getResourceNames(txn, "user02", calendarName2)
        self.assertEquals(len(names), 0)

        resource = yield self._getResource(txn, "user01", trash1.name(), "")
        yield resource.fromTrash()

        yield txn.commit()

        txn = self.store.newTransaction()
        names = yield self._getResourceNames(txn, "user01", trash1.name())
        self.assertEquals(len(names), 0)
        names = yield self._getResourceNames(txn, "user01", "calendar")
        self.assertEquals(len(names), 1)
        home2 = yield self._homeForUser(txn, "user02")
        trash2 = yield home2.getTrash()
        self.assertEquals(trash2, None)
        names = yield self._getResourceNames(txn, "user02", calendarName2)
        self.assertEquals(len(names), 1)

        yield txn.commit()


    @inlineCallbacks
    def test_trashDuplicateUID(self):
        """
        Verify a duplicate uid is purged from the trash when a matching event
        is added to a collection
        """

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
DTSTART;TZID=America/Los_Angeles:20141108T093000
DTEND;TZID=America/Los_Angeles:20141108T103000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
RRULE:FREQ=DAILY
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
RECURRENCE-ID;TZID=America/Los_Angeles:20141111T093000
DTSTART;TZID=America/Los_Angeles:20141111T110000
DTEND;TZID=America/Los_Angeles:20141111T120000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

        txn = self.store.newTransaction()
        home = yield txn.calendarHomeWithUID("user01", create=True)
        collection = yield home.childWithName("calendar")
        # trash = yield home.getTrash(create=True)
        resource = yield collection.createObjectResourceWithName(
            "test.ics",
            Component.allFromString(data1)
        )
        yield resource.toTrash()
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()
        home = yield txn.calendarHomeWithUID("user01", create=False)
        collection = yield home.childWithName("calendar")
        resource = yield collection.createObjectResourceWithName(
            "duplicate.ics",
            Component.allFromString(data1)
        )
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # Verify the one in the trash has been deleted
        txn = self.store.newTransaction()
        home = yield txn.calendarHomeWithUID("user01")
        trash = yield home.getTrash(create=True)
        resourceNames = yield self._getResourceNames(txn, "user01", trash.name())
        self.assertEqual(len(resourceNames), 0)
        yield txn.commit()


    @inlineCallbacks
    def test_trashDuplicateUIDDifferentOrganizer(self):
        """
        Verify an attendee with a trashed copy of an event with a different
        organizer will have that copy removed.
        """

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        organizer1_data = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20140101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:duplicate
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user03@example.com
END:VEVENT
END:VCALENDAR
"""
        organizer2_data = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20140101T100000Z
DURATION:PT1H
SUMMARY:event 2
UID:duplicate
ORGANIZER:mailto:user02@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:user03@example.com
END:VEVENT
END:VCALENDAR
"""

        # user01 invites user03
        txn = self.store.newTransaction()
        home1 = yield txn.calendarHomeWithUID("user01", create=True)
        collection = yield home1.childWithName("calendar")
        yield collection.createObjectResourceWithName(
            "test.ics",
            Component.allFromString(organizer1_data)
        )
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user03 trashes the event
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user03", "calendar", "")
        yield resource.remove()
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user02 invites user03 using an event with the same uid
        txn = self.store.newTransaction()
        home2 = yield txn.calendarHomeWithUID("user02", create=True)
        collection = yield home2.childWithName("calendar")
        resource = yield collection.createObjectResourceWithName(
            "test.ics",
            Component.allFromString(organizer2_data)
        )
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user03's trash is now empty, and user03's copy is the invite from user02
        txn = self.store.newTransaction()
        resourceNames = yield self._getTrashNames(txn, "user03")
        self.assertEquals(len(resourceNames), 0)
        newData = yield self._getResourceData(txn, "user03", "calendar", "")
        self.assertTrue("user02" in newData)
        yield txn.commit()
        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)


    @inlineCallbacks
    def test_tool_emptyTrashForPrincipal(self):

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
DTSTART;TZID=America/Los_Angeles:20141108T093000
DTEND;TZID=America/Los_Angeles:20141108T103000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
RRULE:FREQ=DAILY
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
RECURRENCE-ID;TZID=America/Los_Angeles:20141111T093000
DTSTART;TZID=America/Los_Angeles:20141111T110000
DTEND;TZID=America/Los_Angeles:20141111T120000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
SEQUENCE:0
SUMMARY:repeating event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

        txn = self.store.newTransaction()
        calendar = yield self._collectionForUser(txn, "user01", "calendar")

        yield calendar.createObjectResourceWithName(
            "test.ics",
            Component.allFromString(data1)
        )
        yield txn.commit()

        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", "calendar", "test.ics")
        yield resource.remove()
        names = yield self._getTrashNames(txn, "user01")
        self.assertEquals(len(names), 1)
        yield txn.commit()

        txn = self.store.newTransaction()
        yield emptyTrashForPrincipal(None, self.store, "user01", 0, txn=txn, verbose=False)
        names = yield self._getTrashNames(txn, "user01")
        self.assertEquals(len(names), 0)
        result = yield txn.execSQL("select * from calendar_object", [])
        self.assertEquals(len(result), 0)
        yield txn.commit()

        # Add event again, and this time remove the containing calendar
        txn = self.store.newTransaction()
        calendar = yield self._collectionForUser(txn, "user01", "calendar")
        yield calendar.createObjectResourceWithName(
            "test.ics",
            Component.allFromString(data1)
        )
        yield txn.commit()

        txn = self.store.newTransaction()
        calendar = yield self._collectionForUser(txn, "user01", "calendar")
        result = yield txn.execSQL("select * from calendar_object", [])
        yield calendar.remove()
        home = yield self._homeForUser(txn, "user01")
        trashedCollections = yield home.children(onlyInTrash=True)
        self.assertEquals(len(trashedCollections), 1)
        yield txn.commit()

        txn = self.store.newTransaction()
        yield emptyTrashForPrincipal(None, self.store, "user01", 0, txn=txn, verbose=False)
        yield txn.commit()

        txn = self.store.newTransaction()
        home = yield self._homeForUser(txn, "user01")
        trashedCollections = yield home.children(onlyInTrash=True)
        self.assertEquals(len(trashedCollections), 0)
        result = yield txn.execSQL("select * from calendar_object", [])
        self.assertEquals(len(result), 0)
        yield txn.commit()


    @inlineCallbacks
    def test_trashedCalendars(self):
        """
        Verify home.calendars(onlyInTrash=) works
        """

        from twistedcaldav.stdconfig import config
        self.patch(config, "EnableTrashCollection", True)

        txn = self.store.newTransaction()
        home = yield self._homeForUser(txn, "user01")
        yield home.getTrash(create=True) # force loading trash
        calendars = yield home.calendars(onlyInTrash=False)
        self.assertEquals(
            set([c.name() for c in calendars]),
            set(["tasks", "inbox", "calendar"]) # trash not there
        )
        calendars = yield home.calendars(onlyInTrash=True)
        self.assertEquals(
            set([c.name() for c in calendars]),
            set() # trash not there either
        )
        yield txn.commit()

        txn = self.store.newTransaction()
        calendar = yield self._collectionForUser(txn, "user01", "calendar")
        resourceID = calendar._resourceID
        yield calendar.remove()
        yield txn.commit()

        txn = self.store.newTransaction()
        home = yield self._homeForUser(txn, "user01")
        yield home.getTrash(create=True) # force loading trash
        calendars = yield home.calendars(onlyInTrash=False)
        self.assertEquals(
            set([c.name() for c in calendars]),
            set(["tasks", "inbox"])
        )
        calendars = yield home.calendars(onlyInTrash=True)
        self.assertEquals(len(calendars), 1)
        self.assertEquals(calendars[0]._resourceID, resourceID)
        yield txn.commit()
