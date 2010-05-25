##
# Copyright (c) 2009-2010 Apple Inc. All rights reserved.
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

class Tests(twistedcaldav.test.util.TestCase):

    def test_allQuery(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                **{"name":"VCALENDAR"}
            )
        )

        calendarqueryfilter.Filter(xml_element)
        
    def test_simpleSummaryRangeQuery(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                caldavxml.ComponentFilter(
                    caldavxml.PropertyFilter(
                        caldavxml.TextMatch.fromString("test"),
                        **{"name":"SUMMARY",}
                    ),
                    **{"name":"VEVENT"}
                ),
                **{"name":"VCALENDAR"}
            )
        )

        calendarqueryfilter.Filter(xml_element)
        
    def test_simpleTimeRangeQuery(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                caldavxml.ComponentFilter(
                    caldavxml.TimeRange(**{"start":"20060605T160000Z", "end":"20060605T170000Z"}),
                    **{"name":"VEVENT"}
                ),
                **{"name":"VCALENDAR"}
            )
        )

        calendarqueryfilter.Filter(xml_element)
        
    def test_multipleTimeRangeQuery(self):

        xml_element = caldavxml.Filter(
            caldavxml.ComponentFilter(
                caldavxml.ComponentFilter(
                    caldavxml.TimeRange(**{"start":"20060605T160000Z", "end":"20060605T170000Z"}),
                    **{"name":("VEVENT", "VFREEBUSY", "VAVAILABILITY")}
                ),
                **{"name":"VCALENDAR"}
            )
        )

        calendarqueryfilter.Filter(xml_element)
        