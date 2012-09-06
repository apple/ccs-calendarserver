##
# Copyright (c) 2008-2012 Apple Inc. All rights reserved.
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

from __future__ import with_statement

from twistedcaldav.localization import translationTo, _
from twistedcaldav.ical import Component
from twistedcaldav.test.util import TestCase
from pycalendar.datetime import PyCalendarDateTime

import os

def getComp(str):
    calendar = Component.fromString(str)
    comp = calendar.masterComponent()
    if comp is None:
        comp = calendar.mainComponent(True)
    return comp

data = (
    ('1-hour-long-morning', getComp('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nCALSCALE:GREGORIAN\r\nMETHOD:REQUEST\r\nPRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN\r\nBEGIN:VTIMEZONE\r\nTZID:US/Pacific\r\nBEGIN:STANDARD\r\nDTSTART:20071104T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nTZNAME:PST\r\nTZOFFSETFROM:-0700\r\nTZOFFSETTO:-0800\r\nEND:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:20070311T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nTZNAME:PDT\r\nTZOFFSETFROM:-0800\r\nTZOFFSETTO:-0700\r\nEND:DAYLIGHT\r\nEND:VTIMEZONE\r\nBEGIN:VEVENT\r\nUID:C7C037CC-1485-461B-8866-777C662C5930\r\nDTSTART;TZID=US/Pacific:20081025T091500\r\nDTEND;TZID=US/Pacific:20081025T101501\r\nATTENDEE;CN=test@systemcall.com;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;RSV\r\n P=TRUE:mailto:test@systemcall.com\r\nATTENDEE;CN=Test User;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:testuser@\r\n example.com\r\nCREATED:20081024T181749Z\r\nDTSTAMP:20081024T183142Z\r\nORGANIZER;CN=Test User:mailto:testuser@example.com\r\nSEQUENCE:5\r\nSUMMARY:testing\r\nTRANSP:OPAQUE\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')),

    ('2-hour-long-evening', getComp('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nCALSCALE:GREGORIAN\r\nMETHOD:REQUEST\r\nPRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN\r\nBEGIN:VTIMEZONE\r\nTZID:US/Pacific\r\nBEGIN:STANDARD\r\nDTSTART:20071104T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nTZNAME:PST\r\nTZOFFSETFROM:-0700\r\nTZOFFSETTO:-0800\r\nEND:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:20070311T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nTZNAME:PDT\r\nTZOFFSETFROM:-0800\r\nTZOFFSETTO:-0700\r\nEND:DAYLIGHT\r\nEND:VTIMEZONE\r\nBEGIN:VEVENT\r\nUID:C7C037CC-1485-461B-8866-777C662C5930\r\nDTSTART;TZID=US/Pacific:20081025T131500\r\nDTEND;TZID=US/Pacific:20081025T151502\r\nATTENDEE;CN=test@systemcall.com;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;RSV\r\n P=TRUE:mailto:test@systemcall.com\r\nATTENDEE;CN=Test User;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:testuser@\r\n example.com\r\nCREATED:20081024T181749Z\r\nDTSTAMP:20081024T183142Z\r\nORGANIZER;CN=Test User:mailto:testuser@example.com\r\nSEQUENCE:5\r\nSUMMARY:testing\r\nTRANSP:OPAQUE\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')),

    ('3-hour-long-cross-noon', getComp('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nCALSCALE:GREGORIAN\r\nMETHOD:REQUEST\r\nPRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN\r\nBEGIN:VTIMEZONE\r\nTZID:US/Pacific\r\nBEGIN:STANDARD\r\nDTSTART:20071104T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nTZNAME:PST\r\nTZOFFSETFROM:-0700\r\nTZOFFSETTO:-0800\r\nEND:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:20070311T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nTZNAME:PDT\r\nTZOFFSETFROM:-0800\r\nTZOFFSETTO:-0700\r\nEND:DAYLIGHT\r\nEND:VTIMEZONE\r\nBEGIN:VEVENT\r\nUID:C7C037CC-1485-461B-8866-777C662C5930\r\nDTSTART;TZID=US/Pacific:20081025T110500\r\nDTEND;TZID=US/Pacific:20081025T141500\r\nATTENDEE;CN=test@systemcall.com;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;RSV\r\n P=TRUE:mailto:test@systemcall.com\r\nATTENDEE;CN=Test User;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:testuser@\r\n example.com\r\nCREATED:20081024T181749Z\r\nDTSTAMP:20081024T183142Z\r\nORGANIZER;CN=Test User:mailto:testuser@example.com\r\nSEQUENCE:5\r\nSUMMARY:testing\r\nTRANSP:OPAQUE\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')),

    ('all-day', getComp('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nCALSCALE:GREGORIAN\r\nMETHOD:REQUEST\r\nPRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN\r\nBEGIN:VTIMEZONE\r\nTZID:US/Pacific\r\nBEGIN:STANDARD\r\nDTSTART:20071104T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nTZNAME:PST\r\nTZOFFSETFROM:-0700\r\nTZOFFSETTO:-0800\r\nEND:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:20070311T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nTZNAME:PDT\r\nTZOFFSETFROM:-0800\r\nTZOFFSETTO:-0700\r\nEND:DAYLIGHT\r\nEND:VTIMEZONE\r\nBEGIN:VEVENT\r\nUID:C7C037CC-1485-461B-8866-777C662C5930\r\nDTSTART;TZID=US/Pacific:20081025\r\nATTENDEE;CN=test@systemcall.com;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;RSV\r\n P=TRUE:mailto:test@systemcall.com\r\nATTENDEE;CN=Test User;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:testuser@\r\n example.com\r\nCREATED:20081024T181749Z\r\nDTSTAMP:20081024T183142Z\r\nORGANIZER;CN=Test User:mailto:testuser@example.com\r\nSEQUENCE:5\r\nSUMMARY:testing\r\nTRANSP:OPAQUE\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')),

    ('instantaneous', getComp('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nCALSCALE:GREGORIAN\r\nMETHOD:REQUEST\r\nPRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN\r\nBEGIN:VTIMEZONE\r\nTZID:US/Pacific\r\nBEGIN:STANDARD\r\nDTSTART:20071104T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nTZNAME:PST\r\nTZOFFSETFROM:-0700\r\nTZOFFSETTO:-0800\r\nEND:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:20070311T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nTZNAME:PDT\r\nTZOFFSETFROM:-0800\r\nTZOFFSETTO:-0700\r\nEND:DAYLIGHT\r\nEND:VTIMEZONE\r\nBEGIN:VEVENT\r\nUID:C7C037CC-1485-461B-8866-777C662C5930\r\nDTSTART;TZID=US/Pacific:20081025T131500\r\nDTEND;TZID=US/Pacific:20081025T131500\r\nATTENDEE;CN=test@systemcall.com;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;RSV\r\n P=TRUE:mailto:test@systemcall.com\r\nATTENDEE;CN=Test User;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:testuser@\r\n example.com\r\nCREATED:20081024T181749Z\r\nDTSTAMP:20081024T183142Z\r\nORGANIZER;CN=Test User:mailto:testuser@example.com\r\nSEQUENCE:5\r\nSUMMARY:testing\r\nTRANSP:OPAQUE\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')),

    ('cross-timezone', getComp('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nCALSCALE:GREGORIAN\r\nMETHOD:REQUEST\r\nPRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN\r\nBEGIN:VTIMEZONE\r\nTZID:US/Pacific\r\nBEGIN:STANDARD\r\nDTSTART:20071104T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nTZNAME:PST\r\nTZOFFSETFROM:-0700\r\nTZOFFSETTO:-0800\r\nEND:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:20070311T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nTZNAME:PDT\r\nTZOFFSETFROM:-0800\r\nTZOFFSETTO:-0700\r\nEND:DAYLIGHT\r\nEND:VTIMEZONE\r\nBEGIN:VTIMEZONE\r\nTZID:US/Eastern\r\nBEGIN:STANDARD\r\nDTSTART:20071104T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nTZNAME:EST\r\nTZOFFSETFROM:-0400\r\nTZOFFSETTO:-0500\r\nEND:STANDARD\r\nBEGIN:DAYLIGHT\r\nDTSTART:20070311T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nTZNAME:EDT\r\nTZOFFSETFROM:-0500\r\nTZOFFSETTO:-0400\r\nEND:DAYLIGHT\r\nEND:VTIMEZONE\r\nBEGIN:VEVENT\r\nUID:C7C037CC-1485-461B-8866-777C662C5930\r\nDTSTART;TZID=US/Pacific:20081025T110500\r\nDTEND;TZID=US/Eastern:20081025T181500\r\nATTENDEE;CN=test@systemcall.com;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;RSV\r\n P=TRUE:mailto:test@systemcall.com\r\nATTENDEE;CN=Test User;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:testuser@\r\n example.com\r\nCREATED:20081024T181749Z\r\nDTSTAMP:20081024T183142Z\r\nORGANIZER;CN=Test User:mailto:testuser@example.com\r\nSEQUENCE:5\r\nSUMMARY:testing\r\nTRANSP:OPAQUE\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')),


)

localeDir = os.path.join(os.path.dirname(__file__), "data", "locales")

class LocalizationTests(TestCase):

    def test_BasicStringLocalization(self):

        with translationTo('pig', localeDir=localeDir):

            self.assertEquals(_("All day"), "Allway ayday")

            self.assertEquals(_("%(startTime)s to %(endTime)s") %
                { 'startTime' : 'a', 'endTime' : 'b' },
                "a otay b"
            )

    def test_TimeFormattingAMPM(self):

        with translationTo('English', localeDir=localeDir) as t:

            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1,  0,  0, 0)), "12:00 AM")
            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1, 12,  0, 0)), "12:00 PM")
            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1, 23, 59, 0)), "11:59 PM")
            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1,  6,  5, 0)), "6:05 AM")
            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1, 16,  5, 0)), "4:05 PM")

    def test_TimeFormatting24Hour(self):

        with translationTo('pig', localeDir=localeDir) as t:

            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1,  0,  0, 0)), "00:00")
            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1, 12,  0, 0)), "12:00")
            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1, 23, 59, 0)), "23:59")
            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1,  6,  5, 0)), "06:05")
            self.assertEquals(t.dtTime(PyCalendarDateTime(2000, 1, 1, 16,  5, 0)), "16:05")

    def test_CalendarFormatting(self):

        with translationTo('English', localeDir=localeDir) as t:

            comp = data[0][1]
            self.assertEquals(t.date(comp), "Saturday, October 25, 2008")
            self.assertEquals(t.time(comp),
                (u'9:15 AM to 10:15 AM (PDT)', u'1 hour 1 second'))

            comp = data[1][1]
            self.assertEquals(t.time(comp),
                (u'1:15 PM to 3:15 PM (PDT)', u'2 hours 2 seconds'))

            comp = data[2][1]
            self.assertEquals(t.time(comp),
                (u'11:05 AM to 2:15 PM (PDT)', u'3 hours 10 minutes'))

            comp = data[3][1]
            self.assertEquals(t.time(comp),
                ("", u'All day'))

            comp = data[4][1]
            self.assertEquals(t.time(comp),
                (u'1:15 PM (PDT)', ""))

            comp = data[5][1]
            self.assertEquals(t.time(comp),
                (u'11:05 AM (PDT) to 6:15 PM (EDT)', u'4 hours 10 minutes'))

            self.assertEquals(t.monthAbbreviation(1), "JAN")

        with translationTo('pig', localeDir=localeDir) as t:

            comp = data[0][1]
            self.assertEquals(t.date(comp), 'Aturdaysay, Octoberway 25, 2008')
            self.assertEquals(t.time(comp),
                (u'09:15 otay 10:15 (PDT)', u'1 ourhay 1 econdsay'))

            comp = data[1][1]
            self.assertEquals(t.time(comp),
                (u'13:15 otay 15:15 (PDT)', u'2 ourshay 2 econdsay'))

            comp = data[2][1]
            self.assertEquals(t.time(comp),
                (u'11:05 otay 14:15 (PDT)', u'3 ourshay 10 inutesmay'))

            comp = data[3][1]
            self.assertEquals(t.time(comp),
                ("", u'Allway ayday'))

            comp = data[4][1]
            self.assertEquals(t.time(comp),
                (u'13:15 (PDT)', ""))

            comp = data[5][1]
            self.assertEquals(t.time(comp),
                (u'11:05 (PDT) otay 18:15 (EDT)', u'4 ourshay 10 inutesmay'))

            self.assertEquals(t.monthAbbreviation(1), "ANJAY")
