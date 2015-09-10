##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
##
"""
A list of predefined component templates for use in the client sim
"""

from twistedcaldav.ical import Component


# Default Event
eventTemplate = Component.fromString("""
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//Mac OS X 10.11//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
TRANSP:OPAQUE
SUMMARY:Sample Event
UID:00000000-0000-0000-0000-000000000000
CREATED:00000000T000000Z
DTSTAMP:00000000T000000Z
DTSTART:00000000T000000
DTEND:00000000T000000
END:VEVENT
END:VCALENDAR
""")


# Default Task
taskTemplate = Component.fromString("""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//Mac OS X 10.11//EN
CALSCALE:GREGORIAN
BEGIN:VTODO
SUMMARY:Sample Task
UID:00000000-0000-0000-0000-000000000000
CREATED:00000000T000000Z
DTSTAMP:00000000T000000Z
END:VTODO
END:VCALENDAR
""")


# Default Alarm
alarmTemplate = Component.fromString("""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//Mac OS X 10.11//EN
CALSCALE:GREGORIAN
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT5M
UID:00000000-0000-0000-0000-000000000000
DESCRIPTION:Sample Alarm
END:VALARM
END:VCALENDAR
""")
