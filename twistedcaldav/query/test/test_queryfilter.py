##
# Copyright (c) 2009-2013 Apple Inc. All rights reserved.
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
from twistedcaldav.caldavxml import TimeZone
from pycalendar.timezone import PyCalendarTimezone

class Tests(twistedcaldav.test.util.TestCase):

    def test_allQuery(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                **{"name": "VCALENDAR"}
            )
        )

        calendarqueryfilter.Filter(xml_element)


    def test_simpleSummaryRangeQuery(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                caldavxml.ComponentFilter(
                    caldavxml.PropertyFilter(
                        caldavxml.TextMatch.fromString("test"),
                        **{"name": "SUMMARY", }
                    ),
                    **{"name": "VEVENT"}
                ),
                **{"name": "VCALENDAR"}
            )
        )

        calendarqueryfilter.Filter(xml_element)


    def test_simpleTimeRangeQuery(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                caldavxml.ComponentFilter(
                    caldavxml.TimeRange(**{"start": "20060605T160000Z", "end": "20060605T170000Z"}),
                    **{"name": "VEVENT"}
                ),
                **{"name": "VCALENDAR"}
            )
        )

        calendarqueryfilter.Filter(xml_element)


    def test_multipleTimeRangeQuery(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                caldavxml.ComponentFilter(
                    caldavxml.TimeRange(**{"start": "20060605T160000Z", "end": "20060605T170000Z"}),
                    **{"name": ("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                ),
                **{"name": "VCALENDAR"}
            )
        )

        calendarqueryfilter.Filter(xml_element)


    def test_queryWithTimezone(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                caldavxml.ComponentFilter(
                    caldavxml.TimeRange(**{"start": "20060605T160000Z", "end": "20060605T170000Z"}),
                    **{"name": "VEVENT"}
                ),
                **{"name": "VCALENDAR"}
            )
        )

        filter = calendarqueryfilter.Filter(xml_element)
        tz = filter.settimezone(TimeZone.fromString("""BEGIN:VCALENDAR
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
VERSION:2.0
BEGIN:VTIMEZONE
TZID:America/New_York
X-LIC-LOCATION:America/New_York
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19180331T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU;UNTIL=19200328T070000Z
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19181027T020000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU;UNTIL=19201031T060000Z
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19210424T020000
RRULE:FREQ=YEARLY;BYMONTH=4;BYDAY=-1SU;UNTIL=19410427T070000Z
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19210925T020000
RRULE:FREQ=YEARLY;BYMONTH=9;BYDAY=-1SU;UNTIL=19410928T060000Z
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19460428T020000
RRULE:FREQ=YEARLY;BYMONTH=4;BYDAY=-1SU;UNTIL=19730429T070000Z
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19460929T020000
RRULE:FREQ=YEARLY;BYMONTH=9;BYDAY=-1SU;UNTIL=19540926T060000Z
END:STANDARD
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19551030T020000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU;UNTIL=20061029T060000Z
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19760425T020000
RRULE:FREQ=YEARLY;BYMONTH=4;BYDAY=-1SU;UNTIL=19860427T070000Z
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19870405T020000
RRULE:FREQ=YEARLY;BYMONTH=4;BYDAY=1SU;UNTIL=20060402T070000Z
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
BEGIN:STANDARD
TZOFFSETFROM:-045602
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:18831118T120358
RDATE:18831118T120358
END:STANDARD
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19200101T000000
RDATE:19200101T000000
RDATE:19420101T000000
RDATE:19460101T000000
RDATE:19670101T000000
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EWT
DTSTART:19420209T020000
RDATE:19420209T020000
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0400
TZOFFSETTO:-0400
TZNAME:EPT
DTSTART:19450814T190000
RDATE:19450814T190000
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19450930T020000
RDATE:19450930T020000
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19740106T020000
RDATE:19740106T020000
RDATE:19750223T020000
END:DAYLIGHT
END:VTIMEZONE
END:VCALENDAR
"""))

        self.assertTrue(isinstance(tz, PyCalendarTimezone))
