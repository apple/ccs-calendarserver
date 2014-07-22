##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
##

from caldavclientlibrary.protocol.caldav.definitions import caldavxml
from caldavclientlibrary.protocol.caldav.definitions import csxml
from caldavclientlibrary.protocol.url import URL
from caldavclientlibrary.protocol.webdav.definitions import davxml

from contrib.performance.httpclient import MemoryConsumer, StringProducer
from contrib.performance.loadtest.ical import XMPPPush, Event, Calendar, OS_X_10_6
from contrib.performance.loadtest.sim import _DirectoryRecord

from pycalendar.datetime import DateTime
from pycalendar.timezone import Timezone

from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.internet.protocol import ProtocolToConsumerAdapter
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase
from twisted.web.client import ResponseDone
from twisted.web.http import OK, NO_CONTENT, CREATED, MULTI_STATUS
from twisted.web.http_headers import Headers

from twistedcaldav.ical import Component
from twistedcaldav.timezones import TimezoneCache

import os

EVENT_UID = 'D94F247D-7433-43AF-B84B-ADD684D023B0'

EVENT = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.3//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
CREATED:20101018T155454Z
UID:%(UID)s
DTEND;TZID=America/New_York:20101028T130000
ATTENDEE;CN="User 03";CUTYPE=INDIVIDUAL;EMAIL="user03@example.com";PARTS
 TAT=NEEDS-ACTION;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:user03@example.co
 m
ATTENDEE;CN="User 01";CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:user01@
 example.com
TRANSP:OPAQUE
SUMMARY:Attended Event
DTSTART;TZID=America/New_York:20101028T120000
DTSTAMP:20101018T155513Z
ORGANIZER;CN="User 01":mailto:user01@example.com
SEQUENCE:3
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {'UID': EVENT_UID}

EVENT_INVITE = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.3//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:America/New_York
X-LIC-LOCATION:America/New_York
BEGIN:STANDARD
DTSTART:18831118T120358
RDATE:18831118T120358
TZNAME:EST
TZOFFSETFROM:-045602
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19180331T020000
RRULE:FREQ=YEARLY;UNTIL=19190330T070000Z;BYDAY=-1SU;BYMONTH=3
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19181027T020000
RRULE:FREQ=YEARLY;UNTIL=19191026T060000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:STANDARD
DTSTART:19200101T000000
RDATE:19200101T000000
RDATE:19420101T000000
RDATE:19460101T000000
RDATE:19670101T000000
TZNAME:EST
TZOFFSETFROM:-0500
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19200328T020000
RDATE:19200328T020000
RDATE:19740106T020000
RDATE:19750223T020000
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19201031T020000
RDATE:19201031T020000
RDATE:19450930T020000
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19210424T020000
RRULE:FREQ=YEARLY;UNTIL=19410427T070000Z;BYDAY=-1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19210925T020000
RRULE:FREQ=YEARLY;UNTIL=19410928T060000Z;BYDAY=-1SU;BYMONTH=9
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19420209T020000
RDATE:19420209T020000
TZNAME:EWT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:19450814T190000
RDATE:19450814T190000
TZNAME:EPT
TZOFFSETFROM:-0400
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:19460428T020000
RRULE:FREQ=YEARLY;UNTIL=19660424T070000Z;BYDAY=-1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19460929T020000
RRULE:FREQ=YEARLY;UNTIL=19540926T060000Z;BYDAY=-1SU;BYMONTH=9
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:STANDARD
DTSTART:19551030T020000
RRULE:FREQ=YEARLY;UNTIL=19661030T060000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19670430T020000
RRULE:FREQ=YEARLY;UNTIL=19730429T070000Z;BYDAY=-1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19671029T020000
RRULE:FREQ=YEARLY;UNTIL=20061029T060000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19760425T020000
RRULE:FREQ=YEARLY;UNTIL=19860427T070000Z;BYDAY=-1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:19870405T020000
RRULE:FREQ=YEARLY;UNTIL=20060402T070000Z;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20101018T155454Z
UID:%(UID)s
DTEND;TZID=America/New_York:20101028T130000
ATTENDEE;CN="User 02";CUTYPE=INDIVIDUAL;EMAIL="user02@example.com";PARTS
 TAT=NEEDS-ACTION;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:user02@example.co
 m
ATTENDEE;CN="User 03";CUTYPE=INDIVIDUAL;EMAIL="user03@example.com";PARTS
 TAT=NEEDS-ACTION;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:user03@example.co
 m
ATTENDEE;CN="User 01";CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:user01
TRANSP:OPAQUE
SUMMARY:Attended Event
DTSTART;TZID=America/New_York:20101028T120000
DTSTAMP:20101018T155513Z
ORGANIZER;CN="User 01":urn:uuid:user01
SEQUENCE:3
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {'UID': EVENT_UID}

EVENT_AND_TIMEZONE = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.3//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:America/New_York
X-LIC-LOCATION:America/New_York
BEGIN:STANDARD
DTSTART:18831118T120358
RDATE:18831118T120358
TZNAME:EST
TZOFFSETFROM:-045602
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19180331T020000
RRULE:FREQ=YEARLY;UNTIL=19190330T070000Z;BYDAY=-1SU;BYMONTH=3
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19181027T020000
RRULE:FREQ=YEARLY;UNTIL=19191026T060000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:STANDARD
DTSTART:19200101T000000
RDATE:19200101T000000
RDATE:19420101T000000
RDATE:19460101T000000
RDATE:19670101T000000
TZNAME:EST
TZOFFSETFROM:-0500
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19200328T020000
RDATE:19200328T020000
RDATE:19740106T020000
RDATE:19750223T020000
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19201031T020000
RDATE:19201031T020000
RDATE:19450930T020000
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19210424T020000
RRULE:FREQ=YEARLY;UNTIL=19410427T070000Z;BYDAY=-1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19210925T020000
RRULE:FREQ=YEARLY;UNTIL=19410928T060000Z;BYDAY=-1SU;BYMONTH=9
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19420209T020000
RDATE:19420209T020000
TZNAME:EWT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:19450814T190000
RDATE:19450814T190000
TZNAME:EPT
TZOFFSETFROM:-0400
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:19460428T020000
RRULE:FREQ=YEARLY;UNTIL=19660424T070000Z;BYDAY=-1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19460929T020000
RRULE:FREQ=YEARLY;UNTIL=19540926T060000Z;BYDAY=-1SU;BYMONTH=9
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:STANDARD
DTSTART:19551030T020000
RRULE:FREQ=YEARLY;UNTIL=19661030T060000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19670430T020000
RRULE:FREQ=YEARLY;UNTIL=19730429T070000Z;BYDAY=-1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19671029T020000
RRULE:FREQ=YEARLY;UNTIL=20061029T060000Z;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19760425T020000
RRULE:FREQ=YEARLY;UNTIL=19860427T070000Z;BYDAY=-1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:19870405T020000
RRULE:FREQ=YEARLY;UNTIL=20060402T070000Z;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20101018T155454Z
UID:%(UID)s
DTEND;TZID=America/New_York:20101028T130000
ATTENDEE;CN="User 03";CUTYPE=INDIVIDUAL;EMAIL="user03@example.com";PARTS
 TAT=NEEDS-ACTION;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:user03@example.co
 m
ATTENDEE;CN="User 01";CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:mailto:user01@
 example.com
TRANSP:OPAQUE
SUMMARY:Attended Event
DTSTART;TZID=America/New_York:20101028T120000
DTSTAMP:20101018T155513Z
ORGANIZER;CN="User 01":mailto:user01@example.com
SEQUENCE:3
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % {'UID': EVENT_UID}



class EventTests(TestCase):
    """
    Tests for L{Event}.
    """
    def test_uid(self):
        """
        When the C{vevent} attribute of an L{Event} instance is set,
        L{Event.getUID} returns the UID value from it.
        """
        event = Event(None, u'/foo/bar', u'etag', Component.fromString(EVENT))
        self.assertEquals(event.getUID(), EVENT_UID)


    def test_withoutUID(self):
        """
        When an L{Event} has a C{vevent} attribute set to C{None},
        L{Event.getUID} returns C{None}.
        """
        event = Event(None, u'/bar/baz', u'etag')
        self.assertIdentical(event.getUID(), None)



PRINCIPAL_PROPFIND_RESPONSE = """\
<?xml version='1.0' encoding='UTF-8'?>
<multistatus xmlns='DAV:'>
  <response>
    <href>/principals/__uids__/user01/</href>
    <propstat>
      <prop>
        <principal-collection-set>
          <href>/principals/</href>
        </principal-collection-set>
        <calendar-home-set xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/calendars/__uids__/user01</href>
        </calendar-home-set>
        <calendar-user-address-set xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/principals/__uids__/user01/</href>
          <href xmlns='DAV:'>/principals/users/user01/</href>
        </calendar-user-address-set>
        <schedule-inbox-URL xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/inbox/</href>
        </schedule-inbox-URL>
        <schedule-outbox-URL xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/outbox/</href>
        </schedule-outbox-URL>
        <dropbox-home-URL xmlns='http://calendarserver.org/ns/'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/dropbox/</href>
        </dropbox-home-URL>
        <notification-URL xmlns='http://calendarserver.org/ns/'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/notification/</href>
        </notification-URL>
        <displayname>User 01</displayname>
        <principal-URL>
          <href>/principals/__uids__/user01/</href>
        </principal-URL>
        <supported-report-set>
          <supported-report>
            <report>
              <acl-principal-prop-set/>
            </report>
          </supported-report>
          <supported-report>
            <report>
              <principal-match/>
            </report>
          </supported-report>
          <supported-report>
            <report>
              <principal-property-search/>
            </report>
          </supported-report>
          <supported-report>
            <report>
              <expand-property/>
            </report>
          </supported-report>
        </supported-report-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
</multistatus>
"""

_CALENDAR_HOME_PROPFIND_RESPONSE_TEMPLATE = """\
<?xml version='1.0' encoding='UTF-8'?>
<multistatus xmlns='DAV:'>
  <response>
    <href>/calendars/__uids__/user01/</href>
    <propstat>
      <prop>
        %(xmpp)s
        <displayname>User 01</displayname>
        <resourcetype>
          <collection/>
        </resourcetype>
        <owner>
          <href>/principals/__uids__/user01/</href>
        </owner>
        <quota-available-bytes>104855434</quota-available-bytes>
        <quota-used-bytes>2166</quota-used-bytes>
        <current-user-privilege-set>
          <privilege>
            <all/>
          </privilege>
          <privilege>
            <read/>
          </privilege>
          <privilege>
            <read-free-busy xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <write/>
          </privilege>
          <privilege>
            <write-properties/>
          </privilege>
          <privilege>
            <write-content/>
          </privilege>
          <privilege>
            <bind/>
          </privilege>
          <privilege>
            <unbind/>
          </privilege>
          <privilege>
            <unlock/>
          </privilege>
          <privilege>
            <read-acl/>
          </privilege>
          <privilege>
            <write-acl/>
          </privilege>
          <privilege>
            <read-current-user-privilege-set/>
          </privilege>
        </current-user-privilege-set>
        <push-transports xmlns='http://calendarserver.org/ns/'/>
        <pushkey xmlns='http://calendarserver.org/ns/'>/Some/Unique/Value</pushkey>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <getctag xmlns='http://calendarserver.org/ns/'/>
        <calendar-description xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-color xmlns='http://apple.com/ns/ical/'/>
        <calendar-order xmlns='http://apple.com/ns/ical/'/>
        <supported-calendar-component-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-free-busy-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-calendar-transp xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-default-calendar-URL xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-timezone xmlns='urn:ietf:params:xml:ns:caldav'/>
        <source xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-alarms xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-attachments xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-todos xmlns='http://calendarserver.org/ns/'/>
        <refreshrate xmlns='http://apple.com/ns/ical/'/>
        <publish-url xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
  <response>
    <href>/calendars/__uids__/user01/notification/</href>
    <propstat>
      <prop>
        <displayname>notification</displayname>
        <resourcetype>
          <collection/>
          <notification xmlns='http://calendarserver.org/ns/'/>
        </resourcetype>
        <owner>
          <href>/principals/__uids__/user01/</href>
        </owner>
        <quota-available-bytes>104855434</quota-available-bytes>
        <quota-used-bytes>2166</quota-used-bytes>
        <current-user-privilege-set>
          <privilege>
            <all/>
          </privilege>
          <privilege>
            <read/>
          </privilege>
          <privilege>
            <read-free-busy xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <write/>
          </privilege>
          <privilege>
            <write-properties/>
          </privilege>
          <privilege>
            <write-content/>
          </privilege>
          <privilege>
            <bind/>
          </privilege>
          <privilege>
            <unbind/>
          </privilege>
          <privilege>
            <unlock/>
          </privilege>
          <privilege>
            <read-acl/>
          </privilege>
          <privilege>
            <write-acl/>
          </privilege>
          <privilege>
            <read-current-user-privilege-set/>
          </privilege>
        </current-user-privilege-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <xmpp-server xmlns='http://calendarserver.org/ns/'/>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
        <getctag xmlns='http://calendarserver.org/ns/'/>
        <calendar-description xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-color xmlns='http://apple.com/ns/ical/'/>
        <calendar-order xmlns='http://apple.com/ns/ical/'/>
        <supported-calendar-component-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-free-busy-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-calendar-transp xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-default-calendar-URL xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-timezone xmlns='urn:ietf:params:xml:ns:caldav'/>
        <source xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-alarms xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-attachments xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-todos xmlns='http://calendarserver.org/ns/'/>
        <refreshrate xmlns='http://apple.com/ns/ical/'/>
        <push-transports xmlns='http://calendarserver.org/ns/'/>
        <pushkey xmlns='http://calendarserver.org/ns/'/>
        <publish-url xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
  <response>
    <href>/calendars/__uids__/user01/dropbox/</href>
    <propstat>
      <prop>
        <resourcetype>
          <collection/>
          <dropbox-home xmlns='http://calendarserver.org/ns/'/>
        </resourcetype>
        <owner>
          <href>/principals/__uids__/user01/</href>
        </owner>
        <quota-available-bytes>104855434</quota-available-bytes>
        <quota-used-bytes>2166</quota-used-bytes>
        <current-user-privilege-set>
          <privilege>
            <all/>
          </privilege>
          <privilege>
            <read/>
          </privilege>
          <privilege>
            <read-free-busy xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <write/>
          </privilege>
          <privilege>
            <write-properties/>
          </privilege>
          <privilege>
            <write-content/>
          </privilege>
          <privilege>
            <bind/>
          </privilege>
          <privilege>
            <unbind/>
          </privilege>
          <privilege>
            <unlock/>
          </privilege>
          <privilege>
            <read-acl/>
          </privilege>
          <privilege>
            <write-acl/>
          </privilege>
          <privilege>
            <read-current-user-privilege-set/>
          </privilege>
        </current-user-privilege-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <xmpp-server xmlns='http://calendarserver.org/ns/'/>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
        <getctag xmlns='http://calendarserver.org/ns/'/>
        <displayname/>
        <calendar-description xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-color xmlns='http://apple.com/ns/ical/'/>
        <calendar-order xmlns='http://apple.com/ns/ical/'/>
        <supported-calendar-component-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-free-busy-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-calendar-transp xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-default-calendar-URL xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-timezone xmlns='urn:ietf:params:xml:ns:caldav'/>
        <source xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-alarms xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-attachments xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-todos xmlns='http://calendarserver.org/ns/'/>
        <refreshrate xmlns='http://apple.com/ns/ical/'/>
        <push-transports xmlns='http://calendarserver.org/ns/'/>
        <pushkey xmlns='http://calendarserver.org/ns/'/>
        <publish-url xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
  <response>
    <href>/calendars/__uids__/user01/calendar/</href>
    <propstat>
      <prop>
        <getctag xmlns='http://calendarserver.org/ns/'>c2696540-4c4c-4a31-adaf-c99630776828#3</getctag>
        <displayname>calendar</displayname>
        <calendar-color xmlns='http://apple.com/ns/ical/'>#0252D4FF</calendar-color>
        <calendar-order xmlns='http://apple.com/ns/ical/'>1</calendar-order>
        <supported-calendar-component-set xmlns='urn:ietf:params:xml:ns:caldav'>
          <comp name='VEVENT'/>
          <comp name='VTODO'/>
          <comp name='VTIMEZONE'/>
          <comp name='VFREEBUSY'/>
        </supported-calendar-component-set>
        <resourcetype>
          <collection/>
          <calendar xmlns='urn:ietf:params:xml:ns:caldav'/>
        </resourcetype>
        <owner>
          <href>/principals/__uids__/user01/</href>
        </owner>
        <schedule-calendar-transp xmlns='urn:ietf:params:xml:ns:caldav'>
          <opaque/>
        </schedule-calendar-transp>
        <quota-available-bytes>104855434</quota-available-bytes>
        <quota-used-bytes>2166</quota-used-bytes>
        <calendar-timezone xmlns='urn:ietf:params:xml:ns:caldav'><![CDATA[BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.3//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:EDT
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:EST
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
END:VCALENDAR
]]></calendar-timezone>
        <current-user-privilege-set>
          <privilege>
            <all/>
          </privilege>
          <privilege>
            <read/>
          </privilege>
          <privilege>
            <read-free-busy xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <write/>
          </privilege>
          <privilege>
            <write-properties/>
          </privilege>
          <privilege>
            <write-content/>
          </privilege>
          <privilege>
            <bind/>
          </privilege>
          <privilege>
            <unbind/>
          </privilege>
          <privilege>
            <unlock/>
          </privilege>
          <privilege>
            <read-acl/>
          </privilege>
          <privilege>
            <write-acl/>
          </privilege>
          <privilege>
            <read-current-user-privilege-set/>
          </privilege>
        </current-user-privilege-set>
        <pushkey xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <xmpp-server xmlns='http://calendarserver.org/ns/'/>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
        <calendar-description xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-free-busy-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-default-calendar-URL xmlns='urn:ietf:params:xml:ns:caldav'/>
        <source xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-alarms xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-attachments xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-todos xmlns='http://calendarserver.org/ns/'/>
        <refreshrate xmlns='http://apple.com/ns/ical/'/>
        <push-transports xmlns='http://calendarserver.org/ns/'/>
        <publish-url xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
  <response>
    <href>/calendars/__uids__/user01/outbox/</href>
    <propstat>
      <prop>
        <supported-calendar-component-set xmlns='urn:ietf:params:xml:ns:caldav'>
          <comp name='VEVENT'/>
          <comp name='VTODO'/>
          <comp name='VTIMEZONE'/>
          <comp name='VFREEBUSY'/>
        </supported-calendar-component-set>
        <resourcetype>
          <collection/>
          <schedule-outbox xmlns='urn:ietf:params:xml:ns:caldav'/>
        </resourcetype>
        <owner>
          <href>/principals/__uids__/user01/</href>
        </owner>
        <quota-available-bytes>104855434</quota-available-bytes>
        <quota-used-bytes>2166</quota-used-bytes>
        <current-user-privilege-set>
          <privilege>
            <all/>
          </privilege>
          <privilege>
            <read/>
          </privilege>
          <privilege>
            <write/>
          </privilege>
          <privilege>
            <write-properties/>
          </privilege>
          <privilege>
            <write-content/>
          </privilege>
          <privilege>
            <bind/>
          </privilege>
          <privilege>
            <unbind/>
          </privilege>
          <privilege>
            <unlock/>
          </privilege>
          <privilege>
            <read-acl/>
          </privilege>
          <privilege>
            <write-acl/>
          </privilege>
          <privilege>
            <read-current-user-privilege-set/>
          </privilege>
          <privilege>
            <schedule-send xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <schedule xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <read-free-busy xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
        </current-user-privilege-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <xmpp-server xmlns='http://calendarserver.org/ns/'/>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
        <getctag xmlns='http://calendarserver.org/ns/'/>
        <displayname/>
        <calendar-description xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-color xmlns='http://apple.com/ns/ical/'/>
        <calendar-order xmlns='http://apple.com/ns/ical/'/>
        <calendar-free-busy-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-calendar-transp xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-default-calendar-URL xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-timezone xmlns='urn:ietf:params:xml:ns:caldav'/>
        <source xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-alarms xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-attachments xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-todos xmlns='http://calendarserver.org/ns/'/>
        <refreshrate xmlns='http://apple.com/ns/ical/'/>
        <push-transports xmlns='http://calendarserver.org/ns/'/>
        <pushkey xmlns='http://calendarserver.org/ns/'/>
        <publish-url xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
  <response>
    <href>/calendars/__uids__/user01/freebusy</href>
    <propstat>
      <prop>
        <resourcetype>
          <free-busy-url xmlns='http://calendarserver.org/ns/'/>
        </resourcetype>
        <owner>
          <href>/principals/__uids__/user01/</href>
        </owner>
        <quota-available-bytes>104855434</quota-available-bytes>
        <quota-used-bytes>2166</quota-used-bytes>
        <current-user-privilege-set>
          <privilege>
            <read/>
          </privilege>
          <privilege>
            <schedule-deliver xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <schedule xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <all/>
          </privilege>
          <privilege>
            <write/>
          </privilege>
          <privilege>
            <write-properties/>
          </privilege>
          <privilege>
            <write-content/>
          </privilege>
          <privilege>
            <bind/>
          </privilege>
          <privilege>
            <unbind/>
          </privilege>
          <privilege>
            <unlock/>
          </privilege>
          <privilege>
            <read-acl/>
          </privilege>
          <privilege>
            <write-acl/>
          </privilege>
          <privilege>
            <read-current-user-privilege-set/>
          </privilege>
          <privilege>
            <read-free-busy xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
        </current-user-privilege-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <xmpp-server xmlns='http://calendarserver.org/ns/'/>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
        <getctag xmlns='http://calendarserver.org/ns/'/>
        <displayname/>
        <calendar-description xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-color xmlns='http://apple.com/ns/ical/'/>
        <calendar-order xmlns='http://apple.com/ns/ical/'/>
        <supported-calendar-component-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-free-busy-set xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-calendar-transp xmlns='urn:ietf:params:xml:ns:caldav'/>
        <schedule-default-calendar-URL xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-timezone xmlns='urn:ietf:params:xml:ns:caldav'/>
        <source xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-alarms xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-attachments xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-todos xmlns='http://calendarserver.org/ns/'/>
        <refreshrate xmlns='http://apple.com/ns/ical/'/>
        <push-transports xmlns='http://calendarserver.org/ns/'/>
        <pushkey xmlns='http://calendarserver.org/ns/'/>
        <publish-url xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
  <response>
    <href>/calendars/__uids__/user01/inbox/</href>
    <propstat>
      <prop>
        <getctag xmlns='http://calendarserver.org/ns/'>a483dab3-1391-445b-b1c3-5ae9dfc81c2f#0</getctag>
        <displayname>inbox</displayname>
        <supported-calendar-component-set xmlns='urn:ietf:params:xml:ns:caldav'>
          <comp name='VEVENT'/>
          <comp name='VTODO'/>
          <comp name='VTIMEZONE'/>
          <comp name='VFREEBUSY'/>
        </supported-calendar-component-set>
        <resourcetype>
          <collection/>
          <schedule-inbox xmlns='urn:ietf:params:xml:ns:caldav'/>
        </resourcetype>
        <owner>
          <href>/principals/__uids__/user01/</href>
        </owner>
        <calendar-free-busy-set xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/calendar</href>
        </calendar-free-busy-set>
        <schedule-default-calendar-URL xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/calendar</href>
        </schedule-default-calendar-URL>
        <quota-available-bytes>104855434</quota-available-bytes>
        <quota-used-bytes>2166</quota-used-bytes>
        <current-user-privilege-set>
          <privilege>
            <schedule-deliver xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <schedule xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
          <privilege>
            <all/>
          </privilege>
          <privilege>
            <read/>
          </privilege>
          <privilege>
            <write/>
          </privilege>
          <privilege>
            <write-properties/>
          </privilege>
          <privilege>
            <write-content/>
          </privilege>
          <privilege>
            <bind/>
          </privilege>
          <privilege>
            <unbind/>
          </privilege>
          <privilege>
            <unlock/>
          </privilege>
          <privilege>
            <read-acl/>
          </privilege>
          <privilege>
            <write-acl/>
          </privilege>
          <privilege>
            <read-current-user-privilege-set/>
          </privilege>
          <privilege>
            <read-free-busy xmlns='urn:ietf:params:xml:ns:caldav'/>
          </privilege>
        </current-user-privilege-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <xmpp-server xmlns='http://calendarserver.org/ns/'/>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
        <calendar-description xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-color xmlns='http://apple.com/ns/ical/'/>
        <calendar-order xmlns='http://apple.com/ns/ical/'/>
        <schedule-calendar-transp xmlns='urn:ietf:params:xml:ns:caldav'/>
        <calendar-timezone xmlns='urn:ietf:params:xml:ns:caldav'/>
        <source xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-alarms xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-attachments xmlns='http://calendarserver.org/ns/'/>
        <subscribed-strip-todos xmlns='http://calendarserver.org/ns/'/>
        <refreshrate xmlns='http://apple.com/ns/ical/'/>
        <push-transports xmlns='http://calendarserver.org/ns/'/>
        <pushkey xmlns='http://calendarserver.org/ns/'/>
        <publish-url xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
</multistatus>
"""

CALENDAR_HOME_PROPFIND_RESPONSE = _CALENDAR_HOME_PROPFIND_RESPONSE_TEMPLATE % {
    "xmpp": """\
        <xmpp-server xmlns='http://calendarserver.org/ns/'/>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>""",
}

CALENDAR_HOME_PROPFIND_RESPONSE_WITH_XMPP = _CALENDAR_HOME_PROPFIND_RESPONSE_TEMPLATE % {
    "xmpp": """\
        <xmpp-server xmlns='http://calendarserver.org/ns/'>xmpp.example.invalid:1952</xmpp-server>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'>xmpp:pubsub.xmpp.example.invalid?pubsub;node=/CalDAV/another.example.invalid/user01/</xmpp-uri>""",
}

CALENDAR_HOME_PROPFIND_RESPONSE_XMPP_MISSING = _CALENDAR_HOME_PROPFIND_RESPONSE_TEMPLATE % {"xmpp": ""}



class MemoryResponse(object):
    def __init__(self, version, code, phrase, headers, bodyProducer):
        self.version = version
        self.code = code
        self.phrase = phrase
        self.headers = headers
        self.length = bodyProducer.length
        self._bodyProducer = bodyProducer


    def deliverBody(self, protocol):
        protocol.makeConnection(self._bodyProducer)
        d = self._bodyProducer.startProducing(ProtocolToConsumerAdapter(protocol))
        d.addCallback(lambda ignored: protocol.connectionLost(Failure(ResponseDone())))



class OS_X_10_6Mixin:
    """
    Mixin for L{TestCase}s for L{OS_X_10_6}.
    """
    def setUp(self):
        TimezoneCache.create()
        self.record = _DirectoryRecord(
            u"user91", u"user91", u"User 91", u"user91@example.org", u"user91",
        )
        serializePath = self.mktemp()
        os.mkdir(serializePath)
        self.client = OS_X_10_6(
            None,
            "http://127.0.0.1",
            "/principals/users/%s/",
            serializePath,
            self.record,
            None,
        )


    def interceptRequests(self):
        requests = []
        def request(*args, **kwargs):
            result = Deferred()
            requests.append((result, args))
            return result
        self.client._request = request
        return requests



class OS_X_10_6Tests(OS_X_10_6Mixin, TestCase):
    """
    Tests for L{OS_X_10_6}.
    """
    def test_parsePrincipalPROPFINDResponse(self):
        """
        L{Principal._parsePROPFINDResponse} accepts an XML document
        like the one in the response to a I{PROPFIND} request for
        I{/principals/__uids__/<uid>/} and returns a C{PropFindResult}
        representing the data from it.
        """
        principals = self.client._parseMultiStatus(PRINCIPAL_PROPFIND_RESPONSE)
        principal = principals['/principals/__uids__/user01/']
        self.assertEquals(
            principal.getHrefProperties(),
            {
                davxml.principal_collection_set: URL(path='/principals/'),
                caldavxml.calendar_home_set: URL(path='/calendars/__uids__/user01'),
                caldavxml.calendar_user_address_set: (
                    URL(path='/principals/__uids__/user01/'),
                    URL(path='/principals/users/user01/'),
                ),
                caldavxml.schedule_inbox_URL: URL(path='/calendars/__uids__/user01/inbox/'),
                caldavxml.schedule_outbox_URL: URL(path='/calendars/__uids__/user01/outbox/'),
                csxml.dropbox_home_URL: URL(path='/calendars/__uids__/user01/dropbox/'),
                csxml.notification_URL: URL(path='/calendars/__uids__/user01/notification/'),
                davxml.principal_URL: URL(path='/principals/__uids__/user01/'),
            }
        )
        self.assertEquals(
            principal.getTextProperties(),
            {davxml.displayname: 'User 01'})

#         self.assertEquals(
#             principal.getSomething(),
#             {SUPPORTED_REPORT_SET: (
#                     '{DAV:}acl-principal-prop-set',
#                     '{DAV:}principal-match',
#                     '{DAV:}principal-property-search',
#                     '{DAV:}expand-property',
#                     )})


    def test_extractCalendars(self):
        """
        L{OS_X_10_6._extractCalendars} accepts a calendar home
        PROPFIND response body and returns a list of calendar objects
        constructed from the data extracted from the response.
        """
        home = "/calendars/__uids__/user01/"
        calendars = self.client._extractCalendars(
            self.client._parseMultiStatus(CALENDAR_HOME_PROPFIND_RESPONSE), home)
        calendars.sort(key=lambda cal: cal.resourceType)
        calendar, inbox = calendars

        self.assertEquals(calendar.resourceType, caldavxml.calendar)
        self.assertEquals(calendar.name, "calendar")
        self.assertEquals(calendar.url, "/calendars/__uids__/user01/calendar/")
        self.assertEquals(calendar.changeToken, "c2696540-4c4c-4a31-adaf-c99630776828#3")

        self.assertEquals(inbox.resourceType, caldavxml.schedule_inbox)
        self.assertEquals(inbox.name, "inbox")
        self.assertEquals(inbox.url, "/calendars/__uids__/user01/inbox/")
        self.assertEquals(inbox.changeToken, "a483dab3-1391-445b-b1c3-5ae9dfc81c2f#0")

        self.assertEqual({}, self.client.xmpp)


    def test_extractCalendarsXMPP(self):
        """
        If there is XMPP push information in a calendar home PROPFIND response,
        L{OS_X_10_6._extractCalendars} finds it and records it.
        """
        home = "/calendars/__uids__/user01/"
        self.client._extractCalendars(
            self.client._parseMultiStatus(CALENDAR_HOME_PROPFIND_RESPONSE_WITH_XMPP),
            home
        )
        self.assertEqual({
            home: XMPPPush(
                "xmpp.example.invalid:1952",
                "xmpp:pubsub.xmpp.example.invalid?pubsub;node=/CalDAV/another.example.invalid/user01/",
                "/Some/Unique/Value"
            )},
            self.client.xmpp
        )


    def test_handleMissingXMPP(self):
        home = "/calendars/__uids__/user01/"
        self.client._extractCalendars(
            self.client._parseMultiStatus(CALENDAR_HOME_PROPFIND_RESPONSE_XMPP_MISSING), home)
        self.assertEqual({}, self.client.xmpp)


    def test_changeEventAttendee(self):
        """
        OS_X_10_6.changeEventAttendee removes one attendee from an
        existing event and appends another.
        """
        requests = self.interceptRequests()

        vevent = Component.fromString(EVENT)
        attendees = tuple(vevent.mainComponent().properties("ATTENDEE"))
        old = attendees[0]
        new = old.duplicate()
        new.setParameter('CN', 'Some Other Guy')
        event = Event(None, u'/some/calendar/1234.ics', None, vevent)
        self.client._events[event.url] = event
        self.client.changeEventAttendee(event.url, old, new)

        _ignore_result, req = requests.pop(0)

        # iCal PUTs the new VCALENDAR object.
        _ignore_expectedResponseCode, method, url, headers, body = req
        self.assertEquals(method, 'PUT')
        self.assertEquals(url, 'http://127.0.0.1' + event.url)
        self.assertIsInstance(url, str)
        self.assertEquals(headers.getRawHeaders('content-type'), ['text/calendar'])

        consumer = MemoryConsumer()
        yield body.startProducing(consumer)
        vevent = Component.fromString(consumer.value())
        attendees = tuple(vevent.mainComponent().properties("ATTENDEE"))
        self.assertEquals(len(attendees), 2)
        self.assertEquals(attendees[0].parameterValue('CN'), 'User 01')
        self.assertEquals(attendees[1].parameterValue('CN'), 'Some Other Guy')


    def test_addEvent(self):
        """
        L{OS_X_10_6.addEvent} PUTs the event passed to it to the
        server and updates local state to reflect its existence.
        """
        requests = self.interceptRequests()

        calendar = Calendar(caldavxml.calendar, set(('VEVENT',)), u'calendar', u'/mumble/', None)
        self.client._calendars[calendar.url] = calendar

        vcalendar = Component.fromString(EVENT)
        d = self.client.addEvent(u'/mumble/frotz.ics', vcalendar)

        result, req = requests.pop(0)

        # iCal PUTs the new VCALENDAR object.
        expectedResponseCode, method, url, headers, body = req
        self.assertEqual(expectedResponseCode, CREATED)
        self.assertEqual(method, 'PUT')
        self.assertEqual(url, 'http://127.0.0.1/mumble/frotz.ics')
        self.assertIsInstance(url, str)
        self.assertEqual(headers.getRawHeaders('content-type'), ['text/calendar'])

        consumer = MemoryConsumer()
        finished = body.startProducing(consumer)
        def cbFinished(ignored):
            self.assertEqual(
                Component.fromString(consumer.value()),
                Component.fromString(EVENT_AND_TIMEZONE))
        finished.addCallback(cbFinished)

        def requested(ignored):
            response = MemoryResponse(
                ('HTTP', '1', '1'), CREATED, "Created", Headers({}),
                StringProducer(""))
            result.callback(response)
        finished.addCallback(requested)

        return d


    @inlineCallbacks
    def test_addInvite(self):
        """
        L{OS_X_10_6.addInvite} PUTs the event passed to it to the
        server and updates local state to reflect its existence, but
        it also does attendee auto-complete and free-busy checks before
        the PUT.
        """

        calendar = Calendar(caldavxml.calendar, set(('VEVENT',)), u'calendar', u'/mumble/', None)
        self.client._calendars[calendar.url] = calendar

        vcalendar = Component.fromString(EVENT_INVITE)

        self.client.uuid = u'urn:uuid:user01'
        self.client.email = u'mailto:user01@example.com'
        self.client.principalCollection = "/principals/"
        self.client.outbox = "/calendars/__uids__/user01/outbox/"

        @inlineCallbacks
        def _testReport(*args, **kwargs):
            expectedResponseCode, method, url, headers, body = args
            self.assertEqual(expectedResponseCode, (MULTI_STATUS,))
            self.assertEqual(method, 'REPORT')
            self.assertEqual(url, 'http://127.0.0.1/principals/')
            self.assertIsInstance(url, str)
            self.assertEqual(headers.getRawHeaders('content-type'), ['text/xml'])

            consumer = MemoryConsumer()
            yield body.startProducing(consumer)

            response = MemoryResponse(
                ('HTTP', '1', '1'), MULTI_STATUS, "MultiStatus", Headers({}),
                StringProducer("<?xml version='1.0' encoding='UTF-8'?><multistatus xmlns='DAV:' />"))

            returnValue(response)

        @inlineCallbacks
        def _testPost(*args, **kwargs):
            expectedResponseCode, method, url, headers, body = args
            self.assertEqual(expectedResponseCode, OK)
            self.assertEqual(method, 'POST')
            self.assertEqual(url, 'http://127.0.0.1/calendars/__uids__/user01/outbox/')
            self.assertIsInstance(url, str)
            self.assertEqual(headers.getRawHeaders('content-type'), ['text/calendar'])

            consumer = MemoryConsumer()
            yield body.startProducing(consumer)
            self.assertNotEqual(consumer.value().find(kwargs["attendee"]), -1)

            response = MemoryResponse(
                ('HTTP', '1', '1'), OK, "OK", Headers({}),
                StringProducer(""))

            returnValue(response)

        def _testPost02(*args, **kwargs):
            return _testPost(*args, attendee="ATTENDEE:mailto:user02@example.com", **kwargs)

        def _testPost03(*args, **kwargs):
            return _testPost(*args, attendee="ATTENDEE:mailto:user03@example.com", **kwargs)

        @inlineCallbacks
        def _testPut(*args, **kwargs):
            expectedResponseCode, method, url, headers, body = args
            self.assertEqual(expectedResponseCode, CREATED)
            self.assertEqual(method, 'PUT')
            self.assertEqual(url, 'http://127.0.0.1/mumble/frotz.ics')
            self.assertIsInstance(url, str)
            self.assertEqual(headers.getRawHeaders('content-type'), ['text/calendar'])

            consumer = MemoryConsumer()
            yield body.startProducing(consumer)
            self.assertEqual(
                Component.fromString(consumer.value()),
                Component.fromString(EVENT_INVITE))

            response = MemoryResponse(
                ('HTTP', '1', '1'), CREATED, "Created", Headers({}),
                StringProducer(""))

            returnValue(response)

        requests = [_testReport, _testPost02, _testReport, _testPost03, _testPut, ]

        def _requestHandler(*args, **kwargs):
            handler = requests.pop(0)
            return handler(*args, **kwargs)
        self.client._request = _requestHandler
        yield self.client.addInvite('/mumble/frotz.ics', vcalendar)


    def test_deleteEvent(self):
        """
        L{OS_X_10_6.deleteEvent} DELETEs the event at the relative
        URL passed to it and updates local state to reflect its
        removal.
        """
        requests = self.interceptRequests()

        calendar = Calendar(caldavxml.calendar, set(('VEVENT',)), u'calendar', u'/foo/', None)
        event = Event(None, calendar.url + u'bar.ics', None)
        self.client._calendars[calendar.url] = calendar
        self.client._setEvent(event.url, event)

        d = self.client.deleteEvent(event.url)

        result, req = requests.pop()

        expectedResponseCode, method, url = req

        self.assertEqual(expectedResponseCode, NO_CONTENT)
        self.assertEqual(method, 'DELETE')
        self.assertEqual(url, 'http://127.0.0.1' + event.url)
        self.assertIsInstance(url, str)

        self.assertNotIn(event.url, self.client._events)
        self.assertNotIn(u'bar.ics', calendar.events)

        response = MemoryResponse(
            ('HTTP', '1', '1'), NO_CONTENT, "No Content", None,
            StringProducer(""))
        result.callback(response)
        return d


    def test_serialization(self):
        """
        L{OS_X_10_6.serialize} properly generates a JSON document.
        """
        clientPath = os.path.join(self.client.serializePath, "user91-OS_X_10.6")
        self.assertFalse(os.path.exists(clientPath))
        indexPath = os.path.join(clientPath, "index.json")
        self.assertFalse(os.path.exists(indexPath))

        cal1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VEVENT
UID:004f8e41-b071-4b30-bb3b-6aada4adcc10
DTSTART:20120817T113000
DTEND:20120817T114500
DTSTAMP:20120815T154420Z
SEQUENCE:2
SUMMARY:Simple event
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        cal2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VEVENT
UID:00a79cad-857b-418e-a54a-340b5686d747
DTSTART:20120817T113000
DTEND:20120817T114500
DTSTAMP:20120815T154420Z
SEQUENCE:2
SUMMARY:Simple event
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        events = (
            Event(self.client.serializeLocation(), u'/home/calendar/1.ics', u'123.123', Component.fromString(cal1)),
            Event(self.client.serializeLocation(), u'/home/inbox/i1.ics', u'123.123', Component.fromString(cal2)),
        )
        self.client._events.update(dict([[event.url, event] for event in events]))

        calendars = (
            Calendar(str(caldavxml.calendar), set(('VEVENT',)), u'calendar', u'/home/calendar/', "123"),
            Calendar(str(caldavxml.calendar), set(('VTODO',)), u'tasks', u'/home/tasks/', "456"),
            Calendar(str(caldavxml.schedule_inbox), set(('VEVENT', "VTODO",)), u'calendar', u'/home/inbox/', "789"),
        )
        self.client._calendars.update(dict([[calendar.url, calendar] for calendar in calendars]))
        self.client._calendars["/home/calendar/"].events["1.ics"] = events[0]
        self.client._calendars["/home/inbox/"].events["i1.ics"] = events[1]

        self.client.serialize()
        self.assertTrue(os.path.exists(clientPath))
        self.assertTrue(os.path.exists(indexPath))
        self.assertEqual(open(indexPath).read().replace(" \n", "\n"), """{
  "calendars": [
    {
      "changeToken": "123",
      "name": "calendar",
      "resourceType": "{urn:ietf:params:xml:ns:caldav}calendar",
      "componentTypes": [
        "VEVENT"
      ],
      "url": "/home/calendar/",
      "events": [
        "1.ics"
      ]
    },
    {
      "changeToken": "789",
      "name": "calendar",
      "resourceType": "{urn:ietf:params:xml:ns:caldav}schedule-inbox",
      "componentTypes": [
        "VEVENT",
        "VTODO"
      ],
      "url": "/home/inbox/",
      "events": [
        "i1.ics"
      ]
    },
    {
      "changeToken": "456",
      "name": "tasks",
      "resourceType": "{urn:ietf:params:xml:ns:caldav}calendar",
      "componentTypes": [
        "VTODO"
      ],
      "url": "/home/tasks/",
      "events": []
    }
  ],
  "principalURL": null,
  "events": [
    {
      "url": "/home/calendar/1.ics",
      "scheduleTag": null,
      "etag": "123.123",
      "uid": "004f8e41-b071-4b30-bb3b-6aada4adcc10"
    },
    {
      "url": "/home/inbox/i1.ics",
      "scheduleTag": null,
      "etag": "123.123",
      "uid": "00a79cad-857b-418e-a54a-340b5686d747"
    }
  ]
}""")

        event1Path = os.path.join(clientPath, "calendar", "1.ics")
        self.assertTrue(os.path.exists(event1Path))
        self.assertEqual(open(event1Path).read(), cal1)

        event2Path = os.path.join(clientPath, "inbox", "i1.ics")
        self.assertTrue(os.path.exists(event2Path))
        self.assertEqual(open(event2Path).read(), cal2)


    def test_deserialization(self):
        """
        L{OS_X_10_6.deserailize} properly parses a JSON document.
        """

        cal1 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VEVENT
UID:004f8e41-b071-4b30-bb3b-6aada4adcc10
DTSTART:20120817T113000
DTEND:20120817T114500
DTSTAMP:20120815T154420Z
SEQUENCE:2
SUMMARY:Simple event
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
        cal2 = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VEVENT
UID:00a79cad-857b-418e-a54a-340b5686d747
DTSTART:20120817T113000
DTEND:20120817T114500
DTSTAMP:20120815T154420Z
SEQUENCE:2
SUMMARY:Simple event
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

        clientPath = os.path.join(self.client.serializePath, "user91-OS_X_10.6")
        os.mkdir(clientPath)
        indexPath = os.path.join(clientPath, "index.json")
        open(indexPath, "w").write("""{
  "calendars": [
    {
      "changeToken": "321",
      "name": "calendar",
      "resourceType": "{urn:ietf:params:xml:ns:caldav}calendar",
      "componentTypes": [
        "VEVENT"
      ],
      "url": "/home/calendar/",
      "events": [
        "2.ics"
      ]
    },
    {
      "changeToken": "987",
      "name": "calendar",
      "resourceType": "{urn:ietf:params:xml:ns:caldav}schedule-inbox",
      "componentTypes": [
        "VEVENT",
        "VTODO"
      ],
      "url": "/home/inbox/",
      "events": [
        "i2.ics"
      ]
    },
    {
      "changeToken": "654",
      "name": "tasks",
      "resourceType": "{urn:ietf:params:xml:ns:caldav}calendar",
      "componentTypes": [
        "VTODO"
      ],
      "url": "/home/tasks/",
      "events": []
    }
  ],
  "principalURL": null,
  "events": [
    {
      "url": "/home/calendar/2.ics",
      "scheduleTag": null,
      "etag": "321.321",
      "uid": "004f8e41-b071-4b30-bb3b-6aada4adcc10"
    },
    {
      "url": "/home/inbox/i2.ics",
      "scheduleTag": null,
      "etag": "987.987",
      "uid": "00a79cad-857b-418e-a54a-340b5686d747"
    }
  ]
}""")

        os.mkdir(os.path.join(clientPath, "calendar"))
        event1Path = os.path.join(clientPath, "calendar", "2.ics")
        open(event1Path, "w").write(cal1)
        os.mkdir(os.path.join(clientPath, "inbox"))
        event1Path = os.path.join(clientPath, "inbox", "i2.ics")
        open(event1Path, "w").write(cal2)

        self.client.deserialize()

        self.assertEqual(len(self.client._calendars), 3)
        self.assertTrue("/home/calendar/" in self.client._calendars)
        self.assertEqual(self.client._calendars["/home/calendar/"].changeToken, "321")
        self.assertEqual(self.client._calendars["/home/calendar/"].name, "calendar")
        self.assertEqual(self.client._calendars["/home/calendar/"].resourceType, "{urn:ietf:params:xml:ns:caldav}calendar")
        self.assertEqual(self.client._calendars["/home/calendar/"].componentTypes, set(("VEVENT",)))
        self.assertTrue("/home/tasks/" in self.client._calendars)
        self.assertTrue("/home/inbox/" in self.client._calendars)
        self.assertEqual(self.client._calendars["/home/inbox/"].componentTypes, set(("VEVENT", "VTODO",)))
        self.assertEqual(len(self.client._events), 2)
        self.assertTrue("/home/calendar/2.ics" in self.client._events)
        self.assertEqual(self.client._events["/home/calendar/2.ics"].scheduleTag, None)
        self.assertEqual(self.client._events["/home/calendar/2.ics"].etag, "321.321")
        self.assertEqual(self.client._events["/home/calendar/2.ics"].getUID(), "004f8e41-b071-4b30-bb3b-6aada4adcc10")
        self.assertEqual(str(self.client._events["/home/calendar/2.ics"].component), cal1)
        self.assertTrue("/home/inbox/i2.ics" in self.client._events)
        self.assertEqual(self.client._events["/home/inbox/i2.ics"].scheduleTag, None)
        self.assertEqual(self.client._events["/home/inbox/i2.ics"].etag, "987.987")
        self.assertEqual(self.client._events["/home/inbox/i2.ics"].getUID(), "00a79cad-857b-418e-a54a-340b5686d747")
        self.assertEqual(str(self.client._events["/home/inbox/i2.ics"].component), cal2)



class UpdateCalendarTests(OS_X_10_6Mixin, TestCase):
    """
    Tests for L{OS_X_10_6._updateCalendar}.
    """

    _CALENDAR_PROPFIND_RESPONSE_BODY = """\
<?xml version='1.0' encoding='UTF-8'?>
<multistatus xmlns='DAV:'>
  <response>
    <href>/something/anotherthing.ics</href>
    <propstat>
      <prop>
        <resourcetype>
          <collection/>
        </resourcetype>
        <getetag>"None"</getetag>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
  <response>
    <href>/something/else.ics</href>
    <propstat>
      <prop>
        <resourcetype>
          <collection/>
        </resourcetype>
        <getetag>"None"</getetag>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
   </response>
</multistatus>
"""
    _CALENDAR_REPORT_RESPONSE_BODY = """\
<?xml version='1.0' encoding='UTF-8'?>
<multistatus xmlns='DAV:'>
  <response>
    <href>/something/anotherthing.ics</href>
    <status>HTTP/1.1 404 Not Found</status>
  </response>
  <response>
    <href>/something/else.ics</href>
    <propstat>
      <prop>
        <getetag>"ef70beb4cb7da4b2e2950350b09e9a01"</getetag>
        <calendar-data xmlns='urn:ietf:params:xml:ns:caldav'><![CDATA[BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VEVENT
UID:CD54161A13AA8A4649D3781E@caldav.corp.apple.com
DTSTART:20110715T140000Z
DURATION:PT1H
DTSTAMP:20110715T144217Z
SUMMARY:Test2
END:VEVENT
END:VCALENDAR
]]></calendar-data>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
  </response>
</multistatus>
"""

    _CALENDAR_REPORT_RESPONSE_BODY_1 = """\
<?xml version='1.0' encoding='UTF-8'?>
<multistatus xmlns='DAV:'>
  <response>
    <href>/something/anotherthing.ics</href>
    <propstat>
      <prop>
        <getetag>"ef70beb4cb7da4b2e2950350b09e9a01"</getetag>
        <calendar-data xmlns='urn:ietf:params:xml:ns:caldav'><![CDATA[BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VEVENT
UID:anotherthing@caldav.corp.apple.com
DTSTART:20110715T140000Z
DURATION:PT1H
DTSTAMP:20110715T144217Z
SUMMARY:Test1
END:VEVENT
END:VCALENDAR
]]></calendar-data>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
  </response>
</multistatus>
"""

    _CALENDAR_REPORT_RESPONSE_BODY_2 = """\
<?xml version='1.0' encoding='UTF-8'?>
<multistatus xmlns='DAV:'>
  <response>
    <href>/something/else.ics</href>
    <propstat>
      <prop>
        <getetag>"ef70beb4cb7da4b2e2950350b09e9a01"</getetag>
        <calendar-data xmlns='urn:ietf:params:xml:ns:caldav'><![CDATA[BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VEVENT
UID:else@caldav.corp.apple.com
DTSTART:20110715T140000Z
DURATION:PT1H
DTSTAMP:20110715T144217Z
SUMMARY:Test2
END:VEVENT
END:VCALENDAR
]]></calendar-data>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
  </response>
</multistatus>
"""

    def test_eventMissing(self):
        """
        If an event included in the calendar PROPFIND response no longer exists
        by the time a REPORT is issued for that event, the 404 is handled and
        the rest of the normal update logic for that event is skipped.
        """
        requests = self.interceptRequests()

        calendar = Calendar(None, set(('VEVENT',)), 'calendar', '/something/', None)
        self.client._calendars[calendar.url] = calendar
        self.client._updateCalendar(calendar, "1234")
        result, req = requests.pop(0)
        expectedResponseCode, method, url, _ignore_headers, _ignore_body = req
        self.assertEqual('PROPFIND', method)
        self.assertEqual('http://127.0.0.1/something/', url)
        self.assertEqual((MULTI_STATUS,), expectedResponseCode)

        result.callback(
            MemoryResponse(
                ('HTTP', '1', '1'), MULTI_STATUS, "Multi-status", None,
                StringProducer(self._CALENDAR_PROPFIND_RESPONSE_BODY)))

        result, req = requests.pop(0)
        expectedResponseCode, method, url, _ignore_headers, _ignore_body = req
        self.assertEqual('REPORT', method)
        self.assertEqual('http://127.0.0.1/something/', url)
        self.assertEqual((MULTI_STATUS,), expectedResponseCode)

        # Someone else comes along and gets rid of the event
        del self.client._events["/something/anotherthing.ics"]

        result.callback(
            MemoryResponse(
                ('HTTP', '1', '1'), MULTI_STATUS, "Multi-status", None,
                StringProducer(self._CALENDAR_REPORT_RESPONSE_BODY)))

        # Verify that processing proceeded to the response after the one with a
        # 404 status.
        self.assertIn('/something/else.ics', self.client._events)


    def test_multigetBatch(self):
        """
        If an event included in the calendar PROPFIND response no longer exists
        by the time a REPORT is issued for that event, the 404 is handled and
        the rest of the normal update logic for that event is skipped.
        """
        requests = self.interceptRequests()

        self.patch(self.client, "MULTIGET_BATCH_SIZE", 1)

        calendar = Calendar(None, set(('VEVENT',)), 'calendar', '/something/', None)
        self.client._calendars[calendar.url] = calendar
        self.client._updateCalendar(calendar, "1234")
        result, req = requests.pop(0)
        expectedResponseCode, method, url, _ignore_headers, _ignore_body = req
        self.assertEqual('PROPFIND', method)
        self.assertEqual('http://127.0.0.1/something/', url)
        self.assertEqual((MULTI_STATUS,), expectedResponseCode)

        result.callback(
            MemoryResponse(
                ('HTTP', '1', '1'), MULTI_STATUS, "Multi-status", None,
                StringProducer(self._CALENDAR_PROPFIND_RESPONSE_BODY)))

        result, req = requests.pop(0)
        expectedResponseCode, method, url, _ignore_headers, _ignore_body = req
        self.assertEqual('REPORT', method)
        self.assertEqual('http://127.0.0.1/something/', url)
        self.assertEqual((MULTI_STATUS,), expectedResponseCode)

        result.callback(
            MemoryResponse(
                ('HTTP', '1', '1'), MULTI_STATUS, "Multi-status", None,
                StringProducer(self._CALENDAR_REPORT_RESPONSE_BODY_1)))

        self.assertTrue(self.client._events['/something/anotherthing.ics'].etag is not None)
        self.assertTrue(self.client._events['/something/else.ics'].etag is None)

        result, req = requests.pop(0)
        expectedResponseCode, method, url, _ignore_headers, _ignore_body = req
        self.assertEqual('REPORT', method)
        self.assertEqual('http://127.0.0.1/something/', url)
        self.assertEqual((MULTI_STATUS,), expectedResponseCode)

        result.callback(
            MemoryResponse(
                ('HTTP', '1', '1'), MULTI_STATUS, "Multi-status", None,
                StringProducer(self._CALENDAR_REPORT_RESPONSE_BODY_2)))

        self.assertTrue(self.client._events['/something/anotherthing.ics'].etag is not None)
        self.assertTrue(self.client._events['/something/else.ics'].etag is not None)



class VFreeBusyTests(OS_X_10_6Mixin, TestCase):
    """
    Tests for L{OS_X_10_6.requestAvailability}.
    """
    def test_requestAvailability(self):
        """
        L{OS_X_10_6.requestAvailability} accepts a date range and a set of
        account uuids and issues a VFREEBUSY request.  It returns a Deferred
        which fires with a dict mapping account uuids to availability range
        information.
        """
        self.client.uuid = u'urn:uuid:user01'
        self.client.email = u'mailto:user01@example.com'
        self.client.outbox = "/calendars/__uids__/%s/outbox/" % (self.record.uid,)
        requests = self.interceptRequests()

        start = DateTime(2011, 6, 10, 10, 45, 0, tzid=Timezone(utc=True))
        end = DateTime(2011, 6, 10, 11, 15, 0, tzid=Timezone(utc=True))
        d = self.client.requestAvailability(
            start, end, [u"urn:uuid:user05", u"urn:uuid:user10"])

        result, req = requests.pop(0)
        expectedResponseCode, method, url, headers, body = req

        self.assertEqual(OK, expectedResponseCode)
        self.assertEqual('POST', method)
        self.assertEqual(
            'http://127.0.0.1/calendars/__uids__/%s/outbox/' % (self.record.uid,),
            url)

        self.assertEqual(headers.getRawHeaders('originator'), ['mailto:user01@example.com'])
        self.assertEqual(headers.getRawHeaders('recipient'), ['urn:uuid:user05, urn:uuid:user10'])
        self.assertEqual(headers.getRawHeaders('content-type'), ['text/calendar'])

        consumer = MemoryConsumer()
        finished = body.startProducing(consumer)
        def cbFinished(ignored):
            vevent = Component.fromString(consumer.value())
            uid = vevent.resourceUID()
            dtstamp = vevent.mainComponent().propertyValue("DTSTAMP")
            dtstamp = dtstamp.getText()
            self.assertEqual("""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
VERSION:2.0
METHOD:REQUEST
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VFREEBUSY
UID:%(uid)s
DTEND:20110611T000000Z
ATTENDEE:urn:uuid:user05
ATTENDEE:urn:uuid:user10
DTSTART:20110610T000000Z
DTSTAMP:%(dtstamp)s
ORGANIZER:mailto:user01@example.com
SUMMARY:Availability for urn:uuid:user05, urn:uuid:user10
END:VFREEBUSY
END:VCALENDAR
""".replace('\n', '\r\n') % {'uid': uid, 'dtstamp': dtstamp}, consumer.value())

        finished.addCallback(cbFinished)

        def requested(ignored):
            response = MemoryResponse(
                ('HTTP', '1', '1'), OK, "Ok", Headers({}),
                StringProducer(""))
            result.callback(response)
        finished.addCallback(requested)

        return d
