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
##

from twisted.internet import reactor
from twisted.internet.task import deferLater

from twistedcaldav.ical import Component
from twistedcaldav.index import Index
from twistedcaldav.index import ReservationError, MemcachedUIDReserver
from twistedcaldav.instance import InvalidOverriddenInstanceError
from twistedcaldav.test.util import InMemoryMemcacheProtocol
import twistedcaldav.test.util

import datetime
import os

class SQLIndexTests (twistedcaldav.test.util.TestCase):
    """
    Test abstract SQL DB class
    """

    def setUp(self):
        super(SQLIndexTests, self).setUp()
        self.site.resource.isCalendarCollection = lambda: True
        self.db = Index(self.site.resource)


    def test_reserve_uid_ok(self):
        uid = "test-test-test"
        d = self.db.isReservedUID(uid)
        d.addCallback(self.assertFalse)
        d.addCallback(lambda _: self.db.reserveUID(uid))
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertTrue)
        d.addCallback(lambda _: self.db.unreserveUID(uid))
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertFalse)

        return d


    def test_reserve_uid_twice(self):
        uid = "test-test-test"
        d = self.db.reserveUID(uid)
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertTrue)
        d.addCallback(lambda _:
                      self.assertFailure(self.db.reserveUID(uid),
                                         ReservationError))
        return d


    def test_unreserve_unreserved(self):
        uid = "test-test-test"
        return self.assertFailure(self.db.unreserveUID(uid),
                                  ReservationError)


    def test_reserve_uid_timeout(self):
        # WARNING: This test is fundamentally flawed and will fail
        # intermittently because it uses the real clock.
        uid = "test-test-test"
        from twistedcaldav.config import config
        old_timeout = config.UIDReservationTimeOut
        config.UIDReservationTimeOut = 1

        def _finally(result):
            config.UIDReservationTimeOut = old_timeout
            return result

        d = self.db.isReservedUID(uid)
        d.addCallback(self.assertFalse)
        d.addCallback(lambda _: self.db.reserveUID(uid))
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertTrue)
        d.addCallback(lambda _: deferLater(reactor, 2, lambda: None))
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertFalse)
        d.addBoth(_finally)

        return d


    def test_index(self):
        data = (
            (
                "#1.1 Simple component",
                "1.1",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1.1
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                True,
            ),
            (
                "#2.1 Recurring component",
                "2.1",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2.1
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=WEEKLY;COUNT=2
END:VEVENT
END:VCALENDAR
""",
                False,
                True,
            ),
            (
                "#2.2 Recurring component with override",
                "2.2",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2.2
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=WEEKLY;COUNT=2
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-2.2
RECURRENCE-ID:20080608T120000Z
DTSTART:20080608T120000Z
DTEND:20080608T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                True,
            ),
            (
                "#2.3 Recurring component with broken override - new",
                "2.3",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2.3
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=WEEKLY;COUNT=2
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-2.3
RECURRENCE-ID:20080609T120000Z
DTSTART:20080608T120000Z
DTEND:20080608T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                False,
                False,
            ),
            (
                "#2.4 Recurring component with broken override - existing",
                "2.4",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2.4
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=WEEKLY;COUNT=2
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-2.4
RECURRENCE-ID:20080609T120000Z
DTSTART:20080608T120000Z
DTEND:20080608T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""",
                True,
                True,
            ),
        )

        for description, name, calendar_txt, reCreate, ok in data:
            calendar = Component.fromString(calendar_txt)
            if ok:
                f = open(os.path.join(self.site.resource.fp.path, name), "w")
                f.write(calendar_txt)
                del f

                self.db.addResource(name, calendar, reCreate=reCreate)
                self.assertTrue(self.db.resourceExists(name), msg=description)
            else:
                self.assertRaises(InvalidOverriddenInstanceError, self.db.addResource, name, calendar)
                self.assertFalse(self.db.resourceExists(name), msg=description)

        self.db._db_recreate()
        for description, name, calendar_txt, reCreate, ok in data:
            if ok:
                self.assertTrue(self.db.resourceExists(name), msg=description)
            else:
                self.assertFalse(self.db.resourceExists(name), msg=description)

        self.db.testAndUpdateIndex(datetime.date(2020, 1, 1))
        for description, name, calendar_txt, reCreate, ok in data:
            if ok:
                self.assertTrue(self.db.resourceExists(name), msg=description)
            else:
                self.assertFalse(self.db.resourceExists(name), msg=description)

class MemcacheTests(SQLIndexTests):
    def setUp(self):
        super(MemcacheTests, self).setUp()
        self.memcache = InMemoryMemcacheProtocol()
        self.db.reserver = MemcachedUIDReserver(self.db, self.memcache)


    def tearDown(self):
        for k, v in self.memcache._timeouts.iteritems():
            if v.active():
                v.cancel()
