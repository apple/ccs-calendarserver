##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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

from pycalendar.timezone import Timezone

from twext.enterprise.dal.syntax import SQLFragment, Parameter

from twistedcaldav.test.util import TestCase
from twistedcaldav import caldavxml
from twistedcaldav.timezones import TimezoneCache

from txdav.caldav.datastore.index_file import sqlcalendarquery
from txdav.caldav.datastore.query.builder import buildExpression
from txdav.caldav.datastore.query.filter import Filter
from txdav.caldav.datastore.query.generator import CalDAVSQLQueryGenerator
from txdav.common.datastore.sql_tables import schema

from dateutil.tz import tzutc
import datetime

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
                    **{"name":("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
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
                    *[caldavxml.TimeRange(**{"start":"20060605T160000Z", "end":"20060605T170000Z"})],
                    **{"name":("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
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
                    *[caldavxml.TimeRange(**{"start":"20060605T160000Z", "end":"20060605T170000Z"})],
                    **{"name":("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
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
            "select distinct RESOURCE_NAME, ICALENDAR_UID, ICALENDAR_TYPE, ORGANIZER, FLOATING, START_DATE, END_DATE, FBTYPE, TIME_RANGE.TRANSPARENT, TRANSPARENCY.TRANSPARENT from CALENDAR_OBJECT, TIME_RANGE left outer join TRANSPARENCY on INSTANCE_ID = TIME_RANGE_INSTANCE_ID and USER_ID = ? where ICALENDAR_TYPE in (?, ?, ?) and (FLOATING = ? and START_DATE < ? and END_DATE > ? or FLOATING = ? and START_DATE < ? and END_DATE > ?) and CALENDAR_OBJECT_RESOURCE_ID = RESOURCE_ID and TIME_RANGE.CALENDAR_RESOURCE_ID = ?",
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
                        **{"name":("VEVENT")}
                    ),
                    caldavxml.ComponentFilter(
                        **{"name":("VTODO")}
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
                        *[caldavxml.TimeRange(**{"start":"20060605T160000Z", })],
                        **{"name":("VEVENT")}
                    ),
                    caldavxml.ComponentFilter(
                        **{"name":("VTODO")}
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
                    **{"name":("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                )],
                **{"name": "VCALENDAR"}
            )
        )
        filter = Filter(filter)
        sql, args = sqlcalendarquery(filter, 1234)

        self.assertTrue(sql.find("RESOURCE") != -1)
        self.assertTrue(sql.find("TIMESPAN") == -1)
        self.assertTrue(sql.find("TRANSPARENCY") == -1)
        self.assertTrue("VEVENT" in args)
