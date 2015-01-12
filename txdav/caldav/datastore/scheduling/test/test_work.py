##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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
from twistedcaldav.ical import Component, diff_iCalStrs, normalize_iCalStr
from twext.enterprise.jobqueue import JobItem, WorkItem
from txdav.common.datastore.sql_tables import scheduleActionFromSQL
from twisted.internet import reactor

"""
Tests for txdav.caldav.datastore.utils
"""

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial import unittest

from txdav.caldav.datastore.scheduling.work import ScheduleOrganizerWork, \
    ScheduleWorkMixin, ScheduleWork, ScheduleOrganizerSendWork
from txdav.common.datastore.test.util import populateCalendarsFrom, CommonCommonTests



class BaseWorkTests(CommonCommonTests, unittest.TestCase):
    """
    Tests for scheduling work.
    """
    @inlineCallbacks
    def setUp(self):

        yield super(BaseWorkTests, self).setUp()
        yield self.buildStoreAndDirectory()
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()

    requirements = {
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


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def _runAllJobs(self):
        """
        Run all outstanding jobs.
        """
        # Run jobs
        jobs = yield JobItem.all(self.transactionUnderTest())
        while jobs:
            yield jobs[0].run()
            yield self.commit()
            jobs = yield JobItem.all(self.transactionUnderTest())
        yield self.commit()


    @inlineCallbacks
    def _runOneJob(self):
        """
        Run the first outstanding jobs.
        """
        # Run jobs
        jobs = yield JobItem.all(self.transactionUnderTest())
        for job in jobs:
            yield job.run()
            break
        yield self.commit()


    @inlineCallbacks
    def createOrganizerEvent(self, organizer, ical, run_jobs=True):
        """
        Create an organizer event and wait for the jobs to complete.
        """
        cal = yield self.calendarUnderTest(name="calendar", home=organizer)
        yield cal.createCalendarObjectWithName("invite.ics", ical)
        yield self.commit()

        if run_jobs:
            yield self._runAllJobs()


    @inlineCallbacks
    def getOrganizerResource(self, organizer):
        """
        Get the attendee's event.
        """
        calobj = yield self.calendarObjectUnderTest(name="invite.ics", calendar_name="calendar", home=organizer)
        returnValue(calobj)


    @inlineCallbacks
    def setOrganizerEvent(self, organizer, ical, run_jobs=True):
        """
        Set the organizer's event.
        """
        calobj = yield self.getOrganizerResource(organizer)
        yield calobj.setComponent(ical)
        yield self.commit()

        if run_jobs:
            yield self._runAllJobs()


    @inlineCallbacks
    def getOrganizerEvent(self, organizer):
        """
        Get the organizer's event.
        """
        calobj = yield self.getOrganizerResource(organizer)
        comp = yield calobj.componentForUser()
        yield self.commit()
        returnValue(comp)


    @inlineCallbacks
    def getAttendeeResource(self, attendee):
        """
        Get the attendee's event.
        """
        cal = yield self.calendarUnderTest(name="calendar", home=attendee)
        calobjs = yield cal.calendarObjects()
        self.assertEqual(len(calobjs), 1)
        returnValue(calobjs[0])


    @inlineCallbacks
    def setAttendeeEvent(self, attendee, ical, run_jobs=True):
        """
        Set the attendee's event.
        """
        calobj = yield self.getAttendeeResource(attendee)
        yield calobj.setComponent(ical)
        yield self.commit()

        if run_jobs:
            yield self._runAllJobs()


    @inlineCallbacks
    def getAttendeeEvent(self, attendee):
        """
        Get the attendee's event.
        """
        calobj = yield self.getAttendeeResource(attendee)
        comp = yield calobj.componentForUser()
        yield self.commit()
        returnValue(comp)



class TestScheduleOrganizerWork(BaseWorkTests):
    """
    Test creation of L{ScheduleOrganizerWork} items.
    """

    calendar_old = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DURATION:PT1H
ORGANIZER:urn:uuid:user01
ATTENDEE:urn:uuid:user01
ATTENDEE:urn:uuid:user02
END:VEVENT
END:VCALENDAR
""")

    calendar_new = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER:urn:uuid:user01
ATTENDEE:urn:uuid:user01
ATTENDEE:urn:uuid:user02
END:VEVENT
END:VCALENDAR
""")


    @inlineCallbacks
    def test_create(self):
        """
        Test that jobs associated with L{txdav.caldav.datastore.scheduling.work.ScheduleOrganizerWork}
        can be created and correctly removed.
        """

        ScheduleWorkMixin._queued = 0
        txn = self.transactionUnderTest()
        home = yield self.homeUnderTest(name="user01")
        yield ScheduleOrganizerWork.schedule(
            txn,
            "12345-67890",
            "create",
            home,
            None,
            None,
            self.calendar_new,
            "urn:uuid:user01",
            2,
            True,
        )
        yield self.commit()
        self.assertEqual(ScheduleWorkMixin._queued, 1)

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 1)

        work = yield jobs[0].workItem()
        self.assertTrue(isinstance(work, ScheduleOrganizerWork))
        self.assertEqual(work.icalendarUid, "12345-67890")
        self.assertEqual(scheduleActionFromSQL[work.scheduleAction], "create")

        yield work.delete()
        yield jobs[0].delete()
        yield self.commit()

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 0)
        work = yield ScheduleOrganizerWork.all(self.transactionUnderTest())
        self.assertEqual(len(work), 0)
        baseWork = yield ScheduleWork.all(self.transactionUnderTest())
        self.assertEqual(len(baseWork), 0)


    @inlineCallbacks
    def test_cascade_delete_cleanup(self):
        """
        Test that when work associated with L{txdav.caldav.datastore.scheduling.work.ScheduleWork}
        is removed with the L{ScheduleWork} item being removed, the associated L{JobItem} runs and
        removes itself and the L{ScheduleWork}.
        """

        ScheduleWorkMixin._queued = 0
        txn = self.transactionUnderTest()
        home = yield self.homeUnderTest(name="user01")
        yield ScheduleOrganizerWork.schedule(
            txn,
            "12345-67890",
            "create",
            home,
            None,
            None,
            self.calendar_new,
            "urn:uuid:user01",
            2,
            True,
        )
        yield self.commit()
        self.assertEqual(ScheduleWorkMixin._queued, 1)

        jobs = yield JobItem.all(self.transactionUnderTest())
        work = yield jobs[0].workItem()
        yield WorkItem.delete(work)
        yield self.commit()

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 1)
        baseWork = yield ScheduleWork.all(self.transactionUnderTest())
        self.assertEqual(len(baseWork), 1)
        self.assertEqual(baseWork[0].jobID, jobs[0].jobID)

        work = yield jobs[0].workItem()
        self.assertTrue(work is None)
        yield self.commit()

        yield JobItem.waitEmpty(self.storeUnderTest().newTransaction, reactor, 60)

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 0)
        work = yield ScheduleOrganizerWork.all(self.transactionUnderTest())
        self.assertEqual(len(work), 0)
        baseWork = yield ScheduleWork.all(self.transactionUnderTest())
        self.assertEqual(len(baseWork), 0)



class TestScheduleOrganizerSendWork(BaseWorkTests):
    """
    Test creation of L{ScheduleOrganizerSendWork} items.
    """

    itip_new = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER:urn:x-uid:user01
{attendees}
END:VEVENT
END:VCALENDAR
""".format(attendees="\n".join(["ATTENDEE:urn:x-uid:user%02d" % i for i in range(1, 100)])))


    @inlineCallbacks
    def test_create(self):
        """
        Test that jobs associated with L{txdav.caldav.datastore.scheduling.work.ScheduleOrganizerSendWork}
        can be created and correctly removed.
        """

        txn = self.transactionUnderTest()
        home = yield self.homeUnderTest(name="user01")
        yield ScheduleOrganizerSendWork.schedule(
            txn,
            "create",
            home,
            None,
            "urn:x-uid:user01",
            "urn:x-uid:user02",
            self.itip_new,
            True,
            1000,
        )

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 1)

        work = yield jobs[0].workItem()
        yield work.doWork()

        home2 = yield self.calendarUnderTest(home="user02", name="calendar")
        cobjs = yield home2.calendarObjects()
        self.assertEqual(len(cobjs), 1)
        # cal2 = yield cobjs[0].component()

        yield work.delete()
        yield jobs[0].delete()
        yield self.commit()



class TestScheduleWork(BaseWorkTests):
    """
    Test various scheduling work scenarios that are potential race conditions and could give rise to
    partstat mismatches between organizer and attendee, or cause work items to fail.
    """

    def configure(self):
        super(TestScheduleWork, self).configure()

        # Enable the queue and make it slow
        self.patch(self.config.Scheduling.Options.WorkQueues, "Enabled", True)
        self.patch(self.config.Scheduling.Options.WorkQueues, "RequestDelaySeconds", 1000)
        self.patch(self.config.Scheduling.Options.WorkQueues, "ReplyDelaySeconds", 1000)
        self.patch(self.config.Scheduling.Options.WorkQueues, "AutoReplyDelaySeconds", 1000)
        self.patch(self.config.Scheduling.Options.WorkQueues, "AttendeeRefreshBatchDelaySeconds", 1000)
        self.patch(self.config.Scheduling.Options.WorkQueues, "AttendeeRefreshBatchIntervalSeconds", 1000)
        self.patch(JobItem, "failureRescheduleInterval", 1000)
        self.patch(JobItem, "lockRescheduleInterval", 1000)


    @inlineCallbacks
    def test_replyBeforeResourceDelete(self):
        """
        Test that a reply is sent if an attendee changes an event, then immediately deletes it.
        """

        organizer1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        attendee1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")

        organizer2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        attendee2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=DECLINED:urn:x-uid:user02
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")

        yield self.createOrganizerEvent("user01", organizer1)
        attendee = yield self.getAttendeeEvent("user02")
        self.assertEqual(attendee, attendee1, msg=diff_iCalStrs(attendee, attendee1))

        yield self.setAttendeeEvent("user02", attendee2, run_jobs=False)
        calobj = yield self.getAttendeeResource("user02")
        yield calobj.remove()
        yield self.commit()

        yield self._runAllJobs()

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 0)
        yield self.commit()

        organizer = yield self.getOrganizerEvent("user01")
        self.assertEqual(organizer, organizer2, msg=diff_iCalStrs(organizer, organizer2))


    @inlineCallbacks
    def test_replyBeforeOrganizerEXDATE(self):
        """
        Test that a reply is sent if an attendee changes an event, but the organizer exdate's
        the instance before the reply work is processed.
        """

        organizer1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
RRULE:FREQ=DAILY
END:VEVENT
END:VCALENDAR
""")

        attendee1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
RRULE:FREQ=DAILY
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")

        organizer2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
EXDATE:20080602T130000Z
RRULE:FREQ=DAILY
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""")

        attendee2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
RRULE:FREQ=DAILY
TRANSP:TRANSPARENT
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20080602T130000Z
DTSTAMP:20080601T130000Z
DTSTART:20080602T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=DECLINED:urn:x-uid:user02
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")

        attendee3 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
EXDATE:20080602T130000Z
RRULE:FREQ=DAILY
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")

        yield self.createOrganizerEvent("user01", organizer1)
        attendee = yield self.getAttendeeEvent("user02")
        self.assertEqual(attendee, attendee1, msg=diff_iCalStrs(attendee, attendee1))

        yield self.setOrganizerEvent("user01", organizer2, run_jobs=False)
        yield self._runOneJob()
        yield self.setAttendeeEvent("user02", attendee2, run_jobs=False)
        yield self.setAttendeeEvent("user02", attendee3, run_jobs=False)

        yield self._runAllJobs()

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 0)
        yield self.commit()


    @inlineCallbacks
    def test_replyBeforeOrganizerInconsequentialChange(self):
        """
        Test that the organizer and attendee see the attendee's partstat change when the organizer makes
        an inconsequential change whilst the attendee reply is in progress.
        """

        organizer1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        organizer2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""")

        organizer3 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:urn:x-uid:user02
SEQUENCE:1
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""")

        attendee1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")

        attendee2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        attendee3 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com;SCHEDULE-STATUS=1.2:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user02
SEQUENCE:1
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""")


        yield self.createOrganizerEvent("user01", organizer1)
        attendee = yield self.getAttendeeEvent("user02")
        self.assertEqual(attendee, attendee1, msg=diff_iCalStrs(attendee, attendee1))

        yield self.setOrganizerEvent("user01", organizer2, run_jobs=False)
        yield self._runOneJob()
        yield self.setAttendeeEvent("user02", attendee2, run_jobs=False)

        yield self._runAllJobs()

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 0)
        yield self.commit()

        organizer = yield self.getOrganizerEvent("user01")
        self.assertEqual(normalize_iCalStr(organizer), normalize_iCalStr(organizer3), msg=diff_iCalStrs(organizer3, organizer))
        attendee = yield self.getAttendeeEvent("user02")
        self.assertEqual(normalize_iCalStr(attendee), normalize_iCalStr(attendee3), msg=diff_iCalStrs(attendee3, attendee))


    @inlineCallbacks
    def test_replyBeforeOrganizerConsequentialChange(self):
        """
        Test that the organizer and attendee see the attendee's partstat change when the organizer makes
        a consequential change whilst the attendee reply is in progress.
        """

        organizer1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        organizer2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080602T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""")

        organizer3 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080602T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;SCHEDULE-STATUS=1.2;X-CALENDARSERVER-RESET-PARTSTAT=1:urn:x-uid:user02
SEQUENCE:1
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""")

        attendee1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")

        attendee2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        attendee3 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080602T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com;SCHEDULE-STATUS=1.2:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
SEQUENCE:1
SUMMARY:Test
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")


        yield self.createOrganizerEvent("user01", organizer1)
        attendee = yield self.getAttendeeEvent("user02")
        self.assertEqual(attendee, attendee1, msg=diff_iCalStrs(attendee, attendee1))

        yield self.setOrganizerEvent("user01", organizer2, run_jobs=False)
        yield self._runOneJob()
        yield self.setAttendeeEvent("user02", attendee2, run_jobs=False)

        yield self._runAllJobs()

        jobs = yield JobItem.all(self.transactionUnderTest())
        self.assertEqual(len(jobs), 0)
        yield self.commit()

        organizer = yield self.getOrganizerEvent("user01")
        self.assertEqual(normalize_iCalStr(organizer), normalize_iCalStr(organizer3), msg=diff_iCalStrs(organizer3, organizer))
        attendee = yield self.getAttendeeEvent("user02")
        self.assertEqual(normalize_iCalStr(attendee), normalize_iCalStr(attendee3), msg=diff_iCalStrs(attendee3, attendee))


    @inlineCallbacks
    def test_needsActionOrganizerChange(self):
        """
        Test that if the organizer makes an inconsequential change and also changes the
        attendee partstat, then the new partstat is sent to the attendee.
        """

        organizer1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        organizer2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED;SCHEDULE-STATUS=2.0:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        organizer3 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION:urn:x-uid:user02
SUMMARY:Test
END:VEVENT
END:VCALENDAR
""")

        attendee1 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")

        attendee2 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user02
END:VEVENT
END:VCALENDAR
""")

        attendee3 = Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20080601T130000Z
DTSTART:20080601T130000Z
DURATION:PT1H
ORGANIZER;CN=User 01;EMAIL=user01@example.com;SCHEDULE-STATUS=1.2:urn:x-uid:user01
ATTENDEE;CN=User 01;EMAIL=user01@example.com;PARTSTAT=ACCEPTED:urn:x-uid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:urn:x-uid:user02
SEQUENCE:1
SUMMARY:Test
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR
""")


        yield self.createOrganizerEvent("user01", organizer1)
        attendee = yield self.getAttendeeEvent("user02")
        self.assertEqual(attendee, attendee1, msg=diff_iCalStrs(attendee, attendee1))
        yield self.setAttendeeEvent("user02", attendee2)
        organizer = yield self.getOrganizerEvent("user01")
        self.assertEqual(normalize_iCalStr(organizer), normalize_iCalStr(organizer2), msg=diff_iCalStrs(organizer2, organizer))

        yield self.setOrganizerEvent("user01", organizer3)
        attendee = yield self.getAttendeeEvent("user02")
        self.assertEqual(normalize_iCalStr(attendee), normalize_iCalStr(attendee3), msg=diff_iCalStrs(attendee3, attendee))
