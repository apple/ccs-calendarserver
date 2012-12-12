##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

from twisted.trial.unittest import TestCase
from calendarserver.methodDescriptor import getAdjustedMethodName

class MethodDescriptor(TestCase):
    """
    Tests for L{getAdjustedMethodName}.
    """
    def test_getAdjustedMethodName(self):
        """
        L{getAdjustedMethodName} returns the appropriate method.
        """

        data = (
            ("PROPFIND", "/calendars/users/user01/", {}, "PROPFIND Calendar Home",),
            ("PROPFIND", "/calendars/users/user01/", {"cached": "1"}, "PROPFIND cached Calendar Home",),
            ("PROPFIND", "/calendars/users/user01/ABC/", {}, "PROPFIND Calendar",),
            ("PROPFIND", "/calendars/users/user01/inbox/", {}, "PROPFIND Inbox",),
            ("PROPFIND", "/addressbooks/users/user01/", {}, "PROPFIND Adbk Home",),
            ("PROPFIND", "/addressbooks/users/user01/", {"cached": "1"}, "PROPFIND cached Adbk Home",),
            ("PROPFIND", "/addressbooks/users/user01/ABC/", {}, "PROPFIND Adbk",),
            ("PROPFIND", "/addressbooks/users/user01/inbox/", {}, "PROPFIND Adbk",),
            ("PROPFIND", "/principals/users/user01/", {}, "PROPFIND Principals",),
            ("PROPFIND", "/principals/users/user01/", {"cached": "1"}, "PROPFIND cached Principals",),
            ("PROPFIND", "/.well-known/caldav", {}, "PROPFIND",),

            ("REPORT(CalDAV:sync-collection)", "/calendars/users/user01/ABC/", {}, "REPORT cal-sync",),
            ("REPORT(CalDAV:calendar-query)", "/calendars/users/user01/ABC/", {}, "REPORT cal-query",),

            ("POST", "/calendars/users/user01/", {}, "POST Calendar Home",),
            ("POST", "/calendars/users/user01/outbox/", {"recipients": "1"}, "POST Freebusy",),
            ("POST", "/calendars/users/user01/outbox/", {}, "POST Outbox",),
            ("POST", "/apns", {}, "POST apns",),

            ("PUT", "/calendars/users/user01/calendar/1.ics", {}, "PUT ics",),
            ("PUT", "/calendars/users/user01/calendar/1.ics", {"itip.requests": "1"}, "PUT Organizer",),
            ("PUT", "/calendars/users/user01/calendar/1.ics", {"itip.reply": "1"}, "PUT Attendee",),

            ("GET", "/calendars/users/user01/", {}, "GET Calendar Home",),
            ("GET", "/calendars/users/user01/calendar/", {}, "GET Calendar",),
            ("GET", "/calendars/users/user01/calendar/1.ics", {}, "GET ics",),

            ("DELETE", "/calendars/users/user01/", {}, "DELETE Calendar Home",),
            ("DELETE", "/calendars/users/user01/calendar/", {}, "DELETE Calendar",),
            ("DELETE", "/calendars/users/user01/calendar/1.ics", {}, "DELETE ics",),
            ("DELETE", "/calendars/users/user01/inbox/1.ics", {}, "DELETE inbox ics",),

            ("ACL", "/calendars/users/user01/", {}, "ACL",),
        )

        for method, uri, extras, result in data:
            self.assertEqual(getAdjustedMethodName(method, uri, extras), result, "Failed getAdjustedMethodName: %s" % (result,))
