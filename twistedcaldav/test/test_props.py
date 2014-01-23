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

from txweb2 import responsecode, http_headers
from txweb2.dav.util import davXMLFromStream
from txweb2.iweb import IResponse
from txweb2.stream import MemoryStream

from twistedcaldav import caldavxml
from twistedcaldav.test.util import StoreTestCase, SimpleStoreRequest

from txdav.xml import element as davxml

class Properties(StoreTestCase):
    """
    CalDAV properties
    """
    def test_live_props(self):
        """
        Live CalDAV properties
        """
        calendar_uri = "/calendars/users/user01/test/"

        def mkcalendar_cb(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("MKCALENDAR failed: %s" % (response.code,))

            def propfind_cb(response):
                response = IResponse(response)

                if response.code != responsecode.MULTI_STATUS:
                    self.fail("Incorrect response to PROPFIND: %s" % (response.code,))

                def got_xml(doc):
                    if not isinstance(doc.root_element, davxml.MultiStatus):
                        self.fail("PROPFIND response XML root element is not multistatus: %r" % (doc.root_element,))

                    response = doc.root_element.childOfType(davxml.Response)
                    href = response.childOfType(davxml.HRef)
                    self.failUnless(str(href) == calendar_uri)

                    for propstat in response.childrenOfType(davxml.PropertyStatus):
                        status = propstat.childOfType(davxml.Status)
                        if status.code != responsecode.OK:
                            self.fail("Unable to read requested properties (%s): %r"
                                      % (status, propstat.childOfType(davxml.PropertyContainer).toxml()))

                    container = propstat.childOfType(davxml.PropertyContainer)

                    #
                    # Check CalDAV:supported-calendar-component-set
                    #

                    supported_components = container.childOfType(caldavxml.SupportedCalendarComponentSet)
                    if not supported_components:
                        self.fail("Expected CalDAV:supported-calendar-component-set element; but got none.")

                    supported = set(("VEVENT",))

                    for component in supported_components.children:
                        if component.type in supported:
                            supported.remove(component.type)

                    if supported:
                        self.fail("Expected supported calendar component types: %s" % (tuple(supported),))

                    #
                    # Check CalDAV:supported-calendar-data
                    #

                    supported_calendar = container.childOfType(caldavxml.SupportedCalendarData)
                    if not supported_calendar:
                        self.fail("Expected CalDAV:supported-calendar-data element; but got none.")

                    for calendar in supported_calendar.children:
                        if calendar.content_type not in ("text/calendar", "application/calendar+json"):
                            self.fail("Expected a text/calendar calendar-data type restriction")
                        if calendar.version != "2.0":
                            self.fail("Expected a version 2.0 calendar-data restriction")

                    #
                    # Check DAV:supported-report-set
                    #

                    supported_reports = container.childOfType(davxml.SupportedReportSet)
                    if not supported_reports:
                        self.fail("Expected DAV:supported-report-set element; but got none.")

                    cal_query = False
                    cal_multiget = False
                    cal_freebusy = False
                    for supported in supported_reports.childrenOfType(davxml.SupportedReport):
                        report = supported.childOfType(davxml.Report)
                        if report.childOfType(caldavxml.CalendarQuery) is not None:
                            cal_query = True
                        if report.childOfType(caldavxml.CalendarMultiGet) is not None:
                            cal_multiget = True
                        if report.childOfType(caldavxml.FreeBusyQuery) is not None:
                            cal_freebusy = True

                    if not cal_query:
                        self.fail("Expected CalDAV:CalendarQuery element; but got none.")
                    if not cal_multiget:
                        self.fail("Expected CalDAV:CalendarMultiGet element; but got none.")
                    if not cal_freebusy:
                        self.fail("Expected CalDAV:FreeBusyQuery element; but got none.")

                return davXMLFromStream(response.stream).addCallback(got_xml)

            query = davxml.PropertyFind(
                        davxml.PropertyContainer(
                            caldavxml.SupportedCalendarData(),
                            caldavxml.SupportedCalendarComponentSet(),
                            davxml.SupportedReportSet(),
                        ),
                    )

            request = SimpleStoreRequest(
                self,
                "PROPFIND",
                calendar_uri,
                headers=http_headers.Headers({"Depth": "0"}),
                authid="user01",
            )
            request.stream = MemoryStream(query.toxml())
            return self.send(request, propfind_cb)

        request = SimpleStoreRequest(self, "MKCALENDAR", calendar_uri, authid="user01")
        return self.send(request, mkcalendar_cb)


    def test_all_props(self):
        """
        Live CalDAV properties
        """
        calendar_uri = "/calendars/users/user01/test/"

        def mkcalendar_cb(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("MKCALENDAR failed: %s" % (response.code,))

            def propfind_cb(response):
                response = IResponse(response)

                if response.code != responsecode.MULTI_STATUS:
                    self.fail("Incorrect response to PROPFIND: %s" % (response.code,))

                def got_xml(doc):
                    if not isinstance(doc.root_element, davxml.MultiStatus):
                        self.fail("PROPFIND response XML root element is not multistatus: %r" % (doc.root_element,))

                    response = doc.root_element.childOfType(davxml.Response)
                    href = response.childOfType(davxml.HRef)
                    self.failUnless(str(href) == calendar_uri)

                    container = response.childOfType(davxml.PropertyStatus).childOfType(davxml.PropertyContainer)

                    #
                    # Check CalDAV:supported-calendar-component-set
                    #

                    supported_components = container.childOfType(caldavxml.SupportedCalendarComponentSet)
                    if supported_components:
                        self.fail("CalDAV:supported-calendar-component-set element was returned; but should be hidden.")

                    #
                    # Check CalDAV:supported-calendar-data
                    #

                    supported_calendar = container.childOfType(caldavxml.SupportedCalendarData)
                    if supported_calendar:
                        self.fail("CalDAV:supported-calendar-data elementwas returned; but should be hidden.")

                    #
                    # Check DAV:supported-report-set
                    #

                    supported_reports = container.childOfType(davxml.SupportedReportSet)
                    if supported_reports:
                        self.fail("DAV:supported-report-set element was returned; but should be hidden..")

                return davXMLFromStream(response.stream).addCallback(got_xml)

            query = davxml.PropertyFind(
                davxml.AllProperties(),
            )

            request = SimpleStoreRequest(
                self,
                "PROPFIND",
                calendar_uri,
                headers=http_headers.Headers({"Depth": "0"}),
                authid="user01",
            )
            request.stream = MemoryStream(query.toxml())
            return self.send(request, propfind_cb)

        request = SimpleStoreRequest(self, "MKCALENDAR", calendar_uri, authid="user01")
        return self.send(request, mkcalendar_cb)
