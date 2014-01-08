##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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

from twistedcaldav import caldavxml
from twistedcaldav.query import calendarqueryfilter
import twistedcaldav.test.util
from pycalendar.timezone import PyCalendarTimezone
from twistedcaldav.query.calendarquery import sqlcalendarquery

class Tests(twistedcaldav.test.util.TestCase):

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
        filter = calendarqueryfilter.Filter(filter)
        filter.child.settzinfo(PyCalendarTimezone(tzid="America/New_York"))

        sql, args = sqlcalendarquery(filter)
        self.assertTrue(sql.find("RESOURCE") != -1)
        self.assertTrue(sql.find("TIMESPAN") == -1)
        self.assertTrue(sql.find("TRANSPARENCY") == -1)
        self.assertTrue("VEVENT" in args)


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
        filter = calendarqueryfilter.Filter(filter)
        filter.child.settzinfo(PyCalendarTimezone(tzid="America/New_York"))

        sql, args = sqlcalendarquery(filter)
        self.assertTrue(sql.find("RESOURCE") != -1)
        self.assertTrue(sql.find("TIMESPAN") != -1)
        self.assertTrue(sql.find("TRANSPARENCY") == -1)
        self.assertTrue("VEVENT" in args)


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
        filter = calendarqueryfilter.Filter(filter)
        filter.child.settzinfo(PyCalendarTimezone(tzid="America/New_York"))

        sql, args = sqlcalendarquery(filter)
        self.assertTrue(sql.find("RESOURCE") != -1)
        self.assertTrue(sql.find("TIMESPAN") == -1)
        self.assertTrue(sql.find("TRANSPARENCY") == -1)
        self.assertTrue(sql.find(" OR ") == -1)
        self.assertTrue("VEVENT" in args)
        self.assertTrue("VTODO" in args)


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
        filter = calendarqueryfilter.Filter(filter)
        filter.child.settzinfo(PyCalendarTimezone(tzid="America/New_York"))

        sql, args = sqlcalendarquery(filter)
        self.assertTrue(sql.find("RESOURCE") != -1)
        self.assertTrue(sql.find("TIMESPAN") != -1)
        self.assertTrue(sql.find("TRANSPARENCY") == -1)
        self.assertTrue(sql.find(" OR ") != -1)
        self.assertTrue("VEVENT" in args)
        self.assertTrue("VTODO" in args)
