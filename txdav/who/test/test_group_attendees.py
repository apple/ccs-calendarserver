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

from twext.enterprise.dal.syntax import Insert
from twext.enterprise.jobqueue import JobItem
from twext.python.filepath import CachingFilePath as FilePath
from twext.who.directory import DirectoryService
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial import unittest
from twistedcaldav.config import config
from twistedcaldav.ical import Component, normalize_iCalStr, ignoredComponents
from txdav.caldav.datastore.test.util import populateCalendarsFrom, CommonCommonTests
from txdav.common.datastore.sql_tables import schema
from txdav.who.directory import CalendarDirectoryRecordMixin
from txdav.who.groups import GroupCacher
import os


class GroupAttendeeReconciliation(CommonCommonTests, unittest.TestCase):
    """
    GroupAttendeeReconciliation tests
    """

    @inlineCallbacks
    def setUp(self):
        yield super(GroupAttendeeReconciliation, self).setUp()

        accountsFilePath = FilePath(
            os.path.join(os.path.dirname(__file__), "accounts")
        )
        yield self.buildStoreAndDirectory(
            accounts=accountsFilePath.child("groupAttendeeAccounts.xml"),
            resources=accountsFilePath.child("resources.xml"),
        )
        yield self.populate()

        self.paths = {}


    def configure(self):
        super(GroupAttendeeReconciliation, self).configure()
        config.GroupAttendees.Enabled = True
        config.GroupAttendees.ReconciliationDelaySeconds = 0
        config.GroupAttendees.UpdateOldEventLimitSeconds = 0


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())

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
            orderMemberValues(Component.fromString(normalize_iCalStr(iCalStr1))),
            orderMemberValues(Component.fromString(normalize_iCalStr(iCalStr2)))
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
DTSTART:20140101T100000Z
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
DTSTART:20140101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=X-SERVER-GROUP;EMAIL=group02@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000002
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

        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)


    @inlineCallbacks
    def test_unknownPUT(self):
        """
        Test unknown group with CUTYPE=X-SERVER-GROUP handled
        """
        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20140101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE;CUTYPE=X-SERVER-GROUP:urn:uuid:FFFFFFFF-EEEE-DDDD-CCCC-BBBBBBBBBBBB
END:VEVENT
END:VCALENDAR"""

        data_get_1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART:20140101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CUTYPE=X-SERVER-GROUP;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:uuid:FFFFFFFF-EEEE-DDDD-CCCC-BBBBBBBBBBBB
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_1))


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
DTSTART:20140101T100000Z
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
DTSTART:20140101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""
        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_1))


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
DTSTART:20140101T100000Z
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
DTSTART:20140101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 04;CUTYPE=X-SERVER-GROUP;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000004
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

        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_1)

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
DTSTART:20140101T100000Z
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
DTSTART:20140101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=X-SERVER-GROUP;EMAIL=group02@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=X-SERVER-GROUP;EMAIL=group03@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000003
ATTENDEE;CN=User 06;EMAIL=user06@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000006
ATTENDEE;CN=User 07;EMAIL=user07@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000007
ATTENDEE;CN=User 08;EMAIL=user08@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000002","urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000008
ATTENDEE;CN=User 09;EMAIL=user09@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000003";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000009
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:10000000-0000-0000-0000-000000000001
SUMMARY:event 1
END:VEVENT
END:VCALENDAR"""

        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)


    @inlineCallbacks
    def test_groupChange(self):
        """
        Test that group attendee are changed when the group changes.
        """

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20240101T100000Z
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
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
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        self.assertEqual(len(wps), 0)

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_2))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 0)
        yield self.commit()

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", unpatchedExpandedMembers)

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)
        self.assertEqual(list(groupsToRefresh)[0], "20000000-0000-0000-0000-000000000001")

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_3))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 1)
        yield self.commit()

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_4))

        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")
        cobjs = yield cal.objectResources()
        self.assertEqual(len(cobjs), 1)
        comp = yield cobjs[0].componentForUser()
        self.assertTrue("STATUS:CANCELLED" in str(comp))


    @inlineCallbacks
    def test_multieventGroupChange(self):
        """
        Test that every event associated with a group changes when the group changes
        """

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20240101T100000Z
DURATION:PT1H
SUMMARY:event {0}
UID:event{0}@ninevah.local
ORGANIZER:MAILTO:user0{0}@example.com
ATTENDEE:mailto:user0{0}@example.com
ATTENDEE:MAILTO:group01@example.com
END:VEVENT
END:VCALENDAR"""

        data_get_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event{0}@ninevah.local
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 0{0};EMAIL=user0{0}@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-00000000000{0}
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 0{0};EMAIL=user0{0}@example.com:urn:x-uid:10000000-0000-0000-0000-00000000000{0}
SUMMARY:event {0}
END:VEVENT
END:VCALENDAR
"""

        data_get_3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event{0}@ninevah.local
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 0{0};EMAIL=user0{0}@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-00000000000{0}
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 01;EMAIL=user01@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000001";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 0{0};EMAIL=user0{0}@example.com:urn:x-uid:10000000-0000-0000-0000-00000000000{0}
SEQUENCE:1
SUMMARY:event {0}
END:VEVENT
END:VCALENDAR
"""

        data_get_4 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event{0}@ninevah.local
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 0{0};EMAIL=user0{0}@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-00000000000{0}
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 0{0};EMAIL=user0{0}@example.com:urn:x-uid:10000000-0000-0000-0000-00000000000{0}
SEQUENCE:2
SUMMARY:event {0}
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
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        self.assertEqual(len(wps), 0)

        userRange = range(6, 10) # have to be 1 diget and homes in requirements

        for i in userRange:
            calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-00000000000{0}".format(i))
            vcalendar = Component.fromString(data_put_1.format(i))
            yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
            yield self.commit()

            cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-00000000000{0}".format(i))
            vcalendar = yield cobj.component()
            self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_2.format(i)))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 0)
        yield self.commit()

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", unpatchedExpandedMembers)

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)
        self.assertEqual(list(groupsToRefresh)[0], "20000000-0000-0000-0000-000000000001")

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), len(userRange))
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        for i in userRange:
            cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-00000000000{0}".format(i))
            vcalendar = yield cobj.component()
            self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_3.format(i)))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", len(userRange))
        yield self.commit()

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), len(userRange))
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        for i in userRange:
            cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-00000000000{0}".format(i))
            vcalendar = yield cobj.component()
            self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_4.format(i)))

        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")
        cobjs = yield cal.objectResources()
        self.assertEqual(len(cobjs), len(userRange))
        for cobj in cobjs:
            comp = yield cobj.componentForUser()
            self.assertTrue("STATUS:CANCELLED" in str(comp))


    @inlineCallbacks
    def test_groupPutOldEvent(self):
        """
        Test that old event with group attendee is expaned but not linked to group update
        """

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20140101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user02@example.com
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
DTSTART:20140101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 01;EMAIL=user01@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000001";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 0)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        if len(wps): # This is needed because the test currently fails and does actually create job items we have to wait for
            yield self.commit()
            yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)
        self.assertEqual(len(wps), 0)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_1))


    @inlineCallbacks
    def test_groupChangeOldEvent(self):
        """
        Test that group attendee changes not applied to old events
        """

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20240101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user02@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:MAILTO:group01@example.com
END:VEVENT
END:VCALENDAR"""

        data_put_2 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20140101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user02@example.com
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 01;EMAIL=user01@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000001";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        data_get_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART:20140101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
SEQUENCE:1
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        @inlineCallbacks
        def expandedMembers(self, records=None):
            yield None
            returnValue(set())

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)
        self.assertEqual(list(groupsToRefresh)[0], "20000000-0000-0000-0000-000000000001")

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), 0)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_1))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 1)

        vcalendar = Component.fromString(data_put_2)
        yield cobj.setComponent(vcalendar)
        yield self.commit()

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_2))

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        self.assertEqual(len(wps), 0)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        #finally, simulate an event that has become old
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", unpatchedExpandedMembers)

        (
            groupID, _ignore_name, _ignore_membershipHash, _ignore_modDate,
            _ignore_extant
        ) = yield self.transactionUnderTest().groupByUID("20000000-0000-0000-0000-000000000001")
        ga = schema.GROUP_ATTENDEE
        yield Insert({
                ga.RESOURCE_ID: cobj._resourceID,
                ga.GROUP_ID: groupID,
                ga.MEMBERSHIP_HASH: (-1),
            }
        ).on(self.transactionUnderTest())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_2))

        '''
        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")
        cobjs = yield cal.objectResources()
        for cobj in cobjs:
            print("comp = %s" % ((yield cobj.componentForUser())))
        '''

    @inlineCallbacks
    def test_groupChangeOldNoMasterEvent(self):
        """
        Test that group attendee changes not applied to old events with no master event
        """
        yield None

    test_groupChangeOldNoMasterEvent.todo = "Create test data"


    @inlineCallbacks
    def test_groupChangeOldRecurringEvent(self):
        """
        Test that group attendee changes not applied to old recurring events
        """

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20120101T100000Z
DURATION:PT1H
RRULE:FREQ=DAILY;UNTIL=20240101T100000
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user02@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:MAILTO:group01@example.com
END:VEVENT
END:VCALENDAR"""

        data_put_2 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20120101T100000Z
DURATION:PT1H
RRULE:FREQ=DAILY;UNTIL=20140101T100000
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user02@example.com
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
DTSTART:20120101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 01;EMAIL=user01@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000001";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
RRULE:FREQ=DAILY;UNTIL=20240101T100000
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        data_get_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART:20120101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
RRULE:FREQ=DAILY;UNTIL=20140101T100000
SEQUENCE:1
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        @inlineCallbacks
        def expandedMembers(self, records=None):
            yield None
            returnValue(set())

        unpatchedExpandedMembers = CalendarDirectoryRecordMixin.expandedMembers
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 1)
        self.assertEqual(list(groupsToRefresh)[0], "20000000-0000-0000-0000-000000000001")

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), 0)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_1))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 1)

        vcalendar = Component.fromString(data_put_2)
        yield cobj.setComponent(vcalendar)
        yield self.commit()

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_2))

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        if len(wps): # This is needed because the test currently fails and does actually create job items we have to wait for
            yield self.commit()
            yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)
        self.assertEqual(len(wps), 0)

        #finally, simulate an event that has become old
        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", unpatchedExpandedMembers)

        (
            groupID, _ignore_name, _ignore_membershipHash, _ignore_modDate,
            _ignore_extant
        ) = yield self.transactionUnderTest().groupByUID("20000000-0000-0000-0000-000000000001")
        ga = schema.GROUP_ATTENDEE
        yield Insert({
                ga.RESOURCE_ID: cobj._resourceID,
                ga.GROUP_ID: groupID,
                ga.MEMBERSHIP_HASH: (-1),
            }
        ).on(self.transactionUnderTest())
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_2))


    @inlineCallbacks
    def test_groupChangeSmallerSpanningEvent(self):
        """
        Test that group attendee changes not applied to old recurring events
        """

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20120101T100000Z
DURATION:PT1H
RRULE:FREQ=DAILY;UNTIL=20240101T100000
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user02@example.com
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
DTSTART:20120101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 01;EMAIL=user01@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000001";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
RRULE:FREQ=DAILY;UNTIL=20240101T100000
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        data_get_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
{start}DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
{relatedTo}RRULE:FREQ=DAILY;UNTIL=20240101T100000
SEQUENCE:2
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""
        data_get_3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
{uid}DTSTART:20120101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 01;EMAIL=user01@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000001";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
{relatedTo}{rule}SEQUENCE:1
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        @inlineCallbacks
        def expandedMembers(self, records=None):
            yield None
            returnValue(set())

        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_1))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 1)

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", expandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        cobjs = yield cal.objectResources()
        for cobj in cobjs:
            vcalendar = yield cobj.component()
            for component in vcalendar.subcomponents():
                if component.name() in ignoredComponents:
                    continue
                relatedTo = component.getProperty("RELATED-TO")
                start = component.getProperty("DTSTART")
                rule = component.getProperty("RRULE")
                uid = component.getProperty("UID")
                break

            if cobj.name() == "data1.ics":
                self.assertEqual(
                    normalize_iCalStr(vcalendar),
                    normalize_iCalStr(
                        data_get_2.format(
                            start=start,
                            relatedTo=relatedTo,
                        )
                    )
                )
            else:
                self.assertEqual(
                    normalize_iCalStr(vcalendar),
                    normalize_iCalStr(
                        data_get_3.format(
                            relatedTo=relatedTo,
                            rule=rule,
                            uid=uid
                        )
                    )
                )

        #TODO: add some meaningful test
        '''
        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")
        cobjs = yield cal.objectResources()
        for cobj in cobjs:
            vcalendar = yield cobj.component()
            print("vcalendar = %s" % (vcalendar,))
        '''

    @inlineCallbacks
    def test_groupChangeLargerSpanningEvent(self):
        """
        Test that group attendee changes not applied to old recurring events
        """

        data_put_1 = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20120101T100000Z
DURATION:PT1H
RRULE:FREQ=DAILY;UNTIL=20240101T100000
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user02@example.com
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
DTSTART:20120101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
RRULE:FREQ=DAILY;UNTIL=20240101T100000
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        data_get_2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
{start}DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=User 01;EMAIL=user01@example.com;MEMBER="urn:x-uid:20000000-0000-0000-0000-000000000001";PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:10000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
{relatedTo}RRULE:FREQ=DAILY;UNTIL=20240101T100000
SEQUENCE:2
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""
        data_get_3 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
{uid}DTSTART:20120101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
CREATED:20060101T150000Z
ORGANIZER;CN=User 02;EMAIL=user02@example.com:urn:x-uid:10000000-0000-0000-0000-000000000002
{relatedTo}{rule}SEQUENCE:1
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

        calendar = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000002")
        vcalendar = yield cobj.component()
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get_1))

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 0)

        self.patch(CalendarDirectoryRecordMixin, "expandedMembers", unpatchedExpandedMembers)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000001")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000002")
        cobjs = yield cal.objectResources()
        for cobj in cobjs:
            vcalendar = yield cobj.component()
            for component in vcalendar.subcomponents():
                if component.name() in ignoredComponents:
                    continue
                relatedTo = component.getProperty("RELATED-TO")
                start = component.getProperty("DTSTART")
                rule = component.getProperty("RRULE")
                uid = component.getProperty("UID")
                break

            if cobj.name() == "data1.ics":
                self.assertEqual(
                    normalize_iCalStr(vcalendar),
                    normalize_iCalStr(
                        data_get_2.format(
                            start=start,
                            relatedTo=relatedTo,
                        )
                    )
                )
            else:
                self.assertEqual(
                    normalize_iCalStr(vcalendar),
                    normalize_iCalStr(
                        data_get_3.format(
                            relatedTo=relatedTo,
                            rule=rule,
                            uid=uid
                        )
                    )
                )

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000001", 1)
        #TODO: add some meaningful test
        '''
        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000001")
        cobjs = yield cal.objectResources()
        for cobj in cobjs:
            vcalendar = yield cobj.component()
            print("vcalendar = %s" % (vcalendar,))
        '''

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
DTSTART:20240101T100000Z
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=X-SERVER-GROUP;EMAIL=group02@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=X-SERVER-GROUP;EMAIL=group03@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000003
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=X-SERVER-GROUP;EMAIL=group02@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=X-SERVER-GROUP;EMAIL=group03@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000003
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 01;CUTYPE=X-SERVER-GROUP;EMAIL=group01@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=X-SERVER-GROUP;EMAIL=group02@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=X-SERVER-GROUP;EMAIL=group03@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000003
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

        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)

        # cache group
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 3)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        yield self.commit()
        self.assertEqual(len(wps), 0)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_1)

        # remove group members run cacher again
        self.patch(DirectoryService, "recordWithUID", recordWithUID)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        yield self.commit()
        self.assertEqual(len(wps), 1)
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_2)

        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000006")
        cobjs = yield cal.objectResources()
        self.assertEqual(len(cobjs), 1)
        comp = yield cobjs[0].componentForUser()
        self.assertTrue("STATUS:CANCELLED" in str(comp))
        yield self.commit()

        # add group members back, run cacher
        self.patch(DirectoryService, "recordWithUID", unpatchedRecordWithUID)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        self.assertEqual(len(wps), 1)
        yield self.commit()
        yield JobItem.waitEmpty(self._sqlCalendarStore.newTransaction, reactor, 60)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_3)

        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000006")
        cobjs = yield cal.objectResources()
        self.assertEqual(len(cobjs), 1)
        comp = yield cobjs[0].componentForUser()
        self.assertFalse("STATUS:CANCELLED" in str(comp))
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
DTSTART:20240101T100000Z
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=X-SERVER-GROUP;EMAIL=group02@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000002
ATTENDEE;CN=Group 03;CUTYPE=X-SERVER-GROUP;EMAIL=group03@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000003
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
DTSTART:20240101T100000Z
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
DTSTART:20240101T100000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:x-uid:10000000-0000-0000-0000-000000000001
ATTENDEE;CN=Group 02;CUTYPE=X-SERVER-GROUP;EMAIL=group02@example.com;RSVP=TRUE:urn:x-uid:20000000-0000-0000-0000-000000000002
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

        vcalendar = Component.fromString(data_put_1)
        yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_1)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)

        # cache groups
        groupCacher = GroupCacher(self.transactionUnderTest().directoryService())
        groupsToRefresh = yield groupCacher.groupsToRefresh(self.transactionUnderTest())
        self.assertEqual(len(groupsToRefresh), 2)

        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        yield self.commit()
        self.assertEqual(len(wps), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000003")
        yield self.commit()
        self.assertEqual(len(wps), 0)

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_1)

        vcalendar = Component.fromString(data_put_2)
        yield cobj.setComponent(vcalendar)
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="10000000-0000-0000-0000-000000000001")
        vcalendar = yield cobj.component()
        self._assertICalStrEqual(vcalendar, data_get_2)

        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000006", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000007", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000008", 1)
        yield self._verifyObjectResourceCount("10000000-0000-0000-0000-000000000009", 1)

        # groups did not change so no work proposals
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000002")
        self.assertEqual(len(wps), 0)
        wps = yield groupCacher.refreshGroup(self.transactionUnderTest(), "20000000-0000-0000-0000-000000000003")
        self.assertEqual(len(wps), 0)

        cal = yield self.calendarUnderTest(name="calendar", home="10000000-0000-0000-0000-000000000009")
        cobjs = yield cal.objectResources()
        self.assertEqual(len(cobjs), 1)
        comp = yield cobjs[0].componentForUser()
        self.assertTrue("STATUS:CANCELLED" in str(comp))
        yield self.commit()
