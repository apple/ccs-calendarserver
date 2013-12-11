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

from twext.python.clsprop import classproperty
import twext.web2.dav.test.util
from twisted.internet.defer import inlineCallbacks, succeed, returnValue
from txdav.caldav.datastore.scheduling.ischedule.localservers import Servers, Server
from txdav.caldav.datastore.test.util import buildCalendarStore, \
    TestCalendarStoreDirectoryRecord
from txdav.common.datastore.podding.resource import ConduitResource
from txdav.common.datastore.test.util import populateCalendarsFrom, CommonCommonTests
from txdav.common.datastore.podding.conduit import PoddingConduit, \
    FailedCrossPodRequestError
from txdav.common.idirectoryservice import DirectoryRecordNotFoundError
from txdav.common.datastore.podding.test.util import MultiStoreConduitTest, \
    FakeConduitRequest
from txdav.common.datastore.sql_tables import _BIND_STATUS_ACCEPTED
from pycalendar.datetime import DateTime
from twistedcaldav.ical import Component

class TestConduit (CommonCommonTests, twext.web2.dav.test.util.TestCase):

    class FakeConduit(object):

        def recv_fake(self, j):
            return succeed({
                "result": "ok",
                "back2u": j["echo"],
                "more": "bits",
            })


    @inlineCallbacks
    def setUp(self):
        yield super(TestConduit, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        self.directory = self._sqlCalendarStore.directoryService()

        for ctr in range(1, 100):
            self.directory.addRecord(TestCalendarStoreDirectoryRecord(
                "puser{:02d}".format(ctr),
                ("puser{:02d}".format(ctr),),
                "Puser {:02d}".format(ctr),
                frozenset((
                    "urn:uuid:puser{:02d}".format(ctr),
                    "mailto:puser{:02d}@example.com".format(ctr),
                )),
                thisServer=False,
            ))

        self.site.resource.putChild("conduit", ConduitResource(self.site.resource, self.storeUnderTest()))

        self.thisServer = Server("A", "http://127.0.0.1", "A", True)
        Servers.addServer(self.thisServer)

        yield self.populate()


    def storeUnderTest(self):
        """
        Return a store for testing.
        """
        return self._sqlCalendarStore


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
        "user03": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
    }


    def test_validRequst(self):
        """
        Cross-pod request fails when there is no shared secret header present.
        """

        conduit = PoddingConduit(self.storeUnderTest())
        r1, r2 = conduit.validRequst("user01", "puser02")
        self.assertTrue(r1 is not None)
        self.assertTrue(r2 is not None)

        self.assertRaises(DirectoryRecordNotFoundError, conduit.validRequst, "bogus01", "user02")
        self.assertRaises(DirectoryRecordNotFoundError, conduit.validRequst, "user01", "bogus02")
        self.assertRaises(FailedCrossPodRequestError, conduit.validRequst, "user01", "user02")



class TestConduitToConduit(MultiStoreConduitTest):

    class FakeConduit(PoddingConduit):

        @inlineCallbacks
        def send_fake(self, txn, ownerUID, shareeUID):
            _ignore_owner, sharee = self.validRequst(ownerUID, shareeUID)
            action = {
                "action": "fake",
                "echo": "bravo"
            }

            result = yield self.sendRequest(txn, sharee, action)
            returnValue(result)


        def recv_fake(self, txn, j):
            return succeed({
                "result": "ok",
                "back2u": j["echo"],
                "more": "bits",
            })


    def makeConduit(self, store):
        """
        Use our own variant.
        """
        conduit = self.FakeConduit(store)
        conduit.conduitRequestClass = FakeConduitRequest
        return conduit


    @inlineCallbacks
    def test_fake_action(self):
        """
        Cross-pod request works when conduit does support the action.
        """

        txn = self.transactionUnderTest()
        store1 = self.storeUnderTest()
        response = yield store1.conduit.send_fake(txn, "user01", "puser01")
        self.assertTrue("result" in response)
        self.assertEqual(response["result"], "ok")
        self.assertTrue("back2u" in response)
        self.assertEqual(response["back2u"], "bravo")
        self.assertTrue("more" in response)
        self.assertEqual(response["more"], "bits")
        yield txn.commit()

        store2 = self.otherStoreUnderTest()
        txn = store2.newTransaction()
        response = yield store2.conduit.send_fake(txn, "puser01", "user01")
        self.assertTrue("result" in response)
        self.assertEqual(response["result"], "ok")
        self.assertTrue("back2u" in response)
        self.assertEqual(response["back2u"], "bravo")
        self.assertTrue("more" in response)
        self.assertEqual(response["more"], "bits")
        yield txn.commit()



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

    caldata2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:ui2
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
    def test_basic_share(self):
        """
        Test that basic invite/uninvite works.
        """

        yield self.createShare("user01", "puser01")

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        shared = yield  calendar1.shareeView("puser01")
        self.assertEqual(shared.shareStatus(), _BIND_STATUS_ACCEPTED)
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        self.assertTrue(shared is not None)
        self.assertTrue(shared.external())
        yield self.otherCommit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar1.uninviteUserFromShare("puser01")
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        self.assertTrue(shared is None)
        yield self.otherCommit()


    @inlineCallbacks
    def test_countobjects(self):
        """
        Test that action=countobjects works.
        """

        yield self.createShare("user01", "puser01")

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        count = yield shared.countObjectResources()
        self.assertEqual(count, 0)
        yield self.otherCommit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        yield  calendar1.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        count = yield calendar1.countObjectResources()
        self.assertEqual(count, 1)
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        count = yield shared.countObjectResources()
        self.assertEqual(count, 1)
        yield self.otherCommit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        object1 = yield self.calendarObjectUnderTest(home="user01", calendar_name="calendar", name="1.ics")
        yield  object1.remove()
        count = yield calendar1.countObjectResources()
        self.assertEqual(count, 0)
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        count = yield shared.countObjectResources()
        self.assertEqual(count, 0)
        yield self.otherCommit()


    @inlineCallbacks
    def test_listobjects(self):
        """
        Test that action=listobjects works.
        """

        yield self.createShare("user01", "puser01")

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        objects = yield shared.listObjectResources()
        self.assertEqual(set(objects), set())
        yield self.otherCommit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        yield  calendar1.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield  calendar1.createCalendarObjectWithName("2.ics", Component.fromString(self.caldata2))
        objects = yield calendar1.listObjectResources()
        self.assertEqual(set(objects), set(("1.ics", "2.ics",)))
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        objects = yield shared.listObjectResources()
        self.assertEqual(set(objects), set(("1.ics", "2.ics",)))
        yield self.otherCommit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        object1 = yield self.calendarObjectUnderTest(home="user01", calendar_name="calendar", name="1.ics")
        yield  object1.remove()
        objects = yield calendar1.listObjectResources()
        self.assertEqual(set(objects), set(("2.ics",)))
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        objects = yield shared.listObjectResources()
        self.assertEqual(set(objects), set(("2.ics",)))
        yield self.otherCommit()


    @inlineCallbacks
    def test_synctoken(self):
        """
        Test that action=synctoken works.
        """

        yield self.createShare("user01", "puser01")

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        token1_1 = yield calendar1.syncToken()
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        token2_1 = yield shared.syncToken()
        yield self.otherCommit()

        self.assertEqual(token1_1, token2_1)

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        yield  calendar1.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield self.commit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        token1_2 = yield calendar1.syncToken()
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        token2_2 = yield shared.syncToken()
        yield self.otherCommit()

        self.assertNotEqual(token1_1, token1_2)
        self.assertEqual(token1_2, token2_2)

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        object1 = yield self.calendarObjectUnderTest(home="user01", calendar_name="calendar", name="1.ics")
        yield  object1.remove()
        count = yield calendar1.countObjectResources()
        self.assertEqual(count, 0)
        yield self.commit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        token1_3 = yield calendar1.syncToken()
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        token2_3 = yield shared.syncToken()
        yield self.otherCommit()

        self.assertNotEqual(token1_1, token1_3)
        self.assertNotEqual(token1_2, token1_3)
        self.assertEqual(token1_3, token2_3)


    @inlineCallbacks
    def test_resourcenamessincerevision(self):
        """
        Test that action=synctoken works.
        """

        yield self.createShare("user01", "puser01")

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        token1_1 = yield calendar1.syncToken()
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        token2_1 = yield shared.syncToken()
        yield self.otherCommit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        yield  calendar1.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield self.commit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        token1_2 = yield calendar1.syncToken()
        names1 = yield calendar1.resourceNamesSinceToken(token1_1)
        self.assertEqual(names1, (["1.ics"], [],))
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        token2_2 = yield shared.syncToken()
        names2 = yield shared.resourceNamesSinceToken(token2_1)
        self.assertEqual(names2, (["1.ics"], [],))
        yield self.otherCommit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        object1 = yield self.calendarObjectUnderTest(home="user01", calendar_name="calendar", name="1.ics")
        yield  object1.remove()
        count = yield calendar1.countObjectResources()
        self.assertEqual(count, 0)
        yield self.commit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        token1_3 = yield calendar1.syncToken()
        names1 = yield calendar1.resourceNamesSinceToken(token1_2)
        self.assertEqual(names1, ([], ["1.ics"],))
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        token2_3 = yield shared.syncToken()
        names2 = yield shared.resourceNamesSinceToken(token2_2)
        self.assertEqual(names2, ([], ["1.ics"],))
        yield self.otherCommit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        names1 = yield calendar1.resourceNamesSinceToken(token1_3)
        self.assertEqual(names1, ([], [],))
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        names2 = yield shared.resourceNamesSinceToken(token2_3)
        self.assertEqual(names2, ([], [],))
        yield self.otherCommit()


    @inlineCallbacks
    def test_resourceuidforname(self):
        """
        Test that action=resourceuidforname works.
        """

        yield self.createShare("user01", "puser01")

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        yield  calendar1.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield self.commit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        uid = yield calendar1.resourceUIDForName("1.ics")
        self.assertEqual(uid, "uid1")
        uid = yield calendar1.resourceUIDForName("2.ics")
        self.assertTrue(uid is None)
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        uid = yield shared.resourceUIDForName("1.ics")
        self.assertEqual(uid, "uid1")
        uid = yield shared.resourceUIDForName("2.ics")
        self.assertTrue(uid is None)
        yield self.otherCommit()


    @inlineCallbacks
    def test_resourcenameforuid(self):
        """
        Test that action=resourcenameforuid works.
        """

        yield self.createShare("user01", "puser01")

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        yield  calendar1.createCalendarObjectWithName("1.ics", Component.fromString(self.caldata1))
        yield self.commit()

        calendar1 = yield self.calendarUnderTest(home="user01", name="calendar")
        uid = yield calendar1.resourceNameForUID("uid1")
        self.assertEqual(uid, "1.ics")
        uid = yield calendar1.resourceNameForUID("uid2")
        self.assertTrue(uid is None)
        yield self.commit()

        shared = yield self.calendarUnderTest(txn=self.newOtherTransaction(), home="puser01", name="shared-calendar")
        uid = yield shared.resourceNameForUID("uid1")
        self.assertEqual(uid, "1.ics")
        uid = yield shared.resourceNameForUID("uid2")
        self.assertTrue(uid is None)
        yield self.otherCommit()
