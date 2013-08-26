##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from pycalendar.datetime import DateTime

from twext.python.clsprop import classproperty

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase

from twistedcaldav.ical import Component

from txdav.caldav.datastore.test.util import buildCalendarStore
from txdav.common.datastore.test.util import CommonCommonTests, populateCalendarsFrom
from txdav.caldav.datastore.scheduling.caldav.scheduler import CalDAVScheduler

def normalizeiCalendarText(data):
    data = data.replace("\r\n ", "")
    data = [line for line in data.splitlines() if not (line.startswith("UID") or line.startswith("DTSTAMP"))]
    return "\r\n".join(data) + "\r\n"



class SchedulerFreeBusyRequest(CommonCommonTests, TestCase):
    """
    Test txdav.caldav.datastore.scheduling.scheduler.doScheduleingViaPOST
    """

    @inlineCallbacks
    def setUp(self):
        yield super(SchedulerFreeBusyRequest, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        yield self.populate()

        self.now = DateTime.getNowUTC()
        self.now.setHHMMSS(0, 0, 0)

        self.now_12H = self.now.duplicate()
        self.now_12H.offsetHours(12)

        self.now_13H = self.now.duplicate()
        self.now_13H.offsetHours(13)

        self.now_1D = self.now.duplicate()
        self.now_1D.offsetDay(1)


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user02": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user03": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
    }


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def _createCalendarObject(self, data, user, name):
        calendar_collection = (yield self.calendarUnderTest(home=user))
        yield calendar_collection.createCalendarObjectWithName("test.ics", Component.fromString(data))
        yield self.commit()


    @inlineCallbacks
    def _listCalendarObjects(self, user, collection_name="calendar_1"):
        collection = (yield self.calendarUnderTest(name=collection_name, home=user))
        items = (yield collection.listCalendarObjects())
        yield self.commit()
        returnValue(items)


    @inlineCallbacks
    def _getCalendarData(self, user, name=None):
        if name is None:
            items = (yield self._listCalendarObjects(user))
            name = items[0]

        calendar_resource = (yield self.calendarObjectUnderTest(name=name, home=user))
        calendar = (yield calendar_resource.component())
        yield self.commit()
        returnValue(str(calendar).replace("\r\n ", ""))


    @inlineCallbacks
    def _setCalendarData(self, data, user, name=None):
        if name is None:
            items = (yield self._listCalendarObjects(user))
            name = items[0]

        calendar_resource = (yield self.calendarObjectUnderTest(name=name, home=user))
        yield calendar_resource.setComponent(Component.fromString(data))
        yield self.commit()


    @inlineCallbacks
    def test_no_events(self):
        """
        Test when the calendar is empty.
        """

        data_request = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VFREEBUSY
UID:1234-5678
DTSTAMP:20080601T000000Z
DTSTART:%s
DTEND:%s
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
END:VFREEBUSY
END:VCALENDAR
""" % (self.now.getText(), self.now_1D.getText(),)

        data_reply = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VFREEBUSY
DTSTART:%s
DTEND:%s
ATTENDEE:mailto:user01@example.com
ORGANIZER:mailto:user01@example.com
END:VFREEBUSY
END:VCALENDAR
""" % (self.now.getText(), self.now_1D.getText(),)

        scheduler = CalDAVScheduler(self.transactionUnderTest(), "user01")
        result = (yield scheduler.doSchedulingViaPOST("mailto:user01@example.com", ["mailto:user01@example.com", ], Component.fromString(data_request)))
        self.assertEqual(len(result.responses), 1)
        self.assertEqual(str(result.responses[0].recipient.children[0]), "mailto:user01@example.com")
        self.assertTrue(str(result.responses[0].reqstatus).startswith("2"))
        self.assertEqual(normalizeiCalendarText(str(result.responses[0].calendar)), data_reply.replace("\n", "\r\n"))


    @inlineCallbacks
    def test_one_event(self):
        """
        Test when the calendar is empty.
        """

        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:1234-5678
DTSTAMP:20080601T000000Z
DTSTART:%s
DTEND:%s
END:VEVENT
END:VCALENDAR
""" % (self.now_12H.getText(), self.now_13H.getText(),)

        yield self._createCalendarObject(data, "user01", "test.ics")

        data_request = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VFREEBUSY
UID:1234-5678
DTSTAMP:20080601T000000Z
DTSTART:%s
DTEND:%s
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
END:VFREEBUSY
END:VCALENDAR
""" % (self.now.getText(), self.now_1D.getText(),)

        data_reply = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VFREEBUSY
DTSTART:%s
DTEND:%s
ATTENDEE:mailto:user01@example.com
FREEBUSY;FBTYPE=BUSY:%s/PT1H
ORGANIZER:mailto:user01@example.com
END:VFREEBUSY
END:VCALENDAR
""" % (self.now.getText(), self.now_1D.getText(), self.now_12H.getText(),)

        scheduler = CalDAVScheduler(self.transactionUnderTest(), "user01")
        result = (yield scheduler.doSchedulingViaPOST("mailto:user01@example.com", ["mailto:user01@example.com", ], Component.fromString(data_request)))
        self.assertEqual(len(result.responses), 1)
        self.assertEqual(str(result.responses[0].recipient.children[0]), "mailto:user01@example.com")
        self.assertTrue(str(result.responses[0].reqstatus).startswith("2"))
        self.assertEqual(normalizeiCalendarText(str(result.responses[0].calendar)), data_reply.replace("\n", "\r\n"))


    @inlineCallbacks
    def test_one_event_event_details(self):
        """
        Test when the calendar is empty.
        """

        data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:1234-5678
DTSTAMP:20080601T000000Z
DTSTART:%s
DTEND:%s
END:VEVENT
END:VCALENDAR
""" % (self.now_12H.getText(), self.now_13H.getText(),)

        yield self._createCalendarObject(data, "user01", "test.ics")

        data_request = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VFREEBUSY
UID:1234-5678
DTSTAMP:20080601T000000Z
DTSTART:%s
DTEND:%s
ORGANIZER:mailto:user01@example.com
ATTENDEE:mailto:user01@example.com
X-CALENDARSERVER-EXTENDED-FREEBUSY:T
END:VFREEBUSY
END:VCALENDAR
""" % (self.now.getText(), self.now_1D.getText(),)

        data_reply = """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
DTSTART:%(now_12H)s
DTEND:%(now_13H)s
END:VEVENT
BEGIN:VFREEBUSY
DTSTART:%(now)s
DTEND:%(now_1D)s
ATTENDEE:mailto:user01@example.com
FREEBUSY;FBTYPE=BUSY:%(now_12H)s/PT1H
ORGANIZER:mailto:user01@example.com
END:VFREEBUSY
END:VCALENDAR
""" % {
    "now": self.now.getText(),
    "now_1D": self.now_1D.getText(),
    "now_12H": self.now_12H.getText(),
    "now_13H": self.now_13H.getText(),
}

        scheduler = CalDAVScheduler(self.transactionUnderTest(), "user01")
        result = (yield scheduler.doSchedulingViaPOST("mailto:user01@example.com", ["mailto:user01@example.com", ], Component.fromString(data_request)))
        self.assertEqual(len(result.responses), 1)
        self.assertEqual(str(result.responses[0].recipient.children[0]), "mailto:user01@example.com")
        self.assertTrue(str(result.responses[0].reqstatus).startswith("2"))
        self.assertEqual(normalizeiCalendarText(str(result.responses[0].calendar)), data_reply.replace("\n", "\r\n"))
