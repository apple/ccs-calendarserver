##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

from twisted.web2.iweb import IResponse
from twisted.web2.dav.test.util import SimpleRequest

import twistedcaldav.test.util

class OPTIONS (twistedcaldav.test.util.TestCase):
    """
    OPTIONS request
    """
    def test_dav_header_caldav(self):
        """
        DAV header advertises CalDAV
        """
        def do_test(response):
            response = IResponse(response)

            dav = response.headers.getHeader("dav")
            if not dav: self.fail("no DAV header: %s" % (response.headers,))
            self.assertIn("1", dav, "no DAV level 1 header")
            self.assertIn("calendar-access", dav, "no DAV calendar-access header")

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
            self.assertIn("MKCALENDAR", allow, "no MKCALENDAR support")

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

    test_allow_header_acl.todo = "ACLs are unimplemented."

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
