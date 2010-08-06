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
Tests for txcaldav.calendarstore.postgres, mostly based on
L{txcaldav.calendarstore.test.common}.
"""


from txcaldav.calendarstore.test.common import CommonTests

from twisted.trial import unittest
from txdav.datastore.subpostgres import PostgresService, \
    DiagnosticConnectionWrapper
from txcaldav.calendarstore.postgres import PostgresStore, v1_schema
from twisted.internet.defer import Deferred, inlineCallbacks, succeed
from twisted.internet import reactor
from twext.python.filepath import CachingFilePath
from twext.python.vcomponent import VComponent
from twisted.internet.task import deferLater
from twisted.python import log
import gc



def allInstancesOf(cls):
    for o in gc.get_referrers(cls):
        if isinstance(o, cls):
            yield o



def dumpConnectionStatus():
    print '+++ ALL CONNECTIONS +++'
    for connection in allInstancesOf(DiagnosticConnectionWrapper):
        print connection.label, connection.state
    print '--- CONNECTIONS END ---'



class StoreBuilder(object):
    """
    Test-fixture-builder which can construct a PostgresStore.
    """
    sharedService = None
    currentTestID = None

    SHARED_DB_PATH = "../_test_postgres_db"

    def buildStore(self, testCase, notifierFactory):
        """
        Do the necessary work to build a store for a particular test case.

        @return: a L{Deferred} which fires with an L{IDataStore}.
        """
        currentTestID = testCase.id()
        dbRoot = CachingFilePath(self.SHARED_DB_PATH)
        if self.sharedService is None:
            ready = Deferred()
            def getReady(connectionFactory):
                attachmentRoot = dbRoot.child("attachments")
                try:
                    attachmentRoot.createDirectory()
                except OSError:
                    pass
                try:
                    self.calendarStore = PostgresStore(
                        lambda label=None: connectionFactory(
                            label or currentTestID
                        ),
                        notifierFactory,
                        attachmentRoot
                    )
                except:
                    ready.errback()
                    raise
                else:
                    self.cleanDatabase(testCase)
                    ready.callback(self.calendarStore)
                return self.calendarStore
            self.sharedService = PostgresService(
                dbRoot,
                getReady, v1_schema, "caldav"
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
            self.calendarStore.notifierFactory = notifierFactory
            self.cleanDatabase(testCase)
            result = succeed(self.calendarStore)

        def cleanUp():
            # FIXME: clean up any leaked connections and report them with an
            # immediate test failure.
            def stopit():
                self.sharedService.pauseMonitor()
            return deferLater(reactor, 0.1, stopit)
        testCase.addCleanup(cleanUp)
        return result


    def cleanDatabase(self, testCase):
        cleanupConn = self.calendarStore.connectionFactory(
            "%s schema-cleanup" % (testCase.id(),)
        )
        cursor = cleanupConn.cursor()
        tables = ['RESOURCE_PROPERTY',
                  'ATTACHMENT',
                  'ADDRESSBOOK_OBJECT',
                  'CALENDAR_OBJECT',
                  'CALENDAR_BIND',
                  'ADDRESSBOOK_BIND',
                  'CALENDAR',
                  'ADDRESSBOOK',
                  'CALENDAR_HOME',
                  'ADDRESSBOOK_HOME']
        for table in tables:
            try:
                cursor.execute("delete from "+table)
            except:
                log.err()
        cleanupConn.commit()
        cleanupConn.close()



theStoreBuilder = StoreBuilder()
buildStore = theStoreBuilder.buildStore


class SQLStorageTests(CommonTests, unittest.TestCase):
    """
    File storage tests.
    """

    @inlineCallbacks
    def setUp(self):
        super(SQLStorageTests, self).setUp()
        self.calendarStore = yield buildStore(self, self.notifierFactory)
        self.populate()


    def populate(self):
        populateTxn = self.calendarStore.newTransaction()
        for homeUID in self.requirements:
            calendars = self.requirements[homeUID]
            if calendars is not None:
                home = populateTxn.calendarHomeWithUID(homeUID, True)
                # We don't want the default calendar to appear unless it's
                # explicitly listed.
                home.removeCalendarWithName("calendar")
                for calendarName in calendars:
                    calendarObjNames = calendars[calendarName]
                    if calendarObjNames is not None:
                        home.createCalendarWithName(calendarName)
                        calendar = home.calendarWithName(calendarName)
                        for objectName in calendarObjNames:
                            objData = calendarObjNames[objectName]
                            calendar.createCalendarObjectWithName(
                                objectName, VComponent.fromString(objData)
                            )
        populateTxn.commit()
        self.notifierFactory.history = []


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self.calendarStore

