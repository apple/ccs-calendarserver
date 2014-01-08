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

import os

from twisted.trial.unittest import SkipTest

from twext.web2 import responsecode
from twext.web2.iweb import IResponse
from twext.web2.stream import MemoryStream
from txdav.xml import element as davxml
from twext.web2.dav.util import davXMLFromStream

from twistedcaldav import caldavxml
from twistedcaldav import ical

from twistedcaldav.query import calendarqueryfilter
from twistedcaldav.config import config
from twistedcaldav.test.util import StoreTestCase, SimpleStoreRequest
from twisted.internet.defer import inlineCallbacks, returnValue

from pycalendar.datetime import PyCalendarDateTime
from twistedcaldav.ical import Component
from txdav.caldav.icalendarstore import ComponentUpdateState
from twistedcaldav.directory.directory import DirectoryService


@inlineCallbacks
def addEventsDir(testCase, eventsDir, uri):
    """
    Add events to a L{HomeTestCase} from a directory.

    @param testCase: The test case to add events to.
    @type testCase: L{HomeTestCase}

    @param eventsDir: A directory full of events.
    @type eventsDir: L{FilePath}

    @param uri: The URI-path of the calendar to insert events into.
    @type uri: C{str}

    @return: a L{Deferred} which fires with the number of added calendar object
        resources.
    """
    count = 0
    for child in eventsDir.children():
        count += 1
        if child.basename().split(".")[-1] != "ics":
            continue
        request = SimpleStoreRequest(testCase, "PUT", uri + "/" + child.basename())
        request.stream = MemoryStream(child.getContent())
        yield testCase.send(request)
    returnValue(count)



class CalendarQuery (StoreTestCase):
    """
    calendar-query REPORT
    """
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    holidays_dir = os.path.join(data_dir, "Holidays")

    @inlineCallbacks
    def populate(self):
        """
        Put the contents of the Holidays directory into the store.
        """
        record = self.directory.recordWithShortName(DirectoryService.recordType_users, "wsanchez")
        yield self.transactionUnderTest().calendarHomeWithUID(record.uid, create=True)
        calendar = yield self.calendarUnderTest(name="calendar", home=record.uid)
        for f in os.listdir(self.holidays_dir):
            if f.endswith(".ics"):
                component = Component.fromString(open(os.path.join(self.holidays_dir, f)).read())
                yield calendar._createCalendarObjectWithNameInternal(f, component, internal_state=ComponentUpdateState.RAW)
        yield self.commit()


    def test_calendar_query_time_range(self):
        """
        Partial retrieval of events by time range.
        (CalDAV-access-09, section 7.6.1)
        """
        calendar_properties = (
            davxml.GETETag(),
            caldavxml.CalendarData(
                caldavxml.CalendarComponent(
                    caldavxml.AllProperties(),
                    caldavxml.CalendarComponent(
                        caldavxml.Property(name="X-ABC-GUID"),
                        caldavxml.Property(name="UID"),
                        caldavxml.Property(name="DTSTART"),
                        caldavxml.Property(name="DTEND"),
                        caldavxml.Property(name="DURATION"),
                        caldavxml.Property(name="EXDATE"),
                        caldavxml.Property(name="EXRULE"),
                        caldavxml.Property(name="RDATE"),
                        caldavxml.Property(name="RRULE"),
                        caldavxml.Property(name="LOCATION"),
                        caldavxml.Property(name="SUMMARY"),
                        name="VEVENT",
                    ),
                    caldavxml.CalendarComponent(
                        caldavxml.AllProperties(),
                        caldavxml.AllComponents(),
                        name="VTIMEZONE",
                    ),
                    name="VCALENDAR",
                ),
            ),
        )

        query_timerange = caldavxml.TimeRange(
            start="%04d1001T000000Z" % (PyCalendarDateTime.getToday().getYear(),),
            end="%04d1101T000000Z" % (PyCalendarDateTime.getToday().getYear(),),
        )

        query = caldavxml.CalendarQuery(
            davxml.PropertyContainer(*calendar_properties),
            caldavxml.Filter(
                caldavxml.ComponentFilter(
                    caldavxml.ComponentFilter(
                        query_timerange,
                        name="VEVENT",
                    ),
                    name="VCALENDAR",
                ),
            ),
        )

        def got_xml(doc):
            if not isinstance(doc.root_element, davxml.MultiStatus):
                self.fail("REPORT response XML root element is not multistatus: %r" % (doc.root_element,))

            for response in doc.root_element.childrenOfType(davxml.PropertyStatusResponse):
                properties_to_find = [p.qname() for p in calendar_properties]

                for propstat in response.childrenOfType(davxml.PropertyStatus):
                    status = propstat.childOfType(davxml.Status)
                    properties = propstat.childOfType(davxml.PropertyContainer).children

                    if status.code != responsecode.OK:
                        self.fail("REPORT failed (status %s) to locate properties: %r"
                                  % (status.code, properties))

                    for property in properties:
                        qname = property.qname()
                        if qname in properties_to_find:
                            properties_to_find.remove(qname)
                        else:
                            self.fail("REPORT found property we didn't ask for: %r" % (property,))

                        if isinstance(property, caldavxml.CalendarData):
                            cal = property.calendar()
                            instances = cal.expandTimeRanges(query_timerange.end)
                            vevents = [x for x in cal.subcomponents() if x.name() == "VEVENT"]
                            if not calendarqueryfilter.TimeRange(query_timerange).matchinstance(vevents[0], instances):
                                self.fail("REPORT property %r returned calendar %s outside of request time range %r"
                                          % (property, property.calendar, query_timerange))

        return self.calendar_query(query, got_xml)


    def test_calendar_query_partial_recurring(self):
        """
        Partial retrieval of recurring events.
        (CalDAV-access-09, section 7.6.2)
        """
        raise SkipTest("test unimplemented")


    def test_calendar_query_expanded_recurring(self):
        """
        Expanded retrieval of recurring events.
        (CalDAV-access-09, section 7.6.3)
        """
        raise SkipTest("test unimplemented")


    def test_calendar_query_partial_freebusy(self):
        """
        Partial retrieval of stored free busy components.
        (CalDAV-access-09, section 7.6.4)
        """
        raise SkipTest("test unimplemented")


    def test_calendar_query_todo_alarm(self):
        """
        Retrieval of to-dos by alarm time range.
        (CalDAV-access-09, section 7.6.5)
        """
        raise SkipTest("test unimplemented")


    def test_calendar_query_by_uid(self):
        """
        Event by UID.
        (CalDAV-access-09, section 7.6.6)
        """
        uid = "C3189A88-1ED0-11D9-A5E0-000A958A3252"

        return self.simple_event_query(
            caldavxml.PropertyFilter(
                caldavxml.TextMatch.fromString(uid, False),
                name="UID",
            ),
            [uid]
        )


    def test_calendar_query_partstat(self):
        """
        Retrieval of events by participation status.
        (CalDAV-access-09, section 7.6.7)
        """
        raise SkipTest("test unimplemented")


    def test_calendar_query_all_events(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """
        uids = [r[0] for r in (os.path.splitext(f) for f in
                os.listdir(self.holidays_dir)) if r[1] == ".ics"]

        return self.simple_event_query(None, uids)


    def test_calendar_query_limited_with_data(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """

        self.patch(config, "MaxQueryWithDataResults", 1)
        def _restoreValueOK(f):
            self.fail("REPORT must fail with 403")

        def _restoreValueError(f):
            return None

        uids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.holidays_dir)) if r[1] == ".ics"]

        d = self.simple_event_query(None, uids)
        d.addCallbacks(_restoreValueOK, _restoreValueError)
        return d


    def test_calendar_query_limited_without_data(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """

        self.patch(config, "MaxQueryWithDataResults", 1)
        def _restoreValueError(f):
            self.fail("REPORT must not fail with 403")

        uids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.holidays_dir)) if r[1] == ".ics"]

        d = self.simple_event_query(None, uids, withData=False)
        d.addErrback(_restoreValueError)
        return d


    def simple_event_query(self, event_filter, uids, withData=True):
        props = (
            davxml.GETETag(),
        )
        if withData:
            props += (
                caldavxml.CalendarData(),
            )
        query = caldavxml.CalendarQuery(
            davxml.PropertyContainer(*props),
            caldavxml.Filter(
                caldavxml.ComponentFilter(
                    caldavxml.ComponentFilter(
                        event_filter,
                        name="VEVENT",
                    ),
                    name="VCALENDAR",
                ),
            ),
        )

        def got_xml(doc):
            if not isinstance(doc.root_element, davxml.MultiStatus):
                self.fail("REPORT response XML root element is not multistatus: %r" % (doc.root_element,))

            for response in doc.root_element.childrenOfType(davxml.PropertyStatusResponse):
                for propstat in response.childrenOfType(davxml.PropertyStatus):
                    status = propstat.childOfType(davxml.Status)

                    if status.code != responsecode.OK:
                        self.fail("REPORT failed (status %s) to locate properties: %r"
                                  % (status.code, propstat))

                    properties = propstat.childOfType(davxml.PropertyContainer).children

                    for property in properties:
                        qname = property.qname()
                        if qname == (davxml.dav_namespace, "getetag"):
                            continue
                        if qname != (caldavxml.caldav_namespace, "calendar-data"):
                            self.fail("Response included unexpected property %r" % (property,))

                        result_calendar = property.calendar()

                        if result_calendar is None:
                            self.fail("Invalid response CalDAV:calendar-data: %r" % (property,))

                        uid = result_calendar.resourceUID()

                        if uid in uids:
                            uids.remove(uid)
                        else:
                            self.fail("Got calendar for unexpected UID %r" % (uid,))

                        original_filename = file(os.path.join(self.holidays_dir, uid + ".ics"))
                        original_calendar = ical.Component.fromStream(original_filename)

                        self.assertEqual(result_calendar, original_calendar)

        return self.calendar_query(query, got_xml)


    @inlineCallbacks
    def calendar_query(self, query, got_xml):

        request = SimpleStoreRequest(self, "REPORT", "/calendars/users/wsanchez/calendar/", authid="wsanchez")
        request.stream = MemoryStream(query.toxml())
        response = yield self.send(request)

        response = IResponse(response)

        if response.code != responsecode.MULTI_STATUS:
            self.fail("REPORT failed: %s" % (response.code,))

        returnValue(
            (yield davXMLFromStream(response.stream).addCallback(got_xml))
        )
