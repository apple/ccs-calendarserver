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

from txcaldav.calendarstore.test.common import CommonTests

from twisted.trial import unittest
from txdav.datastore.subpostgres import PostgresService
from txcaldav.calendarstore.postgres import PostgresStore, v1_schema
from twisted.internet.defer import Deferred
from twisted.internet import reactor
from twext.python.filepath import CachingFilePath
from twext.python.vcomponent import VComponent
from twisted.internet.task import deferLater



sharedService = None

class SQLStorageTests(CommonTests, unittest.TestCase):
    """
    File storage tests.
    """

    def setUp(self):
        global sharedService
        if sharedService is None:
            ready = Deferred()
            def getReady(connectionFactory):
                global calendarStore
                calendarStore = PostgresStore(connectionFactory)
                self.populate()
                ready.callback(None)
                return calendarStore
            sharedService = PostgresService(
                CachingFilePath("pg"), getReady, v1_schema, "caldav"
            )
            sharedService.startService()
            def startStopping():
                for pipe in sharedService.monitor.transport.pipes.values():
                    pipe.startReading()
                    pipe.startWriting()
                sharedService.stopService()
            reactor.addSystemEventTrigger(
                "before", "shutdown", startStopping)
            return ready
        else:
            cleanupConn = calendarStore.connectionFactory()
            cursor = cleanupConn.cursor()
            cursor.execute("delete from RESOURCE_PROPERTY")
            cursor.execute("delete from ATTACHMENT")
            cursor.execute("delete from CALENDAR_OBJECT")
            cursor.execute("delete from CALENDAR_BIND")
            cursor.execute("delete from CALENDAR")
            cursor.execute("delete from CALENDAR_HOME")
            cleanupConn.commit()
            cleanupConn.close()
            self.populate()
            for pipe in sharedService.monitor.transport.pipes.values():
                pipe.startReading()
                pipe.startWriting()
            # I need to allow the log buffer to unspool.
            return deferLater(reactor, 0.1, lambda : None)


    def tearDown(self):
        def stopit():
            for pipe in sharedService.monitor.transport.pipes.values():
                pipe.stopReading()
                pipe.stopWriting()
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

