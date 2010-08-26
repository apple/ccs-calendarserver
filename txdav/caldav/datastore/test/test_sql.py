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

from txdav.caldav.datastore.test.common import CommonTests as CalendarCommonTests

from txdav.common.datastore.test.util import SQLStoreBuilder
from txdav.common.icommondatastore import NoSuchHomeChildError

from twisted.trial import unittest
from twisted.internet.defer import inlineCallbacks
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
