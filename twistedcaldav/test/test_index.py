##
# Copyright (c) 2007 Apple Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

from twistedcaldav.index import Index

import twistedcaldav.test.util
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.index import ReservationError
import os
import time

class TestIndex (twistedcaldav.test.util.TestCase):
    """
    Test abstract SQL DB class
    """
    
    def setUp(self):
        super(TestIndex, self).setUp()
        self.site.resource.isCalendarCollection = lambda: True

    def test_reserve_uid_ok(self):
        uid = "test-test-test"
        db = Index(self.site.resource)
        self.assertFalse(db.isReservedUID(uid))
        db.reserveUID(uid)
        self.assertTrue(db.isReservedUID(uid))
        db.unreserveUID(uid)
        self.assertFalse(db.isReservedUID(uid))

    def test_reserve_uid_twice(self):
        uid = "test-test-test"
        db = Index(self.site.resource)
        db.reserveUID(uid)
        self.assertTrue(db.isReservedUID(uid))
        self.assertRaises(ReservationError, db.reserveUID, uid)

    def test_unreserve_unreserved(self):
        uid = "test-test-test"
        db = Index(self.site.resource)
        self.assertRaises(ReservationError, db.unreserveUID, uid)

    def test_reserve_uid_timeout(self):
        uid = "test-test-test"
        old_timeout = twistedcaldav.index.reservation_timeout_secs
        twistedcaldav.index.reservation_timeout_secs = 2
        try:
            db = Index(self.site.resource)
            self.assertFalse(db.isReservedUID(uid))
            db.reserveUID(uid)
            self.assertTrue(db.isReservedUID(uid))
            time.sleep(3)
            self.assertFalse(db.isReservedUID(uid))
        finally:
            twistedcaldav.index.reservation_timeout_secs = old_timeout
