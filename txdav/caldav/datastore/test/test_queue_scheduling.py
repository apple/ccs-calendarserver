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

from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.clsprop import classproperty
from twistedcaldav.config import config
from txdav.caldav.datastore.scheduling.work import ScheduleWorkMixin
from txdav.caldav.datastore.test.util import CommonStoreTests
from txdav.common.datastore.test.util import componentUpdate
from twistedcaldav.ical import normalize_iCalStr

class BaseQueueSchedulingTests(CommonStoreTests):

    """
    Test store-based calendar sharing.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(BaseQueueSchedulingTests, self).setUp()

        # Enable the queue and make it fast
        self.patch(config.Scheduling.Options.WorkQueues, "Enabled", True)
        self.patch(config.Scheduling.Options.WorkQueues, "RequestDelaySeconds", 1)
        self.patch(config.Scheduling.Options.WorkQueues, "ReplyDelaySeconds", 1)
        self.patch(config.Scheduling.Options.WorkQueues, "AutoReplyDelaySeconds", 1)
        self.patch(config.Scheduling.Options.WorkQueues, "AttendeeRefreshBatchDelaySeconds", 1)
        self.patch(config.Scheduling.Options.WorkQueues, "AttendeeRefreshBatchIntervalSeconds", 1)


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
            "user01": {
                "calendar": {
                },
                "inbox": {
                },
            },
            "user02": {
                "calendar": {
                },
                "inbox": {
                },
            },
            "user03": {
                "calendar": {
                },
                "inbox": {
                },
            },
        }


    @inlineCallbacks
    def _getOneResource(self, home, calendar_name):
        """
        Get the one resources expected in a collection
        """
        inbox = yield self.calendarUnderTest(home=home, name=calendar_name)
        objs = yield inbox.objectResources()
        self.assertEqual(len(objs), 1)
        returnValue(objs[0])


    @inlineCallbacks
    def _testOneResource(self, home, calendar_name, data):
        """
        Get the one resources expected in a collection
        """
        inbox = yield self.calendarUnderTest(home=home, name=calendar_name)
        objs = yield inbox.objectResources()
        self.assertEqual(len(objs), 1)

        caldata = yield objs[0].componentForUser()
        self.assertEqual(normalize_iCalStr(caldata), normalize_iCalStr(componentUpdate(data)))



class SimpleSchedulingTests(BaseQueueSchedulingTests):

    @inlineCallbacks
    def test_invite_reply(self):
        """
        Test simple invite/reply roundtrip.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:{now}T000000Z
DURATION:PT1H
ATTENDEE;PARTSTAT=ACCEPTED:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
DTSTAMP:20051222T210507Z
ORGANIZER:mailto:user01@example.com
SUMMARY:1
END:VEVENT
END:VCALENDAR
"""

        data2 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:{now}T000000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:x-uid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
SUMMARY:1
END:VEVENT
END:VCALENDAR
"""

        data3 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:12345-67890
DTSTART:{now}T000000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
SUMMARY:1
END:VEVENT
END:VCALENDAR
"""

        data4 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:{now}T000000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE:urn:x-uid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
SUMMARY:1
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
"""

        data5 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:{now}T000000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
SUMMARY:1
END:VEVENT
END:VCALENDAR
"""

        data6 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:{now}T000000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:urn:x-uid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
SUMMARY:1
END:VEVENT
END:VCALENDAR
"""

        data7 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890
DTSTART:{now}T000000Z
DURATION:PT1H
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
SUMMARY:1
REQUEST-STATUS:2.0;Success
END:VEVENT
END:VCALENDAR
"""

        data8 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:{now}T000000Z
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user02
DTSTAMP:20051222T210507Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com;SCHEDULE-STATUS=1.2:urn:x-uid:user01
SUMMARY:1
END:VEVENT
END:VCALENDAR
"""

        waitForWork = ScheduleWorkMixin.allDone()
        calendar = yield self.calendarUnderTest(home="user01", name="calendar")
        yield calendar.createCalendarObjectWithName("data1.ics", componentUpdate(data1))
        yield self.commit()

        yield waitForWork

        yield self._testOneResource("user01", "calendar", data2)
        yield self._testOneResource("user02", "inbox", data3)
        yield self._testOneResource("user02", "calendar", data4)
        yield self.commit()

        waitForWork = ScheduleWorkMixin.allDone()
        cobj = yield self._getOneResource("user02", "calendar")
        yield cobj.setComponent(componentUpdate(data5))
        yield self.commit()

        yield waitForWork

        yield self._testOneResource("user01", "calendar", data6)
        yield self._testOneResource("user01", "inbox", data7)
        yield self._testOneResource("user02", "calendar", data8)
