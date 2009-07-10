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
from twistedcaldav.index import Index, default_future_expansion_duration,\
    maximum_future_expansion_duration, IndexedSearchException,\
    AbstractCalendarIndex
from twistedcaldav.index import ReservationError, MemcachedUIDReserver
from twistedcaldav.instance import InvalidOverriddenInstanceError
from twistedcaldav.test.util import InMemoryMemcacheProtocol
import twistedcaldav.test.util
from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from vobject.icalendar import utc
import sqlite3

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

    def test_index_timespan(self):
        data = (
            (
                "#1.1 Simple component - busy",
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
                "20080601T000000Z", "20080602T000000Z",
                "mailto:user1@example.com",
                (('N', "2008-06-01 12:00:00+00:00", "2008-06-01 13:00:00+00:00", 'B'),),
            ),
            (
                "#1.2 Simple component - transparent",
                "1.2",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1.2
DTSTART:20080602T120000Z
DTEND:20080602T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
                "20080602T000000Z", "20080603T000000Z",
                "mailto:user1@example.com",
                (('N', "2008-06-02 12:00:00+00:00", "2008-06-02 13:00:00+00:00", 'F'),),
            ),
            (
                "#1.3 Simple component - canceled",
                "1.3",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1.3
DTSTART:20080603T120000Z
DTEND:20080603T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
""",
                "20080603T000000Z", "20080604T000000Z",
                "mailto:user1@example.com",
                (('N', "2008-06-03 12:00:00+00:00", "2008-06-03 13:00:00+00:00", 'F'),),
            ),
            (
                "#1.4 Simple component - tentative",
                "1.4",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-1.4
DTSTART:20080604T120000Z
DTEND:20080604T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
STATUS:TENTATIVE
END:VEVENT
END:VCALENDAR
""",
                "20080604T000000Z", "20080605T000000Z",
                "mailto:user1@example.com",
                (('N', "2008-06-04 12:00:00+00:00", "2008-06-04 13:00:00+00:00", 'T'),),
            ),
            (
                "#2.1 Recurring component - busy",
                "2.1",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2.1
DTSTART:20080605T120000Z
DTEND:20080605T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
END:VCALENDAR
""",
                "20080605T000000Z", "20080607T000000Z",
                "mailto:user1@example.com",
                (
                    ('N', "2008-06-05 12:00:00+00:00", "2008-06-05 13:00:00+00:00", 'B'),
                    ('N', "2008-06-06 12:00:00+00:00", "2008-06-06 13:00:00+00:00", 'B'),
                ),
            ),
            (
                "#2.2 Recurring component - busy",
                "2.2",
                """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890-2.2
DTSTART:20080607T120000Z
DTEND:20080607T130000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=DAILY;COUNT=2
END:VEVENT
BEGIN:VEVENT
UID:12345-67890-2.2
RECURRENCE-ID:20080608T120000Z
DTSTART:20080608T140000Z
DTEND:20080608T150000Z
ORGANIZER;CN="User 01":mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""",
                "20080607T000000Z", "20080609T000000Z",
                "mailto:user1@example.com",
                (
                    ('N', "2008-06-07 12:00:00+00:00", "2008-06-07 13:00:00+00:00", 'B'),
                    ('N', "2008-06-08 14:00:00+00:00", "2008-06-08 15:00:00+00:00", 'F'),
                ),
            ),
        )

        for description, name, calendar_txt, trstart, trend, organizer, instances in data:
            calendar = Component.fromString(calendar_txt)

            f = open(os.path.join(self.site.resource.fp.path, name), "w")
            f.write(calendar_txt)
            del f

            self.db.addResource(name, calendar)
            self.assertTrue(self.db.resourceExists(name), msg=description)

            # Create fake filter element to match time-range
            filter =  caldavxml.Filter(
                  caldavxml.ComponentFilter(
                      caldavxml.ComponentFilter(
                          TimeRange(
                              start=trstart,
                              end=trend,
                          ),
                          name=("VEVENT", "VFREEBUSY", "VAVAILABILITY"),
                      ),
                      name="VCALENDAR",
                   )
              )

            resources = self.db.indexedSearch(filter, fbtype=True)
            index_results = set()
            for _ignore_name, _ignore_uid, type, test_organizer, float, start, end, fbtype in resources:
                self.assertEqual(test_organizer, organizer, msg=description)
                index_results.add((float, start, end, fbtype,))

            self.assertEqual(set(instances), index_results, msg=description)

class SQLIndexUpgradeTests (twistedcaldav.test.util.TestCase):
    """
    Test abstract SQL DB class
    """

    class OldIndexv6(Index):

        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return "6"

        def _db_init_data_tables_base(self, q, uidunique):
            """
            Initialise the underlying database tables.
            @param q:           a database cursor to use.
            """
            #
            # RESOURCE table is the primary index table
            #   NAME: Last URI component (eg. <uid>.ics, RESOURCE primary key)
            #   UID: iCalendar UID (may or may not be unique)
            #   TYPE: iCalendar component type
            #   RECURRANCE_MAX: Highest date of recurrence expansion
            #
            if uidunique:
                q.execute(
                    """
                    create table RESOURCE (
                        NAME           text unique,
                        UID            text unique,
                        TYPE           text,
                        RECURRANCE_MAX date
                    )
                    """
                )
            else:
                q.execute(
                    """
                    create table RESOURCE (
                        NAME           text unique,
                        UID            text,
                        TYPE           text,
                        RECURRANCE_MAX date
                    )
                    """
                )
    
            #
            # TIMESPAN table tracks (expanded) timespans for resources
            #   NAME: Related resource (RESOURCE foreign key)
            #   FLOAT: 'Y' if start/end are floating, 'N' otherwise
            #   START: Start date
            #   END: End date
            #
            q.execute(
                """
                create table TIMESPAN (
                    NAME  text,
                    FLOAT text(1),
                    START date,
                    END   date
                )
                """
            )
    
            if uidunique:
                #
                # RESERVED table tracks reserved UIDs
                #   UID: The UID being reserved
                #   TIME: When the reservation was made
                #
                q.execute(
                    """
                    create table RESERVED (
                        UID  text unique,
                        TIME date
                    )
                    """
                )

        def _db_upgrade(self, old_version):
            """
            Upgrade the database tables.
            """
            
            return super(AbstractCalendarIndex, self)._db_upgrade(old_version)

        def _add_to_db(self, name, calendar, cursor = None, expand_until=None, reCreate=False):
            """
            Records the given calendar resource in the index with the given name.
            Resource names and UIDs must both be unique; only one resource name may
            be associated with any given UID and vice versa.
            NB This method does not commit the changes to the db - the caller
            MUST take care of that
            @param name: the name of the resource to add.
            @param calendar: a L{Calendar} object representing the resource
                contents.
            """
            uid = calendar.resourceUID()
    
            # Decide how far to expand based on the component
            master = calendar.masterComponent()
            if master is None or not calendar.isRecurring() and not calendar.isRecurringUnbounded():
                # When there is no master we have a set of overridden components - index them all.
                # When there is one instance - index it.
                # When bounded - index all.
                expand = datetime.datetime(2100, 1, 1, 0, 0, 0, tzinfo=utc)
            else:
                if expand_until:
                    expand = expand_until
                else:
                    expand = datetime.date.today() + default_future_expansion_duration
        
                if expand > (datetime.date.today() + maximum_future_expansion_duration):
                    raise IndexedSearchException
    
            try:
                instances = calendar.expandTimeRanges(expand, ignoreInvalidInstances=reCreate)
            except InvalidOverriddenInstanceError:
                raise
    
            self._delete_from_db(name, uid)
    
            for key in instances:
                instance = instances[key]
                start = instance.start.replace(tzinfo=utc)
                end = instance.end.replace(tzinfo=utc)
                float = 'Y' if instance.start.tzinfo is None else 'N'
                self._db_execute(
                    """
                    insert into TIMESPAN (NAME, FLOAT, START, END)
                    values (:1, :2, :3, :4)
                    """, name, float, start, end
                )
    
            # Special - for unbounded recurrence we insert a value for "infinity"
            # that will allow an open-ended time-range to always match it.
            if calendar.isRecurringUnbounded():
                start = datetime.datetime(2100, 1, 1, 0, 0, 0, tzinfo=utc)
                end = datetime.datetime(2100, 1, 1, 1, 0, 0, tzinfo=utc)
                float = 'N'
                self._db_execute(
                    """
                    insert into TIMESPAN (NAME, FLOAT, START, END)
                    values (:1, :2, :3, :4)
                    """, name, float, start, end
                )
                 
            self._db_execute(
                """
                insert into RESOURCE (NAME, UID, TYPE, RECURRANCE_MAX)
                values (:1, :2, :3, :4)
                """, name, uid, calendar.resourceType(), instances.limit
            )

    def setUp(self):
        super(SQLIndexUpgradeTests, self).setUp()
        self.site.resource.isCalendarCollection = lambda: True
        self.db = Index(self.site.resource)
        self.olddb = SQLIndexUpgradeTests.OldIndexv6(self.site.resource)

    def prepareOldDB(self):
        if os.path.exists(self.olddb.dbpath):
            os.remove(self.olddb.dbpath)

    def test_old_schema(self):
        
        self.prepareOldDB()

        schema = self.olddb._db_value_for_sql(
            """
            select VALUE from CALDAV
             where KEY = 'SCHEMA_VERSION'
            """)
        self.assertEqual(schema, self.olddb._db_version())

    def test_empty_upgrade(self):
        
        self.prepareOldDB()

        schema = self.olddb._db_value_for_sql(
            """
            select VALUE from CALDAV
             where KEY = 'SCHEMA_VERSION'
            """)
        self.assertEqual(schema, self.olddb._db_version())

        self.assertRaises(sqlite3.OperationalError, self.olddb._db_value_for_sql, "select ORGANIZER from RESOURCE")
        self.assertRaises(sqlite3.OperationalError, self.olddb._db_value_for_sql, "select FBTYPE from TIMESPAN")

        schema = self.db._db_value_for_sql(
            """
            select VALUE from CALDAV
             where KEY = 'SCHEMA_VERSION'
            """)
        self.assertEqual(schema, self.db._db_version())

        value = self.db._db_value_for_sql("select ORGANIZER from RESOURCE")
        self.assertEqual(value, None)

    def test_basic_upgrade(self):
        
        self.prepareOldDB()

        calendar_name = "1.ics"
        calendar_data = """BEGIN:VCALENDAR
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
"""

        self.olddb.addResource(calendar_name, Component.fromString(calendar_data))
        self.assertTrue(self.olddb.resourceExists(calendar_name))

        self.assertRaises(sqlite3.OperationalError, self.olddb._db_value_for_sql, "select ORGANIZER from RESOURCE")
        self.assertRaises(sqlite3.OperationalError, self.olddb._db_value_for_sql, "select FBTYPE from TIMESPAN")

        value = self.db._db_value_for_sql("select ORGANIZER from RESOURCE where NAME = :1", calendar_name)
        self.assertEqual(value, "?")

        value = self.db._db_value_for_sql("select FBTYPE from TIMESPAN where NAME = :1", calendar_name)
        self.assertEqual(value, "?")

        self.db.addResource(calendar_name, Component.fromString(calendar_data))
        self.assertTrue(self.olddb.resourceExists(calendar_name))

        value = self.db._db_value_for_sql("select ORGANIZER from RESOURCE where NAME = :1", calendar_name)
        self.assertEqual(value, "mailto:user1@example.com")

        value = self.db._db_value_for_sql("select FBTYPE from TIMESPAN where NAME = :1", calendar_name)
        self.assertEqual(value, "B")

class MemcacheTests(SQLIndexTests):
    def setUp(self):
        super(MemcacheTests, self).setUp()
        self.memcache = InMemoryMemcacheProtocol()
        self.db.reserver = MemcachedUIDReserver(self.db, self.memcache)


    def tearDown(self):
        for _ignore_k, v in self.memcache._timeouts.iteritems():
            if v.active():
                v.cancel()
