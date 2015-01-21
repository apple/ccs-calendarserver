##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.common.datastore.podding.test.util import MultiStoreConduitTest
from pycalendar.datetime import DateTime
from twistedcaldav.ical import Component, normalize_iCalStr
from txdav.common.icommondatastore import ObjectResourceNameAlreadyExistsError, \
    InvalidUIDError


class TestConduitAPI(MultiStoreConduitTest):
    """
    Test that the conduit api works.
    """

    nowYear = {"now": DateTime.getToday().getYear()}

    caldata1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid1
DTSTART:{now:04d}0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**nowYear)

    caldata1_changed = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid1
DTSTART:{now:04d}0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance changed
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**nowYear)

    caldata1_failed = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid1-failed
DTSTART:{now:04d}0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance changed
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**nowYear)

    caldata2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid2
DTSTART:{now:04d}0102T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:instance
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**nowYear)

    @inlineCallbacks
    def _remoteHome(self, txn, uid):
        """
        Create a synthetic external home object that maps to the actual remote home.

        @param ownerUID: directory uid of the user's home
        @type ownerUID: L{str}
        """

        from txdav.caldav.datastore.sql_external import CalendarHomeExternal
        recipient = yield txn.store().directoryService().recordWithUID(uid)
        resourceID = yield txn.store().conduit.send_home_resource_id(self, recipient)
        home = CalendarHomeExternal(txn, recipient.uid, resourceID) if resourceID is not None else None
        if home:
            home._childClass = home._childClass._externalClass
        returnValue(home)


    @inlineCallbacks
    def test_remote_home(self):
        """
        Test that a remote home can be accessed.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        self.assertEqual(home.id(), home01.id())
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_homechild_listobjects(self):
        """
        Test that a remote home L{listChildren} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        children01 = yield home01.listChildren()
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        self.assertEqual(home.id(), home01.id())
        children = yield home.listChildren()
        self.assertEqual(set(children), set(children01))
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_homechild_loadallobjects(self):
        """
        Test that a remote home L{loadChildren} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        children01 = yield home01.loadChildren()
        names01 = [child.name() for child in children01]
        ids01 = [child.id() for child in children01]
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        self.assertEqual(home.id(), home01.id())
        children = yield home.loadChildren()
        names = [child.name() for child in children]
        ids = [child.id() for child in children]
        self.assertEqual(set(names), set(names01))
        self.assertEqual(set(ids), set(ids01))
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_homechild_objectwith(self):
        """
        Test that a remote home L{loadChildren} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        self.assertEqual(calendar.id(), calendar01.id())
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_loadallobjects(self):
        """
        Test that a remote home child L{objectResources} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        objects = yield calendar.objectResources()
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].name(), "1.ics")
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_loadallobjectswithnames(self):
        """
        Test that a remote home child L{objectResourcesWithNames} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar01.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        objects = yield calendar.objectResourcesWithNames(("2.ics",))
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].name(), "2.ics")
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_listobjects(self):
        """
        Test that a remote home child L{listObjectResources} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar01.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        names = yield calendar.listObjectResources()
        self.assertEqual(set(names), set(("1.ics", "2.ics",)))
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_countobjects(self):
        """
        Test that a remote home child L{countObjectResources} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar01.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        count = yield calendar.countObjectResources()
        self.assertEqual(count, 2)
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_objectwith(self):
        """
        Test that a remote home child L{objectResourceWithName} and L{objectResourceWithUID} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        resource01 = yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar01.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")

        resource = yield calendar.objectResourceWithName("2.ics")
        self.assertEqual(resource.name(), "2.ics")

        resource = yield calendar.objectResourceWithName("foo.ics")
        self.assertEqual(resource, None)

        resource = yield calendar.objectResourceWithUID("uid1")
        self.assertEqual(resource.name(), "1.ics")

        resource = yield calendar.objectResourceWithUID("foo")
        self.assertEqual(resource, None)

        resource = yield calendar.objectResourceWithID(resource01.id())
        self.assertEqual(resource.name(), "1.ics")

        resource = yield calendar.objectResourceWithID(12345)
        self.assertEqual(resource, None)

        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_resourcenameforuid(self):
        """
        Test that a remote home child L{resourceNameForUID} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar01.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")

        name = yield calendar.resourceNameForUID("uid1")
        self.assertEqual(name, "1.ics")

        name = yield calendar.resourceNameForUID("uid2")
        self.assertEqual(name, "2.ics")

        name = yield calendar.resourceNameForUID("foo")
        self.assertEqual(name, None)

        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_resourceuidforname(self):
        """
        Test that a remote home child L{resourceUIDForName} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar01.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")

        uid = yield calendar.resourceUIDForName("1.ics")
        self.assertEqual(uid, "uid1")

        uid = yield calendar.resourceUIDForName("2.ics")
        self.assertEqual(uid, "uid2")

        uid = yield calendar.resourceUIDForName("foo.ics")
        self.assertEqual(uid, None)

        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_create(self):
        """
        Test that a remote object resource L{create} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        yield home01.childWithName("calendar")
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        resource = yield calendar.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield self.commitTransaction(1)

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        resource01 = yield calendar01.objectResourceWithName("1.ics")
        self.assertEqual(resource01.id(), resource.id())
        caldata = yield resource01.component()
        self.assertEqual(str(caldata), self.caldata1)
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        resource = yield calendar.objectResourceWithName("1.ics")
        caldata = yield resource.component()
        self.assertEqual(str(caldata), self.caldata1)
        yield self.commitTransaction(1)

        # Recreate fails
        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        self.assertFailure(
            calendar.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1)),
            ObjectResourceNameAlreadyExistsError,
        )
        yield self.abortTransaction(1)


    @inlineCallbacks
    def test_objectresource_setcomponent(self):
        """
        Test that a remote object resource L{setComponent} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        resource = yield calendar.objectResourceWithName("1.ics")
        changed = yield resource.setComponent(Component.fromString(self.caldata1_changed))
        self.assertFalse(changed)
        caldata = yield resource.component()
        self.assertEqual(normalize_iCalStr(str(caldata)), normalize_iCalStr(self.caldata1_changed))
        yield self.commitTransaction(1)

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        resource01 = yield calendar01.objectResourceWithName("1.ics")
        caldata = yield resource01.component()
        self.assertEqual(normalize_iCalStr(str(caldata)), normalize_iCalStr(self.caldata1_changed))
        yield self.commitTransaction(0)

        # Fail to set with different UID
        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        resource = yield calendar.objectResourceWithName("1.ics")
        self.assertFailure(
            resource.setComponent(Component.fromString(self.caldata1_failed)),
            InvalidUIDError,
        )
        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_component(self):
        """
        Test that a remote object resource L{component} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield calendar01.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")

        resource = yield calendar.objectResourceWithName("1.ics")
        caldata = yield resource.component()
        self.assertEqual(str(caldata), self.caldata1)

        resource = yield calendar.objectResourceWithName("2.ics")
        caldata = yield resource.component()
        self.assertEqual(str(caldata), self.caldata2)

        yield self.commitTransaction(1)


    @inlineCallbacks
    def test_objectresource_remove(self):
        """
        Test that a remote object resource L{component} works.
        """

        home01 = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.assertTrue(home01 is not None)
        calendar01 = yield home01.childWithName("calendar")
        yield calendar01.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        resource = yield calendar.objectResourceWithName("1.ics")
        yield resource.remove()
        yield self.commitTransaction(1)

        resource01 = yield self.calendarObjectUnderTest(
            txn=self.theTransactionUnderTest(0),
            home="user01",
            calendar_name="calendar",
            name="1.ics",
        )
        self.assertTrue(resource01 is None)
        yield self.commitTransaction(0)

        home = yield self._remoteHome(self.theTransactionUnderTest(1), "user01")
        self.assertTrue(home is not None)
        calendar = yield home.childWithName("calendar")
        resource = yield calendar.objectResourceWithName("1.ics")
        self.assertTrue(resource is None)
        yield self.commitTransaction(1)
