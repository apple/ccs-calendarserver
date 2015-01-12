##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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
Tests for txdav.caldav.datastore.cuaddress
"""

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from txdav.caldav.datastore.scheduling.cuaddress import calendarUserFromCalendarUserAddress, \
    LocalCalendarUser, InvalidCalendarUser
from txdav.common.datastore.test.util import populateCalendarsFrom, CommonCommonTests


class CalendarUser(CommonCommonTests, unittest.TestCase):
    """
    Tests for deleting events older than a given date
    """

    requirements = {
        "user01" : {
            "calendar1" : {},
            "inbox" : {},
        },
        "user02" : {
            "calendar2" : {},
            "inbox" : {},
        },
        "user03" : {
            "calendar3" : {},
            "inbox" : {},
        }
    }

    @inlineCallbacks
    def setUp(self):

        yield super(CalendarUser, self).setUp()
        yield self.buildStoreAndDirectory()
        yield self.populate()
        yield self.removeRecord(u"user03")


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @inlineCallbacks
    def test_lookup(self):
        """
        Test that L{CalendarUser.hosted} returns the expected results.
        """

        txn = self.transactionUnderTest()
        cu = yield calendarUserFromCalendarUserAddress("urn:x-uid:user01", txn)
        yield self.commit()

        self.assertTrue(isinstance(cu, LocalCalendarUser))
        self.assertTrue(cu.hosted())
        self.assertTrue(cu.validOriginator())
        self.assertTrue(cu.validRecipient())

        txn = self.transactionUnderTest()
        cu = yield calendarUserFromCalendarUserAddress("mailto:foobar@example.org", txn)
        yield self.commit()

        self.assertTrue(isinstance(cu, InvalidCalendarUser))
        self.assertFalse(cu.hosted())
        self.assertFalse(cu.validOriginator())
        self.assertFalse(cu.validRecipient())

        txn = self.transactionUnderTest()
        cu = yield calendarUserFromCalendarUserAddress("urn:x-uid:user03", txn)
        yield self.commit()

        self.assertTrue(isinstance(cu, LocalCalendarUser))
        self.assertTrue(cu.hosted())
        self.assertTrue(cu.validOriginator())
        self.assertFalse(cu.validRecipient())
