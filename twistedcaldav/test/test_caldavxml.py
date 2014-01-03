##
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
##

import twistedcaldav.test.util
from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import CalendarData
from twistedcaldav.ical import normalize_iCalStr, Component

def normalizeJSON(j):
    return "".join(map(str.strip, j.splitlines())).replace(", ", ",").replace(": ", ":")



class CustomXML (twistedcaldav.test.util.TestCase):


    def test_TimeRange(self):

        self.assertRaises(ValueError, caldavxml.CalDAVTimeRangeElement)

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000Z")
        self.assertTrue(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(end="20110201T120000Z")
        self.assertTrue(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(end="20110201T120000")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(end="20110201")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000Z", end="20110202T120000Z")
        self.assertTrue(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000Z", end="20110202T120000")
        self.assertFalse(tr.valid())

        tr = caldavxml.CalDAVTimeRangeElement(start="20110201T120000Z", end="20110202")
        self.assertFalse(tr.valid())


    def test_CalendarDataTextAndJSON(self):
        """
        Text that we can both parse and generate CalendarData elements with both text and json formats.
        """
        dataText = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
DTSTAMP:20080601T120000Z
EXDATE:20080602T120000Z
EXDATE:20080603T120000Z
ORGANIZER;CN=User 01:mailto:user1@example.com
RRULE:FREQ=DAILY;COUNT=400
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

        dataXML = """<?xml version='1.0' encoding='UTF-8'?>
<calendar-data xmlns='urn:ietf:params:xml:ns:caldav'><![CDATA[%s]]></calendar-data>""" % (dataText,)

        jsonText = """[
  "vcalendar",
  [
    ["version", {}, "text", "2.0"],
    ["prodid", {}, "text", "-//CALENDARSERVER.ORG//NONSGML Version 1//EN"]
  ],
  [
    ["vevent",
      [
        ["uid", {}, "text", "12345-67890"],
        ["dtstart", {}, "date-time", "2008-06-01T12:00:00Z"],
        ["dtend", {}, "date-time", "2008-06-01T13:00:00Z"],
        ["attendee", {}, "cal-address", "mailto:user1@example.com"],
        ["attendee", {}, "cal-address", "mailto:user2@example.com"],
        ["dtstamp", {}, "date-time", "2008-06-01T12:00:00Z"],
        ["exdate", {}, "date-time", "2008-06-02T12:00:00Z"],
        ["exdate", {}, "date-time", "2008-06-03T12:00:00Z"],
        ["organizer", {"cn": "User 01"}, "cal-address", "mailto:user1@example.com"],
        ["rrule", {}, "recur", {"count": 400, "freq": "DAILY"}],
        ["summary", {}, "text", "Test"]
      ],
      [
      ]
    ]
  ]
]
"""

        jsonXML = """<?xml version='1.0' encoding='UTF-8'?>
<calendar-data content-type='application/calendar+json' xmlns='urn:ietf:params:xml:ns:caldav'><![CDATA[%s]]></calendar-data>""" % (jsonText,)

        cd = CalendarData.fromTextData(dataText)
        self.assertEqual(normalize_iCalStr(cd.calendar().getTextWithTimezones(True, format="text/calendar")), normalize_iCalStr(dataText))
        self.assertEqual(normalizeJSON(cd.calendar().getTextWithTimezones(True, format="application/calendar+json")), normalizeJSON(jsonText))
        self.assertEqual(cd.content_type, "text/calendar")
        self.assertEqual(cd.toxml(), dataXML)

        comp = Component.fromString(dataText)
        cd = CalendarData.fromCalendar(comp)
        self.assertEqual(normalize_iCalStr(cd.calendar().getTextWithTimezones(True, format="text/calendar")), normalize_iCalStr(dataText))
        self.assertEqual(normalizeJSON(cd.calendar().getTextWithTimezones(True, format="application/calendar+json")), normalizeJSON(jsonText))
        self.assertEqual(cd.content_type, "text/calendar")
        self.assertEqual(cd.toxml(), dataXML)

        cd = CalendarData.fromCalendar(comp, format="application/calendar+json")
        self.assertEqual(normalize_iCalStr(cd.calendar().getTextWithTimezones(True, format="text/calendar")), normalize_iCalStr(dataText))
        self.assertEqual(normalizeJSON(cd.calendar().getTextWithTimezones(True, format="application/calendar+json")), normalizeJSON(jsonText))
        self.assertEqual(cd.content_type, "application/calendar+json")
        self.assertEqual(normalizeJSON(cd.toxml()), normalizeJSON(jsonXML))

        cd = CalendarData.fromTextData(jsonText, format="application/calendar+json")
        self.assertEqual(normalize_iCalStr(cd.calendar().getTextWithTimezones(True, format="text/calendar")), normalize_iCalStr(dataText))
        self.assertEqual(normalizeJSON(cd.calendar().getTextWithTimezones(True, format="application/calendar+json")), normalizeJSON(jsonText))
        self.assertEqual(cd.content_type, "application/calendar+json")
        self.assertEqual(cd.toxml(), jsonXML)

        comp = Component.fromString(jsonText, format="application/calendar+json")
        cd = CalendarData.fromCalendar(comp)
        self.assertEqual(normalize_iCalStr(cd.calendar().getTextWithTimezones(True, format="text/calendar")), normalize_iCalStr(dataText))
        self.assertEqual(normalizeJSON(cd.calendar().getTextWithTimezones(True, format="application/calendar+json")), normalizeJSON(jsonText))
        self.assertEqual(cd.content_type, "text/calendar")
        self.assertEqual(cd.toxml(), dataXML)

        cd = CalendarData.fromCalendar(comp, format="application/calendar+json")
        self.assertEqual(normalize_iCalStr(cd.calendar().getTextWithTimezones(True, format="text/calendar")), normalize_iCalStr(dataText))
        self.assertEqual(normalizeJSON(cd.calendar().getTextWithTimezones(True, format="application/calendar+json")), normalizeJSON(jsonText))
        self.assertEqual(cd.content_type, "application/calendar+json")
        self.assertEqual(normalizeJSON(cd.toxml()), normalizeJSON(jsonXML))
