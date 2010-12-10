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
#
##

from twisted.trial.unittest import TestCase

from protocol.url import URL
from protocol.webdav.definitions import davxml
from protocol.caldav.definitions import caldavxml
from protocol.caldav.definitions import csxml

from ical import SnowLeopard


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


CALENDAR_HOME_PROPFIND_RESPONSE = """\
<?xml version='1.0' encoding='UTF-8'?>
<multistatus xmlns='DAV:'>
  <response>
    <href>/calendars/__uids__/user01/</href>
    <propstat>
      <prop>
        <xmpp-server xmlns='http://calendarserver.org/ns/'/>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
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
        <pushkey xmlns='http://calendarserver.org/ns/'/>
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




class SnowLeopardTests(TestCase):
    """
    Tests for L{SnowLeopard}.
    """
    def setUp(self):
        self.client = SnowLeopard(None, "127.0.0.1", 80, None, None)


    def test_parsePrincipalPROPFINDResponse(self):
        """
        L{Principal._parsePROPFINDResponse} accepts an XML document
        like the one in the response to a I{PROPFIND} request for
        I{/principals/__uids__/<uid>/} and returns a C{PropFindResult}
        representing the data from it.
        """
        principals = self.client._parsePROPFINDResponse(PRINCIPAL_PROPFIND_RESPONSE)
        principal = principals['/principals/__uids__/user01/']
        self.assertEquals(
            principal.getHrefProperties(),
            {davxml.principal_collection_set: URL(path='/principals/'),
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
             })
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
        L{SnowLeopard._extractCalendars} accepts a calendar home
        PROPFIND response body and returns a list of calendar objects
        constructed from the data extracted from the response.
        """
        calendars = self.client._extractCalendars(CALENDAR_HOME_PROPFIND_RESPONSE)
        resourceTypes = [resourceType for (resourceType, element) in calendars]
        self.assertEquals(
            resourceTypes,
            sorted([csxml.dropbox_home,
                    csxml.notification,
                    caldavxml.calendar,
                    caldavxml.schedule_inbox,
                    caldavxml.schedule_outbox]))
