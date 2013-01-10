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

from twext.web2.iweb import IResponse
from twext.web2.test.test_server import SimpleRequest

import twistedcaldav.test.util
from twistedcaldav.config import config

class OPTIONS (twistedcaldav.test.util.TestCase):
    """
    OPTIONS request
    """
    def test_dav_header_full_caldav(self):
        """
        DAV header advertises CalDAV
        """
        def do_test(response):
            response = IResponse(response)

            dav = response.headers.getHeader("dav")
            if not dav: self.fail("no DAV header: %s" % (response.headers,))
            self.assertIn("1", dav, "no DAV level 1 header")
            self.assertIn("access-control", dav, "no DAV access-control header")
            self.assertIn("calendar-access", dav, "no DAV calendar-access header")
            self.assertIn("calendar-schedule", dav, "no DAV calendar-schedule header")
            self.assertIn("calendar-auto-schedule", dav, "no DAV calendar-auto-schedule header")
            self.assertIn("calendar-availability", dav, "no DAV calendar-availability header")

        config.Scheduling.CalDAV.OldDraftCompatibility = True
        request = SimpleRequest(self.site, "OPTIONS", "/")

        return self.send(request, do_test)

    def test_dav_header_implicit_caldav(self):
        """
        DAV header advertises CalDAV
        """
        def do_test(response):
            response = IResponse(response)

            dav = response.headers.getHeader("dav")
            if not dav: self.fail("no DAV header: %s" % (response.headers,))
            self.assertIn("1", dav, "no DAV level 1 header")
            self.assertIn("access-control", dav, "no DAV access-control header")
            self.assertIn("calendar-access", dav, "no DAV calendar-access header")
            self.assertIn("calendar-auto-schedule", dav, "no DAV calendar-auto-schedule header")
            self.assertIn("calendar-availability", dav, "no DAV calendar-availability header")

        config.Scheduling.CalDAV.OldDraftCompatibility = False
        request = SimpleRequest(self.site, "OPTIONS", "/")

        return self.send(request, do_test)

    def test_allow_header_caldav(self):
        """
        Allow header advertises MKCALENDAR
        """
        def do_test(response):
            response = IResponse(response)

            allow = response.headers.getHeader("allow")
            if not allow: self.fail("no Allow header: %s" % (response.headers,))
            self.assertNotIn("MKCALENDAR", allow, "no MKCALENDAR support")

        request = SimpleRequest(self.site, "OPTIONS", "/")

        return self.send(request, do_test)

    def test_allow_header_acl(self):
        """
        Allow header advertises ACL
        """
        def do_test(response):
            response = IResponse(response)

            allow = response.headers.getHeader("allow")
            if not allow: self.fail("no Allow header: %s" % (response.headers,))
            self.assertIn("ACL", allow, "no ACL support")

        request = SimpleRequest(self.site, "OPTIONS", "/")

        return self.send(request, do_test)

    def test_allow_header_deltav(self):
        """
        Allow header advertises REPORT
        """
        def do_test(response):
            response = IResponse(response)

            allow = response.headers.getHeader("allow")
            if not allow: self.fail("no Allow header: %s" % (response.headers,))
            self.assertIn("REPORT", allow, "no REPORT support")

        request = SimpleRequest(self.site, "OPTIONS", "/")

        return self.send(request, do_test)

    def test_dav_header_caldav_disabled(self):
        """
        DAV header does not advertise CalDAV
        """
        def do_test(response):
            response = IResponse(response)

            dav = response.headers.getHeader("dav")
            if not dav: self.fail("no DAV header: %s" % (response.headers,))
            self.assertIn("1", dav, "no DAV level 1 header")
            self.assertNotIn("calendar-access", dav, "DAV calendar-access header")
        self.patch(config, "EnableCalDAV", False)
        request = SimpleRequest(self.site, "OPTIONS", "/")

        return self.send(request, do_test)

    def test_dav_header_carddav_disabled(self):
        """
        DAV header does not advertise CardDAV
        """
        def do_test(response):
            response = IResponse(response)

            dav = response.headers.getHeader("dav")
            if not dav: self.fail("no DAV header: %s" % (response.headers,))
            self.assertIn("1", dav, "no DAV level 1 header")
            self.assertNotIn("addressbook", dav, "DAV addressbook header")

        self.patch(config, "EnableCardDAV", False)
        request = SimpleRequest(self.site, "OPTIONS", "/")

        return self.send(request, do_test)

