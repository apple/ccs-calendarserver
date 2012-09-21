##
# Copyright (c) 2009-2012 Apple Inc. All rights reserved.
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
from twistedcaldav.datafilters.calendardata import CalendarDataFilter
from twistedcaldav.caldavxml import CalendarData, CalendarComponent,\
    AllComponents, AllProperties, Property
from twistedcaldav.ical import Component

class CalendarDataTest (twistedcaldav.test.util.TestCase):

    def test_empty(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        empty = CalendarData()
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(empty).filter(item)), data)

    def test_vcalendar_no_effect(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        no_effect = CalendarData(
            CalendarComponent(
                name="VCALENDAR"
            )
        )
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(no_effect).filter(item)), data)
 
        no_effect = CalendarData(
            CalendarComponent(
                AllComponents(),
                AllProperties(),
                name="VCALENDAR"
            )
        )
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(no_effect).filter(item)), data)

    def test_vcalendar_no_props(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
X-WR-CALNAME:Help
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        result = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        empty = CalendarData(
            CalendarComponent(
                AllComponents(),
                name="VCALENDAR"
            )
        )
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(empty).filter(item)), result)

    def test_vcalendar_no_comp(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
X-WR-CALNAME:Help
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        result = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
X-WR-CALNAME:Help
END:VCALENDAR
""".replace("\n", "\r\n")
        
        empty = CalendarData(
            CalendarComponent(
                AllProperties(),
                name="VCALENDAR"
            )
        )
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(empty).filter(item)), result)

    def test_vevent_no_effect(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        no_effect = CalendarData(
            CalendarComponent(
                CalendarComponent(
                    name="VEVENT"
                ),
                AllProperties(),
                name="VCALENDAR"
            )
        )
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(no_effect).filter(item)), data)

    def test_vevent_other_component(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        result = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
END:VCALENDAR
""".replace("\n", "\r\n")
        
        other_component = CalendarData(
            CalendarComponent(
                CalendarComponent(
                    name="VTODO"
                ),
                AllProperties(),
                name="VCALENDAR"
            )
        )
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(other_component).filter(item)), result)

    def test_vevent_no_props(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        result = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        empty = CalendarData(
            CalendarComponent(
                CalendarComponent(
                    AllComponents(),
                    name="VEVENT"
                ),
                AllProperties(),
                name="VCALENDAR"
            )
        )
        
        for item in (data, Component.fromString(data),):
            filtered = str(CalendarDataFilter(empty).filter(item))
            filtered = "".join([line for line in filtered.splitlines(True) if not line.startswith("UID:")])
            self.assertEqual(filtered, result)

    def test_vevent_no_comp(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        result = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        empty = CalendarData(
            CalendarComponent(
                CalendarComponent(
                    AllProperties(),
                    name="VEVENT"
                ),
                AllProperties(),
                name="VCALENDAR"
            )
        )
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(empty).filter(item)), result)

    def test_vevent_some_props(self):
        
        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ORGANIZER;CN=User 01:mailto:user1@example.com
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        result = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:Test
TRIGGER;RELATED=START:-PT10M
END:VALARM
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        
        empty = CalendarData(
            CalendarComponent(
                CalendarComponent(
                    AllComponents(),
                    Property(
                        name="UID",
                    ),
                    Property(
                        name="DTSTART",
                    ),
                    Property(
                        name="DTEND",
                    ),
                    name="VEVENT"
                ),
                AllProperties(),
                name="VCALENDAR"
            )
        )
        
        for item in (data, Component.fromString(data),):
            self.assertEqual(str(CalendarDataFilter(empty).filter(item)), result)

