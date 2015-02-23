##
# Copyright (c) 2012-2015 Apple Inc. All rights reserved.
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
Tests for L{txdav.common.datastore.sql}.
"""

from uuid import UUID

from pycalendar.datetime import DateTime
from twext.enterprise.dal.syntax import Insert
from twext.enterprise.dal.syntax import Select
from twext.enterprise.jobqueue import JobItem
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.internet.task import Clock
from twisted.trial.unittest import TestCase
from twistedcaldav.ical import Component
from twistedcaldav.test.util import StoreTestCase
# from twistedcaldav.vcard import Component as VCard
from txdav.common.datastore.sql import (
    log, CommonStoreTransactionMonitor,
    CommonHome, CommonHomeChild, ECALENDARTYPE
)
from txdav.common.datastore.sql import fixUUIDNormalization
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.test.util import CommonCommonTests
from txdav.common.icommondatastore import AllRetriesFailed
from txdav.xml import element as davxml



exampleUID = UUID("a" * 32)
denormalizedUID = unicode(exampleUID)
normalizedUID = denormalizedUID.upper()


class CommonSQLStoreTests(CommonCommonTests, TestCase):
    """
    Tests for shared functionality in L{txdav.common.datastore.sql}.
    """

    @inlineCallbacks
    def setUp(self):
        """
        Set up two stores to migrate between.
        """
        yield super(CommonSQLStoreTests, self).setUp()
        yield self.buildStoreAndDirectory(
            extraUids=(denormalizedUID, normalizedUID, u"uid")
        )


    @inlineCallbacks
    def test_logging(self):
        """
        txn.execSQL works with all logging options on.
        """

        # Patch config to turn on logging then rebuild the store
        self.patch(self.store, "logLabels", True)
        self.patch(self.store, "logStats", True)
        self.patch(self.store, "logSQL", True)

        txn = self.transactionUnderTest()
        cs = schema.CALENDARSERVER
        version = (yield Select(
            [cs.VALUE, ],
            From=cs,
            Where=cs.NAME == 'VERSION',
        ).on(txn))
        self.assertNotEqual(version, None)
        self.assertEqual(len(version), 1)
        self.assertEqual(len(version[0]), 1)


    def test_logWaits(self):
        """
        CommonStoreTransactionMonitor logs waiting transactions.
        """

        c = Clock()
        self.patch(CommonStoreTransactionMonitor, "callLater", c.callLater)

        # Patch config to turn on log waits then rebuild the store
        self.patch(self.store, "logTransactionWaits", 1)

        ctr = [0]

        def counter(*args, **kwargs):
            ctr[0] += 1

        self.patch(log, "error", counter)

        txn = self.transactionUnderTest()

        c.advance(2)
        self.assertNotEqual(ctr[0], 0)
        txn.abort()


    def test_txnTimeout(self):
        """
        CommonStoreTransactionMonitor terminates long transactions.
        """

        c = Clock()
        self.patch(CommonStoreTransactionMonitor, "callLater", c.callLater)

        # Patch config to turn on transaction timeouts then rebuild the store
        self.patch(self.store, "timeoutTransactions", 1)

        ctr = [0]

        def counter(*args, **kwargs):
            ctr[0] += 1

        self.patch(log, "error", counter)

        txn = self.transactionUnderTest()
        self.assertFalse(txn.timedout)

        c.advance(2)
        self.assertNotEqual(ctr[0], 0)
        self.assertTrue(txn._sqlTxn._completed)
        self.assertTrue(txn.timedout)


    def test_logWaitsAndTxnTimeout(self):
        """
        CommonStoreTransactionMonitor logs waiting transactions and terminates
        long transactions.
        """

        c = Clock()
        self.patch(CommonStoreTransactionMonitor, "callLater", c.callLater)

        # Patch config to turn on log waits then rebuild the store
        self.patch(self.store, "logTransactionWaits", 1)
        self.patch(self.store, "timeoutTransactions", 2)

        ctr = [0, 0]

        def counter(logStr, *args, **kwargs):
            if "wait" in logStr:
                ctr[0] += 1
            elif "abort" in logStr:
                ctr[1] += 1

        self.patch(log, "error", counter)

        txn = self.transactionUnderTest()

        c.advance(2)
        self.assertNotEqual(ctr[0], 0)
        self.assertNotEqual(ctr[1], 0)
        self.assertTrue(txn._sqlTxn._completed)


    @inlineCallbacks
    def test_subtransactionOK(self):
        """
        txn.subtransaction runs loop once.
        """

        txn = self.transactionUnderTest()
        ctr = [0]

        def _test(subtxn):
            ctr[0] += 1
            cs = schema.CALENDARSERVER
            return Select(
                [cs.VALUE, ],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(subtxn)

        (yield txn.subtransaction(_test, retries=0))[0][0]
        self.assertEqual(ctr[0], 1)


    @inlineCallbacks
    def test_subtransactionOKAfterRetry(self):
        """
        txn.subtransaction runs loop twice when one failure.
        """

        txn = self.transactionUnderTest()
        ctr = [0]

        def _test(subtxn):
            ctr[0] += 1
            if ctr[0] == 1:
                raise ValueError
            cs = schema.CALENDARSERVER
            return Select(
                [cs.VALUE, ],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(subtxn)

        (yield txn.subtransaction(_test, retries=1))[0][0]
        self.assertEqual(ctr[0], 2)


    @inlineCallbacks
    def test_subtransactionFailNoRetry(self):
        """
        txn.subtransaction runs loop once when one failure and no retries.
        """

        txn = self.transactionUnderTest()
        ctr = [0]

        def _test(subtxn):
            ctr[0] += 1
            raise ValueError
            cs = schema.CALENDARSERVER
            return Select(
                [cs.VALUE, ],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(subtxn)

        try:
            (yield txn.subtransaction(_test, retries=0))[0][0]
        except AllRetriesFailed:
            pass
        else:
            self.fail("AllRetriesFailed not raised")
        self.assertEqual(ctr[0], 1)


    @inlineCallbacks
    def test_subtransactionFailSomeRetries(self):
        """
        txn.subtransaction runs loop three times when all fail and two retries
        requested.
        """

        txn = self.transactionUnderTest()
        ctr = [0]

        def _test(subtxn):
            ctr[0] += 1
            raise ValueError
            cs = schema.CALENDARSERVER
            return Select(
                [cs.VALUE, ],
                From=cs,
                Where=cs.NAME == 'VERSION',
            ).on(subtxn)

        try:
            (yield txn.subtransaction(_test, retries=2))[0][0]
        except AllRetriesFailed:
            pass
        else:
            self.fail("AllRetriesFailed not raised")
        self.assertEqual(ctr[0], 3)


    @inlineCallbacks
    def test_subtransactionAbortOuterTransaction(self):
        """
        If an outer transaction that is holding a subtransaction open is
        aborted, then the L{Deferred} returned by L{subtransaction} raises
        L{AllRetriesFailed}.
        """
        txn = self.transactionUnderTest()
        cs = schema.CALENDARSERVER
        yield Select([cs.VALUE], From=cs).on(txn)
        waitAMoment = Deferred()

        @inlineCallbacks
        def later(subtxn):
            yield waitAMoment
            value = yield Select([cs.VALUE], From=cs).on(subtxn)
            returnValue(value)

        started = txn.subtransaction(later)
        txn.abort()
        waitAMoment.callback(True)
        try:
            result = yield started
        except AllRetriesFailed:
            pass
        else:
            self.fail("AllRetriesFailed not raised, %r returned instead" %
                      (result,))


    @inlineCallbacks
    def test_changeRevision(self):
        """
        CommonHomeChild._changeRevision actions.
        """

        class TestCommonHome(CommonHome):
            pass

        class TestCommonHomeChild(CommonHomeChild):
            _homeChildSchema = schema.CALENDAR
            _homeChildMetaDataSchema = schema.CALENDAR_METADATA
            _bindSchema = schema.CALENDAR_BIND
            _revisionsSchema = schema.CALENDAR_OBJECT_REVISIONS

            def resourceType(self):
                return davxml.ResourceType.calendar

        txn = self.transactionUnderTest()
        home = yield txn.homeWithUID(ECALENDARTYPE, "uid", create=True)
        homeChild = yield TestCommonHomeChild.create(home, "B")

        # insert test
        token = yield homeChild.syncToken()
        yield homeChild._changeRevision("insert", "C")
        changed = yield homeChild.resourceNamesSinceToken(token)
        self.assertEqual(changed, (["C"], [], [],))

        # update test
        token = yield homeChild.syncToken()
        yield homeChild._changeRevision("update", "C")
        changed = yield homeChild.resourceNamesSinceToken(token)
        self.assertEqual(changed, (["C"], [], [],))

        # delete test
        token = yield homeChild.syncToken()
        yield homeChild._changeRevision("delete", "C")
        changed = yield homeChild.resourceNamesSinceToken(token)
        self.assertEqual(changed, ([], ["C"], [],))

        # missing update test
        token = yield homeChild.syncToken()
        yield homeChild._changeRevision("update", "D")
        changed = yield homeChild.resourceNamesSinceToken(token)
        self.assertEqual(changed, (["D"], [], [],))

        # missing delete test
        token = yield homeChild.syncToken()
        yield homeChild._changeRevision("delete", "E")
        changed = yield homeChild.resourceNamesSinceToken(token)
        self.assertEqual(changed, ([], [], [],))

        yield txn.abort()


    @inlineCallbacks
    def test_normalizeColumnUUIDs(self):
        """
        L{_normalizeColumnUUIDs} upper-cases only UUIDs in a given column.
        """
        rp = schema.RESOURCE_PROPERTY
        txn = self.transactionUnderTest()
        # setup
        yield Insert({
            rp.RESOURCE_ID: 1,
            rp.NAME: "asdf",
            rp.VALUE: "property-value",
            rp.VIEWER_UID: "not-a-uuid"}).on(txn)
        yield Insert({
            rp.RESOURCE_ID: 2,
            rp.NAME: "fdsa",
            rp.VALUE: "another-value",
            rp.VIEWER_UID: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
        ).on(txn)
        # test
        from txdav.common.datastore.sql import _normalizeColumnUUIDs
        yield _normalizeColumnUUIDs(txn, rp.VIEWER_UID)
        self.assertEqual(
            map(
                list,
                (
                    yield Select(
                        [rp.RESOURCE_ID, rp.NAME, rp.VALUE, rp.VIEWER_UID],
                        From=rp,
                        OrderBy=rp.RESOURCE_ID, Ascending=True,
                    ).on(txn)
                )
            ),
            [
                [1, "asdf", "property-value", "not-a-uuid"],
                [
                    2, "fdsa",
                    "another-value", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
                ]
            ]
        )


    @inlineCallbacks
    def allHomeUIDs(self, table=schema.CALENDAR_HOME):
        """
        Get a listing of all UIDs in the current store.
        """
        results = yield (Select([table.OWNER_UID], From=table)
                         .on(self.transactionUnderTest()))
        yield self.commit()
        returnValue(results)


    @inlineCallbacks
    def test_fixUUIDNormalization_lowerToUpper(self):
        """
        L{fixUUIDNormalization} will fix the normalization of UUIDs.  If a home
        is found with the wrong case but no duplicate, it will simply be
        upper-cased.
        """
        t1 = self.transactionUnderTest()
        yield t1.calendarHomeWithUID(denormalizedUID, create=True)
        yield self.commit()
        yield fixUUIDNormalization(self.storeUnderTest())
        self.assertEqual(
            map(list, (yield self.allHomeUIDs())),
            [[normalizedUID]]
        )


    @inlineCallbacks
    def test_fixUUIDNormalization_lowerToUpper_notification(self):
        """
        L{fixUUIDNormalization} will fix the normalization of UUIDs.  If a home
        is found with the wrong case but no duplicate, it will simply be
        upper-cased.
        """
        t1 = self.transactionUnderTest()
        yield t1.notificationsWithUID(denormalizedUID, create=True)
        yield self.commit()
        yield fixUUIDNormalization(self.storeUnderTest())
        self.assertEqual(
            map(list, (yield self.allHomeUIDs(schema.NOTIFICATION_HOME))),
            [[normalizedUID]]
        )


    @inlineCallbacks
    def test_fixUUIDNormalization_lowerToUpper_addressbook(self):
        """
        L{fixUUIDNormalization} will fix the normalization of UUIDs.  If a home
        is found with the wrong case but no duplicate, it will simply be
        upper-cased.
        """
        t1 = self.transactionUnderTest()
        yield t1.addressbookHomeWithUID(denormalizedUID, create=True)
        yield self.commit()
        yield fixUUIDNormalization(self.storeUnderTest())
        self.assertEqual(
            map(list, (yield self.allHomeUIDs(schema.ADDRESSBOOK_HOME))),
            [[normalizedUID]]
        )


    @inlineCallbacks
    def test_inTransaction(self):
        """
        Make sure a successful operation commits the transaction while an
        unsuccessful operation (raised an exception) aborts the transaction.
        """

        store = self.storeUnderTest()

        def txnCreator(label):
            self.txn = StubTransaction(label)
            return self.txn

        def goodOperation(txn):
            return succeed(None)

        def badOperation(txn):
            1 / 0
            return succeed(None)

        yield store.inTransaction("good", goodOperation, txnCreator)
        self.assertEquals(self.txn.action, "committed")
        self.assertEquals(self.txn.label, "good")

        try:
            yield store.inTransaction("bad", badOperation, txnCreator)
        except:
            pass
        self.assertEquals(self.txn.action, "aborted")
        self.assertEquals(self.txn.label, "bad")



class StubTransaction(object):

    def __init__(self, label):
        self.label = label
        self.action = None


    def commit(self):
        self.action = "committed"
        return succeed(None)


    def abort(self):
        self.action = "aborted"
        return succeed(None)



class CommonTrashTests(StoreTestCase):

    @inlineCallbacks
    def _collectionForUser(self, txn, userName, collectionName):
        home = yield txn.calendarHomeWithUID(userName, create=True)
        collection = yield home.childWithName(collectionName)
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
        trash = yield home.childWithName("trash")

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
        self.assertFalse((yield resource.isTrash()))

        # Move object to trash
        yield resource.toTrash()

        # Verify it's in the trash
        self.assertTrue((yield resource.isTrash()))

        # No objects in collection
        objects = yield collection.listObjectResources()
        self.assertEquals(len(objects), 0)

        # One object in trash
        objects = yield trash.listObjectResources()
        self.assertEquals(len(objects), 1)

        # Put back from trash
        resource = yield self._getResource(txn, "user01", "trash", objects[0])
        yield resource.fromTrash()

        # Not in trash
        self.assertFalse((yield resource.isTrash()))

        # One object in collection
        objects = yield collection.listObjectResources()
        self.assertEquals(len(objects), 1)

        # No objects in trash
        objects = yield trash.listObjectResources()
        self.assertEquals(len(objects), 0)


        # Not implemented
#         #
#         # Now with addressbook
#         #

#         data2 = """BEGIN:VCARD
# VERSION:3.0
# PRODID:-//Apple Inc.//iOS 6.0//EN
# UID:41425f1b-b831-40f2-b0bb-e70ec0938afd
# FN:Test User
# N:User;Test;;;
# REV:20120613T002007Z
# TEL;type=CELL;type=VOICE;type=pref:(408) 555-1212
# END:VCARD
# """

#         print("ADDRESSBOOK TIME")

#         home = yield txn.addressbookHomeWithUID("user01", create=True)
#         collection = yield home.childWithName("addressbook")
#         trash = yield home.childWithName("trash")

#         # Create an object
#         resource = yield collection.createObjectResourceWithName(
#             "test.vcf",
#             VCard.fromString(data2)
#         )

#         # One object
#         objects = yield collection.listObjectResources()
#         self.assertEquals(len(objects), 1)

#         # Verify it's not in the trash
#         self.assertFalse((yield resource.isTrash()))

#         # Move object to trash
#         yield resource.toTrash()

#         # Verify it's in the trash
#         self.assertTrue((yield resource.isTrash()))

#         # No objects
#         objects = yield collection.listObjectResources()
#         self.assertEquals(len(objects), 0)

#         # One object in trash
#         objects = yield trash.listObjectResources()
#         print("OBJECT LIST", objects)
#         self.assertEquals(len(objects), 1)

#         # Put back from trash
#         print("FETCHING FROM TRASH USING", objects[0])
#         resource = yield self._getResource(txn, "user01", "trash", objects[0])
#         yield resource.fromTrash()

#         # Not in trash
#         self.assertFalse((yield resource.isTrash()))

#         # One object
#         objects = yield collection.listObjectResources()
#         self.assertEquals(len(objects), 1)

#         yield txn.commit()




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
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy is in the trash, still with user02 accepted
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "trash", "")
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
        data = yield self._getResource(txn, "user02", "trash", "")
        self.assertEquals(data, None)
        yield txn.commit()

        # user01 restores event from the trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", "trash", "")
        data = yield self._getResourceData(txn, "user01", "trash", "")
        yield resource.fromTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        # user01's copy should be back on their calendar
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=NEEDS-ACTION" in data)

        # user02's copy should be back on their calendar
        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=NEEDS-ACTION" in data)

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
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy is in the trash, still with user02 partstat
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "trash", "")
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
        data = yield self._getResource(txn, "user02", "trash", "")
        self.assertEquals(data, None)
        yield txn.commit()

        # user01 restores event from the trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", "trash", "")
        data = yield self._getResourceData(txn, "user01", "trash", "")
        yield resource.fromTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        # user01's copy should be back on their calendar
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("PARTSTAT=TENTATIVE" in data)

        # user02's copy should be back on their calendar
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
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        # user01's copy is in the trash, still with user02 accepted
        txn = self.store.newTransaction()
        data = yield self._getResourceData(txn, "user01", "trash", "")
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
        data = yield self._getResource(txn, "user02", "trash", "")
        self.assertEquals(data, None)
        yield txn.commit()

        # user01 restores event from the trash
        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", "trash", "")
        yield resource.fromTrash()
        yield txn.commit()

        yield JobItem.waitEmpty(self.store.newTransaction, reactor, 60)

        txn = self.store.newTransaction()

        # user01's trash should be empty
        resourceNames = yield self._getResourceNames(txn, "user01", "trash")
        self.assertEquals(len(resourceNames), 0)

        # user01 should have test.ics and a new .ics
        resourceNames = yield self._getResourceNames(txn, "user01", "calendar")
        self.assertEquals(len(resourceNames), 2)
        self.assertTrue("test.ics" in resourceNames)
        resourceNames.remove("test.ics")
        newName = resourceNames[0]

        # user01's test.ics -- verify it got split correctly
        data = yield self._getResourceData(txn, "user01", "calendar", "test.ics")
        self.assertTrue("COUNT=15" in data)

        # user01's new .ics -- verify it got split correctly
        data = yield self._getResourceData(txn, "user01", "calendar", newName)
        self.assertTrue("RRULE:FREQ=WEEKLY;UNTIL=" in data)

        # user02's copy should be back on their calendar, and not in trash

        resourceNames = yield self._getResourceNames(txn, "user02", "calendar")
        self.assertEquals(len(resourceNames), 1)
        resourceNames = yield self._getResourceNames(txn, "user02", "trash")
        self.assertEquals(len(resourceNames), 0)

        data = yield self._getResourceData(txn, "user02", "calendar", "")
        self.assertTrue("PARTSTAT=NEEDS-ACTION" in data)

        yield txn.commit()
