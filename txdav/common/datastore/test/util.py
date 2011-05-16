# -*- test-case-name: txdav.carddav.datastore.test -*-
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Store test utility functions
"""

import gc
from zope.interface.verify import verifyObject
from zope.interface.exceptions import BrokenMethodImplementation,\
    DoesNotImplement

from twext.python.filepath import CachingFilePath
from twext.python.vcomponent import VComponent
from twext.web2.dav.resource import TwistedGETContentMD5

from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet.task import deferLater
from twisted.python import log
from twisted.application.service import Service

from txdav.common.datastore.sql import CommonDataStore, v1_schema
from txdav.base.datastore.subpostgres import PostgresService
from txdav.base.datastore.dbapiclient import DiagnosticConnectionWrapper
from txdav.base.propertystore.base import PropertyName
from txdav.common.icommondatastore import NoSuchHomeChildError
from twext.enterprise.adbapi2 import ConnectionPool
from twisted.internet.defer import returnValue
from twistedcaldav.notify import Notifier, NodeCreationException
from twistedcaldav.vcard import Component as ABComponent

md5key = PropertyName.fromElement(TwistedGETContentMD5)

def allInstancesOf(cls):
    for o in gc.get_referrers(cls):
        if isinstance(o, cls):
            yield o



def dumpConnectionStatus():
    print '+++ ALL CONNECTIONS +++'
    for connection in allInstancesOf(DiagnosticConnectionWrapper):
        print connection.label, connection.state
    print '--- CONNECTIONS END ---'



class SQLStoreBuilder(object):
    """
    Test-fixture-builder which can construct a PostgresStore.
    """
    sharedService = None
    currentTestID = None

    SHARED_DB_PATH = "_test_sql_db"

    def buildStore(self, testCase, notifierFactory):
        """
        Do the necessary work to build a store for a particular test case.

        @return: a L{Deferred} which fires with an L{IDataStore}.
        """
        disableMemcacheForTest(testCase)
        dbRoot = CachingFilePath(self.SHARED_DB_PATH)
        attachmentRoot = dbRoot.child("attachments")
        if self.sharedService is None:
            ready = Deferred()
            def getReady(connectionFactory):
                self.makeAndCleanStore(
                    testCase, notifierFactory, attachmentRoot
                ).chainDeferred(ready)
                return Service()
            self.sharedService = PostgresService(
                dbRoot, getReady, v1_schema, resetSchema=True,
                databaseName="caldav",
                testMode=True
            )
            self.sharedService.startService()
            def startStopping():
                log.msg("Starting stopping.")
                self.sharedService.unpauseMonitor()
                return self.sharedService.stopService()
            reactor.addSystemEventTrigger(#@UndefinedVariable
                "before", "shutdown", startStopping)
            result = ready
        else:
            result = self.makeAndCleanStore(
                testCase, notifierFactory, attachmentRoot
            )
        def cleanUp():
            def stopit():
                self.sharedService.pauseMonitor()
            return deferLater(reactor, 0.1, stopit)
        testCase.addCleanup(cleanUp)
        return result


    @inlineCallbacks
    def makeAndCleanStore(self, testCase, notifierFactory, attachmentRoot):
        """
        Create a L{CommonDataStore} specific to the given L{TestCase}.

        This also creates a L{ConnectionPool} that gets stopped when the test
        finishes, to make sure that any test which fails will terminate
        cleanly.

        @return: a L{Deferred} that fires with a L{CommonDataStore}
        """
        try:
            attachmentRoot.createDirectory()
        except OSError:
            pass
        cp = ConnectionPool(self.sharedService.produceConnection)
        store = CommonDataStore(
            cp.connection, notifierFactory, attachmentRoot
        )
        currentTestID = testCase.id()
        store.label = currentTestID
        cp.startService()
        def stopIt():
            return cp.stopService()
        testCase.addCleanup(stopIt)
        yield self.cleanStore(testCase, store)
        returnValue(store)


    @inlineCallbacks
    def cleanStore(self, testCase, storeToClean):
        cleanupTxn = storeToClean.sqlTxnFactory(
            "%s schema-cleanup" % (testCase.id(),)
        )
        # TODO: should be getting these tables from a declaration of the schema
        # somewhere.
        tables = ['INVITE',
                  'RESOURCE_PROPERTY',
                  'ATTACHMENT',
                  'NOTIFICATION_OBJECT_REVISIONS',
                  'ADDRESSBOOK_OBJECT_REVISIONS',
                  'CALENDAR_OBJECT_REVISIONS',
                  'ADDRESSBOOK_OBJECT',
                  'CALENDAR_OBJECT',
                  'CALENDAR_BIND',
                  'ADDRESSBOOK_BIND',
                  'CALENDAR',
                  'ADDRESSBOOK',
                  'CALENDAR_HOME',
                  'ADDRESSBOOK_HOME',
                  'NOTIFICATION',
                  'NOTIFICATION_HOME']
        for table in tables:
            try:
                yield cleanupTxn.execSQL("delete from "+table, [])
            except:
                log.err()
        yield cleanupTxn.commit()
        
        # Deal with memcached items that must be cleared
        from txdav.caldav.datastore.sql import CalendarHome
        CalendarHome._cacher.flush_all()
        from txdav.carddav.datastore.sql import AddressBookHome
        AddressBookHome._cacher.flush_all()
        from txdav.base.propertystore.sql import PropertyStore
        PropertyStore._cacher.flush_all()

theStoreBuilder = SQLStoreBuilder()
buildStore = theStoreBuilder.buildStore



@inlineCallbacks
def populateCalendarsFrom(requirements, store):
    """
    Populate C{store} from C{requirements}.

    @param requirements: a dictionary of the format described by
        L{txdav.caldav.datastore.test.common.CommonTests.requirements}.

    @param store: the L{IDataStore} to populate with calendar data.
    """
    populateTxn = store.newTransaction()
    for homeUID in requirements:
        calendars = requirements[homeUID]
        if calendars is not None:
            home = yield populateTxn.calendarHomeWithUID(homeUID, True)
            # We don't want the default calendar or inbox to appear unless it's
            # explicitly listed.
            try:
                yield home.removeCalendarWithName("calendar")
                yield home.removeCalendarWithName("inbox")
            except NoSuchHomeChildError:
                pass
            for calendarName in calendars:
                calendarObjNames = calendars[calendarName]
                if calendarObjNames is not None:
                    # XXX should not be yielding!  this SQL will be executed
                    # first!
                    yield home.createCalendarWithName(calendarName)
                    calendar = yield home.calendarWithName(calendarName)
                    for objectName in calendarObjNames:
                        objData, metadata = calendarObjNames[objectName]
                        yield calendar.createCalendarObjectWithName(
                            objectName,
                            VComponent.fromString(objData),
                            metadata = metadata,
                        )
    yield populateTxn.commit()

@inlineCallbacks
def resetCalendarMD5s(md5s, store):
    """
    Change MD5s in C{store} from C{requirements}.

    @param requirements: a dictionary of the format described by
        L{txdav.caldav.datastore.test.common.CommonTests.requirements}.

    @param store: the L{IDataStore} to populate with calendar data.
    """
    populateTxn = store.newTransaction()
    for homeUID in md5s:
        calendars = md5s[homeUID]
        if calendars is not None:
            home = yield populateTxn.calendarHomeWithUID(homeUID, True)
            for calendarName in calendars:
                calendarObjNames = calendars[calendarName]
                if calendarObjNames is not None:
                    # XXX should not be yielding!  this SQL will be executed
                    # first!
                    calendar = yield home.calendarWithName(calendarName)
                    for objectName in calendarObjNames:
                        md5 = calendarObjNames[objectName]
                        obj = yield calendar.calendarObjectWithName(
                            objectName,
                        )
                        obj.properties()[md5key] = TwistedGETContentMD5.fromString(md5)
    yield populateTxn.commit()


@inlineCallbacks
def populateAddressBooksFrom(requirements, store):
    """
    Populate C{store} from C{requirements}.

    @param requirements: a dictionary of the format described by
        L{txdav.caldav.datastore.test.common.CommonTests.requirements}.

    @param store: the L{IDataStore} to populate with addressbook data.
    """
    populateTxn = store.newTransaction()
    for homeUID in requirements:
        addressbooks = requirements[homeUID]
        if addressbooks is not None:
            home = yield populateTxn.addressbookHomeWithUID(homeUID, True)
            # We don't want the default addressbook
            try:
                yield home.removeAddressBookWithName("addressbook")
            except NoSuchHomeChildError:
                pass
            for addressbookName in addressbooks:
                addressbookObjNames = addressbooks[addressbookName]
                if addressbookObjNames is not None:
                    # XXX should not be yielding!  this SQL will be executed
                    # first!
                    yield home.createAddressBookWithName(addressbookName)
                    addressbook = yield home.addressbookWithName(addressbookName)
                    for objectName in addressbookObjNames:
                        objData = addressbookObjNames[objectName]
                        yield addressbook.createAddressBookObjectWithName(
                            objectName,
                            ABComponent.fromString(objData),
                        )
    yield populateTxn.commit()

@inlineCallbacks
def resetAddressBookMD5s(md5s, store):
    """
    Change MD5s in C{store} from C{requirements}.

    @param requirements: a dictionary of the format described by
        L{txdav.caldav.datastore.test.common.CommonTests.requirements}.

    @param store: the L{IDataStore} to populate with addressbook data.
    """
    populateTxn = store.newTransaction()
    for homeUID in md5s:
        addressbooks = md5s[homeUID]
        if addressbooks is not None:
            home = yield populateTxn.addressbookHomeWithUID(homeUID, True)
            for addressbookName in addressbooks:
                addressbookObjNames = addressbooks[addressbookName]
                if addressbookObjNames is not None:
                    # XXX should not be yielding!  this SQL will be executed
                    # first!
                    addressbook = yield home.addressbookWithName(addressbookName)
                    for objectName in addressbookObjNames:
                        md5 = addressbookObjNames[objectName]
                        obj = yield addressbook.addressbookObjectWithName(
                            objectName,
                        )
                        obj.properties()[md5key] = TwistedGETContentMD5.fromString(md5)
    yield populateTxn.commit()


def assertProvides(testCase, interface, provider):
    """
    Verify that C{provider} properly provides C{interface}

    @type interface: L{zope.interface.Interface}
    @type provider: C{provider}
    """
    try:
        verifyObject(interface, provider)
    except BrokenMethodImplementation, e:
        testCase.fail(e)
    except DoesNotImplement, e:
        testCase.fail("%r does not provide %s.%s" %
                      (provider, interface.__module__, interface.getName()))



class CommonCommonTests(object):
    """
    Common utility functionality for file/store combination tests.
    """

    lastTransaction = None
    savedStore = None
    assertProvides = assertProvides
    lastCommitSetUp = False

    def transactionUnderTest(self):
        """
        Create a transaction from C{storeUnderTest} and save it as
        C[lastTransaction}.  Also makes sure to use the same store, saving the
        value from C{storeUnderTest}.
        """
        if not self.lastCommitSetUp:
            self.lastCommitSetUp = True
            self.addCleanup(self.commitLast)
        if self.lastTransaction is not None:
            return self.lastTransaction
        if self.savedStore is None:
            self.savedStore = self.storeUnderTest()
        self.counter += 1
        txn = self.lastTransaction = self.savedStore.newTransaction(
            self.id() + " #" + str(self.counter)
        )
        return txn


    def commit(self):
        """
        Commit the last transaction created from C{transactionUnderTest}, and
        clear it.
        """
        result = self.lastTransaction.commit()
        self.lastTransaction = None
        return result


    def abort(self):
        """
        Abort the last transaction created from C[transactionUnderTest}, and
        clear it.
        """
        result = self.lastTransaction.abort()
        self.lastTransaction = None
        return result


    def setUp(self):
        self.counter = 0
        self.notifierFactory = StubNotifierFactory()

    def commitLast(self):
        if self.lastTransaction is not None:
            return self.commit()


class StubNodeCacher(object):

    def waitForNode(self, notifier, nodeName):
        if "fail" in nodeName:
            raise NodeCreationException("Could not create node")
        else:
            return succeed(True)


class StubNotifierFactory(object):
    """
    For testing push notifications without an XMPP server.
    """

    def __init__(self):
        self.reset()
        self.nodeCacher = StubNodeCacher()
        self.pubSubConfig = {
            "enabled" : True,
            "service" : "pubsub.example.com",
            "host" : "example.com",
            "port" : "123",
        }

    def newNotifier(self, label="default", id=None, prefix=None):
        return Notifier(self, label=label, id=id, prefix=prefix)

    def send(self, op, id):
        self.history.append((op, id))

    def reset(self):
        self.history = []



def disableMemcacheForTest(aTest):
    """
    Disable all memcache logic for the duration of a test; we shouldn't be
    starting or connecting to any memcache stuff for most tests.
    """

    # These imports are local so that they don't accidentally leak to anything
    # else in this module; nothing else in this module should ever touch global
    # configuration. -glyph

    from twistedcaldav.config import config
    from twistedcaldav.memcacher import Memcacher

    aTest.patch(config.Memcached.Pools.Default, "ClientEnabled", False)
    aTest.patch(config.Memcached.Pools.Default, "ServerEnabled", False)
    aTest.patch(Memcacher, "allowTestCache", True)


