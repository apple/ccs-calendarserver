##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
from calendarserver.logAnalysis import getAdjustedMethodName, \
    getAdjustedClientName

class LogAnalysis(TestCase):

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
            extras["method"] = method
            extras["uri"] = uri
            self.assertEqual(getAdjustedMethodName(extras), result, "Failed getAdjustedMethodName: %s" % (result,))


    def test_getAdjustedClientName(self):
        """
        L{getAdjustedClientName} returns the appropriate method.
        """

        data = (
            ("Mac OS X/10.8.2 (12C60) CalendarAgent/55", "Mac OS X/10.8.2 CalendarAgent",),
            ("CalendarStore/5.0.3 (1204.2); iCal/5.0.3 (1605.4); Mac OS X/10.7.5 (11G63b)", "Mac OS X/10.7.5 iCal",),
            ("DAVKit/5.0 (767); iCalendar/5.0 (79); iPhone/4.2.1 8C148", "iPhone/4.2.1",),
            ("iOS/6.0 (10A405) Preferences/1.0", "iOS/6.0 Preferences",),
            ("iOS/6.0.1 (10A523) dataaccessd/1.0", "iOS/6.0.1 dataaccessd",),
            ("InterMapper/5.4.3", "InterMapper",),
            ("Mac OS X/10.8.2 (12C60) AddressBook/1167", "Mac OS X/10.8.2 AddressBook",),
        )

        for ua, result in data:
            self.assertEqual(getAdjustedClientName({"userAgent": ua}), result, "Failed getAdjustedClientName: %s" % (ua,))
