##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, succeed
from twisted.trial import unittest

from twistedcaldav import memcacher
from twistedcaldav.ical import Component
from twistedcaldav.stdconfig import config

from txdav.caldav.datastore.scheduling.processing import ImplicitProcessor
from txdav.caldav.datastore.scheduling.cuaddress import LocalCalendarUser


class FakeImplicitProcessor(ImplicitProcessor):
    """
    A fake ImplicitProcessor that tracks batch refreshes.
    """

    def __init__(self):
        self.batches = 0


    def _enqueueBatchRefresh(self, exclude_attendees):
        self.batches += 1


    def writeCalendarResource(self, collection, resource, calendar):
        return succeed(FakeResource())



class FakePrincipal(object):

    def __init__(self, cuaddr):
        self.cuaddr = cuaddr


    def calendarUserAddresses(self):
        return (self.cuaddr,)



class FakeResource(object):

    def parentCollection(self):
        return self


    def ownerHome(self):
        return self


    def uid(self):
        return None


    def id(self):
        return 1



class BatchRefresh (unittest.TestCase):
    """
    iCalendar support tests
    """

    def setUp(self):
        super(BatchRefresh, self).setUp()
        config.Memcached.Pools.Default.ClientEnabled = False
        config.Memcached.Pools.Default.ServerEnabled = False
        memcacher.Memcacher.allowTestCache = True
        memcacher.Memcacher.memoryCacheInstance = None


    @inlineCallbacks
    def test_queueAttendeeUpdate_no_refresh(self):

        self.patch(config.Scheduling.Options, "AttendeeRefreshBatch", 5)

        calendar = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER:urn:uuid:user01
ATTENDEE:urn:uuid:user01
ATTENDEE:urn:uuid:user02
END:VEVENT
END:VCALENDAR
""")
        processor = FakeImplicitProcessor()
        processor.txn = ""
        processor.uid = "12345-67890"
        processor.recipient_calendar_resource = FakeResource()
        processor.recipient_calendar = calendar
        yield processor.queueAttendeeUpdate(("urn:uuid:user02", "urn:uuid:user01",))
        self.assertEqual(processor.batches, 0)


    @inlineCallbacks
    def test_queueAttendeeUpdate_with_refresh(self):

        self.patch(config.Scheduling.Options, "AttendeeRefreshBatch", 5)

        calendar = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER:urn:uuid:user01
ATTENDEE:urn:uuid:user01
ATTENDEE:urn:uuid:user02
ATTENDEE:urn:uuid:user03
END:VEVENT
END:VCALENDAR
""")
        processor = FakeImplicitProcessor()
        processor.txn = ""
        processor.uid = "12345-67890"
        processor.recipient_calendar_resource = FakeResource()
        processor.recipient_calendar = calendar
        yield processor.queueAttendeeUpdate(("urn:uuid:user02", "urn:uuid:user01",))
        self.assertEqual(processor.batches, 1)


    @inlineCallbacks
    def test_queueAttendeeUpdate_count_suppressed(self):

        self.patch(config.Scheduling.Options, "AttendeeRefreshCountLimit", 5)
        self.patch(config.Scheduling.Options, "AttendeeRefreshBatch", 5)

        calendar_small = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER:urn:uuid:user01
ATTENDEE:urn:uuid:user01
ATTENDEE:urn:uuid:user02
ATTENDEE:urn:uuid:user03
ATTENDEE:urn:uuid:user04
END:VEVENT
END:VCALENDAR
""")
        itip_small = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER:urn:uuid:user01
ATTENDEE;PARTSTAT="ACCEPTED":urn:uuid:user02
END:VEVENT
END:VCALENDAR
""")
        calendar_large = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER:urn:uuid:user01
ATTENDEE:urn:uuid:user01
ATTENDEE:urn:uuid:user02
ATTENDEE:urn:uuid:user03
ATTENDEE:urn:uuid:user04
ATTENDEE:urn:uuid:user05
ATTENDEE:urn:uuid:user06
ATTENDEE:urn:uuid:user07
ATTENDEE:urn:uuid:user08
ATTENDEE:urn:uuid:user09
ATTENDEE:urn:uuid:user10
END:VEVENT
END:VCALENDAR
""")
        itip_large = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER:urn:uuid:user01
ATTENDEE;PARTSTAT="ACCEPTED":urn:uuid:user02
END:VEVENT
END:VCALENDAR
""")

        for count, calendar, itip, result, msg in (
            (5, calendar_small, itip_small, 1, "Small, count=5"),
            (5, calendar_large, itip_large, 0, "Large, count=5"),
            (0, calendar_small, itip_small, 1, "Small, count=0"),
            (0, calendar_large, itip_large, 1, "Large, count=0"),
        ):
            config.Scheduling.Options.AttendeeRefreshCountLimit = count
            processor = FakeImplicitProcessor()
            processor.txn = ""
            processor.recipient_calendar = calendar.duplicate()
            processor.uid = processor.recipient_calendar.newUID()
            processor.recipient_calendar_resource = FakeResource()
            processor.message = itip.duplicate()
            processor.message.newUID(processor.uid)
            processor.originator = LocalCalendarUser(None, None)
            processor.recipient = LocalCalendarUser(None, None)
            processor.uid = calendar.resourceUID()
            processor.noAttendeeRefresh = False

            processed = yield processor.doImplicitOrganizerUpdate()
            self.assertTrue(processed[3] is not None, msg=msg)
            self.assertEqual(processor.batches, result, msg=msg)
