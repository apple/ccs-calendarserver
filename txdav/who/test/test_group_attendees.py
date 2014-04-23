##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

"""
    group attendee tests
"""

from twext.who.directory import DirectoryService
from twext.who.test.test_xml import xmlService
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial import unittest
from twistedcaldav.config import config
from twistedcaldav.ical import Component, normalize_iCalStr, ignoredComponents
from txdav.caldav.datastore.test.util import buildCalendarStore, populateCalendarsFrom, CommonCommonTests
from txdav.who.directory import CalendarDirectoryRecordMixin
from txdav.who.groups import GroupCacher
from txdav.who.util import directoryFromConfig
import os


class GroupAttendeeReconciliation(CommonCommonTests, unittest.TestCase):
    """
    GroupAttendeeReconciliation tests
    """

    @inlineCallbacks
    def setUp(self):
        self.patch(config.Scheduling.Options, "AllowGroupAsAttendee", "True")

        yield super(GroupAttendeeReconciliation, self).setUp()
        self.xmlService = xmlService(self.mktemp(), xmlData=None)

        self.patch(
            config.DirectoryService.params,
            "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "accounts", "groupAttendeeAccounts.xml"
            )
        )
        self.patch(
            config.ResourceService.params,
            "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "accounts", "resources.xml"
            )
        )
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory, directoryFromConfig(config))
        yield self.populate()

        self.paths = {}


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()

    requirements = {
        "10000000-0000-0000-0000-000000000001" : None,
        "10000000-0000-0000-0000-000000000002" : None,
        "10000000-0000-0000-0000-000000000006" : None,
        "10000000-0000-0000-0000-000000000007" : None,
        "10000000-0000-0000-0000-000000000008" : None,
        "10000000-0000-0000-0000-000000000009" : None,
        "10000000-0000-0000-0000-000000000010" : None,

    }

    @inlineCallbacks
    def _verifyObjectResourceCount(self, home, expected_count):
        cal6 = yield self.calendarUnderTest(name="calendar", home=home)
        count = yield cal6.countObjectResources()
        self.assertEqual(count, expected_count)


    def _assertICalStrEqual(self, iCalStr1, iCalStr2):

        def orderMemberValues(event):

            for component in event.subcomponents():
                if component.name() in ignoredComponents:
                    continue

                # remove all values and add them again
                # this is sort of a hack, better pycalendar has ordering
                for attendeeProp in tuple(component.properties("ATTENDEE")):
                    if attendeeProp.hasParameter("MEMBER"):
                        parameterValues = tuple(attendeeProp.parameterValues("MEMBER"))
                        for paramterValue in parameterValues:
                            attendeeProp.removeParameterValue("MEMBER", paramterValue)
                        attendeeProp.setParameter("MEMBER", sorted(parameterValues))

        self.assertEqual(
            orderMemberValues(
                Component.fromString(
                    normalize_iCalStr(
                        iCalStr1
                    )
                )
            ),
            orderMemberValues(
                Component.fromString(
                    normalize_iCalStr(
                        iCalStr2
                    )
                )
            )
        )


    @inlineCallbacks
    def test_simplePUT(self):
        """
        Test that group attendee is expanded on PUT
        """
        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:MAILTO:group02@example.com
END:VEVENT
END:VCALENDAR"""

        data_get_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=GROUP;EMAIL=group02@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=User 06;EMAIL=user06@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000006
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 0)

        vcalendar1 = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar1)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar2 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar2, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)


    @inlineCallbacks
    def test_unknownPUT(self):
        """
        Test unknown group with CUTYPE=GROUP handled
        """
        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;CUTYPE=GROUP:urn:uuid:FFFFFFFF-EEEE-DDDD-CCCC-BBBBBBBBBBBB
END:VEVENT
END:VCALENDAR"""

        data_get_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=GROUP;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:uuid:FFFFFFFF-EEEE-DDDD-CCCC-BBBBBBBBBBBB
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        vcalendar1 = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar1)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar2 = yield cobj1.component()
        self.assertEqual(normalize_iCalStr(vcalendar2), normalize_iCalStr(data_get_1))


    @inlineCallbacks
    def test_primaryAttendeeInGroupPUT(self):
        """
        Test that primary attendee also in group remains primary
        """
        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:MAILTO:group01@example.com
END:VEVENT
END:VCALENDAR"""

        data_get_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=GROUP;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""
        vcalendar1 = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar1)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar1 = yield cobj1.component()
        self.assertEqual(normalize_iCalStr(vcalendar1), normalize_iCalStr(data_get_1))


    @inlineCallbacks
    def test_nestedPUT(self):
        """
        Test that nested groups are expanded expanded on PUT
        """
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000010", 0)

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:urn:x-uid:20000000-0000-0000-0000-000000000004
END:VEVENT
END:VCALENDAR"""

        data_get_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 04;CUTYPE=GROUP;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000004
ATTENDEE;CN=User 06;EMAIL=user06@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000004";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000006
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000004";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000004";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
ATTENDEE;CN=User 09;EMAIL=user09@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000004";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000009
ATTENDEE;CN=User 10;EMAIL=user10@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000004";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000010
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        vcalendar1 = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar1)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar2 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar2, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000010", 1)


    @inlineCallbacks
    def test_multiGroupPUT(self):
        """
        Test that expanded users in two primary groups have groups in MEMBERS param
        """
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 0)

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:MAILTO:group01@example.com
ATTENDEE:MAILTO:group02@example.com
ATTENDEE:MAILTO:group03@example.com
END:VEVENT
END:VCALENDAR"""

        data_get_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 01;CUTYPE=GROUP;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=GROUP;EMAIL=group02@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=GROUP;EMAIL=group03@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000003
ATTENDEE;CN=User 06;EMAIL=user06@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000006
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
ATTENDEE;CN=User 09;EMAIL=user09@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000009
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR"""

        vcalendar1 = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar1)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar2 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar2, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)


    @inlineCallbacks
    def test_groupChange(self):
        """
        Test that group attendee changes are applied to existing resources.
        """
        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user02@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:MAILTO:group01@example.com
END:VEVENT
END:VCALENDAR"""

        data_get_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=GROUP;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        data_get_3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=GROUP;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 01;EMAIL=user01@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000001";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
SEQUENCE:1
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        data_get_4 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=GROUP;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
SEQUENCE:2
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        @inlineCallbacks
        def expandedMembers(self, records=None):
            yield None
            returnValue(set())

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        self.assertEqual(len(wps), 0)

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar1 = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar1)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar2 = yield cobj1.component()
        self.assertEqual(normalize_iCalStr(vcalendar2), normalize_iCalStr(data_get_2))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 0)
        yield self.commit()

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", unpatchedExpandedMembers)

        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield wps[0].whenExecuted()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar3 = yield cobj1.component()
        self.assertEqual(normalize_iCalStr(vcalendar3), normalize_iCalStr(data_get_3))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 1)
        yield self.commit()

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield wps[0].whenExecuted()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar3 = yield cobj1.component()
        self.assertEqual(normalize_iCalStr(vcalendar3), normalize_iCalStr(data_get_4))

        cal1 = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")
        cobjs = yield cal1.objectResources()
        self.assertEqual(len(cobjs), 1)
        comp1 = yield cobjs[0].componentForUser()
        self.assertTrue("STATUS:CANCELLED" in str(comp1))


    @inlineCallbacks
    def test_multieventGroupChange(self):
        """
        Test that every event associated with a group chagnes when the group changes
        """

        self.fail("FIXME: implement this test")


    @inlineCallbacks
    def test_groupRemovalFromDirectory(self):
        """
        Test that removing a group from the directory also removes the expanded attendees.
        This needs to make sure that an attendee in two groups is NOT removed if only one
        of those groups is removed
        """

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000010", 0)

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:MAILTO:group01@example.com
ATTENDEE:MAILTO:group02@example.com
ATTENDEE:MAILTO:group03@example.com
END:VEVENT
END:VCALENDAR"""

        data_get_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 01;CUTYPE=GROUP;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=GROUP;EMAIL=group02@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=GROUP;EMAIL=group03@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000003
ATTENDEE;CN=User 06;EMAIL=user06@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000006
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
ATTENDEE;CN=User 09;EMAIL=user09@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000009
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR"""

        data_get_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 01;CUTYPE=GROUP;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=GROUP;EMAIL=group02@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=GROUP;EMAIL=group03@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000003
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
ATTENDEE;CN=User 09;EMAIL=user09@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000009
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SEQUENCE:1
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        data_get_3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 01;CUTYPE=GROUP;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=GROUP;EMAIL=group02@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=GROUP;EMAIL=group03@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000003
ATTENDEE;CN=User 06;EMAIL=user06@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000006
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
ATTENDEE;CN=User 09;EMAIL=user09@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000009
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SEQUENCE:2
SUMMARY:event 1
END:VEVENT
END:VCALENDAR"""

        unpatchedRecordWithUID = DirectoryService.recordWithUID

        @inlineCallbacks
        def recordWithUID(self, uid):

            if uid == "20000000-0000-0000-0000-000000000002":
                result = None
            else:
                result = yield unpatchedRecordWithUID(self, uid)
            returnValue(result)

        vcalendar1 = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar1)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar2 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar2, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)

        # cache group
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield wps[0].whenExecuted()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar3 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar3, data_get_1)

        # remove group  run cacher again
        self.patch(DirectoryService, "recordWithUID", recordWithUID)

        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield wps[0].whenExecuted()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar4 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar4, data_get_2)

        cal1 = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000006")
        cobjs = yield cal1.objectResources()
        self.assertEqual(len(cobjs), 1)
        comp1 = yield cobjs[0].componentForUser()
        self.assertTrue("STATUS:CANCELLED" in str(comp1))
        yield self.commit()

        # add group back, run cacher
        self.patch(DirectoryService, "recordWithUID", unpatchedRecordWithUID)

        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield wps[0].whenExecuted()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar5 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar5, data_get_3)

        cal1 = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000006")
        cobjs = yield cal1.objectResources()
        self.assertEqual(len(cobjs), 1)
        comp1 = yield cobjs[0].componentForUser()
        self.assertFalse("STATUS:CANCELLED" in str(comp1))
        yield self.commit()


    @inlineCallbacks
    def test_groupRemovalFromEvent(self):
        """
        Test that removing a group from the calendar data also removes the expanded attendees.
        This needs to make sure that an attendee in two groups is NOT removed if only one of
        those groups is removed
        """

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 0)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000010", 0)

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:MAILTO:group02@example.com
ATTENDEE:MAILTO:group03@example.com
END:VEVENT
END:VCALENDAR"""

        data_get_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=GROUP;EMAIL=group02@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=GROUP;EMAIL=group03@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000003
ATTENDEE;CN=User 06;EMAIL=user06@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000006
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
ATTENDEE;CN=User 09;EMAIL=user09@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000009
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR"""

        data_put_2 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:MAILTO:group02@example.com
END:VEVENT
END:VCALENDAR"""

        data_get_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=GROUP;EMAIL=group02@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=User 06;EMAIL=user06@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000006
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SEQUENCE:1
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        vcalendar1 = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar1)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar2 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar2, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)

        # cache groups
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield wps[0].whenExecuted()
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000003")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield wps[0].whenExecuted()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar3 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar3, data_get_1)

        vcalendar4 = Component.fromString(data_put_2)
        yield cobj1.setComponent(vcalendar4)
        yield self.commit()

        cobj1 = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar5 = yield cobj1.component()
        self._assertICalStrEqual(vcalendar5, data_get_2)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)

        # groups did not change so no work proposals
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        self.assertEqual(len(wps), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000003")
        self.assertEqual(len(wps), 0)

        cal1 = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000009")
        cobjs = yield cal1.objectResources()
        self.assertEqual(len(cobjs), 1)
        comp1 = yield cobjs[0].componentForUser()
        self.assertTrue("STATUS:CANCELLED" in str(comp1))
        yield self.commit()
