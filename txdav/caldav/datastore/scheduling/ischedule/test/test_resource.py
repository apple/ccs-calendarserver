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

from twext.web2 import http_headers, responsecode
from twext.web2.test.test_server import SimpleRequest
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.config import config
from twistedcaldav.memcachelock import MemcacheLock
from txdav.caldav.datastore.scheduling.ischedule.resource import IScheduleInboxResource
from twistedcaldav.test.util import TestCase

class iSchedulePOST (TestCase):

    def setUp(self):
        super(iSchedulePOST, self).setUp()
        self.createStockDirectoryService()
        self.setupCalendars()
        self.site.resource.putChild(
            "ischedule", IScheduleInboxResource(self.site.resource,
                                                self.createDataStore()))


    @inlineCallbacks
    def test_deadlock(self):
        """
        Make calendar
        """

        request = SimpleRequest(
            self.site,
            "POST",
            "/ischedule",
            headers=http_headers.Headers(rawHeaders={
                "Originator": ("mailto:wsanchez@example.com",),
                "Recipient": ("mailto:cdaboo@example.com",),
            }),
            content="""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20060101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:deadlocked
ORGANIZER:mailto:wsanchez@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:wsanchez@example.com
ATTENDEE;RSVP=TRUE;PARTSTAT=NEEDS-ACTION:mailto:cdaboo@example.com
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        )

        # Lock the UID here to force a deadlock - but adjust the timeout so the test does not wait too long
        self.patch(config.Scheduling.Options, "UIDLockTimeoutSeconds", 1)
        lock = MemcacheLock("ImplicitUIDLock", "deadlocked", timeout=60, expire_time=60)
        yield lock.acquire()

        response = (yield self.send(request))
        self.assertEqual(response.code, responsecode.CONFLICT)
