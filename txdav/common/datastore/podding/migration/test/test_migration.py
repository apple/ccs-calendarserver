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

from pycalendar.datetime import DateTime

from twext.enterprise.jobs.jobitem import JobItem

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.filepath import FilePath

from twistedcaldav.config import config
from twistedcaldav.ical import Component

from txdav.caldav.datastore.scheduling.ischedule.delivery import IScheduleRequest
from txdav.caldav.datastore.scheduling.ischedule.resource import IScheduleInboxResource
from txdav.caldav.datastore.scheduling.work import allScheduleWork
from txdav.caldav.datastore.test.common import CaptureProtocol
from txdav.common.datastore.podding.migration.home_sync import CrossPodHomeSync
from txdav.common.datastore.podding.migration.sync_metadata import CalendarMigrationRecord, \
    AttachmentMigrationRecord, CalendarObjectMigrationRecord
from txdav.common.datastore.podding.migration.work import HomeCleanupWork, MigratedHomeCleanupWork, MigrationCleanupWork
from txdav.common.datastore.podding.test.util import MultiStoreConduitTest
from txdav.common.datastore.sql_directory import DelegateRecord,\
    DelegateGroupsRecord, ExternalDelegateGroupsRecord
from txdav.common.datastore.sql_tables import _BIND_MODE_READ, \
    _HOME_STATUS_DISABLED, _HOME_STATUS_NORMAL, _HOME_STATUS_EXTERNAL, \
    _HOME_STATUS_MIGRATING
from txdav.common.datastore.test.util import populateCalendarsFrom
from txdav.who.delegates import Delegates

from txweb2.dav.test.util import SimpleRequest
from txweb2.http_headers import MimeType
from txweb2.stream import MemoryStream


class TestCompleteMigrationCycle(MultiStoreConduitTest):
    """
    Test that a full migration cycle using L{CrossPodHomeSync} works.
    """

    def __init__(self, methodName='runTest'):
        super(TestCompleteMigrationCycle, self).__init__(methodName)
        self.stash = {}


    @inlineCallbacks
    def setUp(self):
        @inlineCallbacks
        def _fakeSubmitRequest(iself, ssl, host, port, request):
            pod = (port - 8008) / 100
            inbox = IScheduleInboxResource(self.site.resource, self.theStoreUnderTest(pod), podding=True)
            response = yield inbox.http_POST(SimpleRequest(
                self.site,
                "POST",
                "http://{host}:{port}/podding".format(host=host, port=port),
                request.headers,
                request.stream.mem,
            ))
            returnValue(response)


        self.patch(IScheduleRequest, "_submitRequest", _fakeSubmitRequest)
        self.accounts = FilePath(__file__).sibling("accounts").child("groupAccounts.xml")
        self.augments = FilePath(__file__).sibling("accounts").child("augments.xml")
        yield super(TestCompleteMigrationCycle, self).setUp()
        yield self.populate()

        # Speed up work
        self.patch(MigrationCleanupWork, "notBeforeDelay", 1)
        self.patch(HomeCleanupWork, "notBeforeDelay", 1)
        self.patch(MigratedHomeCleanupWork, "notBeforeDelay", 1)


    def configure(self):
        super(TestCompleteMigrationCycle, self).configure()
        config.GroupAttendees.Enabled = True
        config.GroupAttendees.ReconciliationDelaySeconds = 0
        config.GroupAttendees.AutoUpdateSecondsFromNow = 0
        config.AccountingCategories.migration = True
        config.AccountingPrincipals = ["*"]


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements0, self.theStoreUnderTest(0))
        yield populateCalendarsFrom(self.requirements1, self.theStoreUnderTest(1))

    requirements0 = {
        "user01" : None,
        "user02" : None,
        "user03" : None,
        "user04" : None,
        "user05" : None,
        "user06" : None,
        "user07" : None,
        "user08" : None,
        "user09" : None,
        "user10" : None,
    }

    requirements1 = {
        "puser01" : None,
        "puser02" : None,
        "puser03" : None,
        "puser04" : None,
        "puser05" : None,
        "puser06" : None,
        "puser07" : None,
        "puser08" : None,
        "puser09" : None,
        "puser10" : None,
    }


    @inlineCallbacks
    def _createShare(self, shareFrom, shareTo, accept=True):
        # Invite
        txnindex = 1 if shareFrom[0] == "p" else 0
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(txnindex), name=shareFrom, create=True)
        calendar = yield home.childWithName("calendar")
        shareeView = yield calendar.inviteUIDToShare(shareTo, _BIND_MODE_READ, "summary")
        yield self.commitTransaction(txnindex)

        # Accept
        if accept:
            inviteUID = shareeView.shareUID()
            txnindex = 1 if shareTo[0] == "p" else 0
            shareeHome = yield self.homeUnderTest(txn=self.theTransactionUnderTest(txnindex), name=shareTo)
            shareeView = yield shareeHome.acceptShare(inviteUID)
            sharedName = shareeView.name()
            yield self.commitTransaction(txnindex)
        else:
            sharedName = None

        returnValue(sharedName)


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


    now = {
        "now": DateTime.getToday().getYear(),
        "now1": DateTime.getToday().getYear() + 1,
    }

    data01_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data01_1
DTSTART:{now1:04d}0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:data01_1
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    data01_1_changed = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data01_1
DTSTART:{now1:04d}0102T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:data01_1_changed
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    data01_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data01_2
DTSTART:{now1:04d}0102T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:data01_2
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:puser02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    data01_3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data01_3
DTSTART:{now1:04d}0102T180000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:data01_3
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:group02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    data02_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data02_1
DTSTART:{now1:04d}0103T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:data02_1
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    data02_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data02_2
DTSTART:{now1:04d}0103T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:data02_2
ORGANIZER:mailto:user02@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:puser02@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    data02_3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_data02_3
DTSTART:{now1:04d}0103T180000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:data02_3
ORGANIZER:mailto:user02@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:mailto:group01@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    datap02_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_datap02_1
DTSTART:{now1:04d}0103T140000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
RRULE:FREQ=WEEKLY
SUMMARY:datap02_1
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    datap02_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_datap02_2
DTSTART:{now1:04d}0103T160000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:datap02_2
ORGANIZER:mailto:puser02@example.com
ATTENDEE:mailto:puser02@example.com
ATTENDEE:mailto:user01@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)

    datap02_3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:uid_datap02_3
DTSTART:{now1:04d}0103T180000Z
DURATION:PT1H
CREATED:20060102T190000Z
DTSTAMP:20051222T210507Z
SUMMARY:datap02_3
ORGANIZER:mailto:puser02@example.com
ATTENDEE:mailto:puser02@example.com
ATTENDEE:mailto:group01@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").format(**now)


    @inlineCallbacks
    def preCheck(self):
        """
        Checks prior to starting any tests
        """

        for i in range(self.numberOfStores):
            txn = self.theTransactionUnderTest(i)
            record = yield txn.directoryService().recordWithUID(u"user01")
            self.assertEqual(record.serviceNodeUID, "A")
            self.assertEqual(record.thisServer(), i == 0)
            record = yield txn.directoryService().recordWithUID(u"user02")
            self.assertEqual(record.serviceNodeUID, "A")
            self.assertEqual(record.thisServer(), i == 0)
            record = yield txn.directoryService().recordWithUID(u"puser02")
            self.assertEqual(record.serviceNodeUID, "B")
            self.assertEqual(record.thisServer(), i == 1)
            yield self.commitTransaction(i)


    @inlineCallbacks
    def initialState(self):
        """
        Setup the server with an initial set of data

        user01 - migrating user
        user02 - has a calendar shared with user01
        user03 - shared to by user01

        puser01 - user on other pod
        puser02 - has a calendar shared with user01
        puser03 - shared to by user01
        """

        # Data for user01
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user01", create=True)
        self.stash["user01_pod0_home_id"] = home.id()
        calendar = yield home.childWithName("calendar")
        yield calendar.createCalendarObjectWithName("01_1.ics", Component.fromString(self.data01_1))
        yield calendar.createCalendarObjectWithName("01_2.ics", Component.fromString(self.data01_2))
        obj3 = yield calendar.createCalendarObjectWithName("01_3.ics", Component.fromString(self.data01_3))
        attachment, _ignore_location = yield obj3.addAttachment(None, MimeType.fromString("text/plain"), "test.txt", MemoryStream("Here is some text #1."))
        self.stash["user01_attachment_id"] = attachment.id()
        self.stash["user01_attachment_md5"] = attachment.md5()
        self.stash["user01_attachment_mid"] = attachment.managedID()
        yield self.commitTransaction(0)

        # Data for user02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(0), name="user02", create=True)
        calendar = yield home.childWithName("calendar")
        yield calendar.createCalendarObjectWithName("02_1.ics", Component.fromString(self.data02_1))
        yield calendar.createCalendarObjectWithName("02_2.ics", Component.fromString(self.data02_2))
        yield calendar.createCalendarObjectWithName("02_3.ics", Component.fromString(self.data02_3))
        yield self.commitTransaction(0)

        # Data for puser02
        home = yield self.homeUnderTest(txn=self.theTransactionUnderTest(1), name="puser02", create=True)
        calendar = yield home.childWithName("calendar")
        yield calendar.createCalendarObjectWithName("p02_1.ics", Component.fromString(self.datap02_1))
        yield calendar.createCalendarObjectWithName("p02_2.ics", Component.fromString(self.datap02_2))
        yield calendar.createCalendarObjectWithName("p02_3.ics", Component.fromString(self.datap02_3))
        yield self.commitTransaction(1)

        # Share calendars
        self.stash["sharename_user01_to_user03"] = yield self._createShare("user01", "user03")
        self.stash["sharename_user01_to_puser03"] = yield self._createShare("user01", "puser03")
        self.stash["sharename_user02_to_user01"] = yield self._createShare("user02", "user01")
        self.stash["sharename_puser02_to_user01"] = yield self._createShare("puser02", "user01")

        # Add some delegates
        txn = self.theTransactionUnderTest(0)
        record01 = yield txn.directoryService().recordWithUID(u"user01")
        record02 = yield txn.directoryService().recordWithUID(u"user02")
        record03 = yield txn.directoryService().recordWithUID(u"user03")
        precord01 = yield txn.directoryService().recordWithUID(u"puser01")

        group02 = yield txn.directoryService().recordWithUID(u"group02")
        group03 = yield txn.directoryService().recordWithUID(u"group03")

        # Add user02 and user03 as individual delegates
        yield Delegates.addDelegate(txn, record01, record02, True)
        yield Delegates.addDelegate(txn, record01, record03, False)
        yield Delegates.addDelegate(txn, record01, precord01, False)

        # Add group delegates
        yield Delegates.addDelegate(txn, record01, group02, True)
        yield Delegates.addDelegate(txn, record01, group03, False)

        # Add external delegates
        yield txn.assignExternalDelegates(u"user01", None, None, u"external1", u"external2")

        yield self.commitTransaction(0)

        yield self.waitAllEmpty()


    @inlineCallbacks
    def secondState(self):
        """
        Setup the server with data changes appearing after the first sync
        """
        txn = self.theTransactionUnderTest(0)
        obj = yield self.calendarObjectUnderTest(txn, name="01_1.ics", calendar_name="calendar", home="user01")
        yield obj.setComponent(self.data01_1_changed)

        obj = yield self.calendarObjectUnderTest(txn, name="02_2.ics", calendar_name="calendar", home="user02")
        attachment, _ignore_location = yield obj.addAttachment(None, MimeType.fromString("text/plain"), "test_02.txt", MemoryStream("Here is some text #02."))
        self.stash["user02_attachment_id"] = attachment.id()
        self.stash["user02_attachment_md5"] = attachment.md5()
        self.stash["user02_attachment_mid"] = attachment.managedID()

        yield self.commitTransaction(0)

        yield self.waitAllEmpty()


    @inlineCallbacks
    def finalState(self):
        """
        Setup the server with data changes appearing before the final sync
        """
        txn = self.theTransactionUnderTest(1)
        obj = yield self.calendarObjectUnderTest(txn, name="p02_2.ics", calendar_name="calendar", home="puser02")
        attachment, _ignore_location = yield obj.addAttachment(None, MimeType.fromString("text/plain"), "test_p02.txt", MemoryStream("Here is some text #p02."))
        self.stash["puser02_attachment_id"] = attachment.id()
        self.stash["puser02_attachment_mid"] = attachment.managedID()
        self.stash["puser02_attachment_md5"] = attachment.md5()

        yield self.commitTransaction(1)

        yield self.waitAllEmpty()


    @inlineCallbacks
    def switchAccounts(self):
        """
        Switch the migrated user accounts to point to the new pod
        """

        for i in range(self.numberOfStores):
            txn = self.theTransactionUnderTest(i)
            record = yield txn.directoryService().recordWithUID(u"user01")
            yield self.changeRecord(record, txn.directoryService().fieldName.serviceNodeUID, u"B", directory=txn.directoryService())
            yield self.commitTransaction(i)

        for i in range(self.numberOfStores):
            txn = self.theTransactionUnderTest(i)
            record = yield txn.directoryService().recordWithUID(u"user01")
            self.assertEqual(record.serviceNodeUID, "B")
            self.assertEqual(record.thisServer(), i == 1)
            record = yield txn.directoryService().recordWithUID(u"user02")
            self.assertEqual(record.serviceNodeUID, "A")
            self.assertEqual(record.thisServer(), i == 0)
            record = yield txn.directoryService().recordWithUID(u"puser02")
            self.assertEqual(record.serviceNodeUID, "B")
            self.assertEqual(record.thisServer(), i == 1)
            yield self.commitTransaction(i)


    @inlineCallbacks
    def postCheck(self):
        """
        Checks after migration is done
        """

        # Check that the home has been moved
        home = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="user01")
        self.assertTrue(home.external())
        home = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="user01", status=_HOME_STATUS_NORMAL)
        self.assertTrue(home is None)
        home = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="user01", status=_HOME_STATUS_EXTERNAL)
        self.assertTrue(home is not None)
        home = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="user01", status=_HOME_STATUS_DISABLED)
        self.assertTrue(home is not None)
        home = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="user01", status=_HOME_STATUS_MIGRATING)
        self.assertTrue(home is None)
        yield self.commitTransaction(0)

        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="user01")
        self.assertTrue(home.normal())
        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_NORMAL)
        self.assertTrue(home is not None)
        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_EXTERNAL)
        self.assertTrue(home is None)
        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_DISABLED)
        self.assertTrue(home is not None)
        home = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_MIGRATING)
        self.assertTrue(home is None)
        yield self.commitTransaction(1)

        # Check that the notifications have been moved
        notifications = yield self.notificationCollectionUnderTest(self.theTransactionUnderTest(0), name="user01", status=_HOME_STATUS_NORMAL)
        self.assertTrue(notifications is None)
        notifications = yield self.notificationCollectionUnderTest(self.theTransactionUnderTest(0), name="user01", status=_HOME_STATUS_EXTERNAL)
        self.assertTrue(notifications is None)
        notifications = yield self.notificationCollectionUnderTest(self.theTransactionUnderTest(0), name="user01", status=_HOME_STATUS_DISABLED)
        self.assertTrue(notifications is not None)
        yield self.commitTransaction(0)

        notifications = yield self.notificationCollectionUnderTest(self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_NORMAL)
        self.assertTrue(notifications is not None)
        notifications = yield self.notificationCollectionUnderTest(self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_EXTERNAL)
        self.assertTrue(notifications is None)
        notifications = yield self.notificationCollectionUnderTest(self.theTransactionUnderTest(1), name="user01", status=_HOME_STATUS_DISABLED)
        self.assertTrue(notifications is not None)
        yield self.commitTransaction(1)

        # New pod data
        homes = {}
        homes["user01"] = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="user01")
        homes["user02"] = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="user02")
        self.assertTrue(homes["user02"].external())
        homes["user03"] = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="user03")
        self.assertTrue(homes["user03"].external())
        homes["puser01"] = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="puser01")
        self.assertTrue(homes["puser01"].normal())
        homes["puser02"] = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="puser02")
        self.assertTrue(homes["puser02"].normal())
        homes["puser03"] = yield self.homeUnderTest(self.theTransactionUnderTest(1), name="puser03")
        self.assertTrue(homes["puser03"].normal())

        # Check calendar data on new pod
        calendars = yield homes["user01"].loadChildren()
        calnames = dict([(calendar.name(), calendar) for calendar in calendars])
        self.assertEqual(
            set(calnames.keys()),
            set(("calendar", "tasks", "inbox", self.stash["sharename_user02_to_user01"], self.stash["sharename_puser02_to_user01"],))
        )

        # Check shared-by user01 on new pod
        shared = calnames["calendar"]
        invitations = yield shared.sharingInvites()
        by_sharee = dict([(invitation.shareeUID, invitation) for invitation in invitations])
        self.assertEqual(len(invitations), 2)
        self.assertEqual(set(by_sharee.keys()), set(("user03", "puser03",)))
        self.assertEqual(by_sharee["user03"].shareeHomeID, homes["user03"].id())
        self.assertEqual(by_sharee["puser03"].shareeHomeID, homes["puser03"].id())

        # Check shared-to user01 on new pod
        shared = calnames[self.stash["sharename_user02_to_user01"]]
        self.assertEqual(shared.ownerHome().uid(), "user02")
        self.assertEqual(shared.ownerHome().id(), homes["user02"].id())

        shared = calnames[self.stash["sharename_puser02_to_user01"]]
        self.assertEqual(shared.ownerHome().uid(), "puser02")
        self.assertEqual(shared.ownerHome().id(), homes["puser02"].id())

        shared = yield homes["puser02"].calendarWithName("calendar")
        invitations = yield shared.sharingInvites()
        self.assertEqual(len(invitations), 1)
        self.assertEqual(invitations[0].shareeHomeID, homes["user01"].id())

        yield self.commitTransaction(1)

        # Old pod data
        homes = {}
        homes["user01"] = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="user01")
        homes["user02"] = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="user02")
        self.assertTrue(homes["user02"].normal())
        homes["user03"] = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="user03")
        self.assertTrue(homes["user03"].normal())
        homes["puser01"] = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="puser01")
        self.assertTrue(homes["puser01"] is None)
        homes["puser02"] = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="puser02")
        self.assertTrue(homes["puser02"].external())
        homes["puser03"] = yield self.homeUnderTest(self.theTransactionUnderTest(0), name="puser03")
        self.assertTrue(homes["puser03"].external())

        # Check shared-by user01 on old pod
        shared = yield homes["user03"].calendarWithName(self.stash["sharename_user01_to_user03"])
        self.assertEqual(shared.ownerHome().uid(), "user01")
        self.assertEqual(shared.ownerHome().id(), homes["user01"].id())

        # Check shared-to user01 on old pod
        shared = yield homes["user02"].calendarWithName("calendar")
        invitations = yield shared.sharingInvites()
        self.assertEqual(len(invitations), 1)
        self.assertEqual(invitations[0].shareeHomeID, homes["user01"].id())

        yield self.commitTransaction(0)

        # Delegates on each pod
        for pod in range(self.numberOfStores):
            txn = self.theTransactionUnderTest(pod)
            records = {}
            for ctr in range(10):
                uid = u"user{:02d}".format(ctr + 1)
                records[uid] = yield txn.directoryService().recordWithUID(uid)
            for ctr in range(10):
                uid = u"puser{:02d}".format(ctr + 1)
                records[uid] = yield txn.directoryService().recordWithUID(uid)
            for ctr in range(10):
                uid = u"group{:02d}".format(ctr + 1)
                records[uid] = yield txn.directoryService().recordWithUID(uid)

            delegates = yield Delegates.delegatesOf(txn, records["user01"], True, False)
            self.assertTrue(records["user02"] in delegates)
            self.assertTrue(records["group02"] in delegates)
            delegates = yield Delegates.delegatesOf(txn, records["user01"], True, True)
            self.assertTrue(records["user02"] in delegates)
            self.assertTrue(records["user06"] in delegates)
            self.assertTrue(records["user07"] in delegates)
            self.assertTrue(records["user08"] in delegates)

            delegates = yield Delegates.delegatesOf(txn, records["user01"], False, False)
            self.assertTrue(records["user03"] in delegates)
            self.assertTrue(records["group03"] in delegates)
            self.assertTrue(records["puser01"] in delegates)
            delegates = yield Delegates.delegatesOf(txn, records["user01"], False, True)
            self.assertTrue(records["user03"] in delegates)
            self.assertTrue(records["user07"] in delegates)
            self.assertTrue(records["user08"] in delegates)
            self.assertTrue(records["user09"] in delegates)
            self.assertTrue(records["puser01"] in delegates)

        # Attachments
        obj = yield self.calendarObjectUnderTest(txn=self.theTransactionUnderTest(1), name="01_3.ics", calendar_name="calendar", home="user01")
        attachment = yield obj.attachmentWithManagedID(self.stash["user01_attachment_mid"])
        self.assertTrue(attachment is not None)
        self.assertEqual(attachment.md5(), self.stash["user01_attachment_md5"])
        data = yield self.attachmentToString(attachment)
        self.assertEqual(data, "Here is some text #1.")

        # Check removal of data from new pod

        # Make sure all jobs are done
        yield JobItem.waitEmpty(self.theStoreUnderTest(1).newTransaction, reactor, 60)

        # No migration state data left
        txn = self.theTransactionUnderTest(1)
        for migrationType in (CalendarMigrationRecord, CalendarObjectMigrationRecord, AttachmentMigrationRecord,):
            records = yield migrationType.all(txn)
            self.assertEqual(len(records), 0, msg=migrationType.__name__)
        yield self.commitTransaction(1)

        # No homes
        txn = self.theTransactionUnderTest(1)
        oldhome = yield txn.calendarHomeWithUID("user01", status=_HOME_STATUS_DISABLED)
        self.assertTrue(oldhome is None)
        oldhome = yield txn.notificationsWithUID("user01", status=_HOME_STATUS_DISABLED)
        self.assertTrue(oldhome is None)

        # Check removal of data from old pod

        # Make sure all jobs are done
        yield JobItem.waitEmpty(self.theStoreUnderTest(0).newTransaction, reactor, 60)

        # No homes
        txn = self.theTransactionUnderTest(0)
        oldhome = yield txn.calendarHomeWithUID("user01", status=_HOME_STATUS_DISABLED)
        self.assertTrue(oldhome is None)
        oldhome = yield txn.notificationsWithUID("user01", status=_HOME_STATUS_DISABLED)
        self.assertTrue(oldhome is None)

        # No delegates
        for delegateType in (DelegateRecord, DelegateGroupsRecord, ExternalDelegateGroupsRecord):
            records = yield delegateType.query(txn, delegateType.delegator == "user01")
            self.assertEqual(len(records), 0, msg=delegateType.__name__)

        # No work items
        for workType in allScheduleWork:
            records = yield workType.query(txn, workType.homeResourceID == self.stash["user01_pod0_home_id"])
            self.assertEqual(len(records), 0, msg=workType.__name__)


    @inlineCallbacks
    def test_migration(self):
        """
        Full migration cycle.
        """

        yield self.preCheck()

        # Step 1. Live full sync
        yield self.initialState()
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.sync()

        # Step 2. Live incremental sync
        yield self.secondState()
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.sync()

        # Step 3. Disable home after final changes
        yield self.finalState()
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01")
        yield syncer.disableRemoteHome()

        # Step 4. Final incremental sync
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01", final=True)
        yield syncer.sync()

        # Step 5. Final reconcile sync
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01", final=True)
        yield syncer.finalSync()

        # Step 6. Enable new home
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01", final=True)
        yield syncer.enableLocalHome()

        # Step 7. Remove old home
        syncer = CrossPodHomeSync(self.theStoreUnderTest(1), "user01", final=True)
        yield syncer.removeRemoteHome()

        yield self.switchAccounts()

        yield self.postCheck()
