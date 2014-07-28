# #
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
# #

from pycalendar.timezone import Timezone

from twext.enterprise.dal.syntax import SQLFragment, Parameter

from twistedcaldav.test.util import TestCase
from twistedcaldav import caldavxml
from twistedcaldav.timezones import TimezoneCache

from txdav.caldav.datastore.index_file import sqlcalendarquery
from txdav.caldav.datastore.query.builder import buildExpression
from txdav.caldav.datastore.query.filter import Filter, FilterBase, TimeRange, \
    PropertyFilter, TextMatch
from txdav.caldav.datastore.query.generator import CalDAVSQLQueryGenerator
from txdav.common.datastore.sql_tables import schema

from dateutil.tz import tzutc
import datetime
from twistedcaldav.ical import Component

class TestQueryFilter(TestCase):

    _objectSchema = schema.CALENDAR_OBJECT
    _queryFields = {
        "UID": _objectSchema.UID,
        "TYPE": _objectSchema.ICALENDAR_TYPE,
    }

    def setUp(self):
        super(TestQueryFilter, self).setUp()
        TimezoneCache.create()


    def test_query(self):
        """
        Basic query test - no time range
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[caldavxml.ComponentFilter(
                    **{"name": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                )],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))

        expression = buildExpression(filter, self._queryFields)
        sql = CalDAVSQLQueryGenerator(expression, self, 1234)
        select, args, usedtimerange = sql.generate()

        self.assertEqual(select.toSQL(), SQLFragment(
            "select distinct RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = ? and ICALENDAR_TYPE in (?, ?, ?)",
            [1234, Parameter('arg1', 3)]
        ))
        self.assertEqual(args, {"arg1": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")})
        self.assertEqual(usedtimerange, False)


    def test_query_timerange(self):
        """
        Basic query test - with time range
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[caldavxml.ComponentFilter(
                    *[caldavxml.TimeRange(**{"start": "20060605T160000Z", "end": "20060605T170000Z"})],
                    **{"name": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                )],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))

        expression = buildExpression(filter, self._queryFields)
        sql = CalDAVSQLQueryGenerator(expression, self, 1234)
        select, args, usedtimerange = sql.generate()

        self.assertEqual(select.toSQL(), SQLFragment(
            "select distinct RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE from CALENDAR_OBJECT, TIME_RANGE where ICALENDAR_TYPE in (?, ?, ?) and (FLOATING = ? and START_DATE < ? and END_DATE > ? or FLOATING = ? and START_DATE < ? and END_DATE > ?) and CALENDAR_OBJECT_RESOURCE_ID = RESOURCE_ID and TIME_RANGE.CALENDAR_RESOURCE_ID = ?",
            [Parameter('arg1', 3), False, datetime.datetime(2006, 6, 5, 17, 0, tzinfo=tzutc()), datetime.datetime(2006, 6, 5, 16, 0, tzinfo=tzutc()), True, datetime.datetime(2006, 6, 5, 13, 0, tzinfo=tzutc()), datetime.datetime(2006, 6, 5, 12, 0, tzinfo=tzutc()), 1234]
        ))
        self.assertEqual(args, {"arg1": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")})
        self.assertEqual(usedtimerange, True)


    def test_query_freebusy(self):
        """
        Basic query test - with time range
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[caldavxml.ComponentFilter(
                    *[caldavxml.TimeRange(**{"start": "20060605T160000Z", "end": "20060605T170000Z"})],
                    **{"name": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                )],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))

        expression = buildExpression(filter, self._queryFields)
        sql = CalDAVSQLQueryGenerator(expression, self, 1234, "user01", True)
        select, args, usedtimerange = sql.generate()

        self.assertEqual(select.toSQL(), SQLFragment(
            "select distinct RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE, ORGANIZER, FLOATING, coalesce(ADJUSTED_START_DATE, START_DATE), coalesce(ADJUSTED_END_DATE, END_DATE), FBTYPE, TIME_RANGE.TRANSPARENT, PERUSER.TRANSPARENT from CALENDAR_OBJECT, TIME_RANGE left outer join PERUSER on INSTANCE_ID = TIME_RANGE_INSTANCE_ID and USER_ID = ? where ICALENDAR_TYPE in (?, ?, ?) and (FLOATING = ? and coalesce(ADJUSTED_START_DATE, START_DATE) < ? and coalesce(ADJUSTED_END_DATE, END_DATE) > ? or FLOATING = ? and coalesce(ADJUSTED_START_DATE, START_DATE) < ? and coalesce(ADJUSTED_END_DATE, END_DATE) > ?) and CALENDAR_OBJECT_RESOURCE_ID = RESOURCE_ID and TIME_RANGE.CALENDAR_RESOURCE_ID = ?",
            ['user01', Parameter('arg1', 3), False, datetime.datetime(2006, 6, 5, 17, 0, tzinfo=tzutc()), datetime.datetime(2006, 6, 5, 16, 0, tzinfo=tzutc()), True, datetime.datetime(2006, 6, 5, 13, 0, tzinfo=tzutc()), datetime.datetime(2006, 6, 5, 12, 0, tzinfo=tzutc()), 1234]
        ))
        self.assertEqual(args, {"arg1": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")})
        self.assertEqual(usedtimerange, True)


    def test_query_not_extended(self):
        """
        Query test - two terms not anyof
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[
                    caldavxml.ComponentFilter(
                        **{"name": ("VEVENT")}
                    ),
                    caldavxml.ComponentFilter(
                        **{"name": ("VTODO")}
                    ),
                ],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))

        expression = buildExpression(filter, self._queryFields)
        sql = CalDAVSQLQueryGenerator(expression, self, 1234)
        select, args, usedtimerange = sql.generate()

        self.assertEqual(select.toSQL(), SQLFragment(
            "select distinct RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = ? and ICALENDAR_TYPE = ? and ICALENDAR_TYPE = ?",
            [1234, "VEVENT", "VTODO"]
        ))
        self.assertEqual(args, {})
        self.assertEqual(usedtimerange, False)


    def test_query_extended(self):
        """
        Extended query test - two terms with anyof
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[
                    caldavxml.ComponentFilter(
                        *[caldavxml.TimeRange(**{"start": "20060605T160000Z", })],
                        **{"name": ("VEVENT")}
                    ),
                    caldavxml.ComponentFilter(
                        **{"name": ("VTODO")}
                    ),
                ],
                **{"name": "VCALENDAR", "test": "anyof"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))

        expression = buildExpression(filter, self._queryFields)
        sql = CalDAVSQLQueryGenerator(expression, self, 1234)
        select, args, usedtimerange = sql.generate()

        self.assertEqual(select.toSQL(), SQLFragment(
            "select distinct RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE from CALENDAR_OBJECT, TIME_RANGE where (ICALENDAR_TYPE = ? and (FLOATING = ? and END_DATE > ? or FLOATING = ? and END_DATE > ?) or ICALENDAR_TYPE = ?) and CALENDAR_OBJECT_RESOURCE_ID = RESOURCE_ID and TIME_RANGE.CALENDAR_RESOURCE_ID = ?",
            ['VEVENT', False, datetime.datetime(2006, 6, 5, 16, 0, tzinfo=tzutc()), True, datetime.datetime(2006, 6, 5, 12, 0, tzinfo=tzutc()), 'VTODO', 1234]
        ))
        self.assertEqual(args, {})
        self.assertEqual(usedtimerange, True)


    def test_sqllite_query(self):
        """
        Basic query test - single term.
        Only UID can be queried via sql.
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[caldavxml.ComponentFilter(
                    **{"name": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                )],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        sql, args = sqlcalendarquery(filter, 1234)

        self.assertTrue(sql.find("RESOURCE") != -1)
        self.assertTrue(sql.find("TIMESPAN") == -1)
        self.assertTrue(sql.find("PERUSER") == -1)
        self.assertTrue("VEVENT" in args)



class TestQueryFilterSerialize(TestCase):

    def setUp(self):
        super(TestQueryFilterSerialize, self).setUp()
        TimezoneCache.create()


    def test_query(self):
        """
        Basic query test - no time range
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[caldavxml.ComponentFilter(
                    **{"name": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                )],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))
        j = filter.serialize()
        self.assertEqual(j["type"], "Filter")

        f = FilterBase.deserialize(j)
        self.assertTrue(isinstance(f, Filter))


    def test_timerange_query(self):
        """
        Basic query test with time range
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[caldavxml.ComponentFilter(
                    *[caldavxml.TimeRange(**{"start": "20060605T160000Z", "end": "20060605T170000Z"})],
                    **{"name": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                )],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))
        j = filter.serialize()
        self.assertEqual(j["type"], "Filter")

        f = FilterBase.deserialize(j)
        self.assertTrue(isinstance(f, Filter))
        self.assertTrue(isinstance(f.child.filters[0].qualifier, TimeRange))
        self.assertTrue(isinstance(f.child.filters[0].qualifier.tzinfo, Timezone))
        self.assertEqual(f.child.filters[0].qualifier.tzinfo.getTimezoneID(), "America/New_York")


    def test_query_not_extended(self):
        """
        Basic query test with time range
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[
                    caldavxml.ComponentFilter(
                        **{"name": ("VEVENT")}
                    ),
                    caldavxml.ComponentFilter(
                        **{"name": ("VTODO")}
                    ),
                ],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))
        j = filter.serialize()
        self.assertEqual(j["type"], "Filter")

        f = FilterBase.deserialize(j)
        self.assertTrue(isinstance(f, Filter))
        self.assertEqual(len(f.child.filters), 2)


    def test_query_extended(self):
        """
        Basic query test with time range
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[
                    caldavxml.ComponentFilter(
                        *[caldavxml.TimeRange(**{"start": "20060605T160000Z", })],
                        **{"name": ("VEVENT")}
                    ),
                    caldavxml.ComponentFilter(
                        **{"name": ("VTODO")}
                    ),
                ],
                **{"name": "VCALENDAR", "test": "anyof"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))
        j = filter.serialize()
        self.assertEqual(j["type"], "Filter")

        f = FilterBase.deserialize(j)
        self.assertTrue(isinstance(f, Filter))
        self.assertEqual(len(f.child.filters), 2)
        self.assertTrue(isinstance(f.child.filters[0].qualifier, TimeRange))


    def test_query_text(self):
        """
        Basic query test with time range
        """

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[
                    caldavxml.ComponentFilter(
                        caldavxml.PropertyFilter(
                            caldavxml.TextMatch.fromString("1234", False),
                            name="UID",
                        ),
                        **{"name": ("VEVENT")}
                    ),
                ],
                **{"name": "VCALENDAR", "test": "anyof"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))
        j = filter.serialize()
        self.assertEqual(j["type"], "Filter")

        f = FilterBase.deserialize(j)
        self.assertTrue(isinstance(f, Filter))
        self.assertTrue(isinstance(f.child.filters[0].filters[0], PropertyFilter))
        self.assertTrue(isinstance(f.child.filters[0].filters[0].qualifier, TextMatch))
        self.assertEqual(f.child.filters[0].filters[0].qualifier.text, "1234")



class TestQueryFilterMatch(TestCase):

    def setUp(self):
        super(TestQueryFilterMatch, self).setUp()
        TimezoneCache.create()


    def test_vlarm_undefined(self):

        filter = caldavxml.Filter(
            caldavxml.ComponentFilter(
                *[caldavxml.ComponentFilter(
                    *[caldavxml.ComponentFilter(
                        caldavxml.IsNotDefined(),
                        **{"name": "VALARM"}
                    )],
                    **{"name": "VEVENT"}
                )],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        filter.child.settzinfo(Timezone(tzid="America/New_York"))

        self.assertFalse(filter.match(
            Component.fromString("""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VTIMEZONE
LAST-MODIFIED:20040110T032845Z
TZID:US/Eastern
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20051222T210412Z
CREATED:20060102T150000Z
DTSTART;TZID=US/Eastern:20130102T100000
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=5
SUMMARY:event 5
UID:945113826375CBB89184DC36@ninevah.local
CATEGORIES:cool,hot
CATEGORIES:warm
BEGIN:VALARM
ACTION:AUDIO
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""")))
