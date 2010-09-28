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

from twext.python.filepath import CachingFilePath
from twext.python.vcomponent import VComponent

from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed
from twisted.internet.task import deferLater
from twisted.python import log

from txdav.common.datastore.sql import CommonDataStore, v1_schema
from txdav.base.datastore.subpostgres import PostgresService,\
    DiagnosticConnectionWrapper
from txdav.common.icommondatastore import NoSuchHomeChildError


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

    SHARED_DB_PATH = "../_test_sql_db"

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
                    self.store = CommonDataStore(
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
                    ready.callback(self.store)
                return self.store
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
            self.store.notifierFactory = notifierFactory
            self.cleanDatabase(testCase)
            result = succeed(self.store)

        def cleanUp():
            # FIXME: clean up any leaked connections and report them with an
            # immediate test failure.
            def stopit():
                self.sharedService.pauseMonitor()
            return deferLater(reactor, 0.1, stopit)
        testCase.addCleanup(cleanUp)
        return result


    def cleanDatabase(self, testCase):
        cleanupConn = self.store.connectionFactory(
            "%s schema-cleanup" % (testCase.id(),)
        )
        cursor = cleanupConn.cursor()
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
                cursor.execute("delete from "+table)
            except:
                log.err()
        cleanupConn.commit()
        cleanupConn.close()

theStoreBuilder = SQLStoreBuilder()
buildStore = theStoreBuilder.buildStore


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
            home = populateTxn.calendarHomeWithUID(homeUID, True)
            # We don't want the default calendar or inbox to appear unless it's
            # explicitly listed.
            try:
                home.removeCalendarWithName("calendar")
                home.removeCalendarWithName("inbox")
            except NoSuchHomeChildError:
                pass
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

