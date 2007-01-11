##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
# DRI: Cyrus Daboo, cdaboo@apple.com
##

import os
import shutil

from twisted.web2 import responsecode
from twisted.web2.iweb import IResponse
from twisted.web2.stream import MemoryStream
from twisted.web2.dav import davxml
from twisted.web2.dav.fileop import rmdir
from twisted.web2.dav.util import davXMLFromStream
from twisted.web2.test.test_server import SimpleRequest

import twistedcaldav.test.util
from twistedcaldav import caldavxml
from twistedcaldav import ical
from twistedcaldav.index import db_basename

class CalendarMultiget (twistedcaldav.test.util.TestCase):
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

        baduids = ["12345@example.com", "67890@example.com"]

        return self.simple_event_multiget("/calendar_multiget_events/", okuids, baduids)

    def test_multiget_all_events(self):
        """
        All events.
        (CalDAV-access-09, section 7.6.8)
        """
        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.holidays_dir)) if r[1] == ".ics"]

        baduids = ["12345@example.com", "67890@example.com"]

        return self.simple_event_multiget("/calendar_multiget_events/", okuids, baduids)

    def simple_event_multiget(self, cal_uri, okuids, baduids):
        children = []
        children.append(davxml.PropertyContainer(
                        davxml.GETETag(),
                        caldavxml.CalendarData()))
        
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
        
            if len(okuids) + len(badhrefs):
                self.fail("Some components were not returned: %r, %r" % (okuids, badhrefs))

        return self.calendar_query(cal_uri, query, got_xml)

    def calendar_query(self, calendar_uri, query, got_xml):
        calendar_path = os.path.join(self.docroot, calendar_uri[1:])

        if os.path.exists(calendar_path): rmdir(calendar_path)

        def do_report(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("MKCALENDAR failed: %s" % (response.code,))

            # Add holiday events to calendar
            # We're cheating by simply copying the files in
            for filename in os.listdir(self.holidays_dir):
                if os.path.splitext(filename)[1] != ".ics": continue
                path = os.path.join(self.holidays_dir, filename)
                shutil.copy(path, calendar_path)

            # Delete the index because we cheated
            index_path = os.path.join(calendar_path, db_basename)
            if os.path.isfile(index_path): os.remove(index_path)

            request = SimpleRequest(self.site, "REPORT", calendar_uri)
            request.stream = MemoryStream(query.toxml())

            def do_test(response):
                response = IResponse(response)

                if response.code != responsecode.MULTI_STATUS:
                    self.fail("REPORT failed: %s" % (response.code,))

                return davXMLFromStream(response.stream).addCallback(got_xml)

            return self.send(request, do_test)

        request = SimpleRequest(self.site, "MKCALENDAR", calendar_uri)

        return self.send(request, do_report)
