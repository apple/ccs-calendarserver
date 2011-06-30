##
# Copyright (c) 2009 Apple Inc. All rights reserved.
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

from xml.etree.cElementTree import XML

from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

# XXX this should be public, but it isn't, since it's in a test_* module.  Need
# to address this to use system twisted.
from twext.web2.test.test_server import SimpleRequest
from twext.web2.http import HTTPError

from twistedcaldav.config import config
from twistedcaldav.ical import Component, Property
from twistedcaldav.method.put_common import StoreCalendarObjectResource
from twistedcaldav.caldavxml import MaxAttendeesPerInstance
from twistedcaldav.resource import CalDAVResource

class TestCopyMoveValidation(TestCase):
    """
    Tests for the validation code in L{twistedcaldav.method.put_common}.
    """

    def setUp(self):
        """
        Set up some CalDAV stuff.
        """

        self.destination = CalDAVResource()
        self.destination.name = lambda : '1'
        self.destinationParent = CalDAVResource()
        self.destinationParent.name = lambda : '2'

    def _getSampleCalendar(self):
        return Component.fromString("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Computer\, Inc//iCal 2.0//EN
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20071114T000000Z
DTSTART:20071114T000000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
RRULE:FREQ=YEARLY
END:VEVENT
END:VCALENDAR
""")

    def _getStorer(self, calendar):
        self.sampleCalendar = calendar
        req = SimpleRequest(None, "COPY", "http://example.com/foo/bar")
        self.storer = StoreCalendarObjectResource(
            req,
            destination=self.destination,
            destinationparent=self.destinationParent,
            destination_uri="http://example.com/foo/baz",
            calendar=self.sampleCalendar
        )
        return self.storer
                
    @inlineCallbacks
    def test_simpleValidRequest(self):
        """
        For a simple valid request,
        L{StoreCalendarObjectResource.fullValidation} results in a L{Deferred}
        which fires with C{None} (and raises no exception).
        """
        self.assertEquals((yield self._getStorer(self._getSampleCalendar()).fullValidation()), None)


    @inlineCallbacks
    def test_exceedMaximumAttendees(self):
        """
        If too many attendees are specified (more than the configured maximum
        for the server), the storer raises an exception containing a
        L{MaxAttendeesPerInstance} element that reports the maximum value, as
        per U{RFC4791 section 5.2.9
        <http://www.webdav.org/specs/rfc4791.html#max-attendees-per-instance>}.
        """

        # Get the event, and add too many attendees to it.
        self.sampleCalendar = self._getSampleCalendar()
        eventComponent = list(self.sampleCalendar.subcomponents())[0]
        for x in xrange(config.MaxAttendeesPerInstance):
            eventComponent.addProperty(
                Property("ATTENDEE", "mailto:user%d@example.com" % (x+3,)))

        try:
            yield self._getStorer(self.sampleCalendar).fullValidation()
        except HTTPError, err:
            element = XML(err.response.stream.mem)[0]
            self.assertEquals(
                element.tag,
                "{%s}%s" % (
                    MaxAttendeesPerInstance.namespace,
                    MaxAttendeesPerInstance.name
                )
            )
            self.assertEquals(int(element.text), config.MaxAttendeesPerInstance)
        else:
            self.fail("No error; validation should have failed!")
