# Copyright (c) 2006-2012 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.python.filepath import CachingFilePath as FilePath
from twext.web2 import responsecode
from twext.web2.iweb import IResponse
from twext.web2.stream import MemoryStream
from txdav.xml import element as davxml
from twext.web2.dav.util import davXMLFromStream
from twext.web2.test.test_server import SimpleRequest

from twistedcaldav import caldavxml
from twistedcaldav import ical
from twistedcaldav.test.util import HomeTestCase, todo
from twistedcaldav.config import config

class CalendarMultiget (HomeTestCase):
    """
    calendar-multiget REPORT
    """
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    holidays_dir = os.path.join(data_dir, "Holidays")

    def test_multiget_some_events(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """
        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.holidays_dir)) if r[1] == ".ics"]
        okuids[:] = okuids[1:10]

        baduids = ["12345%40example.com", "67890%40example.com"]

        return self.simple_event_multiget("/calendar_multiget_events/", okuids, baduids)

    def test_multiget_all_events(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """
        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.holidays_dir)) if r[1] == ".ics"]

        baduids = ["12345%40example.com", "67890%40example.com"]

        return self.simple_event_multiget("/calendar_multiget_events/", okuids, baduids)

    def test_multiget_limited_with_data(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """
        oldValue = config.MaxMultigetWithDataHrefs
        config.MaxMultigetWithDataHrefs = 1
        def _restoreValueOK(f):
            config.MaxMultigetWithDataHrefs = oldValue
            self.fail("REPORT must fail with 403")

        def _restoreValueError(f):
            config.MaxMultigetWithDataHrefs = oldValue
            return None

        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.holidays_dir)) if r[1] == ".ics"]

        baduids = ["12345%40example.com", "67890%40example.com"]

        d = self.simple_event_multiget("/calendar_multiget_events/", okuids, baduids)
        d.addCallbacks(_restoreValueOK, _restoreValueError)
        return d

    def test_multiget_limited_no_data(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """
        oldValue = config.MaxMultigetWithDataHrefs
        config.MaxMultigetWithDataHrefs = 1
        def _restoreValueOK(f):
            config.MaxMultigetWithDataHrefs = oldValue
            return None

        def _restoreValueError(f):
            config.MaxMultigetWithDataHrefs = oldValue
            self.fail("REPORT must not fail with 403")

        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.holidays_dir)) if r[1] == ".ics"]

        baduids = ["12345%40example.com", "67890%40example.com"]

        return self.simple_event_multiget("/calendar_multiget_events/", okuids, baduids, withData=False)

    @todo("Remove: Does not work with new store")
    @inlineCallbacks
    def test_multiget_one_broken_event(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """
        okuids = ["good", "bad",]
        baduids = []
        data = {
            "good":"""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Apple Computer\, Inc//iCal 2.0//EN
VERSION:2.0
BEGIN:VEVENT
UID:good
DTSTART;VALUE=DATE:20020101
DTEND;VALUE=DATE:20020102
DTSTAMP:20020101T121212Z
RRULE:FREQ=YEARLY;INTERVAL=1;UNTIL=20031231;BYMONTH=1
SUMMARY:New Year's Day
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"),
            "bad":"""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Apple Computer\, Inc//iCal 2.0//EN
VERSION:2.0
BEGIN:VEVENT
UID:bad
DTSTART;VALUE=DATE:20020214
DTEND;VALUE=DATE:20020215
DTSTAMP:20020101T121212Z
RRULE:FREQ=YEARLY;INTERVAL=1;BYMONTH=2
SUMMARY:Valentine's Day
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        }

        yield self.simple_event_multiget("/calendar_multiget_events/", okuids, baduids, data)
        
        # Now forcibly corrupt one piece of calendar data
        calendar_path = os.path.join(self.docroot, "calendar_multiget_events/", "bad.ics")
        f = open(calendar_path, "w")
        f.write("""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Apple Computer\, Inc//iCal 2.0//EN
VERSION:2.0
BEGIN:VEVENT
UID:bad
DTSTART;VALUE=DATE:20020214
DTEND;VALUE=DATE:20020
DTSTAMP:20020101T121212Z
END:VCALENDAR
""".replace("\n", "\r\n"))
        f.close

        okuids = ["good", ]
        baduids = ["bad", ]
        yield self.simple_event_multiget("/calendar_multiget_events/", okuids, baduids, data, no_init=True)

    def simple_event_multiget(self, cal_uri, okuids, baduids, data=None, no_init=False, withData=True):
        props = (
            davxml.GETETag(),
        )
        if withData:
            props += (
                caldavxml.CalendarData(),
            )
        children = []
        children.append(davxml.PropertyContainer(*props))
        
        okhrefs = [cal_uri + x + ".ics" for x in okuids]
        badhrefs = [cal_uri + x + ".ics" for x in baduids]
        for href in okhrefs + badhrefs:
            children.append(davxml.HRef.fromString(href))
        
        query = caldavxml.CalendarMultiGet(*children)
        
        def got_xml(doc):
            if not isinstance(doc.root_element, davxml.MultiStatus):
                self.fail("REPORT response XML root element is not multistatus: %r" % (doc.root_element,))

            for response in doc.root_element.childrenOfType(davxml.PropertyStatusResponse):
                href = str(response.childOfType(davxml.HRef))
                for propstat in response.childrenOfType(davxml.PropertyStatus):
                    status = propstat.childOfType(davxml.Status)

                    if status.code != responsecode.OK:
                        self.fail("REPORT failed (status %s) to locate properties: %r"
                              % (status.code, href))

                    properties = propstat.childOfType(davxml.PropertyContainer).children

                    for property in properties:
                        qname = property.qname()
                        if qname == (davxml.dav_namespace, "getetag"): continue
                        if qname != (caldavxml.caldav_namespace, "calendar-data"):
                            self.fail("Response included unexpected property %r" % (property,))

                        result_calendar = property.calendar()

                        if result_calendar is None:
                            self.fail("Invalid response CalDAV:calendar-data: %r" % (property,))

                        uid = result_calendar.resourceUID()

                        if uid in okuids:
                            okuids.remove(uid)
                        else:
                            self.fail("Got calendar for unexpected UID %r" % (uid,))

                        if data:
                            original_calendar = ical.Component.fromString(data[uid])
                        else:
                            original_filename = file(os.path.join(self.holidays_dir, uid + ".ics"))
                            original_calendar = ical.Component.fromStream(original_filename)

                        self.assertEqual(result_calendar, original_calendar)
            
            for response in doc.root_element.childrenOfType(davxml.StatusResponse):
                href = str(response.childOfType(davxml.HRef))
                propstatus = response.childOfType(davxml.PropertyStatus)
                if propstatus is not None:
                    status = propstatus.childOfType(davxml.Status)
                else:
                    status = response.childOfType(davxml.Status)
                if status.code != responsecode.OK:
                    if href in okhrefs:
                        self.fail("REPORT failed (status %s) to locate properties: %r"
                              % (status.code, href))
                    else:
                        if href in badhrefs:
                            badhrefs.remove(href)
                            continue
                        else:
                            self.fail("Got unexpected href %r" % (href,))
        
            if withData and (len(okuids) + len(badhrefs)):
                self.fail("Some components were not returned: %r, %r" % (okuids, badhrefs))

        return self.calendar_query(cal_uri, query, got_xml, data, no_init)

    @inlineCallbacks
    def calendar_query(self, calendar_uri, query, got_xml, data, no_init):

        if not no_init:
            response = yield self.send(SimpleRequest(self.site, "MKCALENDAR",
                calendar_uri))
            response = IResponse(response)
            if response.code != responsecode.CREATED:
                self.fail("MKCALENDAR failed: %s" % (response.code,))

            if data:
                for filename, icaldata in data.iteritems():
                    request = SimpleRequest(self.site, "PUT",
                        calendar_uri + "/" + filename + ".ics")
                    request.stream = MemoryStream(icaldata)
                    yield self.send(request)
            else:
                # Add holiday events to calendar
                for child in FilePath(self.holidays_dir).children():
                    if os.path.splitext(child.basename())[1] != ".ics": continue
                    request = SimpleRequest(self.site, "PUT",
                        calendar_uri + "/" + child.basename())
                    request.stream = MemoryStream(child.getContent())
                    yield self.send(request)

        request = SimpleRequest(self.site, "REPORT", calendar_uri)
        request.stream = MemoryStream(query.toxml())
        response = yield self.send(request)

        response = IResponse(response)

        if response.code != responsecode.MULTI_STATUS:
            self.fail("REPORT failed: %s" % (response.code,))

        returnValue(
            (yield davXMLFromStream(response.stream).addCallback(got_xml))
        )
