##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

"""
Tests for txdav.caldav.datastore.util.
"""

from twext.web2.http_headers import MimeType

from twisted.internet.defer import inlineCallbacks

from twistedcaldav.ical import Component
from twistedcaldav.test.util import TestCase

from txdav.caldav.datastore.util import dropboxIDFromCalendarObject,\
    StorageTransportBase

class DropboxIDTests(TestCase):
    """
    Test dropbox ID extraction from calendar data.
    """

    class FakeCalendarResource(object):
        """
        Fake object resource to work with tests.
        """

        def __init__(self, data):

            self.ical = Component.fromString(data)

        def component(self):
            return self.ical

        def uid(self):
            return self.ical.resourceUID()


    @inlineCallbacks
    def test_noAttachOrXdash(self):
        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890.dropbox"
        )


    @inlineCallbacks
    def test_okXdash(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
X-APPLE-DROPBOX:http://example.com/calendars/__uids__/1234/dropbox/12345-67890X.dropbox
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890X.dropbox"
        )


    @inlineCallbacks
    def test_badXdash(self):
        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
X-APPLE-DROPBOX:
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals( (yield dropboxIDFromCalendarObject(resource)), "")


    @inlineCallbacks
    def test_okAttach(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH;VALUE=URI:http://example.com/calendars/__uids__/1234/dropbox/12345-67890Y.dropbox/text.txt
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890Y.dropbox"
        )


    @inlineCallbacks
    def test_badAttach(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH;VALUE=URI:tag:bogus
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890.dropbox"
        )


    @inlineCallbacks
    def test_inlineAttach(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH:bmFzZTY0
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890.dropbox"
        )


    @inlineCallbacks
    def test_multipleAttach(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH;VALUE=URI:tag:bogus
ATTACH:bmFzZTY0
ATTACH;VALUE=URI:http://example.com/calendars/__uids__/1234/dropbox/12345-67890Z.dropbox/text.txt
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890Z.dropbox"
        )


    @inlineCallbacks
    def test_okAttachRecurring(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
BEGIN:VEVENT
UID:12345-67890
RECURRENCE-ID:20081114T000000Z
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
ATTACH;VALUE=URI:http://example.com/calendars/__uids__/1234/dropbox/12345-67890Y.dropbox/text.txt
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)),
            "12345-67890Y.dropbox"
        )


    @inlineCallbacks
    def test_okAttachAlarm(self):

        resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:12345-67890
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
BEGIN:VALARM
ACTION:AUDIO
ATTACH;VALUE=URI:Ping
TRIGGER:-PT15M
X-WR-ALARMUID:5548D654-8FDA-49DB-8983-8FCAD1F322B1
END:VALARM
END:VEVENT
END:VCALENDAR
""")

        self.assertEquals(
            (yield dropboxIDFromCalendarObject(resource)), 
            "12345-67890.dropbox"
        )


    @inlineCallbacks
    def test_UIDbadPath(self):
        
        test_UIDs = (
            ("12345/67890", "12345-67890"),
            ("http://12345,67890", "12345,67890"),
            ("https://12345,67890", "12345,67890"),
            ("12345:67890", "1234567890"),
            ("12345.67890", "1234567890"),
            ("12345/6:7.890", "12345-67890"),
        )

        for uid, result in test_UIDs:
            resource = DropboxIDTests.FakeCalendarResource("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:%s
DTSTART:20071114T000000Z
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
""" % (uid,))
    
            self.assertEquals(
                (yield dropboxIDFromCalendarObject(resource)),
                "%s.dropbox" % (result,),
            )

class StorageTransportTests(TestCase):

    def test_MissingContentType(self):
        
        test_files = (
            ("plain.txt", MimeType.fromString("text/plain"),),
            ("word.doc", MimeType.fromString("application/msword"),),
            ("markup.xml", MimeType.fromString("application/xml"),),
            ("octet", MimeType.fromString("application/octet-stream"),),
            ("bogus.bog", MimeType.fromString("application/octet-stream"),),
        )

        class FakeAttachment(object):
            
            def __init__(self, name):
                self._name = name
            
            def name(self):
                return self._name
    
        for filename, result in test_files:
            item = StorageTransportBase(FakeAttachment(filename), None)
            self.assertEquals(item._contentType, result)
            item = StorageTransportBase(FakeAttachment(filename), result)
            self.assertEquals(item._contentType, result)
