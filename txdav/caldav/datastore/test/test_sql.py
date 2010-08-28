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
Tests for txdav.caldav.datastore.postgres, mostly based on
L{txdav.caldav.datastore.test.common}.
"""

import time

from txdav.caldav.datastore.test.common import CommonTests as CalendarCommonTests

from txdav.common.datastore.sql import ECALENDARTYPE
from txdav.common.datastore.test.util import SQLStoreBuilder
from txdav.common.icommondatastore import NoSuchHomeChildError

from twisted.trial import unittest
from twisted.internet.defer import inlineCallbacks
from twisted.internet.threads import deferToThread
from twext.python.vcomponent import VComponent


theStoreBuilder = SQLStoreBuilder()
buildStore = theStoreBuilder.buildStore

class CalendarSQLStorageTests(CalendarCommonTests, unittest.TestCase):
    """
    Calendar SQL storage tests.
    """

    @inlineCallbacks
    def setUp(self):
        super(CalendarSQLStorageTests, self).setUp()
        self.calendarStore = yield buildStore(self, self.notifierFactory)
        self.populate()


    def populate(self):
        populateTxn = self.calendarStore.newTransaction()
        for homeUID in self.requirements:
            calendars = self.requirements[homeUID]
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
        self.notifierFactory.reset()


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self.calendarStore

    @inlineCallbacks
    def test_homeProvisioningConcurrency(self):

        calendarStore1 = yield buildStore(self, self.notifierFactory)
        calendarStore2 = yield buildStore(self, self.notifierFactory)
        calendarStore3 = yield buildStore(self, self.notifierFactory)

        txn1 = calendarStore1.newTransaction()
        txn2 = calendarStore2.newTransaction()
        txn3 = calendarStore3.newTransaction()
        
        # Provision one home now
        home_uid2 = txn3.homeWithUID(ECALENDARTYPE, "uid2", create=True)
        self.assertNotEqual(home_uid2, None)
        txn3.commit()

        home_uid1_1 = txn1.homeWithUID(ECALENDARTYPE, "uid1", create=True)
        
        def _defer_home_uid1_2():
            home_uid1_2 = txn2.homeWithUID(ECALENDARTYPE, "uid1", create=True)
            txn2.commit()
            return home_uid1_2
        d1 = deferToThread(_defer_home_uid1_2)
        
        def _pause_home_uid1_1():
            time.sleep(1)
            txn1.commit()
        d2 = deferToThread(_pause_home_uid1_1)
        
        # Verify that we can still get to the existing home - i.e. the lock
        # on the table allows concurrent reads
        txn4 = calendarStore3.newTransaction()
        home_uid2 = txn4.homeWithUID(ECALENDARTYPE, "uid2", create=True)
        self.assertNotEqual(home_uid2, None)
        txn4.commit()
        
        # Now do the concurrent provision attempt
        yield d2
        home_uid1_2 = yield d1
        
        self.assertNotEqual(home_uid1_1, None)
        self.assertNotEqual(home_uid1_2, None)
