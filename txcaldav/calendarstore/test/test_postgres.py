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
from twisted.internet.defer import Deferred
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



sharedService = None
currentTestID = None

class SQLStorageTests(CommonTests, unittest.TestCase):
    """
    File storage tests.
    """

    def setUp(self):
        global sharedService
        global currentTestID
        currentTestID = self.id()
        if sharedService is None:
            ready = Deferred()
            def getReady(connectionFactory):
                global calendarStore
                try:
                    calendarStore = PostgresStore(
                        lambda label=None: connectionFactory(
                            label or currentTestID
                        )
                    )
                except:
                    ready.errback()
                    raise
                else:
                    self.cleanAndPopulate().chainDeferred(ready)
                return calendarStore
            sharedService = PostgresService(
                CachingFilePath("../_test_postgres_db"),
                getReady, v1_schema, "caldav"
            )
            sharedService.startService()
            def startStopping():
                log.msg("Starting stopping.")
                sharedService.unpauseMonitor()
                dumpConnectionStatus()
                return sharedService.stopService()
            reactor.addSystemEventTrigger(#@UndefinedVariable
                "before", "shutdown", startStopping)
            return ready
        else:
            return self.cleanAndPopulate()


    def cleanAndPopulate(self):
        """
        Delete everything from the database, then clean it up.
        """
        dumpConnectionStatus()
        cleanupConn = calendarStore.connectionFactory(
            "%s schema-cleanup" % (self.id(),)
        )
        cursor = cleanupConn.cursor()
        cursor.execute("delete from RESOURCE_PROPERTY")
        cleanupConn.commit()
        cursor.execute("delete from ATTACHMENT")
        cleanupConn.commit()
        cursor.execute("delete from CALENDAR_OBJECT")
        cleanupConn.commit()
        cursor.execute("delete from CALENDAR_BIND")
        cleanupConn.commit()
        cursor.execute("delete from CALENDAR")
        cleanupConn.commit()
        cursor.execute("delete from CALENDAR_HOME")
        cleanupConn.commit()
        cleanupConn.close()
        self.populate()
        sharedService.unpauseMonitor()
        # I need to allow the log buffer to unspool.
        return deferLater(reactor, 0.1, lambda : None)


    def tearDown(self):
        super(SQLStorageTests, self).tearDown()
        def stopit():
            sharedService.pauseMonitor()
        return deferLater(reactor, 0.1, stopit)


    def populate(self):
        populateTxn = calendarStore.newTransaction()
        for homeUID in self.requirements:
            calendars = self.requirements[homeUID]
            if calendars is not None:
                home = populateTxn.calendarHomeWithUID(homeUID, True)
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


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return calendarStore

