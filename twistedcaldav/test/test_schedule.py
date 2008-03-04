##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

from twisted.web2 import responsecode
from twisted.web2.iweb import IResponse
from twisted.web2.dav import davxml
from twisted.web2.dav.util import davXMLFromStream
from twisted.web2.stream import MemoryStream
from twisted.web2.test.test_server import SimpleRequest

from twistedcaldav import caldavxml
from twistedcaldav.static import ScheduleInboxFile

import twistedcaldav.test.util

class Properties (twistedcaldav.test.util.TestCase):
    """
    CalDAV properties
    """
    def test_missing_free_busy_set_prop(self):
        """
        Test for PROPFIND on Inbox with missing calendar-free-busy-set property.
        """

        inbox_uri  = "/inbox/"
        inbox_path = os.path.join(self.docroot, "inbox")
        self.site.resource.putChild("inbox", ScheduleInboxFile(inbox_path, self.site.resource))

        def propfind_cb(response):
            response = IResponse(response)

            if response.code != responsecode.MULTI_STATUS:
                self.fail("Incorrect response to PROPFIND: %s" % (response.code,))

            def got_xml(doc):
                if not isinstance(doc.root_element, davxml.MultiStatus):
                    self.fail("PROPFIND response XML root element is not multistatus: %r" % (doc.root_element,))

                response = doc.root_element.childOfType(davxml.Response)
                href = response.childOfType(davxml.HRef)
                self.failUnless(str(href) == inbox_uri)

                for propstat in response.childrenOfType(davxml.PropertyStatus):
                    status = propstat.childOfType(davxml.Status)
                    if status.code != responsecode.OK:
                        self.fail("Unable to read requested properties (%s): %r"
                                  % (status, propstat.childOfType(davxml.PropertyContainer).toxml()))

                container = propstat.childOfType(davxml.PropertyContainer)

                #
                # Check CalDAV:calendar-free-busy-set
                #

                free_busy_set = container.childOfType(caldavxml.CalendarFreeBusySet)
                if not free_busy_set:
                    self.fail("Expected CalDAV:calendar-free-busy-set element; but got none.")

                if free_busy_set.children:
                    self.fail("Expected empty CalDAV:calendar-free-busy-set element; but got %s." % (free_busy_set.children,))

            return davXMLFromStream(response.stream).addCallback(got_xml)

        query = davxml.PropertyFind(
                    davxml.PropertyContainer(
                        davxml.GETETag(),
                        caldavxml.CalendarFreeBusySet(),
                    ),
                )

        request = SimpleRequest(self.site, "PROPFIND", inbox_uri)
        request.stream = MemoryStream(query.toxml())
        return self.send(request, propfind_cb)
