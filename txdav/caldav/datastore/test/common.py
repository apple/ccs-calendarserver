# -*- test-case-name: txdav.caldav.datastore -*-
##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
Tests for common calendar store API functions.
"""

from StringIO import StringIO
import os

from twisted.internet.defer import Deferred, inlineCallbacks, returnValue, \
    maybeDeferred
from twisted.internet.protocol import Protocol
from twisted.python import hashlib

from twext.python.clsprop import classproperty
from twext.python.vcomponent import VComponent
from twext.python.filepath import CachingFilePath as FilePath
from twext.enterprise.ienterprise import AlreadyFinishedError
from twext.web2.http_headers import MimeType

from txdav.xml.element import WebDAVUnknownElement, ResourceType
from txdav.idav import IPropertyStore, IDataStore
from txdav.base.propertystore.base import PropertyName
from txdav.common.icommondatastore import HomeChildNameAlreadyExistsError, \
    ICommonTransaction
from txdav.common.icommondatastore import InvalidObjectResourceError
from txdav.common.icommondatastore import NoSuchHomeChildError
from txdav.common.icommondatastore import NoSuchObjectResourceError
from txdav.common.icommondatastore import ObjectResourceNameAlreadyExistsError
from txdav.common.inotifications import INotificationObject
from txdav.common.datastore.test.util import CommonCommonTests
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE, _BIND_MODE_READ

from txdav.caldav.icalendarstore import (
    ICalendarObject, ICalendarHome,
    ICalendar, IAttachment, ICalendarTransaction)


from twistedcaldav.customxml import InviteNotification, InviteSummary
from txdav.caldav.icalendarstore import IAttachmentStorageTransport
from txdav.caldav.icalendarstore import QuotaExceeded
from txdav.common.datastore.test.util import deriveQuota
from txdav.common.datastore.test.util import withSpecialQuota
from txdav.common.icommondatastore import ConcurrentModification
from twistedcaldav.ical import Component
from twistedcaldav.config import config

storePath = FilePath(__file__).parent().child("calendar_store")

homeRoot = storePath.child("ho").child("me").child("home1")
cal1Root = homeRoot.child("calendar_1")

homeSplitsRoot = storePath.child("ho").child("me").child("home_splits")
cal1SplitsRoot = homeSplitsRoot.child("calendar_1")
cal2SplitsRoot = homeSplitsRoot.child("calendar_2")

homeNoSplitsRoot = storePath.child("ho").child("me").child("home_no_splits")
cal1NoSplitsRoot = homeNoSplitsRoot.child("calendar_1")

calendar1_objectNames = [
    "1.ics",
    "2.ics",
    "3.ics",
    "4.ics",
]

home1_calendarNames = [
    "calendar_1",
    "calendar_2",
    "calendar_empty",
]

OTHER_HOME_UID = "home_splits"

test_event_text = (
    "BEGIN:VCALENDAR\r\n"
      "VERSION:2.0\r\n"
      "PRODID:-//Apple Inc.//iCal 4.0.1//EN\r\n"
      "CALSCALE:GREGORIAN\r\n"
      "BEGIN:VTIMEZONE\r\n"
        "TZID:US/Pacific\r\n"
        "BEGIN:DAYLIGHT\r\n"
          "TZOFFSETFROM:-0800\r\n"
          "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\n"
          "DTSTART:20070311T020000\r\n"
          "TZNAME:PDT\r\n"
          "TZOFFSETTO:-0700\r\n"
        "END:DAYLIGHT\r\n"
        "BEGIN:STANDARD\r\n"
          "TZOFFSETFROM:-0700\r\n"
          "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\n"
          "DTSTART:20071104T020000\r\n"
          "TZNAME:PST\r\n"
          "TZOFFSETTO:-0800\r\n"
        "END:STANDARD\r\n"
      "END:VTIMEZONE\r\n"
      "BEGIN:VEVENT\r\n"
        "CREATED:20100203T013849Z\r\n"
        "UID:uid-test\r\n"
        "DTEND;TZID=US/Pacific:20100207T173000\r\n"
        "TRANSP:OPAQUE\r\n"
        "SUMMARY:New Event\r\n"
        "DTSTART;TZID=US/Pacific:20100207T170000\r\n"
        "DTSTAMP:20100203T013909Z\r\n"
        "SEQUENCE:3\r\n"
        "BEGIN:VALARM\r\n"
          "X-WR-ALARMUID:1377CCC7-F85C-4610-8583-9513D4B364E1\r\n"
          "TRIGGER:-PT20M\r\n"
          "ATTACH:Basso\r\n"
          "ACTION:AUDIO\r\n"
        "END:VALARM\r\n"
      "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)



test_event_notCalDAV_text = (
    "BEGIN:VCALENDAR\r\n"
      "VERSION:2.0\r\n"
      "PRODID:-//Apple Inc.//iCal 4.0.1//EN\r\n"
      "CALSCALE:GREGORIAN\r\n"
      "BEGIN:VEVENT\r\n"
        "CREATED:20100203T013849Z\r\n"
        "UID:test\r\n"
        "DTEND;TZID=US/Pacific:20100207T173000\r\n" # TZID without VTIMEZONE
        "TRANSP:OPAQUE\r\n"
        "SUMMARY:New Event\r\n"
        "DTSTART;TZID=US/Pacific:20100207T170000\r\n"
        "DTSTAMP:20100203T013909Z\r\n"
        "SEQUENCE:3\r\n"
        "BEGIN:VALARM\r\n"
          "X-WR-ALARMUID:1377CCC7-F85C-4610-8583-9513D4B364E1\r\n"
          "TRIGGER:-PT20M\r\n"
          "ATTACH:Basso\r\n"
          "ACTION:AUDIO\r\n"
        "END:VALARM\r\n"
      "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)



event1modified_text = test_event_text.replace(
    "\r\nUID:uid-test\r\n",
    "\r\nUID:uid1\r\n"
)


class CaptureProtocol(Protocol):
    """
    A proocol that captures the data delivered to it, and calls back a Deferred
    with that data.

    @ivar deferred: a L{Deferred} which will be called back with all the data
        yet delivered to C{dataReceived} when C{connectionLost} is called.
    """

    def __init__(self):
        self.deferred = Deferred()
        self.io = StringIO()
        self.dataReceived = self.io.write


    def connectionLost(self, reason):
        self.deferred.callback(self.io.getvalue())



class CommonTests(CommonCommonTests):
    """
    Tests for common functionality of interfaces defined in
    L{txdav.caldav.icalendarstore}.
    """

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
    metadata5 = {
        "accessMode": "PUBLIC",
        "isScheduleObject": True,
        "scheduleTag": "abc5",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }

    md5Values = (
        hashlib.md5("1234").hexdigest(),
        hashlib.md5("5678").hexdigest(),
        hashlib.md5("9ABC").hexdigest(),
        hashlib.md5("DEFG").hexdigest(),
        hashlib.md5("HIJK").hexdigest(),
    )

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
            "calendar_2": {},
            "calendar_empty": {},
            "not_a_calendar": None
        },
        "not_a_home": None,
        "home_splits": {
            "calendar_1": {
                "1.ics": (cal1SplitsRoot.child("1.ics").getContent(), metadata1),
                "2.ics": (cal1SplitsRoot.child("2.ics").getContent(), metadata2),
                "3.ics": (cal1SplitsRoot.child("3.ics").getContent(), metadata3),
            },
            "calendar_2": {
                "1.ics": (cal2SplitsRoot.child("1.ics").getContent(), metadata1),
                "2.ics": (cal2SplitsRoot.child("2.ics").getContent(), metadata2),
                "3.ics": (cal2SplitsRoot.child("3.ics").getContent(), metadata3),
                "4.ics": (cal2SplitsRoot.child("4.ics").getContent(), metadata4),
                "5.ics": (cal2SplitsRoot.child("5.ics").getContent(), metadata4),
            },
        },
        "home_no_splits": {
            "calendar_1": {
                "1.ics": (cal1NoSplitsRoot.child("1.ics").getContent(), metadata1),
                "2.ics": (cal1NoSplitsRoot.child("2.ics").getContent(), metadata2),
                "3.ics": (cal1NoSplitsRoot.child("3.ics").getContent(), metadata3),
            },
        },
        "home_splits_shared": {
            "calendar_1": {},
        },
    }
    md5s = {
        "home1": {
            "calendar_1": {
                "1.ics": md5Values[0],
                "2.ics": md5Values[1],
                "3.ics": md5Values[2],
                "4.ics": md5Values[3],
            },
            "calendar_2": {},
            "calendar_empty": {},
            "not_a_calendar": None
        },
        "not_a_home": None,
        "home_splits": {
            "calendar_1": {
                "1.ics": md5Values[0],
                "2.ics": md5Values[1],
                "3.ics": md5Values[2],
            },
            "calendar_2": {
                "1.ics": md5Values[0],
                "2.ics": md5Values[1],
                "3.ics": md5Values[2],
                "4.ics": md5Values[3],
                "5.ics": md5Values[4],
            },
        },
        "home_no_splits": {
            "calendar_1": {
                "1.ics": md5Values[0],
                "2.ics": md5Values[1],
                "3.ics": md5Values[2],
            },
        },
    }


    def storeUnderTest(self):
        """
        Subclasses must override this to return an L{ICommonDataStore} provider
        which adheres to the structure detailed by L{CommonTests.requirements}.
        This attribute is a dict of dict of dicts; the outermost layer
        representing UIDs mapping to calendar homes, then calendar names mapping
        to calendar collections, and finally calendar object names mapping to
        calendar object text.
        """
        raise NotImplementedError()


    @inlineCallbacks
    def homeUnderTest(self, txn=None, name="home1"):
        """
        Get the calendar home detailed by C{requirements['home1']}.
        """
        if txn is None:
            txn = self.transactionUnderTest()
        returnValue((yield txn.calendarHomeWithUID(name)))


    @inlineCallbacks
    def calendarUnderTest(self, txn=None, name="calendar_1", home="home1"):
        """
        Get the calendar detailed by C{requirements['home1']['calendar_1']}.
        """
        returnValue((yield
            (yield self.homeUnderTest(txn, home)).calendarWithName(name))
        )


    @inlineCallbacks
    def calendarObjectUnderTest(self, name="1.ics", txn=None):
        """
        Get the calendar detailed by
        C{requirements['home1']['calendar_1'][name]}.
        """
        returnValue((yield (yield self.calendarUnderTest(txn))
                     .calendarObjectWithName(name)))


    def test_calendarStoreProvides(self):
        """
        The calendar store provides L{IDataStore} and its required attributes.
        """
        calendarStore = self.storeUnderTest()
        self.assertProvides(IDataStore, calendarStore)


    def test_transactionProvides(self):
        """
        The transactions generated by the calendar store provide
        L{ICommonStoreTransaction}, L{ICalendarTransaction}, and their
        respectively required attributes.
        """
        txn = self.transactionUnderTest()
        self.assertProvides(ICommonTransaction, txn)
        self.assertProvides(ICalendarTransaction, txn)


    @inlineCallbacks
    def test_homeProvides(self):
        """
        The calendar homes generated by the calendar store provide
        L{ICalendarHome} and its required attributes.
        """
        self.assertProvides(ICalendarHome, (yield self.homeUnderTest()))


    @inlineCallbacks
    def test_calendarProvides(self):
        """
        The calendars generated by the calendar store provide L{ICalendar} and
        its required attributes.
        """
        self.assertProvides(ICalendar, (yield self.calendarUnderTest()))


    @inlineCallbacks
    def test_calendarObjectProvides(self):
        """
        The calendar objects generated by the calendar store provide
        L{ICalendarObject} and its required attributes.
        """
        self.assertProvides(
            ICalendarObject, (yield self.calendarObjectUnderTest())
        )


    @inlineCallbacks
    def notificationUnderTest(self):
        txn = self.transactionUnderTest()
        notifications = yield txn.notificationsWithUID("home1")
        inviteNotification = InviteNotification()
        yield notifications.writeNotificationObject("abc", inviteNotification,
            inviteNotification.toxml())
        notificationObject = yield notifications.notificationObjectWithUID("abc")
        returnValue(notificationObject)


    @inlineCallbacks
    def test_notificationObjectProvides(self):
        """
        The objects retrieved from the notification home (the object returned
        from L{notificationsWithUID}) provide L{INotificationObject}.
        """
        notificationObject = yield self.notificationUnderTest()
        self.assertProvides(INotificationObject, notificationObject)


    @inlineCallbacks
    def test_notificationSyncToken(self):
        """
        L{ICalendar.resourceNamesSinceToken} will return the names of calendar
        objects changed or deleted since 
        """
        txn = self.transactionUnderTest()
        coll = yield txn.notificationsWithUID("home1")
        invite1 = InviteNotification()
        yield coll.writeNotificationObject("1", invite1, invite1.toxml())
        st = yield coll.syncToken()
        yield coll.writeNotificationObject("2", invite1, invite1.toxml())
        rev = self.token2revision(st)
        yield coll.removeNotificationObjectWithUID("1")
        st2 = yield coll.syncToken()
        rev2 = self.token2revision(st2)
        changed, deleted = yield coll.resourceNamesSinceToken(rev)
        self.assertEquals(set(changed), set(["2.xml"]))
        self.assertEquals(set(deleted), set(["1.xml"]))
        changed, deleted = yield coll.resourceNamesSinceToken(rev2)
        self.assertEquals(set(changed), set([]))
        self.assertEquals(set(deleted), set([]))


    @inlineCallbacks
    def test_replaceNotification(self):
        """
        L{INotificationCollection.writeNotificationObject} will silently
        overwrite the notification object.
        """
        notifications = yield self.transactionUnderTest().notificationsWithUID(
            "home1"
        )
        inviteNotification = InviteNotification()
        yield notifications.writeNotificationObject("abc", inviteNotification,
            inviteNotification.toxml())
        inviteNotification2 = InviteNotification(InviteSummary("a summary"))
        yield notifications.writeNotificationObject(
            "abc", inviteNotification, inviteNotification2.toxml())
        abc = yield notifications.notificationObjectWithUID("abc")
        self.assertEquals((yield abc.xmldata()), inviteNotification2.toxml())


    @inlineCallbacks
    def test_addRemoveNotification(self):
        """
        L{INotificationCollection.writeNotificationObject} will silently
        overwrite the notification object.
        """
        # Prime the home collection first
        yield self.transactionUnderTest().notificationsWithUID(
            "home1"
        )
        yield self.commit()

        notifications = yield self.transactionUnderTest().notificationsWithUID(
            "home1"
        )
        self.notifierFactory.reset()
        inviteNotification = InviteNotification()
        yield notifications.writeNotificationObject("abc", inviteNotification,
            inviteNotification.toxml())

        yield self.commit()

        # Make sure notification fired after commit
        self.assertEquals(self.notifierFactory.history,
            [
                ("update", "CalDAV|home1"),
                ("update", "CalDAV|home1/notification"),
            ]
        )

        notifications = yield self.transactionUnderTest().notificationsWithUID(
            "home1"
        )
        self.notifierFactory.reset()
        yield notifications.removeNotificationObjectWithUID("abc")
        abc = yield notifications.notificationObjectWithUID("abc")
        self.assertEquals(abc, None)

        yield self.commit()

        # Make sure notification fired after commit
        self.assertEquals(self.notifierFactory.history,
            [
                ("update", "CalDAV|home1"),
                ("update", "CalDAV|home1/notification"),
            ]
        )


    @inlineCallbacks
    def test_loadAllNotifications(self):
        """
        L{INotificationCollection.writeNotificationObject} will silently
        overwrite the notification object.
        """
        notifications = yield self.transactionUnderTest().notificationsWithUID(
            "home1"
        )
        inviteNotification = InviteNotification()
        yield notifications.writeNotificationObject("abc", inviteNotification,
            inviteNotification.toxml())
        inviteNotification2 = InviteNotification(InviteSummary("a summary"))
        yield notifications.writeNotificationObject(
            "def", inviteNotification, inviteNotification2.toxml())

        yield self.commit()

        notifications = yield self.transactionUnderTest().notificationsWithUID(
            "home1"
        )
        allObjects = yield notifications.notificationObjects()
        self.assertEqual(set([obj.uid() for obj in allObjects]),
                         set(["abc", "def"]))


    @inlineCallbacks
    def test_notificationObjectMetaData(self):
        """
        The objects retrieved from the notification home have various
        methods which return metadata values.
        """
        notification = yield self.notificationUnderTest()
        self.assertIsInstance(notification.md5(), basestring)
        self.assertIsInstance(notification.size(), int)
        self.assertIsInstance(notification.created(), int)
        self.assertIsInstance(notification.modified(), int)


    @inlineCallbacks
    def test_notificationObjectParent(self):
        """
        L{INotificationObject.notificationCollection} returns the
        L{INotificationCollection} that the object was retrieved from.
        """
        txn = self.transactionUnderTest()
        collection = yield txn.notificationsWithUID("home1")
        notification = yield self.notificationUnderTest()
        self.assertIdentical(collection, notification.notificationCollection())


    @inlineCallbacks
    def test_notifierID(self):
        home = yield self.homeUnderTest()
        self.assertEquals(home.notifierID(), "CalDAV|home1")
        calendar = yield home.calendarWithName("calendar_1")
        self.assertEquals(calendar.notifierID(), "CalDAV|home1")
        self.assertEquals(calendar.notifierID(label="collection"), "CalDAV|home1/calendar_1")

    @inlineCallbacks
    def test_nodeNameSuccess(self):
        home = yield self.homeUnderTest()
        name = yield home.nodeName()
        self.assertEquals(name, "/CalDAV/example.com/home1/")

    @inlineCallbacks
    def test_nodeNameFailure(self):
        # The StubNodeCacher is set up to fail when the node name has the
        # word "fail" in it, for testing the failure mode:
        home = yield self.transactionUnderTest().calendarHomeWithUID("fail",
            create=True)
        name = yield home.nodeName()
        self.assertEquals(name, None)

    @inlineCallbacks
    def test_calendarHomeWithUID_exists(self):
        """
        Finding an existing calendar home by UID results in an object that
        provides L{ICalendarHome} and has a C{uid()} method that returns the
        same value that was passed in.
        """
        calendarHome = (yield self.transactionUnderTest()
                        .calendarHomeWithUID("home1"))
        self.assertEquals(calendarHome.uid(), "home1")
        self.assertProvides(ICalendarHome, calendarHome)


    @inlineCallbacks
    def test_calendarHomeWithUID_absent(self):
        """
        L{ICommonStoreTransaction.calendarHomeWithUID} should return C{None}
        when asked for a non-existent calendar home.
        """
        txn = self.transactionUnderTest()
        self.assertEquals((yield txn.calendarHomeWithUID("xyzzy")), None)


    @inlineCallbacks
    def test_calendarTasks_exists(self):
        """
        L{ICalendarHome.createdHome} creates a calendar only, or a calendar and tasks
        collection only, in addition to inbox.
        """
        self.patch(config, "RestrictCalendarsToOneComponentType", False)
        home1 = yield self.transactionUnderTest().calendarHomeWithUID("home_provision1", create=True)
        for name in ("calendar", "inbox",):
            calendar = yield home1.calendarWithName(name)
            if calendar is None:
                self.fail("calendar %r didn't exist" % (name,))
            self.assertProvides(ICalendar, calendar)
            self.assertEquals(calendar.name(), name)
        for name in ("tasks",):
            calendar = yield home1.calendarWithName(name)
            if calendar is not None:
                self.fail("calendar %r exists" % (name,))

        self.patch(config, "RestrictCalendarsToOneComponentType", True)
        home2 = yield self.transactionUnderTest().calendarHomeWithUID("home_provision2", create=True)
        for name in ("calendar", "tasks", "inbox",):
            calendar = yield home2.calendarWithName(name)
            if calendar is None:
                self.fail("calendar %r didn't exist" % (name,))
            self.assertProvides(ICalendar, calendar)
            self.assertEquals(calendar.name(), name)

    @inlineCallbacks
    def test_calendarWithName_exists(self):
        """
        L{ICalendarHome.calendarWithName} returns an L{ICalendar} provider,
        whose name matches the one passed in.
        """
        home = yield self.homeUnderTest()
        for name in home1_calendarNames:
            calendar = yield home.calendarWithName(name)
            if calendar is None:
                self.fail("calendar %r didn't exist" % (name,))
            self.assertProvides(ICalendar, calendar)
            self.assertEquals(calendar.name(), name)


    @inlineCallbacks
    def test_calendarRename(self):
        """
        L{ICalendar.rename} changes the name of the L{ICalendar}.
        """
        home = yield self.homeUnderTest()
        calendar = yield home.calendarWithName("calendar_1")
        yield calendar.rename("some_other_name")
        @inlineCallbacks
        def positiveAssertions():
            self.assertEquals(calendar.name(), "some_other_name")
            self.assertEquals(
                calendar, (yield home.calendarWithName("some_other_name")))
            self.assertEquals(
                None, (yield home.calendarWithName("calendar_1")))
        yield positiveAssertions()
        yield self.commit()
        home = yield self.homeUnderTest()
        calendar = yield home.calendarWithName("some_other_name")
        yield positiveAssertions()
        # FIXME: revert
        # FIXME: test for multiple renames
        # FIXME: test for conflicting renames (a->b, c->a in the same txn)


    @inlineCallbacks
    def test_calendarWithName_absent(self):
        """
        L{ICalendarHome.calendarWithName} returns C{None} for calendars which
        do not exist.
        """
        home = yield self.homeUnderTest()
        calendar = yield home.calendarWithName("xyzzy")
        self.assertEquals(calendar, None)


    @inlineCallbacks
    def test_createCalendarWithName_absent(self):
        """
        L{ICalendarHome.createCalendarWithName} creates a new L{ICalendar} that
        can be retrieved with L{ICalendarHome.calendarWithName}.
        """
        home = yield self.homeUnderTest()
        name = "new"
        self.assertIdentical((yield home.calendarWithName(name)), None)
        yield home.createCalendarWithName(name)
        self.assertNotIdentical((yield home.calendarWithName(name)), None)
        @inlineCallbacks
        def checkProperties():
            calendarProperties = (
                yield home.calendarWithName(name)).properties()
            self.assertEquals(
                calendarProperties[
                    PropertyName.fromString(ResourceType.sname())
                ],
                ResourceType.calendar #@UndefinedVariable
            )
        yield checkProperties()

        yield self.commit()

        # Make sure notification fired after commit
        self.assertTrue(("update", "CalDAV|home1") in self.notifierFactory.history)

        # Make sure it's available in a new transaction; i.e. test the commit.
        home = yield self.homeUnderTest()
        self.assertNotIdentical((yield home.calendarWithName(name)), None)

        # Sanity check: are the properties actually persisted?  Check in
        # subsequent transaction.
        yield checkProperties()

        # FIXME: no independent testing of the property store's persistence
        # right now


    @inlineCallbacks
    def test_createCalendarWithName_exists(self):
        """
        L{ICalendarHome.createCalendarWithName} raises
        L{CalendarAlreadyExistsError} when the name conflicts with an already-
        existing 
        """
        home = yield self.homeUnderTest()
        for name in home1_calendarNames:
            yield self.failUnlessFailure(
                maybeDeferred(home.createCalendarWithName, name),
                HomeChildNameAlreadyExistsError
            )


    @inlineCallbacks
    def test_removeCalendarWithName_exists(self):
        """
        L{ICalendarHome.removeCalendarWithName} removes a calendar that already
        exists.
        """
        home = yield self.homeUnderTest()

        # FIXME: test transactions
        for name in home1_calendarNames:
            self.assertNotIdentical((yield home.calendarWithName(name)), None)
            yield home.removeCalendarWithName(name)
            self.assertEquals((yield home.calendarWithName(name)), None)

        yield self.commit()

        # Make sure notification fired after commit
        self.assertEquals(
            self.notifierFactory.history,
            [
                ("update", "CalDAV|home1"),
                ("update", "CalDAV|home1/calendar_1"),
                ("update", "CalDAV|home1"),
                ("update", "CalDAV|home1/calendar_2"),
                ("update", "CalDAV|home1"),
                ("update", "CalDAV|home1/calendar_empty"),
            ]
        )


    @inlineCallbacks
    def test_removeCalendarWithName_absent(self):
        """
        Attempt to remove an non-existing calendar should raise.
        """
        home = yield self.homeUnderTest()
        yield self.failUnlessFailure(
            maybeDeferred(home.removeCalendarWithName, "xyzzy"),
            NoSuchHomeChildError
        )


    @inlineCallbacks
    def test_supportedComponentSet(self):
        """
        Attempt to remove an non-existing calendar object should raise.
        """
        calendar = yield self.calendarUnderTest()

        result = yield maybeDeferred(calendar.getSupportedComponents)
        self.assertEquals(result, None)

        yield maybeDeferred(calendar.setSupportedComponents, "VEVENT,VTODO")
        result = yield maybeDeferred(calendar.getSupportedComponents)
        self.assertEquals(result, "VEVENT,VTODO")

        yield maybeDeferred(calendar.setSupportedComponents, None)
        result = yield maybeDeferred(calendar.getSupportedComponents)
        self.assertEquals(result, None)

    @inlineCallbacks
    def test_countComponentTypes(self):
        """
        Test Calendar._countComponentTypes to make sure correct counts are returned.
        """

        tests = (
            ("calendar_1", (("VEVENT", 3),)),
            ("calendar_2", (("VEVENT", 3), ("VTODO", 2))),
        )

        for calname, results in tests:
            testalendar = yield (yield self.transactionUnderTest().calendarHomeWithUID(
                "home_splits")).calendarWithName(calname)
            result = yield maybeDeferred(testalendar._countComponentTypes)
            self.assertEquals(result, results)

    @inlineCallbacks
    def test_calendarObjects(self):
        """
        L{ICalendar.calendarObjects} will enumerate the calendar objects present
        in the filesystem, in name order, but skip those with hidden names.
        """
        calendar1 = yield self.calendarUnderTest()
        calendarObjects = list((yield calendar1.calendarObjects()))

        for calendarObject in calendarObjects:
            self.assertProvides(ICalendarObject, calendarObject)
            self.assertEquals(
                (yield calendar1.calendarObjectWithName(calendarObject.name())),
                calendarObject
            )

        self.assertEquals(
            set(list(o.name() for o in calendarObjects)),
            set(calendar1_objectNames)
        )


    @inlineCallbacks
    def test_calendarObjectsWithRemovedObject(self):
        """
        L{ICalendar.calendarObjects} skips those objects which have been
        removed by L{Calendar.removeCalendarObjectWithName} in the same
        transaction, even if it has not yet been committed.
        """
        calendar1 = yield self.calendarUnderTest()
        yield calendar1.removeCalendarObjectWithName("2.ics")
        calendarObjects = list((yield calendar1.calendarObjects()))
        self.assertEquals(set(o.name() for o in calendarObjects),
                          set(calendar1_objectNames) - set(["2.ics"]))


    @inlineCallbacks
    def test_calendarObjectRemoveConcurrent(self):
        """
        If a transaction, C{A}, is examining an L{ICalendarObject} C{O} while
        another transaction, C{B}, deletes O, L{O.component()} should raise
        L{ConcurrentModification}.  (This assumes that we are in the default
        serialization level, C{READ COMMITTED}.  This test might fail if
        something changes that.)
        """
        calendarObject = yield self.calendarObjectUnderTest()
        ctxn = self.concurrentTransaction()
        calendar1prime = yield self.calendarUnderTest(ctxn)
        yield calendar1prime.removeCalendarObjectWithName("1.ics")
        yield ctxn.commit()
        try:
            retrieval = yield calendarObject.component()
        except ConcurrentModification:
            pass
        else:
            self.fail("ConcurrentModification not raised, %r returned." %
                      (retrieval,))


    @inlineCallbacks
    def test_ownerCalendarHome(self):
        """
        L{ICalendar.ownerCalendarHome} should match the home UID.
        """
        self.assertEquals(
            (yield self.calendarUnderTest()).ownerCalendarHome().uid(),
            (yield self.homeUnderTest()).uid()
        )


    @inlineCallbacks
    def test_calendarObjectWithName_exists(self):
        """
        L{ICalendar.calendarObjectWithName} returns an L{ICalendarObject}
        provider for calendars which already exist.
        """
        calendar1 = yield self.calendarUnderTest()
        for name in calendar1_objectNames:
            calendarObject = yield calendar1.calendarObjectWithName(name)
            self.assertProvides(ICalendarObject, calendarObject)
            self.assertEquals(calendarObject.name(), name)
            # FIXME: add more tests based on CommonTests.requirements


    @inlineCallbacks
    def test_calendarObjectWithName_absent(self):
        """
        L{ICalendar.calendarObjectWithName} returns C{None} for calendars which
        don't exist.
        """
        calendar1 = yield self.calendarUnderTest()
        self.assertEquals((yield calendar1.calendarObjectWithName("xyzzy")), None)


    @inlineCallbacks
    def test_removeCalendarObjectWithUID_exists(self):
        """
        Remove an existing calendar object.
        """
        calendar = yield self.calendarUnderTest()
        for name in calendar1_objectNames:
            uid = (u'uid' + name.rstrip(".ics"))
            self.assertNotIdentical((yield calendar.calendarObjectWithUID(uid)),
                                    None)
            yield calendar.removeCalendarObjectWithUID(uid)
            self.assertEquals(
                (yield calendar.calendarObjectWithUID(uid)),
                None
            )
            self.assertEquals(
                (yield calendar.calendarObjectWithName(name)),
                None
            )

        # Make sure notifications are fired after commit
        yield self.commit()
        self.assertEquals(
            self.notifierFactory.history,
            [
                ("update", "CalDAV|home1"),
                ("update", "CalDAV|home1/calendar_1"),
            ]
        )

    @inlineCallbacks
    def test_removeCalendarObjectWithName_exists(self):
        """
        Remove an existing calendar object.
        """
        calendar = yield self.calendarUnderTest()
        for name in calendar1_objectNames:
            self.assertNotIdentical(
                (yield calendar.calendarObjectWithName(name)), None
            )
            yield calendar.removeCalendarObjectWithName(name)
            self.assertIdentical(
                (yield calendar.calendarObjectWithName(name)), None
            )


    @inlineCallbacks
    def test_removeCalendarObjectWithName_absent(self):
        """
        Attempt to remove an non-existing calendar object should raise.
        """
        calendar = yield self.calendarUnderTest()
        yield self.failUnlessFailure(
            maybeDeferred(calendar.removeCalendarObjectWithName, "xyzzy"),
            NoSuchObjectResourceError
        )


    @inlineCallbacks
    def test_calendarName(self):
        """
        L{Calendar.name} reflects the name of the calendar.
        """
        self.assertEquals((yield self.calendarUnderTest()).name(), "calendar_1")


    @inlineCallbacks
    def test_shareWith(self):
        """
        L{ICalendar.shareWith} will share a calendar with a given home UID.
        """
        cal = yield self.calendarUnderTest()
        other = yield self.homeUnderTest(name=OTHER_HOME_UID)
        newCalName = yield cal.shareWith(other, _BIND_MODE_WRITE)
        self.sharedName = newCalName
        yield self.commit()
        normalCal = yield self.calendarUnderTest()
        otherHome = yield self.homeUnderTest(name=OTHER_HOME_UID)
        otherCal = yield otherHome.sharedChildWithName(newCalName)
        self.assertNotIdentical(otherCal, None)
        self.assertEqual(
            (yield
             (yield otherCal.calendarObjectWithName("1.ics")).component()),
            (yield
             (yield normalCal.calendarObjectWithName("1.ics")).component())
        )
        # Check legacy shares database too, since that's what the protocol layer
        # is still using to list things.
        self.assertEqual(
            [(record.shareuid, record.localname) for record in
             (yield otherHome.retrieveOldShares().allRecords())],
            [(newCalName, newCalName)]
        )


    @inlineCallbacks
    def test_shareAgainChangesMode(self):
        """
        If a calendar is already shared with a given calendar home,
        L{ICalendar.shareWith} will change the sharing mode.
        """
        yield self.test_shareWith()
        # yield self.commit() # txn is none? why?
        cal = yield self.calendarUnderTest()
        other = yield self.homeUnderTest(name=OTHER_HOME_UID)
        newName = yield cal.shareWith(other, _BIND_MODE_READ)
        otherCal = yield other.sharedChildWithName(self.sharedName)

        # Name should not change just because we updated the mode.
        self.assertEqual(newName, self.sharedName)
        self.assertNotIdentical(otherCal, None)

        # FIXME: permission information should be visible on the retrieved
        # calendar object, we shoudln't need to go via the legacy API.
        invites = yield cal.retrieveOldInvites().allRecords()
        self.assertEqual(len(invites), 1)
        self.assertEqual(invites[0].access, "read-only")


    @inlineCallbacks
    def test_unshareWith(self, commit=False):
        """
        L{ICalendar.unshareWith} will remove a previously-shared calendar from
        another user's calendar home.
        """
        yield self.test_shareWith()
        if commit:
            yield self.commit()
        cal = yield self.calendarUnderTest()
        other = yield self.homeUnderTest(name=OTHER_HOME_UID)
        newName = yield cal.unshareWith(other)
        otherCal = yield other.sharedChildWithName(newName)
        self.assertIdentical(otherCal, None)
        invites = yield cal.retrieveOldInvites().allRecords()
        self.assertEqual(len(invites), 0)
        shares = yield other.retrieveOldShares().allRecords()
        self.assertEqual(len(shares), 0)

    @inlineCallbacks
    def test_unshareSharerSide(self, commit=False):
        """
        Verify the coll.unshare( ) method works when called from the
        sharer's copy
        """
        yield self.test_shareWith()
        if commit:
            yield self.commit()
        cal = yield self.calendarUnderTest()
        other = yield self.homeUnderTest(name=OTHER_HOME_UID)
        otherCal = yield other.sharedChildWithName(self.sharedName)
        self.assertNotEqual(otherCal, None)
        yield cal.unshare()
        otherCal = yield other.sharedChildWithName(self.sharedName)
        self.assertEqual(otherCal, None)
        invites = yield cal.retrieveOldInvites().allRecords()
        self.assertEqual(len(invites), 0)
        shares = yield other.retrieveOldShares().allRecords()
        self.assertEqual(len(shares), 0)

    @inlineCallbacks
    def test_unshareShareeSide(self, commit=False):
        """
        Verify the coll.unshare( ) method works when called from the
        sharee's copy
        """
        yield self.test_shareWith()
        if commit:
            yield self.commit()
        cal = yield self.calendarUnderTest()
        other = yield self.homeUnderTest(name=OTHER_HOME_UID)
        otherCal = yield other.sharedChildWithName(self.sharedName)
        self.assertNotEqual(otherCal, None)
        yield otherCal.unshare()
        otherCal = yield other.sharedChildWithName(self.sharedName)
        self.assertEqual(otherCal, None)
        invites = yield cal.retrieveOldInvites().allRecords()
        self.assertEqual(len(invites), 0)
        shares = yield other.retrieveOldShares().allRecords()
        self.assertEqual(len(shares), 0)

    @inlineCallbacks
    def test_unshareWithInDifferentTransaction(self):
        """
        L{ICalendar.unshareWith} will remove a previously-shared calendar from
        another user's calendar home, assuming the sharing was committed in a
        previous transaction.
        """
        yield self.test_unshareWith(True)


    @inlineCallbacks
    def test_asShared(self):
        """
        L{ICalendar.asShared} returns an iterable of all versions of a shared
        calendar.
        """
        cal = yield self.calendarUnderTest()
        sharedBefore = yield cal.asShared()
        # It's not shared yet; make sure asShared doesn't include owner version.
        self.assertEqual(len(sharedBefore), 0)
        yield self.test_shareWith()
        # FIXME: don't know why this separate transaction is needed; remove it.
        yield self.commit()
        cal = yield self.calendarUnderTest()
        sharedAfter = yield cal.asShared()
        self.assertEqual(len(sharedAfter), 1)
        self.assertEqual(sharedAfter[0].shareMode(), _BIND_MODE_WRITE)
        self.assertEqual(sharedAfter[0].viewerCalendarHome().uid(),
                         OTHER_HOME_UID)


    @inlineCallbacks
    def test_hasCalendarResourceUIDSomewhereElse(self):
        """
        L{ICalendarHome.hasCalendarResourceUIDSomewhereElse} will determine if
        a calendar object with a conflicting iCalendar UID is found anywhere
        within the calendar home.
        """
        home = yield self.homeUnderTest()
        object = yield self.calendarObjectUnderTest()
        result = (yield home.hasCalendarResourceUIDSomewhereElse("123", object, "schedule"))
        self.assertFalse(result)

        result = (yield home.hasCalendarResourceUIDSomewhereElse("uid1", object, "schedule"))
        self.assertFalse(result)

        result = (yield home.hasCalendarResourceUIDSomewhereElse("uid2", object, "schedule"))
        self.assertTrue(result)
        from twistedcaldav.sharing import SharedCollectionRecord
        scr = SharedCollectionRecord(
            shareuid="opaque", sharetype="D", summary="ignored",
            hosturl="/.../__uids__/home_splits/calendar_2",
            localname="shared_other_calendar"
        )
        yield home.retrieveOldShares().addOrUpdateRecord(scr)
        # uid 2-5 is the UID of a VTODO in home_splits/calendar_2.
        result = (yield home.hasCalendarResourceUIDSomewhereElse(
            "uid2-5", object, "schedule"
        ))
        self.assertFalse(result)


    @inlineCallbacks
    def test_getCalendarResourcesForUID(self):
        """
        L{ICalendar.calendarObjects} will enumerate the calendar objects present
        in the filesystem, in name order, but skip those with hidden names.
        """
        home = yield self.homeUnderTest()
        calendarObjects = (yield home.getCalendarResourcesForUID("123"))
        self.assertEquals(len(calendarObjects), 0)

        calendarObjects = (yield home.getCalendarResourcesForUID("uid1"))
        self.assertEquals(len(calendarObjects), 1)


    @inlineCallbacks
    def test_calendarObjectName(self):
        """
        L{ICalendarObject.name} reflects the name of the calendar object.
        """
        self.assertEquals(
            (yield self.calendarObjectUnderTest()).name(),
            "1.ics"
        )


    @inlineCallbacks
    def test_calendarObjectMetaData(self):
        """
        The objects retrieved from the calendar have a various methods which
        return metadata values.
        """
        calendar = yield self.calendarObjectUnderTest()
        self.assertIsInstance(calendar.name(), basestring)
        self.assertIsInstance(calendar.uid(), basestring)
        self.assertIsInstance(calendar.accessMode, basestring)
        self.assertIsInstance(calendar.isScheduleObject, bool)
        self.assertIsInstance(calendar.scheduleEtags, tuple)
        self.assertIsInstance(calendar.hasPrivateComment, bool)
        self.assertIsInstance(calendar.md5(), basestring)
        self.assertIsInstance(calendar.size(), int)
        self.assertIsInstance(calendar.created(), int)
        self.assertIsInstance(calendar.modified(), int)

        self.assertEqual(calendar.accessMode,
                         CommonTests.metadata1["accessMode"])
        self.assertEqual(calendar.isScheduleObject,
                         CommonTests.metadata1["isScheduleObject"])
        self.assertEqual(calendar.scheduleEtags,
                         CommonTests.metadata1["scheduleEtags"])
        self.assertEqual(calendar.hasPrivateComment,
                         CommonTests.metadata1["hasPrivateComment"])

        calendar.accessMode = Component.ACCESS_PRIVATE
        calendar.isScheduleObject = True
        calendar.scheduleEtags = ("1234", "5678",)
        calendar.hasPrivateComment = True

        self.assertEqual(calendar.accessMode, Component.ACCESS_PRIVATE)
        self.assertEqual(calendar.isScheduleObject, True)
        self.assertEqual(calendar.scheduleEtags, ("1234", "5678",))
        self.assertEqual(calendar.hasPrivateComment, True)


    @inlineCallbacks
    def test_usedQuotaAdjustment(self):
        """
        Adjust used quota on the calendar home and then verify that it's used.
        """
        home = yield self.homeUnderTest()
        initialQuota = yield home.quotaUsedBytes()
        yield home.adjustQuotaUsedBytes(30)
        yield self.commit()
        home2 = yield self.homeUnderTest()
        afterQuota = yield home2.quotaUsedBytes()
        self.assertEqual(afterQuota - initialQuota, 30)
        yield home2.adjustQuotaUsedBytes(-100000)
        yield self.commit()
        home3 = yield self.homeUnderTest()
        self.assertEqual((yield home3.quotaUsedBytes()), 0)


    @inlineCallbacks
    def test_component(self):
        """
        L{ICalendarObject.component} returns a L{VComponent} describing the
        calendar data underlying that calendar object.
        """
        component = yield (yield self.calendarObjectUnderTest()).component()

        self.failUnless(
            isinstance(component, VComponent),
            component
        )

        self.assertEquals(component.name(), "VCALENDAR")
        self.assertEquals(component.mainType(), "VEVENT")
        self.assertEquals(component.resourceUID(), "uid1")


    perUserComponent = lambda self: VComponent.fromString("""BEGIN:VCALENDAR
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
VERSION:2.0
BEGIN:VEVENT
DTSTART:20110101T120000Z
DTEND:20110101T120100Z
DTSTAMP:20080601T120000Z
UID:event-with-some-per-user-data
ATTENDEE:urn:uuid:home1
ORGANIZER:urn:uuid:home1
END:VEVENT
BEGIN:X-CALENDARSERVER-PERUSER
X-CALENDARSERVER-PERUSER-UID:some-other-user
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:somebody else
TRIGGER:-PT20M
END:VALARM
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
BEGIN:X-CALENDARSERVER-PERUSER
X-CALENDARSERVER-PERUSER-UID:home1
BEGIN:X-CALENDARSERVER-PERINSTANCE
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:the owner
TRIGGER:-PT20M
END:VALARM
END:X-CALENDARSERVER-PERINSTANCE
END:X-CALENDARSERVER-PERUSER
END:VCALENDAR
""".replace("\n", "\r\n"))


    asSeenByOwner = lambda self: VComponent.fromString("""BEGIN:VCALENDAR
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
VERSION:2.0
BEGIN:VEVENT
DTSTART:20110101T120000Z
DTEND:20110101T120100Z
DTSTAMP:20080601T120000Z
UID:event-with-some-per-user-data
ATTENDEE:urn:uuid:home1
ORGANIZER:urn:uuid:home1
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:the owner
TRIGGER:-PT20M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"))


    asSeenByOther = lambda self: VComponent.fromString("""BEGIN:VCALENDAR
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
VERSION:2.0
BEGIN:VEVENT
DTSTART:20110101T120000Z
DTEND:20110101T120100Z
DTSTAMP:20080601T120000Z
UID:event-with-some-per-user-data
ATTENDEE:urn:uuid:home1
ORGANIZER:urn:uuid:home1
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:somebody else
TRIGGER:-PT20M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"))


    @inlineCallbacks
    def setUpPerUser(self):
        """
        Set up state for testing of per-user components.
        """
        cal = yield self.calendarUnderTest()
        yield cal.createCalendarObjectWithName(
            "per-user-stuff.ics",
            self.perUserComponent())
        returnValue((yield cal.calendarObjectWithName("per-user-stuff.ics")))


    @inlineCallbacks
    def test_filteredComponent(self):
        """
        L{ICalendarObject.filteredComponent} returns a L{VComponent} that has
        filtered per-user data.
        """
        obj = yield self.setUpPerUser()
        temp = yield obj.component()
        obj._component = temp.duplicate()
        otherComp = (yield obj.filteredComponent("some-other-user"))
        self.assertEquals(otherComp, self.asSeenByOther())
        obj._component = temp.duplicate()
        ownerComp = (yield obj.filteredComponent("home1"))
        self.assertEquals(ownerComp, self.asSeenByOwner())


    @inlineCallbacks
    def test_iCalendarText(self):
        """
        L{ICalendarObject.iCalendarText} returns a C{str} describing the same
        data provided by L{ICalendarObject.component}.
        """
        text = yield (yield self.calendarObjectUnderTest())._text()
        self.assertIsInstance(text, str)
        self.failUnless(text.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertIn("\r\nUID:uid1\r\n", text)
        self.failUnless(text.endswith("\r\nEND:VCALENDAR\r\n"))


    @inlineCallbacks
    def test_calendarObjectUID(self):
        """
        L{ICalendarObject.uid} returns a C{str} describing the C{UID} property
        of the calendar object's component.
        """
        self.assertEquals(
            (yield self.calendarObjectUnderTest()).uid(), "uid1"
        )


    def test_organizer(self):
        """
        L{ICalendarObject.organizer} returns a C{str} describing the calendar
        user address of the C{ORGANIZER} property of the calendar object's
        component.
        """
        self.assertEquals(
            (yield self.calendarObjectUnderTest()).organizer(),
            "mailto:wsanchez@example.com"
        )


    @inlineCallbacks
    def test_calendarObjectWithUID_absent(self):
        """
        L{ICalendar.calendarObjectWithUID} returns C{None} for calendars which
        don't exist.
        """
        calendar1 = yield self.calendarUnderTest()
        self.assertEquals((yield calendar1.calendarObjectWithUID("xyzzy")),
                          None)


    @inlineCallbacks
    def test_calendars(self):
        """
        L{ICalendarHome.calendars} returns an iterable of L{ICalendar}
        providers, which are consistent with the results from
        L{ICalendar.calendarWithName}.
        """
        # Add a dot directory to make sure we don't find it
        # self.home1._path.child(".foo").createDirectory()
        home = yield self.homeUnderTest()
        calendars = list((yield home.calendars()))

        for calendar in calendars:
            self.assertProvides(ICalendar, calendar)
            self.assertEquals(calendar,
                              (yield home.calendarWithName(calendar.name())))

        self.assertEquals(
            set(c.name() for c in calendars),
            set(home1_calendarNames)
        )

    @inlineCallbacks
    def test_loadAllCalendars(self):
        """
        L{ICalendarHome.loadCalendars} returns an iterable of L{ICalendar}
        providers, which are consistent with the results from
        L{ICalendar.calendarWithName}.
        """
        # Add a dot directory to make sure we don't find it
        # self.home1._path.child(".foo").createDirectory()
        home = yield self.homeUnderTest()
        calendars = (yield home.loadCalendars())

        for calendar in calendars:
            self.assertProvides(ICalendar, calendar)
            self.assertEquals(calendar,
                              (yield home.calendarWithName(calendar.name())))

        self.assertEquals(
            set(c.name() for c in calendars),
            set(home1_calendarNames)
        )

        for c in calendars:
            self.assertTrue(c.properties() is not None)


    @inlineCallbacks
    def test_calendarsAfterAddCalendar(self):
        """
        L{ICalendarHome.calendars} includes calendars recently added with
        L{ICalendarHome.createCalendarWithName}.
        """
        home = yield self.homeUnderTest()
        allCalendars = yield home.calendars()
        before = set(x.name() for x in allCalendars)
        yield home.createCalendarWithName("new-name")
        allCalendars = yield home.calendars()
        after = set(x.name() for x in allCalendars)
        self.assertEquals(before | set(['new-name']), after)


    @inlineCallbacks
    def test_createCalendarObjectWithName_absent(self):
        """
        L{ICalendar.createCalendarObjectWithName} creates a new
        L{ICalendarObject}.
        """
        calendar1 = yield self.calendarUnderTest()
        name = "test.ics"
        self.assertIdentical(
            (yield calendar1.calendarObjectWithName(name)), None
        )
        component = VComponent.fromString(test_event_text)
        metadata = {
            "accessMode": "PUBLIC",
            "isScheduleObject": True,
            "scheduleTag": "abc",
            "scheduleEtags": (),
            "hasPrivateComment": False,
        }
        yield calendar1.createCalendarObjectWithName(name, component, metadata=metadata)

        calendarObject = yield calendar1.calendarObjectWithName(name)
        self.assertEquals((yield calendarObject.component()), component)
        self.assertEquals((yield calendarObject.getMetadata()), metadata)

        yield self.commit()

        # Make sure notifications fire after commit
        self.assertEquals(
            self.notifierFactory.history,
            [
                ("update", "CalDAV|home1"),
                ("update", "CalDAV|home1/calendar_1"),
            ]
        )


    @inlineCallbacks
    def test_createCalendarObjectWithName_exists(self):
        """
        L{ICalendar.createCalendarObjectWithName} raises
        L{CalendarObjectNameAlreadyExistsError} if a calendar object with the
        given name already exists in that calendar.
        """
        cal = yield self.calendarUnderTest()
        comp = VComponent.fromString(test_event_text)
        yield self.failUnlessFailure(
            maybeDeferred(cal.createCalendarObjectWithName, "1.ics", comp),
            ObjectResourceNameAlreadyExistsError,
        )


    @inlineCallbacks
    def test_createCalendarObjectWithName_invalid(self):
        """
        L{ICalendar.createCalendarObjectWithName} raises
        L{InvalidCalendarComponentError} if presented with invalid iCalendar
        text.
        """
        yield self.failUnlessFailure(
            maybeDeferred((yield self.calendarUnderTest()).createCalendarObjectWithName,
            "new", VComponent.fromString(test_event_notCalDAV_text)),
            InvalidObjectResourceError,
        )

    @inlineCallbacks
    def test_setComponent_invalid(self):
        """
        L{ICalendarObject.setComponent} raises L{InvalidICalendarDataError} if
        presented with invalid iCalendar text.
        """
        calendarObject = yield self.calendarObjectUnderTest()
        yield self.failUnlessFailure(
            maybeDeferred(calendarObject.setComponent,
                          VComponent.fromString(test_event_notCalDAV_text)),
            InvalidObjectResourceError,
        )


    @inlineCallbacks
    def test_setComponent_uidchanged(self):
        """
        L{ICalendarObject.setComponent} raises L{InvalidCalendarComponentError}
        when given a L{VComponent} whose UID does not match its existing UID.
        """
        calendar1 = yield self.calendarUnderTest()
        component = VComponent.fromString(test_event_text)
        calendarObject = yield calendar1.calendarObjectWithName("1.ics")
        yield self.failUnlessFailure(
            maybeDeferred(calendarObject.setComponent, component),
            InvalidObjectResourceError,
        )


    @inlineCallbacks
    def test_calendarHomeWithUID_create(self):
        """
        L{ICommonStoreTransaction.calendarHomeWithUID} with C{create=True}
        will create a calendar home that doesn't exist yet.
        """
        txn = self.transactionUnderTest()
        noHomeUID = "xyzzy"
        calendarHome = yield txn.calendarHomeWithUID(
            noHomeUID,
            create=True
        )
        @inlineCallbacks
        def readOtherTxn():
            otherTxn = self.savedStore.newTransaction(self.id() + "other txn")
            self.addCleanup(otherTxn.commit)
            returnValue((yield otherTxn.calendarHomeWithUID(noHomeUID)))
        self.assertProvides(ICalendarHome, calendarHome)
        # Default calendar should be automatically created.
        self.assertProvides(ICalendar,
                            (yield calendarHome.calendarWithName("calendar")))
        # A concurrent transaction shouldn't be able to read it yet:
        self.assertIdentical((yield readOtherTxn()), None)
        yield self.commit()
        # But once it's committed, other transactions should see it.
        self.assertProvides(ICalendarHome, (yield readOtherTxn()))


    @inlineCallbacks
    def test_setComponent(self):
        """
        L{CalendarObject.setComponent} changes the result of
        L{CalendarObject.component} within the same transaction.
        """
        component = VComponent.fromString(event1modified_text)

        calendar1 = yield self.calendarUnderTest()
        calendarObject = yield calendar1.calendarObjectWithName("1.ics")
        oldComponent = yield calendarObject.component()
        self.assertNotEqual(component, oldComponent)
        yield calendarObject.setComponent(component)
        self.assertEquals((yield calendarObject.component()), component)

        # Also check a new instance
        calendarObject = yield calendar1.calendarObjectWithName("1.ics")
        self.assertEquals((yield calendarObject.component()), component)

        yield self.commit()

        # Make sure notification fired after commit
        self.assertEquals(
            self.notifierFactory.history,
            [
                ("update", "CalDAV|home1"),
                ("update", "CalDAV|home1/calendar_1"),
            ]
        )


    def checkPropertiesMethod(self, thunk):
        """
        Verify that the given object has a properties method that returns an
        L{IPropertyStore}.
        """
        properties = thunk.properties()
        self.assertProvides(IPropertyStore, properties)


    @inlineCallbacks
    def test_homeProperties(self):
        """
        L{ICalendarHome.properties} returns a property store.
        """
        self.checkPropertiesMethod((yield self.homeUnderTest()))


    @inlineCallbacks
    def test_calendarProperties(self):
        """
        L{ICalendar.properties} returns a property store.
        """
        self.checkPropertiesMethod((yield self.calendarUnderTest()))


    @inlineCallbacks
    def test_calendarObjectProperties(self):
        """
        L{ICalendarObject.properties} returns a property store.
        """
        self.checkPropertiesMethod((yield self.calendarObjectUnderTest()))


    @inlineCallbacks
    def test_newCalendarObjectProperties(self):
        """
        L{ICalendarObject.properties} returns an empty property store for a
        calendar object which has been created but not committed.
        """
        calendar = yield self.calendarUnderTest()
        yield calendar.createCalendarObjectWithName(
            "test.ics", VComponent.fromString(test_event_text)
        )
        newEvent = yield calendar.calendarObjectWithName("test.ics")
        self.assertEquals(newEvent.properties().items(), [])


    @inlineCallbacks
    def test_setComponentPreservesProperties(self):
        """
        L{ICalendarObject.setComponent} preserves properties.

        (Some implementations must go to extra trouble to provide this
        behavior; for example, file storage must copy extended attributes from
        the existing file to the temporary file replacing it.)
        """
        propertyName = PropertyName("http://example.com/ns", "example")
        propertyContent = WebDAVUnknownElement("sample content")
        propertyContent.name = propertyName.name
        propertyContent.namespace = propertyName.namespace

        calobject = (yield self.calendarObjectUnderTest())
        if calobject._parentCollection.objectResourcesHaveProperties():
            (yield self.calendarObjectUnderTest()).properties()[
                propertyName] = propertyContent
            yield self.commit()
            # Sanity check; are properties even readable in a separate transaction?
            # Should probably be a separate test.
            self.assertEquals(
                (yield self.calendarObjectUnderTest()).properties()[propertyName],
                propertyContent)
            obj = yield self.calendarObjectUnderTest()
            event1_text = yield obj._text()
            event1_text_withDifferentSubject = event1_text.replace(
                "SUMMARY:CalDAV protocol updates",
                "SUMMARY:Changed"
            )
            # Sanity check; make sure the test has the right idea of the subject.
            self.assertNotEquals(event1_text, event1_text_withDifferentSubject)
            newComponent = VComponent.fromString(event1_text_withDifferentSubject)
            yield obj.setComponent(newComponent)

            # Putting everything into a separate transaction to account for any
            # caching that may take place.
            yield self.commit()
            self.assertEquals(
                (yield self.calendarObjectUnderTest()).properties()[propertyName],
                propertyContent
            )


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
    def test_dropboxID(self):
        """
        L{ICalendarObject.dropboxID} should synthesize its dropbox from the X
        -APPLE-DROPBOX property, if available.
        """
        cal = yield self.calendarUnderTest()
        yield cal.createCalendarObjectWithName("drop.ics", VComponent.fromString(
                self.eventWithDropbox
            )
        )
        obj = yield cal.calendarObjectWithName("drop.ics")
        self.assertEquals((yield obj.dropboxID()), "some-dropbox-id")


    def token2revision(self, token):
        """
        FIXME: the API names for L{syncToken}() and L{resourceNamesSinceToken}()
        are slightly inaccurate; one doesn't produce input for the other.
        Actually it should be resource names since I{revision} and you need to
        understand the structure of the tokens to extract the revision.  Right
        now that logic lives in the protocol layer, so this testing method
        replicates it.
        """
        _ignore_uuid, rev = token.split("_", 1)
        rev = int(rev)
        return rev


    @inlineCallbacks
    def test_simpleHomeSyncToken(self):
        """
        L{ICalendarHome.resourceNamesSinceToken} will return the names of
        calendar objects created since L{ICalendarHome.syncToken} last returned
        a particular value.
        """
        home = yield self.homeUnderTest()
        cal = yield self.calendarUnderTest()
        st = yield home.syncToken()
        yield cal.createCalendarObjectWithName("new.ics", VComponent.fromString(
                self.eventWithDropbox
            )
        )

        yield cal.removeCalendarObjectWithName("2.ics")
        yield home.createCalendarWithName("other-calendar")
        st2 = yield home.syncToken()
        self.failIfEquals(st, st2)

        home = yield self.homeUnderTest()

        changed, deleted = yield home.resourceNamesSinceToken(
            self.token2revision(st), "depth_is_ignored")

        self.assertEquals(set(changed), set(["calendar_1/new.ics",
                                             "calendar_1/2.ics",
                                             "other-calendar/"]))
        self.assertEquals(set(deleted), set(["calendar_1/2.ics"]))

        changed, deleted = yield home.resourceNamesSinceToken(
            self.token2revision(st2), "depth_is_ignored")
        self.assertEquals(changed, [])
        self.assertEquals(deleted, [])


    @inlineCallbacks
    def test_collectionSyncToken(self):
        """
        L{ICalendar.resourceNamesSinceToken} will return the names of calendar
        objects changed or deleted since 
        """
        cal = yield self.calendarUnderTest()
        st = yield cal.syncToken()
        rev = self.token2revision(st)
        yield cal.createCalendarObjectWithName("new.ics", VComponent.fromString(
                self.eventWithDropbox
            )
        )
        yield cal.removeCalendarObjectWithName("2.ics")
        st2 = yield cal.syncToken()
        rev2 = self.token2revision(st2)
        changed, deleted = yield cal.resourceNamesSinceToken(rev)
        self.assertEquals(set(changed), set(["new.ics"]))
        self.assertEquals(set(deleted), set(["2.ics"]))
        changed, deleted = yield cal.resourceNamesSinceToken(rev2)
        self.assertEquals(set(changed), set([]))
        self.assertEquals(set(deleted), set([]))


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
            objName, VComponent.fromString(
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
    def createAttachmentTest(self, refresh):
        """
        Common logic for attachment-creation tests.
        """
        obj = yield self.calendarObjectUnderTest()
        attachment = yield obj.createAttachmentWithName(
            "new.attachment",
        )
        t = attachment.store(MimeType("text", "x-fixture"))
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
            [attachment.name() for attachment in (yield obj.attachments())],
            ['new.attachment']
        )


    @inlineCallbacks
    def test_twoAttachmentsWithTheSameName(self):
        """
        Attachments are uniquely identified by their associated object and path;
        two attachments with the same name won't overwrite each other.
        """
        obj = yield self.calendarObjectUnderTest()
        obj2 = yield self.calendarObjectUnderTest("2.ics")
        att1 = yield self.stringToAttachment(obj, "sample.attachment",
                                             "test data 1")
        att2 = yield self.stringToAttachment(obj2, "sample.attachment",
                                             "test data 2")
        data1 = yield self.attachmentToString(att1)
        data2 = yield self.attachmentToString(att2)
        self.assertEquals(data1, "test data 1")
        self.assertEquals(data2, "test data 2")


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
        t = att.store(mimeType)
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
        transport = attachment.store(MimeType("test", "x-something"))
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
        t = attachment.store(MimeType("text", "x-fixture"))
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
        t = attachment.store(MimeType("text", "x-fixture"))
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


    def test_removeAttachmentWithName(self, refresh=lambda x:x):
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
        t = attachment.store(MimeType("text", "plain"))
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
    def test_finishedOnCommit(self):
        """ 
        Calling L{ITransaction.abort} or L{ITransaction.commit} after
        L{ITransaction.commit} has already been called raises an
        L{AlreadyFinishedError}.
        """
        yield self.calendarObjectUnderTest()
        txn = self.lastTransaction
        yield self.commit()

        yield self.failUnlessFailure(
            maybeDeferred(txn.commit),
            AlreadyFinishedError
        )
        yield self.failUnlessFailure(
            maybeDeferred(txn.abort),
            AlreadyFinishedError
        )


    @inlineCallbacks
    def test_dontLeakCalendars(self):
        """
        Calendars in one user's calendar home should not show up in another
        user's calendar home.
        """
        home2 = yield self.transactionUnderTest().calendarHomeWithUID(
            "home2", create=True)
        self.assertIdentical(
            (yield home2.calendarWithName("calendar_1")), None)


    @inlineCallbacks
    def test_dontLeakObjects(self):
        """
        Calendar objects in one user's calendar should not show up in another
        user's via uid or name queries.
        """
        home1 = yield self.homeUnderTest()
        home2 = yield self.transactionUnderTest().calendarHomeWithUID(
            "home2", create=True)
        calendar1 = yield home1.calendarWithName("calendar_1")
        calendar2 = yield home2.calendarWithName("calendar")
        objects = list(
            (yield (yield home2.calendarWithName("calendar")).calendarObjects()))
        self.assertEquals(objects, [])
        for resourceName in self.requirements['home1']['calendar_1'].keys():
            obj = yield calendar1.calendarObjectWithName(resourceName)
            self.assertIdentical(
                (yield calendar2.calendarObjectWithName(resourceName)), None)
            self.assertIdentical(
                (yield calendar2.calendarObjectWithUID(obj.uid())), None)


    @inlineCallbacks
    def test_eachCalendarHome(self):
        """
        L{ICalendarTransaction.eachCalendarHome} returns an iterator that
        yields 2-tuples of (transaction, home).
        """
        # create some additional calendar homes
        additionalUIDs = set('alpha-uid home2 home3 beta-uid'.split())
        txn = self.transactionUnderTest()
        for name in additionalUIDs:
            # maybe it's not actually necessary to yield (i.e. wait) for each
            # one?  commit() should wait for all of them.
            yield txn.calendarHomeWithUID(name, create=True)
        yield self.commit()
        foundUIDs = set([])
        lastTxn = None
        for txn, home in (yield self.storeUnderTest().eachCalendarHome()):
            self.addCleanup(txn.commit)
            foundUIDs.add(home.uid())
            self.assertNotIdentical(lastTxn, txn)
            lastTxn = txn
        requiredUIDs = set([
            uid for uid in self.requirements
            if self.requirements[uid] is not None
        ])
        additionalUIDs.add("home_bad")
        additionalUIDs.add("home_attachments")
        expectedUIDs = additionalUIDs.union(requiredUIDs)
        self.assertEquals(foundUIDs, expectedUIDs)

